import {afterEach, expect, test, vi} from 'vitest';
import {HttpAutomationRunHistory} from '../src/adapters/automation-run-history-http';
import {AutomationRunHistoryController} from '../src/application/automation-run-history';
import type {AutomationRun, AutomationRunHistoryScope, AutomationRunHistoryServer, AutomationRunHistoryView, AutomationRunPage}
  from '../src/application/automation-run-history';
import {EntryReadError} from '../src/application/ports';
import type {EntryRead} from '../src/application/ports';
import {revisionValue} from '../src/domain/administration';
import '../src/presentation/domus-automation-run-history';

const scope: AutomationRunHistoryScope = {key: 'home-owner', memberId: 'member', readOnly: false, authorization: 'member-1-policy-1',
  context: {installationId: '01234567-89ab-cdef-0123-456789abcdef', channel: 'edge', subject: 'a'.repeat(32)}};
const made: AutomationRun = {operationId: 'made', revision: revisionValue('1'), time: 1000,
  taskCreated: true, historical: false, taskOccurrenceId: 'task'};
const skipped: AutomationRun = {operationId: 'skipped', revision: revisionValue('2'), time: 2000,
  taskCreated: false, historical: false, taskOccurrenceId: null};
const retained = {...made, operationId: 'retained', historical: true, taskOccurrenceId: null};
const current = {items: [made], next: 'cursor'};
const older = {items: [skipped], next: null};

const settled = <T>(value: T): EntryRead<T> => ({result: Promise.resolve(value), cancel: vi.fn()});
const failed = (error: unknown = new EntryReadError('unavailable')): EntryRead<never> =>
  ({result: Promise.reject(error), cancel: vi.fn()});

function fixture() {
  const page = vi.fn<AutomationRunHistoryServer['page']>(() => settled(current));
  const publish = vi.fn();
  const history = new AutomationRunHistoryController({page}, publish);
  const last = () => publish.mock.lastCall?.[0] as AutomationRunHistoryView | null;
  return {page, publish, history, last};
}

test('history retries the same older request and can restart from recent results', async () => {
  const f = fixture();
  await f.history.handle('open');
  f.history.bind(scope, 'rule', 'UTC');
  expect(f.last()?.phase).toBe('closed');
  await f.history.handle('retry');
  await f.history.handle('latest');
  await f.history.handle('older');
  expect(f.page).not.toHaveBeenCalled();

  const reading = f.history.handle('open');
  expect(f.last()?.phase).toBe('loading');
  await f.history.handle('open');
  await reading;
  await f.history.handle('open');
  expect(f.page).toHaveBeenCalledTimes(1);
  expect(f.last()).toEqual({phase: 'ready', items: [made], hasOlder: true, timeZone: 'UTC'});
  f.history.bind({...scope}, 'rule', 'UTC');
  expect(f.last()?.phase).toBe('ready');

  f.page.mockReturnValueOnce(failed(new Error('offline')));
  await f.history.handle('older');
  expect(f.last()).toMatchObject({phase: 'unavailable', items: [made]});
  f.page.mockReturnValueOnce(settled(older));
  await f.history.handle('retry');
  expect(f.page.mock.calls.slice(-2)).toEqual([[scope, 'rule', 'cursor'], [scope, 'rule', 'cursor']]);
  expect(f.last()).toMatchObject({phase: 'ready', items: [skipped], hasOlder: false});
  await f.history.handle('older');
  expect(f.page).toHaveBeenCalledTimes(3);
  await f.history.handle('latest');
  expect(f.page).toHaveBeenLastCalledWith(scope, 'rule', null);
  f.page.mockReturnValueOnce(settled('expired'));
  await f.history.handle('older');
  expect(f.last()).toMatchObject({phase: 'expired', items: [], hasOlder: false});
  await f.history.handle('latest');
  expect(f.page).toHaveBeenLastCalledWith(scope, 'rule', null);
  expect(f.last()?.items).toEqual([made]);
});

