import {afterEach, expect, test, vi} from 'vitest';
import {HttpRewardsServer} from '../src/adapters/reward-http';
import {REWARD_JOURNAL_KEY, RewardsSessionJournal} from '../src/adapters/reward-journal';
import {RewardsController} from '../src/application/rewards-controller';
import type {RewardRequest, RewardsScope, RewardsServer, RewardsView} from '../src/application/rewards-controller';
import type {EntryRead} from '../src/application/ports';
import {revisionValue} from '../src/domain/administration';
import {MEMBER_ROLES} from '../src/domain/administration-commands';
import {managementAction, rewardCommand, rewardCost, rewardRoles} from '../src/domain/rewards';
import type {RewardCommand, RewardReport} from '../src/domain/rewards';
import '../src/presentation/domus-rewards';
import corpus from './fixtures/entry-wire.json';

const context = {installationId: '047cc6fb-dfb0-4fa4-b3c3-e0fe54d116b6', channel: 'edge' as const, subject: 'a'.repeat(32)};
const scope: RewardsScope = {key: 'verified', context, memberId: 'member', readOnly: false};
const revision = revisionValue('1'), laterRevision = revisionValue('2'), exactRevision = revisionValue('9007199254740993');
const configure = {action: 'reward.configure', enabled: true, expected_revision: '0'} as const;
const makeOffer = {action: 'reward.offer', offer_id: null, title: 'Movie night', cost_minor: 200,
  enabled: true, eligible_roles: MEMBER_ROLES, expected_revision: '0'} as const;
const reserve = {action: 'reward.request', offer_id: 'offer', expected_revision: revision} as const;
const approve = {action: 'reward.approve', redemption_id: 'request'} as const;
const deliver = {action: 'reward.deliver', redemption_id: 'request'} as const;
const cancel = {action: 'reward.cancel', redemption_id: 'request', expected_revision: exactRevision, reason: 'Later'} as const;
const original: RewardRequest = {key: 'original', scope: scope.key, command: reserve};
const offerWire = {offer_id: 'offer', title: 'Movie night', cost_minor: 200, enabled: true, eligible_roles: MEMBER_ROLES, revision: 1};
const requestWire = {redemption_id: 'request', member_id: 'member', offer_id: 'offer', title: '<img src=x>',
  offer_revision: 1, cost_minor: 200, requested_at: 100, stage: 'requested', revision: 1, approval: null, closed: null, cancellation_reason: null};
const decision = {actor_member_id: 'admin', at: 200};
const closed = {actor_member_id: 'admin', at: 300};
const wire = {enabled: true, revision: 1, may_manage: true, balance: {posted_minor: 500, reserved_minor: 200},
  catalog: [{offer: offerWire, eligible: true}], requests: [requestWire], next_cursor: 'next'};
const report: RewardReport = {enabled: true, revision, mayManage: true, posted: 500, reserved: 200, available: 300,
  catalog: [{id: 'offer', title: 'Movie night', cost: 200, enabled: true, eligible: true, roles: MEMBER_ROLES, revision}],
  requests: [{id: 'request', title: '<img src=x>', cost: 200, stage: 'requested', revision,
    requestedAt: 100, approvedAt: null, closedAt: null, cancellationReason: null}], cursor: 'next'};
const failure = (code: string) => ({state: 'blocked', code, message: 'Blocked.', action_required: 'Review.', correlation_id: 'cor_test'});
const csrf = {csrf_token: 'c'.repeat(64)};
const receipt = (result: unknown, state = 'committed') => ({state, archived_by: state === 'historical' ? 'restore' : null,
  operation_id: 'operation', created_at: 100, result, message: 'Saved.', action_required: 'Review.'});
const read = <T>(result: T): EntryRead<T> => ({result: Promise.resolve(result), cancel: vi.fn()});
const lost = <T>(): EntryRead<T> => ({result: Promise.reject(new Error('lost')), cancel: vi.fn()});

function http(replies: readonly (readonly [number, unknown])[], deployment: 'native' | 'standalone' = 'standalone') {
  const endpoint = {...corpus[deployment].endpoint, deployment};
  let index = 0;
  const fetch = vi.fn(async (path: string, _init: RequestInit) => {
    const [status, payload] = replies[index++];
    const raw = JSON.stringify(payload).replaceAll('"exact-next"', '9007199254740994');
    const response = new Response(raw, {status, headers: {'Content-Type': 'application/json', 'Cache-Control': 'no-store'}});
    Object.defineProperty(response, 'url', {value: endpoint.origin + path}); return response;
  });
  return {server: new HttpRewardsServer(endpoint, fetch), fetch};
}

