import {expect, test, vi} from 'vitest';
import {AdministrationController} from '../src/application/administration-controller';
import type {AdministrationCommandResult, AdministrationOriginal, AdministrationRequest} from '../src/application/administration-ports';
import {EntryReadError} from '../src/application/ports';
import type {EntryRead, VerifiedEntrySession} from '../src/application/ports';
import {AdministrationSessionJournal, ADMINISTRATION_JOURNAL_KEY} from '../src/adapters/administration-journal';
import {administrationCommand} from '../src/domain/administration-commands';
import type {AdministrationCommand} from '../src/domain/administration-commands';
import {revisionValue} from '../src/domain/administration';
import type {AdministrationAccess, AdministrationReceipt, OwnPreferences, Roster} from '../src/domain/administration-views';

function read<T>(value: T): EntryRead<T> {return {result: Promise.resolve(value), cancel: vi.fn()};}
function deferred<T>() {
  let resolve!: (value: T) => void, reject!: (value: unknown) => void;
  const result = new Promise<T>((yes, no) => {resolve = yes; reject = no;});
  return {result, resolve, reject, cancel: vi.fn()};
}
async function settle() {for (let i = 0; i < 40; i++) await Promise.resolve();}
const context = {installationId: '01234567-89ab-cdef-0123-456789abcdef', channel: 'edge' as const, subject: 'a'.repeat(32)};
const session: VerifiedEntrySession = {context, deployment: 'standalone', access: 'full', serverTime: 1000,
  expiresAt: 1_000_000, householdApiAvailable: true};
const member = {memberId: 'member-own', role: 'adult' as const, status: 'active' as const, revision: revisionValue('3'),
  haUserId: context.subject, exceptions: []};
const access: AdministrationAccess = {state: 'active', setupAllowed: false, enrollmentAllowed: false, member,
  effectiveRole: 'administrator', policyRevision: revisionValue('5'), permissions: ['household.read', 'household.manage',
    'members.read', 'members.manage', 'policy.manage', 'preferences.read', 'preferences.write', 'operations.read']};
const home = {householdId: 'home', name: 'Home', timeZone: 'UTC', revision: revisionValue('7')};
const policy = {householdId: 'home', revision: revisionValue('5'), mappingMode: 'all_ha_administrators' as const,
  targetHAUserId: null, adjustments: []};
const own = {memberId: member.memberId, alias: null, revision: revisionValue('11')};
const preferences: OwnPreferences = {memberId: member.memberId, revision: revisionValue('13'), locale: 'es',
  routine_participation_summaries: true, notificationDelivery: 'unavailable' as const};
const commands: readonly AdministrationCommand[] = [
  administrationCommand({action: 'household.update', payload: {expected_revision: '7', name: 'New home', time_zone: 'Europe/Madrid'}}),
  administrationCommand({action: 'member.update', memberId: member.memberId, payload: {expected_revision: '3', role: 'restricted', status: 'active', exceptions: []}}),
  administrationCommand({action: 'policy.update', payload: {expected_revision: '5', mapping_mode: 'all_ha_administrators', target_ha_user_id: null, adjustments: []}}),
  administrationCommand({action: 'member.presentation.update', memberId: member.memberId, payload: {expected_revision: '11', alias: 'Literal <owner>'}}),
  administrationCommand({action: 'member.preferences.update', payload: {expected_revision: '13', locale: 'en', routine_participation_summaries: false}}),
];
function receipt(command: AdministrationCommand): AdministrationReceipt {
  const revision = revisionValue(String(BigInt(command.payload.expected_revision) + 1n));
  const result = command.action === 'household.update' ? {householdId: 'home', revision}
    : command.action === 'policy.update' ? {householdId: 'home', revision, mappingMode: command.payload.mapping_mode}
    : command.action === 'member.update' ? {memberId: command.memberId, role: command.payload.role, status: command.payload.status, revision}
    : command.action === 'member.presentation.update' ? {memberId: command.memberId, alias: command.payload.alias, revision}
    : {...preferences, locale: command.payload.locale, routine_participation_summaries: command.payload.routine_participation_summaries, revision};
  return {kind: 'receipt', stage: 'committed', action: command.action, operationId: 'op-original', archivedBy: null,
    createdAt: 1000, result, eventDelivery: null, notificationDelivery: 'unavailable'};
}
function fixture(initial = access, mode: 'native' | 'standalone' = 'standalone') {
  let now = 1000;
  const values = new Map<string, string>();
  const storage = {getItem: vi.fn((key: string) => values.get(key) ?? null),
    setItem: vi.fn((key: string, value: string) => {values.set(key, value);}), removeItem: vi.fn()};
  const journal = new AdministrationSessionJournal(storage);
  const identity = {session: vi.fn(() => read<VerifiedEntrySession | null>({...session, deployment: mode}))};
  const server = {
    capabilities: vi.fn(() => read({contractVersion: 2 as const, householdId: 'home', actions: commands.map(c => c.action)})),
    authorization: vi.fn(() => read(initial)), household: vi.fn(() => read(home)), policy: vi.fn(() => read(policy)),
    roster: vi.fn(() => read<Roster>({directoryState: 'available' as const, members: [{member, presentation: own,
      metadata: {state: 'available' as const, name: 'Verified owner', avatarState: 'unavailable' as const}}]})),
    directory: vi.fn(() => read({state: 'denied' as const, profiles: []})), preferences: vi.fn(() => read(preferences)),
    presentation: vi.fn(() => read(own)),
    send: vi.fn((request: AdministrationRequest) => Promise.resolve<AdministrationCommandResult>(receipt(request.command))),
    original: vi.fn((request: AdministrationOriginal): EntryRead<AdministrationReceipt> => read({...receipt(request.command), eventDelivery: 'delivered' as const})),
    operation: vi.fn((request: AdministrationOriginal): EntryRead<AdministrationReceipt> => read({...receipt(request.command), eventDelivery: 'pending' as const})),
  };
  const clock = {anchor: vi.fn(), now: vi.fn(() => now)}, entropy = {requestKey: vi.fn(() => 'request-original')};
  const controller = new AdministrationController(mode, identity, server, journal, clock, entropy);
  return {controller, identity, server, journal, values, storage, clock, entropy, setNow: (value: number) => {now = value;}};
}

