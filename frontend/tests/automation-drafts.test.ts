import {afterEach, expect, test, vi} from 'vitest';
import {HttpAutomationDrafts} from '../src/adapters/automation-draft-http';
import {AUTOMATION_DRAFT_JOURNAL_KEY, AutomationDraftSessionJournal} from '../src/adapters/automation-draft-journal';
import {AutomationDraftController} from '../src/application/automation-drafts';
import type {AutomationDraftServer, AutomationDraftView, DraftCondition, DraftOutcome, DraftPage, DraftRequest, SavedAutomationDraft} from '../src/application/automation-drafts';
import {EntryReadError} from '../src/application/ports';
import {revisionValue} from '../src/domain/administration';
import '../src/presentation/domus-automation-drafts';

const context = {installationId: '01234567-89ab-cdef-0123-456789abcdef', channel: 'edge' as const, subject: 'a'.repeat(32)};
const scope = {key: 'private-scope', context, memberId: 'member', readOnly: false};
const idea = {title: 'Buy tea', productId: 'tea'};
const first = {id: 'draft-1', title: 'Buy tea', revision: revisionValue('1')};
const second = {...first, revision: revisionValue('2'), title: 'Prepare tea'};
const request: DraftRequest = {key: 'exact-request', scope: scope.key, ruleId: null, revision: '0', rule: idea};
const grouped: DraftCondition = {kind: 'all', children: [{kind: 'not', child: {kind: 'stock_below_minimum', product_id: 'milk'}},
  {kind: 'any', children: [{kind: 'stock_below_minimum', product_id: 'tea'}]}]};
const settled = <T>(value: T) => ({result: Promise.resolve(value), cancel: vi.fn()});
const failed = (error = new Error('network')) => ({result: Promise.reject(error), cancel: vi.fn()});
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const result = new Promise<T>((done, fail) => {resolve = done; reject = fail;});
  return {result, resolve, reject, cancel: vi.fn()};
}
function setup() {
  const storage = new Map<string, string>();
  const journal = new AutomationDraftSessionJournal({
    getItem: key => storage.get(key) ?? null,
    setItem: (key, value) => {storage.set(key, value);},
    removeItem: key => {storage.delete(key);},
  });
  const page: DraftPage = {drafts: [first], next: 'more'};
  const server = {
    list: vi.fn<AutomationDraftServer['list']>(() => settled(page)),
    reopen: vi.fn<AutomationDraftServer['reopen']>(() => settled({...first, condition: null})),
    previewSaved: vi.fn<AutomationDraftServer['previewSaved']>(() => settled(true)),
    send: vi.fn<AutomationDraftServer['send']>(() => settled({kind: 'rejected'})),
    original: vi.fn<AutomationDraftServer['original']>(() => settled({kind: 'missing'})),
  };
  const edit = vi.fn(), publish = vi.fn(), counter = {value: 0};
  const controller = () => new AutomationDraftController(server, journal,
    {requestKey: () => 'req-' + ++counter.value}, edit, publish);
  return {storage, journal, page, server, edit, publish, controller};
}

