import {expect, test, vi} from 'vitest';
import {EntryController} from '../src/application/entry-controller';
import {EntryReadError, JournalStorageError} from '../src/application/ports';
import type {CommandResult, EntryRead, EntryReceipt, EntryServer, VerifiedEntrySession} from '../src/application/ports';
import type {Authorization} from '../src/domain/entry';
import {SessionJournal} from '../src/adapters/session-journal';
import {ENTRY_JOURNAL_KEY} from '../src/adapters/session-journal';

function deferred<T>() {
  let resolve!: (value: T) => void, reject!: (error: unknown) => void;
  const result = new Promise<T>((yes, no) => {resolve = yes; reject = no;});
  return {result, resolve, reject, cancel: vi.fn()};
}
function read<T>(value: T): EntryRead<T> {return {result: Promise.resolve(value), cancel: vi.fn()};}
const context = {installationId: '01234567-89ab-cdef-0123-456789abcdef', channel: 'edge' as const, subject: 'user-1'};
const session: VerifiedEntrySession = {context, deployment: 'standalone', access: 'full', serverTime: 1000,
  expiresAt: 1_000_000, householdApiAvailable: true};
const setup: Authorization = {state: 'unconfigured', setupAllowed: true, enrollmentAllowed: false, permissions: []};
const eligible: Authorization = {...setup, state: 'not_enrolled', setupAllowed: false, enrollmentAllowed: true};
const pending: Authorization = {...eligible, state: 'pending', enrollmentAllowed: false};
const active: Authorization = {...pending, state: 'active', permissions: ['household.read', 'household.manage']};
const household = {householdId: 'home', name: 'Home', timeZone: 'Europe/Madrid', revision: 1};
const receipt: EntryReceipt = {kind: 'receipt', stage: 'committed', operationId: 'op-original', archivedBy: null,
  createdAt: 1000, result: {household_id: 'home', revision: 1}};
function fixture(authorization = setup) {
  let now = 1000;
  const values = new Map<string, string>();
  const storage = {getItem: (key: string) => values.get(key) ?? null,
    setItem: vi.fn((key: string, value: string) => {values.set(key, value);}),
    removeItem: vi.fn((key: string) => {values.delete(key);})};
  const journal = new SessionJournal(storage);
  const server = {session: vi.fn(() => read<VerifiedEntrySession | null>(session)),
    authorization: vi.fn(() => read(authorization)), household: vi.fn(() => read(household)),
    operation: vi.fn(() => read({...receipt, delivery: 'pending' as const})),
    send: vi.fn((_request: Parameters<EntryServer['send']>[0]) => Promise.resolve<CommandResult>(receipt)),
    logout: vi.fn(() => Promise.resolve({upstreamRevoked: true as boolean | null}))};
  const clock = {anchor: vi.fn((_time: number) => {}), now: vi.fn(() => now)};
  const entropy = {requestKey: vi.fn(() => 'key-original')};
  const controller = new EntryController('standalone', server, journal, clock, entropy);
  return {controller, server, journal, storage, values, clock, entropy, setNow: (time: number) => {now = time;}};
}
async function settle() {for (let i = 0; i < 12; i++) await Promise.resolve();}

test('C09: opening and refreshing only read; setup needs an explicit prepared submission', async () => {
  const f = fixture(); expect(f.controller.view.phase).toBe('idle');
  await f.controller.refresh(); await f.controller.refresh();
  expect(f.controller.view.decision?.action).toBe('create_household');
  expect(f.server.send).not.toHaveBeenCalled(); expect(f.entropy.requestKey).not.toHaveBeenCalled();
  f.server.send.mockImplementation(async request => {
    expect(JSON.parse(f.values.get(ENTRY_JOURNAL_KEY)!).records[0]).toMatchObject({...request, stage: 'prepared'});
    expect(f.controller.view.phase).toBe('sending');
    f.server.authorization.mockImplementation(() => read(active));
    return receipt;
  });
  await f.controller.submitSetup('  Home  ', 'Europe/Madrid');
  expect(f.server.send).toHaveBeenCalledExactlyOnceWith({action: 'setup', key: 'key-original',
    payload: {name: 'Home', time_zone: 'Europe/Madrid', expected_revision: 0, mapping_mode: 'all_ha_administrators'}}, context);
  expect(f.controller.view.outcome).toEqual(receipt);
  expect(f.controller.view.household).toEqual(household);
  expect(f.server.authorization).toHaveBeenLastCalledWith(context);
  expect(f.server.household).toHaveBeenLastCalledWith(context);
  expect(f.controller.view.journal?.records[0]).toMatchObject({stage: 'committed', operationId: 'op-original'});
  expect(f.controller.view.busy).toBe(false);
});

