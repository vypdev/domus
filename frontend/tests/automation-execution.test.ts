import {afterEach, expect, test, vi} from 'vitest';
import {HttpAutomationExecution} from '../src/adapters/automation-execution-http';
import {AUTOMATION_EXECUTION_JOURNAL_KEY, AutomationExecutionSessionJournal} from '../src/adapters/automation-execution-journal';
import type {DraftScope} from '../src/application/automation-drafts';
import {AutomationExecutionController} from '../src/application/automation-execution';
import type {AutomationConfiguration, AutomationExecutionRequest, AutomationExecutionResult,
  AutomationExecutionServer, AutomationExecutionView} from '../src/application/automation-execution';
import {EntryReadError} from '../src/application/ports';
import type {EntryRead} from '../src/application/ports';
import {revisionValue} from '../src/domain/administration';
import '../src/presentation/domus-automation-execution';

const one = revisionValue('1'), two = revisionValue('2'), three = revisionValue('3');
const scope: DraftScope = {key: 'private-scope', memberId: 'member', readOnly: false,
  context: {installationId: '01234567-89ab-cdef-0123-456789abcdef', channel: 'edge', subject: 'a'.repeat(32)}};
const selection = {id: 'rule', revision: two};
const inactive: AutomationConfiguration = {id: 'rule', latestRevision: two, latestTitle: 'Check supplies', control: null};
const active: AutomationConfiguration = {...inactive,
  control: {ruleRevision: one, controlRevision: three, enabled: true, title: 'Check the pantry'}};
const enabled: AutomationExecutionResult = {kind: 'committed', action: 'configure',
  operationId: 'enable-operation', ruleRevision: two, enabled: true};
const madeTask: AutomationExecutionResult = {kind: 'committed', action: 'run', operationId: 'run-operation',
  ruleRevision: one, taskOccurrenceId: 'the-created-task'};
const runRequest: AutomationExecutionRequest = {kind: 'run', ruleId: 'rule', ruleRevision: one,
  controlRevision: three, key: 'previous-run', scope: scope.key};
const enableRequest: AutomationExecutionRequest = {kind: 'configure', ruleId: 'rule', ruleRevision: two,
  controlRevision: '0', enabled: true, key: 'previous-enable', scope: scope.key};

const settled = <T>(value: T): EntryRead<T> => ({result: Promise.resolve(value), cancel: vi.fn()});
const failed = (error = new EntryReadError('unavailable')): EntryRead<never> => ({result: Promise.reject(error), cancel: vi.fn()});

function fixture() {
  const storage = new Map<string, string>();
  const journal = new AutomationExecutionSessionJournal({getItem: key => storage.get(key) ?? null,
    setItem: (key, value) => {storage.set(key, value);}, removeItem: key => {storage.delete(key);}});
  const server = {
    state: vi.fn<AutomationExecutionServer['state']>(() => settled(active)),
    send: vi.fn<AutomationExecutionServer['send']>(() => settled(madeTask)),
    original: vi.fn<AutomationExecutionServer['original']>(() => settled({kind: 'missing'})),
  };
  const publish = vi.fn();
  const controller = () => new AutomationExecutionController(server, journal, {requestKey: () => 'new-key'}, publish);
  const last = () => publish.mock.lastCall?.[0] as AutomationExecutionView | null;
  return {storage, journal, server, publish, controller, last};
}

