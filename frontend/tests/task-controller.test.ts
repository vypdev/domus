import {expect, test, vi} from 'vitest';
import {TaskController} from '../src/application/task-controller';
import {TaskSessionJournal} from '../src/adapters/task-journal';
import {JournalError} from '../src/domain/journal';
import {revisionValue} from '../src/domain/administration';
import {EntryReadError} from '../src/application/ports';
import type {TaskAccess, TaskDetail, TaskReceipt, TaskScheduleDraft} from '../src/domain/tasks';
import type {VerifiedEntrySession} from '../src/application/ports';
import type {TaskServer} from '../src/application/task-ports';
const context = {installationId: '01234567-89ab-cdef-0123-456789abcdef', channel: 'edge' as const, subject: 'a'.repeat(32)};
const revision = revisionValue('1');
const detail: TaskDetail = {occurrenceId: 'work-1', definitionId: 'def-1', definitionRevision: revision, title: 'Clean 🧹',
  description: '', priority: 'normal', state: 'available', revision, assigneeIds: [], dueAt: null, currentCycleId: null,
  allowedActions: ['claim', 'complete'], cycle: null, materials: [], materialRecording: 'review_on_completion', dependencyReviewRequired: false, pendingMaterials: false};
const saved: TaskReceipt = {kind: 'receipt', stage: 'committed', action: 'task.create', operationId: 'op-1', occurrenceId: 'work-1', revision, state: 'available', cycle: null, archivedBy: null};
const read = <T>(value: T) => ({result: Promise.resolve(value), cancel: vi.fn()});
function fixture() {
  let now = 1000, sequence = 0;
  const storage = new Map<string, string>();
  const session = {context, deployment: 'native' as const, access: 'full' as 'full' | 'read_only', serverTime: now, expiresAt: 100000, householdApiAvailable: true};
  const identity = {session: vi.fn(() => read<VerifiedEntrySession | null>(session))};
  const server = {access: vi.fn(() => read<TaskAccess>({householdId: 'home', memberId: 'member-1', canCreate: true, canReviewSchedule: true})),
    list: vi.fn(() => read({items: [detail], nextCursor: null as string | null})), detail: vi.fn(() => read(detail)),
    original: vi.fn(() => read(saved)), send: vi.fn<TaskServer['send']>(async () => saved)};
  const journal = new TaskSessionJournal({getItem: key => storage.get(key) ?? null, setItem: (key, value) => {storage.set(key, value);}, removeItem: key => {storage.delete(key);}});
  const clock = {anchor: vi.fn((value: number) => {now = value;}), now: vi.fn(() => now)};
  const entropy = {requestKey: vi.fn(() => 'key-' + ++sequence)};
  const controller = new TaskController('native', identity, server, journal, clock, entropy);
  return {controller, server, identity, session, storage, journal, clock, entropy, setNow: (value: number) => {now = value;}, advance: () => {now = 100000;}};
}
test('a real task workspace loads under fresh identity and creates title-only work with a saved original', async () => {
  const f = fixture(); await f.controller.refresh(); expect(f.controller.view.page?.items[0].title).toBe('Clean 🧹');
  await f.controller.create('  New task 🧹  ', '', 'normal');
  expect(f.server.send).toHaveBeenCalledTimes(1);
  expect(f.server.send.mock.calls[0]).toEqual([{key: 'key-1', command: {action: 'task.create', payload: {expected_revision: 0, title: '  New task 🧹  ', description: '', priority: 'normal'}}}, context]);
  expect(f.controller.view.outcome).toEqual(saved); expect(f.controller.view.records?.[0]).toMatchObject({stage: 'committed', key: 'key-1', operationId: 'op-1'});
});
test('lost task replies block a second new key and recover by read without resending', async () => {
  const f = fixture(); await f.controller.refresh(); f.server.send.mockResolvedValueOnce({kind: 'uncertain'});
  await f.controller.create('New', '', 'normal'); expect(f.controller.view.records?.[0].stage).toBe('uncertain');
  await f.controller.create('Duplicate', '', 'normal'); expect(f.server.send).toHaveBeenCalledTimes(1);
  expect(f.controller.view.notice).toBe('previous_request_unresolved');
  await f.controller.recover('key-1'); expect(f.server.original).toHaveBeenCalledTimes(1);
  expect(f.server.send).toHaveBeenCalledTimes(1); expect(f.controller.view.outcome).toEqual(saved);
});
test('scheduled task creation binds the verified household policy and keeps a lost reply under its original key', async () => {
  const f = fixture();
  const draft: TaskScheduleDraft = {kind: 'relative', start: {kind: 'date', local: '2027-01-02'},
    interval_days: 18, visibility: 'at_verification'};
  await f.controller.create('Inspect', '', 'normal', draft);
  await f.controller.refresh();
  await f.controller.create('Inspect', '', 'normal', draft);
  expect(f.controller.view.notice).toBe('invalid_input');
  expect(f.server.send).not.toHaveBeenCalled();
  const policy = {zone: 'Europe/Madrid', data_identity: 'tzdata:2026.6/iana:2026f', repeated_time: 'second_instant' as const, revision};
  f.server.access.mockReturnValue(read({...f.controller.view.access!, schedulePolicy: policy}));
  await f.controller.refresh();
  f.server.send.mockResolvedValueOnce({kind: 'uncertain'});
  await f.controller.create('Inspect', '', 'normal', draft);
  const request = f.server.send.mock.calls[0][0];
  expect(request).toMatchObject({key: 'key-1', command: {payload: {schedule: {draft, policy}}}});
  f.server.original.mockReturnValue(read({...saved, state: 'active', occurrenceId: null}));
  await f.controller.recover('key-1');
  expect(f.server.original).toHaveBeenCalledWith({...request, operationId: null}, context);
  expect(f.server.send).toHaveBeenCalledOnce();
  expect(f.controller.view.outcome).toMatchObject({kind: 'receipt', state: 'active', occurrenceId: null});
});
test('self completion uses the freshly verified member and actual server-anchored time', async () => {
  const f = fixture(); await f.controller.refresh(); await f.controller.select('work-1');
  f.server.send.mockResolvedValueOnce({...saved, action: 'task.complete', state: 'completed', revision: revisionValue('2')});
  await f.controller.complete(null);
  expect(f.server.send.mock.calls[0][0].command).toEqual({action: 'task.complete', occurrenceId: 'work-1', payload: {
    expected_revision: '1', performer_ids: ['member-1'], performed_at: '1000', material_usages: null}});
});
test('invalid text, expired sessions and read-only grace cannot create work', async () => {
  const f = fixture(); await f.controller.refresh(); await f.controller.create(' ', '', 'normal'); expect(f.server.send).not.toHaveBeenCalled();
  f.session.access = 'read_only'; await f.controller.refresh(); await f.controller.create('New', '', 'normal');
  expect(f.controller.view.notice).toBe('read_only'); expect(f.server.send).not.toHaveBeenCalled();
  f.advance(); f.controller.tick(); expect(f.controller.view.page).toBeNull(); expect(f.controller.view.notice).toBe('authentication_required');
});
test('a changed verified account cannot submit the previous account draft', async () => {
  const f = fixture(); await f.controller.refresh(); f.identity.session.mockImplementation(() => read({...f.session, context: {...context, subject: 'b'.repeat(32)}}));
  await f.controller.create('Private draft', '', 'normal'); expect(f.server.send).not.toHaveBeenCalled();
  expect(f.controller.view.notice).toBe('context_changed');
});
test('closing owns cancellation and fences a late callback', async () => {
  const f = fixture(); let resolve!: (value: typeof f.session) => void;
  const cancel = vi.fn(); f.identity.session.mockReturnValue({result: new Promise(done => {resolve = done;}), cancel});
  const pending = f.controller.refresh(); f.controller.close(); resolve(f.session); await pending;
  expect(cancel).toHaveBeenCalledOnce(); expect(f.controller.view.phase).toBe('closed'); expect(f.server.list).not.toHaveBeenCalled();
});
test('a current permission denial removes task content and never submits a command', async () => {
  const f = fixture(); await f.controller.refresh(); f.server.access.mockImplementation(() => ({result: Promise.reject(new EntryReadError('forbidden')), cancel: vi.fn()}));
  await f.controller.create('New', '', 'normal'); expect(f.server.send).not.toHaveBeenCalled();
  expect(f.controller.view.page).toBeNull(); expect(f.controller.view.notice).toBe('forbidden');
});