test('C04/C24: invalid input and pre-send persistence failure never send or lose the draft errors', async () => {
  const f = fixture(); await f.controller.refresh();
  await f.controller.submitSetup('', '\n');
  expect(f.controller.view.fields).toEqual(['name', 'time_zone']);
  expect(f.entropy.requestKey).not.toHaveBeenCalled();
  f.storage.setItem.mockImplementation(() => {throw new Error('private-provider-error');});
  await f.controller.submitSetup('Home', 'UTC');
  expect(f.controller.view.notice).toBe('journal_unavailable');
  expect(f.server.send).not.toHaveBeenCalled();
  expect(JSON.stringify(f.controller.view)).not.toContain('private-provider-error');
});

test('C11: repeated submission during preflight or send uses one key and one command', async () => {
  const f = fixture(eligible); await f.controller.refresh();
  const proof = deferred<VerifiedEntrySession | null>(), sent = deferred<CommandResult>();
  f.server.session.mockReturnValueOnce(proof); f.server.send.mockReturnValueOnce(sent.result);
  const first = f.controller.requestMembership();
  await f.controller.requestMembership(); await f.controller.submitSetup('Home', 'UTC');
  expect(f.controller.view.busy).toBe(true); expect(f.entropy.requestKey).not.toHaveBeenCalled();
  proof.resolve(session); await settle();
  await f.controller.requestMembership();
  expect(f.server.send).toHaveBeenCalledTimes(1); expect(f.entropy.requestKey).toHaveBeenCalledTimes(1);
  sent.resolve(receipt); await first; expect(f.controller.view.busy).toBe(false);
});

test('C12/C17: lost response retains the original and fresh pending membership permits deliberate recovery', async () => {
  const f = fixture(eligible); await f.controller.refresh();
  f.server.send.mockImplementationOnce(async () => {throw new Error('lost after commit');});
  await f.controller.requestMembership();
  const original = f.controller.view.journal!.records[0];
  expect(original.stage).toBe('uncertain'); expect(f.controller.view.outcome).toEqual({kind: 'uncertain'});
  f.server.authorization.mockImplementation(() => read(pending));
  await f.controller.refresh(); await f.controller.requestMembership();
  expect(f.server.send).toHaveBeenCalledTimes(1);
  await f.controller.recover(original.key);
  expect(f.server.send).toHaveBeenCalledTimes(2);
  expect(f.server.send.mock.calls[1]).toEqual(f.server.send.mock.calls[0]);
  expect(f.entropy.requestKey).toHaveBeenCalledTimes(1);
  expect(f.controller.view.journal?.records[0]).toMatchObject({createdAt: original.createdAt,
    expiresAt: original.expiresAt, stage: 'committed', operationId: 'op-original'});
});

test('C24: a received receipt survives a journal failure and current-state refresh', async () => {
  const f = fixture(); await f.controller.refresh();
  f.server.send.mockImplementation(async () => {
    f.storage.setItem.mockImplementation(() => {throw new Error('post-commit failure');});
    return receipt;
  });
  await f.controller.submitSetup('Home', 'UTC');
  expect(f.controller.view.outcome).toEqual(receipt); expect(f.controller.view.notice).toBe('journal_unavailable');
  expect(f.controller.view.journal).toBeNull(); expect(f.server.send).toHaveBeenCalledTimes(1);
  expect(JSON.parse(f.values.get(ENTRY_JOURNAL_KEY)!).records[0].stage).toBe('prepared');
});

