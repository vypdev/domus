import {afterEach, expect, test, vi} from 'vitest';
import {HttpEntryServer, HTTP_TIMEOUT_MS} from '../src/adapters/http';
import {EntryReadError} from '../src/application/ports';
import type {JournalContext} from '../src/domain/journal';
import corpus from './fixtures/entry-wire.json';
import {EntryController} from '../src/application/entry-controller';
import {SessionJournal, ENTRY_JOURNAL_KEY} from '../src/adapters/session-journal';

const context: JournalContext = {installationId: '01234567-89ab-cdef-0123-456789abcdef',
  channel: 'edge', subject: 'a'.repeat(32)};
const base = '/api/hassio_ingress/' + 'b'.repeat(43) + '/';
const endpoint = {deployment: 'standalone' as const, applicationBase: '/', origin: 'https://domus.example'};
function session() {return {state: 'authenticated', ha_user_id: context.subject, ha_administrator: true,
  access: 'full', expires_in: 3600, message: 'Verified.', action_required: 'No action required.',
  context: {installation_id: context.installationId, channel: context.channel, deployment: 'standalone',
    application_base: '/', household_api_available: true, server_time: 1000, expires_at: 3_601_000}};}
function access(state = 'unconfigured') {return {state, setup_allowed: state === 'unconfigured',
  enrollment_allowed: state === 'not_enrolled', permission_scope: 'household_administration',
  permissions: [], message: 'Review current access.', action_required: 'Review status.'};}
function receipt(action = 'setup') {return {state: 'committed', archived_by: null, operation_id: 'op-1',
  created_at: 1000, message: 'Saved.', action_required: 'Keep the original request.',
  result: action === 'setup' ? {state: 'configured', household_id: 'home', revision: 1, policy_revision: 1,
    member_id: 'member-1', administrator_member_id: 'member-1', mapping_mode: 'all_ha_administrators'}
    : {member_id: 'member-1', status: 'pending', role: 'viewer', revision: 1, policy_revision: 1}};}
function response(value: unknown, status = 200) {return new Response(JSON.stringify(value), {status,
  headers: {'Content-Type': 'application/json', 'Cache-Control': 'no-store'}});}
function blocked(status: number) {return response({state: 'blocked', code: 'request_forbidden',
  message: 'Private provider content.', action_required: 'Review current access.', correlation_id: 'cor_safe'}, status);}
function fixture() {
  const transport = vi.fn((_path: string, _init: RequestInit) => Promise.resolve(response(session())));
  const network = async (path: string, init: RequestInit) => {
    const result = await transport(path, init);
    if (!result.url) Object.defineProperty(result, 'url', {value: endpoint.origin + path});
    return result;
  };
  return {transport, network, server: new HttpEntryServer(endpoint, network)};
}
const setupCommand = {key: 'original-key', action: 'setup' as const, payload: {name: '  Home  ',
  time_zone: 'UTC', expected_revision: 0 as const, mapping_mode: 'all_ha_administrators' as const}};
afterEach(() => {vi.useRealTimers();});

test('C02/C20: standalone session exposes only strictly decoded proof and makes one read', async () => {
  const f = fixture(); const proof = await f.server.session().result;
  expect(proof).toEqual({context, deployment: 'standalone', access: 'full', serverTime: 1000,
    expiresAt: 3_601_000, householdApiAvailable: true});
  expect(Object.isFrozen(proof?.context)).toBe(true);
  expect(f.transport).toHaveBeenCalledTimes(1);
  expect(f.transport.mock.calls[0][0]).toBe('/api/v1/session');
  expect(f.transport.mock.calls[0][1]).toMatchObject({method: 'GET', mode: 'same-origin',
    credentials: 'same-origin', redirect: 'error', cache: 'no-store', referrerPolicy: 'no-referrer'});
});

test('C19: every native API path stays under the accepted base and bound reads assert context', async () => {
  const f = fixture(), wire = {...session(), source: 'home_assistant_ingress'};
  wire.context = {...wire.context, deployment: 'native', application_base: base};
  f.transport.mockResolvedValueOnce(response(wire)).mockResolvedValueOnce(response(access()))
    .mockResolvedValueOnce(response({household_id: 'home', name: 'Home', time_zone: 'UTC', revision: 1}));
  const native = new HttpEntryServer({...endpoint, deployment: 'native', applicationBase: base}, f.network);
  expect((await native.session().result)?.deployment).toBe('native');
  expect((await native.authorization(context).result).state).toBe('unconfigured');
  expect((await native.household(context).result).name).toBe('Home');
  expect(f.transport.mock.calls.map(([path]) => path)).toEqual([base+'api/v1/session', base+'api/v1/authorization', base+'api/v1/household']);
  expect(new Headers(f.transport.mock.calls[1][1].headers).get('X-Domus-Context'))
    .toBe(`v1:${context.installationId}:edge:${context.subject}`);
});

