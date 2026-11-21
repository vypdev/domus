import {expect, test, vi} from 'vitest';
import {DailyAutomationController} from '../src/application/automation-daily';
import type {DailyRequest, DailyResult, DailyServer, DailyView} from '../src/application/automation-daily';
import {DAILY_AUTOMATION_JOURNAL_KEY, DailyAutomationSessionJournal} from '../src/adapters/automation-daily-journal';
import {EntryReadError} from '../src/application/ports';
import {active, failed, inactive, one, point, scope, selection, settled, two} from './automation-daily-fixtures';

const enabled: DailyResult = {kind: 'committed', action: 'enable', ruleId: 'rule', ruleRevision: two, operationId: 'operation', next: point()};
const request: DailyRequest = {kind: 'enable', ruleId: 'rule', ruleRevision: two, controlRevision: '0', scheduleRevision: '0',
  reviewed: point(), key: 'daily-key', scope: scope.key};
function fixture() {
  const storage = new Map<string, string>();
  const remove = vi.fn((key: string) => {storage.delete(key);});
  const journal = new DailyAutomationSessionJournal({getItem: key => storage.get(key) ?? null,
    setItem: (key, value) => {storage.set(key, value);}, removeItem: remove});
  const server = {active: vi.fn<DailyServer['active']>(() => settled(null)), review: vi.fn<DailyServer['review']>(() => settled(inactive)),
    send: vi.fn<DailyServer['send']>(() => settled(enabled)), original: vi.fn<DailyServer['original']>(() => settled({kind: 'missing'}))};
  const publish = vi.fn(), changed = vi.fn();
  const owner = () => new DailyAutomationController(server, journal, {requestKey: () => 'daily-key'}, publish, changed);
  const last = () => publish.mock.lastCall?.[0] as DailyView | null;
  const ready = async (controller: DailyAutomationController, value = inactive) => {
    controller.bind(scope, selection);
    await vi.waitFor(() => expect(last()).toMatchObject({review: value, busy: false}));
  };
  return {storage, remove, journal, server, publish, changed, owner, last, ready};
}

test('daily grants bind the saved revision, require deliberate confirmation and retain success if refresh fails', async () => {
  const f = fixture(), owner = f.owner();
  await owner.handle('confirm');
  owner.bind(scope, null);
  expect(f.last()).toBeNull();
  await owner.handle('enable');
  await owner.handle('confirm');
  await f.ready(owner);
  await owner.handle('disable'); await owner.handle('adopt'); await owner.handle('confirm');
  expect(f.server.send).not.toHaveBeenCalled();
  await owner.handle('enable');
  expect(f.last()?.confirmation).toEqual({kind: 'enable', ruleId: 'rule', ruleRevision: two,
    controlRevision: '0', scheduleRevision: '0', reviewed: point()});
  expect(f.server.send).not.toHaveBeenCalled();
  owner.bind({...scope, readOnly: true}, selection);
  await owner.handle('confirm');
  expect(f.server.send).not.toHaveBeenCalled();
  await owner.handle('cancel');
  expect(f.last()?.confirmation).toBeNull();
  owner.bind(scope, selection);
  await owner.handle('enable');
  f.server.review.mockReturnValueOnce(failed());
  await owner.handle('confirm');
  expect(f.server.send).toHaveBeenCalledWith(scope, request);
  expect(f.last()).toMatchObject({result: enabled, review: null, pending: false, notice: 'unavailable'});
  expect(f.journal.open(scope.key)).toBeNull();
  expect(f.changed).toHaveBeenCalledOnce();
  await owner.handle('reload');
  expect(f.last()).toMatchObject({result: enabled, review: inactive, notice: null});
});