test.each(['conflict', 'invalid_input', 'forbidden', 'authentication_required', 'unavailable'] as const)(
  'C13/C14: known %s rejection is retained without retry or rebase', async reason => {
    const f = fixture(); await f.controller.refresh();
    f.server.send.mockResolvedValueOnce({kind: 'rejected', reason, correlationId: 'cor-safe'});
    await f.controller.submitSetup('Home', 'UTC');
    expect(f.server.send).toHaveBeenCalledTimes(1); expect(f.entropy.requestKey).toHaveBeenCalledTimes(1);
    expect(f.controller.view.outcome).toEqual({kind: 'rejected', reason, correlationId: 'cor-safe'});
    if (reason !== 'authentication_required' && reason !== 'forbidden')
      expect(f.controller.view.journal?.records[0].stage).toBe('rejected');
  },
);

test('C16: retired read is cancelled and cannot replace a newer subject', async () => {
  const f = fixture(); const old = deferred<VerifiedEntrySession | null>(); f.server.session.mockReturnValueOnce(old);
  const first = f.controller.refresh();
  f.server.session.mockImplementation(() => read({...session, context: {...context, subject: 'user-2'}}));
  await f.controller.refresh(); expect(old.cancel).toHaveBeenCalledTimes(1);
  old.resolve(session); await first;
  expect(f.controller.view.session?.context.subject).toBe('user-2');
  expect(f.server.authorization).toHaveBeenCalledTimes(1);
});

test('C16/C41: a stale sent response cannot disclose the previous user receipt or alter the new journal', async () => {
  const f = fixture(); await f.controller.refresh(); const sent = deferred<CommandResult>();
  f.server.send.mockReturnValueOnce(sent.result); const submit = f.controller.submitSetup('Home', 'UTC'); await settle();
  expect(f.server.send).toHaveBeenCalledTimes(1);
  f.server.session.mockImplementation(() => read({...session, context: {...context, subject: 'user-2'}}));
  await f.controller.refresh(); sent.resolve(receipt); await submit;
  expect(f.controller.view.session?.context.subject).toBe('user-2'); expect(f.controller.view.outcome).toBeNull();
  expect(f.controller.view.journal?.records).toEqual([]);
});

test('C13/C41: changed subject during command preflight blocks the original action', async () => {
  const f = fixture(); await f.controller.refresh();
  f.server.session.mockImplementation(() => read({...session, context: {...context, subject: 'different'}}));
  await f.controller.submitSetup('Home', 'UTC');
  expect(f.server.send).not.toHaveBeenCalled(); expect(f.controller.view.notice).toBe('context_changed');
});

test('C15: grace reads are permitted, writes are blocked and expiry clears personal presentation', async () => {
  const f = fixture(active); f.server.session.mockImplementation(() => read({...session, access: 'read_only'}));
  await f.controller.refresh(); expect(f.controller.view.household).toEqual(household);
  expect(f.controller.view.journal).toBeNull(); await f.controller.requestMembership();
  f.setNow(session.expiresAt); f.controller.tick();
  expect(f.controller.view.decision?.state).toBe('authentication_required');
  expect(f.controller.view.household).toBeNull(); expect(f.controller.view.authorization).toBeNull();
  expect(f.server.send).not.toHaveBeenCalled();
});

test('C42: native logout clears owned data, never invokes standalone logout and explains HA ownership', async () => {
  const f = fixture(); f.server.session.mockImplementation(() => read({...session, deployment: 'native'}));
  const controller = new EntryController('native', f.server, f.journal, f.clock, f.entropy);
  await controller.refresh(); f.values.set('unrelated', 'keep'); await controller.logout();
  expect(f.server.logout).not.toHaveBeenCalled(); expect(f.values.get(ENTRY_JOURNAL_KEY)).toBeUndefined();
  expect(f.values.get('unrelated')).toBe('keep'); expect(controller.view.notice).toBe('home_assistant_sign_out');
  expect(controller.view.phase).toBe('closed'); expect(controller.view.cleanup).toBe('confirmed');
});