test('reward commands are exact, closed, and never supply an actor or a caller-selected price', () => {
  for (const command of [configure, makeOffer, reserve, approve, deliver, cancel]) {
    expect(rewardCommand(command)).toEqual(command);
  }
  expect(rewardCommand({...makeOffer, offer_id: 'offer', expected_revision: exactRevision})).toMatchObject({expected_revision: exactRevision});
  expect(managementAction(reserve.action)).toBe(false);
  expect(managementAction(cancel.action)).toBe(false);
  expect(managementAction(approve.action)).toBe(true);
  for (const invalid of [null, true, [], {}, {...configure, enabled: 1}, {...configure, subject: 'forged'},
    {action: configure.action, enabled: true, revision: '0'}, {...reserve, cost_minor: 1},
    {...makeOffer, offer_id: '../foreign'}, {...makeOffer, title: ' '}, {...makeOffer, cost_minor: 0},
    {...cancel, reason: ' '}, {...approve, redemption_id: null}]) expect(() => rewardCommand(invalid)).toThrow();
  for (const cost of [null, 0, 1.01, 1_000_001]) expect(() => rewardCost(cost)).toThrow();
  for (const roles of [null, [], ['administrator','adult','restricted','viewer','unknown'], ['stranger'], ['adult','adult']]) {
    expect(() => rewardRoles(roles)).toThrow();
  }
});

test.each(['native', 'standalone'] as const)('%s preserves scoped reads, exact revisions, and every committed result', async mode => {
  const {server, fetch} = http([
    [200, wire],
    [200, {...wire, enabled: false, revision: 0, next_cursor: null}],
    [200, csrf], [200, receipt({enabled: true, revision: 1})],
    [200, csrf], [200, receipt(offerWire)],
    [200, csrf], [200, receipt({...offerWire, revision: 'exact-next'})],
    [200, csrf], [200, receipt({redemption_id: 'request', stage: 'requested', revision: 1, requester_member_id: 'member'})],
    [200, csrf], [200, receipt({redemption_id: 'request', stage: 'funding_hold', revision: 2})],
    [200, csrf], [200, receipt({redemption_id: 'request', stage: 'delivered', revision: 3})],
    [200, csrf], [200, receipt({redemption_id: 'request', stage: 'cancelled', revision: 'exact-next', requester_member_id: 'member'})],
    [200, receipt({redemption_id: 'request', stage: 'approved', revision: 2}, 'historical')],
    [404, failure('operation_missing')],
    [409, failure('unavailable')],
  ], mode);
  expect(await server.read(scope, null).result).toEqual(report);
  expect(await server.read(scope, 'opaque/+?').result).toMatchObject({enabled: false, revision: '0', cursor: null});
  for (const [command, stage] of [
    [configure, null], [makeOffer, null], [{...makeOffer, offer_id: 'offer', expected_revision: exactRevision}, null],
    [reserve, 'requested'], [approve, 'funding_hold'], [deliver, 'delivered'], [cancel, 'cancelled'],
  ] as const) expect(await server.send(scope, {...original, command}).result).toEqual({kind: 'committed', stage});
  expect(await server.original(scope, {...original, command: approve}).result).toEqual({kind: 'historical', stage: 'approved'});
  expect(await server.original(scope, original).result).toBeNull();
  await expect(server.original(scope, original).result).rejects.toMatchObject({code: 'unavailable'});
  expect(fetch.mock.calls[1][0]).toContain('cursor=opaque%2F%2B%3F');
  expect(fetch.mock.calls[7][1].body).toContain('"expected_revision":9007199254740993');
  const headers = new Headers(fetch.mock.calls[7][1].headers);
  expect(headers.get('Idempotency-Key')).toBe('original');
  expect(headers.get('X-CSRF-Token')).toBe('c'.repeat(64));
  expect(headers.get('X-Domus-Context')).toContain(context.subject);
});