test('unknown outcomes recover the exact original before an explicit same-key resend, including in read-only sessions', async () => {
  const f = fixture(), owner = f.owner();
  await f.ready(owner);
  await owner.handle('recover');
  f.server.send.mockReturnValueOnce(failed());
  await owner.handle('enable'); await owner.handle('confirm');
  expect(f.last()).toMatchObject({pending: true, notice: 'uncertain'});
  expect(f.last()?.review).toBeNull();
  expect(f.journal.open(scope.key)).toEqual(request);
  await owner.handle('enable');
  expect(f.last()?.confirmation).toBeNull();
  owner.bind(scope, {id: 'another-rule', revision: one});
  await vi.waitFor(() => expect(f.last()?.busy).toBe(false));
  expect(f.server.review).toHaveBeenLastCalledWith(scope, 'rule', two);
  owner.bind(null, null);
  const reopened = f.owner();
  reopened.bind({...scope, readOnly: true}, null);
  await vi.waitFor(() => expect(f.last()).toMatchObject({pending: true, busy: false}));
  await reopened.handle('recover');
  expect(f.server.original).toHaveBeenCalledWith({...scope, readOnly: true}, request);
  expect(f.server.send).toHaveBeenCalledTimes(1);
  reopened.bind(scope, null);
  await reopened.handle('recover');
  expect(f.server.send).toHaveBeenLastCalledWith(scope, request);
  expect(f.last()).toMatchObject({result: enabled, pending: false, review: inactive});
  expect(f.journal.open(scope.key)).toBeNull();
});

test('reload recovery keeps a read-only route to the original rule without selecting or changing another draft', async () => {
  const f = fixture(), owner = f.owner();
  f.journal.save(request);
  owner.bind(scope, null);
  await vi.waitFor(() => expect(f.last()).toMatchObject({pending:true,busy:false}));
  f.server.original.mockReturnValueOnce(settled(enabled));
  f.server.review.mockReturnValueOnce(failed());
  await owner.handle('recover');
  expect(f.last()).toMatchObject({result:enabled,review:null,notice:'unavailable',savedRevision:null,pending:false});
  const current = {...active,ruleRevision:two,activeRevision:two};
  f.server.review.mockReturnValueOnce(settled(current));
  await owner.handle('reload');
  expect(f.server.review).toHaveBeenLastCalledWith(scope,'rule',two);
  expect(f.last()).toMatchObject({result:enabled,review:current,savedRevision:null,notice:null});
  expect(f.server.send).not.toHaveBeenCalled();
  owner.bind({...scope,authorization:'no-longer-authorized'},null);
  await vi.waitFor(() => expect(f.last()).toBeNull());
});

test('authorization and timing changes cancel stale reviews without changing the journal owner', async () => {
  const f = fixture(), owner = f.owner();
  const slow = Promise.withResolvers<typeof inactive>(), cancel = vi.fn();
  f.server.review.mockReturnValueOnce({result: slow.promise, cancel});
  owner.bind(scope, selection);
  owner.bind({...scope, authorization: 'policy-2'}, selection);
  slow.resolve({...active, title: 'Private old result'});
  await vi.waitFor(() => expect(f.last()).toMatchObject({review: inactive, busy: false}));
  expect(cancel).toHaveBeenCalledOnce();
  const rejected = Promise.withResolvers<typeof inactive>();
  f.server.review.mockReturnValueOnce({result: rejected.promise, cancel: vi.fn()});
  owner.bind({...scope, timing: 'policy-2'}, selection);
  owner.bind(null, null);
  rejected.reject(new EntryReadError('forbidden'));
  await vi.waitFor(() => expect(f.last()).toBeNull());
  f.journal.save(request);
  f.server.review.mockReturnValueOnce(failed());
  owner.bind(scope, selection);
  await vi.waitFor(() => expect(f.last()).toMatchObject({pending: true, notice: 'uncertain', busy: false}));
  owner.bind({...scope, timing: 'new-time-zone'}, selection);
  await vi.waitFor(() => expect(f.last()).toMatchObject({pending: true, busy: false}));
  expect(f.journal.open(scope.key)).toEqual(request);
  f.server.original.mockReturnValueOnce(failed(new EntryReadError('forbidden')));
  f.remove.mockImplementationOnce(() => {throw new Error('storage unavailable');});
  await owner.handle('recover');
  expect(f.last()).toMatchObject({notice: 'denied', review: null, result: null, pending: false});
  expect(f.server.send).not.toHaveBeenCalled();
});