test.each(['missing', 'expired', 'wrong_deployment', 'missing_api'])(
  '%s identity cannot probe tasks or prepare writes', async kind => {
    const f = fixture();
    f.identity.session.mockReturnValueOnce(read(kind === 'missing' ? null : {...f.session,
      ...(kind === 'expired' ? {expiresAt: 1000} : {}), ...(kind === 'wrong_deployment' ? {deployment: 'standalone' as const} : {}),
      ...(kind === 'missing_api' ? {householdApiAvailable: false} : {})}));
    await f.controller.refresh(); expect(f.controller.view.page).toBeNull(); expect(f.server.access).not.toHaveBeenCalled();
    await f.controller.create('New', '', 'normal'); expect(f.server.send).not.toHaveBeenCalled();
  });
test('unavailable or corrupt recovery storage allows queries and blocks new task effects', async () => {
  const f = fixture(); vi.spyOn(f.journal, 'open').mockImplementation(() => {throw Error('private storage fault');});
  await f.controller.refresh(); expect(f.controller.view.page?.items).toHaveLength(1); expect(f.controller.view.records).toBeNull();
  await f.controller.create('New', '', 'normal'); expect(f.server.send).not.toHaveBeenCalled(); expect(f.controller.view.notice).toBe('journal_unavailable');
});
test('no task-creation grant and changed current action hints both refuse before posting', async () => {
  const f = fixture(); await f.controller.refresh();
  f.server.access.mockReturnValue(read({householdId: 'home', memberId: 'member-1', canCreate: false, canReviewSchedule: false}));
  await f.controller.create('New', '', 'normal'); expect(f.controller.view.notice).toBe('action_not_allowed');
  await f.controller.select('work-1'); f.server.detail.mockReturnValue(read({...detail, allowedActions: []}));
  await f.controller.claim(); expect(f.controller.view.notice).toBe('action_not_allowed'); expect(f.server.send).not.toHaveBeenCalled();
});
test('a concurrently changed task revision is shown for review without rebasing the submitted intent', async () => {
  const f = fixture(); await f.controller.refresh(); await f.controller.select('work-1');
  f.server.detail.mockReturnValue(read({...detail, revision: revisionValue('2')}));
  await f.controller.claim(); expect(f.controller.view.notice).toBe('conflict'); expect(f.controller.view.detail?.revision).toBe('2');
  expect(f.server.send).not.toHaveBeenCalled();
});
test.each(['household', 'member'])(
  'a changed canonical %s rejects the previous draft even for the same HA identity', async kind => {
    const f = fixture(); await f.controller.refresh(); f.server.access.mockReturnValue(read({householdId: kind === 'household' ? 'other' : 'home',
      memberId: kind === 'member' ? 'replacement' : 'member-1', canCreate: true, canReviewSchedule: true}));
    await f.controller.create('Private draft', '', 'normal'); expect(f.controller.view.notice).toBe('context_changed'); expect(f.server.send).not.toHaveBeenCalled();
  });