test('reward reads reject mismatched member, clock, balance, stage and ledger evidence', async () => {
  const approved = {...requestWire, stage: 'approved', approval: decision};
  const cancelled = {...approved, stage: 'cancelled', closed, cancellation_reason: 'Later'};
  const delivered = {...approved, stage: 'delivered', closed};
  const {server} = http([[200, {...wire, requests: [approved, {...delivered, redemption_id: 'delivered'}, {...cancelled, redemption_id: 'cancelled'}]}]]);
  expect((await server.read(scope, null).result).requests.map(row => row.stage)).toEqual(['approved','delivered','cancelled']);
  const cancelledBeforeReview = http([[200, {...wire, requests: [{...cancelled, approval: null}]}]]);
  expect((await cancelledBeforeReview.server.read(scope, null).result).requests[0].approvedAt).toBeNull();
  const malformed = [
    {...wire, balance: {posted_minor: -Number.MAX_SAFE_INTEGER, reserved_minor: 1}},
    {...wire, revision: 0}, {...wire, catalog: false}, {...wire, catalog: Array(65).fill(wire.catalog[0])},
    {...wire, requests: false}, {...wire, requests: Array(26).fill(requestWire)},
    {...wire, catalog: [wire.catalog[0], wire.catalog[0]]}, {...wire, requests: [requestWire, requestWire]},
    ...[
      {...requestWire, member_id: 'outsider'}, {...requestWire, requested_at: Number.MAX_SAFE_INTEGER},
      {...requestWire, cancellation_reason: 'Unexpected'}, {...requestWire, closed},
      {...approved, approval: null}, {...approved, approval: {...decision, at: 99}},
      {...delivered, closed: {...closed, at: 150}}, {...cancelled, cancellation_reason: null},
      {...delivered, closed: null},
    ].map(row => ({...wire, requests: [row]})),
  ];
  for (const data of malformed) await expect(http([[200, data]]).server.read(scope, null).result).rejects.toMatchObject({code: 'invalid_response'});
});

test('receipt validation and errors preserve known effects without trusting mismatched facts', async () => {
  const {server} = http([
    [200, csrf], [409, failure('insufficient_reward_points')],
    [200, csrf], [403, failure('unrecognized')],
    [200, csrf], [503, failure('unavailable')],
    [404, failure('unrecognized')],
  ]);
  expect(await server.send(scope, original).result).toEqual({kind: 'rejected', reason: 'insufficient_reward_points'});
  expect(await server.send(scope, original).result).toEqual({kind: 'rejected', reason: 'rejected'});
  await expect(server.send(scope, original).result).rejects.toMatchObject({code: 'unavailable'});
  await expect(server.original(scope, original).result).rejects.toMatchObject({code: 'unavailable'});
  const own = {redemption_id: 'request', stage: 'requested', revision: 1, requester_member_id: 'member'};
  for (const [command, result] of [
    [configure, {enabled: false, revision: 1}],
    [configure, {enabled: true, revision: 2}],
    [{...makeOffer, offer_id: 'expected'}, offerWire],
    [makeOffer, {...offerWire, title: 'Changed'}],
    [makeOffer, {...offerWire, cost_minor: 1}],
    [makeOffer, {...offerWire, enabled: false}],
    [makeOffer, {...offerWire, eligible_roles: ['adult']}],
    [makeOffer, {...offerWire, revision: 2}],
    [reserve, {...own, requester_member_id: 'other'}], [reserve, {...own, stage: 'approved'}],
    [reserve, {...own, revision: 2}],
    [cancel, {...own, stage: 'requested'}],
    [cancel, {...own, stage: 'cancelled', revision: 2}],
    [approve, {redemption_id: 'different', stage: 'approved', revision: 2}],
  ] as const) {
    await expect(http([[200, receipt(result)]]).server.original(scope, {...original, command}).result).rejects.toMatchObject({code: 'invalid_response'});
  }
});

function journal() {
  const values = new Map<string, string>();
  const journal = new RewardsSessionJournal({getItem: key => values.get(key) ?? null,
    setItem: (key, value) => {values.set(key, value);}, removeItem: key => {values.delete(key);}});
  return {journal, values};
}

test('the reward journal recovers only canonical original commands for the verified owner', () => {
  const f = journal();
  expect(f.journal.open(scope.key)).toBeNull();
  f.journal.save(original);
  expect(f.journal.open(scope.key)).toEqual(original);
  expect(f.journal.open('replaced')).toBeNull();
  f.values.set(REWARD_JOURNAL_KEY, 'x'.repeat(4097));
  expect(() => f.journal.open(scope.key)).toThrow();
  f.values.set(REWARD_JOURNAL_KEY, ' ' + JSON.stringify(original));
  expect(() => f.journal.open(scope.key)).toThrow();
});