test('explicitly confirms a saved revision and separately identifies the enabled revision', async () => {
  const f = fixture(), owner = f.controller();
  await owner.handle('run');
  owner.bind(scope, null);
  expect(f.last()).toBeNull();
  await owner.handle('enable');
  f.server.state.mockReturnValueOnce(settled(inactive));
  owner.bind(scope, selection);
  await owner.handle('run');
  expect(f.server.send).not.toHaveBeenCalled();
  await vi.waitFor(() => expect(f.last()?.configuration).toEqual(inactive));
  await owner.handle('confirm');
  await owner.handle('disable');
  expect(f.last()?.confirmation).toBeNull();
  await owner.handle('enable');
  expect(f.last()?.confirmation).toEqual({title: 'Check supplies',
    command: {kind: 'configure', ruleId: 'rule', ruleRevision: two, controlRevision: '0', enabled: true}});
  expect(f.server.send).not.toHaveBeenCalled();
  owner.bind({...scope, readOnly: true}, selection);
  expect(f.last()?.readOnly).toBe(true);
  await owner.handle('confirm');
  await owner.handle('cancel');
  expect(f.last()?.confirmation).toBeNull();
  expect(f.server.send).not.toHaveBeenCalled();
  owner.bind(scope, selection);
  await owner.handle('enable');
  f.server.send.mockReturnValueOnce(settled(enabled));
  await owner.handle('confirm');
  expect(f.server.send).toHaveBeenCalledWith(scope, {...enableRequest, key: 'new-key'});
  expect(f.last()).toMatchObject({result: enabled, pending: false, busy: false, configuration: active});
  expect(f.journal.open(scope.key)).toBeNull();
  await owner.handle('run');
  expect(f.last()?.confirmation).toMatchObject({title: 'Check the pantry',
    command: {kind: 'run', ruleRevision: one, controlRevision: three}});
  await owner.handle('enable');
  expect(f.last()?.confirmation?.command).toMatchObject({enabled: true, ruleRevision: two, controlRevision: three});
  await owner.handle('disable');
  expect(f.last()?.confirmation?.command).toMatchObject({enabled: false, ruleRevision: one, controlRevision: three});
  f.server.send.mockReturnValueOnce(settled({kind: 'stale'}));
  await owner.handle('confirm');
  expect(f.last()).toMatchObject({notice: 'stale', configuration: active});
  owner.bind(null, null);
  expect(f.last()).toBeNull();
});

test('a lost response recovers the same journaled run after navigation and reload', async () => {
  const f = fixture(), owner = f.controller();
  owner.bind(scope, selection);
  await vi.waitFor(() => expect(f.last()?.configuration).toEqual(active));
  await owner.handle('recover');
  expect(f.server.original).not.toHaveBeenCalled();
  f.server.send.mockReturnValueOnce(failed());
  await owner.handle('run');
  await owner.handle('confirm');
  const expected = {...runRequest, key: 'new-key'};
  expect(f.journal.open(scope.key)).toEqual(expected);
  expect(f.last()).toMatchObject({notice: 'uncertain', pending: true});
  await owner.handle('run');
  expect(f.last()?.confirmation).toBeNull();
  owner.bind(scope, {id: 'another-rule', revision: one});
  expect(f.last()?.pending).toBe(true);
  owner.bind(null, null);
  const reopened = f.controller();
  reopened.bind({...scope, readOnly: true}, null);
  await vi.waitFor(() => expect(f.last()).toMatchObject({pending: true, busy: false}));
  await reopened.handle('recover');
  expect(f.server.original).toHaveBeenCalledWith({...scope, readOnly: true}, expected);
  expect(f.server.send).toHaveBeenCalledTimes(1);
  reopened.bind(scope, null);
  await reopened.handle('recover');
  expect(f.server.send).toHaveBeenLastCalledWith(scope, expected);
  expect(f.last()).toMatchObject({result: madeTask, pending: false, configuration: null});
  expect(f.journal.open(scope.key)).toBeNull();
});