test('open, page, edit and resolve conflicts while preserving entered values', async () => {
  const {server, controller, edit, publish} = setup();
  const drafts = controller();
  await drafts.handle({type: 'save'}, idea);
  drafts.bind(scope, true);
  await vi.waitFor(() => expect(publish).toHaveBeenLastCalledWith(expect.objectContaining({state: 'ready', busy: false})));
  await drafts.handle({type: 'first'}, null);
  await drafts.handle({type: 'next'}, null);
  expect(server.list).toHaveBeenLastCalledWith(scope, 'more');
  await drafts.handle({type: 'first'}, null);
  expect(server.list).toHaveBeenLastCalledWith(scope, null);
  await drafts.handle({type: 'open', id: 'outside-page'}, null);
  expect(server.reopen).not.toHaveBeenCalled();
  await drafts.handle({type: 'open', id: first.id}, null);
  expect(edit).toHaveBeenLastCalledWith({title: first.title, productId: null});
  await drafts.handle({type: 'save'}, {title: ' ', productId: null});
  expect(publish).toHaveBeenLastCalledWith(expect.objectContaining({notice: 'invalid_title'}));
  const dirty = {...idea, title: 'My revision'};
  server.send.mockReturnValueOnce(settled({kind: 'conflict'}));
  await drafts.handle({type: 'save'}, dirty);
  expect(publish).toHaveBeenLastCalledWith(expect.objectContaining({notice: 'conflict'}));
  await drafts.handle({type: 'save'}, dirty);
  expect(server.send).toHaveBeenCalledOnce();
  server.reopen.mockReturnValueOnce(settled({...second, condition: grouped}));
  await drafts.handle({type: 'review'}, null);
  await drafts.handle({type: 'rebase'}, null);
  expect(publish).toHaveBeenLastCalledWith(expect.objectContaining({notice: 'conflict'}));
  server.reopen.mockReturnValueOnce(settled({...second, condition: null}));
  await drafts.handle({type: 'review'}, null);
  expect(publish).toHaveBeenLastCalledWith(expect.objectContaining({competing: {...second, condition: null}}));
  drafts.bind({...scope, readOnly: true}, true);
  await drafts.handle({type: 'rebase'}, null);
  expect(edit).toHaveBeenCalledOnce();
  drafts.bind(scope, true);
  await drafts.handle({type: 'rebase'}, null);
  await drafts.handle({type: 'save'}, dirty);
  expect(server.send).toHaveBeenLastCalledWith(scope, expect.objectContaining({rule: dirty, revision: '2'}));
  expect(edit).toHaveBeenCalledOnce();
  await drafts.handle({type: 'new'}, null);
  expect(edit).toHaveBeenLastCalledWith({title: '', productId: null});
  server.reopen.mockReturnValueOnce(failed());
  await drafts.handle({type: 'open', id: first.id}, null);
  expect(publish).toHaveBeenLastCalledWith(expect.objectContaining({notice: 'unavailable'}));
});

test('recover an uncertain save after reload with its exact key and retire denied details', async () => {
  const {server, controller, journal, edit, publish} = setup();
  const drafting = controller();
  drafting.bind(scope, true);
  await vi.waitFor(() => expect(publish).toHaveBeenLastCalledWith(expect.objectContaining({busy: false})));
  server.send.mockReturnValueOnce(failed());
  await drafting.handle({type: 'save'}, idea);
  expect(publish).toHaveBeenLastCalledWith(expect.objectContaining({pending: true, notice: 'uncertain'}));
  const original = journal.open(scope.key);
  drafting.bind(null);
  const reloaded = controller();
  reloaded.bind(scope, true);
  await vi.waitFor(() => expect(edit).toHaveBeenLastCalledWith(idea));
  await reloaded.handle({type: 'new'}, null);
  expect(edit).toHaveBeenCalledOnce();
  reloaded.bind({...scope, readOnly: true}, true);
  await reloaded.handle({type: 'recover'}, null);
  expect(server.send).toHaveBeenCalledOnce();
  reloaded.bind(scope, true);
  server.send.mockReturnValueOnce(settled({kind: 'committed', id: first.id, revision: first.revision, operationId: 'operation'}));
  await reloaded.handle({type: 'recover'}, null);
  expect(server.original).toHaveBeenLastCalledWith(scope, original);
  expect(server.send).toHaveBeenLastCalledWith(scope, original);
  expect(journal.open(scope.key)).toBeNull();
  expect(publish).toHaveBeenLastCalledWith(expect.objectContaining({pending: false, notice: 'saved', operationId: 'operation'}));

  server.send.mockReturnValueOnce(failed());
  await reloaded.handle({type: 'save'}, idea);
  server.original.mockReturnValueOnce(settled({kind: 'historical', id: first.id, revision: second.revision,
    operationId: 'before-restore'}));
  await reloaded.handle({type: 'recover'}, null);
  expect(publish).toHaveBeenLastCalledWith(expect.objectContaining({selected: null, notice: 'historical'}));
  server.send.mockReturnValueOnce(failed());
  await reloaded.handle({type: 'save'}, idea);
  server.original.mockReturnValueOnce(failed(new EntryReadError('forbidden')));
  await reloaded.handle({type: 'recover'}, null);
  expect(publish).toHaveBeenLastCalledWith({state: 'denied'});
  expect(edit).toHaveBeenLastCalledWith({title: '', productId: null});
  expect(journal.open(scope.key)).toBeNull();
});

