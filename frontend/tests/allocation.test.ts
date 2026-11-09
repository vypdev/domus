import {afterEach, expect, test, vi} from 'vitest';
import {HttpAllocationServer} from '../src/adapters/allocation-http';
import {ALLOCATION_JOURNAL_KEY, AllocationSessionJournal} from '../src/adapters/allocation-journal';
import {allocationEvidence, allocationPolicy, allocationPreview, allocationShares} from '../src/adapters/allocation-values';
import {administrationJSON, identifier} from '../src/adapters/json-values';
import {AllocationController} from '../src/application/allocation-controller';
import type {AllocationRequest, AllocationScope, AllocationServer, AllocationView} from '../src/application/allocation-controller';
import type {EntryRead} from '../src/application/ports';
import {revisionValue} from '../src/domain/administration';
import {allocationFingerprint, allocationPerformers, displayPoints, manualPointShares, minorPoints, requiresManualAllocation} from '../src/domain/point-allocation';
import type {AllocationPolicy} from '../src/domain/point-allocation';
import '../src/presentation/domus-allocation-preview';
import '../src/presentation/domus-allocation-settings';
import corpus from './fixtures/entry-wire.json';

const context = {installationId: '047cc6fb-dfb0-4fa4-b3c3-e0fe54d116b6', channel: 'edge' as const, subject: 'a'.repeat(32)};
const revision = revisionValue('1'), exactRevision = revisionValue('9007199254740993');
const scope: AllocationScope = {key: 'scope', context, definitionId: null, work: null, canManage: true, readOnly: false};
const work = {occurrenceId: 'work', revision: exactRevision, canComplete: true};
const taskScope: AllocationScope = {...scope, definitionId: 'definition', work};
const conserved = {mode: 'conserve_total', precision: 0, rounding: null} as const;
const policy = {mode: 'equal_share', precision: 0, rounding: 'ceil'} as const;
const request: AllocationRequest = {key: 'original', scope: 'scope', definitionId: 'definition', revision: '0', policy};
const inherited = {household: {policy, revision}, override: null};
const named = [{id: 'owner', name: 'Owner'}, {id: 'child', name: 'Member alias'}];
const fingerprint = 'a'.repeat(64);
const allocation = {...policy, policy_revision: 1, task_override: true, base_minor: 225, total_minor: 400,
  shares: [['child', 200], ['owner', 200]]};
const previewWire = {allocation, actual_total: 400, fingerprint};
const evidence = {...policy, policyRevision: revision, taskOverride: true, base: 225, total: 400,
  shares: [['child', 200], ['owner', 200]] as const, fingerprint};
const draft = {performerIds: ['child', 'owner']};
const failure = (code: string) => ({state: 'blocked', code, message: 'Blocked.', action_required: 'Review.', correlation_id: 'cor_test'});
const committed = (candidate = request, state = 'committed') => ({state,
  archived_by: state === 'historical' ? 'restore' : null, operation_id: 'operation', created_at: 100,
  result: {definition_id: candidate.definitionId, setting: {policy: candidate.policy, revision: Number(candidate.revision) + 1}},
  message: 'Saved.', action_required: 'Review.'});
const serialized = (value: unknown) => administrationJSON(JSON.stringify(value));
const read = <T>(result: T): EntryRead<T> => ({result: Promise.resolve(result), cancel: vi.fn()});
const lost = <T>(): EntryRead<T> => ({result: Promise.reject(new Error('lost')), cancel: vi.fn()});

function transport(replies: readonly (readonly [number, unknown])[], deployment: 'native' | 'standalone' = 'standalone') {
  const endpoint = {...corpus[deployment].endpoint, deployment};
  let next = 0;
  const fetch = vi.fn(async (path: string, _init: RequestInit) => {
    const [status, body] = replies[next++];
    const response = new Response(JSON.stringify(body), {status, headers: {'Content-Type': 'application/json', 'Cache-Control': 'no-store'}});
    Object.defineProperty(response, 'url', {value: endpoint.origin + path}); return response;
  });
  return {server: new HttpAllocationServer(endpoint, fetch), fetch};
}

