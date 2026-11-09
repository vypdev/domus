import {afterEach, expect, test, vi} from 'vitest';
import {HttpAdministrationServer} from '../src/adapters/administration-http';
import {administrationJSON, responseRevision, ROSTER_MAX_BYTES} from '../src/adapters/json-values';
import {administrationCommandBody} from '../src/adapters/administration-json';
import {household} from '../src/adapters/http-values';
import {BoundedHTTP, HTTP_TIMEOUT_MS} from '../src/adapters/http-transport';
import {administrationCommand} from '../src/domain/administration-commands';
import type {JournalContext} from '../src/domain/journal';

const context: JournalContext = {installationId: '01234567-89ab-cdef-0123-456789abcdef', channel: 'edge', subject: 'a'.repeat(32)};
const REV = '9007199254740993', NEXT = '9007199254740994';
const encode = (value: unknown) => JSON.stringify(value).replaceAll('"$revision"', REV).replaceAll('"$next"', NEXT);
const commands = [
  {action: 'household.update', payload: {expected_revision: REV, name: 'Home', time_zone: 'UTC'}},
  {action: 'member.update', memberId: 'member-1', payload: {expected_revision: REV, role: 'adult', status: 'active', exceptions: []}},
  {action: 'policy.update', payload: {expected_revision: REV, mapping_mode: 'all_ha_administrators', target_ha_user_id: null, adjustments: []}},
  {action: 'member.presentation.update', memberId: 'member-1', payload: {expected_revision: REV, alias: '  Literal  '}},
  {action: 'member.preferences.update', payload: {expected_revision: REV, locale: 'es', routine_participation_summaries: false}},
];
const paths = ['household', 'members/member-1', 'policy', 'administration/members/member-1/presentation', 'administration/preferences'];
const member = () => ({member_id: 'member-1', role: 'viewer', status: 'active', revision: '$revision', ha_user_id: context.subject, exceptions: [] as {permission: string; allow: boolean}[]});
const presentation = () => ({member_id: 'member-1', alias: null as string | null, revision: '$revision'});
const preferences = () => ({member_id: 'member-1', locale: 'es', routine_participation_summaries: false, revision: '$revision', notification_delivery: 'unavailable'});
const policy = () => ({household_id: 'home', mapping: {mode: 'all_ha_administrators', target_ha_user_id: null}, revision: '$revision', adjustments: []});
const capabilities = () => ({state: 'available', contract_version: 2, household_id: 'home', exact_revisions: 'json-integer-int64', actions: commands.map(c => c.action),
  journal: {namespace: 'administration', version: 1, maximum_records: 8, maximum_bytes: 65536, lifetime_ms: 3600000}});
const access = () => ({state: 'active', setup_allowed: false, enrollment_allowed: false, member: member(), policy_revision: '$revision', effective_role: 'administrator',
  permission_scope: 'household_administration', permissions: ['household.read', 'members.read', 'policy.manage'], message: 'Current access.', action_required: 'Review.'});
const roster = () => ({members: [{member: member(), presentation: presentation(), metadata: {state: 'available', name: '<b>HA name</b>', avatar_state: 'unavailable'}}], directory_state: 'available'});
const results = [
  {household_id: 'home', revision: '$next'}, {member_id: 'member-1', role: 'adult', status: 'active', revision: '$next'},
  {household_id: 'home', revision: '$next', mapping_mode: 'all_ha_administrators'},
  {member_id: 'member-1', alias: 'Literal', revision: '$next'},
  {member_id: 'member-1', locale: 'es', routine_participation_summaries: false, revision: '$next', notification_delivery: 'unavailable'},
];
function receipt(index: number, lookup = false) {
  return {state: 'committed', archived_by: null, operation_id: 'op-1', created_at: 1000, result: results[index], message: 'Saved.', action_required: 'Review current state.',
    ...(index >= 3 || lookup ? {notification_delivery: 'unavailable'} : {}),
    ...(lookup ? {action: commands[index].action, command_key: 'original-key', event_delivery: 'pending'} : {})};
}
function fixture(mode: 'native' | 'standalone' = 'standalone') {
  const target = {deployment: mode, applicationBase: mode === 'native' ? '/api/hassio_ingress/' + 'b'.repeat(43) + '/' : '/', origin: 'https://domus.example'};
  const transport = vi.fn(async (_path: string, _init: RequestInit) => new Response('{}'));
  const network = async (path: string, init: RequestInit) => {
    const reply = await transport(path, init);
    if (!reply.url) Object.defineProperty(reply, 'url', {value: target.origin + path}); return reply;
  };
  return {target, transport, network, server: new HttpAdministrationServer(target, network)};
}
function reply(value: unknown, status = 200) {return new Response(encode(value), {status, headers: {'Content-Type': 'application/json', 'Cache-Control': 'no-store'}});}
const blocked = (status: number) => reply({state: 'blocked', code: 'request_forbidden', message: 'Private detail.', action_required: 'Review.', correlation_id: 'cor_safe'}, status);
afterEach(() => vi.useRealTimers());