test('current management permission can revoke a grant without task-create permission and adoption uses the active saved revision', async () => {
  const f = fixture(), owner = f.owner();
  f.server.review.mockReturnValue(settled({...active, mayEnable: false, policyChanged: true}));
  await f.ready(owner, {...active, mayEnable: false, policyChanged: true});
  await owner.handle('enable'); await owner.handle('adopt');
  expect(f.last()?.confirmation).toBeNull();
  await owner.handle('disable');
  expect(f.last()?.confirmation).toMatchObject({kind: 'disable', ruleRevision: one});
  await owner.handle('cancel');
  f.server.review.mockReturnValueOnce(settled({...active, ruleRevision: one, mayEnable: false, policyChanged: true}));
  await owner.handle('active');
  expect(f.server.review).toHaveBeenLastCalledWith(scope, 'rule', one);
  await owner.handle('adopt');
  expect(f.last()?.confirmation).toMatchObject({kind: 'adopt', ruleRevision: one, reviewed: point()});
  await owner.handle('cancel');
  await owner.handle('saved');
  expect(f.server.review).toHaveBeenLastCalledWith(scope, 'rule', two);
  f.server.review.mockReturnValueOnce(settled({...active, activeRevision: two}));
  await owner.handle('reload');
  await owner.handle('enable'); await owner.handle('adopt');
  expect(f.last()?.confirmation).toBeNull();
  f.server.send.mockReturnValueOnce(settled({kind: 'stale'}));
  await owner.handle('disable'); await owner.handle('confirm');
  expect(f.last()?.notice).toBe('stale');
  expect(f.server.send.mock.lastCall?.[1]).not.toHaveProperty('reviewed');
  f.server.active.mockReturnValueOnce(settled({...active, ruleRevision: one}));
  owner.bind(scope, {id: 'rule', revision: two, activeDaily: one});
  await vi.waitFor(() => expect(f.server.active).toHaveBeenLastCalledWith(scope, 'rule'));
  await vi.waitFor(() => expect(f.last()?.busy).toBe(false));
  owner.bind(scope, {id: 'rule', revision: two});
  expect(f.last()?.review ?? null).toBeNull();
});

test('a config-only manager discovers and can revoke an active daily revision while the selected saved draft is manual', async () => {
  const f = fixture(), owner = f.owner();
  const current = {...active, ruleRevision: one, mayEnable: false};
  f.server.active.mockReturnValueOnce(settled(current));
  owner.bind(scope, {id: 'rule', revision: two});
  await vi.waitFor(() => expect(f.last()).toMatchObject({review: current, savedRevision: null, readOnly: false, busy: false}));
  expect(f.server.active).toHaveBeenCalledWith(scope, 'rule');
  expect(f.server.review).not.toHaveBeenCalled();
  await owner.handle('enable');
  expect(f.last()?.confirmation).toBeNull();
  await owner.handle('disable');
  expect(f.last()?.confirmation).toMatchObject({kind: 'disable', ruleRevision: one});
});

test('a verified commit stays visible when local receipt retirement fails, and can be recovered without a replacement write', async () => {
  const f = fixture(), owner = f.owner();
  await f.ready(owner);
  await owner.handle('enable');
  f.remove.mockImplementationOnce(() => {throw new Error('blocked storage');});
  await owner.handle('confirm');
  expect(f.last()).toMatchObject({result: enabled, pending: true, notice: 'journal_unavailable'});
  expect(f.journal.open(scope.key)).toEqual(request);
  f.server.original.mockReturnValueOnce(settled({...enabled, kind: 'historical'}));
  await owner.handle('recover');
  expect(f.last()).toMatchObject({result: {...enabled, kind: 'historical'}, pending: false, notice: null});
  expect(f.server.send).toHaveBeenCalledTimes(1);
  expect(f.journal.open(scope.key)).toBeNull();
});