test('scope and rule changes cancel stale results and current access denial clears details', async () => {
  const f = fixture();
  f.history.bind(scope, 'rule', 'UTC');
  await f.history.handle('open');
  const pending = Promise.withResolvers<AutomationRunPage>();
  const cancel = vi.fn();
  f.page.mockReturnValueOnce({result: pending.promise, cancel});
  const oldRule = f.history.handle('older');
  f.history.bind(scope, 'different-rule', 'UTC');
  pending.resolve(older);
  await oldRule;
  expect(cancel).toHaveBeenCalledOnce();
  expect(f.last()).toMatchObject({phase: 'closed', items: []});
  await f.history.handle('open');
  f.page.mockReturnValueOnce(failed(new EntryReadError('forbidden')));
  await f.history.handle('older');
  expect(f.last()).toMatchObject({phase: 'denied', items: [], hasOlder: false});
  await f.history.handle('close');
  f.page.mockReturnValueOnce(failed(new EntryReadError('authentication_required')));
  await f.history.handle('open');
  expect(f.last()?.phase).toBe('denied');

  f.history.bind({...scope, readOnly: true}, 'different-rule', 'UTC');
  expect(f.last()?.phase).toBe('closed');
  f.history.bind({...scope, readOnly: true}, 'different-rule', 'Europe/Madrid');
  expect(f.last()?.timeZone).toBe('Europe/Madrid');

  const other = Promise.withResolvers<AutomationRunPage>();
  f.page.mockReturnValueOnce({result: other.promise, cancel: vi.fn()});
  const inFlight = f.history.handle('open');
  f.history.bind({...scope, key: 'new-member'}, 'different-rule', 'Europe/Madrid');
  other.reject(new EntryReadError('unavailable'));
  await inFlight;
  expect(f.last()).toMatchObject({phase: 'closed', items: []});
  f.history.bind(scope, null, 'UTC');
  expect(f.last()).toBeNull();
  f.history.bind(scope, 'rule', null);
  f.history.bind(null, null, null);
});

test('a verified access change retires an open history with the same member and rule', async () => {
  const f = fixture();
  f.history.bind(scope, 'rule', 'UTC');
  await f.history.handle('open');
  const pending = Promise.withResolvers<AutomationRunPage>();
  const cancel = vi.fn();
  f.page.mockReturnValueOnce({result: pending.promise, cancel});
  const read = f.history.handle('older');
  const updated = {...scope, authorization: 'member-2-policy-1'};
  f.history.bind(updated, 'rule', 'UTC');
  expect(f.last()).toMatchObject({phase: 'closed', items: []});
  pending.resolve(older);
  await read;
  expect(cancel).toHaveBeenCalledOnce();
  expect(f.last()?.items).toEqual([]);
  f.page.mockReturnValueOnce(failed(new EntryReadError('forbidden')));
  await f.history.handle('open');
  expect(f.page).toHaveBeenLastCalledWith(updated, 'rule', null);
  expect(f.last()).toMatchObject({phase: 'denied', items: []});
});

const target = {origin: 'https://domus.local', applicationBase: '/', deployment: 'standalone'} as const;
const wire = {operation_id: 'made', created_at: 1000, rule_revision: '1',
  condition_matched: true, task_created: true, historical: false, task_occurrence_id: 'task'};
const envelope = (items: readonly unknown[], next: string | null = null) =>
  ({rule_id: 'rule', items, next_cursor: next});
const errorBody = (code: string) =>
  ({state: 'blocked', code, message: 'Unable to read.', action_required: 'Try again.', correlation_id: 'cor_history'});

