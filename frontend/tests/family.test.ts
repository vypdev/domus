import {afterEach, expect, test, vi} from 'vitest';
import {FamilyController} from '../src/application/family-controller';
import type {FamilyReport} from '../src/application/family-controller';
import {EntryReadError} from '../src/application/ports';
import {HttpFamilyServer} from '../src/adapters/family-http';
import '../src/presentation/domus-family';
import corpus from './fixtures/entry-wire.json';

const period = {start: '2026-05-25', end: '2026-06-01'};
const award = {event_id: 'award', cycle_id: 'cycle', occurrence_id: 'work', title: '<img src=x>', amount_minor: 125,
  performed_at: 1_780_261_200_000, verified_at: 1_780_266_000_000, posted_at: 1_780_270_000_000,
  reverses: null, policy_version: 'conserve_total.v1',
  allocation: {mode: 'conserve_total', precision: 2, rounding: null, policy_revision: 0,
    task_override: false, base_minor: 125, total_minor: 125, shares: [['member', 125]]}};
const reversal = {...award, event_id: 'reversal', amount_minor: -125, reverses: 'award', posted_at: 1_780_800_000_000};
const wire = {period, time_zone: 'Europe/Madrid', posted_minor: 0, available_minor: 0, earned_minor: 0,
  pending_verification_minor: 200, pending_posting_minor: 100, completed_count: 2, tracked_count: 1,
  elapsed_ms: 1_800_000, pending_count: 2, pending: [
    {cycle_id: 'waiting', title: 'Clean yard', performed_at: award.performed_at, state: 'verification', allocation: award.allocation},
    {cycle_id: 'verified', title: 'Water plants', performed_at: award.performed_at, state: 'posting', allocation: award.allocation},
  ], history: [reversal, award], next_cursor: 'next'};
const endpoint = {...corpus.standalone.endpoint, deployment: 'standalone' as const};
const context = {installationId: '047cc6fb-dfb0-4fa4-b3c3-e0fe54d116b6', channel: 'edge' as const, subject: 'a'.repeat(32)};

function server(payload: unknown, status = 200) {
  const transport = vi.fn(async (path: string, _init: RequestInit) => {
    const response = new Response(JSON.stringify(payload), {status, headers: {'Content-Type': 'application/json', 'Cache-Control': 'no-store'}});
    Object.defineProperty(response, 'url', {value: endpoint.origin + path}); return response;
  });
  return {http: new HttpFamilyServer(endpoint, transport), transport};
}

test('the private Family adapter preserves signed postings, dates and exact scoped pagination', async () => {
  const {http, transport} = server(wire);
  const report = await http.read(context, period, 'cursor').result;
  expect(report).toMatchObject({period, earned: 0, pendingPosting: 100, pendingVerification: 200, tracked: 1,
    history: [{id: 'reversal', amount: -125, reverses: 'award'}, {id: 'award', amount: 125, reverses: null}]});
  expect(transport.mock.calls[0][0]).toContain('family?start=2026-05-25&end=2026-06-01&limit=8&cursor=cursor');
  expect(new Headers(transport.mock.calls[0][1].headers).get('X-Domus-Context')).toContain(context.subject);
  expect((await server({...wire, history: [{...award, verified_at: null}], next_cursor: null}).http.read(context, period, null).result).cursor).toBeNull();
});

test.each([
  {...wire, period: {...period, start: '2026-05-26'}},
  {...wire, period: {...period, end: '2026-06-02'}},
  {...wire, history: false},
  {...wire, history: Array(26).fill(award)},
  {...wire, tracked_count: 3},
  {...wire, pending: false},
  {...wire, pending: Array(5).fill(wire.pending[0])},
  {...wire, pending_count: 3},
  {...wire, pending: [wire.pending[0], wire.pending[0]]},
  {...wire, completed_count: 1},
  {...wire, available_minor: 1},
  {...wire, history: [{...award, amount_minor: -125}]},
  {...wire, history: [{...reversal, amount_minor: 125}]},
  {...wire, history: [award, award]},
  {...wire, history: [{...award, performed_at: Number.MAX_SAFE_INTEGER}]},
])('Family rejects inconsistent report data %#', async bad => {
  await expect(server(bad).http.read(context, period, null).result).rejects.toMatchObject({code: 'invalid_response'});
});

