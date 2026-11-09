import {expect,test,vi} from 'vitest';
import {CALENDAR_JOURNAL_KEY, CalendarSessionJournal} from '../src/adapters/calendar-journal';
import {HttpCalendarPreferences} from '../src/adapters/calendar-preference-http';
import {CalendarPreferenceController} from '../src/application/calendar-preferences';
import type {CalendarPreferenceServer, CalendarPreferenceView, PreferenceRequest, PreferenceScope} from '../src/application/calendar-preferences';
import {revisionValue} from '../src/domain/administration';
import {JOURNAL_LIFETIME} from '../src/domain/journal';
import '../src/presentation/domus-calendar';

const revision = revisionValue('9007199254740993');
const scope: PreferenceScope = {key:'calendar-member',memberId:'member',serverTime:100,expiresAt:100 + 2 * JOURNAL_LIFETIME,readOnly:false,
  context:{installationId:'01234567-89ab-cdef-0123-456789abcdef',channel:'edge',subject:'a'.repeat(32)}};
const request: PreferenceRequest = {scope:scope.key,createdAt:100,key:'request',weekStart:'sunday',revision};
const monday = {weekStart:'monday',revision} as const;
const sunday = {weekStart:'sunday',revision:revisionValue('9007199254740994')} as const;

function storage() {
  const items = new Map<string,string>();
  const provider = {getItem:vi.fn((key:string) => items.get(key) ?? null),
    setItem:vi.fn((key:string,value:string) => {items.set(key,value);}),
    removeItem:vi.fn((key:string) => {items.delete(key);})};
  return {items,provider,journal:new CalendarSessionJournal(provider)};
}

test('the separate journal validates scope, expiry, canonical revisions and storage acknowledgement', () => {
  const {items,journal,provider} = storage();
  expect(journal.open(scope.key,100)).toBeNull();
  journal.save(request);
  const raw = items.get(CALENDAR_JOURNAL_KEY)!;
  expect(raw).toContain(revision);
  expect(journal.open(scope.key,100)).toEqual(request);
  expect(() => journal.open(scope.key,99)).toThrow();
  expect(() => journal.save(request)).toThrow();
  expect(() => journal.clear({...request,key:'other'})).toThrow();
  expect(journal.open('other',100)).toBeNull();
  items.set(CALENDAR_JOURNAL_KEY,raw);
  expect(journal.open(scope.key,100+JOURNAL_LIFETIME)).toBeNull();
  for (const corrupted of [raw+' ',raw.replace(CALENDAR_JOURNAL_KEY,'domus.recurrence.journal.v1'),
    'x'.repeat(2049),'é'.repeat(1025),raw.replace(revision,'1e7')]) {
    items.set(CALENDAR_JOURNAL_KEY,corrupted);
    expect(() => journal.open(scope.key,100)).toThrow();
  }
  items.delete(CALENDAR_JOURNAL_KEY);
  provider.setItem.mockImplementationOnce(() => {});
  expect(() => journal.save(request)).toThrow();
  journal.save(request);
  provider.removeItem.mockImplementationOnce(() => {});
  expect(() => journal.clear(request)).toThrow();
});