test('C42: failed clear still logs out standalone and never restores local authority', async () => {
  const f = fixture(); await f.controller.refresh();
  f.storage.removeItem.mockImplementation(() => {throw new JournalStorageError('storage_unavailable');});
  f.server.logout.mockRejectedValueOnce(new Error('raw remote error'));
  await f.controller.logout();
  expect(f.server.logout).toHaveBeenCalledTimes(1); expect(f.controller.view.notice).toBe('logout_unconfirmed');
  expect(f.controller.view.cleanup).toBe('unconfirmed'); expect(f.controller.view.session).toBeNull();
  await f.controller.refresh(); await f.controller.logout(); await f.controller.requestMembership();
  expect(f.server.session).toHaveBeenCalledTimes(1); expect(f.server.logout).toHaveBeenCalledTimes(1);
});

test('C48: teardown cancels owned reads and fences late failures without deleting recovery evidence', async () => {
  const f = fixture(); await f.controller.refresh(); const encoded = f.values.get(ENTRY_JOURNAL_KEY);
  const blocked = deferred<Authorization>(); f.server.authorization.mockReturnValueOnce(blocked);
  const refresh = f.controller.refresh(); await settle(); f.controller.close();
  expect(blocked.cancel).toHaveBeenCalledTimes(1); blocked.reject(new EntryReadError('forbidden')); await refresh;
  expect(f.controller.view.phase).toBe('closed'); expect(f.controller.view.session).toBeNull();
  expect(f.values.get(ENTRY_JOURNAL_KEY)).toBe(encoded); expect(f.server.logout).not.toHaveBeenCalled();
});

test.each(['authentication_required', 'forbidden', 'unavailable', 'invalid_response', 'raw'] as const)(
  'C08/C21: %s read failure has a safe state and exposes no cached authority', async code => {
    const f = fixture(active); await f.controller.refresh();
    f.server.authorization.mockImplementationOnce(() => ({cancel: vi.fn(), result: Promise.reject(
      code === 'raw' ? new Error('private-details') : new EntryReadError(code))}));
    await f.controller.refresh();
    expect(f.controller.view.session).toBeNull(); expect(f.controller.view.household).toBeNull();
    expect(f.controller.view.journal).toBeNull();
    expect(f.controller.view.notice).toBe(code === 'raw' ? 'unavailable' : code);
    expect(f.controller.view.decision?.state).toBe(code === 'authentication_required' ? code : 'unavailable');
    expect(JSON.stringify(f.controller.view)).not.toContain('private-details');
  },
);

test('C02: a deployment mismatch is unavailable and cannot read or write household state', async () => {
  const f = fixture(); f.server.session.mockImplementationOnce(() => read({...session, deployment: 'native'}));
  await f.controller.refresh(); expect(f.controller.view.notice).toBe('invalid_response');
  expect(f.server.authorization).not.toHaveBeenCalled(); expect(f.values.size).toBe(0);
});

test('C09: missing identity follows the deployment authentication action and never opens the journal', async () => {
  const f = fixture(); f.server.session.mockReturnValueOnce(read(null));
  await f.controller.refresh(); expect(f.controller.view.decision?.action).toBe('sign_in');
  expect(f.server.authorization).not.toHaveBeenCalled(); expect(f.values.size).toBe(0);
});

test('C08: preview without household APIs remains unavailable and does not probe missing APIs', async () => {
  const f = fixture(); f.server.session.mockImplementation(() => read({...session, householdApiAvailable: false}));
  await f.controller.refresh(); expect(f.controller.view.decision?.state).toBe('unavailable');
  expect(f.controller.view.journal).toBeNull(); expect(f.server.authorization).not.toHaveBeenCalled();
});

test('C15: expiry before authorization or while household data is arriving exposes no personal state', async () => {
  const f = fixture(active); f.setNow(session.expiresAt); await f.controller.refresh();
  expect(f.server.authorization).not.toHaveBeenCalled(); expect(f.controller.view.session).toBeNull();
  f.setNow(1000); const data = deferred<typeof household>(); f.server.household.mockReturnValueOnce(data);
  const refresh = f.controller.refresh(); await settle(); f.setNow(session.expiresAt); data.resolve(household); await refresh;
  expect(f.controller.view.household).toBeNull(); expect(f.controller.view.decision?.action).toBe('sign_in');
});