test('retain the saved grouped condition and preview it without allowing replacement', async () => {
  const {controller, server, publish} = setup();
  const drafts = controller();
  const saved = {...first, condition: grouped};
  server.reopen.mockReturnValue(settled(saved));
  drafts.bind(scope, true);
  await vi.waitFor(() => expect(publish).toHaveBeenLastCalledWith(expect.objectContaining({busy: false})));
  await drafts.handle({type: 'open', id: first.id}, null);
  expect(publish).toHaveBeenLastCalledWith(expect.objectContaining({locked: saved}));
  await drafts.handle({type: 'save'}, idea);
  expect(server.send).not.toHaveBeenCalled();
  server.previewSaved.mockReturnValueOnce(failed());
  await drafts.handle({type: 'preview_saved'}, null);
  expect(publish).toHaveBeenLastCalledWith(expect.objectContaining({notice: 'unavailable'}));
  await drafts.handle({type: 'preview_saved'}, null);
  expect(server.previewSaved).toHaveBeenLastCalledWith(scope, saved);
  expect(publish).toHaveBeenLastCalledWith(expect.objectContaining({preview: true}));
});

test('ignore navigation-cancelled reads and fail closed on storage or request errors', async () => {
  const {controller, server, storage, publish} = setup();
  const drafts = controller(), obsolete = deferred<DraftPage>();
  server.list.mockReturnValueOnce(obsolete);
  drafts.bind(scope, true);
  drafts.bind(scope, false);
  expect(obsolete.cancel).toHaveBeenCalledOnce();
  obsolete.reject(new Error('obsolete'));
  await Promise.resolve();
  expect(publish).toHaveBeenLastCalledWith(null);
  storage.set(AUTOMATION_DRAFT_JOURNAL_KEY, '{}');
  drafts.bind(scope, true);
  await vi.waitFor(() => expect(publish).toHaveBeenLastCalledWith({state: 'unavailable'}));
  storage.delete(AUTOMATION_DRAFT_JOURNAL_KEY);
  await drafts.handle({type: 'retry'}, null);
  const late = deferred<DraftOutcome>();
  server.send.mockReturnValueOnce(late);
  const outgoing = drafts.handle({type: 'save'}, idea);
  drafts.bind(null);
  late.resolve({kind: 'rejected'});
  await outgoing;
  expect(publish).toHaveBeenLastCalledWith(null);
  expect(storage.get(AUTOMATION_DRAFT_JOURNAL_KEY)).toContain('req-1');
});

const target = {origin: 'https://domus.test', deployment: 'standalone' as const, applicationBase: '/'};
const status = {rule_id: first.id, revision: '1', state: 'draft', enabled: false};
const wire = {...status, version: 1, trigger: {kind: 'manual'}, condition: grouped, action: {kind: 'task.create', title: first.title}};
const receipt = {state: 'committed', archived_by: null, operation_id: 'operation', created_at: 100,
  result: {...status, member_id: scope.memberId}, message: 'Saved.', action_required: 'Retain original.'};
const blocked = (code: string) => ({state: 'blocked', code, message: 'Blocked.', action_required: 'Review details.', correlation_id: 'cor_issue'});
function response(path: string, value: unknown, status = 200): Response {
  const reply = new Response(JSON.stringify(value), {status,
    headers: {'Content-Type': 'application/json', 'Cache-Control': 'no-store'}});
  Object.defineProperty(reply, 'url', {value: target.origin + path});
  return reply;
}

test('HTTP binds list, exact saves, complex reads and original recovery to the current context', async () => {
  const transport = vi.fn(async (path: string, init: RequestInit) => {
    const headers = init.headers as Headers;
    expect(headers.get('X-Domus-Context')).toBe('v1:' + context.installationId + ':edge:' + context.subject);
    if (path.endsWith('/csrf')) return response(path, {csrf_token: 'c'.repeat(64)});
    if (path.endsWith('?cursor=opaque%3D')) return response(path, {drafts: [{...status, title: first.title}], next_cursor: 'next'});
    if (path.endsWith(first.id)) return response(path, wire);
    if (path.endsWith('/preview')) {
      expect(JSON.parse(String(init.body)).condition).toEqual(grouped);
      expect(headers.get('Idempotency-Key')).toBeNull();
      return response(path, {version: 1, trigger: 'manual', task_title: first.title, would_create: false, conditions: []});
    }
    if (path.endsWith('/requests/' + request.key)) {
      return response(path, {...receipt, state: 'historical', archived_by: 'backup'});
    }
    expect(init.method).toBe('POST');
    expect(headers.get('Idempotency-Key')).toBe(request.key);
    expect(headers.get('X-CSRF-Token')).toBe('c'.repeat(64));
    expect(JSON.parse(String(init.body))).toEqual({version: 1, trigger: wire.trigger, action: wire.action,
      condition: {kind: 'stock_below_minimum', product_id: 'tea'}, rule_id: null, expected_revision: '0'});
    return response(path, receipt);
  });
  const server = new HttpAutomationDrafts(target, transport);
  await expect(server.list(scope, 'opaque=').result).resolves.toEqual({drafts: [first], next: 'next'});
  const draft: SavedAutomationDraft = await server.reopen(scope, first.id).result;
  expect(draft).toEqual({...first, condition: grouped});
  await expect(server.previewSaved(scope, draft).result).resolves.toBe(false);
  await expect(server.send(scope, request).result).resolves.toMatchObject({kind: 'committed', ...statusFact()});
  await expect(server.original(scope, request).result).resolves.toMatchObject({kind: 'historical', ...statusFact()});
  function statusFact() {return {id: first.id, revision: first.revision, operationId: 'operation'};}
});

