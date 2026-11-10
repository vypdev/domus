import {INVENTORY_JOURNAL_KEY} from '../src/adapters/inventory-journal';
import {REWARD_JOURNAL_KEY} from '../src/adapters/reward-journal';
import {ALLOCATION_JOURNAL_KEY} from '../src/adapters/allocation-journal';
import {CALENDAR_JOURNAL_KEY} from '../src/adapters/calendar-journal';
import {RECURRENCE_JOURNAL_KEY} from '../src/adapters/recurrence-journal';
import {afterEach, expect, test, vi} from 'vitest';
import {decodeIntent, decodeAdministrationIntent, decodeTaskIntent, decodeCalendarIntent, decodeReviewIntent, decodeInventoryIntent, mountEntry} from '../src/composition/entry-page';
import {AllocationController} from '../src/application/allocation-controller';
import {revisionValue} from '../src/domain/administration';
import {TaskController} from '../src/application/task-controller';
import type {EntryPage} from '../src/composition/entry-page';
import type {DomusApp} from '../src/presentation/domus-app';
import type {DomusAdministration} from '../src/presentation/domus-administration';
import {ENTRY_JOURNAL_KEY} from '../src/adapters/session-journal';
import corpus from './fixtures/entry-wire.json';

const dispose: (() => void)[] = [], nodes: Element[] = [];
afterEach(() => {
  for (const stop of dispose.splice(0)) stop();
  for (const node of nodes.splice(0)) node.remove();
  document.querySelector('#domus-entry-error')?.remove();
});
function fixture(deployment: 'native' | 'standalone' = 'standalone', locale = 'en', canReview = false, canManagePoints = false) {
  const wire = corpus[deployment], values = new Map<string, string>(), navigation: string[] = [];
  const root = document.createElement('div'); root.id = 'domus-entry'; document.body.append(root); nodes.push(root);
  const data = document.createElement('script'); data.id = 'domus-bootstrap'; data.type = 'application/json';
  data.textContent = JSON.stringify({version: 1, deployment, application_base: wire.endpoint.applicationBase, style_nonce: 'a'.repeat(32)});
  document.head.append(data); nodes.push(data);
  let phase = 'unconfigured', postRequests = 0, putRequests = 0;
  const originalAccess=JSON.parse(wire.active);
  let preferenceReceipt:Record<string,unknown>|null=null;
  let memberId:string=originalAccess.member.member_id, preferenceLocale:'en'|'es'|null=null, preferenceRevision=1, preferencesReadable=true;
  const presentation=()=>({member_id:memberId,alias:null,revision:1});
  const preferences=()=>({member_id:memberId,locale:preferenceLocale,revision:preferenceRevision,routine_participation_summaries:true,notification_delivery:'unavailable'});
  let weekStart='monday', weekRevision=1, weekOriginal:object|null=null;
  const fetch = vi.fn(async (path: string, init: RequestInit) => {
    const route = path.slice(wire.endpoint.applicationBase.length + 'api/v1/'.length);
    let raw: string;
    if (route === 'session') raw = phase === 'eligible' || phase === 'pending' ? wire.participantSession : wire.session;
    else if (route === 'authorization') raw = phase === 'active' ? JSON.stringify({...originalAccess,member:{...originalAccess.member,member_id:memberId},
      permissions:originalAccess.permissions.filter((permission:string)=>preferencesReadable||permission!=='preferences.read')})
      : phase === 'eligible' ? wire.eligible : phase === 'pending' ? wire.pending : wire.unconfigured;
    else if (route === 'auth/csrf') raw = JSON.stringify({csrf_token: 'c'.repeat(64)});
    else if (route === 'auth/logout') raw = JSON.stringify({state: 'logged_out', upstream_revoked: true,
      message: 'You are signed out of Domus.', action_required: 'Sign in to continue.'});
    else if (route === 'tasks/calendar/preferences') {
      if (init.method === 'PUT') {
        weekStart = JSON.parse(String(init.body)).week_start; weekRevision++;
        weekOriginal = {state:'committed',archived_by:null,operation_id:'week-op',created_at:100,
          result:{week_start:weekStart,revision:weekRevision,member_id:memberId},message:'Saved.',action_required:'Review.'};
        throw new Error('Committed response lost');
      }
      raw=JSON.stringify({week_start:weekStart,revision:weekRevision});
    }
    else if (route.startsWith('tasks/calendar/preferences/requests/')) raw=JSON.stringify(weekOriginal);
    else if (route === 'family/allocation' && init.method === 'PUT') {
      const {definition_id, expected_revision, policy} = JSON.parse(String(init.body));
      raw = JSON.stringify({state:'committed',archived_by:null,operation_id:'points-policy',created_at:100,
        result:{definition_id,setting:{revision:expected_revision+1,policy}},message:'Saved.',action_required:'Review.'});
    }
    else if (init.method==='PUT') {
      if(route!=='administration/preferences')throw new Error('This fixture supports preference mutations only');
      putRequests++;const body=JSON.parse(init.body as string);preferenceLocale=body.locale;preferenceRevision++;
      preferenceReceipt={state:'committed',archived_by:null,operation_id:'profile-'+putRequests,created_at:JSON.parse(wire.session).context.server_time,
        result:preferences(),message:'Saved.',action_required:'Review current state.'};
      raw=JSON.stringify({...preferenceReceipt,notification_delivery:'unavailable'});
    }
    else if (route.startsWith('operations/')&&preferenceReceipt!==null)raw=JSON.stringify({...preferenceReceipt,delivery:'pending'});
    else if (route==='administration/capabilities') raw=JSON.stringify({state:'available',contract_version:2,household_id:'home',exact_revisions:'json-integer-int64',
      actions:['household.update','member.update','policy.update','member.presentation.update','member.preferences.update'],
      journal:{namespace:'administration',version:1,maximum_records:8,maximum_bytes:65536,lifetime_ms:3600000}});
    else if (route==='tasks/access') raw=JSON.stringify({household_id:'home',member_id:memberId,can_create:true,can_review_schedule:canReview,
      can_manage_points:canManagePoints,can_record_for_others:canManagePoints});
    else if (route === 'family/allocation' || route.startsWith('family/allocation?')) raw = JSON.stringify({household:null,override:null});
    else if (route === 'family/rewards/commands' && init.method === 'POST') {
      const payload = JSON.parse(String(init.body));
      raw = JSON.stringify({state:'committed',archived_by:null,operation_id:'reward-policy',created_at:100,
        result:{enabled:payload.enabled,revision:payload.expected_revision+1},message:'Saved.',action_required:'Review.'});
    }
    else if (route === 'inventory/commands' && init.method === 'POST') {
      const {name, base_unit} = JSON.parse(String(init.body));
      raw = JSON.stringify({state:'committed',archived_by:null,operation_id:'product-operation',created_at:100,
        result:{product_id:'product',name,base_unit},message:'Saved.',action_required:'Review.'});
    }
    else if (route.startsWith('inventory/products/product/movements?')) raw = JSON.stringify({
      product_id:'product', product_name:'Salt', base_unit:'gram', movements:[],
      next_cursor:route.includes('cursor=')?null:'older',
    });
    else if (route.startsWith('inventory/purchases/purchase/receipts?')) raw = JSON.stringify({
      purchase:{purchase_id:'purchase',product_id:null,name:'Apples',base_unit:'piece',purchased:'2',
        received:'0',remaining:'2',pending_stock:'0',revision:'1',member_id:'member',author_alias:null,created_at:'100'},
      receipts:[], next_cursor:route.includes('cursor=')?null:'older-receipts',
    });
    else if (route.startsWith('inventory/purchases?')) raw = JSON.stringify({
      purchases:[], next_cursor:route.includes('cursor=')?null:'older-purchases',
    });
    else if (route.startsWith('inventory/purchase-sessions?')) raw = JSON.stringify({
      sessions:[],next_cursor:route.includes('cursor=')?null:'older-sessions',
    });
    else if (route === 'inventory/purchase-sessions/session') {
      const session = {session_id:'session',member_id:'member',author_alias:null,created_at:'100'};
      const item = {purchase_id:'a',product_id:null,name:'Apples',base_unit:'piece',purchased:'2',
        received:'0',remaining:'2',pending_stock:'0',revision:'1',member_id:'member',author_alias:null,created_at:'100'};
      raw = JSON.stringify({session,items:[item,{...item,purchase_id:'b',name:'Bread'}]});
    }
    else if (route.startsWith('inventory/shopping-list/product/sources?')) raw = JSON.stringify({
      item:{product_id:'product',extra_id:null,name:'Salt',base_unit:'gram',pantry:'0',
        tasks:'0',manual:'0',total:'0',attribution:null},
      sources:[],next_cursor:route.includes('cursor=')?null:'more-sources',
    });
    else if (route.startsWith('inventory/shopping-list?')) raw = JSON.stringify({
      items:[],next_cursor:route.includes('cursor=')?null:'more-list',
    });
    else if (route.startsWith('inventory?')) raw = JSON.stringify({location_id:'pantry', may_manage:true, may_shop:true, may_request:true, products:[],
      next_cursor:route.includes('cursor=')?null:'inventory-next'});
    else if (route.startsWith('family/rewards?')) raw = JSON.stringify({
      enabled:false,revision:0,may_manage:canManagePoints,balance:{posted_minor:0,reserved_minor:0},
      catalog:[],requests:[],next_cursor:null,
    });
    else if (route.startsWith('family?')) {
      const query = new URLSearchParams(route.split('?')[1]);
      raw = JSON.stringify({period:{start:query.get('start'),end:query.get('end')},time_zone:'UTC',
        posted_minor:0,available_minor:0,reserved_minor:0,spent_in_period_minor:0,spending_count:0,spending:[],earned_minor:0,pending_verification_minor:0,pending_posting_minor:0,
        completed_count:0,tracked_count:0,elapsed_ms:0,pending_count:0,pending:[],history:[],next_cursor:query.has('cursor')?null:'family-next'});
    }
    else if (route.startsWith('tasks/calendar?')) {
      const query=new URLSearchParams(route.split('?')[1]);
      raw=JSON.stringify({period:{start:query.get('start'),end:query.get('end')},time_zone:'UTC',
        entries:[],count:0,occurrence_count:0,next_cursor:query.has('cursor')?null:'next-page',pending:false});
    }
    else if (route.startsWith('tasks/occurrences?')) raw=JSON.stringify({items:[],next_cursor:null});
    else if (route==='administration/preferences') raw=JSON.stringify(preferences());
    else if (route==='administration/roster') raw=JSON.stringify({directory_state:'available',members:[{
      member:{...originalAccess.member,member_id:memberId},presentation:presentation(),metadata:{state:'available',name:'Verified owner',avatar_state:'unavailable'}}]});
    else if (route==='administration/directory') raw=JSON.stringify({state:'available',profiles:[{ha_user_id:originalAccess.member.ha_user_id,name:'Verified owner'}]});
    else if (route==='administration/members/'+memberId+'/presentation') raw=JSON.stringify(presentation());
    else if (route==='policy') raw=JSON.stringify({household_id:'home',revision:1,mapping:{mode:'all_ha_administrators',target_ha_user_id:null},adjustments:[]});
    else if (init.method === 'POST') {postRequests++; phase = route === 'household' ? 'active' : 'pending'; raw = route === 'household' ? wire.setup : wire.enrollment;}
    else raw = wire.household;
    const response = new Response(raw, {headers: {'Content-Type': 'application/json', 'Cache-Control': 'no-store'}});
    Object.defineProperty(response, 'url', {value: wire.endpoint.origin + path}); return response;
  });
  const events = new EventTarget();
  const page: EntryPage = {document, location: {href: wire.endpoint.origin + wire.endpoint.applicationBase,
    assign: url => {navigation.push(String(url));}, reload: vi.fn()}, navigator: {language: locale},
    crypto, performance, fetch, sessionStorage: {getItem: key => values.get(key) ?? null,
      setItem: (key, value) => {values.set(key, value);}, removeItem: key => {values.delete(key);}},
    addEventListener: events.addEventListener.bind(events), removeEventListener: events.removeEventListener.bind(events),
    dispatchEvent: events.dispatchEvent.bind(events), setTimeout: window.setTimeout.bind(window), clearTimeout: window.clearTimeout.bind(window)};
  const open = async () => {const mounted = mountEntry(page); dispose.push(mounted.dispose); await mounted.ready;
    const app = root.querySelector<DomusApp>('domus-app')!; await app?.updateComplete; return {mounted, app};};
  return {root, data, page, open, values, navigation, fetch, events, postRequests: () => postRequests,
    putRequests:()=>putRequests,preferences:(locale:'en'|'es'|null,revision=1)=>{preferenceLocale=locale;preferenceRevision=revision;},
    member:(value:string)=>{memberId=value;},preferencesReadable:(value:boolean)=>{preferencesReadable=value;},
    phase: (value: string) => {phase = value;}};
}
function intent(app: DomusApp, detail: unknown) {app.dispatchEvent(new CustomEvent('domus-intent', {detail, bubbles: true, composed: true}));}
function administrationIntent(app:DomusApp,detail:unknown){app.dispatchEvent(new CustomEvent('domus-administration-intent',{detail,bubbles:true,composed:true}));}