test.each(['setup', 'enroll'] as const)('C07/C22: %s sends fresh CSRF and exact original payload/key once', async action => {
  const f = fixture(); f.transport.mockResolvedValueOnce(response({csrf_token: 'c'.repeat(64)}))
    .mockResolvedValueOnce(response(receipt(action)));
  const command = action === 'setup' ? setupCommand : {key: 'original-key', action, payload: {expected_revision: 0 as const}};
  const result = await f.server.send(command, context);
  expect(result).toMatchObject({kind: 'receipt', stage: 'committed', operationId: 'op-1'});
  expect(f.transport.mock.calls.map(([path]) => path)).toEqual(['/api/v1/auth/csrf',
    action === 'setup' ? '/api/v1/household' : '/api/v1/members/enrollment']);
  const init = f.transport.mock.calls[1][1], headers = new Headers(init.headers);
  expect(init.method).toBe('POST'); expect(JSON.parse(init.body as string)).toEqual(command.payload);
  expect(headers.get('Idempotency-Key')).toBe('original-key'); expect(headers.get('X-CSRF-Token')).toBe('c'.repeat(64));
  expect(headers.get('Content-Type')).toBe('application/json'); expect(headers.has('Origin')).toBe(false);
  expect(Object.isFrozen(result)).toBe(true);
});

test.each([401,403,409,422,503])('C13/C14: known POST %s preserves rejection and safe correlation only', async status => {
  const f = fixture(); f.transport.mockResolvedValueOnce(response({csrf_token: 'c'.repeat(64)}))
    .mockResolvedValueOnce(blocked(status));
  const result = await f.server.send(setupCommand, context);
  expect(result).toMatchObject({kind: 'rejected', correlationId: 'cor_safe'});
  expect(JSON.stringify(result)).not.toContain('Private'); expect(f.transport).toHaveBeenCalledTimes(2);
});

test('C12: lost POST response is uncertain, with no automatic retry or key replacement', async () => {
  const f = fixture(); f.transport.mockResolvedValueOnce(response({csrf_token: 'c'.repeat(64)}))
    .mockRejectedValueOnce(new Error('private transport details'));
  expect(await f.server.send(setupCommand, context)).toEqual({kind: 'uncertain'});
  expect(f.transport).toHaveBeenCalledTimes(2);
});

test('C44: operation query decodes historical original receipt and actual suppressed delivery', async () => {
  const f = fixture(); f.transport.mockResolvedValueOnce(response({...receipt(), state: 'historical',
    archived_by: 'restore-1', delivery: 'suppressed'}));
  const result = await f.server.operation('setup', 'op-1', context).result;
  expect(result).toMatchObject({stage: 'historical', operationId: 'op-1', archivedBy: 'restore-1', delivery: 'suppressed'});
  expect(f.transport.mock.calls[0][0]).toBe('/api/v1/operations/op-1');
});

test('C18/C42: standalone logout verifies current context, gets CSRF and clears the actual session', async () => {
  const f = fixture(); f.transport.mockResolvedValueOnce(response(session()))
    .mockResolvedValueOnce(response({csrf_token: 'c'.repeat(64)}))
    .mockResolvedValueOnce(response({state: 'logged_out', upstream_revoked: false,
      message: 'You are signed out of Domus.', action_required: 'Review authorization.'}));
  expect(await f.server.logout()).toEqual({upstreamRevoked: false});
  expect(f.transport.mock.calls.map(([path]) => path)).toEqual(['/api/v1/session','/api/v1/auth/csrf','/api/v1/auth/logout']);
  expect(f.transport.mock.calls[2][1].body).toBe('{}');
});