test('C40: active membership without actual read permission never requests household facts', async () => {
  const f = fixture({...active, permissions: ['preferences.read']}); await f.controller.refresh();
  expect(f.server.household).not.toHaveBeenCalled(); expect(f.controller.view.household).toBeNull();
  expect(f.controller.view.authorization?.permissions).toEqual(['preferences.read']);
  expect(Object.isFrozen(f.controller.view.authorization?.permissions)).toBe(true);
  expect(Object.isFrozen(f.controller.view.session?.context)).toBe(true);
});

test.each(['suspended', 'archived'] as const)('C13: %s linkage hides local work and blocks recovery', async state => {
  const f = fixture(eligible); await f.controller.refresh();
  f.server.send.mockResolvedValueOnce({kind: 'uncertain'}); await f.controller.requestMembership();
  f.server.authorization.mockImplementation(() => read({...pending, state}));
  await f.controller.refresh(); await f.controller.recover('key-original');
  expect(f.controller.view.journal).toBeNull(); expect(f.controller.view.outcome).toBeNull();
  expect(f.server.send).toHaveBeenCalledTimes(1); expect(f.values.get(ENTRY_JOURNAL_KEY)).toContain('key-original');
});

test('C13: new authority denial during preflight cannot use the earlier setup flag', async () => {
  const f = fixture(); await f.controller.refresh();
  f.server.authorization.mockImplementation(() => read({...setup, setupAllowed: false}));
  await f.controller.submitSetup('Home', 'UTC');
  expect(f.server.send).not.toHaveBeenCalled(); expect(f.controller.view.notice).toBe('action_not_allowed');
});

test.each(['missing', 'grace', 'storage', 'preview'] as const)(
  'C13: %s preflight loss cannot send the command', async loss => {
    const f = fixture(); await f.controller.refresh();
    if (loss === 'missing') f.server.session.mockReturnValueOnce(read(null));
    if (loss === 'grace') f.server.session.mockReturnValueOnce(read({...session, access: 'read_only'}));
    if (loss === 'preview') f.server.session.mockReturnValueOnce(read({...session, householdApiAvailable: false}));
    if (loss === 'storage') f.storage.setItem.mockImplementationOnce(() => {throw new Error('storage lost');});
    await f.controller.submitSetup('Home', 'UTC'); expect(f.server.send).not.toHaveBeenCalled();
    expect(f.entropy.requestKey).not.toHaveBeenCalled();
  },
);

test.each(['prepared', 'uncertain'] as const)('C06/C11: existing %s work blocks a new key until deliberate recovery', async stage => {
  const f = fixture(); await f.controller.refresh();
  f.journal.prepare('prior', {action: 'setup', payload: {name: 'Original', time_zone: 'UTC',
    expected_revision: 0, mapping_mode: 'all_ha_administrators'}}, 1000);
  if (stage === 'uncertain') f.journal.record('prior', {stage, operationId: null}, 1000);
  await f.controller.refresh(); await f.controller.submitSetup('Different', 'UTC');
  expect(f.controller.view.notice).toBe('previous_request_unresolved');
  expect(f.entropy.requestKey).not.toHaveBeenCalled(); expect(f.server.send).not.toHaveBeenCalled();
});

test('C06/C07: unresolved requests cannot be dismissed; resolved requests can be explicitly removed', async () => {
  const f = fixture(eligible); await f.controller.refresh();
  f.server.send.mockResolvedValueOnce({kind: 'uncertain'}); await f.controller.requestMembership();
  await f.controller.dismiss('key-original'); expect(f.controller.view.notice).toBe('journal_unavailable');
  expect(f.values.get(ENTRY_JOURNAL_KEY)).toContain('key-original');
  await f.controller.refresh(); await f.controller.recover('key-original'); await f.controller.dismiss('key-original');
  expect(f.controller.view.journal?.records).toEqual([]); expect(f.server.send).toHaveBeenCalledTimes(2);
});