function controller() {
  const j = journal();
  const load = vi.fn<RewardsServer['read']>(() => read(report));
  const send = vi.fn<RewardsServer['send']>(() => read({kind: 'committed', stage: 'requested'}));
  const original = vi.fn<RewardsServer['original']>(() => read(null));
  const view = vi.fn<(value: RewardsView | null) => void>();
  const balance = vi.fn(async () => {});
  const app = new RewardsController({read: load, send, original}, j.journal, {requestKey: () => 'key'}, view, balance);
  const current = () => view.mock.lastCall?.[0];
  return {app, load, send, original, view, current, balance, ...j};
}

test('rewards controller retires protected facts and reloads the authoritative balance after mutations', async () => {
  const f = controller();
  await f.app.refresh(); await f.app.more(); await f.app.submit(reserve); await f.app.recover();
  f.app.bind(scope); f.app.bind({...scope});
  await f.app.submit(reserve); await f.app.refresh();
  await vi.waitFor(() => expect(f.current()?.report).toEqual(report));
  f.load.mockReturnValueOnce(read({...report, requests: [{...report.requests[0], id: 'older'}], cursor: null}));
  await f.app.more(); await f.app.more();
  expect(f.current()?.report?.requests.map(item => item.id)).toEqual(['request', 'older']);
  await f.app.submit({wrong: true});
  expect(f.current()?.notice).toBe('unavailable');
  f.send.mockReturnValueOnce(read({kind: 'rejected', reason: 'revision_conflict'}));
  await f.app.submit(reserve);
  expect(f.balance).toHaveBeenCalledOnce();
  expect(f.current()?.result).toEqual({kind: 'rejected', reason: 'revision_conflict'});
  f.load.mockReturnValueOnce(read({...report, mayManage: false}));
  await f.app.refresh();
  await f.app.submit(approve);
  expect(f.send).toHaveBeenCalledTimes(1);
  f.load.mockReturnValueOnce(lost());
  await f.app.refresh();
  expect(f.current()).toMatchObject({report: null, notice: 'unavailable'});
  await f.app.submit(reserve);
  await f.app.refresh();
  expect(f.current()).toMatchObject({report, notice: null});
  f.app.bind(null);
  expect(f.current()).toBeNull();
});

test('reward recovery looks up the same request after reload, resends only that key, and respects read-only mode', async () => {
  const f = controller();
  f.app.bind(scope);
  await vi.waitFor(() => expect(f.current()?.busy).toBe(false));
  f.send.mockReturnValueOnce(lost());
  await f.app.submit(reserve);
  expect(f.current()).toMatchObject({pending: true, notice: 'uncertain'});
  await f.app.submit(reserve);
  const saved = f.journal.open(scope.key)!;
  f.original.mockReturnValueOnce(lost());
  await f.app.recover();
  expect(f.current()?.notice).toBe('uncertain');
  f.app.bind({...scope, readOnly: true});
  await vi.waitFor(() => expect(f.current()?.busy).toBe(false));
  await f.app.submit(reserve);
  await f.app.recover();
  expect(f.send).toHaveBeenCalledOnce();
  f.app.bind(scope);
  await vi.waitFor(() => expect(f.current()?.busy).toBe(false));
  await f.app.recover();
  expect(f.send.mock.calls[1][1]).toEqual(saved);
  expect(f.current()).toMatchObject({pending: false, result: {kind: 'committed'}});
  f.send.mockReturnValueOnce(lost());
  await f.app.submit(reserve);
  f.original.mockReturnValueOnce(read({kind: 'historical', stage: 'requested'}));
  await f.app.recover();
  expect(f.current()?.result?.kind).toBe('historical');
  f.values.set(REWARD_JOURNAL_KEY, 'bad');
  f.app.bind({...scope, key: 'new'});
  expect(f.current()).toMatchObject({pending: true, notice: 'unavailable'});
});

test('retired reward responses cannot appear in a new member scope or clear its data', async () => {
  const f = controller();
  let complete!: (value: RewardReport) => void;
  const cancel = vi.fn();
  f.load.mockReturnValueOnce({result: new Promise(resolve => {complete = resolve;}), cancel});
  f.app.bind(scope);
  f.app.bind({...scope, key: 'new'});
  await vi.waitFor(() => expect(f.current()?.busy).toBe(false));
  complete({...report, mayManage: false});
  await Promise.resolve();
  expect(cancel).toHaveBeenCalledOnce();
  expect(f.current()?.report).toBe(report);
  let reject!: (error: Error) => void;
  f.load.mockReturnValueOnce({result: new Promise((_resolve, fail) => {reject = fail;}), cancel});
  const retiring = f.app.refresh();
  f.app.bind(scope);
  await vi.waitFor(() => expect(f.current()?.busy).toBe(false));
  reject(new Error('retired'));
  await retiring;
  expect(f.current()?.report).toBe(report);
});