test('C48: cancellation aborts an owned read and maps its error without exposing provider details', async () => {
  const f = fixture(); f.transport.mockImplementation((_path, init) => new Promise((_resolve, reject) => {
    init.signal!.addEventListener('abort', () => reject(new Error('private cancelled read')));
  }));
  const read = f.server.session(); read.cancel();
  await expect(read.result).rejects.toThrow(EntryReadError);
  expect(f.transport.mock.calls[0][1].signal!.aborted).toBe(true);
});

test('C21: operation deadline aborts a stalled transport without retry', async () => {
  vi.useFakeTimers({toFake: ['setTimeout', 'clearTimeout']});
  const f = fixture(); f.transport.mockImplementation((_path, init) => new Promise((_resolve, reject) => {
    init.signal!.addEventListener('abort', () => reject(new Error('timeout')));
  }));
  const read = f.server.session(); const result = expect(read.result).rejects.toThrow('unavailable');
  await vi.advanceTimersByTimeAsync(HTTP_TIMEOUT_MS); await result;
  expect(f.transport).toHaveBeenCalledTimes(1); expect(vi.getTimerCount()).toBe(0);
});

test('C48: deadline finishes an owned read even when a provider ignores abort', async () => {
  vi.useFakeTimers({toFake: ['setTimeout', 'clearTimeout']}); const f = fixture();
  let release!: (response: Response) => void, settled = false;
  f.transport.mockImplementation(() => new Promise(resolve => {release = resolve;}));
  const result = f.server.session().result.catch(() => {settled = true;});
  await vi.advanceTimersByTimeAsync(HTTP_TIMEOUT_MS); const atDeadline = settled;
  release(response(session())); await result;
  expect(atDeadline).toBe(true); expect(vi.getTimerCount()).toBe(0);
});

test.each([
  {origin: 'https://foreign.invalid/path'}, {origin: 'javascript:alert(1)'}, {origin: 'not-a-url'},
  {origin: 'https://user:secret@domus.example'}, {origin: 'https://domus.example/'},
  {deployment: 'unknown'}, {applicationBase: '//foreign.invalid/'}, {applicationBase: '/extra/'},
  {deployment: 'native', applicationBase: '/'}, {deployment: 'native', applicationBase: base+'../'},
  {deployment: 'native', applicationBase: '/api/hassio_ingress/%2e%2e/'}, {secret: 'extra'},
])('C23: unsupported bootstrap %j cannot create a network capability', patch => {
  const f = fixture(); expect(() => new HttpEntryServer({...endpoint, ...patch} as never, f.network)).toThrow('invalid_response');
  expect(f.transport).not.toHaveBeenCalled();
});

test.each([
  {context: null}, {state: 'unknown'}, {access: 'administrator'}, {ha_user_id: '../other'},
  {ha_administrator: 'true'}, {expires_in: -1}, {expires_in: 3601}, {message: ''},
  {credential: 'private'}, {source: 'home_assistant_ingress'},
])('C02/C21: bad session %j never becomes verified proof', async patch => {
  const f = fixture(); f.transport.mockResolvedValueOnce(response({...session(), ...patch}));
  await expect(f.server.session().result).rejects.toThrow('invalid_response');
});

test.each([
  {installation_id: 'foreign'}, {installation_id: context.installationId.toUpperCase()}, {channel: 'production'},
  {application_base: '//foreign.invalid/'}, {deployment: 'native'}, {server_time: -1}, {server_time: 1.5},
  {expires_at: 2**53}, {expires_at: 28_802_000}, {household_api_available: 1}, {actor: 'extra'},
])('C02/C21: bad server metadata %j cannot retarget or extend a session', async patch => {
  const f = fixture(), value = session(); value.context = {...value.context, ...patch} as never;
  f.transport.mockResolvedValueOnce(response(value)); await expect(f.server.session().result).rejects.toThrow('invalid_response');
});

test('C08/C15: absent identity, preview and grace remain separate truthful states', async () => {
  const f = fixture(); f.transport.mockResolvedValueOnce(blocked(401)); expect(await f.server.session().result).toBeNull();
  const preview = session(); preview.context.household_api_available = false;
  f.transport.mockResolvedValueOnce(response(preview)); expect((await f.server.session().result)?.householdApiAvailable).toBe(false);
  f.transport.mockResolvedValueOnce(response({...session(), access: 'read_only'}));
  expect((await f.server.session().result)?.access).toBe('read_only');
});