test.each(['native','standalone'] as const)('HADB-03: %s document mounts the actual administration widget with current independently verified facts',async mode=>{
  const f=fixture(mode);f.phase('active');const {app}=await f.open();
  expect(app.administration?.preferences?.memberId).toBe('identity-1');
  const widget=app.shadowRoot!.querySelector<DomusAdministration>('domus-administration')!;await widget.updateComplete;
  expect(widget.view).toEqual(app.administration);expect(widget.shadowRoot!.textContent).toContain('Verified owner');expect(f.putRequests()).toBe(0);
});
test('household-browser-C18: saved locale wins, a temporary language stays local, and both higher and restored lower revisions reapply current preferences',async()=>{
  const f=fixture('standalone','en-GB');f.phase('active');f.preferences('es',4);const {app}=await f.open();
  expect(app.language).toBe('es');expect(document.documentElement.lang).toBe('es');
  intent(app,{type:'language',language:'en'});administrationIntent(app,{type:'refresh'});
  await vi.waitFor(()=>expect(app.view?.busy).toBe(false));expect(app.language).toBe('en');expect(f.putRequests()).toBe(0);
  f.preferences('es',5);administrationIntent(app,{type:'refresh'});await vi.waitFor(()=>expect(app.language).toBe('es'));
  f.preferences('en',1);administrationIntent(app,{type:'refresh'});await vi.waitFor(()=>expect(app.language).toBe('en'));
  expect(f.putRequests()).toBe(0);
});
test('household-browser-C18: unavailable own preferences use browser fallback and the same saved revision applies again when readable',async()=>{
  const f=fixture();f.phase('active');f.preferences('es',3);const {app}=await f.open();expect(app.language).toBe('es');
  f.preferencesReadable(false);administrationIntent(app,{type:'refresh'});await vi.waitFor(()=>expect(app.language).toBe('en'));
  f.preferencesReadable(true);administrationIntent(app,{type:'refresh'});await vi.waitFor(()=>expect(app.language).toBe('es'));
});
test('household-browser-C13: replacing the same-HA member clears the prior temporary language and private preference scope',async()=>{
  const f=fixture();f.phase('active');const {app}=await f.open();intent(app,{type:'language',language:'es'});
  f.member('replacement');administrationIntent(app,{type:'refresh'});
  await vi.waitFor(()=>expect(app.administration?.preferences?.memberId).toBe('replacement'));
  expect(app.language).toBe('en');expect(document.documentElement.lang).toBe('en');expect(f.putRequests()).toBe(0);
});
test.each([null,{},[],{type:'other'},{type:'refresh',url:'https://foreign.invalid'},
  {type:'submit',command:{action:'member.preferences.update',payload:{expected_revision:'1',locale:'es',routine_participation_summaries:true}},actor:'forged'},
  {type:'submit',command:{action:'member.preferences.update',payload:{expected_revision:'1',locale:'es',routine_participation_summaries:true,member_id:'forged'}}},
  {type:'recover',key:'../other'},{type:'dismiss',key:''}])('household-browser-C15: closed administration intent %j cannot select a principal or route',value=>{
    expect(decodeAdministrationIntent(value)).toBeNull();
});
test('HADB-03: valid administration intents retain the exact immutable command and have no principal selector',()=>{
  const command={action:'member.preferences.update',payload:{expected_revision:'9007199254740993',locale:null,routine_participation_summaries:false}};
  expect(decodeAdministrationIntent({type:'submit',command})).toEqual({type:'submit',command});
  expect(decodeAdministrationIntent({type:'recover',key:'original'})).toEqual({type:'recover',key:'original'});
  expect(decodeAdministrationIntent({type:'dismiss',key:'original'})).toEqual({type:'dismiss',key:'original'});
  expect(decodeAdministrationIntent({type:'refresh'})).toEqual({type:'refresh'});
});
test('HADB-03: a real mounted preference form reaches the protected HTTP adapter once and applies only freshly read saved locale',async()=>{
  const f=fixture();f.phase('active');const {app}=await f.open(),widget=app.shadowRoot!.querySelector<DomusAdministration>('domus-administration')!;
  await widget.updateComplete;const button=(name:string)=>[...widget.shadowRoot!.querySelectorAll('button')].find(value=>value.textContent?.trim()===name)!;
  button('Edit preferences').click();await widget.updateComplete;const select=widget.shadowRoot!.querySelector('select')!;
  select.value='es';select.dispatchEvent(new Event('change',{bubbles:true}));await widget.updateComplete;
  button('Review changes').click();await widget.updateComplete;expect(f.putRequests()).toBe(0);button('Save changes').click();
  await vi.waitFor(()=>{expect(f.putRequests()).toBe(1);expect(app.administration?.preferences?.locale).toBe('es');expect(app.view?.busy).toBe(false);});
  expect(app.language).toBe('es');expect(document.documentElement.lang).toBe('es');
  const mutation=f.fetch.mock.calls.find(([,init])=>init.method==='PUT')!;
  expect(mutation[0]).toBe('/api/v1/administration/preferences');
  expect(JSON.parse(mutation[1].body as string)).toEqual({expected_revision:1,locale:'es',routine_participation_summaries:true});
});
test('household-browser-C17: an explicit onboarding language survives a proof tick and first membership without saving a preference',async()=>{
  const f=fixture();let tick!:()=>void;f.page.setTimeout=callback=>{tick=callback;return 1;};f.page.clearTimeout=()=>{};
  const {app}=await f.open();intent(app,{type:'language',language:'es'});tick();expect(app.language).toBe('es');
  intent(app,{type:'setup',name:'Home',timeZone:'UTC'});
  await vi.waitFor(()=>expect(app.administration?.preferences?.memberId).toBe('identity-1'));
  expect(app.language).toBe('es');expect(app.administration?.preferences?.locale).toBeNull();expect(f.putRequests()).toBe(0);
});