test('paging uses the captured opaque cursor, and an authority change refuses its continuation', async () => {
  const f = fixture(); await f.controller.more(); expect(f.identity.session).not.toHaveBeenCalled();
  f.server.list.mockReturnValue(read({items: [detail], nextCursor: 'opaque/+?'})); await f.controller.refresh();
  await f.controller.more(); expect(f.server.list.mock.calls.at(-1)).toEqual([context, 'opaque/+?']); expect(f.controller.view.detail).toBeNull();
  f.server.access.mockReturnValue(read({householdId: 'other', memberId: 'member-1', canCreate: true, canReviewSchedule: true}));
  const calls = f.server.list.mock.calls.length; await f.controller.more(); expect(f.server.list).toHaveBeenCalledTimes(calls);
  expect(f.controller.view.notice).toBe('context_changed');
});
test('selection accepts only an identifier and does not carry a task into another verified scope', async () => {
  const f = fixture(); await f.controller.select('../work'); expect(f.identity.session).not.toHaveBeenCalled();
  await f.controller.refresh(); f.server.access.mockReturnValue(read({householdId: 'other', memberId: 'member-1', canCreate: true, canReviewSchedule: true}));
  await f.controller.select('work-1'); expect(f.server.detail).not.toHaveBeenCalled(); expect(f.controller.view.notice).toBe('context_changed');
});
test('no selected work or cycle means no implicit claim, completion, review or reopening', async () => {
  const f = fixture(); await f.controller.claim(); await f.controller.complete(null); await f.controller.verify('approved', ''); await f.controller.reopen('Repeat');
  await f.controller.refresh(); await f.controller.select('work-1'); await f.controller.verify('approved', ''); await f.controller.reopen('Repeat');
  expect(f.server.send).not.toHaveBeenCalled();
});
test.each(['approved', 'rejected', 'reopen'] as const)('current cycle %s uses its exact identity and revision', async decision => {
  const f = fixture(), cycle = {cycleId: 'cycle-1', verification: 'pending' as const, performedAt: '90', performerIds: ['member-1']};
  f.server.detail.mockReturnValue(read({...detail, cycle, state: 'completed', allowedActions: ['approve', 'reject', 'reopen']}));
  await f.controller.refresh(); await f.controller.select('work-1');
  if (decision === 'reopen') await f.controller.reopen('Repeat'); else await f.controller.verify(decision, 'Reviewed');
  expect(f.server.send).toHaveBeenCalledOnce(); const command = f.server.send.mock.calls[0][0].command;
  expect(command).toMatchObject({action: decision === 'reopen' ? 'task.reopen' : 'task.verify', occurrenceId: 'work-1', payload: {expected_revision: '1', cycle_id: 'cycle-1'}});
});
test('an exhausted or unavailable request key and a failed journal write cannot reach the server', async () => {
  const f = fixture(); await f.controller.refresh(); f.entropy.requestKey.mockImplementationOnce(() => {throw Error('entropy unavailable');});
  await f.controller.create('New', '', 'normal'); expect(f.controller.view.notice).toBe('journal_unavailable');
  vi.spyOn(f.journal, 'prepare').mockImplementationOnce(() => {throw Error('storage changed');});
  await f.controller.create('New', '', 'normal'); expect(f.server.send).not.toHaveBeenCalled();
});
test('failure to save a returned receipt retains its original prepared key and reports recovery storage failure', async () => {
  const f = fixture(); await f.controller.refresh(); vi.spyOn(f.journal, 'record').mockImplementationOnce(() => {throw Error('storage unavailable');});
  await f.controller.create('New', '', 'normal'); expect(f.controller.view.outcome).toEqual(saved);
  expect(f.controller.view.notice).toBe('journal_unavailable'); expect(f.controller.view.records?.[0].stage).toBe('prepared');
  await f.controller.recover('key-1'); expect(f.server.original).toHaveBeenCalledOnce(); expect(f.controller.view.records?.[0].stage).toBe('committed');
});
test.each(['authentication_required', 'forbidden', 'conflict'] as const)('current write rejection %s is recorded without retry', async reason => {
  const f = fixture(); await f.controller.refresh(); f.server.send.mockResolvedValueOnce({kind: 'rejected', reason, correlationId: 'cor_safe'});
  await f.controller.create('New', '', 'normal'); expect(f.server.send).toHaveBeenCalledOnce();
  if (reason === 'conflict') expect(f.controller.view.records?.[0].stage).toBe('rejected');
  else {expect(f.controller.view.notice).toBe(reason); expect(f.controller.view.page).toBeNull();}
});
test('a slow posted command can finish after closure without repopulating private data or sending twice', async () => {
  const f = fixture(); await f.controller.refresh(); let resolve!: (value: TaskReceipt) => void;
  f.server.send.mockImplementationOnce(() => new Promise(done => {resolve = done;}));
  const pending = f.controller.create('New', '', 'normal'); await vi.waitFor(() => expect(f.server.send).toHaveBeenCalledOnce());
  await f.controller.create('Duplicate', '', 'normal'); f.controller.close(); resolve(saved); await pending;
  expect(f.controller.view.phase).toBe('closed'); expect(f.controller.view.outcome).toBeNull(); expect(f.server.send).toHaveBeenCalledOnce();
  await f.controller.refresh(); f.controller.tick(); expect(f.controller.view.phase).toBe('closed');
});
test('session expiry during a query or after a posted result hides facts and keeps original evidence', async () => {
  const f = fixture(); let resolve!: (value: {items: TaskDetail[]; nextCursor: null}) => void;
  f.server.list.mockReturnValueOnce({result: new Promise(done => {resolve = done;}), cancel: vi.fn()});
  const pending = f.controller.refresh(); await vi.waitFor(() => expect(f.server.list).toHaveBeenCalledOnce());
  f.advance(); resolve({items: [detail], nextCursor: null}); await pending;
  expect(f.controller.view.notice).toBe('authentication_required'); expect(f.controller.view.page).toBeNull();
  await f.controller.refresh(); f.server.send.mockImplementationOnce(async () => {f.advance(); return saved;});
  await f.controller.create('New', '', 'normal'); expect(f.controller.view.notice).toBe('authentication_required');
});
test('a clock fault refuses completion and a later unknown lease retires the view', async () => {
  const f = fixture(); await f.controller.refresh(); await f.controller.select('work-1');
  f.clock.now.mockImplementationOnce(() => {throw Error('clock unavailable');}); await f.controller.complete(null);
  expect(f.server.send).not.toHaveBeenCalled(); expect(f.controller.view.notice).toBe('unavailable');
  f.clock.now.mockImplementationOnce(() => {throw Error('clock unavailable');}); f.controller.tick(); expect(f.controller.view.page).toBeNull();
});
test('a missing or expired original is not looked up or replaced, and unresolved dismissal fails safely', async () => {
  const f = fixture(); await f.controller.recover('missing'); expect(f.identity.session).not.toHaveBeenCalled();
  await f.controller.refresh(); f.server.send.mockResolvedValueOnce({kind: 'uncertain'}); await f.controller.create('New', '', 'normal');
  await f.controller.dismiss('key-1'); expect(f.controller.view.notice).toBe('request_unavailable');
  f.storage.clear(); await f.controller.recover('key-1'); expect(f.controller.view.notice).toBe('request_changed'); expect(f.server.original).not.toHaveBeenCalled();
});
test('resolved originals can be explicitly dismissed without changing tasks or server history', async () => {
  const f = fixture(); await f.controller.refresh(); await f.controller.create('New', '', 'normal'); await f.controller.dismiss('key-1');
  expect(f.controller.view.records).toEqual([]); expect(f.controller.view.page?.items).toHaveLength(1); expect(f.server.send).toHaveBeenCalledOnce();
});
test.each(['recover', 'dismiss'] as const)('a changed owner cannot %s an earlier private task request', async method => {
  const f = fixture(); await f.controller.refresh(); await f.controller.create('New', '', 'normal');
  f.server.access.mockReturnValue(read({householdId: 'home', memberId: 'replacement', canCreate: true, canReviewSchedule: true}));
  await f.controller[method]('key-1'); expect(f.controller.view.notice).toBe('context_changed'); expect(f.server.original).not.toHaveBeenCalled();
});
test('retired cancellation errors and unavailable server reads cannot disclose internal diagnostics', async () => {
  const f = fixture(); let resolve!: (value: VerifiedEntrySession | null) => void;
  f.identity.session.mockReturnValueOnce({result: new Promise(done => {resolve = done;}), cancel: vi.fn(() => {throw Error('private cancel fault');})});
  const pending = f.controller.refresh(); f.controller.close(); resolve(f.session); await pending; expect(f.controller.view.phase).toBe('closed');
  const next = fixture(); next.identity.session.mockReturnValueOnce({result: Promise.reject(Error('private transport')), cancel: vi.fn()});
  await next.controller.refresh(); expect(next.controller.view.notice).toBe('unavailable'); expect(JSON.stringify(next.controller.view)).not.toContain('private transport');
});
test('expired journal entries are pruned without a new proof request or a busy timer loop', async () => {
  const f = fixture(); f.session.expiresAt = 10_000_000; await f.controller.refresh(); await f.controller.create('New', '', 'normal');
  const count = f.identity.session.mock.calls.length; f.setNow(3_601_000); f.controller.tick();
  expect(f.controller.view.records).toEqual([]); expect(f.controller.view.page?.items).toHaveLength(1); expect(f.identity.session).toHaveBeenCalledTimes(count);
});