test('C17: missing and expired original requests are never recreated', async () => {
  const f = fixture(eligible); await f.controller.refresh(); await f.controller.recover('absent');
  expect(f.controller.view.notice).toBe('request_unavailable');
  f.server.send.mockResolvedValueOnce({kind: 'uncertain'}); await f.controller.requestMembership();
  f.server.session.mockImplementation(() => {
    f.setNow(3_601_000); return read({...session, serverTime: 3_601_000, expiresAt: 4_000_000});
  });
  await f.controller.recover('key-original'); expect(f.controller.view.notice).toBe('request_unavailable');
  expect(f.server.send).toHaveBeenCalledTimes(1); expect(f.entropy.requestKey).toHaveBeenCalledTimes(1);
});

test.each(['payload', 'creation', 'operation'] as const)('C07: changed original %s during fresh reads is never replayed', async change => {
  const f = fixture(); await f.controller.refresh();
  f.server.send.mockResolvedValueOnce({kind: 'uncertain'}); await f.controller.submitSetup('Original', 'UTC');
  f.server.authorization.mockImplementationOnce(() => {
    const stored = JSON.parse(f.values.get(ENTRY_JOURNAL_KEY)!);
    if (change === 'payload') stored.records[0].payload.name = 'Changed';
    if (change === 'creation') {stored.records[0].createdAt = 999; stored.records[0].expiresAt = 3_600_999;}
    if (change === 'operation') {stored.records[0].operationId = 'other-op'; stored.records[0].stage = 'committed';}
    f.values.set(ENTRY_JOURNAL_KEY, JSON.stringify(stored)); return read(setup);
  });
  await f.controller.recover('key-original'); expect(f.controller.view.notice).toBe('request_changed');
  expect(f.server.send).toHaveBeenCalledTimes(1);
});

test.each(['unconfigured_allowed', 'unconfigured_denied', 'active_allowed', 'active_denied', 'pending'] as const)(
  'C13/C17: setup recovery respects current %s authority, separate from new-write eligibility', async permission => {
    const f = fixture(); await f.controller.refresh();
    f.server.send.mockResolvedValueOnce({kind: 'uncertain'}); await f.controller.submitSetup('Home', 'UTC');
    const authorization = permission.startsWith('unconfigured') ? {...setup, setupAllowed: permission.endsWith('allowed')}
      : permission === 'pending' ? pending : {...active, permissions: permission.endsWith('allowed') ? ['household.manage'] : []};
    f.server.authorization.mockImplementation(() => read(authorization));
    await f.controller.recover('key-original');
    expect(f.server.send).toHaveBeenCalledTimes(permission.endsWith('allowed') ? 2 : 1);
  },
);

test('C10: enrollment recovery is blocked if the household is now unconfigured', async () => {
  const f = fixture(eligible); await f.controller.refresh();
  f.server.send.mockResolvedValueOnce({kind: 'uncertain'}); await f.controller.requestMembership();
  f.server.authorization.mockImplementation(() => read(setup)); await f.controller.recover('key-original');
  expect(f.controller.view.notice).toBe('action_not_allowed'); expect(f.server.send).toHaveBeenCalledTimes(1);
});

test('C14: a known rejected original is not replayed by the recovery action', async () => {
  const f = fixture(); await f.controller.refresh();
  f.server.send.mockResolvedValueOnce({kind: 'rejected', reason: 'conflict', correlationId: null});
  await f.controller.submitSetup('Home', 'UTC'); await f.controller.recover('key-original');
  expect(f.controller.view.notice).toBe('action_not_allowed'); expect(f.server.send).toHaveBeenCalledTimes(1);
});

test('C44: historical recovery preserves original operation identity and its absent effect', async () => {
  const f = fixture(); await f.controller.refresh(); await f.controller.submitSetup('Home', 'UTC');
  f.server.send.mockResolvedValueOnce({...receipt, stage: 'historical', archivedBy: 'restore-1'});
  await f.controller.recover('key-original');
  expect(f.controller.view.outcome).toMatchObject({stage: 'historical', archivedBy: 'restore-1', operationId: 'op-original'});
  expect(f.controller.view.journal?.records[0]).toMatchObject({stage: 'historical', operationId: 'op-original'});
  expect(f.entropy.requestKey).toHaveBeenCalledTimes(1);
});