test.each([
  [409, 'revision_conflict', 'conflict'],
  [409, 'idempotency_conflict', 'rejected'],
  [404, 'inventory_product_missing', 'rejected'],
  [422, 'invalid_request', 'rejected'],
])('HTTP recognizes definite save failure %s %s', async (status, code, kind) => {
  const server = new HttpAutomationDrafts(target, async path => path.endsWith('/csrf')
    ? response(path, {csrf_token: 'c'.repeat(64)}) : response(path, blocked(code), status));
  await expect(server.send(scope, request).result).resolves.toEqual({kind});
});

test('HTTP treats only a scoped operation 404 as missing and rejects mismatched receipts', async () => {
  const server = new HttpAutomationDrafts(target, async path => response(path, blocked('operation_missing'), 404));
  await expect(server.original(scope, request).result).resolves.toEqual({kind: 'missing'});
  const denied = new HttpAutomationDrafts(target, async path => path.endsWith('/csrf')
    ? response(path, {csrf_token: 'c'.repeat(64)}) : response(path, blocked('permission_denied'), 403));
  await expect(denied.send(scope, request).result).rejects.toMatchObject({code: 'forbidden'});
  await expect(denied.original(scope, request).result).rejects.toMatchObject({code: 'forbidden'});
  await expect(denied.previewSaved(scope, {...first, condition: null}).result).rejects.toMatchObject({code: 'forbidden'});
  const wrong = new HttpAutomationDrafts(target, async path => response(path, {...receipt, result: {...receipt.result, member_id: 'other'}}));
  await expect(wrong.original(scope, request).result).rejects.toMatchObject({code: 'invalid_response'});
});

test('session journal keeps canonical request bytes and retires another scope', () => {
  const {journal, storage} = setup();
  journal.save(request);
  expect(journal.open(scope.key)).toEqual(request);
  expect(() => journal.save(request)).toThrow();
  expect(journal.open('other-scope')).toBeNull();
  const editRequest: DraftRequest = {...request, ruleId: first.id, revision: first.revision, rule: {...idea, productId: null}};
  journal.save(editRequest);
  expect(journal.open(scope.key)).toEqual(editRequest);
  storage.set(AUTOMATION_DRAFT_JOURNAL_KEY, JSON.stringify({...editRequest, ruleId: null}));
  expect(() => journal.open(scope.key)).toThrow();
});

test('load and recover an existing revision and handle temporary local failures', async () => {
  const {controller, server, storage, journal, edit, publish} = setup();
  const amendment: DraftRequest = {...request, ruleId: first.id, revision: first.revision};
  journal.save(amendment);
  const drafts = controller();
  drafts.bind(scope, true);
  await drafts.handle({type: 'save'}, null);
  await vi.waitFor(() => expect(publish).toHaveBeenLastCalledWith(expect.objectContaining({selected: firstIdentity()})));
  server.original.mockReturnValueOnce(settled({kind: 'rejected'}));
  await drafts.handle({type: 'recover'}, null);
  await drafts.handle({type: 'recover'}, null);
  expect(server.original).toHaveBeenCalledOnce();
  server.reopen.mockReturnValueOnce(settled({...first, condition: {kind: 'stock_below_minimum', product_id: 'tea'}}));
  await drafts.handle({type: 'open', id: first.id}, null);
  expect(edit).toHaveBeenLastCalledWith(idea);
  storage.set(AUTOMATION_DRAFT_JOURNAL_KEY, '{}');
  await drafts.handle({type: 'save'}, idea);
  expect(server.send).not.toHaveBeenCalled();
  expect(publish).toHaveBeenLastCalledWith(expect.objectContaining({notice: 'unavailable'}));
  server.list.mockReturnValueOnce(failed());
  await drafts.handle({type: 'retry'}, null);
  expect(publish).toHaveBeenLastCalledWith(expect.objectContaining({state: 'ready', notice: 'unavailable'}));
  storage.delete(AUTOMATION_DRAFT_JOURNAL_KEY);
  server.list.mockReturnValueOnce(failed(new EntryReadError('forbidden')));
  await drafts.handle({type: 'retry'}, null);
  expect(publish).toHaveBeenLastCalledWith({state: 'denied'});
  await drafts.handle({type: 'open', id: first.id}, null);
  expect(server.reopen).toHaveBeenCalledOnce();
  function firstIdentity() {return {id: first.id, revision: first.revision};}
});