test.each(['native', 'standalone'] as const)('HADW-04/05: %s refresh loads only currently permitted facts and never mutates', async mode => {
  const f = fixture(access, mode); expect(f.controller.view.phase).toBe('idle');
  await f.controller.refresh();
  expect(f.controller.view.phase).toBe('ready'); expect(f.controller.view.preferences).toEqual(preferences);
  expect(f.controller.view.roster?.members[0].member.role).toBe('adult');
  expect(f.controller.view.access?.effectiveRole).toBe('administrator');
  expect(f.controller.view.directory).toEqual({state: 'denied', profiles: []});
  expect(f.server.authorization).toHaveBeenCalledTimes(2); expect(f.server.send).not.toHaveBeenCalled();
  expect(f.entropy.requestKey).not.toHaveBeenCalled(); expect(f.controller.view.journal?.records).toEqual([]);
});
test.each(commands)('HADW-01/02/04/05: explicit $action persists exact original before one send', async command => {
  const f = fixture(); await f.controller.refresh();
  f.server.send.mockImplementationOnce(async request => {
    expect(JSON.parse(f.values.get(ADMINISTRATION_JOURNAL_KEY)!).records[0]).toMatchObject({key: request.key, ...request.command, stage: 'prepared'});
    expect(f.controller.view.phase).toBe('sending'); return receipt(request.command);
  });
  await f.controller.submit(command);
  expect(f.server.send).toHaveBeenCalledExactlyOnceWith({key: 'request-original', command}, context);
  expect(f.controller.view.outcome).toEqual(receipt(command));
  expect(f.controller.view.journal?.records[0]).toMatchObject({stage: 'committed', operationId: 'op-original'});
  expect(f.entropy.requestKey).toHaveBeenCalledTimes(1); expect(f.controller.view.busy).toBe(false);
});
test('C69: reload and explicit recovery use GET with the immutable original, never mutation replay', async () => {
  const f = fixture(); await f.controller.refresh(); f.server.send.mockResolvedValueOnce({kind: 'uncertain'});
  await f.controller.submit(commands[4]); const original = f.controller.view.journal!.records[0];
  await f.controller.refresh(); expect(f.server.original).not.toHaveBeenCalled();
  await f.controller.recover(original.key);
  expect(f.server.original).toHaveBeenCalledExactlyOnceWith({key: original.key, command: commands[4], operationId: null}, context);
  expect(f.server.send).toHaveBeenCalledTimes(1); expect(f.controller.view.outcome?.kind).toBe('receipt');
  await f.controller.recover(original.key);
  expect(f.server.operation).toHaveBeenCalledExactlyOnceWith({key: original.key, command: commands[4], operationId: 'op-original'}, context);
  expect(f.entropy.requestKey).toHaveBeenCalledTimes(1);
});
test('HADW-02: an unbound private preferences member is never presented', async () => {
  const f = fixture(); f.server.preferences.mockReturnValue(read({...preferences, memberId: 'another-member'}));
  await f.controller.refresh(); expect(f.controller.view.preferences).toBeNull();
  expect(f.controller.view.errors.preferences).toBe('invalid_response'); expect(f.controller.view.household).toEqual(home);
});
test('C21/C72: authority drift during reads hides all collected private facts', async () => {
  const f = fixture(); f.server.authorization.mockReturnValueOnce(read(access)).mockReturnValueOnce(read({...access, policyRevision: revisionValue('6')}));
  await f.controller.refresh(); expect(f.controller.view.notice).toBe('access_changed');
  expect(f.controller.view.preferences).toBeNull(); expect(f.controller.view.roster).toBeNull();
});
test('C72: a retired pending private read cannot repopulate a closed view', async () => {
  const f = fixture(), pending = deferred<typeof preferences>(); f.server.preferences.mockReturnValue(pending);
  const work = f.controller.refresh(); await settle(); f.controller.close();
  expect(pending.cancel).toHaveBeenCalled(); pending.resolve(preferences); await work;
  expect(f.controller.view.phase).toBe('closed'); expect(f.controller.view.preferences).toBeNull();
});
test('C10/C11: stale or exhausted original revision is not rebased and has no prepared effect', async () => {
  const f = fixture(); await f.controller.refresh(); f.server.household.mockReturnValue(read({...home, revision: revisionValue('8')}));
  await f.controller.submit(commands[0]); expect(f.controller.view.notice).toBe('conflict');
  expect(f.server.send).not.toHaveBeenCalled(); expect(f.entropy.requestKey).not.toHaveBeenCalled();
  f.server.household.mockReturnValue(read({...home, revision: revisionValue('9223372036854775807')})); await f.controller.refresh();
  await f.controller.submit({...commands[0], payload: {...commands[0].payload, expected_revision: '9223372036854775807'}});
  expect(f.controller.view.notice).toBe('revision_exhausted'); expect(f.server.send).not.toHaveBeenCalled();
});
test('HADW-05: read-only outage permits local facts and an owned journal until expiry, with no mutation', async () => {
  const f = fixture(); f.identity.session.mockReturnValue(read({...session, access: 'read_only'}));
  await f.controller.refresh(); expect(f.controller.view.preferences).toEqual(preferences); expect(f.controller.view.journal?.records).toEqual([]);
  await f.controller.submit(commands[4]); expect(f.server.send).not.toHaveBeenCalled();
  f.setNow(session.expiresAt); f.controller.tick(); expect(f.controller.view.preferences).toBeNull();
  expect(f.controller.view.notice).toBe('authentication_required');
});
test('C69: stale command responses cannot repopulate a new verified subject', async () => {
  const f = fixture(); await f.controller.refresh(); const pending = deferred<AdministrationCommandResult>(); f.server.send.mockReturnValue(pending.result);
  const sent = f.controller.submit(commands[4]); await settle();
  const nextMember = {...member, memberId: 'member-new', haUserId: 'b'.repeat(32)};
  f.identity.session.mockReturnValue(read({...session, context: {...context, subject: nextMember.haUserId}}));
  f.server.authorization.mockReturnValue(read({...access, member: nextMember}));
  f.server.preferences.mockReturnValue(read({...preferences, memberId: nextMember.memberId}));
  await f.controller.refresh(); pending.resolve(receipt(commands[4])); await sent;
  expect(f.controller.view.preferences?.memberId).toBe('member-new');
  expect(f.controller.view.session?.context.subject).toBe('b'.repeat(32)); expect(f.controller.view.outcome).toBeNull();
  expect(f.controller.view.journal?.records).toEqual([]);
});

test('HADW-02: a same-account replacement membership cannot retain the former private receipt', async () => {
  const f = fixture(); await f.controller.refresh(); await f.controller.submit(commands[4]);
  f.server.authorization.mockReturnValue(read({...access, member: {...member, memberId: 'replacement'}}));
  f.server.preferences.mockReturnValue(read({...preferences, memberId: 'replacement'}));
  await f.controller.refresh(); expect(f.controller.view.preferences?.memberId).toBe('replacement');
  expect(f.controller.view.outcome).toBeNull();
});
test('C05: original GET recovery requires original-action authority without a current aggregate read', async () => {
  const f = fixture(); await f.controller.refresh(); await f.controller.submit(commands[0]);
  f.server.authorization.mockReturnValue(read({...access, permissions: ['household.manage', 'operations.read']}));
  await f.controller.refresh(); expect(f.controller.view.household).toBeNull();
  await f.controller.recover('request-original');
  expect(f.server.operation).toHaveBeenCalledTimes(1); expect(f.controller.view.notice).not.toBe('invalid_response');
  expect(f.controller.view.outcome?.kind).toBe('receipt');
});