test('C07: incompatible receipt identity is rejected without overwriting the original', async () => {
  const f = fixture(); await f.controller.refresh(); await f.controller.submitSetup('Home', 'UTC');
  f.server.send.mockResolvedValueOnce({...receipt, operationId: 'wrong-operation'});
  await f.controller.recover('key-original');
  expect(f.controller.view.notice).toBe('invalid_response'); expect(f.controller.view.outcome).toEqual(receipt);
  expect(f.controller.view.journal?.records[0].operationId).toBe('op-original');
});

test.each(['uncertain', 'rejected'] as const)('C07: %s checking cannot erase a known operation', async kind => {
  const f = fixture(); await f.controller.refresh(); await f.controller.submitSetup('Home', 'UTC');
  f.server.send.mockResolvedValueOnce(kind === 'uncertain' ? {kind} : {kind, reason: 'unavailable', correlationId: null});
  await f.controller.recover('key-original');
  expect(f.controller.view.notice).toBe('check_unconfirmed');
  expect(f.controller.view.journal?.records[0]).toMatchObject({stage: 'committed', operationId: 'op-original'});
});

test('C06: expiry after preparation blocks the send without silently replacing the prepared request', async () => {
  const f = fixture(); await f.controller.refresh(); const prepare = f.journal.prepare.bind(f.journal);
  vi.spyOn(f.journal, 'prepare').mockImplementation((...args) => {const result = prepare(...args); f.setNow(session.expiresAt); return result;});
  await f.controller.submitSetup('Home', 'UTC');
  expect(f.server.send).not.toHaveBeenCalled(); expect(f.controller.view.session).toBeNull();
  expect(f.values.get(ENTRY_JOURNAL_KEY)).toContain('key-original');
});

test('C15: a failed semantic clock clears local access and never renews the deadline', async () => {
  const f = fixture(active); await f.controller.refresh(); f.clock.now.mockImplementation(() => {throw new Error('clock unavailable');});
  f.controller.tick(); expect(f.controller.view.decision?.state).toBe('authentication_required');
  expect(f.controller.view.household).toBeNull(); expect(f.controller.view.journal).toBeNull();
});

test('C24: failed entropy has no effect and retains prior journal content', async () => {
  const f = fixture(); await f.controller.refresh();
  f.entropy.requestKey.mockImplementation(() => {throw new Error('entropy unavailable');});
  await f.controller.submitSetup('Home', 'UTC');
  expect(f.controller.view.notice).toBe('journal_unavailable'); expect(f.server.send).not.toHaveBeenCalled();
  expect(JSON.parse(f.values.get(ENTRY_JOURNAL_KEY)!).records).toEqual([]);
});

test('C48: cancellation exceptions cannot revive an older read', async () => {
  const f = fixture(); const old = deferred<VerifiedEntrySession | null>();
  old.cancel.mockImplementation(() => {throw new Error('cancellation failure');});
  f.server.session.mockReturnValueOnce(old); const first = f.controller.refresh(); f.controller.close(); old.resolve(session); await first;
  expect(f.controller.view.phase).toBe('closed'); expect(f.server.authorization).not.toHaveBeenCalled();
});

test('C16: retirement between completed preflight and its continuation prevents a send', async () => {
  const f = fixture(); await f.controller.refresh(); const open = f.journal.open.bind(f.journal);
  vi.spyOn(f.journal, 'open').mockImplementationOnce((...args) => {
    const result = open(...args); queueMicrotask(() => f.controller.close()); return result;
  });
  await f.controller.submitSetup('Home', 'UTC'); expect(f.controller.view.phase).toBe('closed');
  expect(f.server.send).not.toHaveBeenCalled();
});

test('C48: teardown during a failing preparation is not overwritten by its failure handler', async () => {
  const f = fixture(); await f.controller.refresh();
  f.entropy.requestKey.mockImplementation(() => {f.controller.close(); throw new Error('retired entropy');});
  await f.controller.submitSetup('Home', 'UTC');
  expect(f.controller.view.phase).toBe('closed'); expect(f.controller.view.notice).toBeNull();
  expect(f.server.send).not.toHaveBeenCalled();
});