test.each([401,403,404,409,422,503])('C21: failed bound read %s has a safe typed error', async status => {
  const f = fixture(); f.transport.mockResolvedValueOnce(blocked(status));
  await expect(f.server.household(context).result).rejects.toThrow(EntryReadError);
});

test('C21: failed session read is separate from a missing session', async () => {
  const f = fixture(); f.transport.mockResolvedValueOnce(blocked(503));
  await expect(f.server.session().result).rejects.toThrow('unavailable');
});

function active() {return {...access('active'), member: {member_id: 'member-1', role: 'viewer', status: 'active',
  revision: 1, ha_user_id: context.subject, exceptions: [{permission: 'tasks.read', allow: false}]},
  effective_role: 'administrator', policy_revision: 1, permissions: ['household.read']};}
test.each(['pending','active','suspended','archived','not_enrolled'])('C01/C40: %s access consumes actual flags/permissions, not profile grants', async state => {
  const f = fixture(); const value = state === 'active' ? active() : {...access(state),
    ...(['pending','suspended','archived'].includes(state) ? {member: {member_id: 'member-1', role: 'viewer', status: state, revision: 1}} : {})};
  f.transport.mockResolvedValueOnce(response(value)); const result = await f.server.authorization(context).result;
  expect(result.state).toBe(state); expect(result.permissions).toEqual(state === 'active' ? ['household.read'] : []);
  expect(Object.isFrozen(result.permissions)).toBe(true);
});

test.each([
  {permission_scope: 'all_domains'}, {permissions: ['tasks.configure']}, {permissions: ['household.read','household.read']},
  {permissions: {}}, {permissions: new Array(9).fill('household.read')}, {setup_allowed: true}, {enrollment_allowed: true},
  {policy_revision: 0}, {effective_role: 'owner'}, {member: null},
  {member: {...active().member, ha_user_id: 'b'.repeat(32)}}, {member: {...active().member, status: 'pending'}},
  {member: {...active().member, exceptions: [{permission: 'tasks.read', allow: 'false'}]}},
  {member: {...active().member, exceptions: [{permission: '../bad', allow: true}]}},
  {member: {...active().member, exceptions: [{permission: 'tasks.read', allow: true},{permission:'tasks.read',allow:false}]}},
  {member: {...active().member, exceptions: new Array(257).fill({permission: 'tasks.read', allow: true})}},
  {member: {...active().member, exceptions: 'invalid'}},
])('C21/C40: inconsistent authority %j cannot grant access', async patch => {
  const f = fixture(); f.transport.mockResolvedValueOnce(response({...active(), ...patch}));
  await expect(f.server.authorization(context).result).rejects.toThrow('invalid_response');
});

test.each([{permissions:['household.read']},{member:{member_id:'m',role:'viewer',status:'active',revision:1}},
  {policy_revision:1},{effective_role:'administrator'}])('C21: inactive access cannot carry active authority %j', async patch => {
  const f = fixture(); f.transport.mockResolvedValueOnce(response({...access(),...patch}));
  await expect(f.server.authorization(context).result).rejects.toThrow('invalid_response');
});

test('C21: household read preserves inert historical DEL/C1 text without applying setup normalization', async () => {
  const f = fixture(); f.transport.mockResolvedValueOnce(response({household_id:'home',name:'Home\u007f\u0085',time_zone:'UTC',revision:2}));
  expect((await f.server.household(context).result).name).toBe('Home\u007f\u0085');
});
test.each([{name:' '},{name:'a'.repeat(161)},{name:'bad\n'},{time_zone:''},{time_zone:'bad\t'},
  {revision:0},{revision:2**53},{household_id:'../home'}])('C21: invalid household %j is unavailable', async patch => {
  const f=fixture(); f.transport.mockResolvedValueOnce(response({household_id:'home',name:'Home',time_zone:'UTC',revision:1,...patch}));
  await expect(f.server.household(context).result).rejects.toThrow('invalid_response');
});

test.each(['','not-json','null','[]','{}','{"state":','{"state":"authenticated","state":"other"}',
  '{"state":"authenticated","st\\u0061te":"other"}', '[[[[[[[[[[[[[[[[[0]]]]]]]]]]]]]]]]]',
  '{"value":9007199254740993}', '{"value":9007199254740990.5}', '{"value":1e3}', '{"value":-0}'])(
  'C21: malformed/deep/duplicate/unsafe JSON %s cannot become decoded proof', async raw => {
    const f=fixture(); f.transport.mockResolvedValueOnce(new Response(raw,{headers:{'Content-Type':'application/json','Cache-Control':'no-store'}}));
    await expect(f.server.session().result).rejects.toThrow('invalid_response');
  },
);

