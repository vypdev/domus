import {TaskController} from '../src/application/task-controller';
import {TaskSessionJournal} from '../src/adapters/task-journal';
import type {TaskServer} from '../src/application/task-ports';
import type {TaskDetail, TaskReceipt} from '../src/domain/tasks';
import {expect, test, vi} from 'vitest';
import {HouseholdController} from '../src/application/household-controller';
import {EntryController} from '../src/application/entry-controller';
import {AdministrationController} from '../src/application/administration-controller';
import {EntryReadError} from '../src/application/ports';
import type {EntryRead, VerifiedEntrySession, EntryServer} from '../src/application/ports';
import type {AdministrationAccess, AdministrationReceipt} from '../src/domain/administration-views';
import type {AdministrationRequest, AdministrationOriginal, AdministrationCommandResult} from '../src/application/administration-ports';
import type {Authorization} from '../src/domain/entry';
import {revisionValue} from '../src/domain/administration';
import {administrationCommand} from '../src/domain/administration-commands';
import {SessionJournal, ENTRY_JOURNAL_KEY} from '../src/adapters/session-journal';
import {AdministrationSessionJournal, ADMINISTRATION_JOURNAL_KEY} from '../src/adapters/administration-journal';

function read<T>(value: T): EntryRead<T> {return {result: Promise.resolve(value), cancel: vi.fn()};}
function deferred<T>() {
  let resolve!: (value: T) => void, reject!: (error: unknown) => void;
  const result = new Promise<T>((yes, no) => {resolve = yes; reject = no;});
  return {result, resolve, reject, cancel: vi.fn()};
}
async function settle() {for (let n = 0; n < 120; n++) await Promise.resolve();}
const context = {installationId: '01234567-89ab-cdef-0123-456789abcdef', channel: 'edge' as const, subject: 'a'.repeat(32)};
const session: VerifiedEntrySession = {context, deployment: 'standalone', access: 'full', serverTime: 1000,
  expiresAt: 10_000, householdApiAvailable: true};
const home = {householdId: 'home', name: 'Home', timeZone: 'UTC', revision: revisionValue('7')};
const member = {memberId: 'member-own', haUserId: context.subject, role: 'adult' as const, status: 'active' as const,
  exceptions: [], revision: revisionValue('3')};
const access: AdministrationAccess = {state: 'active', setupAllowed: false, enrollmentAllowed: false,
  member, effectiveRole: 'administrator', policyRevision: revisionValue('5'),
  permissions: ['household.read', 'household.manage', 'members.read', 'members.manage', 'policy.manage',
    'preferences.read', 'preferences.write', 'operations.read']};
const own = {memberId: member.memberId, locale: 'es' as const, routine_participation_summaries: true,
  revision: revisionValue('13'), notificationDelivery: 'unavailable' as const};
const command = administrationCommand({action: 'member.preferences.update', payload: {expected_revision: '13',
  locale: 'en', routine_participation_summaries: false}});
const receipt: AdministrationReceipt = {kind: 'receipt', stage: 'committed', action: command.action,
  operationId: 'op-original', createdAt: 1000, archivedBy: null, eventDelivery: null,
  notificationDelivery: 'unavailable', result: {...own, locale: 'en', revision: revisionValue('14')}};
const basic = (value: AdministrationAccess): Authorization => ({state: value.state, setupAllowed: value.setupAllowed,
  enrollmentAllowed: value.enrollmentAllowed, permissions: value.permissions});
function fixture(mode: 'native' | 'standalone' = 'standalone') {
  let now = 1000;
  const proof = {...session, deployment: mode};
  const values = new Map<string, string>();
  const storage = {getItem: vi.fn((key: string) => values.get(key) ?? null),
    setItem: vi.fn((key: string, value: string) => {values.set(key, value);}),
    removeItem: vi.fn((key: string) => {values.delete(key);})};
  const clock = {anchor: vi.fn(), now: vi.fn(() => now)};
  let nextKey = 0;
  const entropy = {requestKey: vi.fn(() => 'request-' + (++nextKey))};
  const identity = {session: vi.fn(() => read<VerifiedEntrySession | null>(proof))};
  const entryServer = {session: vi.fn(() => read<VerifiedEntrySession | null>(proof)),
    authorization: vi.fn(() => read(basic(access))), household: vi.fn(() => read(home)),
    operation: vi.fn(() => {throw new Error('No entry operation requested.');}),
    send: vi.fn((_value: Parameters<EntryServer['send']>[0]): ReturnType<EntryServer['send']> => Promise.resolve({kind: 'uncertain'})),
    logout: vi.fn(async () => ({upstreamRevoked: true}))};
  const server = {
    capabilities: vi.fn(() => read({contractVersion: 2 as const, householdId: 'home', actions: [command.action]})),
    authorization: vi.fn(() => read(access)), household: vi.fn(() => read(home)),
    policy: vi.fn(() => read({householdId: 'home', revision: revisionValue('5'), mappingMode: 'all_ha_administrators' as const,
      targetHAUserId: null, adjustments: []})),
    roster: vi.fn(() => read({directoryState: 'available' as const, members: [{member,
      presentation: {memberId: member.memberId, alias: null, revision: revisionValue('11')},
      metadata: {state: 'available' as const, name: 'Current member', avatarState: 'unavailable' as const}}]})),
    directory: vi.fn(() => read({state: 'denied' as const, profiles: []})), preferences: vi.fn(() => read(own)),
    presentation: vi.fn(() => read({memberId: member.memberId, alias: null, revision: revisionValue('11')})),
    send: vi.fn((_request: AdministrationRequest): Promise<AdministrationCommandResult> => Promise.resolve(receipt)),
    original: vi.fn((_request: AdministrationOriginal) => read(receipt)),
    operation: vi.fn((_request: AdministrationOriginal) => read(receipt)),
  };
  const entries: EntryController[] = [], administrators: AdministrationController[] = [];
  const entry = new EntryController(mode, entryServer, new SessionJournal(storage), clock, entropy); entries.push(entry);
  const factory = vi.fn(() => {
    const next = new AdministrationController(mode, identity, server, new AdministrationSessionJournal(storage), clock, entropy);
    administrators.push(next); return next;
  });
  const controller = new HouseholdController(entry, factory);
  return {controller, entry, entryServer, identity, server, storage, values, clock, entropy, factory, administrators,
    mode, proof, setNow: (value: number) => {now = value;},
    reload: () => {
      const nextEntry = new EntryController(mode, entryServer, new SessionJournal(storage), clock, entropy); entries.push(nextEntry);
      return new HouseholdController(nextEntry, factory);
    }};
}