for (const mode of ['native', 'standalone'] as const) {
  test(`${mode}: reads project exact values, stored/effective role provenance and honest metadata`, async () => {
    const f = fixture(mode);
    const wires = [capabilities(), access(), {household_id: 'home', name: 'Home', time_zone: 'UTC', revision: '$revision'}, policy(), roster(),
      {state: 'available', profiles: [{ha_user_id: context.subject, name: null}]}, presentation(), preferences()];
    for (const data of wires) f.transport.mockResolvedValueOnce(reply(data));
    expect(await f.server.capabilities(context).result).toMatchObject({contractVersion: 2, householdId: 'home', actions: commands.map(c => c.action)});
    const authority = await f.server.authorization(context).result;
    expect(authority).toMatchObject({member: {memberId: 'member-1', role: 'viewer', revision: REV}, effectiveRole: 'administrator', policyRevision: REV});
    expect((await f.server.household(context).result).revision).toBe(REV);
    expect((await f.server.policy(context).result).revision).toBe(REV);
    expect((await f.server.roster(context).result).members[0]).toMatchObject({member: {revision: REV}, metadata: {state: 'available', name: '<b>HA name</b>'}});
    expect((await f.server.directory(context).result).profiles).toEqual([{haUserId: context.subject, name: null}]);
    expect((await f.server.presentation('member-1', context).result).revision).toBe(REV);
    expect(await f.server.preferences(context).result).toMatchObject({memberId: 'member-1', locale: 'es', revision: REV, notificationDelivery: 'unavailable'});
    for (const [path, init] of f.transport.mock.calls) {
      expect(path.startsWith(f.target.applicationBase + 'api/v1/')).toBe(true);
      expect(init.method).toBe('GET'); expect(new Headers(init.headers).has('X-CSRF-Token')).toBe(false);
    }
  });
  test.each(commands)(`${mode}: $action sends the exact original once and recovers with a GET`, async raw => {
    const index = commands.indexOf(raw), command = administrationCommand(raw), f = fixture(mode), input = {key: 'original-key', command};
    f.transport.mockResolvedValueOnce(reply({csrf_token: 'c'.repeat(64)})).mockResolvedValueOnce(reply(receipt(index))).mockResolvedValueOnce(reply(receipt(index, true)));
    const saved = await f.server.send(input, context);
    expect(saved).toMatchObject({kind: 'receipt', action: command.action, operationId: 'op-1', result: {revision: NEXT}, notificationDelivery: 'unavailable'});
    const [path, init] = f.transport.mock.calls[1];
    expect(path).toBe(f.target.applicationBase + 'api/v1/' + paths[index]); expect(init.method).toBe('PUT');
    const body = administrationJSON(init.body) as Record<string, unknown>;
    expect(responseRevision(body.expected_revision)).toBe(REV);
    if (index === 3) expect(body.alias).toBe('  Literal  ');
    expect(new Headers(init.headers).get('Idempotency-Key')).toBe('original-key');
    expect(new Headers(init.headers).get('X-CSRF-Token')).toBe('c'.repeat(64));
    expect(await f.server.original({...input, operationId: 'op-1'}, context).result).toMatchObject({kind: 'receipt', eventDelivery: 'pending'});
    expect(f.transport.mock.calls[2][0]).toBe(f.target.applicationBase + 'api/v1/administration/requests/' + command.action + '/original-key');
    expect(f.transport.mock.calls[2][1].method).toBe('GET'); expect(f.transport).toHaveBeenCalledTimes(3);
  });
}