test('transport validates the selected rule, bounded page, date, historical link and expiry', async () => {
  let payload: unknown = envelope([wire]), status = 200;
  const transport = vi.fn(async (route: string, _init: RequestInit) => {
    const response = new Response(JSON.stringify(payload), {status,
      headers: {'Content-Type': 'application/json', 'Cache-Control': 'no-store'}});
    Object.defineProperty(response, 'url', {value: target.origin + route});
    return response;
  });
  const server = new HttpAutomationRunHistory(target, transport);
  await expect(server.page(scope, 'rule', null).result).resolves.toEqual({items: [made], next: null});
  expect(transport.mock.lastCall?.[0]).toBe('/api/v1/automation/drafts/rule/runs');
  expect(transport.mock.lastCall?.[1].method).toBe('GET');
  const sizes = Array.from({length: 25}, (_, i) => ({...wire, operation_id: 'operation-' + i}));
  payload = envelope(sizes, 'more');
  await expect(server.page(scope, 'rule', 'signed+=cursor').result).resolves.toMatchObject({next: 'more'});
  expect(transport.mock.lastCall?.[0]).toBe('/api/v1/automation/drafts/rule/runs?cursor=signed%2B%3Dcursor');
  for (const invalid of [
    {...envelope([wire]), rule_id: 'other'}, {...envelope([wire]), items: {}},
    envelope([...sizes, wire]), envelope([wire, wire]), envelope([wire], 'too-early'),
    envelope(sizes, ''), envelope(sizes, 'same'),
    envelope([{...wire, historical: true}]), envelope([{...wire, created_at: 8_700_000_000_000_000}]),
    envelope([{...wire, condition_matched: false}]),
    envelope([{...wire, task_created: false, condition_matched: false}]),
  ]) {
    payload = invalid;
    await expect(server.page(scope, 'rule', 'same').result).rejects.toMatchObject({code: 'invalid_response'});
  }
  payload = envelope([{...wire, task_occurrence_id: null, historical: true}]);
  await expect(server.page(scope, 'rule', null).result).resolves.toMatchObject({
    items: [{...made, historical: true, taskOccurrenceId: null}],
  });
  status = 422; payload = errorBody('invalid_task_cursor');
  await expect(server.page(scope, 'rule', 'stale').result).resolves.toBe('expired');
  await expect(server.page(scope, 'rule', null).result).rejects.toMatchObject({code: 'invalid_response'});
  payload = errorBody('invalid_request');
  await expect(server.page(scope, 'rule', 'stale').result).rejects.toMatchObject({code: 'invalid_response'});
  status = 403; payload = errorBody('permission_denied');
  await expect(server.page(scope, 'rule', 'stale').result).rejects.toMatchObject({code: 'forbidden'});
});

afterEach(() => document.querySelectorAll('domus-automation-run-history').forEach(node => node.remove()));

test('the history panel localizes empty, unavailable, expired, denied and exact retained outcomes', async () => {
  const element = document.createElement('domus-automation-run-history');
  document.body.append(element);
  await element.updateComplete;
  const root = element.shadowRoot!;
  expect(root.querySelector('vyp-ha-card')).toBeNull();
  const intents = vi.fn(), task = vi.fn();
  element.addEventListener('domus-automation-run-history-intent', intents);
  element.addEventListener('domus-automation-task-intent', task);
  const view = async (phase: AutomationRunHistoryView['phase'], items: readonly AutomationRun[] = [], hasOlder = false) => {
    element.view = {phase, items, hasOlder, timeZone: 'UTC'};
    await element.updateComplete;
  };
  const press = (label: string) => {
    const button = [...root.querySelectorAll('vyp-ha-button')].find(node => node.state?.label === label);
    expect(button).toBeDefined();
    button!.dispatchEvent(new CustomEvent('ha-press-request'));
  };

  await view('closed');
  press('Show run history');
  expect(intents.mock.lastCall?.[0].detail).toBe('open');
  expect(root.querySelector('section')).toBeNull();
  await view('loading');
  expect(root.querySelector('section')?.getAttribute('aria-busy')).toBe('true');
  expect(root.querySelector('vyp-ha-feedback')?.state?.message).toContain('Loading manual runs');
  await view('ready');
  expect(root.textContent).toContain('You have no manual runs');
  await view('ready', [skipped, made, retained], true);
  expect(root.querySelectorAll('li')).toHaveLength(3);
  expect(root.querySelectorAll('a')).toHaveLength(1);
  expect(root.querySelector('time')?.dateTime).toBe('1970-01-01T00:00:02.000Z');
  expect(root.textContent).toContain('Result from before restoration.');
  root.querySelector('a')!.click();
  expect(task.mock.lastCall?.[0].detail).toEqual({type: 'select', occurrenceId: 'task'});
  press('Older runs');
  expect(root.activeElement?.tagName).toBe('SECTION');

  element.language = 'es';
  await view('unavailable', [made]);
  expect(root.querySelector('vyp-ha-feedback')?.state?.message).toContain('no está disponible');
  expect(root.textContent).toContain('Tarea creada.');
  press('Volver a intentar');
  expect(intents.mock.lastCall?.[0].detail).toBe('retry');
  await view('expired');
  expect(root.querySelector('vyp-ha-feedback')?.state?.message).toContain('ha caducado');
  press('Ejecuciones recientes');
  expect(intents.mock.lastCall?.[0].detail).toBe('latest');
  await view('denied');
  expect(root.querySelector('vyp-ha-feedback')?.state?.message).toContain('Tus permisos actuales');
  press('Ocultar historial');
  expect(intents.mock.lastCall?.[0].detail).toBe('close');
});