test.each(['native','standalone'] as const)('%s wire recovers the exact owner and int64 revision', async deployment => {
  const target = {deployment,origin:'https://domus.example',
    applicationBase:deployment==='native' ? '/api/hassio_ingress/'+'b'.repeat(43)+'/' : '/'};
  const queue: [string,number][] = [];
  const fetch = vi.fn(async (path:string,_options:RequestInit) => {
    const [body,status] = queue.shift()!;
    const response = new Response(body,{status,headers:{'Content-Type':'application/json','Cache-Control':'no-store'}});
    Object.defineProperty(response,'url',{value:target.origin+path}); return response;
  });
  const server = new HttpCalendarPreferences(target,fetch);
  const reply = (state:string,member='member',day='sunday',rev='9007199254740994') =>
    '{"state":"'+state+'","archived_by":'+(state==='historical'?'"restore"':'null')+',"operation_id":"op","created_at":100,"result":{"member_id":"'+member+
    '","week_start":"'+day+'","revision":'+rev+'},"message":"Saved.","action_required":"Review."}';
  const csrf = JSON.stringify({csrf_token:'c'.repeat(64)});
  const failure = (code:string) => JSON.stringify({state:'blocked',code,message:'Blocked',action_required:'Review.',correlation_id:'cor_safe'});
  queue.push(['{"week_start":"monday","revision":9007199254740993}',200]);
  expect(await server.read(scope).result).toEqual(monday);
  queue.push([csrf,200],[reply('committed'),200],[reply('historical'),200]);
  expect(await server.send(scope,request).result).toBe(true);
  expect(await server.original(scope,request).result).toBe(true);
  const [url,options] = fetch.mock.calls[2];
  expect(url).toBe(target.applicationBase+'api/v1/tasks/calendar/preferences');
  expect(options.body).toBe('{"expected_revision":9007199254740993,"week_start":"sunday"}');
  expect(options.method).toBe('PUT');
  expect(new Headers(options.headers).get('Idempotency-Key')).toBe(request.key);
  expect(fetch.mock.calls[3][0]).toContain('/requests/request');
  queue.push([csrf,200],[failure('revision_conflict'),409],[failure('operation_missing'),404]);
  expect(await server.send(scope,request).result).toBe(false);
  expect(await server.original(scope,request).result).toBe(false);
  queue.push([csrf,200],[failure('storage_busy'),503]);
  await expect(server.send(scope,request).result).rejects.toThrow();
  for (const response of [[reply('historical','other'),200],[reply('committed','member','monday'),200],
    [reply('committed','member','sunday','9007199254740995'),200],[failure('member_missing'),404],[failure('storage_busy'),503]] as [string,number][]) {
    queue.push(response); await expect(server.original(scope,request).result).rejects.toThrow();
  }
});

function owned<T>(result:T) {return {cancel:vi.fn(),result:Promise.resolve(result)};}
function failure() {return {cancel:vi.fn(),result:Promise.reject(new Error('unavailable'))};}

test('an uncertain preference write remains scoped and recoverable without another write', async () => {
  const {journal,items,provider} = storage();
  let time=100;
  const server = {read:vi.fn<CalendarPreferenceServer['read']>(()=>owned(monday)),
    send:vi.fn<CalendarPreferenceServer['send']>(failure),original:vi.fn<CalendarPreferenceServer['original']>(()=>owned(true))};
  const views = vi.fn<(view:CalendarPreferenceView|null)=>void>();
  const clock = {anchor:vi.fn(),now:()=>time}, entropy={requestKey:()=>request.key};
  const controller = new CalendarPreferenceController(server,journal,clock,entropy,views);
  const view = () => views.mock.calls.at(-1)?.[0];
  await controller.refresh(); await controller.recover(); controller.bind(null);
  controller.bind(scope); await vi.waitFor(()=>expect(view()?.value).toEqual(monday));
  controller.bind({...scope});
  await controller.save('monday');
  controller.bind({...scope,readOnly:true}); await controller.save('sunday');
  expect(server.send).not.toHaveBeenCalled();
  controller.bind(scope);
  provider.setItem.mockImplementationOnce(()=>{throw new Error();});
  await controller.save('sunday'); expect(view()?.notice).toBe('preferenceUnavailable');
  await controller.save('sunday'); expect(view()?.notice).toBe('preferenceUncertain');
  expect(items.get(CALENDAR_JOURNAL_KEY)).toContain(revision);
  await controller.save('sunday'); expect(server.send).toHaveBeenCalledOnce();
  controller.bind(null); expect(view()).toBeNull();
  const restored = new CalendarPreferenceController(server,journal,clock,entropy,views);
  restored.bind(scope); await vi.waitFor(()=>expect(view()?.busy).toBe(false));
  expect(view()?.pending).toBe(true);
  server.original.mockImplementationOnce(failure);
  await restored.recover(); expect(view()?.notice).toBe('preferenceUncertain');
  server.read.mockReturnValueOnce(owned(sunday));
  await restored.recover(); expect(view()?.value).toEqual(sunday);
  expect(server.original.mock.calls.at(-1)?.[1]).toEqual(request);
  expect(items.has(CALENDAR_JOURNAL_KEY)).toBe(false);
  server.send.mockReturnValueOnce(owned(false));
  await restored.save('monday'); expect(view()?.notice).toBe('preferenceRejected');
  await restored.save('sunday');
  time += JOURNAL_LIFETIME;
  provider.removeItem.mockImplementationOnce(()=>{throw new Error();});
  await restored.recover(); expect(view()?.notice).toBe('preferenceUnavailable');
  await restored.recover(); expect(view()?.notice).toBe('preferenceRejected');
  restored.bind(null);
  items.set(CALENDAR_JOURNAL_KEY,'corrupt');
  server.read.mockImplementationOnce(failure);
  restored.bind({...scope,key:'other',serverTime:time});
  await vi.waitFor(()=>expect(view()?.busy).toBe(false));
  expect(view()).toMatchObject({value:null,readOnly:true,notice:'preferenceUnavailable'});
  const other={...scope,key:'other',serverTime:time};
  restored.bind({...other,readOnly:true}); restored.bind(other);
  expect(view()?.readOnly).toBe(true);
});