test('manual mode uses verified completion facts before settings arrive and current override precedence afterward', () => {
  const manual = {policy: {mode: 'manual', precision: 2, rounding: null} as const, revision};
  expect(requiresManualAllocation(null, true)).toBe(true);
  expect(requiresManualAllocation(undefined, false)).toBe(false);
  expect(requiresManualAllocation({household: manual, override: null}, false)).toBe(true);
  expect(requiresManualAllocation({household: manual, override: {policy: conserved, revision}}, true)).toBe(false);
  expect(requiresManualAllocation({household: null, override: {policy: null, revision}}, true)).toBe(false);
});

test('exact policy and participant facts reject unknown, inconsistent and out-of-range values', () => {
  expect(minorPoints('1,5')).toBe(150);
  expect(minorPoints(' 0 ')).toBe(0);
  expect(minorPoints('10000.00')).toBe(1_000_000);
  for (const value of ['', '2.001', '10000.01']) expect(minorPoints(value)).toBeNull();
  expect(displayPoints(225, 'en')).toBe('2.25');
  expect(displayPoints(-225, 'es', 2)).toBe('−2,25');
  expect(displayPoints(200, 'es', 0)).toBe('2');
  expect(allocationFingerprint(fingerprint)).toBe(fingerprint);
  expect(() => allocationFingerprint(null)).toThrow();
  expect(() => allocationFingerprint('x')).toThrow();
  expect(allocationPerformers(draft.performerIds, identifier)).toEqual(draft.performerIds);
  for (const invalid of [[], false, ['owner', 'owner'], Array(33).fill('member')]) {
    expect(() => allocationPerformers(invalid, identifier)).toThrow();
  }
  const zero = {member_id: 'owner', amount_minor: 0}, amount = {member_id: 'child', amount_minor: 1_000_000};
  expect(manualPointShares([zero, amount], draft.performerIds)).toEqual([zero, amount]);
  for (const invalid of [
    false, [], [null, amount], ['owner', amount], [[], amount], [{}, amount],
    [{different: 'owner', amount_minor: 0}, amount], [{member_id: 'owner', different: 0}, amount],
    [{...zero, member_id: 'outsider'}, amount], [zero, zero], [{...zero, amount_minor: 0.5}, amount],
    [{...zero, amount_minor: -1}, amount], [zero, {...amount, amount_minor: 1_000_001}],
  ]) expect(() => manualPointShares(invalid, draft.performerIds)).toThrow();
  expect(allocationPolicy(serialized(policy))).toEqual(policy);
  for (const invalid of [{...policy, precision: 1}, {...policy, rounding: null}, {...policy, mode: 'conserve_total'}]) {
    expect(() => allocationPolicy(serialized(invalid))).toThrow();
  }
  for (const invalid of [false, [], Array(33).fill(['owner', 1]), ['owner'], [['owner']], [['owner', 1_000_001]],
    [['owner', 200], ['owner', 200]], [['owner', 200]]]) {
    expect(() => allocationShares(serialized(invalid), 400)).toThrow();
  }
  expect(allocationEvidence(serialized(allocation))).toMatchObject(evidenceWithoutFingerprint());
  expect(allocationPreview(serialized(previewWire), draft.performerIds)).toEqual(evidence);
  for (const [invalid, participants] of [
    [{...previewWire, actual_total: 399}, draft.performerIds],
    [previewWire, ['owner']],
    [previewWire, ['owner', 'other']],
  ] as const) expect(() => allocationPreview(serialized(invalid), participants)).toThrow();
});

function evidenceWithoutFingerprint() {
  const {fingerprint: _, ...facts} = evidence;
  return facts;
}