test('the roster budget accepts all 256 valid maximal UTF-8 labels without using or changing the 64 KiB journal budget', async () => {
  const f = fixture(), data = roster();
  const ordinary = ['household.read','members.read','preferences.read','preferences.write','operations.read','tasks.read','tasks.claim','tasks.manage',
    'tasks.record_for_others','tasks.material_use','tasks.create','tasks.complete','tasks.approve','shopping.request','shopping.manage','inventory.manage'];
  data.members = Array.from({length: 256}, (_v, index) => {
    const id = 'm' + String(index).padStart(127, '0');
    return {member: {...member(), member_id: id, ha_user_id: index === 0 ? context.subject : index.toString(16).padStart(32, '0'), exceptions: ordinary.map(permission => ({permission, allow: true}))},
      presentation: {member_id: id, alias: '😀'.repeat(80), revision: '$revision'}, metadata: {state: 'available', name: '😀'.repeat(256), avatar_state: 'unavailable'}};
  });
  const bytes = new TextEncoder().encode(encode(data)).byteLength;
  expect(bytes).toBeGreaterThan(65536); expect(bytes).toBeLessThan(ROSTER_MAX_BYTES);
  f.transport.mockResolvedValueOnce(reply(data));
  expect((await f.server.roster(context).result).members).toHaveLength(256);
});

test.each([401,403,409,422,503])('known mutation rejection %s keeps only its safe reason/correlation', async status => {
  const f = fixture(); f.transport.mockResolvedValueOnce(reply({csrf_token: 'c'.repeat(64)})).mockResolvedValueOnce(blocked(status));
  const result = await f.server.send({key: 'key', command: administrationCommand(commands[4])}, context);
  expect(result).toMatchObject({kind: 'rejected', correlationId: 'cor_safe'}); expect(JSON.stringify(result)).not.toContain('Private detail');
});

test.each(['lost', 'malformed', 'mismatched_revision', 'mismatched_owner', 'unexpected_status'])(
  'a %s mutation response never triggers an automatic resend', async failure => {
    const f = fixture(); f.transport.mockResolvedValueOnce(reply({csrf_token: 'c'.repeat(64)}));
    if (failure === 'lost') f.transport.mockRejectedValueOnce(new Error('private error'));
    else f.transport.mockResolvedValueOnce(reply(failure === 'malformed' ? {} : {...receipt(3), result: {...results[3],
      ...(failure === 'mismatched_revision' ? {revision: '$revision'} : {}), ...(failure === 'mismatched_owner' ? {member_id: 'other'} : {})}}, failure === 'unexpected_status' ? 201 : 200));
    expect(await f.server.send({key: 'key', command: administrationCommand(commands[3])}, context)).toEqual({kind: 'uncertain'});
    expect(f.transport).toHaveBeenCalledTimes(2);
  });

test('unsupported decoder/transport budget choices fail before data or a request can be accepted', async () => {
  expect(() => administrationJSON('{}', 0 as never)).toThrow('invalid_response');
  const f = fixture(), network = new BoundedHTTP(f.target, f.network);
  await expect(network.get('session', context, new AbortController().signal, 'unknown' as never)).rejects.toThrow('invalid_response');
  expect(f.transport).not.toHaveBeenCalled();
});

test.each(['absent','denied','unavailable'])('masked roster preserves a truthful %s label without HA linkage or invented data', async state => {
  const f = fixture(); f.transport.mockResolvedValueOnce(reply({directory_state: 'unavailable', members: [{member: {...member(), ha_user_id: null, exceptions: null},
    presentation: presentation(), metadata: {state, name: null, avatar_state: 'unavailable'}}]}));
  expect((await f.server.roster(context).result).members[0]).toMatchObject({member: {haUserId: null, exceptions: null}, metadata: {state, name: null}});
});

test.each(['available','denied','unavailable'])('directory %s with no choices remains distinct from another state', async state => {
  const f = fixture(); f.transport.mockResolvedValueOnce(reply({state, profiles: []}));
  expect(await f.server.directory(context).result).toEqual({state, profiles: []});
});

test('pending and unconfigured authorization preserve actual membership rather than fabricating active grants', async () => {
  const f = fixture();
  f.transport.mockResolvedValueOnce(reply({state: 'unconfigured', setup_allowed: true, enrollment_allowed: false,
    permission_scope: 'household_administration', permissions: [], message: 'Setup.', action_required: 'Review.'}));
  expect(await f.server.authorization(context).result).toMatchObject({member: null, policyRevision: null, effectiveRole: null});
  f.transport.mockResolvedValueOnce(reply({...access(), state: 'pending', member: {...member(), status: 'pending', ha_user_id: null, exceptions: null},
    policy_revision: null, effective_role: null, permissions: []}));
  expect(await f.server.authorization(context).result).toMatchObject({member: {status: 'pending'}, effectiveRole: null});
});