const mounted: HTMLElement[] = [];
afterEach(() => {for (const element of mounted.splice(0)) element.remove();});
function component() {
  const node = document.createElement('domus-rewards'); document.body.append(node); mounted.push(node);
  const root = node.shadowRoot!;
  const events = vi.fn(); node.addEventListener('domus-rewards-intent', events);
  const button = (label: string) => [...root.querySelectorAll('vyp-ha-button')].find(item => item.state.label === label);
  const press = (label: string) => {const control = button(label); expect(control).toBeDefined(); control!.dispatchEvent(new Event('ha-press-request'));};
  const label = <T extends HTMLInputElement | HTMLSelectElement>(value: string, selector = 'input'): T =>
    [...root.querySelectorAll('label')].find(item => item.textContent?.trim().startsWith(value))!.querySelector<T>(selector)!;
  const type = (value: string, input: string) => {
    const control = label<HTMLInputElement>(value);
    control.value = input; control.dispatchEvent(new Event('input')); return control;
  };
  const change = (control: HTMLInputElement, checked: boolean) => {
    control.checked = checked; control.dispatchEvent(new Event('change'));
  };
  const submit = (target: HTMLFormElement) => target.dispatchEvent(new Event('submit', {cancelable: true}));
  return {node, root, events, button, press, label, type, change, submit};
}
const initial: RewardsView = {scope, report: null, pending: false, busy: false, result: null, notice: null};

test('rewards render optional catalog, balance reasons, exact confirmation, and safe lifecycle text', async () => {
  const f = component(), {node, root, events, press, submit, type} = f;
  await node.updateComplete;
  expect(root.textContent).not.toContain('Rewards');
  node.view = {...initial, busy: true}; await node.updateComplete;
  expect(root.querySelector('vyp-ha-feedback')?.state?.message).toBe('Loading rewards');
  node.view = {...initial, pending: true, notice: 'uncertain'};
  await node.updateComplete; press('Check reward request'); press('Refresh rewards');
  expect(events.mock.calls.map(([event]) => event.detail)).toEqual([{type: 'recover'}, {type: 'refresh'}]);
  node.view = {...initial, report: {...report, enabled: false, mayManage: false, catalog: [], requests: [], cursor: null}};
  await node.updateComplete;
  expect(root.textContent).toContain('Rewards are disabled');
  expect(root.textContent).toContain('There are no rewards in the catalog.');
  expect(root.textContent).toContain('You have no reward requests.');
  const base = report.catalog[0];
  node.view = {...initial, report: {...report, mayManage: false, catalog: [
    base, {...base, id: 'inactive', enabled: false}, {...base, id: 'restricted', eligible: false}, {...base, id: 'expensive', cost: 301},
  ]}};
  await node.updateComplete;
  for (const message of ['This reward is disabled.', 'Your household role is not eligible', 'You need more available points']) {
    expect(root.textContent).toContain(message);
  }
  press('More reward requests');
  press('Request reward'); await node.updateComplete;
  expect(root.textContent).toContain('Available after the reservation 1.00');
  press('Go back'); await node.updateComplete;
  press('Request reward'); await node.updateComplete;
  const before = events.mock.calls.length;
  node.view = {...node.view, busy: true}; await node.updateComplete;
  submit(root.querySelector('form')!);
  expect(events.mock.calls).toHaveLength(before);
  node.view = {...node.view, busy: false}; await node.updateComplete;
  submit(root.querySelector('form')!); await node.updateComplete;
  expect(events.mock.lastCall?.[0].detail).toEqual({type: 'submit', command: reserve});
  press('Cancel request'); await node.updateComplete;
  submit(root.querySelector('form')!);
  expect(events.mock.lastCall?.[0].detail).toEqual({type: 'submit', command: reserve});
  press('Go back'); await node.updateComplete;
  press('Cancel request'); await node.updateComplete;
  type('Reason for cancellation', 'Later'); await node.updateComplete;
  submit(root.querySelector('form')!);
  expect(events.mock.lastCall?.[0].detail).toEqual({type: 'submit',
    command: {action: 'reward.cancel', redemption_id: 'request', expected_revision: revision, reason: 'Later'}});
  const request = report.requests[0];
  node.view = {...initial, result: {kind: 'rejected', reason: 'insufficient_reward_points'},
    report: {...report, mayManage: false, available: -200, requests: [
      request, {...request, id: 'approved', stage: 'approved', approvedAt: 200},
      {...request, id: 'held', stage: 'funding_hold', approvedAt: 200},
      {...request, id: 'delivered', stage: 'delivered', approvedAt: 200, closedAt: 300},
      {...request, id: 'cancelled', stage: 'cancelled', closedAt: 400, cancellationReason: 'Later'},
    ]}};
  await node.updateComplete;
  for (const message of ['Awaiting approval', 'Approved for delivery', 'Points needed to cover active reservations 2.00',
    'Spending recorded −2.00', 'Reservation released', 'Later']) expect(root.textContent).toContain(message);
  expect(root.querySelector('img')).toBeNull();
  expect(root.querySelector('vyp-ha-feedback')?.state?.message).toContain('Your available points do not cover');
  node.language = 'es'; node.view = {...node.view, result: {kind: 'historical', stage: 'delivered'}};
  await node.updateComplete;
  expect(root.textContent).toContain('Puntos necesarios para cubrir las reservas activas 2,00');
  expect(root.querySelector('vyp-ha-feedback')?.state?.message).toContain('anterior a una restauración');
  node.view = {...node.view, result: {kind: 'committed', stage: 'delivered'}};
  await node.updateComplete;
  expect(root.querySelector('vyp-ha-feedback')?.state?.message).toBe('Entregada');
});