test.each(['native', 'standalone'] as const)('allocation HTTP uses exact revision, current context and original key in %s', async mode => {
  const csrf = {csrf_token: 'c'.repeat(64)};
  const {server, fetch} = transport([
    [200, {household: null, override: null}],
    [200, {household: {policy, revision: 1}, override: {policy: null, revision: 2}}],
    [200, csrf], [200, previewWire],
    [200, csrf], [200, committed()],
    [200, committed({...request, definitionId: null, revision, policy: conserved}, 'historical')],
    [200, csrf], [200, committed({...request, policy: null})],
    [200, csrf], [200, committed({...request, definitionId: null, revision, policy: conserved})],
  ], mode);
  expect(await server.settings(scope).result).toEqual({household: null, override: null});
  expect(await server.settings(taskScope).result).toEqual({...inherited, override: {policy: null, revision: revisionValue('2')}});
  const manualShares = [{member_id: 'owner', amount_minor: 0}, {member_id: 'child', amount_minor: 200}];
  expect(await server.preview(taskScope, work, {...draft, manualShares}).result).toEqual(evidence);
  expect(await server.save(taskScope, request).result).toBe('saved');
  const household = {...request, definitionId: null, revision, policy: conserved};
  expect(await server.original(scope, household).result).toBe('historical');
  expect(await server.save(taskScope, {...request, policy: null}).result).toBe('saved');
  expect(await server.save(scope, household).result).toBe('saved');
  expect(fetch.mock.calls[1][0]).toContain('family/allocation?definition_id=definition');
  expect(fetch.mock.calls[3][1].body).toContain('"expected_revision":9007199254740993');
  expect(fetch.mock.calls[3][1].body).toContain('"manual_shares"');
  const headers = new Headers(fetch.mock.calls[5][1].headers);
  expect(headers.get('Idempotency-Key')).toBe('original');
  expect(headers.get('X-Domus-Context')).toContain(context.subject);
  expect(headers.get('X-CSRF-Token')).toBe('c'.repeat(64));
});

test('allocation HTTP distinguishes a missing original from stale policy, invalid evidence, and transport failure', async () => {
  const csrf = {csrf_token: 'c'.repeat(64)};
  const {server, fetch} = transport([
    [200, {household: {policy: null, revision: 1}, override: null}],
    [200, {household: null, override: {policy, revision: 1}}],
    [200, csrf], [422, failure('invalid_points_policy')],
    [200, csrf], [503, failure('unavailable')],
    [200, csrf], [422, failure('points_precision_two_required')],
    [200, csrf], [409, failure('revision_conflict')],
    [200, csrf], [422, failure('invalid_points_policy')],
    [200, csrf], [403, failure('permission_denied')],
    [404, failure('operation_missing')], [404, failure('different')], [403, failure('permission_denied')],
    [200, committed({...request, definitionId: 'wrong'})],
    [200, committed({...request, revision})],
    [200, committed({...request, policy: conserved})],
  ]);
  await expect(server.settings(scope).result).rejects.toMatchObject({code: 'invalid_response'});
  await expect(server.settings(scope).result).rejects.toMatchObject({code: 'invalid_response'});
  expect(await server.preview(taskScope, work, draft).result).toBeNull();
  await expect(server.preview(taskScope, work, draft).result).rejects.toMatchObject({code: 'unavailable'});
  expect(await server.preview(taskScope, work, draft).result).toBe('precisionRequired');
  expect(fetch.mock.calls[3][1].body).not.toContain('manual_shares');
  expect(await server.save(taskScope, request).result).toBe('rejected');
  expect(await server.save(taskScope, request).result).toBe('rejected');
  await expect(server.save(taskScope, request).result).rejects.toMatchObject({code: 'unavailable'});
  expect(await server.original(taskScope, request).result).toBeNull();
  await expect(server.original(taskScope, request).result).rejects.toMatchObject({code: 'unavailable'});
  await expect(server.original(taskScope, request).result).rejects.toMatchObject({code: 'unavailable'});
  for (let count = 0; count < 3; count++) await expect(server.original(taskScope, request).result).rejects.toMatchObject({code: 'invalid_response'});
});

function journal() {
  const values = new Map<string, string>();
  const storage = {getItem: (key: string) => values.get(key) ?? null, setItem: (key: string, value: string) => values.set(key, value),
    removeItem: (key: string) => values.delete(key)};
  return {values, storage, journal: new AllocationSessionJournal(storage)};
}

test('allocation journal preserves exact originals and clears them on completion or a change of principal', () => {
  const fixture = journal();
  expect(fixture.journal.open(scope.key)).toBeNull();
  fixture.journal.save(request);
  expect(fixture.journal.open(scope.key)).toEqual(request);
  expect(() => fixture.journal.save(request)).toThrow();
  expect(() => fixture.journal.clear({...request, key: 'other'})).toThrow();
  expect(fixture.journal.open('different')).toBeNull();
  const clearing = {...request, revision: exactRevision, policy: null};
  fixture.journal.save(clearing);
  expect(fixture.journal.open(scope.key)).toEqual(clearing);
  fixture.journal.clear(clearing);
  expect(() => fixture.journal.save({...request, definitionId: null, policy: null})).toThrow();
  fixture.values.set(ALLOCATION_JOURNAL_KEY, 'x'.repeat(2049));
  expect(() => fixture.journal.open(scope.key)).toThrow();
  fixture.values.set(ALLOCATION_JOURNAL_KEY, ' ' + JSON.stringify(request));
  expect(() => fixture.journal.open(scope.key)).toThrow();
  const silent = new AllocationSessionJournal({...fixture.storage, getItem: () => null, setItem: () => {}});
  expect(() => silent.save(request)).toThrow();
});