test('HTTP reopens a simple rule and checks the revision on an edit receipt', async () => {
  const server = new HttpAutomationDrafts(target, async path => {
    if (path.endsWith(first.id)) return response(path, {...wire, condition: null});
    if (path.endsWith('/drafts')) return response(path, {drafts: [], next_cursor: null});
    return response(path, {...receipt, archived_by: 'rollback', result: {...receipt.result, revision: '2'}});
  });
  await expect(server.list(scope, null).result).resolves.toEqual({drafts: [], next: null});
  await expect(server.reopen(scope, first.id).result).resolves.toEqual({...first, condition: null});
  await expect(server.original(scope, {...request, ruleId: first.id, revision: first.revision}).result)
    .resolves.toMatchObject({kind: 'committed', revision: second.revision, id: first.id});
});

afterEach(() => document.querySelectorAll('domus-automation-drafts').forEach(element => element.remove()));

test('draft interface exposes localized inactive revisions, recovery and explicit review', async () => {
  const element = document.createElement('domus-automation-drafts');
  document.body.append(element);
  const event = vi.fn();
  element.addEventListener('domus-automation-draft-intent', event);
  await element.updateComplete;
  expect(element.shadowRoot!.textContent!.trim()).toBe('');
  const ready: Extract<AutomationDraftView, {state: 'ready'}> = {state: 'ready', page: {drafts: [first], next: 'next'},
    after: null, selected: first, locked: null, competing: secondWithGroup(), operationId: 'operation', preview: null,
    busy: false, pending: false, readOnly: false, notice: 'conflict'};
  element.view = ready;
  element.canEdit = true;
  await element.updateComplete;
  const root = element.shadowRoot!;
  expect(root.textContent).toContain('Inactive');
  expect(root.textContent).toContain('operation');
  expect(root.textContent).toContain('Any condition');
  expect(root.textContent).toContain('Stock below minimum · milk');
  const buttons = [...root.querySelectorAll('vyp-ha-button')];
  expect(buttons[0].disabled).toBe(true);
  buttons.find(button => button.state?.label === 'Review latest revision')!
    .dispatchEvent(new CustomEvent('ha-press-request'));
  expect(event.mock.lastCall?.[0].detail).toEqual({type: 'review'});
  element.language = 'es';
  element.view = {...ready, readOnly: true, busy: true, pending: true, notice: 'uncertain',
    locked: secondWithGroup(), preview: false, after: 'previous'};
  await element.updateComplete;
  expect(root.textContent).toContain('Cualquier condición');
  expect(root.textContent).toContain('No se crearía ninguna tarea');
  expect(root.textContent).toContain('sesión de solo lectura');
  for (const state of ['loading', 'denied', 'unavailable'] as const) {
    element.view = {state};
    await element.updateComplete;
    expect(root.querySelectorAll('vyp-ha-feedback')).toHaveLength(1);
  }
  element.view = {...ready, page: {drafts: [], next: null}, after: 'previous', notice: 'saved', competing: null};
  await element.updateComplete;
  expect(root.textContent).toContain('guarda tu primer borrador');
  element.view = {...ready, selected: null, notice: null, operationId: null, competing: null,
    after: null, page: {drafts: [], next: null}};
  await element.updateComplete;
  expect(root.textContent).not.toContain('Borrador actual');
  element.view = {...ready, locked: {...first, condition: null}, notice: null, preview: null};
  await element.updateComplete;
  expect(root.textContent).toContain('condiciones agrupadas');
  element.view = {...ready, locked: secondWithGroup(), preview: true};
  await element.updateComplete;
  expect(root.textContent).toContain('Se crearía esta tarea');
  element.view = {...ready, competing: {...second, condition: null}};
  await element.updateComplete;
  expect(root.textContent).toContain('Sin condición de existencias');
  function secondWithGroup(): SavedAutomationDraft {return {...second, condition: grouped};}
});