test('stale loads retire on scope changes and current authorization can deny pending receipts', async () => {
  const f = fixture(), owner = f.controller();
  const delayed = Promise.withResolvers<AutomationConfiguration>();
  const cancel = vi.fn();
  f.server.state.mockReturnValueOnce({result: delayed.promise, cancel});
  owner.bind(scope, selection);
  owner.bind({...scope, key: 'other-scope'}, selection);
  delayed.resolve(inactive);
  await vi.waitFor(() => expect(f.last()?.configuration).toEqual(active));
  expect(cancel).toHaveBeenCalledOnce();
  f.server.state.mockReturnValueOnce(failed());
  await owner.handle('reload');
  expect(f.last()).toMatchObject({configuration: null, notice: 'unavailable'});
  await owner.handle('reload');
  expect(f.last()).toMatchObject({configuration: active, notice: null});
  owner.bind(null, null);
  f.journal.save(runRequest);
  const reloaded = f.controller();
  reloaded.bind(scope, selection);
  await vi.waitFor(() => expect(f.last()?.configuration).toEqual(active));
  f.server.original.mockReturnValueOnce(failed(new EntryReadError('forbidden')));
  await reloaded.handle('recover');
  expect(f.last()).toMatchObject({notice: 'denied', configuration: null, pending: false});
  expect(f.journal.open(scope.key)).toBeNull();

  f.storage.set(AUTOMATION_EXECUTION_JOURNAL_KEY, '{}');
  const malformed = f.controller();
  malformed.bind(scope, selection);
  await vi.waitFor(() => expect(f.last()?.configuration).toEqual(active));
  expect(f.last()?.notice).toBe('unavailable');
  await malformed.handle('run');
  await malformed.handle('confirm');
  expect(f.server.send).not.toHaveBeenCalled();
  expect(f.last()?.notice).toBe('unavailable');
});

test('recovery tolerates an unavailable status read and discards a canceled request failure', async () => {
  const f = fixture();
  f.journal.save(runRequest);
  const owner = f.controller();
  f.server.state.mockReturnValueOnce({result: Promise.reject(new Error('network failure')), cancel: vi.fn()});
  owner.bind(scope, null);
  await vi.waitFor(() => expect(f.last()).toMatchObject({pending: true, notice: 'uncertain', busy: false}));
  f.server.original.mockReturnValueOnce(settled(madeTask));
  await owner.handle('recover');
  expect(f.last()).toMatchObject({result: madeTask, pending: false});

  const delayed = Promise.withResolvers<AutomationConfiguration>();
  f.server.state.mockReturnValueOnce({result: delayed.promise, cancel: vi.fn()});
  owner.bind(scope, selection);
  owner.bind(null, null);
  delayed.reject(new EntryReadError('unavailable'));
  await vi.waitFor(() => expect(f.last()).toBeNull());

  f.server.state.mockReturnValueOnce(failed(new EntryReadError('authentication_required')));
  owner.bind(scope, selection);
  await vi.waitFor(() => expect(f.last()).toMatchObject({notice: 'denied', pending: false}));
});

test('the request journal accepts only current scope and exact revision identities', () => {
  const f = fixture();
  expect(f.journal.open(scope.key)).toBeNull();
  f.journal.save(enableRequest);
  expect(f.journal.open(scope.key)).toEqual(enableRequest);
  expect(f.journal.open('next-owner')).toBeNull();
  expect(f.storage.size).toBe(0);
  const later = {...enableRequest, controlRevision: one};
  f.journal.save(later);
  expect(f.journal.open(scope.key)).toEqual(later);
  f.journal.clear(later);
  expect(() => f.journal.save({...runRequest, enabled: true} as AutomationExecutionRequest)).toThrow();
  expect(() => f.journal.save({...runRequest, controlRevision: '0'} as AutomationExecutionRequest)).toThrow();
});

const target = {origin: 'https://domus.example', deployment: 'standalone' as const, applicationBase: '/'};
const common = {rule_id: 'rule', rule_revision: '1', control_revision: '3', member_id: 'member'};
const completedWire = {...common, run_id: 'run', condition_matched: true, task_occurrence_id: 'the-created-task',
  task_operation_id: 'task-operation'};
const envelope = (result: unknown) => ({state: 'committed', archived_by: null, operation_id: 'run-operation',
  created_at: 100, result, message: 'Recorded.', action_required: 'See activity.'});
const wireError = (code: string) => ({state: 'blocked', code, message: 'Unable to continue.',
  action_required: 'Review the state.', correlation_id: 'cor_fixture'});