test.each(['native', 'standalone'] as const)('HADB-01/C01: %s composes a matched current view without writes and reuses same-context evidence', async mode => {
  const f = fixture(mode); expect(f.controller.view.phase).toBe('idle'); expect(f.controller.administration).toBeNull();
  const opening = f.controller.refresh(); expect(f.controller.view.busy).toBe(true); expect(f.controller.administration).toBeNull();
  await opening;
  expect(f.controller.view.decision?.state).toBe('active'); expect(f.controller.administration?.preferences).toEqual(own);
  expect(f.factory).toHaveBeenCalledOnce(); expect(Object.isFrozen(f.controller.view)).toBe(true);
  expect(f.server.send).not.toHaveBeenCalled(); expect(f.entryServer.send).not.toHaveBeenCalled();
  await f.controller.refresh(); expect(f.factory).toHaveBeenCalledOnce(); f.controller.close();
});
test.each(['unconfigured', 'not_enrolled', 'pending', 'suspended', 'archived'] as const)(
  'HADB-01: %s entry never opens private administration', async state => {
    const f = fixture(); f.entryServer.authorization.mockReturnValue(read({...basic(access), state, permissions: []}));
    await f.controller.refresh(); expect(f.factory).not.toHaveBeenCalled(); expect(f.controller.administration).toBeNull();
    expect(f.controller.view.decision?.state).toBe(state); f.controller.close();
  },
);
test('HADB-01: missing session, unavailable API or failed entry does not probe private administration', async () => {
  const f = fixture(); f.entryServer.session.mockReturnValueOnce(read(null));
  await f.controller.refresh(); expect(f.factory).not.toHaveBeenCalled();
  f.entryServer.session.mockReturnValueOnce(read({...f.proof, householdApiAvailable: false}));
  await f.controller.refresh(); expect(f.factory).not.toHaveBeenCalled();
  f.entryServer.session.mockImplementationOnce(() => ({cancel: vi.fn(), result: Promise.reject(new EntryReadError('forbidden'))}));
  await f.controller.refresh(); expect(f.factory).not.toHaveBeenCalled(); expect(f.controller.administration).toBeNull();
});
test.each(['installationId', 'channel', 'subject'] as const)('HADB-01/C02: persistent %s drift is hidden after one reconciliation', async field => {
  const f = fixture(), changed = {...context, [field]: field === 'channel' ? 'stable' : field === 'subject' ? 'b'.repeat(32)
    : '11234567-89ab-cdef-0123-456789abcdef'};
  f.identity.session.mockReturnValue(read({...f.proof, context: changed}));
  await f.controller.refresh();
  expect(f.controller.administration).toBeNull(); expect(f.controller.view.notice).toBe('context_changed');
  expect(f.entryServer.session).toHaveBeenCalledTimes(2); expect(f.identity.session).toHaveBeenCalledOnce();
  expect(f.administrators[0].view.phase).toBe('closed'); expect(f.server.send).not.toHaveBeenCalled();
});
test('HADB-01/C02: a new context which reconciles once can publish only that context', async () => {
  const f = fixture(), changed = {...context, installationId: '11234567-89ab-cdef-0123-456789abcdef'};
  f.entryServer.session.mockReturnValueOnce(read(f.proof)).mockReturnValue(read({...f.proof, context: changed}));
  f.identity.session.mockReturnValue(read({...f.proof, context: changed}));
  await f.controller.refresh(); expect(f.controller.view.session?.context).toEqual(changed);
  expect(f.controller.administration?.session?.context).toEqual(changed);
  expect(f.entryServer.session).toHaveBeenCalledTimes(2);
  await f.controller.refresh(); expect(f.factory).toHaveBeenCalledOnce();
});
test('HADB-01/C03: drifted current grants are reconciled without exposing previously collected private preferences', async () => {
  const f = fixture(), current = {...access, permissions: ['household.read']};
  f.server.authorization.mockReturnValueOnce(read(access)).mockReturnValue(read(current));
  f.entryServer.authorization.mockReturnValueOnce(read(basic(access))).mockReturnValue(read(basic(current)));
  await f.controller.refresh();
  expect(f.controller.administration?.notice).toBe('access_changed');
  expect(f.controller.administration?.preferences).toBeNull(); expect(f.controller.view.authorization?.permissions).toEqual(current.permissions);
  expect(f.entryServer.session).toHaveBeenCalledTimes(2); expect(f.server.send).not.toHaveBeenCalled();
});
test('HADB-01/C08: grant mismatch that persists through reconciliation remains hidden', async () => {
  const f = fixture(); f.server.authorization.mockReturnValue(read({...access, permissions: ['household.read']}));
  await f.controller.refresh(); expect(f.controller.administration).toBeNull();
  expect(f.controller.view.notice).toBe('context_changed'); expect(f.entryServer.session).toHaveBeenCalledTimes(2);
});
test('HADB-01: equal grant sets in a different order are not treated as drift', async () => {
  const f = fixture(); f.entryServer.authorization.mockReturnValue(read({...basic(access), permissions: [...access.permissions].reverse()}));
  await f.controller.refresh(); expect(f.controller.administration?.preferences).toEqual(own);
  expect(f.entryServer.session).toHaveBeenCalledOnce();
});
test('HADB-01: inconsistent household facts cannot be combined even with matching account grants', async () => {
  const f = fixture(); f.entryServer.household.mockReturnValue(read({...home, householdId: 'other-home'}));
  await f.controller.refresh(); expect(f.controller.administration).toBeNull();
  expect(f.controller.view.notice).toBe('context_changed'); expect(f.entryServer.session).toHaveBeenCalledTimes(2);
});
test('HADB-01: compatible failure view contains no private facts and preserves the current entry session', async () => {
  const f = fixture(); f.server.capabilities.mockImplementation(() => ({cancel: vi.fn(), result: Promise.reject(new EntryReadError('unavailable'))}));
  await f.controller.refresh(); expect(f.controller.administration?.notice).toBe('unavailable');
  expect(f.controller.administration?.session).toBeNull(); expect(f.controller.administration?.preferences).toBeNull();
  expect(f.controller.view.session).toEqual(f.proof);
});
test('HADB-01: administration authentication failure retires both views without renewing entry proof', async () => {
  const f = fixture(); f.identity.session.mockReturnValue(read(null));
  await f.controller.refresh(); expect(f.controller.administration).toBeNull();
  expect(f.controller.view.decision?.state).toBe('authentication_required'); expect(f.controller.view.session).toBeNull();
  expect(f.entryServer.session).toHaveBeenCalledOnce();
});
test('HADB-01/C04: the earlier entry lease expires during administration collection without automatic reverification', async () => {
  const f = fixture(), waiting = deferred<typeof own>(); f.server.preferences.mockReturnValueOnce(waiting);
  f.identity.session.mockReturnValue(read({...f.proof, expiresAt: 20_000}));
  const opening = f.controller.refresh(); await settle(); expect(f.controller.administration).toBeNull();
  f.setNow(10_000); waiting.resolve(own); await opening;
  expect(f.controller.view.session).toBeNull(); expect(f.controller.administration).toBeNull();
  expect(f.controller.view.decision?.state).toBe('authentication_required'); expect(f.entryServer.session).toHaveBeenCalledOnce();
});
test('HADB-01/C04: administration lease expiry retires the entry view as well', async () => {
  const f = fixture(); f.identity.session.mockReturnValue(read({...f.proof, expiresAt: 2000}));
  await f.controller.refresh(); f.setNow(2000); f.controller.tick();
  expect(f.controller.view.session).toBeNull(); expect(f.controller.view.decision?.state).toBe('authentication_required');
  expect(f.controller.administration).toBeNull(); expect(f.entryServer.session).toHaveBeenCalledOnce();
});
test('HADB-02/C09: an optional entry household failure leaves original GET recovery independently available', async () => {
  const f = fixture(); await f.controller.refresh(); f.server.send.mockResolvedValueOnce({kind: 'uncertain'});
  await f.controller.submitAdministration(command); expect(f.controller.administration?.outcome?.kind).toBe('uncertain');
  const original = f.controller.administration!.journal!.records[0];
  f.entryServer.household.mockImplementation(() => ({cancel: vi.fn(), result: Promise.reject(new EntryReadError('unavailable'))}));
  f.server.household.mockImplementation(() => ({cancel: vi.fn(), result: Promise.reject(new EntryReadError('unavailable'))}));
  await f.controller.refresh(); await f.controller.recoverAdministration(original.key);
  expect(f.server.original).toHaveBeenCalledOnce(); expect(f.server.send).toHaveBeenCalledOnce();
  expect(f.controller.administration?.outcome?.kind).toBe('receipt'); expect(f.controller.view.household).toBeNull();
});
test('HADB-02/C10/C11: reload and explicit original GET need no aggregate-read grant and never resend', async () => {
  const f = fixture(); await f.controller.refresh(); f.server.send.mockResolvedValueOnce({kind: 'uncertain'});
  await f.controller.submitAdministration(command); const record = f.controller.administration!.journal!.records[0];
  f.controller.close(); const current = {...access, permissions: ['preferences.read', 'preferences.write', 'operations.read']};
  f.server.authorization.mockReturnValue(read(current)); f.entryServer.authorization.mockReturnValue(read(basic(current)));
  const restored = f.reload(); await restored.refresh(); expect(f.server.original).not.toHaveBeenCalled();
  await restored.recoverAdministration(record.key);
  expect(f.server.original).toHaveBeenCalledExactlyOnceWith({key: record.key, command, operationId: null}, context);
  expect(f.server.send).toHaveBeenCalledOnce(); expect(restored.administration?.outcome?.kind).toBe('receipt');
  await restored.dismissAdministration(record.key); expect(restored.administration?.journal?.records).toEqual([]);
  restored.close();
});
test('HADB-02: same-context refresh retains the actual receipt rather than recreating the administration controller', async () => {
  const f = fixture(); await f.controller.refresh(); await f.controller.submitAdministration(command);
  expect(f.controller.administration?.outcome).toEqual(receipt); await f.controller.refresh();
  expect(f.controller.administration?.outcome).toEqual(receipt); expect(f.factory).toHaveBeenCalledOnce();
});
test('HADB-01/C05: logout and competing intents during administration preflight/send preserve the original command', async () => {
  const f = fixture(); await f.controller.refresh(); const proof = deferred<VerifiedEntrySession | null>();
  const waiting = deferred<AdministrationCommandResult>(); f.identity.session.mockReturnValueOnce(proof); f.server.send.mockReturnValueOnce(waiting.result);
  const work = f.controller.submitAdministration(command); expect(f.controller.view.busy).toBe(true);
  await f.controller.logout(); await f.controller.submitSetup('Home', 'UTC'); await f.controller.requestMembership();
  await f.controller.refresh(); await f.controller.submitAdministration(command);
  expect(f.entryServer.logout).not.toHaveBeenCalled(); expect(f.entryServer.send).not.toHaveBeenCalled();
  proof.resolve(f.proof); await settle(); expect(f.server.send).toHaveBeenCalledOnce();
  const raw = f.values.get(ADMINISTRATION_JOURNAL_KEY); await f.controller.logout();
  expect(f.values.get(ADMINISTRATION_JOURNAL_KEY)).toBe(raw); expect(f.controller.view.busy).toBe(true);
  waiting.resolve(receipt); await work; expect(f.controller.view.busy).toBe(false);
  expect(f.controller.administration?.outcome).toEqual(receipt); await f.controller.logout();
  expect(f.controller.view.phase).toBe('closed'); expect(f.controller.administration).toBeNull();
  expect(f.entryServer.logout).toHaveBeenCalledOnce(); expect(f.values.has(ADMINISTRATION_JOURNAL_KEY)).toBe(true);
});
test('HADB-01/C05: an entry command also blocks administration and stale logout until its original completes', async () => {
  const f = fixture(), eligible: Authorization = {...basic(access), state: 'not_enrolled', permissions: [], enrollmentAllowed: true};
  f.entryServer.authorization.mockReturnValue(read(eligible)); await f.controller.refresh();
  const waiting = deferred<Awaited<ReturnType<EntryServer['send']>>>(); f.entryServer.send.mockReturnValueOnce(waiting.result);
  const work = f.controller.requestMembership(); await settle();
  await f.controller.logout(); await f.controller.submitAdministration(command); await f.controller.recoverAdministration('no-key');
  expect(f.entryServer.logout).not.toHaveBeenCalled(); expect(f.server.send).not.toHaveBeenCalled();
  expect(f.values.has(ENTRY_JOURNAL_KEY)).toBe(true); waiting.resolve({kind: 'uncertain'}); await work;
  expect(f.controller.view.outcome).toEqual({kind: 'uncertain'}); expect(f.entryServer.send).toHaveBeenCalledOnce();
});
test('HADB-01/C06: closing a command and opening a new lifetime retains its original without accepting the late reply', async () => {
  const f = fixture(); await f.controller.refresh(); const waiting = deferred<AdministrationCommandResult>();
  f.server.send.mockReturnValueOnce(waiting.result); const work = f.controller.submitAdministration(command); await settle();
  expect(f.server.send).toHaveBeenCalledOnce(); f.controller.close();
  const restored = f.reload(); await restored.refresh(); const before = restored.administration;
  waiting.resolve(receipt); await work;
  expect(f.controller.administration).toBeNull(); expect(f.controller.view.phase).toBe('closed');
  expect(restored.administration).toEqual(before); expect(restored.administration?.journal?.records[0].stage).toBe('prepared');
  expect(f.server.original).not.toHaveBeenCalled(); restored.close();
});
test('HADB-01/C07: close cancels pending entry reads and fences late completion', async () => {
  const f = fixture(), waiting = deferred<VerifiedEntrySession | null>(); f.entryServer.session.mockReturnValueOnce(waiting);
  const work = f.controller.refresh(); f.controller.close(); f.controller.close(); waiting.resolve(f.proof); await work;
  expect(waiting.cancel).toHaveBeenCalledOnce(); expect(f.factory).not.toHaveBeenCalled();
  expect(f.controller.view.phase).toBe('closed'); expect(f.controller.administration).toBeNull();
  await f.controller.refresh(); await f.controller.submitSetup('Home', 'UTC'); await f.controller.requestMembership();
  await f.controller.recover('key'); await f.controller.dismiss('key'); await f.controller.logout();
  await f.controller.submitAdministration(command); await f.controller.recoverAdministration('key'); await f.controller.dismissAdministration('key');
  f.controller.tick(); expect(f.entryServer.session).toHaveBeenCalledOnce();
});
test('HADB-01/C07: closing administration collection cancels its private read and blocks late publication', async () => {
  const f = fixture(), waiting = deferred<typeof own>(); f.server.preferences.mockReturnValueOnce(waiting);
  const work = f.controller.refresh(); await settle(); f.controller.close(); waiting.resolve(own); await work;
  expect(waiting.cancel).toHaveBeenCalledOnce(); expect(f.controller.administration).toBeNull();
  expect(f.controller.view.session).toBeNull();
});
test('HADB-02/C14: read-only original recovery remains possible while mutations are blocked', async () => {
  const f = fixture(); await f.controller.refresh(); f.server.send.mockResolvedValueOnce({kind: 'uncertain'});
  await f.controller.submitAdministration(command); const record = f.controller.administration!.journal!.records[0];
  f.entryServer.session.mockReturnValue(read({...f.proof, access: 'read_only'}));
  f.identity.session.mockReturnValue(read({...f.proof, access: 'read_only'}));
  await f.controller.refresh(); await f.controller.submitAdministration(command);
  await f.controller.recoverAdministration(record.key); expect(f.server.send).toHaveBeenCalledOnce();
  expect(f.server.original).toHaveBeenCalledOnce(); expect(f.controller.administration?.outcome?.kind).toBe('receipt');
  f.setNow(f.proof.expiresAt); f.controller.tick(); expect(f.controller.view.session).toBeNull();
  expect(f.controller.administration).toBeNull();
});
test('HADB-02: entry form validation, explicit rejection, original recovery guard and dismissal retain their separate owner', async () => {
  const f = fixture(), setup: Authorization = {state: 'unconfigured', setupAllowed: true, enrollmentAllowed: false, permissions: []};
  f.entryServer.authorization.mockReturnValue(read(setup)); await f.controller.refresh();
  await f.controller.submitSetup('', ''); expect(f.controller.view.fields).toEqual(['name', 'time_zone']);
  f.entryServer.send.mockResolvedValueOnce({kind: 'rejected', reason: 'invalid_input', correlationId: null});
  await f.controller.submitSetup('Home', 'UTC');
  const original = f.controller.view.journal!.records[0];
  await f.controller.recover(original.key); expect(f.entryServer.send).toHaveBeenCalledOnce();
  await f.controller.dismiss(original.key); expect(f.controller.view.journal?.records).toEqual([]);
  expect(f.factory).not.toHaveBeenCalled(); expect(f.server.send).not.toHaveBeenCalled();
});
test('HADB-01: an inactive administration observation cannot publish alongside an earlier active entry', async () => {
  const f = fixture(); f.server.authorization.mockReturnValue(read({...access, state: 'pending',
    member: {...member, status: 'pending'}, permissions: []}));
  await f.controller.refresh(); expect(f.controller.administration).toBeNull();
  expect(f.controller.view.notice).toBe('context_changed'); expect(f.entryServer.session).toHaveBeenCalledTimes(2);
});
test.each(['access', 'setupAllowed', 'enrollmentAllowed'] as const)(
  'HADB-01: a persistent current %s mismatch never publishes a joint private view', async field => {
    const f = fixture();
    if (field === 'access') f.identity.session.mockReturnValue(read({...f.proof, access: 'read_only'}));
    else f.entryServer.authorization.mockReturnValue(read({...basic(access), [field]: true}));
    await f.controller.refresh(); expect(f.controller.administration).toBeNull();
    expect(f.controller.view.notice).toBe('context_changed'); expect(f.entryServer.session).toHaveBeenCalledTimes(2);
  },
);
test('HADB-01/C03: newly verified inactive entry during private collection retires the incompatible administration view', async () => {
  const f = fixture(), waiting = deferred<typeof own>(); f.server.preferences.mockReturnValueOnce(waiting);
  const opening = f.controller.refresh(); await settle();
  f.entryServer.authorization.mockReturnValue(read({...basic(access), state: 'suspended', permissions: []}));
  await f.entry.refresh(); waiting.resolve(own); await opening;
  expect(f.controller.administration).toBeNull(); expect(f.controller.view.decision?.state).toBe('suspended');
  expect(f.administrators[0].view.phase).toBe('closed');
});
test('HADB-01/C03: a newer underlying authority observation is fenced by a tick without another network request', async () => {
  const f = fixture(); await f.controller.refresh(); f.controller.tick();
  expect(f.controller.administration?.preferences).toEqual(own);
  f.server.authorization.mockReturnValue(read({...access, permissions: ['household.read']}));
  await f.administrators[0].refresh(); const reads = f.entryServer.session.mock.calls.length;
  f.controller.tick(); expect(f.controller.administration).toBeNull();
  expect(f.controller.view.notice).toBe('context_changed'); expect(f.entryServer.session).toHaveBeenCalledTimes(reads);
});
test('HADB-01: an independently pending entry read cannot keep previously visible private administration on a tick', async () => {
  const f = fixture(); await f.controller.refresh(); const waiting = deferred<VerifiedEntrySession | null>();
  f.entryServer.session.mockReturnValueOnce(waiting); const readEntry = f.entry.refresh();
  f.controller.tick(); expect(f.controller.administration).toBeNull(); expect(f.controller.view.notice).toBe('context_changed');
  waiting.resolve(f.proof); await readEntry;
});
test('HADB-01/C07: close during the sole reconciliation cancels that read and fences its completion', async () => {
  const f = fixture(), waiting = deferred<VerifiedEntrySession | null>();
  f.entryServer.session.mockReturnValueOnce(read(f.proof)).mockReturnValueOnce(waiting);
  f.identity.session.mockReturnValue(read({...f.proof, context: {...context, channel: 'stable'}}));
  const opening = f.controller.refresh(); await settle(); expect(f.entryServer.session).toHaveBeenCalledTimes(2);
  f.controller.close(); waiting.resolve(f.proof); await opening;
  expect(waiting.cancel).toHaveBeenCalledOnce(); expect(f.controller.administration).toBeNull();
  expect(f.controller.view.session).toBeNull();
});
test('HADB-01/C04: expiry during the sole reconciliation retires both views without retrying', async () => {
  const f = fixture(), waiting = deferred<typeof home>();
  f.entryServer.session.mockReturnValueOnce(read(f.proof)).mockReturnValueOnce(read({...f.proof, expiresAt: 2000}));
  f.entryServer.household.mockReturnValueOnce(read(home)).mockReturnValueOnce(waiting);
  f.identity.session.mockReturnValue(read({...f.proof, context: {...context, channel: 'stable'}}));
  const opening = f.controller.refresh(); await settle(); expect(f.entryServer.session).toHaveBeenCalledTimes(2);
  f.setNow(2000); waiting.resolve(home); await opening;
  expect(f.controller.administration).toBeNull(); expect(f.controller.view.decision?.state).toBe('authentication_required');
  expect(f.entryServer.session).toHaveBeenCalledTimes(2);
});
test('HADB-01/C03: revoked membership during reconciliation remains inactive with no private facts', async () => {
  const f = fixture(); f.entryServer.authorization.mockReturnValueOnce(read(basic(access)))
    .mockReturnValue(read({...basic(access), state: 'pending', permissions: []}));
  f.identity.session.mockReturnValue(read({...f.proof, context: {...context, channel: 'stable'}}));
  await f.controller.refresh(); expect(f.controller.view.decision?.state).toBe('pending');
  expect(f.controller.administration).toBeNull(); expect(f.administrators[0].view.phase).toBe('closed');
});
test('HADB-01/C04: a late atomic command response cannot automatically renew an expired entry lease', async () => {
  const f = fixture(); await f.controller.refresh(); const waiting = deferred<AdministrationCommandResult>();
  f.server.send.mockReturnValueOnce(waiting.result); const work = f.controller.submitAdministration(command); await settle();
  expect(f.server.send).toHaveBeenCalledOnce(); const raw = f.values.get(ADMINISTRATION_JOURNAL_KEY);
  f.setNow(f.proof.expiresAt); waiting.resolve(receipt); await work;
  expect(f.controller.view.decision?.state).toBe('authentication_required'); expect(f.controller.administration).toBeNull();
  expect(f.entryServer.session).toHaveBeenCalledOnce(); expect(f.values.get(ADMINISTRATION_JOURNAL_KEY)).toBe(raw);
});
test('HADB-01: a command reply does not silently reverify a newer suspended entry observed while it was pending', async () => {
  const f = fixture(); await f.controller.refresh(); const waiting = deferred<AdministrationCommandResult>();
  f.server.send.mockReturnValueOnce(waiting.result); const work = f.controller.submitAdministration(command); await settle();
  f.entryServer.authorization.mockReturnValue(read({...basic(access), state: 'suspended', permissions: []}));
  await f.entry.refresh(); const reads = f.entryServer.session.mock.calls.length;
  waiting.resolve(receipt); await work;
  expect(f.controller.view.decision?.state).toBe('suspended'); expect(f.controller.administration).toBeNull();
  expect(f.entryServer.session).toHaveBeenCalledTimes(reads);
});
test('HADB-01/C05: the coordinator respects an underlying busy entry even when another trusted owner started it', async () => {
  const f = fixture(); f.entryServer.authorization.mockReturnValue(read({...basic(access), state: 'not_enrolled',
    enrollmentAllowed: true, permissions: []}));
  await f.controller.refresh(); const waiting = deferred<Awaited<ReturnType<EntryServer['send']>>>();
  f.entryServer.send.mockReturnValueOnce(waiting.result); const work = f.entry.requestMembership(); await settle();
  expect(f.controller.view.busy).toBe(true); await f.controller.logout();
  expect(f.entryServer.logout).not.toHaveBeenCalled(); waiting.resolve({kind: 'uncertain'}); await work;
});
test('HADB-01/C05: an underlying administration command also blocks stale logout and replacement refresh', async () => {
  const f = fixture(); await f.controller.refresh(); const waiting = deferred<AdministrationCommandResult>();
  f.server.send.mockReturnValueOnce(waiting.result); const work = f.administrators[0].submit(command); await settle();
  expect(f.controller.view.busy).toBe(true); const reads = f.entryServer.session.mock.calls.length;
  await f.controller.logout(); await f.controller.refresh(); expect(f.entryServer.logout).not.toHaveBeenCalled();
  expect(f.entryServer.session).toHaveBeenCalledTimes(reads); waiting.resolve(receipt); await work;
});
test('HADB-01/C13: relinking the same HA account cannot expose the prior private receipt through the joined view', async () => {
  const f = fixture(); await f.controller.refresh(); await f.controller.submitAdministration(command);
  const original = f.controller.administration!.journal!.records[0], next = {...member, memberId: 'member-relinked'};
  f.server.authorization.mockReturnValue(read({...access, member: next}));
  f.server.preferences.mockReturnValue(read({...own, memberId: next.memberId}));
  f.server.roster.mockReturnValue(read({directoryState: 'available', members: [{member: next,
    presentation: {memberId: next.memberId, alias: null, revision: revisionValue('11')},
    metadata: {state: 'available', name: 'Current member', avatarState: 'unavailable'}}]}));
  await f.controller.refresh(); expect(f.controller.administration?.outcome).toBeNull();
  expect(f.controller.administration?.preferences?.memberId).toBe(next.memberId);
  await f.controller.recoverAdministration(original.key);
  expect(f.server.operation).toHaveBeenCalledOnce(); expect(f.server.send).toHaveBeenCalledOnce();
  expect(f.controller.administration?.outcome).toBeNull();
  expect(f.controller.administration?.notice).toBe('invalid_response');
  expect(JSON.stringify(f.controller.administration)).not.toContain('"memberId":"member-own"');
});
test('HADB-02/C12: reconciling entry after a rejected stale draft preserves the actionable conflict and sends no command', async () => {
  const f = fixture(); await f.controller.refresh();
  await f.controller.submitAdministration({...command, payload: {...command.payload, expected_revision: '12'}});
  expect(f.controller.administration?.notice).toBe('conflict'); expect(f.server.send).not.toHaveBeenCalled();
  expect(f.controller.administration?.preferences).toEqual(own);
});
test('HADB-02/C12: invalid intent remains an explicit error after entry reconciliation without sending', async () => {
  const f = fixture(); await f.controller.refresh(); await f.controller.submitAdministration(null);
  expect(f.controller.administration?.notice).toBe('invalid_input'); expect(f.server.send).not.toHaveBeenCalled();
});
test('HADB-01/C04: session expiry supersedes an earlier context mismatch notice', async () => {
  const f = fixture(); f.identity.session.mockReturnValue(read({...f.proof, context: {...context, channel: 'stable'}}));
  await f.controller.refresh(); expect(f.controller.view.notice).toBe('context_changed');
  f.setNow(f.proof.expiresAt); f.controller.tick();
  expect(f.controller.view.notice).toBe('authentication_required'); expect(f.controller.administration).toBeNull();
});
test('HADB-01/C03: newer pending authority supersedes an earlier context mismatch notice', async () => {
  const f = fixture(); f.identity.session.mockReturnValue(read({...f.proof, context: {...context, channel: 'stable'}}));
  await f.controller.refresh(); expect(f.controller.view.notice).toBe('context_changed');
  f.entryServer.authorization.mockReturnValue(read({...basic(access), state: 'pending', permissions: []}));
  await f.entry.refresh(); f.controller.tick(); expect(f.controller.view.decision?.state).toBe('pending');
  expect(f.controller.view.notice).toBeNull();
});
test('HADB-01/C07: disposal during logout fences the late revocation response as well as private reads', async () => {
  const f = fixture(); await f.controller.refresh(); const waiting = deferred<{upstreamRevoked: boolean}>();
  f.entryServer.logout.mockReturnValueOnce(waiting.result); const work = f.controller.logout(); await settle();
  expect(f.entryServer.logout).toHaveBeenCalledOnce(); const before = f.controller.view;
  f.controller.close(); waiting.resolve({upstreamRevoked: true}); await work;
  expect(f.controller.view).toEqual(before); expect(f.controller.administration).toBeNull();
  expect(f.controller.view.notice).toBeNull(); expect(f.controller.view.cleanup).toBeNull();
});
test.each(['invalid_input', 'missing_request', 'read_only'] as const)(
  'household-browser-C13: %s cannot reuse private facts after the same HA account changes member', async kind => {
    const f = fixture();
    if (kind === 'read_only') {
      f.entryServer.session.mockReturnValue(read({...f.proof, access: 'read_only'}));
      f.identity.session.mockReturnValue(read({...f.proof, access: 'read_only'}));
    }
    await f.controller.refresh(); expect(f.controller.administration?.preferences?.memberId).toBe(member.memberId);
    const next = {...member, memberId: 'member-relinked'};
    f.server.authorization.mockReturnValue(read({...access, member: next}));
    f.server.preferences.mockReturnValue(read({...own, memberId: next.memberId}));
    f.server.roster.mockReturnValue(read({directoryState: 'available', members: [{member: next,
      presentation: {memberId: next.memberId, alias: null, revision: revisionValue('11')},
      metadata: {state: 'available', name: 'Current member', avatarState: 'unavailable'}}]}));
    if (kind === 'missing_request') await f.controller.recoverAdministration('missing-original');
    else await f.controller.submitAdministration(kind === 'invalid_input' ? null : command);
    expect(f.controller.administration?.preferences?.memberId).toBe(next.memberId);
    expect(JSON.stringify(f.controller.administration)).not.toContain('"memberId":"member-own"');
    expect(f.server.send).not.toHaveBeenCalled(); expect(f.server.original).not.toHaveBeenCalled();
    expect(f.server.operation).not.toHaveBeenCalled();
  },
);
test('household-browser-C02: an empty administration error from the earlier context cannot be joined to a new account context', async () => {
  const f = fixture(); await f.controller.refresh();
  f.server.send.mockResolvedValueOnce({kind: 'rejected', reason: 'forbidden', correlationId: 'old-context-correlation'});
  const next = {...f.proof, context: {...context, installationId: '11234567-89ab-cdef-0123-456789abcdef'}};
  f.entryServer.session.mockReturnValue(read(next));
  await f.controller.submitAdministration(command);
  expect(f.controller.administration).toBeNull(); expect(f.controller.view.notice).toBe('context_changed');
  expect(JSON.stringify(f.controller.view)).not.toContain('old-context-correlation');
});
test('household-browser-C04: the scheduling projection contains only immutable absolute lease and original-retention deadlines', async () => {
  const f = fixture(); expect(f.controller.deadlines).toEqual([]); await f.controller.refresh();
  expect(f.controller.deadlines).toEqual([f.proof.expiresAt, f.proof.expiresAt]);
  await f.controller.submitAdministration(command);
  const deadlines = f.controller.deadlines;
  expect(deadlines).toEqual([f.proof.expiresAt, f.proof.expiresAt, 3_601_000]);
  expect(Object.isFrozen(deadlines)).toBe(true); expect(JSON.stringify(deadlines)).not.toContain('locale');
  f.controller.close(); expect(f.controller.deadlines).toEqual([]); expect(deadlines).toHaveLength(3);
});