test.each([{url:'https://foreign.invalid/api/v1/session'},{url:endpoint.origin+'/wrong'}, {redirected:true},
  {type:'opaque'}, {type:'opaqueredirect'}, {type:'error'}])('C23: foreign/redirect/opaque response %j cannot export context', async properties => {
  const f=fixture(), result=response(session());
  for(const [key,value] of Object.entries(properties)) Object.defineProperty(result,key,{value});
  f.transport.mockResolvedValueOnce(result); await expect(f.server.session().result).rejects.toThrow('invalid_response');
});

test.each([{'Content-Type':'text/html'},{'Content-Type':'application/json;charset=latin1'},
  {'Cache-Control':'public,max-age=30'},{'Content-Length':'65537'},{'Content-Length':'10, 10'}])(
  'C21: unsupported response headers %j are rejected before decoding', async headers => {
    const f=fixture(), values=new Headers({'Content-Type':'application/json','Cache-Control':'no-store'});
    for(const [key,value] of Object.entries(headers)) values.set(key,value!);
    f.transport.mockResolvedValueOnce(new Response(JSON.stringify(session()),{headers:values}));
    await expect(f.server.session().result).rejects.toThrow('invalid_response');
  },
);

test('C21: declared and actual UTF-8 size, fatal encoding and stream failure are bounded', async () => {
  for (const bytes of [new Uint8Array(65_537),new Uint8Array([0xff])]) {
    const f=fixture(); f.transport.mockResolvedValueOnce(new Response(bytes,{headers:{'Content-Type':'application/json','Cache-Control':'no-store'}}));
    await expect(f.server.session().result).rejects.toThrow(EntryReadError);
  }
  const f=fixture(); f.transport.mockResolvedValueOnce(new Response(null,{headers:{'Content-Type':'application/json','Cache-Control':'no-store'}}));
  await expect(f.server.session().result).rejects.toThrow('invalid_response');
});

test.each([{key:'../bad'},{action:'other'},{actor:'forged'},{payload:{...setupCommand.payload,selected_ha_user_id:'b'.repeat(32)}},
  {payload:{...setupCommand.payload,name:'bad\u007f'}},{payload:{...setupCommand.payload,expected_revision:1}}])(
  'C22: invalid command %j never reaches CSRF or POST', async patch => {
    const f=fixture(); expect(await f.server.send({...setupCommand,...patch} as never,context)).toMatchObject({kind:'rejected'});
    expect(f.transport).not.toHaveBeenCalled();
  },
);

test.each([{installationId:'bad'},{channel:'production'},{subject:'other'},{actor:'extra'}])('C41: malformed expected context %j never reaches the server', async patch => {
  const f=fixture(); await expect(f.server.household({...context,...patch} as never).result).rejects.toThrow('invalid_response');
  expect(f.transport).not.toHaveBeenCalled();
});

test.each([401,403,503])('C22: rejected CSRF preflight %s never posts', async status => {
  const f=fixture(); f.transport.mockResolvedValueOnce(blocked(status)); expect(await f.server.send(setupCommand,context)).toMatchObject({kind:'rejected'});
  expect(f.transport).toHaveBeenCalledTimes(1);
});
test.each([{csrf_token:'bad'},{csrf_token:'c'.repeat(64),actor:'extra'}])('C22: malformed CSRF %j never posts', async csrf => {
  const f=fixture(); f.transport.mockResolvedValueOnce(response(csrf)); expect(await f.server.send(setupCommand,context)).toMatchObject({kind:'rejected'});
  expect(f.transport).toHaveBeenCalledTimes(1);
});

test.each([500,404,201])('C12: unexpected POST status %s stays uncertain', async status => {
  const f=fixture(); f.transport.mockResolvedValueOnce(response({csrf_token:'c'.repeat(64)})).mockResolvedValueOnce(blocked(status));
  expect(await f.server.send(setupCommand,context)).toEqual({kind:'uncertain'});
});
test.each([{operation_id:'../bad'},{created_at:-1},{state:'historical'}, {result:{...receipt().result,revision:2}},
  {result:{...receipt().result,mapping_mode:'selected_ha_user'}},{state:'other'},{actor:'extra'},
  {result:{...receipt().result,secret:'extra'}}, {result:{...receipt().result,member_id:'../bad'}}])('C12/C44: malformed received receipt %j stays uncertain', async patch => {
  const f=fixture(); f.transport.mockResolvedValueOnce(response({csrf_token:'c'.repeat(64)})).mockResolvedValueOnce(response({...receipt(),...patch}));
  expect(await f.server.send(setupCommand,context)).toEqual({kind:'uncertain'});
});