test('unavailable journals block sending, and authentication rejection retires all private facts', async () => {
  const f = fixture(), owner = f.owner();
  f.storage.set(DAILY_AUTOMATION_JOURNAL_KEY, '{}');
  await f.ready(owner);
  expect(f.last()?.notice).toBe('journal_unavailable');
  await owner.handle('enable'); await owner.handle('confirm');
  expect(f.server.send).not.toHaveBeenCalled();
  expect(f.last()?.notice).toBe('record_failed');
  f.server.review.mockReturnValueOnce(failed(new EntryReadError('authentication_required')));
  await owner.handle('reload');
  expect(f.last()).toMatchObject({notice: 'denied', review: null, confirmation: null});
  await owner.handle('active');
  owner.bind({...scope, key: 'new-owner'}, null);
  expect(f.last()).toBeNull();
});

test('a scope change during missing-original recovery cannot resend under either scope', async () => {
  const f = fixture(), owner = f.owner();
  f.journal.save(request);
  await f.ready(owner);
  const delayed = Promise.withResolvers<{kind: 'missing'}>(), cancel = vi.fn();
  f.server.original.mockReturnValueOnce({result: delayed.promise, cancel});
  const recovery = owner.handle('recover');
  await owner.handle('confirm'); // Busy requests cannot start another command.
  owner.bind({...scope, key: 'different-household'}, null);
  delayed.resolve({kind: 'missing'});
  await recovery;
  expect(cancel).toHaveBeenCalledOnce();
  expect(f.server.send).not.toHaveBeenCalled();
  expect(f.last()).toBeNull();
});

test('the journal keeps exact reviewed evidence and rejects incompatible scope, actions, revisions and malformed records', () => {
  const f = fixture();
  expect(f.journal.open(scope.key)).toBeNull();
  f.journal.save(request);
  expect(f.journal.open(scope.key)).toEqual(request);
  expect(f.journal.open('another-owner')).toBeNull();
  const disable: DailyRequest = {kind: 'disable', ruleId: 'rule', ruleRevision: one, controlRevision: two,
    scheduleRevision: one, key: 'disable', scope: scope.key};
  f.journal.save(disable);
  expect(f.journal.open(scope.key)).toEqual(disable);
  f.journal.clear(disable);
  for (const invalid of [{...disable, reviewed: point()}, {...request, reviewed: undefined}, {...request, ruleRevision: '01'},
    {...request, controlRevision: 0}, {...request, scheduleRevision: '01'}, {...request, kind: 'run'},
    {...request, reviewed: {...point(), offsetSeconds: 90000}}, {...request, scope: 'x'.repeat(4097)}])
    expect(() => f.journal.save(invalid as DailyRequest)).toThrow();
  f.storage.set(DAILY_AUTOMATION_JOURNAL_KEY, JSON.stringify({...request, admin: true}));
  expect(() => f.journal.open(scope.key)).toThrow();
});

test('unavailable current timing blocks grants and adoption while retaining deliberate revocation', async () => {
  const f = fixture(), owner = f.owner();
  const unavailable = {...active, activeRevision: two, proposedTimes: [], proposedUnavailable: true, policyChanged: true};
  f.server.review.mockReturnValue(settled(unavailable));
  await f.ready(owner, unavailable);
  await owner.handle('enable'); await owner.handle('adopt');
  expect(f.last()?.confirmation).toBeNull();
  await owner.handle('disable');
  expect(f.last()?.confirmation).toMatchObject({kind: 'disable', ruleRevision: two});
});

test('navigation during the post-commit refresh cannot reload or repopulate the former household', async () => {
  const f = fixture(), owner = f.owner();
  await f.ready(owner);
  const delayed = Promise.withResolvers<typeof inactive>(), cancel = vi.fn();
  f.server.review.mockReturnValueOnce({result: delayed.promise, cancel});
  await owner.handle('enable');
  const committing = owner.handle('confirm');
  await vi.waitFor(() => expect(f.server.review).toHaveBeenCalledTimes(2));
  expect(f.last()?.result).toEqual(enabled);
  owner.bind(null, null);
  delayed.resolve(active);
  await committing;
  expect(cancel).toHaveBeenCalledOnce();
  expect(f.changed).not.toHaveBeenCalled();
  expect(f.last()).toBeNull();
  expect(f.journal.open(scope.key)).toBeNull();
});