test('catalog editing keeps the selected revision and review uses a member-shared code with explicit delivery', async () => {
  const f = component(), {node, root, events, press, label, type, change, submit} = f;
  node.view = {...initial, report: {...report, enabled: false, revision: '0'}};
  await node.updateComplete;
  press('Enable rewards');
  expect(events.mock.lastCall?.[0].detail).toEqual({type: 'submit', command: configure});
  node.view = {...initial, report, result: {kind: 'committed', stage: null}};
  await node.updateComplete;
  expect(root.querySelector('vyp-ha-feedback')?.state?.message).toBe('Reward change saved.');
  press('Disable rewards');
  expect(events.mock.lastCall?.[0].detail).toEqual({type: 'submit', command: {...configure, enabled: false, expected_revision: revision}});
  const form = root.querySelector('form')!;
  submit(form);
  expect(events.mock.lastCall?.[0].detail.command.action).toBe('reward.configure');
  type('Reward name', 'Movie night'); type('Price in points', '2,00');
  change(label<HTMLInputElement>('Reward enabled'), false);
  change(label<HTMLInputElement>('Viewer'), false);
  await node.updateComplete; submit(form);
  expect(events.mock.lastCall?.[0].detail).toEqual({type: 'submit', command: {...makeOffer, enabled: false,
    eligible_roles: MEMBER_ROLES.slice(0, 3)}});
  const choose = label<HTMLSelectElement>('Edit reward', 'select');
  choose.value = 'offer'; choose.dispatchEvent(new Event('change')); await node.updateComplete;
  expect(label<HTMLInputElement>('Price in points').value).toBe('2.00');
  submit(form);
  expect(events.mock.lastCall?.[0].detail.command).toEqual({...makeOffer, offer_id: 'offer', expected_revision: revision});
  choose.value = ''; choose.dispatchEvent(new Event('change')); await node.updateComplete;
  expect(label<HTMLInputElement>('Price in points').value).toBe('');
  choose.value = 'offer'; choose.dispatchEvent(new Event('change')); await node.updateComplete;
  node.view = {...node.view, report: {...report, catalog: [{...report.catalog[0], revision: laterRevision}]}};
  await node.updateComplete;
  expect(root.textContent).toContain('The reward or request changed.');
  expect(f.button('Save reward')?.disabled).toBe(true);
  press('Go back'); await node.updateComplete;
  expect(label<HTMLInputElement>('Reward name').value).toBe('');

  type('Request code', 'request'); await node.updateComplete;
  press('Approve request'); expect(events.mock.lastCall?.[0].detail).toEqual({type: 'submit', command: approve});
  expect(f.button('Record delivery')?.disabled).toBe(true);
  change(label<HTMLInputElement>('I delivered this reward'), true); await node.updateComplete;
  press('Record delivery');
  expect(events.mock.lastCall?.[0].detail).toEqual({type: 'submit', command: deliver});
  node.view = {...initial, scope: {...scope, key: 'another', readOnly: true}, report};
  await node.updateComplete;
  expect(label<HTMLInputElement>('Request code').value).toBe('');
  expect(f.button('Record delivery')?.disabled).toBe(true);
});