test.each(['pending','delivered'] as const)('C44: committed operation reports real %s delivery', async delivery => {
  const f=fixture(); f.transport.mockResolvedValueOnce(response({...receipt('enroll'),delivery}));
  expect((await f.server.operation('enroll','op-1',context).result).delivery).toBe(delivery);
});
test.each([{delivery:'suppressed'},{delivery:'other'},{operation_id:'different'}])('C44: incompatible operation metadata %j cannot replace the original', async patch => {
  const f=fixture(); f.transport.mockResolvedValueOnce(response({...receipt(),delivery:'pending',...patch}));
  await expect(f.server.operation('setup','op-1',context).result).rejects.toThrow('invalid_response');
});

test('C18: native adapter never invokes standalone logout', async () => {
  const f=fixture(), native=new HttpEntryServer({...endpoint,deployment:'native',applicationBase:base},f.network);
  await expect(native.logout()).rejects.toThrow('forbidden'); expect(f.transport).not.toHaveBeenCalled();
});
test.each([true,null])('C42: valid upstream logout result %j is preserved',async upstream_revoked=>{
  const f=fixture(); f.transport.mockResolvedValueOnce(response(session())).mockResolvedValueOnce(response({csrf_token:'c'.repeat(64)}))
    .mockResolvedValueOnce(response({state:'logged_out',upstream_revoked,message:'You are signed out of Domus.',action_required:'Review authorization.'}));
  expect(await f.server.logout()).toEqual({upstreamRevoked:upstream_revoked});
});
test('C42: server logout rejection stays truthful rather than fabricating revocation',async()=>{
  const f=fixture(); f.transport.mockResolvedValueOnce(response(session())).mockResolvedValueOnce(response({csrf_token:'c'.repeat(64)})).mockResolvedValueOnce(blocked(503));
  await expect(f.server.logout()).rejects.toThrow('unavailable');
});

test.each(['Content-Type','Cache-Control'])('C21: missing %s cannot be accepted as personal JSON',async missing=>{
  const f=fixture(), headers=new Headers({'Content-Type':'application/json','Cache-Control':'no-store'});
  headers.delete(missing);
  f.transport.mockResolvedValueOnce(new Response(new TextEncoder().encode(JSON.stringify(session())),{headers}));
  await expect(f.server.session().result).rejects.toThrow('invalid_response');
});

test('C22: unavailable CSRF transport is a known pre-send failure',async()=>{
  const f=fixture(); f.transport.mockRejectedValueOnce(new Error('private provider details'));
  expect(await f.server.send(setupCommand,context)).toEqual({kind:'rejected',reason:'unavailable',correlationId:null});
  expect(f.transport).toHaveBeenCalledTimes(1);
});

test.each(['preflight','post'] as const)('C12/C22: deadline during %s ends the operation and never retries',async stage=>{
  vi.useFakeTimers({toFake:['setTimeout','clearTimeout']}); const f=fixture();
  let release!:(response:Response)=>void;
  if(stage==='post') f.transport.mockResolvedValueOnce(response({csrf_token:'c'.repeat(64)}));
  f.transport.mockImplementationOnce(()=>new Promise(resolve=>{release=resolve;}));
  const operation=f.server.send(setupCommand,context);
  for(let i=0;i<20;i++) await Promise.resolve();
  await vi.advanceTimersByTimeAsync(HTTP_TIMEOUT_MS);
  const result=await operation;
  expect(result.kind).toBe(stage==='post'?'uncertain':'rejected');
  release(response(stage==='post'?receipt():{csrf_token:'c'.repeat(64)}));
  for(let i=0;i<20;i++) await Promise.resolve();
  expect(f.transport).toHaveBeenCalledTimes(stage==='post'?2:1); expect(vi.getTimerCount()).toBe(0);
});