test('full recovery storage asks the user to review saved requests without evicting them or posting', async () => {
  const f = fixture(); await f.controller.refresh();
  vi.spyOn(f.journal, 'prepare').mockImplementationOnce(() => {throw new JournalError('journal_capacity');});
  await f.controller.create('New', '', 'normal'); expect(f.controller.view.notice).toBe('journal_capacity'); expect(f.server.send).not.toHaveBeenCalled();
});
test('expiry cleanup failure hides recovery records and never renews session proof', async () => {
  const f = fixture(); f.session.expiresAt = 10_000_000; await f.controller.refresh(); await f.controller.create('New', '', 'normal');
  vi.spyOn(f.journal, 'open').mockImplementationOnce(() => {throw Error('storage changed');}); f.setNow(3601000); f.controller.tick();
  expect(f.controller.view.records).toBeNull(); expect(f.controller.view.notice).toBe('journal_unavailable');
});


test('a detail response for a different task cannot authorize a command against the selected one', async () => {
  const f = fixture(); await f.controller.refresh(); await f.controller.select('work-1'); f.server.detail.mockReturnValue(read({...detail, occurrenceId: 'other'}));
  await f.controller.claim(); expect(f.server.send).not.toHaveBeenCalled(); expect(f.controller.view.notice).toBe('action_not_allowed');
});
test.each(['journal_too_large', 'duplicate_request'] as const)('journal %s refuses without posting or inventing a new key', async code => {
  const f = fixture(); await f.controller.refresh(); vi.spyOn(f.journal, 'prepare').mockImplementationOnce(() => {throw new JournalError(code);});
  await f.controller.create('New', '', 'normal'); expect(f.controller.view.notice).toBe(code === 'journal_too_large' ? 'journal_capacity' : 'journal_unavailable');
  expect(f.server.send).not.toHaveBeenCalled(); expect(f.entropy.requestKey).toHaveBeenCalledOnce();
});