function controller() {
  const journalFixture = journal();
  const settings = vi.fn<AllocationServer['settings']>(() => read(inherited));
  const preview = vi.fn<AllocationServer['preview']>(() => read(evidence));
  const save = vi.fn<AllocationServer['save']>(() => read('saved'));
  const original = vi.fn<AllocationServer['original']>(() => read(null));
  const view = vi.fn<(value: AllocationView | null) => void>();
  const app = new AllocationController({settings, preview, save, original}, journalFixture.journal, {requestKey: () => 'key'}, view);
  const current = () => view.mock.lastCall?.[0];
  return {app, current, settings, preview, save, original, view, ...journalFixture};
}

test('controller ties reviewed shares to selected work and clears them on change, denial or policy save', async () => {
  const fixture = controller(), {app, current} = fixture;
  await app.refresh(); await app.save(policy); await app.recover(); await app.preview(draft);
  app.bind(taskScope); app.bind({...taskScope});
  await app.save(policy); await app.preview(draft); await app.refresh();
  await vi.waitFor(() => expect(current()?.settings).toEqual(inherited));
  await app.preview(draft);
  expect(current()?.review?.completion).toEqual({...draft, ...{occurrenceId: 'work', revision: exactRevision, fingerprint}});
  fixture.preview.mockReturnValueOnce(read(null));
  await app.preview(draft);
  expect(current()).toMatchObject({review: null, notice: 'rejected'});
  fixture.preview.mockReturnValueOnce(read('precisionRequired'));
  await app.preview(draft);
  expect(current()?.notice).toBe('precisionRequired');
  fixture.preview.mockReturnValueOnce(lost());
  await app.preview(draft);
  expect(current()?.notice).toBe('unavailable');
  await app.save(policy);
  expect(current()).toMatchObject({pending: false, notice: 'saved'});
  expect(fixture.save.mock.calls[0][1]).toEqual({...request, key: 'key'});
  const previewCount = fixture.preview.mock.calls.length;
  app.bind({...taskScope, work: {...work, canComplete: false}});
  await app.preview(draft);
  app.bind({...taskScope, canManage: false});
  await app.preview({...draft, manualShares: []});
  expect(fixture.preview).toHaveBeenCalledTimes(previewCount);
  await app.preview(draft);
  expect(current()?.review).not.toBeNull();
  app.bind({...taskScope, canManage: false, readOnly: true});
  await app.preview(draft);
  app.bind(null);
  expect(current()).toBeNull();
});

test('controller recovers a lost reply across rebind, preserving the exact payload and one original key', async () => {
  const fixture = controller(), {app, current} = fixture;
  app.bind(scope);
  await vi.waitFor(() => expect(current()?.settings).toEqual(inherited));
  const journalSave = vi.spyOn(fixture.journal, 'save').mockImplementationOnce(() => {throw new Error('storage denied');});
  await app.save(conserved);
  expect(current()).toMatchObject({pending: false, notice: 'unavailable'});
  expect(journalSave).toHaveBeenCalledOnce();
  expect(fixture.save).not.toHaveBeenCalled();
  await app.save(null);
  fixture.save.mockReturnValueOnce(lost());
  await app.save(conserved);
  expect(current()).toMatchObject({pending: true, notice: 'uncertain'});
  const original = fixture.journal.open(scope.key)!;
  await app.save(policy);
  expect(fixture.save).toHaveBeenCalledOnce();
  app.bind(null); app.bind({...scope, readOnly: true});
  await vi.waitFor(() => expect(current()?.busy).toBe(false));
  await app.recover();
  expect(current()?.pending).toBe(true);
  app.bind(scope);
  await vi.waitFor(() => expect(current()?.busy).toBe(false));
  await app.recover();
  expect(fixture.save.mock.calls[1][1]).toEqual(original);
  expect(current()).toMatchObject({pending: false, notice: 'saved'});
  fixture.save.mockReturnValueOnce(lost());
  await app.save(conserved);
  fixture.original.mockReturnValueOnce(read('historical'));
  await app.recover();
  expect(current()).toMatchObject({pending: false, notice: 'historical'});
  fixture.values.set(ALLOCATION_JOURNAL_KEY, 'bad');
  app.bind(taskScope);
  expect(current()).toMatchObject({pending: true, notice: 'unavailable'});
});