test('targeted policy, ordinary profile decisions and browser-following preferences retain immutable exact facts', async () => {
  const f = fixture();
  f.transport.mockResolvedValueOnce(reply({...policy(), mapping: {mode: 'setup_administrator', target_ha_user_id: context.subject},
    adjustments: [{role: 'adult', permission: 'tasks.complete', allow: false}]}));
  const result = await f.server.policy(context).result;
  expect(result).toMatchObject({targetHAUserId: context.subject, mappingMode: 'setup_administrator'});
  expect(Object.isFrozen(result.adjustments[0])).toBe(true);
  f.transport.mockResolvedValueOnce(reply({...preferences(), locale: null}));
  expect((await f.server.preferences(context).result).locale).toBeNull();
});

type Projection = 'capabilities' | 'authorization' | 'policy' | 'roster' | 'directory' | 'preferences';
const malformed: readonly [Projection, unknown][] = [
  ['capabilities', {...capabilities(), state: 'unsupported'}], ['capabilities', {...capabilities(), contract_version: 3}],
  ['capabilities', {...capabilities(), contract_version: 1}],
  ...[null, 7, '../foreign', ''].map(household_id => ['capabilities', {...capabilities(), household_id}] as [Projection, unknown]),
  ['capabilities', {...capabilities(), exact_revisions: 'float'}], ['capabilities', {...capabilities(), actions: ['household.update']}],
  ['capabilities', {...capabilities(), actions: Array(5).fill('household.update')}], ['capabilities', {...capabilities(), actions: [...commands.slice(0,4).map(c => c.action),'unknown.action']}],
  ...[{namespace: 'entry'}, {version: 2}, {maximum_records: 9}, {maximum_bytes: 65537}, {lifetime_ms: 7200000}].map(change =>
    ['capabilities', {...capabilities(), journal: {...capabilities().journal, ...change}}] as [Projection, unknown]),
  ['roster', {members: {}, directory_state: 'available'}], ['roster', {...roster(), members: Array(257).fill(roster().members[0])}],
  ['roster', {...roster(), members: Array(2).fill(roster().members[0])}],
  ['roster', {directory_state: 'available', members: [roster().members[0], {...roster().members[0], member: {...member(), member_id: 'other'}, presentation: {...presentation(), member_id: 'other'}}]}],
  ['roster', {...roster(), members: [{...roster().members[0], presentation: {...presentation(), member_id: 'other'}}]}],
  ...[{state: 'future'}, {state: 'available', name: null}, {state: 'denied', name: 'Unknown'}, {name: ''}, {name: 'x'.repeat(257)},
    {name: 'bad\nname'}, {name: '\ud800'}, {avatar_state: 'available'}, {avatar_url: 'https://external.invalid/image'}].map(change =>
    ['roster', {...roster(), members: [{...roster().members[0], metadata: {...roster().members[0].metadata, ...change}}]}] as [Projection, unknown]),
  ['policy', {...policy(), mapping: {mode: 'selected_ha_user', target_ha_user_id: null}}],
  ['policy', {...policy(), mapping: {mode: 'all_ha_administrators', target_ha_user_id: context.subject}}],
  ['policy', {...policy(), adjustments: [{role: 'adult', permission: 'policy.manage', allow: true}]}],
  ['policy', {...policy(), adjustments: [{role: 'future', permission: 'tasks.read', allow: true}]}],
  ['policy', {...policy(), adjustments: Array(2).fill({role: 'adult', permission: 'tasks.read', allow: true})}],
  ['directory', {state: 'denied', profiles: [{ha_user_id: context.subject, name: 'Denied'}]}],
  ['directory', {state: 'available', profiles: Array(257).fill({ha_user_id: context.subject, name: 'Overflow'})}],
  ['directory', {state: 'available', profiles: Array(2).fill({ha_user_id: context.subject, name: 'Duplicate'})}],
  ['directory', {state: 'available', profiles: [{ha_user_id: 'other-user', name: 'Unverified'}]}],
  ['preferences', {...preferences(), member_id: '../other'}], ['preferences', {...preferences(), notification_delivery: 'delivered'}],
  ['preferences', {...preferences(), locale: 'fr'}], ['preferences', {...preferences(), routine_participation_summaries: 'false'}],
  ['preferences', {...preferences(), actor: 'other'}],
];
test.each(malformed)('malformed %s projection case %# cannot become usable facts', async (method, raw) => {
  const f = fixture(); f.transport.mockResolvedValueOnce(reply(raw));
  await expect(f.server[method](context).result).rejects.toThrow('invalid_response');
});