test.each([false,true])('C48: abort during body streaming releases reader even with cancel failure=%j',async fail=>{
  const f=fixture(); let cancels=0;
  const stream=new ReadableStream<Uint8Array>({cancel(){cancels++; if(fail) throw new Error('private cancellation detail');}});
  f.transport.mockResolvedValueOnce(new Response(stream,{headers:{'Content-Type':'application/json','Cache-Control':'no-store'}}));
  const operation=f.server.session(); const result=expect(operation.result).rejects.toThrow('unavailable');
  for(let i=0;i<12;i++) await Promise.resolve(); operation.cancel(); await result;
  for(let i=0;i<12;i++) await Promise.resolve();
  expect(cancels).toBe(1); expect(stream.locked).toBe(false);
});

test('C21: whitespace, escaped text, split UTF-8 and strict decimal integer zero decode correctly',async()=>{
  const f=fixture(); const value={...session(),message:'Verified 🏠 "name"\\tail',context:{...session().context,server_time:0,expires_at:3_600_000}};
  const bytes=new TextEncoder().encode(JSON.stringify(value,null,2));
  const stream=new ReadableStream<Uint8Array>({start(controller){for(let i=0;i<bytes.length;i++) controller.enqueue(bytes.slice(i,i+1)); controller.close();}});
  f.transport.mockResolvedValueOnce(new Response(stream,{headers:{'Content-Type':'Application/JSON; charset=UTF-8','Cache-Control':'private, no-store','Content-Length':String(bytes.length)}}));
  expect((await f.server.session().result)?.serverTime).toBe(0);
});

test.each(['send','logout'] as const)('C22: exhaustion at each %s continuation never starts a request with an aborted signal',async mode=>{
  vi.useFakeTimers({toFake:['setTimeout','clearTimeout']});
  for(let delay=0;delay<14;delay++){
    const f=fixture(); if(mode==='logout') f.transport.mockResolvedValueOnce(response(session()));
    f.transport.mockImplementationOnce(async()=>{
      const stream=new ReadableStream<Uint8Array>({start(controller){
        controller.enqueue(new TextEncoder().encode(JSON.stringify({csrf_token:'c'.repeat(64)}))); controller.close();
        const later=(count:number)=>{if(count===0) vi.advanceTimersByTime(HTTP_TIMEOUT_MS);else queueMicrotask(()=>later(count-1));};
        queueMicrotask(()=>later(delay));
      }});
      return new Response(stream,{headers:{'Content-Type':'application/json','Cache-Control':'no-store'}});
    });
    f.transport.mockImplementationOnce(async(_path,init)=>{
      expect(init.signal!.aborted).toBe(false);
      return response(mode==='send'?receipt():{state:'logged_out',upstream_revoked:true,message:'You are signed out of Domus.',action_required:'Done.'});
    });
    if(mode==='send') await f.server.send(setupCommand,context);
    else await f.server.logout().catch(error=>{expect(error).toBeInstanceOf(EntryReadError);});
    for(let i=0;i<20;i++) await Promise.resolve();
    expect(vi.getTimerCount()).toBe(0);
  }
});

test('C20: the browser native fetch capability performs a real isolated same-origin read',async()=>{
  let transportError:unknown;
  const observed=new Proxy(fetch,{apply(target,receiver,args){
    try{return (Reflect.apply(target,receiver,args) as Promise<Response>).catch(error=>{transportError=error;throw error;});}
    catch(error){transportError=error;throw error;}
  }});
  const server=new HttpEntryServer({...endpoint,origin:location.origin},observed);
  // The owned Vitest server has no product API. Its real HTTP response must never become proof.
  const failure=await server.session().result.catch(error=>error);
  expect(transportError).toBeUndefined(); expect(failure).toMatchObject({code:'invalid_response'});
});