test('controller drops in-flight protected settings after leaving the workspace', async () => {
  const fixture = controller();
  let resolve!: (value: typeof inherited) => void;
  const cancel = vi.fn();
  fixture.settings.mockReturnValueOnce({result: new Promise(resolveRead => {resolve = resolveRead;}), cancel});
  fixture.app.bind(scope);
  fixture.app.bind(null);
  resolve(inherited);
  await Promise.resolve();
  expect(cancel).toHaveBeenCalledOnce();
  expect(fixture.current()).toBeNull();
  fixture.app.bind(scope);
  await vi.waitFor(() => expect(fixture.current()?.settings).toEqual(inherited));
  fixture.settings.mockReturnValueOnce(lost());
  await fixture.app.refresh();
  expect(fixture.current()?.settings).toBeNull();
  await vi.waitFor(() => expect(fixture.current()?.notice).toBe('unavailable'));
});

const nodes: HTMLElement[] = [];
function attach<T extends HTMLElement>(node: T): T {document.body.append(node); nodes.push(node); return node;}
afterEach(() => {for (const node of nodes.splice(0)) node.remove();});
const initial: AllocationView = {scope, settings: null, review: null, pending: false, busy: false, notice: null};

function change(node: HTMLInputElement | HTMLSelectElement, value?: string) {
  if (value !== undefined) node.value = value;
  node.dispatchEvent(new Event('change'));
}
function press(root: ShadowRoot, label: string) {
  const button = [...root.querySelectorAll('vyp-ha-button')].find(button => button.state.label === label);
  expect(button).toBeDefined(); button!.dispatchEvent(new Event('ha-press-request'));
}

test('settings editor displays localized permission, inherited policy, and semantic writes', async () => {
  const node = attach(document.createElement('domus-allocation-settings')), root = node.shadowRoot!;
  const events = vi.fn(); node.addEventListener('domus-allocation-settings', events);
  await node.updateComplete;
  node.view = {...initial, scope: {...scope, canManage: false}};
  await node.updateComplete; expect(root.querySelector('form')).toBeNull();
  node.view = {...initial, pending: true, notice: 'uncertain'};
  await node.updateComplete;
  press(root, 'Check policy request'); press(root, 'Refresh');
  expect(events.mock.calls.map(([event]) => event.detail)).toEqual([{type: 'recover'}, {type: 'refresh'}]);
  node.view = {...initial, scope: taskScope, settings: {household: null, override: null}, notice: 'unavailable'};
  await node.updateComplete;
  expect(root.textContent).toContain('This task uses the household default.');
  expect(root.textContent).toContain('Unconfigured households');
  const [mode, precision] = root.querySelectorAll('select');
  change(mode, 'equal_share'); change(precision, '2'); await node.updateComplete;
  change(root.querySelectorAll('select')[2], 'floor'); await node.updateComplete;
  root.querySelector('form')!.dispatchEvent(new Event('submit', {cancelable: true}));
  expect(events.mock.lastCall?.[0].detail).toEqual({type: 'save', policy: {mode: 'equal_share', precision: 2, rounding: 'floor'}});
  change(precision, '0'); change(mode, 'full_per_participant'); await node.updateComplete;
  node.view = {...initial, scope: taskScope, settings: {...inherited, override: {policy, revision}}};
  await node.updateComplete; press(root, 'Use household default');
  expect(events.mock.lastCall?.[0].detail).toEqual({type: 'save', policy: null});
  node.language = 'es'; node.view = {...node.view, scope: {...taskScope, readOnly: true}, notice: 'saved'};
  await node.updateComplete;
  expect(root.textContent).toContain('Política de puntos guardada.');
  expect(root.querySelector('select')!.disabled).toBe(true);
});