test.each([null, {...session, deployment: 'native' as const}, {...session, householdApiAvailable: false},
  {...session, expiresAt: 1000}])('HADW-05: unsupported or expired session facts never open administration %j', async source => {
  const f = fixture(); f.identity.session.mockReturnValue(read(source)); await f.controller.refresh();
  expect(f.controller.view.notice).toBe(source === null || source.expiresAt === 1000 ? 'authentication_required'
    : source.deployment === 'native' ? 'invalid_response' : 'api_unavailable');
  expect(f.server.authorization).not.toHaveBeenCalled(); expect(f.controller.view.preferences).toBeNull();
  await f.controller.submit(commands[4]); expect(f.server.send).not.toHaveBeenCalled();
});
test.each(['unconfigured','not_enrolled','pending','suspended','archived'] as const)('HADW-04: %s access has no workspace or journal authority', async state => {
  const f = fixture({...access, state}); await f.controller.refresh(); expect(f.controller.view.notice).toBe('inactive');
  expect(f.server.capabilities).not.toHaveBeenCalled(); expect(f.controller.view.journal).toBeNull();
  await f.controller.submit(commands[4]); expect(f.server.send).not.toHaveBeenCalled();
});
test('HADW-02: active access without a verified current membership fails closed', async () => {
  const f = fixture({...access, member: null}); await f.controller.refresh(); expect(f.controller.view.notice).toBe('invalid_response');
  expect(f.controller.view.preferences).toBeNull(); expect(f.server.preferences).not.toHaveBeenCalled();
});
test.each([new EntryReadError('forbidden'), new Error('private-provider-token')])('HADW-05: session failure is a bounded safe state %j', async error => {
  const f = fixture(); f.identity.session.mockReturnValue({result: Promise.reject(error), cancel: vi.fn()});
  await f.controller.refresh(); expect(f.controller.view.notice).toBe(error instanceof EntryReadError ? 'forbidden' : 'unavailable');
  expect(JSON.stringify(f.controller.view)).not.toContain('private-provider-token');
});
test('HADW-05: synchronous clock/source failure cannot retain a private view', async () => {
  const f = fixture(); await f.controller.refresh(); f.clock.anchor.mockImplementation(() => {throw new Error('clock-private');});
  await f.controller.refresh(); expect(f.controller.view.notice).toBe('unavailable'); expect(f.controller.view.preferences).toBeNull();
});
test.each(['household','roster','policy','directory','preferences'] as const)('HADW-03: failed %s read remains unavailable while other allowed facts stay honest', async field => {
  const f = fixture(); const failed: EntryRead<never> = {result: Promise.reject(new EntryReadError('invalid_response')), cancel: vi.fn()};
  f.server[field].mockReturnValue(failed);
  await f.controller.refresh(); expect(f.controller.view[field]).toBeNull(); expect(f.controller.view.errors[field]).toBe('invalid_response');
  expect(f.controller.view.access).toEqual(access); expect(f.controller.view.phase).toBe('ready');
});
test('HADW-03: unexpected provider failure does not become absence or raw detail', async () => {
  const f = fixture(); f.server.roster.mockImplementation(() => {throw new Error('private-ha-detail');});
  await f.controller.refresh(); expect(f.controller.view.errors.roster).toBe('unavailable');
  expect(f.controller.view.roster).toBeNull(); expect(JSON.stringify(f.controller.view)).not.toContain('private-ha-detail');
});
test('HADW-04: mismatched household/policy scope is not published as a current policy', async () => {
  const f = fixture(); f.server.policy.mockReturnValue(read({...policy, householdId: 'foreign-home'}));
  await f.controller.refresh(); expect(f.controller.view.policy).toBeNull(); expect(f.controller.view.errors.policy).toBe('invalid_response');
});
test.each(commands)('C42: a role label grants no $action permission', async command => {
  const f = fixture({...access, permissions: []}); await f.controller.refresh();
  expect(f.controller.view.household).toBeNull(); expect(f.server.preferences).not.toHaveBeenCalled();
  await f.controller.submit(command); expect(f.controller.view.notice).toBe('action_not_allowed'); expect(f.server.send).not.toHaveBeenCalled();
});
test('HADW-01: own alias uses the owner permission, without granting another alias', async () => {
  const f = fixture({...access, permissions: ['members.read', 'preferences.write']}); await f.controller.refresh();
  await f.controller.submit(commands[3]); expect(f.server.send).toHaveBeenCalledTimes(1);
  await f.controller.submit({...commands[3], memberId: 'other'}); expect(f.controller.view.notice).toBe('action_not_allowed');
  expect(f.server.send).toHaveBeenCalledTimes(1);
});
test.each(commands)('HADW-04: $action needs the target revision facts, without guessing one', async command => {
  const f = fixture(); await f.controller.refresh();
  const field = command.action === 'household.update' ? 'household' : command.action === 'policy.update' ? 'policy'
    : command.action === 'member.preferences.update' ? 'preferences' : 'roster';
  f.server[field].mockImplementation(() => {throw new Error('unavailable');});
  if (command.action === 'member.presentation.update') f.server.presentation.mockImplementation(() => {throw new Error('unavailable');});
  await f.controller.submit(command); expect(f.controller.view.notice).toBe('action_not_allowed'); expect(f.server.send).not.toHaveBeenCalled();
});
test.each([1,3])('HADW-04: member target %s must be present in the current roster', async index => {
  const f = fixture(); await f.controller.refresh(); await f.controller.submit({...commands[index], memberId: 'missing'});
  expect(f.controller.view.notice).toBe('action_not_allowed'); expect(f.server.send).not.toHaveBeenCalled();
});
test('C39/C44: closed invalid command never prepares credentials or creates a key', async () => {
  const f = fixture(); await f.controller.refresh(); await f.controller.submit({...commands[4], credentials: 'forbidden-secret'});
  expect(f.controller.view.notice).toBe('invalid_input'); expect(f.entropy.requestKey).not.toHaveBeenCalled();
  expect(f.server.send).not.toHaveBeenCalled(); expect(f.values.get(ADMINISTRATION_JOURNAL_KEY)).not.toContain('forbidden-secret');
});
test('C67: unavailable journal storage leaves permitted reads usable and blocks a new mutation', async () => {
  const f = fixture(); f.storage.getItem.mockImplementation(() => {throw new Error('storage-private');});
  await f.controller.refresh(); expect(f.controller.view.notice).toBe('journal_unavailable'); expect(f.controller.view.preferences).toEqual(preferences);
  await f.controller.submit(commands[4]); expect(f.server.send).not.toHaveBeenCalled();
});
test('C66: a foreign journal context cannot become the current view', async () => {
  const f = fixture(); vi.spyOn(f.journal, 'open').mockReturnValue({context: {...context, subject: 'b'.repeat(32)}, observedAt: 1000, records: []});
  await f.controller.refresh(); expect(f.controller.view.notice).toBe('journal_unavailable'); expect(f.controller.view.journal).toBeNull();
});
test('C72: cancellation failure still retires the prior generation', async () => {
  const f = fixture(), pending = deferred<VerifiedEntrySession | null>(); pending.cancel.mockImplementation(() => {throw new Error('cancel-failure');});
  f.identity.session.mockReturnValueOnce(pending); const work = f.controller.refresh(); await f.controller.refresh();
  pending.resolve(null); await work; expect(f.controller.view.preferences).toEqual(preferences); expect(pending.cancel).toHaveBeenCalled();
});
test('C72: rejection of a canceled pending fact never changes a newer view', async () => {
  const f = fixture(), pending = deferred<typeof preferences>(); f.server.preferences.mockReturnValueOnce(pending);
  const work = f.controller.refresh(); await settle(); await f.controller.refresh(); pending.reject(new Error('retired-private')); await work;
  expect(f.controller.view.preferences).toEqual(preferences); expect(f.controller.view.notice).toBeNull();
});
test('HADW-05: an initial load that outlives the session cannot publish its private results', async () => {
  const f = fixture(), pending = deferred<typeof preferences>(); f.server.preferences.mockReturnValue(pending);
  const work = f.controller.refresh(); await settle(); f.setNow(session.expiresAt); pending.resolve(preferences); await work;
  expect(f.controller.view.notice).toBe('authentication_required'); expect(f.controller.view.preferences).toBeNull();
});
test('C21: authority change during mutation preflight prevents preparation', async () => {
  const f = fixture(); await f.controller.refresh(); f.server.authorization.mockReturnValueOnce(read(access))
    .mockReturnValueOnce(read({...access, permissions: ['preferences.read']}));
  await f.controller.submit(commands[4]); expect(f.controller.view.notice).toBe('access_changed'); expect(f.server.send).not.toHaveBeenCalled();
});
test('C72: a changed session context during preflight never submits the old draft', async () => {
  const f = fixture(); await f.controller.refresh(); f.identity.session.mockReturnValue(read({...session, context: {...context, channel: 'stable'}}));
  await f.controller.submit(commands[4]); expect(f.controller.view.notice).toBe('context_changed'); expect(f.server.send).not.toHaveBeenCalled();
});
test.each([{access: 'read_only' as const}, {householdApiAvailable: false}])('HADW-05: preflight session downgrade has no new effect %j', async patch => {
  const f = fixture(); await f.controller.refresh(); f.identity.session.mockReturnValue(read({...session, ...patch}));
  await f.controller.submit(commands[4]); expect(f.server.send).not.toHaveBeenCalled(); expect(f.entropy.requestKey).not.toHaveBeenCalled();
});
test('HADW-05: a missing session in preflight does not submit a formerly valid draft', async () => {
  const f = fixture(); await f.controller.refresh(); f.identity.session.mockReturnValue(read(null));
  await f.controller.submit(commands[4]); expect(f.controller.view.notice).toBe('authentication_required'); expect(f.server.send).not.toHaveBeenCalled();
});
test('HADW-05: inactive preflight state removes authority even if the session remains verified', async () => {
  const f = fixture(); await f.controller.refresh(); f.server.authorization.mockReturnValue(read({...access, state: 'suspended'}));
  await f.controller.submit(commands[4]); expect(f.server.send).not.toHaveBeenCalled();
});
test('C69: duplicate interactions during preflight or POST have one original key/effect', async () => {
  const f = fixture(); await f.controller.refresh(); const proof = deferred<VerifiedEntrySession | null>(), sent = deferred<AdministrationCommandResult>();
  f.identity.session.mockReturnValueOnce(proof); f.server.send.mockReturnValue(sent.result);
  const first = f.controller.submit(commands[4]); await f.controller.submit(commands[4]); await f.controller.recover('request-original');
  proof.resolve(session); await settle(); expect(f.server.send).toHaveBeenCalledTimes(1);
  await f.controller.dismiss('request-original'); await f.controller.submit(commands[4]);
  sent.resolve(receipt(commands[4])); await first; expect(f.entropy.requestKey).toHaveBeenCalledTimes(1);
});
test('C68: an unresolved original blocks the same aggregate and permits a different explicit aggregate', async () => {
  const f = fixture(); await f.controller.refresh(); f.server.send.mockResolvedValueOnce({kind: 'uncertain'});
  await f.controller.submit(commands[4]); f.entropy.requestKey.mockReturnValue('different-key');
  await f.controller.submit(commands[4]); expect(f.controller.view.notice).toBe('previous_request_unresolved'); expect(f.server.send).toHaveBeenCalledTimes(1);
  await f.controller.submit(commands[0]); expect(f.server.send).toHaveBeenCalledTimes(2); expect(f.controller.view.journal?.records).toHaveLength(2);
});
test('C68: unresolved alias edits do not block a different member aggregate', async () => {
  const f = fixture(); f.server.roster.mockReturnValue(read({directoryState: 'available', members: [
    {member, presentation: own, metadata: {state: 'available', name: 'Own', avatarState: 'unavailable'}},
    {member: {...member, memberId: 'other'}, presentation: {...own, memberId: 'other'}, metadata: {state: 'available', name: 'Other', avatarState: 'unavailable'}},
  ]}));
  await f.controller.refresh(); f.server.send.mockResolvedValueOnce({kind: 'uncertain'}); await f.controller.submit(commands[3]);
  f.entropy.requestKey.mockReturnValue('other-key'); await f.controller.submit({...commands[3], memberId: 'other'});
  expect(f.server.send).toHaveBeenCalledTimes(2);
});
test.each(['authentication_required','forbidden','invalid_input','conflict','unavailable','invalid_response'] as const)(
  'HADW-05: known %s rejection is never retried or rebased', async reason => {
    const f = fixture(); await f.controller.refresh(); f.server.send.mockResolvedValueOnce({kind: 'rejected', reason, correlationId: 'cor-safe'});
    await f.controller.submit(commands[4]); expect(f.controller.view.outcome).toEqual({kind: 'rejected', reason, correlationId: 'cor-safe'});
    expect(f.server.send).toHaveBeenCalledTimes(1); expect(f.server.original).not.toHaveBeenCalled();
    if (reason === 'forbidden' || reason === 'authentication_required') expect(f.controller.view.preferences).toBeNull();
    else expect(f.controller.view.journal?.records[0].stage).toBe('rejected');
  });