test.each(['native','standalone'] as const)('%s page wires the owned view to actual controller/adapters without automatic mutation', async deployment => {
  const f = fixture(deployment, 'es-ES'), {app} = await f.open();
  expect(app.deployment).toBe(deployment); expect(app.language).toBe('es');
  expect(document.documentElement.lang).toBe('es'); expect(f.page.litNonce).toBe('a'.repeat(32));
  expect(app.view?.decision?.action).toBe('create_household'); expect(f.postRequests()).toBe(0);
  expect(f.fetch.mock.calls.every(([, init]) => init.method === 'GET')).toBe(true);
  intent(app, {type: 'setup', name: 'Maple House', timeZone: 'UTC'});
  await vi.waitFor(() => {expect(app.view?.household?.name).toBe('Home 🏠');});
  expect(f.postRequests()).toBe(1); expect(JSON.parse(f.values.get(ENTRY_JOURNAL_KEY)!).records[0].stage).toBe('committed');
});
test('deliberate enrollment, refresh, original-request recovery and dismissal route through the controller', async () => {
  const f = fixture(); f.phase('eligible'); const {app} = await f.open();
  intent(app, {type: 'request_membership'}); await vi.waitFor(() => {expect(app.view?.decision?.state).toBe('pending');});
  const key = app.view!.journal!.records[0].key;
  intent(app, {type: 'refresh'}); await vi.waitFor(() => {expect(app.view?.phase).toBe('ready');});
  intent(app, {type: 'recover', key}); await vi.waitFor(() => {expect(f.postRequests()).toBe(2);});
  await vi.waitFor(() => {expect(app.view?.busy).toBe(false);});
  intent(app, {type: 'dismiss', key}); await vi.waitFor(() => {expect(app.view?.journal?.records).toEqual([]);});
});
test('language is presentation-only, and navigation has only fixed reviewed destinations', async () => {
  const f = fixture(), {app} = await f.open(); const calls = f.fetch.mock.calls.length;
  intent(app, {type: 'language', language: 'es'}); expect(app.language).toBe('es'); expect(document.documentElement.lang).toBe('es');
  expect(f.fetch).toHaveBeenCalledTimes(calls); intent(app, {type: 'sign_in'}); intent(app, {type: 'reopen'});
  expect(f.navigation).toEqual(['/api/v1/auth/start','/']);
});
test('logout closes local access and keeps explicit deployment-specific reentry available', async () => {
  const f = fixture(), {app} = await f.open();
  f.values.set(REWARD_JOURNAL_KEY, 'private pending reward');
  f.values.set(ALLOCATION_JOURNAL_KEY, 'private pending policy');
  f.values.set(CALENDAR_JOURNAL_KEY, 'private pending preference');
  f.values.set(RECURRENCE_JOURNAL_KEY, 'private pending schedule change');
  intent(app, {type: 'logout'});
  await vi.waitFor(() => {
    expect(app.view?.notice).toBe('signed_out');
    expect(f.values.has(REWARD_JOURNAL_KEY)).toBe(false);
    expect(f.values.has(ALLOCATION_JOURNAL_KEY)).toBe(false);
    expect(f.values.has(CALENDAR_JOURNAL_KEY)).toBe(false);
    expect(f.values.has(RECURRENCE_JOURNAL_KEY)).toBe(false);
  });
  expect(f.values.has(ENTRY_JOURNAL_KEY)).toBe(false); intent(app, {type: 'sign_in'});
  expect(f.navigation).toEqual(['/api/v1/auth/start']);
});
test('detaching the owned component retires reads, events and future commands', async () => {
  const f = fixture(), {app, mounted} = await f.open(); app.remove(); const calls = f.fetch.mock.calls.length;
  intent(app, {type: 'setup', name: 'Home', timeZone: 'UTC'}); await Promise.resolve(); mounted.dispose();
  expect(app.view?.phase).toBe('closed'); expect(f.fetch).toHaveBeenCalledTimes(calls);
});
test('only intents from the actual owned component are accepted', async () => {
  const f = fixture(), {app} = await f.open(), child = document.createElement('span'); app.append(child);
  child.dispatchEvent(new CustomEvent('domus-intent', {detail: {type: 'setup', name: 'Foreign', timeZone: 'UTC'}, bubbles: true}));
  app.dispatchEvent(new Event('domus-intent')); intent(app, {type: 'setup', name: 42, timeZone: 'UTC'});
  expect(f.postRequests()).toBe(0);
});
test.each(['missing-data','duplicate-data','wrong-type','bad-json','wrong-location','missing-root'] as const)(
  '%s yields an owned safe fallback without reading storage or sending API requests', async failure => {
    const f = fixture();
    if (failure === 'missing-data') f.data.remove();
    if (failure === 'duplicate-data') {const extra = f.data.cloneNode(true) as Element; document.head.append(extra); nodes.push(extra);}
    if (failure === 'wrong-type') f.data.type = 'text/javascript';
    if (failure === 'bad-json') f.data.textContent = 'Private raw malformed data';
    if (failure === 'wrong-location') f.page.location.href = 'https://domus.example/wrong';
    if (failure === 'missing-root') f.root.remove();
    const mounted = mountEntry(f.page); dispose.push(mounted.dispose); await mounted.ready;
    const error = document.querySelector('#domus-entry-error')!;
    expect(error.textContent).toContain('Household status unavailable'); expect(error.textContent).not.toContain('Private raw');
    expect(f.fetch).not.toHaveBeenCalled(); error.querySelector('button')!.click(); expect(f.page.location.reload).toHaveBeenCalledOnce();
  });