test('retiring a scope cancels outstanding reads and their late failures', async () => {
  const {journal}=storage(), publish=vi.fn();
  const stop=vi.fn(); let reject!: (error:Error)=>void, resolve!: (value:typeof monday)=>void;
  const server = {read:()=>({cancel:stop,result:new Promise<typeof monday>((succeed,fail)=>{resolve=succeed;reject=fail;})}),
    send:()=>owned(true),original:()=>owned(true)};
  const controller = new CalendarPreferenceController(server,journal,{anchor:vi.fn(),now:()=>100},{requestKey:()=>request.key},publish);
  controller.bind(scope);
  const late = resolve;
  controller.bind({...scope,key:'other'}); late(monday);
  expect(stop).toHaveBeenCalledOnce();
  controller.bind(null); reject(new Error()); await Promise.resolve();
  expect(publish.mock.calls.at(-1)?.[0]).toBeNull();
});

test('Sunday updates the calendar grid and controls stay private to the bound scope', async () => {
  const widget = document.createElement('domus-calendar');
  const sent = vi.fn();
  widget.addEventListener('domus-calendar-intent',sent);
  document.body.append(widget);
  try {
    widget.today='2026-11-01'; widget.scopeKey=scope.key;
    widget.view={status:'ready',page:{entries:[],count:0, occurrenceCount:0,cursor:null,pending:false}};
    widget.preference={value:monday,pending:false,busy:false,notice:null,readOnly:false};
    await widget.updateComplete;
    const root=widget.shadowRoot!;
    const choice=root.querySelector<HTMLSelectElement>('label select')!;
    expect(choice.value).toBe('monday');
    await vi.waitFor(()=>expect(root.querySelectorAll('.calendar-grid > li')).toHaveLength(36));
    choice.value='sunday'; choice.dispatchEvent(new Event('change'));
    expect(sent.mock.calls.at(-1)?.[0].detail).toEqual({type:'setWeekStart',weekStart:'sunday'});
    expect(choice.value).toBe('monday');
    const mode=root.querySelector('form select') as HTMLSelectElement;
    mode.value='week'; mode.dispatchEvent(new Event('change'));
    root.querySelector('form')!.dispatchEvent(new Event('submit',{cancelable:true}));
    expect(sent.mock.calls.at(-1)?.[0].detail.query.start).toBe('2026-10-26');
    widget.preference={...widget.preference,value:sunday}; await widget.updateComplete;
    expect(sent.mock.calls.at(-1)?.[0].detail.query.start).toBe('2026-11-01');
    expect(choice.value).toBe('sunday');
    widget.language='es';
    widget.preference={...widget.preference,pending:true,notice:'preferenceUncertain'}; await widget.updateComplete;
    expect(choice.disabled).toBe(true);
    expect(root.querySelector('[role=alert]')?.textContent).toContain('sin confirmar');
    root.querySelector<HTMLButtonElement>('button[type=button]')!.click();
    expect(sent.mock.calls.at(-1)?.[0].detail).toEqual({type:'recoverPreference'});
    widget.preference={...widget.preference,busy:true,pending:false}; await widget.updateComplete;
    expect(choice.disabled).toBe(true);
    widget.preference={value:null,readOnly:true,busy:false,pending:false,notice:'preferenceUnavailable'};
    await widget.updateComplete;
    root.querySelector<HTMLButtonElement>('button[type=button]')!.click();
    expect(sent.mock.calls.at(-1)?.[0].detail).toEqual({type:'refreshPreference'});
    widget.preference=null; widget.scopeKey=null; await widget.updateComplete;
    expect(root.textContent).not.toContain('Mi semana empieza el');
  } finally {widget.remove();}
});