test('C69: an unexpected lost POST response stays uncertain without leaking its error', async () => {
  const f = fixture(); await f.controller.refresh(); f.server.send.mockRejectedValueOnce(new Error('private-response'));
  await f.controller.submit(commands[4]); await f.controller.refresh();
  expect(f.controller.view.outcome).toEqual({kind: 'uncertain'}); expect(f.server.send).toHaveBeenCalledTimes(1);
  expect(JSON.stringify(f.controller.view)).not.toContain('private-response'); expect(f.server.original).not.toHaveBeenCalled();
});
test.each([0,2,4])('HADW-01/02: unbound mutation result %s is uncertain, never a confirmed original', async index => {
  const f = fixture(); await f.controller.refresh(); const original = receipt(commands[index]);
  f.server.send.mockResolvedValueOnce({...original, result: index === 4 ? {...preferences, memberId: 'foreign', revision: revisionValue('14')}
    : {householdId: 'foreign', revision: revisionValue('8')}});
  await f.controller.submit(commands[index]); expect(f.controller.view.notice).toBe('invalid_response');
  expect(f.controller.view.outcome).toEqual({kind: 'uncertain'}); expect(f.controller.view.journal?.records[0].operationId).toBeNull();
});
test('HADW-05: a receipt for a different action is not accepted as a successful submission', async () => {
  const f = fixture(); await f.controller.refresh(); f.server.send.mockResolvedValueOnce(receipt(commands[0]));
  await f.controller.submit(commands[4]); expect(f.controller.view.notice).toBe('invalid_response'); expect(f.controller.view.outcome?.kind).toBe('uncertain');
});
test('C67: persistence failure after a valid effect does not turn the receipt into failure', async () => {
  const f = fixture(); await f.controller.refresh(); f.server.send.mockImplementationOnce(async request => {
    f.storage.setItem.mockImplementation(() => {throw new Error('after-effect');}); return receipt(request.command);
  });
  await f.controller.submit(commands[4]); expect(f.controller.view.outcome?.kind).toBe('receipt');
  expect(f.controller.view.notice).toBe('journal_unavailable'); expect(f.controller.view.journal).toBeNull();
  expect(JSON.parse(f.values.get(ADMINISTRATION_JOURNAL_KEY)!).records[0].stage).toBe('prepared');
});
test('C67: a failed prepare cannot dispatch a mutation', async () => {
  const f = fixture(); await f.controller.refresh(); f.entropy.requestKey.mockImplementation(() => {throw new Error('entropy-private');});
  await f.controller.submit(commands[4]); expect(f.controller.view.notice).toBe('journal_unavailable'); expect(f.server.send).not.toHaveBeenCalled();
});
test('C72: deadline expiry after prepare preserves the original without sending it', async () => {
  const f = fixture(); await f.controller.refresh(); f.entropy.requestKey.mockImplementation(() => {f.setNow(session.expiresAt); return 'deadline-key';});
  await f.controller.submit(commands[4]); expect(f.controller.view.notice).toBe('authentication_required'); expect(f.server.send).not.toHaveBeenCalled();
  expect(JSON.parse(f.values.get(ADMINISTRATION_JOURNAL_KEY)!).records[0].stage).toBe('prepared');
});
test('C72: deadline expiry during POST cannot disclose a late private result', async () => {
  const f = fixture(); await f.controller.refresh(); f.server.send.mockImplementationOnce(async request => {
    f.setNow(session.expiresAt); return receipt(request.command);
  });
  await f.controller.submit(commands[4]); expect(f.controller.view.notice).toBe('authentication_required'); expect(f.controller.view.outcome).toBeNull();
});