test('unavailable storage and navigation failures never get another endpoint or implicit command', async () => {
  const f = fixture(); Object.defineProperty(f.page, 'sessionStorage', {get: () => {throw new Error('Private provider');}});
  const {app} = await f.open(); expect(app.view?.notice).toBe('journal_unavailable');
  f.page.location.assign = () => {throw new Error('Private navigation error');}; intent(app, {type: 'sign_in'});
  await vi.waitFor(() => {expect(document.querySelector('#domus-entry-error')).not.toBeNull();}); expect(f.postRequests()).toBe(0);
});
test('initial scheduling refusal has an owned fallback and a refused reload stays explicitly disabled', async () => {
  const f = fixture(); f.page.setTimeout = () => {throw new Error('Private timer failure');};
  f.page.location.reload = () => {throw new Error('Private reload failure');};
  const mounted = mountEntry(f.page); dispose.push(mounted.dispose); await mounted.ready;
  const error = document.querySelector('#domus-entry-error')!, button = error.querySelector('button')!;
  button.click(); expect(button.disabled).toBe(true); expect(error.textContent).not.toContain('Private');
});
test('later scheduling refusal replaces closed controls with an actual reload fallback', async () => {
  const f = fixture(); let tick!: () => void;
  f.page.setTimeout = callback => {tick = callback; return 1;}; f.page.clearTimeout = () => {};
  const {app} = await f.open(); f.page.setTimeout = () => {throw new Error('Private later timer failure');};
  expect(() => tick()).not.toThrow(); expect(app.isConnected).toBe(false);
  document.querySelector<HTMLButtonElement>('#domus-entry-error button')!.click();
  expect(f.page.location.reload).toHaveBeenCalledOnce(); expect(f.postRequests()).toBe(0);
});
test('replacing a page mount retires the previous generation and does not let its disposer remove the new one', async () => {
  const f = fixture(), first = await f.open(), second = await f.open(); first.mounted.dispose();
  expect(first.app.view?.phase).toBe('closed'); intent(second.app, {type: 'language', language: 'es'});
  expect(second.app.language).toBe('es');
});
test('ordinary pagehide disposes the page; a persisted hide remains owned for fresh runtime restoration', async () => {
  const f = fixture(), {app} = await f.open(); f.events.dispatchEvent(new PageTransitionEvent('pagehide', {persisted: true}));
  f.events.dispatchEvent(new PageTransitionEvent('pageshow', {persisted: true}));
  await vi.waitFor(() => {expect(app.view?.decision?.action).toBe('create_household');});
  f.events.dispatchEvent(new Event('pagehide')); const calls = f.fetch.mock.calls.length;
  intent(app, {type: 'refresh'}); expect(f.fetch).toHaveBeenCalledTimes(calls);
});
test.each([null, [], {}, {type: 'other'}, {type: 'refresh', url: 'https://foreign.invalid'},
  {type: 'setup', name: 'Home', timeZone: 'UTC', ha_user_id: 'forged'},
  {type: 'setup', name: {}, timeZone: 'UTC'}, {type: 'setup', name: 'Home', timeZone: false},
  {type: 'recover', key: '../new'}, {type: 'dismiss', key: ''}, {type: 'language', language: 'fr'},
])('untrusted DOM intent %s is discarded as a closed value', value => {expect(decodeIntent(value)).toBeNull();});
test('the actual module entrypoint starts safely and refuses the test runner location as a product root', async () => {
  const f = fixture(); await import('../src/composition/main');
  expect(document.querySelector('#domus-entry-error')).not.toBeNull(); expect(f.fetch).not.toHaveBeenCalled();
  const mounted = mountEntry(f.page); dispose.push(mounted.dispose); await mounted.ready;
});