test.each(Object.entries(corpus))('C18/C19/C20: recorded %s provider wire survives the actual client decoder',async(_mode,values)=>{
  const transport=vi.fn(async(path:string,_init:RequestInit)=>{
    const raw=queue.shift()!; const reply=new Response(raw,{headers:{'Content-Type':'application/json','Cache-Control':'no-store'}});
    Object.defineProperty(reply,'url',{value:values.endpoint.origin+path}); return reply;
  });
  const queue:string[]=[];
  const server=new HttpEntryServer(values.endpoint as never,transport);
  queue.push(values.session); const administrator=await server.session().result; expect(administrator).not.toBeNull();
  queue.push(values.unconfigured); expect((await server.authorization(administrator!.context).result).state).toBe('unconfigured');
  queue.push(JSON.stringify({csrf_token:'c'.repeat(64)}),values.setup);
  const created=await server.send({...setupCommand,payload:{...setupCommand.payload,name:'Home 🏠'}},administrator!.context);
  expect(created).toMatchObject({kind:'receipt',stage:'committed'});
  queue.push(values.active); expect((await server.authorization(administrator!.context).result).permissions).toContain('household.manage');
  queue.push(values.household); expect((await server.household(administrator!.context).result).name).toBe('Home 🏠');
  queue.push(values.operation); const id=JSON.parse(values.setup).operation_id;
  expect((await server.operation('setup',id,administrator!.context).result).delivery).toBe('pending');
  queue.push(values.participantSession); const participant=await server.session().result;
  expect(participant!.context.subject).toBe('b'.repeat(32));
  queue.push(values.eligible); expect((await server.authorization(participant!.context).result).enrollmentAllowed).toBe(true);
  queue.push(JSON.stringify({csrf_token:'c'.repeat(64)}),values.enrollment);
  expect(await server.send({action:'enroll',key:'wire-enroll',payload:{expected_revision:0}},participant!.context)).toMatchObject({kind:'receipt'});
  queue.push(values.pending); expect((await server.authorization(participant!.context).result).state).toBe('pending');
  expect(queue).toEqual([]);
});

test('C12/C17: controller, HTTP and owned journal recover a lost simulated effect without a second key',async()=>{
  const f=fixture(), values=new Map<string,string>(); let effects=0, lost=false;
  const journal=new SessionJournal({getItem:key=>values.get(key)??null,setItem:(key,value)=>{values.set(key,value);},removeItem:key=>{values.delete(key);}});
  const submitted:string[]=[];
  f.transport.mockImplementation(async(path,init)=>{
    if(path.endsWith('/session')) return response(session());
    if(path.endsWith('/authorization')) return response(effects===0?access():{...active(),permissions:['household.read','household.manage']});
    if(path.endsWith('/auth/csrf')) return response({csrf_token:'c'.repeat(64)});
    if(init.method==='POST') {
      const stored=JSON.parse(values.get(ENTRY_JOURNAL_KEY)!).records[0];
      expect(new Headers(init.headers).get('Idempotency-Key')).toBe(stored.key);
      expect(JSON.parse(init.body as string)).toEqual(stored.payload); submitted.push(init.body as string);
      if(!lost){effects++;lost=true;throw new Error('Simulated response lost after one effect');}
      return response(receipt());
    }
    return response({household_id:'home',name:'Home',time_zone:'UTC',revision:1});
  });
  const entropy={requestKey:vi.fn(()=>'key-http')};
  const controller=new EntryController('standalone',f.server,journal,{anchor:()=>{},now:()=>1000},entropy);
  await controller.refresh(); expect(effects).toBe(0);
  await controller.submitSetup('Home','UTC'); expect(controller.view.outcome).toEqual({kind:'uncertain'});
  expect(controller.view.journal?.records[0].stage).toBe('uncertain'); expect(effects).toBe(1);
  await controller.recover('key-http'); expect(controller.view.outcome).toMatchObject({kind:'receipt',operationId:'op-1'});
  expect(effects).toBe(1); expect(submitted).toHaveLength(2); expect(submitted[0]).toBe(submitted[1]);
  expect(entropy.requestKey).toHaveBeenCalledTimes(1);
});

test.each(['"'+'\\"'.repeat(32760),'"trailing\\'])('C21: bounded unterminated or trailing-escape strings fail without rescanning prefixes',async raw=>{
  const f=fixture(); f.transport.mockResolvedValueOnce(new Response(raw,{headers:{'Content-Type':'application/json','Cache-Control':'no-store'}}));
  await expect(f.server.session().result).rejects.toThrow('invalid_response');
});

test('C21: legal whitespace between an object key and colon preserves decoded meaning',async()=>{
  const f=fixture(), raw=JSON.stringify(session()).replace('"state":','"state" \n\t :');
  f.transport.mockResolvedValueOnce(new Response(raw,{headers:{'Content-Type':'application/json','Cache-Control':'no-store'}}));
  expect((await f.server.session().result)?.context).toEqual(context);
});