test('C69: unknown request keys never make a lookup or a new key', async () => {
  const f = fixture(); await f.controller.refresh(); await f.controller.recover('missing');
  expect(f.controller.view.notice).toBe('request_unavailable'); expect(f.server.original).not.toHaveBeenCalled();
  expect(f.entropy.requestKey).not.toHaveBeenCalled();
});
test('C65: an original that expires during preflight is not looked up', async () => {
  const f = fixture(); f.identity.session.mockReturnValue(read({...session, expiresAt: 10_000_000}));
  await f.controller.refresh(); await f.controller.submit(commands[4]);
  f.identity.session.mockImplementationOnce(() => {f.setNow(3_601_000); return read({...session, expiresAt: 10_000_000});});
  await f.controller.recover('request-original'); expect(f.controller.view.notice).toBe('request_unavailable');
  expect(f.server.original).not.toHaveBeenCalled(); expect(f.server.operation).not.toHaveBeenCalled();
});
test('C20/C67: a changed stored original is not silently adopted during recovery', async () => {
  const f = fixture(); await f.controller.refresh(); await f.controller.submit(commands[4]);
  const raw = JSON.parse(f.values.get(ADMINISTRATION_JOURNAL_KEY)!); raw.records[0].payload.locale = 'es';
  f.values.set(ADMINISTRATION_JOURNAL_KEY, JSON.stringify(raw));
  await f.controller.recover('request-original'); expect(f.controller.view.notice).toBe('request_changed'); expect(f.server.operation).not.toHaveBeenCalled();
});
test('C42: losing original-action permission hides its journal payload and blocks GET disclosure', async () => {
  const f = fixture(); await f.controller.refresh(); await f.controller.submit(commands[4]);
  f.server.authorization.mockReturnValue(read({...access, permissions: ['preferences.read', 'operations.read']}));
  await f.controller.recover('request-original'); expect(f.controller.view.notice).toBe('action_not_allowed');
  expect(f.controller.view.journal?.records).toEqual([]); expect(f.controller.view.outcome).toBeNull(); expect(f.server.operation).not.toHaveBeenCalled();
});
test('C42: operations.read alone cannot recover an original and original authority alone is insufficient', async () => {
  const f = fixture(); await f.controller.refresh(); await f.controller.submit(commands[4]);
  f.server.authorization.mockReturnValue(read({...access, permissions: ['preferences.read', 'preferences.write']}));
  await f.controller.recover('request-original'); expect(f.controller.view.notice).toBe('action_not_allowed'); expect(f.server.operation).not.toHaveBeenCalled();
});
test('C69: a known rejected original cannot be looked up as an uncertain effect', async () => {
  const f = fixture(); await f.controller.refresh(); f.server.send.mockResolvedValueOnce({kind: 'rejected', reason: 'conflict', correlationId: null});
  await f.controller.submit(commands[4]); await f.controller.recover('request-original');
  expect(f.controller.view.notice).toBe('action_not_allowed'); expect(f.server.original).not.toHaveBeenCalled();
});
test.each([new EntryReadError('authentication_required'),new EntryReadError('forbidden'),new EntryReadError('invalid_response'),new Error('private-get-error')])(
  'C42/C69: a failed explicit lookup %j is never converted to a mutation', async error => {
    const f = fixture(); await f.controller.refresh(); f.server.send.mockResolvedValueOnce({kind: 'uncertain'}); await f.controller.submit(commands[4]);
    f.server.original.mockImplementationOnce(() => ({result: Promise.reject(error), cancel: vi.fn()}));
    await f.controller.recover('request-original'); expect(f.server.send).toHaveBeenCalledTimes(1);
    expect(f.controller.view.notice).toBe(error instanceof EntryReadError ? error.code : 'check_unconfirmed');
    expect(JSON.stringify(f.controller.view)).not.toContain('private-get-error');
    if (error instanceof EntryReadError && ['forbidden','authentication_required'].includes(error.code)) expect(f.controller.view.preferences).toBeNull();
  });
test('C72: a retired explicit lookup cannot record a late result', async () => {
  const f = fixture(); await f.controller.refresh(); f.server.send.mockResolvedValueOnce({kind: 'uncertain'}); await f.controller.submit(commands[4]);
  const pending = deferred<AdministrationReceipt>(); f.server.original.mockReturnValueOnce(pending);
  const work = f.controller.recover('request-original'); await settle(); f.controller.close(); pending.resolve(receipt(commands[4])); await work;
  expect(pending.cancel).toHaveBeenCalled(); expect(f.controller.view.phase).toBe('closed'); expect(f.controller.view.outcome).toBeNull();
  expect(JSON.parse(f.values.get(ADMINISTRATION_JOURNAL_KEY)!).records[0].stage).toBe('uncertain');
});
test('C22: a known operation ID cannot be replaced by lookup', async () => {
  const f = fixture(); await f.controller.refresh(); await f.controller.submit(commands[4]);
  f.server.operation.mockReturnValueOnce(read({...receipt(commands[4]), operationId: 'different-op', eventDelivery: 'pending'}));
  await f.controller.recover('request-original'); expect(f.controller.view.notice).toBe('invalid_response');
  expect(f.controller.view.journal?.records[0].operationId).toBe('op-original');
});
test('HADW-02: a private lookup result remains bound to the current member', async () => {
  const f = fixture(); await f.controller.refresh(); f.server.send.mockResolvedValueOnce({kind: 'uncertain'}); await f.controller.submit(commands[4]);
  f.server.original.mockReturnValueOnce(read({...receipt(commands[4]), result: {householdId: 'home', revision: revisionValue('14')}, eventDelivery: 'delivered'}));
  await f.controller.recover('request-original'); expect(f.controller.view.notice).toBe('invalid_response');
  expect(f.controller.view.journal?.records[0].stage).toBe('uncertain');
});
test('HADW-04: original household results require household-shaped facts even when local reads are unavailable', async () => {
  const f = fixture(); await f.controller.refresh(); f.server.send.mockResolvedValueOnce({kind: 'uncertain'}); await f.controller.submit(commands[0]);
  f.server.original.mockReturnValueOnce(read({...receipt(commands[0]), result: {...own, revision: revisionValue('8')}, eventDelivery: 'delivered'}));
  await f.controller.recover('request-original'); expect(f.controller.view.notice).toBe('invalid_response');
});
test('C07/C59: historical lookup remains processing evidence and never recreates the effect or claims notification delivery', async () => {
  const f = fixture(); await f.controller.refresh(); f.server.send.mockResolvedValueOnce({kind: 'uncertain'}); await f.controller.submit(commands[4]);
  f.server.original.mockReturnValueOnce(read({...receipt(commands[4]), stage: 'historical', archivedBy: 'restore-generation', eventDelivery: 'suppressed'}));
  await f.controller.recover('request-original'); expect(f.controller.view.outcome).toMatchObject({kind: 'receipt', stage: 'historical', notificationDelivery: 'unavailable'});
  expect(f.controller.view.journal?.records[0].stage).toBe('historical'); expect(f.server.send).toHaveBeenCalledTimes(1);
});
test('C68: a prepared/uncertain request cannot be dismissed as resolved', async () => {
  const f = fixture(); await f.controller.refresh(); f.server.send.mockResolvedValueOnce({kind: 'uncertain'}); await f.controller.submit(commands[4]);
  await f.controller.dismiss('request-original'); expect(f.controller.view.notice).toBe('previous_request_unresolved'); expect(f.controller.view.journal?.records).toHaveLength(1);
});
test('C68: a prepared record restored after reload remains unresolved', async () => {
  const f = fixture(); f.journal.open(context,1000); f.journal.prepare('prepared', commands[4],1000); await f.controller.refresh();
  await f.controller.dismiss('prepared'); expect(f.controller.view.notice).toBe('previous_request_unresolved'); expect(f.server.send).not.toHaveBeenCalled();
});
test('HADW-05: dismissing a resolved request removes only that original and its active receipt', async () => {
  const f = fixture(); f.values.set('unrelated-host-key','retained'); await f.controller.refresh(); await f.controller.submit(commands[4]);
  await f.controller.dismiss('request-original'); expect(f.controller.view.journal?.records).toEqual([]); expect(f.controller.view.outcome).toBeNull();
  expect(f.values.get('unrelated-host-key')).toBe('retained'); expect(f.storage.removeItem).not.toHaveBeenCalled(); expect(f.server.send).toHaveBeenCalledTimes(1);
});
test('HADW-05: dismissing another resolved request preserves the current receipt', async () => {
  const f = fixture(); await f.controller.refresh(); await f.controller.submit(commands[4]); f.entropy.requestKey.mockReturnValue('second');
  await f.controller.submit(commands[0]); await f.controller.dismiss('request-original');
  expect(f.controller.view.outcome).toEqual(receipt(commands[0])); expect(f.controller.view.journal?.records.map(r => r.key)).toEqual(['second']);
});
test('C67: failed dismissal does not silently erase original processing evidence', async () => {
  const f = fixture(); await f.controller.refresh(); await f.controller.submit(commands[4]);
  vi.spyOn(f.journal,'forget').mockImplementationOnce(() => {throw new Error('unavailable');});
  await f.controller.dismiss('request-original'); expect(f.controller.view.notice).toBe('journal_unavailable');
  expect(JSON.parse(f.values.get(ADMINISTRATION_JOURNAL_KEY)!).records).toHaveLength(1);
});
test('C65: one-hour expiry removes only the expired view and never extends retention', async () => {
  const f = fixture(); f.identity.session.mockReturnValue(read({...session, expiresAt: 10_000_000}));
  await f.controller.refresh(); await f.controller.submit(commands[4]); f.setNow(3_601_000); f.controller.tick();
  expect(f.controller.view.outcome).toBeNull(); expect(f.controller.view.journal?.records).toEqual([]);
});
test('C65: a backward monotonic clock retires private state instead of extending retention', async () => {
  const f = fixture(); f.setNow(2000); await f.controller.refresh(); f.setNow(1500); f.controller.tick();
  expect(f.controller.view.notice).toBe('authentication_required'); expect(f.controller.view.preferences).toBeNull();
});
test('HADW-05: a failing tick clock retires the view without renewing the session', async () => {
  const f = fixture(); await f.controller.refresh(); f.clock.now.mockImplementation(() => {throw new Error('clock-private');}); f.controller.tick();
  expect(f.controller.view.notice).toBe('authentication_required'); expect(f.identity.session).toHaveBeenCalledTimes(1);
});
test('C72: close is terminal for reads, commands, recovery and dismissal', async () => {
  const f = fixture(); await f.controller.refresh(); f.controller.close(); f.controller.tick();
  await f.controller.refresh(); await f.controller.submit(commands[4]); await f.controller.recover('request-original'); await f.controller.dismiss('request-original');
  expect(f.identity.session).toHaveBeenCalledTimes(1); expect(f.server.send).not.toHaveBeenCalled(); expect(f.controller.view.phase).toBe('closed');
});
test('HADW-05: idle commands cannot select an identity or open storage', async () => {
  const f = fixture(); await f.controller.submit(commands[4]); expect(f.identity.session).not.toHaveBeenCalled(); expect(f.storage.getItem).not.toHaveBeenCalled();
});