test('Next page replaces one bounded page and Refresh tasks returns to the first page with fresh authority', async () => {
  const f = fixture(), first = {...detail, occurrenceId: 'work-first'}, next = {...detail, occurrenceId: 'work-next'};
  f.server.list.mockReturnValueOnce(read({items: [first], nextCursor: 'next-page'}));
  await f.controller.refresh(); expect(f.controller.view.page?.items.map(item => item.occurrenceId)).toEqual(['work-first']);
  f.server.list.mockReturnValueOnce(read({items: [next], nextCursor: null}));
  await f.controller.more(); expect(f.controller.view.page?.items.map(item => item.occurrenceId)).toEqual(['work-next']);
  expect(f.server.list.mock.calls.at(-1)).toEqual([context, 'next-page']);
  f.server.list.mockReturnValueOnce(read({items: [first], nextCursor: 'next-page'}));
  await f.controller.refresh(); expect(f.controller.view.page?.items.map(item => item.occurrenceId)).toEqual(['work-first']);
  expect(f.server.list.mock.calls.at(-1)).toEqual([context, null]); expect(f.identity.session).toHaveBeenCalledTimes(3);
});

test('category writes share the original journal and refresh only the still-current household', async () => {
  const f = fixture(), category = {id:'garden', label:'Garden', revision};
  const access = {householdId:'home', memberId:'member-1', canCreate:true, canReviewSchedule:true,
    categoryCatalog:{canManage:true, categories:[category]}};
  const categoryReceipt = {...saved, action:'task.category.create' as const, occurrenceId:null, state:'active' as const};
  f.server.access.mockImplementation(() => read(access));
  await f.controller.refresh();
  await f.controller.create('Draft', '', 'normal', undefined, 'foreign');
  expect(f.controller.view.notice).toBe('category_unavailable');
  expect(f.server.send).not.toHaveBeenCalled();
  await f.controller.renameCategory('garden', revisionValue('2'), 'Kitchen');
  expect(f.controller.view.notice).toBe('conflict');
  await f.controller.select('work-1');
  f.server.send.mockResolvedValueOnce({kind:'uncertain'});
  await f.controller.createCategory('Garden');
  expect(f.controller.view.records?.[0].stage).toBe('uncertain');
  f.server.original.mockReturnValueOnce(read(categoryReceipt));
  await f.controller.recover('key-1');
  expect(f.controller.view.outcome).toEqual(categoryReceipt);
  expect(f.server.send).toHaveBeenCalledTimes(1);
  f.server.send.mockResolvedValueOnce({...categoryReceipt, action:'task.category.rename'});
  await f.controller.renameCategory('garden', revision, 'Kitchen');
  expect(f.controller.view.access?.categoryCatalog?.canManage).toBe(true);
  await f.controller.create('Classified', '', 'normal', undefined, 'garden');
  expect(f.server.send.mock.calls.at(-1)?.[0].command.payload).toMatchObject({category_id:'garden'});
  f.server.access.mockReturnValueOnce(read(access)).mockReturnValueOnce(read({...access, memberId:'other'}));
  f.server.send.mockResolvedValueOnce({...categoryReceipt, action:'task.category.archive', state:'archived'});
  await f.controller.archiveCategory('garden', revision);
  expect(f.controller.view.notice).toBe('context_changed');
  expect(f.controller.view.records).toBeNull();
  expect(f.controller.view.outcome).toBeNull();
});