test.each([{alias: '  Unnormalized  '}, {alias: '\nControl'}, {member_id: 'other'}])('a changed presentation %j cannot stand for the requested target', async change => {
  const f = fixture(); f.transport.mockResolvedValueOnce(reply({...presentation(), ...change}));
  await expect(f.server.presentation('member-1', context).result).rejects.toThrow('invalid_response');
});

test.each([{key: 'bad/key'}, {command: {action: 'unknown', payload: {}}}, {extra: 'credential'}])('invalid original request %j fails before CSRF or a write', async patch => {
  const f = fixture(); const input = {key: 'key', command: administrationCommand(commands[0]), ...patch};
  expect(await f.server.send(input as never, context)).toMatchObject({kind: 'rejected', reason: 'invalid_input'});
  expect(f.transport).not.toHaveBeenCalled();
});

test.each(['denied','malformed','transport'] as const)('CSRF %s cannot become a mutation or expose raw failure data', async failure => {
  const f = fixture();
  if (failure === 'transport') f.transport.mockRejectedValueOnce(new Error('private transport data'));
  else f.transport.mockResolvedValueOnce(failure === 'denied' ? blocked(403) : reply({csrf_token: 'wrong'}));
  const result = await f.server.send({key: 'key', command: administrationCommand(commands[4])}, context);
  expect(result).toMatchObject({kind: 'rejected'}); expect(JSON.stringify(result)).not.toContain('private'); expect(f.transport).toHaveBeenCalledTimes(1);
});

test.each(['csrf','put'] as const)('a timeout during %s retires the request without an automatic mutation retry', async phase => {
  vi.useFakeTimers(); const f = fixture();
  if (phase === 'put') f.transport.mockResolvedValueOnce(reply({csrf_token: 'c'.repeat(64)}));
  f.transport.mockImplementation(() => new Promise<Response>(() => {}));
  const result = f.server.send({key: 'original', command: administrationCommand(commands[4])}, context);
  await vi.advanceTimersByTimeAsync(HTTP_TIMEOUT_MS);
  expect(await result).toMatchObject({kind: phase === 'put' ? 'uncertain' : 'rejected'});
  expect(f.transport).toHaveBeenCalledTimes(phase === 'put' ? 2 : 1);
});

test('historical original processing does not become current effect or notification delivery', async () => {
  const f = fixture(); f.transport.mockResolvedValueOnce(reply({...receipt(4, true), state: 'historical', archived_by: 'restore-1', event_delivery: 'suppressed'}));
  expect(await f.server.original({key: 'original-key', command: administrationCommand(commands[4]), operationId: null}, context).result)
    .toMatchObject({stage: 'historical', archivedBy: 'restore-1', eventDelivery: 'suppressed', notificationDelivery: 'unavailable'});
});

test.each([{action: 'member.update'}, {command_key: 'other'}, {operation_id: 'other'}, {state: 'historical'}, {event_delivery: 'suppressed'},
  {notification_delivery: 'delivered'}, {result: {...results[4], locale: 'en'}}])('an unbound original response %j cannot replace the captured intent', async patch => {
  const f = fixture(); f.transport.mockResolvedValueOnce(reply({...receipt(4, true), ...patch}));
  await expect(f.server.original({key: 'original-key', command: administrationCommand(commands[4]), operationId: 'op-1'}, context).result).rejects.toThrow('invalid_response');
});

test('invalid original lookup and oversized roster fail without producing a partial result', async () => {
  const f = fixture();
  await expect(f.server.original({key: 'bad/key', command: administrationCommand(commands[0]), operationId: null}, context).result).rejects.toThrow('invalid_response');
  expect(f.transport).not.toHaveBeenCalled();
  f.transport.mockResolvedValueOnce(new Response(' '.repeat(ROSTER_MAX_BYTES + 1), {headers: {'Content-Type': 'application/json', 'Cache-Control': 'no-store'}}));
  await expect(f.server.roster(context).result).rejects.toThrow('invalid_response');
});