test('C72: a lifecycle retirement during failed preparation cannot reopen the controller', async () => {
  const f = fixture(); await f.controller.refresh(); f.entropy.requestKey.mockImplementation(() => {f.controller.close(); throw new Error('retired');});
  await f.controller.submit(commands[4]); expect(f.controller.view.phase).toBe('closed'); expect(f.controller.view.notice).toBeNull(); expect(f.server.send).not.toHaveBeenCalled();
});

test.each([0,2])('HADW-05: a foreign household receipt %s is rejected when aggregate facts are unavailable', async index => {
  const f = fixture(); await f.controller.refresh(); f.server.send.mockResolvedValueOnce({kind: 'uncertain'}); await f.controller.submit(commands[index]);
  f.server.household.mockImplementation(() => {throw new Error('current-household-unavailable');});
  f.server.policy.mockImplementation(() => {throw new Error('current-policy-unavailable');});
  f.server.original.mockReturnValueOnce(read({...receipt(commands[index]), result: {householdId: 'foreign', revision: revisionValue('8')}, eventDelivery: 'delivered'}));
  await f.controller.recover('request-original'); expect(f.controller.view.notice).toBe('invalid_response');
  expect(f.controller.view.journal?.records[0].stage).toBe('uncertain'); expect(f.server.send).toHaveBeenCalledTimes(1);
});

test('HADW-05: current household facts must match independently verified routing scope', async () => {
  const f = fixture(); f.server.household.mockReturnValue(read({...home, householdId: 'foreign'}));
  await f.controller.refresh(); expect(f.controller.view.household).toBeNull(); expect(f.controller.view.errors.household).toBe('invalid_response');
});
test('HADW-05: original household recovery survives reload without any aggregate-read permission', async () => {
  const f = fixture({...access, permissions: ['household.manage','operations.read']});
  f.journal.open(context,1000);f.journal.prepare('prior-original',commands[0],1000);
  f.journal.record('prior-original',{stage:'committed',operationId:'op-original'},1000);f.journal.detach();
  await f.controller.refresh();await f.controller.recover('prior-original');
  expect(f.server.household).not.toHaveBeenCalled();expect(f.server.operation).toHaveBeenCalledTimes(1);
  expect(f.controller.view.outcome).toEqual({...receipt(commands[0]),eventDelivery:'pending'});expect(f.server.send).not.toHaveBeenCalled();
});

test.each([false,true])('C74/C82: verified read-only grace supports explicit original GET recovery with known ID %s', async known => {
  const f = fixture(); await f.controller.refresh(); if (!known) f.server.send.mockResolvedValueOnce({kind:'uncertain'});
  await f.controller.submit(commands[4]);f.identity.session.mockReturnValue(read({...session,access:'read_only'}));
  await f.controller.refresh();await f.controller.recover('request-original');
  expect(known?f.server.operation:f.server.original).toHaveBeenCalledTimes(1);expect(f.controller.view.outcome?.kind).toBe('receipt');
  await f.controller.submit(commands[0]);expect(f.server.send).toHaveBeenCalledTimes(1);expect(f.entropy.requestKey).toHaveBeenCalledTimes(1);
  f.setNow(session.expiresAt);f.controller.tick();expect(f.controller.view.outcome).toBeNull();expect(f.controller.view.preferences).toBeNull();
});