test('completion preview shows names and exact totals, then retires a review when participants or amounts change', async () => {
  const node = attach(document.createElement('domus-allocation-preview')), root = node.shadowRoot!;
  const preview = vi.fn(), changes = vi.fn();
  node.addEventListener('domus-allocation-preview', preview);
  node.addEventListener('domus-allocation-draft', changes);
  await node.updateComplete;
  node.view = {...initial, scope: taskScope}; await node.updateComplete;
  expect(root.querySelector('details')).toBeNull();
  node.ownId = 'owner'; node.names = named;
  await node.updateComplete;
  const checks = () => [...root.querySelectorAll<HTMLInputElement>('input[type=checkbox]')];
  checks()[1].checked = true; change(checks()[1]); await node.updateComplete;
  expect(node.needsReview).toBe(true);
  press(root, 'Preview points');
  expect(preview.mock.lastCall?.[0].detail).toEqual(draft);
  const completion = {...draft, occurrenceId: 'work', revision: exactRevision, fingerprint};
  node.view = {...node.view, review: {evidence, completion}}; await node.updateComplete;
  expect(node.reviewed).toEqual(completion);
  expect(root.textContent).toContain('Member alias');
  expect(root.textContent).toContain('2.25');
  node.language = 'es'; await node.updateComplete;
  expect(root.textContent).toContain('2,25');
  expect(root.textContent).toContain('Total efectivo');
  expect(root.textContent).toContain('Hacia arriba');
  checks()[1].checked = false; change(checks()[1]); await node.updateComplete;
  expect(node.reviewed).toBeUndefined();
  const manual: AllocationPolicy = {mode: 'manual', precision: 2, rounding: null};
  node.view = {...node.view, settings: {...inherited, override: {policy: manual, revision}}, notice: 'unavailable'};
  await node.updateComplete;
  expect(root.textContent).toContain('Introduce un importe válido');
  const input = root.querySelector<HTMLInputElement>('input[type=text]')!;
  input.value = '0'; input.dispatchEvent(new Event('input')); await node.updateComplete;
  press(root, 'Previsualizar puntos');
  expect(preview.mock.lastCall?.[0].detail).toEqual({performerIds: ['owner'], manualShares: [{member_id: 'owner', amount_minor: 0}]});
  node.disabled = true; await node.updateComplete;
  expect(root.querySelector('fieldset')!.disabled).toBe(true);
  node.view = {...node.view, scope: {...taskScope, work: {...work, revision}}};
  await node.updateComplete;
  expect(root.querySelector<HTMLInputElement>('input[type=text]')!.value).toBe('');
  const earlier = preview.mock.calls.length;
  checks()[0].checked = false; change(checks()[0]); await node.updateComplete;
  press(root, 'Previsualizar puntos');
  expect(preview.mock.calls).toHaveLength(earlier);
  expect(changes).toHaveBeenCalled();
});

test('a recovered request cannot be resent after the verified workspace is retired', async () => {
  const fixture = controller(), {app} = fixture;
  fixture.journal.save({...request, definitionId: null, policy: conserved});
  app.bind(scope);
  await vi.waitFor(() => expect(fixture.current()?.busy).toBe(false));
  fixture.view.mockImplementationOnce(() => {});
  fixture.view.mockImplementationOnce(value => {
    if (value?.busy === false) app.bind(null);
  });
  await app.recover();
  expect(fixture.current()).toBeNull();
  expect(fixture.save).not.toHaveBeenCalled();
  expect(fixture.journal.open(scope.key)?.key).toBe('original');
});

test('late settings from a retired member cannot clear the next workspace', async () => {
  const fixture = controller();
  fixture.app.bind(scope);
  await vi.waitFor(() => expect(fixture.current()?.settings).toEqual(inherited));
  let reject!: (error: Error) => void;
  fixture.settings.mockReturnValueOnce({result: new Promise((_resolve, fail) => {reject = fail;}), cancel: vi.fn()});
  const retired = fixture.app.refresh();
  fixture.app.bind(taskScope);
  await vi.waitFor(() => expect(fixture.current()?.settings).toEqual(inherited));
  reject(new Error('retired'));
  await retired;
  expect(fixture.current()?.scope).toBe(taskScope);
  expect(fixture.current()?.settings).toEqual(inherited);
});