test('deadline at each CSRF continuation never invokes a mutation with an aborted signal', async () => {
  vi.useFakeTimers({toFake: ['setTimeout','clearTimeout']});
  for (let delay = 0; delay < 20; delay++) {
    const f = fixture();
    f.transport.mockImplementationOnce(async () => {
      const stream = new ReadableStream<Uint8Array>({start(controller) {
        controller.enqueue(new TextEncoder().encode(encode({csrf_token: 'c'.repeat(64)}))); controller.close();
        const later = (remaining: number) => {if (remaining === 0) vi.advanceTimersByTime(HTTP_TIMEOUT_MS); else queueMicrotask(() => later(remaining - 1));};
        queueMicrotask(() => later(delay));
      }});
      return new Response(stream, {headers: {'Content-Type': 'application/json', 'Cache-Control': 'no-store'}});
    });
    f.transport.mockImplementationOnce(async (_path, init) => {
      expect(init.signal!.aborted).toBe(false); return reply(receipt(4));
    });
    await f.server.send({key: 'original', command: administrationCommand(commands[4])}, context);
    for (let index = 0; index < 20; index++) await Promise.resolve();
    expect(vi.getTimerCount()).toBe(0);
    expect(f.transport.mock.calls.filter(([, init]) => init.method === 'PUT').length).toBeLessThanOrEqual(1);
  }
});

test.each(commands)('operation-ID recovery for $action retains its captured intent under the existing protected GET contract', async raw => {
  const f = fixture(), index = commands.indexOf(raw), data = receipt(index);
  const {notification_delivery: _notification, ...legacy} = data;
  f.transport.mockResolvedValueOnce(reply({...legacy, delivery: 'delivered'}));
  const original = {key: 'original-key', command: administrationCommand(raw), operationId: 'op-1'};
  expect(await f.server.operation(original, context).result).toMatchObject({kind: 'receipt', operationId: 'op-1', action: raw.action,
    eventDelivery: 'delivered', notificationDelivery: 'unavailable', result: {revision: NEXT}});
  expect(f.transport.mock.calls[0][0]).toBe('/api/v1/operations/op-1');
  const init = f.transport.mock.calls[0][1]; expect(init.method).toBe('GET'); expect(init.body).toBeNull();
  expect(new Headers(init.headers).has('X-CSRF-Token')).toBe(false);
});

test('operation-ID lookup requires a captured valid ID and rejects a replacement response', async () => {
  const f = fixture(), command = administrationCommand(commands[4]);
  await expect(f.server.operation({key: 'original-key', command, operationId: null}, context).result).rejects.toThrow('invalid_response');
  expect(f.transport).not.toHaveBeenCalled();
  const {notification_delivery: _notification, ...legacy} = receipt(4);
  f.transport.mockResolvedValueOnce(reply({...legacy, operation_id: 'replacement', delivery: 'delivered'}));
  await expect(f.server.operation({key: 'original-key', command, operationId: 'op-1'}, context).result).rejects.toThrow('invalid_response');
});

test('C39: household wire facts and original intents admit only bounded integer horizons',()=>{
  const fact={household_id:'home',name:'Home',time_zone:'UTC',revision:'$revision'};
  const original={expected_revision:REV,name:'Home',time_zone:'UTC'};
  for(const value of [7,14,366]) {
    expect(household(administrationJSON(encode({...fact,materialization_horizon_days:value})))).toMatchObject({
      revision:REV,materializationHorizonDays:value,
    });
    const command=administrationCommand({action:'household.update',payload:{...original,materialization_horizon_days:value}});
    expect(administrationCommandBody(command)).toBe(
      '{"expected_revision":'+REV+',"name":"Home","time_zone":"UTC","materialization_horizon_days":'+value+'}',
    );
  }
  for(const value of [6,367,14.5,'14',null,true]) {
    expect(()=>household(administrationJSON(encode({...fact,materialization_horizon_days:value})))).toThrow('invalid_response');
    expect(()=>administrationCommand({action:'household.update',payload:{...original,materialization_horizon_days:value}})).toThrow('invalid_command');
  }
});