test('HADB-01/C13: reconciliation preserves an invalid draft notice while replacing all current private facts', async () => {
  const f = fixture(); await f.controller.refresh(); await f.controller.submit(null);
  f.server.preferences.mockReturnValue(read({...preferences, locale: 'en', revision: revisionValue('14')}));
  await f.controller.reconcile();
  expect(f.controller.view.notice).toBe('invalid_input');
  expect(f.controller.view.preferences).toMatchObject({locale: 'en', revision: '14'});
  expect(f.server.send).not.toHaveBeenCalled(); expect(f.server.original).not.toHaveBeenCalled();
  expect(f.server.operation).not.toHaveBeenCalled(); expect(f.entropy.requestKey).not.toHaveBeenCalled();
});
test('HADB-01/C13: reconciliation replaces a prior notice with the current membership transition', async () => {
  const f = fixture(); await f.controller.refresh(); await f.controller.submit(null);
  f.server.authorization.mockReturnValue(read({...access, member: {...member, memberId: 'relinked'}}));
  f.server.preferences.mockReturnValue(read({...preferences, memberId: 'relinked'}));
  await f.controller.reconcile();
  expect(f.controller.view.notice).toBe('access_changed'); expect(f.controller.view.preferences?.memberId).toBe('relinked');
  expect(f.server.send).not.toHaveBeenCalled();
});
test('HADB-01/C02: reconciliation reports a new verified context rather than an earlier invalid draft', async () => {
  const f = fixture(); await f.controller.refresh(); await f.controller.submit(null);
  f.identity.session.mockReturnValue(read({...session, context: {...context, channel: 'stable'}}));
  await f.controller.reconcile();
  expect(f.controller.view.notice).toBe('context_changed'); expect(f.controller.view.session?.context.channel).toBe('stable');
  expect(f.server.send).not.toHaveBeenCalled();
});
test.each(['read_only', 'journal_unavailable', 'inactive', 'api_unavailable', 'access_changed'] as const)(
  'HADB-01/C03: fresh %s proof takes precedence over the earlier action notice', async kind => {
    const f = fixture(); await f.controller.refresh(); await f.controller.submit(null);
    if (kind === 'read_only') f.identity.session.mockReturnValue(read({...session, access: 'read_only'}));
    if (kind === 'journal_unavailable') f.storage.getItem.mockImplementation(() => {throw new Error('private-storage');});
    if (kind === 'inactive') f.server.authorization.mockReturnValue(read({...access, state: 'suspended'}));
    if (kind === 'api_unavailable') f.identity.session.mockReturnValue(read({...session, householdApiAvailable: false}));
    if (kind === 'access_changed') f.server.authorization.mockReturnValueOnce(read(access))
      .mockReturnValueOnce(read({...access, policyRevision: revisionValue('6')}));
    await f.controller.reconcile(); expect(f.controller.view.notice).toBe(kind); expect(f.server.send).not.toHaveBeenCalled();
  },
);
test('HADB-01/C04: failed fresh proof retires earlier private facts and action notices', async () => {
  const f = fixture(); await f.controller.refresh(); await f.controller.submit(null);
  f.identity.session.mockReturnValue(read(null)); await f.controller.reconcile();
  expect(f.controller.view.notice).toBe('authentication_required'); expect(f.controller.view.preferences).toBeNull();
});
test('HADB-01/C07: reconciliation cannot republish facts after disposal while its read is pending', async () => {
  const f = fixture(); await f.controller.refresh(); const pending = deferred<VerifiedEntrySession | null>();
  f.identity.session.mockReturnValueOnce(pending); const work = f.controller.reconcile();
  f.controller.close(); pending.resolve(session); await work;
  expect(pending.cancel).toHaveBeenCalledOnce(); expect(f.controller.view.phase).toBe('closed');
  expect(f.controller.view.preferences).toBeNull();
});
test('HADB-01/C04: expiry during reconciliation cannot restore the previous notice or private facts', async () => {
  const f = fixture(); await f.controller.refresh(); await f.controller.submit(null);
  const pending = deferred<typeof preferences>(); f.server.preferences.mockReturnValueOnce(pending);
  const work = f.controller.reconcile(); await settle(); f.setNow(session.expiresAt); f.controller.tick();
  pending.resolve(preferences); await work;
  expect(f.controller.view.notice).toBe('authentication_required'); expect(f.controller.view.preferences).toBeNull();
});
test('HADB-01/C05: reconciliation is passive while idle, closed or a command is pending', async () => {
  const f = fixture(); await f.controller.reconcile(); expect(f.identity.session).not.toHaveBeenCalled();
  await f.controller.refresh(); const pending = deferred<AdministrationCommandResult>(); f.server.send.mockReturnValueOnce(pending.result);
  const work = f.controller.submit(commands[4]); await settle(); const calls = f.identity.session.mock.calls.length;
  await f.controller.reconcile(); expect(f.identity.session).toHaveBeenCalledTimes(calls);
  pending.resolve(receipt(commands[4])); await work; f.controller.close();
  await f.controller.reconcile(); expect(f.controller.view.phase).toBe('closed');
});
test('HADB-01/C02: same-context empty rejection survives reconciliation without another read or original lookup', async () => {
  const f = fixture(); await f.controller.refresh();
  f.server.send.mockResolvedValueOnce({kind: 'rejected', reason: 'forbidden', correlationId: 'current-correlation'});
  await f.controller.submit(commands[4]); const calls = f.identity.session.mock.calls.length;
  await f.controller.reconcile(); expect(f.identity.session).toHaveBeenCalledTimes(calls);
  expect(f.controller.view.outcome).toEqual({kind: 'rejected', reason: 'forbidden', correlationId: 'current-correlation'});
  expect(f.server.original).not.toHaveBeenCalled(); expect(f.server.operation).not.toHaveBeenCalled();
});
test('HADB-01: reconciliation without an action notice remains a current neutral read', async () => {
  const f = fixture(); await f.controller.refresh(); await f.controller.reconcile();
  expect(f.controller.view.notice).toBeNull(); expect(f.controller.view.preferences).toEqual(preferences);
});

test.each(['without_roster_grant', 'unavailable_roster'] as const)(
  'HADW-01: independent own alias %s keeps its exact revision and permits one explicit edit', async kind => {
    const f = fixture(kind === 'without_roster_grant' ? {...access, permissions: ['preferences.read', 'preferences.write']} : access);
    if (kind === 'unavailable_roster') f.server.roster.mockImplementation(() => {throw new EntryReadError('unavailable');});
    await f.controller.refresh(); expect(f.controller.view.roster).toBeNull(); expect(f.controller.view.presentation).toEqual(own);
    expect(f.server.presentation).toHaveBeenCalledExactlyOnceWith(member.memberId, context);
    await f.controller.submit(commands[3]); expect(f.server.send).toHaveBeenCalledExactlyOnceWith({key: 'request-original', command: commands[3]}, context);
    expect(f.controller.view.outcome?.kind).toBe('receipt'); expect(f.server.original).not.toHaveBeenCalled();
  },
);
test('HADW-01: an independently returned alias for a former member is never published or used for an own edit', async () => {
  const f = fixture({...access, permissions: ['preferences.read','preferences.write']});
  f.server.presentation.mockReturnValue(read({...own, memberId: 'former-member'}));
  await f.controller.refresh(); expect(f.controller.view.presentation).toBeNull();
  expect(f.controller.view.errors.presentation).toBe('invalid_response');
  await f.controller.submit(commands[3]); expect(f.server.send).not.toHaveBeenCalled();
  expect(JSON.stringify(f.controller.view)).not.toContain('former-member');
});
test('HADW-01: lack of either public or own read authority never queries or invents an alias revision', async () => {
  const f = fixture({...access, permissions: ['preferences.write']}); await f.controller.refresh();
  expect(f.controller.view.presentation).toBeNull(); expect(f.server.presentation).not.toHaveBeenCalled();
  await f.controller.submit(commands[3]); expect(f.controller.view.notice).toBe('action_not_allowed'); expect(f.server.send).not.toHaveBeenCalled();
});
test('HADW-01: a permitted current roster remains an honest alias source when the independent own read is unavailable', async () => {
  const f = fixture(); f.server.presentation.mockImplementation(() => {throw new EntryReadError('unavailable');});
  await f.controller.refresh(); expect(f.controller.view.presentation).toBeNull(); expect(f.controller.view.errors.presentation).toBe('unavailable');
  await f.controller.submit(commands[3]); expect(f.server.send).toHaveBeenCalledOnce(); expect(f.controller.view.outcome?.kind).toBe('receipt');
});

const noControls = {household: false, policy: false, preferences: false, ownAlias: false,
  memberIds: [], aliasMemberIds: [], recoverableKeys: [], dismissibleKeys: []};