test.each([true, false, null])('C42: standalone logout reports actual upstream revocation %j', async upstreamRevoked => {
  const f = fixture(); await f.controller.refresh(); f.server.logout.mockResolvedValueOnce({upstreamRevoked});
  await f.controller.logout(); expect(f.controller.view.notice).toBe(upstreamRevoked === true ? 'signed_out' : 'logout_unconfirmed');
  expect(f.controller.view.cleanup).toBe('confirmed'); await f.controller.submitSetup('Home', 'UTC');
  expect(f.server.send).not.toHaveBeenCalled();
});

test('C48: a late logout callback cannot alter a subsequently retired view', async () => {
  const f = fixture(); const result = deferred<{upstreamRevoked: boolean | null}>();
  f.server.logout.mockReturnValueOnce(result.result); const logout = f.controller.logout();
  f.controller.close(); result.resolve({upstreamRevoked: true}); await logout;
  expect(f.controller.view.notice).toBeNull(); expect(f.controller.view.cleanup).toBeNull();
});

test('C41: a new verified installation/channel/subject cannot see the preceding completed result', async () => {
  const f = fixture(); await f.controller.refresh(); await f.controller.submitSetup('Private home', 'UTC');
  expect(f.controller.view.outcome).toEqual(receipt);
  f.server.session.mockReturnValueOnce(read({...session, context: {...context, channel: 'stable', subject: 'other-user'}}));
  await f.controller.refresh();
  expect(f.controller.view.outcome).toBeNull(); expect(f.controller.view.journal?.records).toEqual([]);
  expect(f.values.get(ENTRY_JOURNAL_KEY)).not.toContain('Private home');
});

test('C12/C46: reload after a lost committed response checks the same semantic-server effect once', async () => {
  const f = fixture(eligible), processed = new Map<string, EntryReceipt>(); let effects = 0, loseFirst = true;
  f.server.send.mockImplementation(async request => {
    if (!processed.has(request.key)) {effects++; processed.set(request.key, receipt);}
    if (loseFirst) {loseFirst = false; f.server.authorization.mockImplementation(() => read(pending)); throw new Error('lost response');}
    return processed.get(request.key)!;
  });
  await f.controller.refresh(); await f.controller.requestMembership(); f.controller.close();
  const reloaded = new EntryController('standalone', f.server, new SessionJournal(f.storage), f.clock, f.entropy);
  await reloaded.refresh(); expect(f.server.send).toHaveBeenCalledTimes(1);
  await reloaded.recover('key-original');
  expect(effects).toBe(1); expect(f.server.send).toHaveBeenCalledTimes(2);
  expect(f.server.send.mock.calls[1]).toEqual(f.server.send.mock.calls[0]);
  expect(reloaded.view.outcome).toEqual(receipt);
});

test('C15: receipt arriving after session expiry is retained without exposing expired authority during refresh', async () => {
  const f = fixture(); await f.controller.refresh(); const blocked = deferred<VerifiedEntrySession | null>();
  f.server.send.mockImplementation(async () => {f.setNow(session.expiresAt); f.server.session.mockReturnValueOnce(blocked); return receipt;});
  const submit = f.controller.submitSetup('Home', 'UTC'); await settle(); const observed = f.controller.view;
  blocked.resolve(null); await submit;
  expect(observed.session).toBeNull(); expect(observed.outcome).toBeNull();
  expect(observed.decision?.state).toBe('authentication_required');
  expect(JSON.parse(f.values.get(ENTRY_JOURNAL_KEY)!).records[0]).toMatchObject({stage: 'committed', operationId: 'op-original'});
});

test.each(['tick', 'refresh'] as const)('C06: %s cannot retain a completed result beyond its original journal deadline', async action => {
  const f = fixture(); f.server.session.mockImplementation(() => read({...session, expiresAt: 10_000_000}));
  await f.controller.refresh(); await f.controller.submitSetup('Home', 'UTC');
  expect(f.controller.view.outcome).toEqual(receipt); f.setNow(3_601_000);
  if (action === 'tick') f.controller.tick(); else await f.controller.refresh();
  expect(f.controller.view.outcome).toBeNull(); expect(f.controller.view.journal?.records).toEqual([]);
  expect(f.server.send).toHaveBeenCalledTimes(1);
});