function taskWorkspace(mode: 'native' | 'standalone' = 'standalone') {
  const f = fixture(mode), proof = {...f.proof}, identity = {session: vi.fn(() => read<VerifiedEntrySession | null>(proof))};
  const work: TaskDetail = {occurrenceId: 'work-1', definitionId: 'def-1', definitionRevision: revisionValue('1'), title: 'Clean', description: '', priority: 'normal',
    state: 'available', revision: revisionValue('1'), assigneeIds: [], dueAt: null, currentCycleId: null, allowedActions: ['complete'], cycle: null, materials: [],
    materialRecording: 'review_on_completion', dependencyReviewRequired: false, pendingMaterials: false};
  const result: TaskReceipt = {kind: 'receipt', stage: 'committed', action: 'task.create', operationId: 'task-operation', occurrenceId: 'work-1',
    revision: revisionValue('1'), state: 'available', cycle: null, archivedBy: null};
  const server = {access: vi.fn(() => read({householdId: 'home', memberId: member.memberId, canCreate: true})),
    list: vi.fn(() => read({items: [work], nextCursor: null})), detail: vi.fn(() => read(work)), original: vi.fn(() => read(result)),
    send: vi.fn<TaskServer['send']>(async () => result)};
  const controllers: TaskController[] = [], factory = vi.fn(() => {const value = new TaskController(mode, identity, server, new TaskSessionJournal(f.storage), f.clock, f.entropy);
    controllers.push(value); return value;});
  return {...f, taskIdentity: identity, taskProof: proof, taskServer: server, taskFactory: factory, taskControllers: controllers,
    workspace: new HouseholdController(f.entry, f.factory, factory)};
}
test.each(['native', 'standalone'] as const)('%s: the household owns actual task controllers, mutations, deadlines and closure', async mode => {
  const f = taskWorkspace(mode); expect(f.workspace.tasks).toBeNull(); await f.workspace.taskWork(controller => controller.refresh()); expect(f.taskFactory).not.toHaveBeenCalled();
  await f.workspace.refresh(); expect(f.workspace.tasks?.page?.items[0].title).toBe('Clean');
  await f.workspace.taskWork(controller => controller.create('New', '', 'normal')); expect(f.taskServer.send).toHaveBeenCalledOnce();
  expect(f.workspace.tasks?.outcome).toMatchObject({kind: 'receipt', operationId: 'task-operation'}); expect(f.workspace.deadlines).toContain(3601000);
  f.workspace.close(); expect(f.taskControllers[0].view.phase).toBe('closed'); expect(f.workspace.tasks).toBeNull();
});
test.each(['subject', 'access', 'member', 'household'])(
  'task %s drift cannot be combined with the currently verified household view', async field => {
    const f = taskWorkspace();
    if (field === 'subject') f.taskIdentity.session.mockReturnValue(read({...f.taskProof, context: {...context, subject: 'b'.repeat(32)}}));
    if (field === 'access') f.taskIdentity.session.mockReturnValue(read({...f.taskProof, access: 'read_only'}));
    if (field === 'member') f.taskServer.access.mockReturnValue(read({householdId: 'home', memberId: 'other', canCreate: true}));
    if (field === 'household') f.taskServer.access.mockReturnValue(read({householdId: 'other', memberId: member.memberId, canCreate: true}));
    await f.workspace.refresh(); expect(f.workspace.tasks).toBeNull(); expect(f.workspace.administration).toBeNull(); expect(f.workspace.view.notice).toBe('context_changed');
    f.workspace.close();
  });