test('a task reader with no current category-management permission cannot write a category', async () => {
  const f = fixture();
  await f.controller.refresh();
  await f.controller.createCategory('Garden');
  expect(f.controller.view.notice).toBe('action_not_allowed');
  expect(f.server.send).not.toHaveBeenCalled();
});

test('reviewed completion rejects a different task revision and keeps manual shares under the original request', async () => {
  const f = fixture();
  await f.controller.refresh();
  await f.controller.select('work-1');
  const reviewed = {occurrenceId: 'work-1', revision, performerIds: ['member-1', 'other'],
    manualShares: [{member_id: 'member-1', amount_minor: 0}, {member_id: 'other', amount_minor: 150}], fingerprint: 'a'.repeat(64)};
  await f.controller.complete(null, {...reviewed, occurrenceId: 'elsewhere'});
  await f.controller.complete(null, {...reviewed, revision: revisionValue('2')});
  expect(f.controller.view.notice).toBe('conflict');
  expect(f.server.send).not.toHaveBeenCalled();
  f.server.send.mockResolvedValueOnce({kind: 'uncertain'});
  await f.controller.complete(null, reviewed);
  expect(f.server.send.mock.calls[0][0].command).toMatchObject({action: 'task.complete', payload: {
    performer_ids: reviewed.performerIds, allocation_fingerprint: reviewed.fingerprint, manual_shares: reviewed.manualShares,
  }});
  expect(f.controller.view.records?.[0].stage).toBe('uncertain');
});