test('HADB-02: owned administration events recover the actual original by protected GET and dismiss only after resolution',async()=>{
  const f=fixture();f.phase('active');const {app}=await f.open();administrationIntent(app,{type:'submit',command:{action:'member.preferences.update',
    payload:{expected_revision:'1',locale:'es',routine_participation_summaries:true}}});
  await vi.waitFor(()=>{expect(app.administration?.outcome).toMatchObject({kind:'receipt',stage:'committed'});expect(app.view?.busy).toBe(false);});
  const key=app.administration!.journal!.records[0].key,calls=f.fetch.mock.calls.length;
  administrationIntent(app,{type:'recover',key});await vi.waitFor(()=>{expect(f.fetch.mock.calls.slice(calls).some(([path,init])=>path.endsWith('/operations/profile-1')&&init.method==='GET')).toBe(true);expect(app.view?.busy).toBe(false);});
  expect(f.putRequests()).toBe(1);administrationIntent(app,{type:'dismiss',key});await vi.waitFor(()=>expect(app.administration?.journal?.records).toEqual([]));expect(f.putRequests()).toBe(1);
});
test('HADB-03: foreign and malformed administration events cannot drive the owned page',async()=>{
  const f=fixture();f.phase('active');const {app}=await f.open(),child=document.createElement('span');app.append(child);const before=f.fetch.mock.calls.length;
  child.dispatchEvent(new CustomEvent('domus-administration-intent',{detail:{type:'refresh'},bubbles:true}));
  administrationIntent(app,{type:'refresh',url:'https://foreign.invalid'});app.dispatchEvent(new Event('domus-administration-intent'));await Promise.resolve();
  expect(f.fetch).toHaveBeenCalledTimes(before);expect(f.putRequests()).toBe(0);
});
test('HADB-03: an exceptional owned administration event replaces controls with safe reload guidance',async()=>{
  const f=fixture();f.phase('active');const {app}=await f.open(),event=new Event('domus-administration-intent');
  Object.defineProperty(event,'detail',{get:()=>{throw new Error('Private malformed event source');}});app.dispatchEvent(event);
  await vi.waitFor(()=>expect(document.querySelector('#domus-entry-error')).not.toBeNull());
  expect(document.querySelector('#domus-entry-error')!.textContent).not.toContain('Private');expect(app.isConnected).toBe(false);expect(f.putRequests()).toBe(0);
});
test('household-browser-C18: temporary language persists while current own preferences are unavailable without saving them',async()=>{
  const f=fixture();f.phase('active');const {app}=await f.open();f.preferencesReadable(false);administrationIntent(app,{type:'refresh'});
  await vi.waitFor(()=>{expect(app.administration?.preferences).toBeNull();expect(app.view?.busy).toBe(false);});
  intent(app,{type:'language',language:'es'});administrationIntent(app,{type:'refresh'});await vi.waitFor(()=>expect(app.view?.busy).toBe(false));
  expect(app.language).toBe('es');expect(f.putRequests()).toBe(0);
});
test('household-browser-C18: a signed-out language choice has no identity or mutation side effect',async()=>{
  const f=fixture();const {app}=await f.open();intent(app,{type:'logout'});await vi.waitFor(()=>expect(app.view?.notice).toBe('signed_out'));
  const count=f.fetch.mock.calls.length;intent(app,{type:'language',language:'es'});expect(app.language).toBe('es');expect(f.fetch).toHaveBeenCalledTimes(count);expect(f.putRequests()).toBe(0);
});


test.each([null, {}, [], {type: 'future'}, {type: 'refresh', actor: 'forged'},
  {type: 'create', title: 'Task', description: '', priority: 'normal', householdId: 'forged'},
  {type: 'create', title: 1, description: '', priority: 'normal'}, {type: 'create', title: 'Task', description: '', priority: 'future'},
  {type: 'complete', materialUsages: true}, {type: 'complete', materialUsages: [{line_id: 'line', quantity: '1.0'}]},
  {type: 'verify', decision: 'pending', reason: 'A'}, {type: 'reopen', reason: 1}, {type: 'select', occurrenceId: '../other'},
  {type: 'recover', key: ''}, {type:'createCategory', label:2}, {type:'renameCategory', categoryId:'garden', revision:'1', label:2}])('task event %# cannot select a principal, route or arbitrary command', value => {
    expect(decodeTaskIntent(value)).toBeNull();
});
test('closed task events preserve semantic user inputs and exact material quantities', () => {
  const inputs = [{type:'createCategory', label:'Garden'}, {type:'renameCategory', categoryId:'garden', revision:'9007199254740993', label:'Garden'},
    {type:'archiveCategory', categoryId:'garden', revision:'9007199254740993'},
    {type:'create', title:'Clean', description:'', priority:'normal', categoryId:'garden'}, {type: 'refresh'}, {type: 'more'}, {type: 'claim'}, {type: 'select', occurrenceId: 'work-1'},
    {type: 'create', title: '  Clean 🧹  ', description: '', priority: 'high'}, {type: 'complete', materialUsages: null},
    {type: 'complete', materialUsages: [{line_id: 'line-1', quantity: '3.333333'}]},
    {type: 'verify', decision: 'approved', reason: ''}, {type: 'verify', decision: 'rejected', reason: 'Not done'},
    {type: 'reopen', reason: 'Repeat'}, {type: 'recover', key: 'original'}, {type: 'dismiss', key: 'original'}];
  for (const value of inputs) expect(decodeTaskIntent(value)).toEqual(value);
});
test('the mounted task surface routes only owned semantic intents to its application controller', async () => {
  const f = fixture(); f.phase('active'); const {app} = await f.open(); expect(app.tasks?.access?.memberId).toBe('identity-1');
  const spies = {create: vi.spyOn(TaskController.prototype, 'create').mockResolvedValue(undefined),
    createCategory: vi.spyOn(TaskController.prototype, 'createCategory').mockResolvedValue(undefined),
    renameCategory: vi.spyOn(TaskController.prototype, 'renameCategory').mockResolvedValue(undefined),
    archiveCategory: vi.spyOn(TaskController.prototype, 'archiveCategory').mockResolvedValue(undefined),
    more: vi.spyOn(TaskController.prototype, 'more').mockResolvedValue(undefined), select: vi.spyOn(TaskController.prototype, 'select').mockResolvedValue(undefined),
    claim: vi.spyOn(TaskController.prototype, 'claim').mockResolvedValue(undefined), complete: vi.spyOn(TaskController.prototype, 'complete').mockResolvedValue(undefined),
    verify: vi.spyOn(TaskController.prototype, 'verify').mockResolvedValue(undefined), reopen: vi.spyOn(TaskController.prototype, 'reopen').mockResolvedValue(undefined),
    recover: vi.spyOn(TaskController.prototype, 'recover').mockResolvedValue(undefined), dismiss: vi.spyOn(TaskController.prototype, 'dismiss').mockResolvedValue(undefined),
    refresh: vi.spyOn(TaskController.prototype, 'refresh').mockResolvedValue(undefined)};
  const send = (detail: unknown, target: EventTarget = app) => target.dispatchEvent(new CustomEvent('domus-task-intent', {detail, bubbles: true, composed: true}));
  try {
    const child = document.createElement('span'); app.append(child); send({type: 'create', title: 'Other target', description: '', priority: 'normal'}, child);
    send({type: 'create', title: 'Forged actor', description: '', priority: 'normal', actor: 'other'}); await Promise.resolve(); expect(spies.create).not.toHaveBeenCalled();
    const review = {occurrenceId:'work-1',revision:'1',performerIds:['identity-1','other'],fingerprint:'c'.repeat(64)};
    const cases: readonly [unknown, keyof typeof spies, readonly unknown[]][] = [
      [{type: 'create', title: 'Clean', description: 'Wipe', priority: 'high'}, 'create', ['Clean', 'Wipe', 'high', undefined, undefined]],
      [{type: 'create', title: 'Clean', description: 'Wipe', priority: 'high',
        schedule: {kind: 'fixed', start: {kind: 'date', local: '2027-01-02'}, rrule: 'FREQ=WEEKLY'}},
      'create', ['Clean', 'Wipe', 'high', {kind: 'fixed', start: {kind: 'date', local: '2027-01-02'}, rrule: 'FREQ=WEEKLY'}, undefined]],
      [{type:'createCategory', label:'Garden'}, 'createCategory', ['Garden']],
      [{type:'renameCategory', categoryId:'garden', revision:'1', label:'Garden'}, 'renameCategory', ['garden', '1', 'Garden']],
      [{type:'archiveCategory', categoryId:'garden', revision:'1'}, 'archiveCategory', ['garden', '1']],
      [{type: 'more'}, 'more', []], [{type: 'select', occurrenceId: 'work-1'}, 'select', ['work-1']], [{type: 'claim'}, 'claim', []],
      [{type: 'complete', materialUsages: null}, 'complete', [null]],
      [{type: 'complete', materialUsages: null, reviewed: review}, 'complete', [null, review]], [{type: 'verify', decision: 'approved', reason: ''}, 'verify', ['approved', '']],
      [{type: 'reopen', reason: 'Repeat'}, 'reopen', ['Repeat']], [{type: 'recover', key: 'original'}, 'recover', ['original']],
      [{type: 'dismiss', key: 'original'}, 'dismiss', ['original']], [{type: 'refresh'}, 'refresh', []],
    ];
    for (const [detail, method, args] of cases) {send(detail); await vi.waitFor(() => expect(app.view?.busy).toBe(false)); expect(spies[method]).toHaveBeenCalledWith(...args);}
    expect(f.putRequests()).toBe(0); expect(f.postRequests()).toBe(0);
  } finally {for (const spy of Object.values(spies)) spy.mockRestore();}
});
test('an unexpected task delegation failure closes the runtime and shows the bounded failure view', async () => {
  const f = fixture(); f.phase('active'); const {app} = await f.open();
  const spy = vi.spyOn(TaskController.prototype, 'create').mockRejectedValue(Error('private delegation fault'));
  try {app.dispatchEvent(new CustomEvent('domus-task-intent', {detail: {type: 'create', title: 'Clean', description: '', priority: 'normal'}}));
    await vi.waitFor(() => expect(document.querySelector('#domus-entry-error')).not.toBeNull());
    expect(document.querySelector('#domus-entry-error')!.textContent).not.toContain('private delegation fault');
  } finally {spy.mockRestore();}
});