test('an empty task permission failure is displayed without inventing an empty task list', async () => {
  const f = taskWorkspace(); f.taskServer.access.mockReturnValue({result: Promise.reject(new EntryReadError('forbidden')), cancel: vi.fn()});
  await f.workspace.refresh(); expect(f.workspace.tasks?.notice).toBe('forbidden'); expect(f.workspace.tasks?.page).toBeNull(); expect(f.workspace.administration).not.toBeNull(); f.workspace.close();
});
test('a shorter verified task lease expires every private household workspace without renewing proof', async () => {
  const f = taskWorkspace(); f.taskProof.expiresAt = 2000; await f.workspace.refresh(); const calls = f.taskIdentity.session.mock.calls.length;
  f.setNow(2000); f.workspace.tick(); expect(f.workspace.tasks).toBeNull(); expect(f.workspace.administration).toBeNull();
  expect(f.workspace.view.decision?.state).toBe('authentication_required'); expect(f.taskIdentity.session).toHaveBeenCalledTimes(calls); f.workspace.close();
});
test('parent closure fences a task refresh delivered after its owned lifetime', async () => {
  const f = taskWorkspace(), pending = deferred<VerifiedEntrySession | null>(); f.taskIdentity.session.mockReturnValue(pending);
  const opening = f.workspace.refresh(); await vi.waitFor(() => expect(f.taskFactory).toHaveBeenCalledOnce());
  f.workspace.close(); pending.resolve(f.taskProof); await opening; expect(f.workspace.tasks).toBeNull(); expect(f.workspace.view.phase).toBe('closed');
});
test('a changed verified household after a task action hides its old result', async () => {
  const f = taskWorkspace(); await f.workspace.refresh();
  await f.workspace.taskWork(async () => {f.taskIdentity.session.mockReturnValue(read({...f.taskProof, context: {...context, subject: 'b'.repeat(32)}}));
    await f.taskControllers[0].refresh();});
  expect(f.workspace.tasks).toBeNull(); expect(f.workspace.view.notice).toBe('context_changed'); f.workspace.close();
});
test('closure during an in-flight task command retains only its original journal, without reviving a view', async () => {
  const f = taskWorkspace(); await f.workspace.refresh(); const pending = deferred<TaskReceipt>();
  f.taskServer.send.mockReturnValueOnce(pending.result);
  const sending = f.workspace.taskWork(controller => controller.create('New', '', 'normal'));
  await vi.waitFor(() => expect(f.taskServer.send).toHaveBeenCalledOnce()); f.workspace.close(); pending.resolve({kind: 'receipt', stage: 'committed', action: 'task.create',
    operationId: 'task-operation', occurrenceId: 'work-1', revision: revisionValue('1'), state: 'available', cycle: null, archivedBy: null});
  await sending; expect(f.workspace.tasks).toBeNull(); expect(f.workspace.view.phase).toBe('closed');
});


test('unavailable administration metadata does not turn independently protected task reads into an empty list', async () => {
  const f = taskWorkspace(); f.server.capabilities.mockReturnValue({result: Promise.reject(new EntryReadError('unavailable')), cancel: vi.fn()});
  await f.workspace.refresh(); expect(f.workspace.tasks?.page?.items[0].title).toBe('Clean'); expect(f.workspace.administration?.notice).toBe('unavailable');
  f.workspace.close();
});