function response(route: string, body: unknown, status = 200) {
  const answer = new Response(JSON.stringify(body), {status,
    headers: {'Content-Type': 'application/json', 'Cache-Control': 'no-store'}});
  Object.defineProperty(answer, 'url', {value: target.origin + route});
  return answer;
}

test('transport verifies the exact enabled rule, request body and committed or historical receipt', async () => {
  let state: unknown = {rule_id: 'rule', latest_revision: '2', latest_title: 'Check supplies', control: null};
  let command: unknown = envelope(completedWire);
  let status = 200;
  const transport = vi.fn(async (route: string, init: RequestInit) => {
    if (route.endsWith('/auth/csrf')) return response(route, {csrf_token: 'c'.repeat(64)});
    if (init.method === 'GET' && route.endsWith('/execution')) return response(route, state);
    return response(route, command, status);
  });
  const server = new HttpAutomationExecution(target, transport);
  await expect(server.state(scope, 'rule').result).resolves.toEqual(inactive);
  state = {...state as object, control: {rule_revision: '1', control_revision: '3', enabled: true, title: 'Check the pantry'}};
  await expect(server.state(scope, 'rule').result).resolves.toEqual(active);
  await expect(server.send(scope, runRequest).result).resolves.toEqual(madeTask);
  const wrote = transport.mock.lastCall!;
  expect(wrote[0]).toBe('/api/v1/automation/drafts/rule/runs');
  expect(JSON.parse(String(wrote[1].body))).toEqual({rule_revision: '1', control_revision: '3'});
  expect(new Headers(wrote[1].headers).get('idempotency-key')).toBe(runRequest.key);
  await expect(server.original(scope, runRequest).result).resolves.toEqual(madeTask);
  expect(transport.mock.lastCall?.[0]).toBe('/api/v1/automation/execution/requests/run/previous-run');

  command = {...envelope({...completedWire, condition_matched: false, task_occurrence_id: null, task_operation_id: null}),
    state: 'historical', archived_by: 'restore'};
  await expect(server.original(scope, runRequest).result).resolves.toEqual({
    ...madeTask, kind: 'historical', taskOccurrenceId: null,
  });
  command = {...envelope({...common, rule_revision: '2', control_revision: '1', enabled: true}),
    operation_id: enabled.operationId};
  await expect(server.send(scope, enableRequest).result).resolves.toEqual(enabled);
  expect(JSON.parse(String(transport.mock.lastCall?.[1].body))).toEqual({
    rule_revision: '2', expected_control_revision: '0', enabled: true,
  });
  for (const [code, expected] of [['revision_conflict', 'stale'], ['automation_disabled', 'disabled'],
    ['idempotency_conflict', 'rejected']]) {
    status = 409; command = wireError(code);
    await expect(server.send(scope, runRequest).result).resolves.toEqual({kind: expected});
  }
  status = 404; command = wireError('operation_missing');
  await expect(server.original(scope, runRequest).result).resolves.toEqual({kind: 'missing'});
  status = 403; command = wireError('permission_denied');
  await expect(server.send(scope, runRequest).result).rejects.toMatchObject({code: 'forbidden'});
  await expect(server.original(scope, runRequest).result).rejects.toMatchObject({code: 'forbidden'});
});