test('workspace fragments preserve the mounted administration and stop after disposal', async () => {
  const f = fixture('native');
  const base = f.page.location.href;
  const route = (fragment: string) => {
    f.page.location.href = base + fragment;
    f.events.dispatchEvent(new Event('hashchange'));
  };
  f.phase('active');
  route('#household');
  const {app, mounted} = await f.open();
  const tabs = () => app.shadowRoot!.querySelector('vyp-ha-tabs')!;
  const widget = app.shadowRoot!.querySelector('domus-administration');
  expect(tabs()).not.toBeNull();
  expect(tabs().state.selected).toBe('household');
  expect(app.shadowRoot!.activeElement?.id).toBe('household');
  const select = (kind: 'navigation' | 'panels', id: string) => tabs().dispatchEvent(
    new CustomEvent('ha-selection-request', {detail: {kind, id}, cancelable: true}));
  const state = tabs().state;
  app.view = {...app.view!};
  await app.updateComplete;
  expect(tabs().state).toBe(state);
  const language = app.shadowRoot!.querySelector('select')!;
  language.focus();
  expect(select('panels', 'household')).toBe(true);
  expect(select('navigation', 'overview')).toBe(true);
  expect(app.shadowRoot!.activeElement).toBe(language);
  expect(select('navigation', 'household')).toBe(false);
  expect(app.shadowRoot!.activeElement?.id).toBe('household');
  route('#overview');
  await app.updateComplete;
  expect(tabs().state.selected).toBe('overview');
  expect(app.shadowRoot!.activeElement?.id).toBe('overview');
  route('#tasks');
  await app.updateComplete;
  expect(tabs().state.selected).toBe('tasks');
  expect(app.shadowRoot!.activeElement?.id).toBe('tasks');
  route('#household%2Fprivate');
  await app.updateComplete;
  expect(tabs().state.selected).toBe('overview');
  expect(f.page.location.href).toBe(base + '#household%2Fprivate');
  expect(select('navigation', 'overview')).toBe(true);
  expect(app.shadowRoot!.querySelector('domus-administration')).toBe(widget);
  expect(f.putRequests()).toBe(0);
  mounted.dispose();
  route('#household');
  await app.updateComplete;
  expect(app.workspaceDestination).toBeNull();
  expect(tabs()).toBeNull();
});

test('unverified and retired views do not expose the household destination', async () => {
  const f = fixture();
  f.page.location.href += '#household';
  const {app} = await f.open();
  const tabs = () => app.shadowRoot!.querySelector('vyp-ha-tabs');
  expect(tabs()).toBeNull();
  f.phase('active');
  intent(app, {type: 'refresh'});
  await vi.waitFor(() => expect(tabs()).not.toBeNull());
  app.view = {...app.view!, notice: 'context_changed'};
  await app.updateComplete;
  expect(tabs()).toBeNull();
});

test('calendar composition accepts bounded reads only on the verified route and clears them on navigation', async () => {
  const query = {start:'2026-11-01',end:'2026-12-01',kind:'',timing:'',state:'',priority:'',category:'',own:true};
  expect(decodeCalendarIntent({type:'load',query})).toEqual({type:'load',query});
  expect(decodeCalendarIntent({type:'more'})).toEqual({type:'more'});
  for (const day of ['monday','sunday']) expect(decodeCalendarIntent({type:'setWeekStart',weekStart:day})).toEqual({type:'setWeekStart',weekStart:day});
  expect(decodeCalendarIntent({type:'setWeekStart',weekStart:'tuesday'})).toBeNull();
  expect(decodeCalendarIntent({type:'recoverPreference'})).toEqual({type:'recoverPreference'});
  expect(decodeCalendarIntent({type:'refreshPreference'})).toEqual({type:'refreshPreference'});
  for (const value of [{type:'load'}, {type:'load',query:{...query,member:'another'}}, {type:'more',query}, {type:'refresh'}, null]) {
    expect(decodeCalendarIntent(value)).toBeNull();
  }
  const f=fixture();f.phase('active');const {app}=await f.open();
  const sends=(detail:unknown,target:EventTarget=app)=>target.dispatchEvent(new CustomEvent('domus-calendar-intent',{detail,bubbles:true,composed:true}));
  const calls=()=>f.fetch.mock.calls.filter(([path])=>path.includes('/tasks/calendar?'));
  sends({type:'load',query});expect(calls()).toHaveLength(0);
  const navigate=(fragment:string)=>{
    f.page.location.href=f.page.location.href.split('#')[0]+fragment;
    f.events.dispatchEvent(new Event('hashchange'));
  };
  navigate('#calendar');
  await vi.waitFor(()=>expect(app.calendar?.status).toBe('ready'));
  expect(calls()).toHaveLength(1);
  sends({type:'load',query},app.querySelector('span')??app.appendChild(document.createElement('span')));
  sends({type:'invalid'});expect(calls()).toHaveLength(1);
  sends({type:'load',query});await vi.waitFor(()=>expect(app.calendar?.page?.cursor).toBe('next-page'));
  expect(calls()[1][0]).toContain('member_id=identity-1');
  sends({type:'more'});await vi.waitFor(()=>expect(app.calendar?.page?.cursor).toBe(null));
  expect(calls()[2][0]).toContain('cursor=next-page');
  await vi.waitFor(()=>expect(app.calendarPreference?.value?.weekStart).toBe('monday'));
  sends({type:'refreshPreference'});
  await vi.waitFor(()=>expect(app.calendarPreference?.busy).toBe(false));
  sends({type:'setWeekStart',weekStart:'sunday'});
  await vi.waitFor(()=>expect(app.calendarPreference?.notice).toBe('preferenceUncertain'));
  sends({type:'recoverPreference'});
  await vi.waitFor(()=>expect(app.calendarPreference?.value?.weekStart).toBe('sunday'));
  expect(app.calendarPreference?.pending).toBe(false);
  navigate('#tasks');expect(app.calendarScopeKey).toBeNull();expect(app.calendar?.page).toBeNull();
  sends({type:'more'});expect(calls()).toHaveLength(3);
});