test('Family refreshes, pages, retains a transient stale view and clears it on scope loss or denial', async () => {
  const first = await server(wire).http.read(context, period, null).result;
  type Deferred = {resolve: (report: FamilyReport) => void; reject: (error: unknown) => void; cancel: ReturnType<typeof vi.fn>};
  const reads: Deferred[] = [];
  const read = vi.fn(() => {
    const cancel = vi.fn();
    const result = new Promise<FamilyReport>((resolve, reject) => reads.push({resolve, reject, cancel}));
    return {result, cancel};
  });
  const publish = vi.fn(), controller = new FamilyController({read}, publish);
  await controller.refresh();
  await controller.more();
  expect(read).not.toHaveBeenCalled();
  const scope = {key: 'one', context, today: '2026-05-31'};
  controller.bind(scope); controller.bind(scope);
  expect(read).toHaveBeenCalledOnce();
  await controller.more();
  const superseding = controller.refresh();
  expect(reads[0].cancel).toHaveBeenCalledOnce();
  reads[0].resolve(first);
  reads[1].resolve(first);
  await superseding;
  expect(publish).toHaveBeenLastCalledWith({state: 'ready', report: first});
  const more = controller.more();
  reads[2].resolve({...first, posted: 100, available: 100, cursor: null, history: [{...first.history[0], id: 'third'}]});
  await more;
  expect(publish.mock.lastCall?.[0]?.report?.history).toHaveLength(3);
  expect(publish.mock.lastCall?.[0]?.report?.posted).toBe(0);
  await controller.more();
  const transient = controller.refresh();
  reads[3].reject(new EntryReadError('unavailable'));
  await transient;
  expect(publish.mock.lastCall?.[0]).toMatchObject({state: 'unavailable', report: {posted: 0}});
  const denied = controller.refresh();
  reads[4].reject(new EntryReadError('forbidden'));
  await denied;
  expect(publish).toHaveBeenLastCalledWith({state: 'unavailable', report: null});
  const unknown = controller.refresh();
  reads[5].reject(new Error('unexpected'));
  await unknown;
  const retired = controller.select('month', '2026-05-31');
  controller.bind(null); controller.bind(null);
  expect(reads[6].cancel).toHaveBeenCalledOnce();
  reads[6].reject(new Error('retired request'));
  await retired;
  expect(publish).toHaveBeenLastCalledWith(null);
});

afterEach(() => {document.querySelector('domus-family')?.remove();});

test('Family shows distinct pending values, contribution, localized signed history and a safe empty state', async () => {
  const node = document.createElement('domus-family'); document.body.append(node); await node.updateComplete;
  const root = node.shadowRoot!;
  expect(root.textContent).not.toContain('Family');
  const first = await server(wire).http.read(context, period, null).result;
  node.today = '2026-05-31'; node.scopeKey = 'member';
  await node.updateComplete;
  expect(root.querySelector('vyp-ha-card')?.state.title).toBe('Your participation');
  node.view = {state: 'loading', report: null}; await node.updateComplete;
  expect(root.querySelector('vyp-ha-feedback')?.state?.message).toBe('Loading Family');
  node.view = {state: 'ready', report: first}; await node.updateComplete;
  expect(root.textContent).toContain('Estimated points awaiting verification');
  expect(root.textContent).toContain('Awaiting verification');
  expect(root.textContent).toContain('Awaiting posting');
  expect(root.textContent).toContain('Clean yard');
  expect(root.textContent).toContain('30 minutes');
  expect(root.textContent).toContain('Reversal −1.25');
  expect(root.textContent).toContain('Award 1.25');
  expect(root.querySelector('img')).toBeNull();
  expect(root.textContent).toContain('Original award');
  expect(root.textContent).toContain('Approved');
  const actions: unknown[] = [];
  node.addEventListener('domus-family-intent', event => actions.push((event as CustomEvent).detail));
  const buttons = [...root.querySelectorAll('vyp-ha-button')];
  buttons.find(button => button.state.label === 'More movements')!.dispatchEvent(new Event('ha-press-request'));
  buttons.find(button => button.state.label === 'Refresh')!.dispatchEvent(new Event('ha-press-request'));
  const select = root.querySelector('select')!;
  select.value = 'month'; select.dispatchEvent(new Event('change'));
  const date = root.querySelector('input')!;
  date.value = ''; date.dispatchEvent(new Event('input'));
  root.querySelector('form')!.dispatchEvent(new SubmitEvent('submit', {cancelable: true}));
  date.value = '2026-05-31'; date.dispatchEvent(new Event('input'));
  root.querySelector('form')!.dispatchEvent(new SubmitEvent('submit', {cancelable: true}));
  expect(actions).toEqual([{type: 'more'}, {type: 'refresh'}, {type: 'period', mode: 'month', anchor: '2026-05-31'}]);
  node.language = 'es'; node.view = {state: 'unavailable', report: {...first, history: [], tracked: 0, cursor: null}};
  await node.updateComplete;
  expect(root.textContent).toContain('Saldo disponible');
  expect(root.textContent).toContain('0,00');
  expect(root.textContent).toContain('Estas tareas no tienen un inicio registrado.');
  expect(root.textContent).toContain('Todavía no hay movimientos de puntos.');
  expect(root.querySelector('vyp-ha-feedback')?.state?.message).toContain('últimos valores');
  node.view = {state: 'unavailable', report: null}; await node.updateComplete;
  expect(root.textContent).not.toContain('Saldo disponible');
  node.view = {state: 'ready', report: {...first, pending: [], pendingCount: 0,
    history: [{...first.history[1], verifiedAt: null}]}};
  await node.updateComplete;
  expect(root.textContent).not.toContain('Aprobado');
});

test('the bounded pending list marks when additional work contributes to its totals', async () => {
  const node = document.createElement('domus-family');
  document.body.append(node);
  const pending = Array.from({length: 4}, (_, i) => ({...wire.pending[i % 2], cycle_id: 'cycle-' + i}));
  const report = await server({...wire, completed_count: 6, pending_count: 5, pending}).http.read(context, period, null).result;
  node.scopeKey = 'member'; node.view = {state: 'ready', report};
  await node.updateComplete;
  expect(node.shadowRoot!.textContent).toContain('Recent completions shown out of all pending work (4/5)');
});