test('receipt shape and ownership must match before a write can be confirmed', async () => {
  let data: unknown = envelope({...completedWire, member_id: 'different-member'});
  const server = new HttpAutomationExecution(target, async route => response(route, data));
  for (const invalid of [
    data,
    envelope({...completedWire, rule_id: 'other-rule'}),
    envelope({...completedWire, rule_revision: '2'}),
    envelope({...completedWire, control_revision: '4'}),
    envelope({...completedWire, task_operation_id: null}),
    envelope({...completedWire, condition_matched: false}),
    {...envelope(completedWire), archived_by: 'restore'},
    {...envelope(completedWire), state: 'historical'},
  ]) {
    data = invalid;
    await expect(server.original(scope, runRequest).result).rejects.toMatchObject({code: 'invalid_response'});
  }
  for (const invalid of [
    {...common, member_id: 'other', rule_revision: '2', control_revision: '1', enabled: true},
    {...common, rule_id: 'other', rule_revision: '2', control_revision: '1', enabled: true},
    {...common, rule_revision: '1', control_revision: '1', enabled: true},
    {...common, rule_revision: '2', control_revision: '1', enabled: false},
    {...common, rule_revision: '2', control_revision: '2', enabled: true},
  ]) {
    data = envelope(invalid);
    await expect(server.original(scope, enableRequest).result).rejects.toMatchObject({code: 'invalid_response'});
  }
  data = {rule_id: 'other', latest_revision: '2', latest_title: 'Other', control: null};
  await expect(server.state(scope, 'rule').result).rejects.toMatchObject({code: 'invalid_response'});
});

afterEach(() => document.querySelectorAll('domus-automation-execution').forEach(element => element.remove()));

test('the manual automation panel localizes exact confirmations, outcomes and task navigation', async () => {
  const element = document.createElement('domus-automation-execution');
  document.body.append(element);
  await element.updateComplete;
  const root = element.shadowRoot!;
  let current: AutomationExecutionView = {configuration: inactive, confirmation: null, result: null, notice: null,
    busy: false, pending: false, readOnly: false};
  const view = async (patch: Partial<AutomationExecutionView>) => {
    current = {...current, ...patch}; element.view = current; await element.updateComplete;
  };
  const button = (label: string) => [...root.querySelectorAll('vyp-ha-button')].find(node => node.state?.label === label)!;
  const press = (label: string) => button(label).dispatchEvent(new CustomEvent('ha-press-request'));
  const intents = vi.fn(), task = vi.fn();
  element.addEventListener('domus-automation-execution-intent', intents);
  element.addEventListener('domus-automation-task-intent', task);
  expect(root.querySelector('vyp-ha-card')).toBeNull();
  await view({});
  expect(root.textContent).toContain('Disabled');
  press('Enable saved revision');
  expect(intents.mock.lastCall?.[0].detail).toBe('enable');
  await view({confirmation: {title: inactive.latestTitle, command: enableRequest}});
  expect(button('Enable this revision')).toBeDefined();
  expect(root.activeElement?.textContent).toBe('Confirm automation action');
  press('Cancel');
  expect(intents.mock.lastCall?.[0].detail).toBe('cancel');
  await view({configuration: {...active, latestRevision: one}, confirmation: null, result: enabled});
  expect(button('Enable saved revision')).toBeUndefined();
  expect(root.textContent).toContain('Rule enabled.');
  await view({configuration: active, confirmation: {title: active.control!.title, command: runRequest},
    result: madeTask});
  expect(button('Run this revision')).toBeDefined();
  root.querySelector('a')!.click();
  expect(task.mock.lastCall?.[0].detail).toEqual({type: 'select', occurrenceId: 'the-created-task'});
  element.language = 'es';
  await view({readOnly: true, confirmation: {title: active.control!.title,
    command: {...enableRequest, ruleRevision: one, enabled: false}}, result: {...enabled, enabled: false}});
  expect(button('Deshabilitar futuras ejecuciones').disabled).toBe(true);
  expect(root.textContent).toContain('Futuras ejecuciones deshabilitadas.');
  await view({readOnly: false, configuration: null, confirmation: null, notice: 'uncertain', pending: true, busy: true});
  expect(root.querySelector('vyp-ha-feedback')?.state?.message).toContain('Consultando el estado');
  await view({busy: false, result: {...madeTask, kind: 'historical', taskOccurrenceId: null}});
  expect(button('Consultar solicitud original')).toBeDefined();
  expect(root.textContent).toContain('Resultado anterior a la restauración.');
  expect(root.textContent).toContain('No se creó ninguna tarea.');
  expect(root.querySelector('a')).toBeNull();
  await view({pending: false, notice: 'unavailable', result: null});
  expect(button('Volver a intentar')).toBeDefined();
});