test('review composition accepts only closed events in the current task manager workspace', async () => {
  const draft = {kind:'attachment',date:'2026-12-01',time:'',zone:'UTC',interval:'30',
    visibility:'at_completion',choice:'adopt',fold:'first_instant',reason:'',rrule:''};
  expect(decodeReviewIntent({type:'preview',draft})).toEqual({type:'preview',draft});
  for (const value of [null,{type:'preview'}, {type:'preview',draft:{...draft, actor:'forged'}},
    {type:'open',key:'original'}, {type:'recover',key:'../x'}, {type:'resend'}]) {
    expect(decodeReviewIntent(value)).toBeNull();
  }
  const f=fixture('standalone','en',true); f.phase('active'); const {app}=await f.open();
  const navigate=(fragment:string)=>{
    f.page.location.href=f.page.location.href.split('#')[0]+fragment;
    f.events.dispatchEvent(new Event('hashchange'));
  };
  const send=(detail:unknown,target:EventTarget=app)=>target.dispatchEvent(new CustomEvent('domus-review-intent',{detail,bubbles:true,composed:true}));
  send({type:'open'}); expect(app.recurrenceReview).toBeNull();
  navigate('#tasks'); expect(app.recurrenceReview?.open).toBe(false);
  const nested=app.appendChild(document.createElement('span'));
  send({type:'open'},nested); send({type:'resend'}); expect(app.recurrenceReview?.open).toBe(false);
  send({type:'open'}); expect(app.recurrenceReview?.open).toBe(true);
  send({type:'preview',draft}); send({type:'apply'}); send({type:'recover',key:'saved'}); send({type:'forget',key:'saved'});
  expect(f.fetch.mock.calls.some(([path])=>path.includes('recurrence/reviews'))).toBe(false);
  send({type:'close'}); expect(app.recurrenceReview?.open).toBe(false);
  navigate('#household'); expect(app.recurrenceReview).toBeNull();
});

test.each(['native','standalone'] as const)('Family fetches only for the verified %s workspace and retires on navigation',async mode=>{
  const f=fixture(mode); f.phase('active'); const {app}=await f.open();
  const calls=()=>f.fetch.mock.calls.filter(([path])=>path.includes('/api/v1/family?'));
  const navigate=(fragment:string)=>{
    f.page.location.href=f.page.location.href.split('#')[0]+fragment;
    f.events.dispatchEvent(new Event('hashchange'));
  };
  const send=(detail:unknown)=>app.dispatchEvent(new CustomEvent('domus-family-intent',{detail}));
  expect(calls()).toHaveLength(0);
  navigate('#family');
  await vi.waitFor(()=>expect(app.family?.state).toBe('ready'));
  expect(calls()).toHaveLength(1);
  send(null); send({type:'period',mode:'day',anchor:'2026-05-31'});
  send({type:'period',mode:'week',anchor:'2026-02-30'});
  expect(calls()).toHaveLength(1);
  send({type:'period',mode:'month',anchor:'2026-05-31'});
  await vi.waitFor(()=>expect(app.family?.report?.period).toEqual({start:'2026-05-01',end:'2026-06-01'}));
  send({type:'period',mode:'week',anchor:'2026-05-31'});
  await vi.waitFor(()=>expect(app.family?.report?.period).toEqual({start:'2026-05-25',end:'2026-06-01'}));
  send({type:'more'}); await vi.waitFor(()=>expect(app.family?.report?.cursor).toBe(null));
  expect(calls().at(-1)?.[0]).toContain('cursor=family-next');
  send({type:'refresh'}); await vi.waitFor(()=>expect(app.family?.report?.cursor).toBe('family-next'));
  navigate('#tasks');
  expect(app.familyScopeKey).toBeNull(); expect(app.family).toBeNull();
});

test('mounted allocation uses only current workspace and owned closed intents', async () => {
  const f = fixture('standalone', 'en', false, true);
  f.phase('active');
  const base = f.page.location.href;
  const navigate = (fragment: string) => {
    f.page.location.href = base + fragment;
    f.events.dispatchEvent(new Event('hashchange'));
  };
  const {app} = await f.open();
  const events = (name: string, detail: unknown, target: EventTarget = app) =>
    target.dispatchEvent(new CustomEvent(name, {detail, bubbles: true, composed: true}));
  navigate('#family');
  await vi.waitFor(() => expect(app.allocation?.settings).toEqual({household: null, override: null}));
  const roster = app.administration!.roster!;
  const unnamed = roster.members[0];
  app.administration = {...app.administration!, roster: {...roster, members: [
    {...unnamed, metadata: {...unnamed.metadata, name: null}},
  ]}};
  await app.updateComplete;
  events('domus-allocation-settings', {type: 'save', policy: {mode: 'conserve_total', precision: 0, rounding: null}});
  await vi.waitFor(() => expect(app.allocation?.notice).toBe('saved'));
  const save = vi.spyOn(AllocationController.prototype, 'save').mockResolvedValue(undefined);
  const recover = vi.spyOn(AllocationController.prototype, 'recover').mockResolvedValue(undefined);
  const preview = vi.spyOn(AllocationController.prototype, 'preview').mockResolvedValue(undefined);
  const policy = {mode: 'equal_share', precision: 2, rounding: 'floor'};
  const name = 'domus-allocation-settings';
  const unowned = document.createElement('span'); app.append(unowned);
  try {
    events(name, {type: 'save', policy}, unowned);
    events(name, {type: 'save', policy, member: 'forged'});
    events(name, {type: 'anything'});
    events('domus-allocation-preview', {performerIds: ['owner']}, unowned);
    events('domus-allocation-preview', {performerIds: ['owner'], context: 'forged'});
    expect(save).not.toHaveBeenCalled();
    expect(preview).not.toHaveBeenCalled();
    events(name, {type: 'save', policy});
    events(name, {type: 'save', policy: null});
    expect(save.mock.calls).toEqual([[policy], [null]]);
    events(name, {type: 'recover'}); expect(recover).toHaveBeenCalledOnce();
    events(name, {type: 'refresh'});
    const performerIds = ['identity-1', 'other'];
    const manualShares = [{member_id: 'identity-1', amount_minor: 0}, {member_id: 'other', amount_minor: 100}];
    events('domus-allocation-preview', {performerIds, manualShares});
    events('domus-allocation-preview', {performerIds});
    expect(preview.mock.calls).toEqual([[{performerIds, manualShares}], [{performerIds}]]);
    const revision = revisionValue('1');
    const reviewed = {performerIds, manualShares, occurrenceId: 'selected', revision, fingerprint: 'c'.repeat(64)};
    expect(decodeTaskIntent({type: 'complete', materialUsages: null, reviewed})).toEqual({type: 'complete', materialUsages: null, reviewed});
    expect(decodeTaskIntent({type: 'complete', materialUsages: null, reviewed: {...reviewed, manualShares: undefined}})).toBeNull();
    const withoutManual = {performerIds, occurrenceId: 'selected', revision, fingerprint: 'c'.repeat(64)};
    expect(decodeTaskIntent({type: 'complete', materialUsages: null, reviewed: withoutManual})).toMatchObject({reviewed: withoutManual});
    app.tasks = {...app.tasks!, detail: {occurrenceId: 'selected', definitionId: 'definition', definitionRevision: revision,
      title: 'Work', description: '', priority: 'normal', state: 'available', revision, assigneeIds: [], dueAt: null, currentCycleId: null,
      allowedActions: ['complete'], cycle: null, materials: [], materialRecording: 'separate_recording', pendingMaterials: false,
      dependencyReviewRequired: false}};
    navigate('#tasks');
    await vi.waitFor(() => expect(app.allocation?.scope.work?.occurrenceId).toBe('selected'));
    expect(app.allocation?.scope.canManage).toBe(true);
    navigate('#overview');
    expect(app.allocation).toBeNull();
  } finally {save.mockRestore(); recover.mockRestore(); preview.mockRestore();}
});