test('HADB-03: idle and disposed views offer no administration controls and obtain no proof', async () => {
  const f = fixture(); expect(f.controller.view.controls).toEqual(noControls);
  f.controller.close(); expect(f.controller.view.controls).toEqual(noControls);
  expect(f.identity.session).not.toHaveBeenCalled(); expect(f.storage.getItem).not.toHaveBeenCalled();
});
test('HADB-03: controls describe current permitted facts without producing a command key, lookup or private payload', async () => {
  const f = fixture(); await f.controller.refresh(); const writes = f.storage.setItem.mock.calls.length;
  const controls = f.controller.view.controls;
  expect(controls).toEqual({...noControls, household: true, policy: true, preferences: true, ownAlias: true, memberIds: [member.memberId]});
  expect(Object.isFrozen(controls)).toBe(true); expect(Object.isFrozen(controls.memberIds)).toBe(true);
  expect(Object.isFrozen(controls.aliasMemberIds)).toBe(true); expect(Object.isFrozen(controls.recoverableKeys)).toBe(true);
  expect(Object.isFrozen(controls.dismissibleKeys)).toBe(true);
  expect(JSON.stringify(controls)).not.toContain('locale'); expect(JSON.stringify(controls)).not.toContain('routine_participation');
  expect(f.storage.setItem).toHaveBeenCalledTimes(writes); expect(f.entropy.requestKey).not.toHaveBeenCalled();
  expect(f.server.original).not.toHaveBeenCalled(); expect(f.server.send).not.toHaveBeenCalled();
});
test('HADB-03: other-member controls require current facts and never invent masked exceptions', async () => {
  const f = fixture(); f.server.roster.mockReturnValue(read({directoryState: 'available', members: [
    {member, presentation: own, metadata: {state: 'available', name: 'Owner', avatarState: 'unavailable'}},
    {member: {...member, memberId: 'other', exceptions: null}, presentation: {...own, memberId: 'other'},
      metadata: {state: 'denied', name: null, avatarState: 'unavailable'}},
  ]}));
  await f.controller.refresh(); expect(f.controller.view.controls.memberIds).toEqual([member.memberId]);
  expect(f.controller.view.controls.aliasMemberIds).toEqual(['other']);
});
test('HADB-03: ordinary current owner controls expose own edits without exposing other-member management', async () => {
  const f = fixture({...access, permissions: ['members.read','preferences.read','preferences.write']});
  await f.controller.refresh(); expect(f.controller.view.controls).toEqual({...noControls, ownAlias: true, preferences: true});
});
test('HADB-03: write grants without current aggregate reads do not invent an edit revision, while original GET remains usable', async () => {
  const f = fixture({...access, permissions: ['household.manage','operations.read']});
  f.journal.open(context,1000); f.journal.prepare('original',commands[0],1000); f.journal.detach();
  await f.controller.refresh(); expect(f.controller.view.controls).toEqual({...noControls, recoverableKeys: ['original']});
  expect(f.server.original).not.toHaveBeenCalled(); await f.controller.recover('original');
  expect(f.server.original).toHaveBeenCalledOnce(); expect(f.controller.view.controls.dismissibleKeys).toEqual(['original']);
});
test('HADB-03: a valid read-only lease offers original recovery and resolved dismissal, with all new edits unavailable', async () => {
  const f = fixture(); f.journal.open(context,1000); f.journal.prepare('saved',commands[4],1000);
  f.journal.record('saved',{stage:'committed',operationId:'operation'},1000); f.journal.detach();
  f.identity.session.mockReturnValue(read({...session,access:'read_only'})); await f.controller.refresh();
  expect(f.controller.view.controls).toEqual({...noControls,recoverableKeys:['saved'],dismissibleKeys:['saved']});
  expect(f.server.original).not.toHaveBeenCalled(); expect(f.server.send).not.toHaveBeenCalled();
});
test('HADB-03: original stages expose only their permitted recovery and dismissal controls', async () => {
  const f = fixture(); f.journal.open(context,1000);
  for (const stage of ['prepared','uncertain','committed','historical','rejected'] as const) {
    f.journal.prepare(stage,commands[4],1000);
    if (stage !== 'prepared') f.journal.record(stage,{stage,operationId:stage==='committed'||stage==='historical'?'operation-'+stage:null},1000);
  }
  f.journal.detach(); await f.controller.refresh();
  expect(f.controller.view.controls.recoverableKeys).toEqual(['prepared','uncertain','committed','historical']);
  expect(f.controller.view.controls.dismissibleKeys).toEqual(['committed','historical','rejected']);
  f.server.authorization.mockReturnValue(read({...access,permissions:access.permissions.filter(value=>value!=='operations.read')}));
  await f.controller.refresh(); expect(f.controller.view.controls.recoverableKeys).toEqual([]);
  expect(f.controller.view.controls.dismissibleKeys).toEqual(['committed','historical','rejected']);
});
test('HADB-03: unavailable owned journal disables controls while current permitted facts remain readable', async () => {
  const f = fixture(); f.storage.getItem.mockImplementation(()=>{throw new Error('private-storage-fault');});
  await f.controller.refresh(); expect(f.controller.view.preferences).toEqual(preferences);
  expect(f.controller.view.controls).toEqual(noControls);
});
test('HADB-03: pending proof and an in-flight atomic change offer no stale form controls', async () => {
  const f = fixture(), proof = deferred<VerifiedEntrySession|null>(); f.identity.session.mockReturnValueOnce(proof);
  const opening = f.controller.refresh(); expect(f.controller.view.controls).toEqual(noControls);
  proof.resolve(session); await opening; const pending = deferred<AdministrationCommandResult>(); f.server.send.mockReturnValueOnce(pending.result);
  const work = f.controller.submit(commands[4]); await settle(); expect(f.controller.view.controls).toEqual(noControls);
  pending.resolve(receipt(commands[4])); await work; expect(f.controller.view.controls.preferences).toBe(true);
});
test('HADB-03: an unresolved original disables only its aggregate and leaves independent forms available', async () => {
  const f = fixture(); await f.controller.refresh(); f.server.send.mockResolvedValueOnce({kind:'uncertain'});
  await f.controller.submit(commands[4]); const controls = f.controller.view.controls;
  expect(controls.preferences).toBe(false); expect(controls.household).toBe(true); expect(controls.ownAlias).toBe(true);
  expect(controls.recoverableKeys).toEqual(['request-original']); expect(f.server.send).toHaveBeenCalledOnce();
});
test('HADB-03: an unresolved own alias does not disable an authorized different-member alias form', async () => {
  const f = fixture(); f.server.roster.mockReturnValue(read({directoryState:'available',members:[
    {member,presentation:own,metadata:{state:'available',name:'Owner',avatarState:'unavailable'}},
    {member:{...member,memberId:'other'},presentation:{...own,memberId:'other'},metadata:{state:'available',name:'Other',avatarState:'unavailable'}},
  ]}));
  await f.controller.refresh(); f.server.send.mockResolvedValueOnce({kind:'uncertain'}); await f.controller.submit(commands[3]);
  expect(f.controller.view.controls.ownAlias).toBe(false); expect(f.controller.view.controls.aliasMemberIds).toEqual(['other']);
  expect(f.controller.view.controls.preferences).toBe(true);
});
test.each([0,2,4])('household-browser-C13: a captured new intent %s cannot cross a same-HA membership replacement with a coincident revision',async index=>{
  const f=fixture();await f.controller.refresh();const next={...member,memberId:'replacement'};
  f.server.authorization.mockReturnValue(read({...access,member:next}));
  f.server.preferences.mockReturnValue(read({...preferences,memberId:next.memberId}));
  f.server.presentation.mockReturnValue(read({...own,memberId:next.memberId}));
  f.server.roster.mockReturnValue(read({directoryState:'available',members:[{member:next,presentation:{...own,memberId:next.memberId},
    metadata:{state:'available',name:'Current member',avatarState:'unavailable'}}]}));
  await f.controller.submit(commands[index]);expect(f.server.send).not.toHaveBeenCalled();expect(f.entropy.requestKey).not.toHaveBeenCalled();
  expect(f.controller.view.notice).toBe('context_changed');expect(f.controller.view.preferences?.memberId).toBe(next.memberId);
});
test('HADB-03: a newer access revision for the same member still permits a currently authorized captured intent',async()=>{
  const f=fixture();await f.controller.refresh();f.server.authorization.mockReturnValue(read({...access,policyRevision:revisionValue('6'),member:{...member,revision:revisionValue('4')}}));
  await f.controller.submit(commands[4]);expect(f.server.send).toHaveBeenCalledOnce();expect(f.controller.view.outcome?.kind).toBe('receipt');
});