test('mounted rewards accept only owned semantic intents and retire on navigation', async () => {
  const f = fixture('native', 'en', false, true);
  f.phase('active');
  const base = f.page.location.href;
  const navigate = (fragment: string) => {
    f.page.location.href = base + fragment;
    f.events.dispatchEvent(new Event('hashchange'));
  };
  const {app} = await f.open();
  const send = (detail: unknown, target: EventTarget = app) =>
    target.dispatchEvent(new CustomEvent('domus-rewards-intent', {detail, bubbles: true, composed: true}));
  navigate('#family');
  await vi.waitFor(() => expect(app.rewards?.report?.mayManage).toBe(true));
  const attempts = () => f.fetch.mock.calls.filter(([path]) => path.includes('/family/rewards/commands')).length;
  const command = {action: 'reward.configure', enabled: true, expected_revision: '0'};
  const unowned = document.createElement('span'); app.append(unowned);
  send({type: 'submit', command}, unowned);
  send({type: 'submit', command, actor: 'forged'});
  send({type: 'anything'});
  send({type: 'refresh', command});
  expect(attempts()).toBe(0);
  send({type: 'more'}); send({type: 'recover'}); send({type: 'refresh'});
  await vi.waitFor(() => expect(app.rewards?.busy).toBe(false));
  send({type: 'submit', command});
  await vi.waitFor(() => expect(app.rewards?.result).toEqual({kind: 'committed', stage: null}));
  expect(attempts()).toBe(1);
  expect(f.values.has(REWARD_JOURNAL_KEY)).toBe(false);
  navigate('#overview');
  expect(app.rewards).toBeNull();
});


test('Inventory owns the current protected destination and accepts only closed user intents', async () => {
  const f = fixture(); f.phase('active'); const {app} = await f.open();
  const navigate = (fragment: string) => {
    f.page.location.href = f.page.location.href.split('#')[0] + fragment;
    f.events.dispatchEvent(new Event('hashchange'));
  };
  const emit = (detail: unknown, target: EventTarget = app) =>
    target.dispatchEvent(new CustomEvent('domus-inventory-intent', {detail,bubbles:true,composed:true}));
  const reads = () => f.fetch.mock.calls.filter(([path]) => path.includes('/api/v1/inventory?'));
  expect(reads()).toHaveLength(0);
  navigate('#inventory');
  await vi.waitFor(() => expect(app.inventory?.report?.cursor).toBe('inventory-next'));
  expect(reads()).toHaveLength(1);
  const nested = app.appendChild(document.createElement('span'));
  emit({type:'refresh'}, nested);
  emit({type:'arbitrary'}); emit({type:'refresh', command:{}});
  expect(reads()).toHaveLength(1);
  emit({type:'more'});
  await vi.waitFor(() => expect(app.inventory?.report?.cursor).toBe(null));
  emit({type:'refresh'});
  await vi.waitFor(() => expect(app.inventory?.report?.cursor).toBe('inventory-next'));
  emit({type:'recover'});
  emit({type:'submit', command:{action:'inventory.register-product',name:'Salt',base_unit:'gram'}});
  await vi.waitFor(() => expect(app.inventory?.result).toMatchObject({kind:'committed', productId:'product'}));
  expect(f.values.has(INVENTORY_JOURNAL_KEY)).toBe(false);
  await vi.waitFor(() => expect(app.inventory?.busy).toBe(false));
  emit({type:'history',productId:'product'});
  await vi.waitFor(() => expect(app.inventory?.history?.cursor).toBe('older'));
  emit({type:'more-history'});
  await vi.waitFor(() => expect(app.inventory?.history?.cursor).toBeNull());
  emit({type:'close-history'});
  expect(app.inventory?.history).toBeNull();
  emit({type:'purchases'});
  await vi.waitFor(() => expect(app.inventory?.purchases?.cursor).toBe('older-purchases'));
  emit({type:'more-purchases'});
  await vi.waitFor(() => expect(app.inventory?.purchases?.cursor).toBeNull());
  emit({type:'purchase-receipts',purchaseId:'purchase'});
  await vi.waitFor(() => expect(app.inventory?.purchaseReceipts?.cursor).toBe('older-receipts'));
  emit({type:'more-purchase-receipts'});
  await vi.waitFor(() => expect(app.inventory?.purchaseReceipts?.cursor).toBeNull());
  emit({type:'shopping-list'});
  await vi.waitFor(() => expect(app.inventory?.shoppingList?.cursor).toBe('more-list'));
  emit({type:'more-shopping-list'});
  await vi.waitFor(() => expect(app.inventory?.shoppingList?.cursor).toBeNull());
  emit({type:'shopping-sources',productId:'product'});
  await vi.waitFor(() => expect(app.inventory?.shoppingSources?.cursor).toBe('more-sources'));
  emit({type:'more-shopping-sources'});
  await vi.waitFor(() => expect(app.inventory?.shoppingSources?.cursor).toBeNull());
  expect(decodeInventoryIntent({type:'shopping-sources',productId:'../outside'})).toBeNull();
  emit({type:'purchase-sessions'});
  await vi.waitFor(() => expect(app.inventory?.purchaseSessions?.cursor).toBe('older-sessions'));
  emit({type:'more-purchase-sessions'});
  await vi.waitFor(() => expect(app.inventory?.purchaseSessions?.cursor).toBeNull());
  emit({type:'purchase-session',sessionId:'session'});
  await vi.waitFor(() => expect(app.inventory?.purchaseSession?.session.id).toBe('session'));
  expect(decodeInventoryIntent({type:'purchase-session',sessionId:'../outside'})).toBeNull();
  expect(decodeInventoryIntent({type:'purchase-receipts',purchaseId:'../outside'})).toBeNull();
  expect(decodeInventoryIntent({type:'submit',command:{action:'inventory.intake',product_id:'product',quantity:'1',location:'foreign'}})).toBeNull();
  navigate('#tasks');
  expect(app.inventory).toBeNull();
});
