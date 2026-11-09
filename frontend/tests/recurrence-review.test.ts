import {afterEach, expect, test, vi} from 'vitest';
import {HttpRecurrenceServer} from '../src/adapters/recurrence-http';
import {RECURRENCE_JOURNAL_KEY, RecurrenceSessionJournal} from '../src/adapters/recurrence-journal';
import {RecurrenceReviewController, ReviewRejected} from '../src/application/recurrence-review-controller';
import type {ReviewRecord, ReviewReceipt, ReviewServer, ReviewView} from '../src/application/recurrence-review-controller';
import {revisionValue} from '../src/domain/administration';
import {JOURNAL_LIFETIME} from '../src/domain/journal';
import type {JournalContext} from '../src/domain/journal';
import {REVIEW_KINDS, reviewCommand, reviewDraft, reviewSelection} from '../src/domain/recurrence-review';
import type {ReviewDraft, ReviewTarget} from '../src/domain/recurrence-review';
import '../src/presentation/domus-recurrence-review';

const context: JournalContext = {installationId: '01234567-89ab-cdef-0123-456789abcdef', channel: 'edge', subject: 'a'.repeat(32)};
const revision = revisionValue('9007199254740993');
const fingerprint = 'a'.repeat(64);
const work: ReviewTarget = {occurrenceId: 'occurrence', definitionId: 'definition', occurrenceRevision: revision,
  definitionRevision: revision, zone: 'Europe/Madrid', schedule: {id: 'schedule', revision, state: 'active',
    nominal: {kind: 'time', local: '2026-12-01T09:15:00'}, zone: 'Europe/Madrid', interval: 30, visibility: 'at_completion', missedPolicy:{policy:'keep_visible',revision:'0'}},
  slotKey: 'slot', actions: REVIEW_KINDS};
const input: ReviewDraft = {kind: 'attachment', date: '2026-12-01', time: '', zone: 'Europe/Madrid', interval: '3',
  visibility: 'at_completion', choice: 'adopt', fold: 'first_instant', reason: '<img src=x>', rrule: 'FREQ=MONTHLY'};
const attachment = reviewSelection(work, input);
const intent: ReviewRecord = {key: 'original-key', command: {step: 'preview', selection: attachment},
  createdAt: 100, status: 'pending', operationId: null};
const scope = {key: 'member-1', context, occurrenceId: work.occurrenceId, readOnly: false, serverTime: 100, expiresAt: 500_000};
const plan: ReviewReceipt = {operationId: 'preview-op', historical: false,
  preview: {fingerprint, expiresAt: 200, retained: 0, planned: 1, cancelled:null, previous: null, destination: '2026-12-01', createsFirst: false,replacementSlots:[],retainedDates:[],cancelledDates:[]}};
const storedEffect: ReviewReceipt = {operationId: 'apply-op', historical: false, preview: null};

function storage() {
  const values = new Map<string,string>();
  const provider = {getItem: vi.fn((key: string) => values.get(key) ?? null),
    setItem: vi.fn((key: string, value: string) => {values.set(key,value);}),
    removeItem: vi.fn((key: string) => {values.delete(key);})};
  return {provider, values, journal: new RecurrenceSessionJournal(provider)};
}

test('closed inputs support each review and preserve exact snapshot identifiers, revisions and literal reasons', () => {
  for (const kind of REVIEW_KINDS) {
    const selected = reviewSelection(work, reviewDraft({...input, kind, time: '09:15', missedPolicy:'skip_after_review'}));
    expect(selected.kind).toBe(kind);
    expect(reviewCommand({step:'preview', selection:selected}).selection).toEqual(selected);
    expect(reviewCommand({step:'apply', selection:selected, previewKey:'preview-key', fingerprint}).selection).toEqual(selected);
    if (kind === 'reschedule') expect(selected.body).toMatchObject({reason:'<img src=x>', occurrence_revision:revision});
  }
  expect(reviewSelection({...work, schedule: {...work.schedule!, state:'paused'}}, {...input, kind:'state'}).body)
    .toMatchObject({target:'active', schedule_revision:revision});
  expect(reviewSelection(work, {...input, time:'04:09:10.001'}).body).toMatchObject({initial:{kind:'time',local:'2026-12-01T04:09:10.001'}});
  for (const change of [{date:'2026-02-29'}, {time:'24:00'}, {time:'no'}, {date:'oops',time:'12:00'}, {interval:'0'},
    {interval:'3.5'}, {interval:'36601'}, {interval:'NaN'}, {zone:''}]) {
    expect(() => reviewSelection(work, {...input,...change})).toThrow();
  }
  expect(() => reviewSelection(work, {...input, kind:'fixed-exclude'})).toThrow();
  expect(() => reviewSelection({...work, actions:[]}, input)).toThrow();
  expect(() => reviewSelection({...work, schedule:null}, {...input,kind:'adoption'})).toThrow();
  for (const malformed of [null, [], 'draft', {...input, ignored:0}, {...input,date:null}, {...input, kind:'unknown'}])
    expect(() => reviewDraft(malformed)).toThrow();
  for (const malformed of [null, [], 42, {step:'retry'}, {step:'apply',selection:attachment,previewKey:'original',fingerprint:'wrong'},
    {step:'preview',selection:{...attachment, actor:'other'}}, {step:'preview',selection:{kind:'attachment',body:{}}}])
    expect(() => reviewCommand(malformed)).toThrow();
});

test('independent storage fences writes, checks bounds and expires original records without renewal', () => {
  const {journal,provider,values} = storage();
  expect(journal.open(scope.key, 100)).toEqual([]);
  expect(journal.save(scope.key, 100, [intent])).toEqual([intent]);
  const exact = values.get(RECURRENCE_JOURNAL_KEY)!;
  expect(exact).toContain(revision);
  expect([...values.keys()]).toEqual([RECURRENCE_JOURNAL_KEY]);
  expect(journal.open(scope.key, 100 + JOURNAL_LIFETIME - 1)).toEqual([intent]);
  expect(journal.open(scope.key, 100 + JOURNAL_LIFETIME)).toEqual([]);
  values.set(RECURRENCE_JOURNAL_KEY, exact);
  expect(journal.open('different-member', 100)).toEqual([]);
  expect(values.get(RECURRENCE_JOURNAL_KEY)).not.toContain('original-key');
  expect(() => journal.save(scope.key, 100, [])).toThrow();
  journal.open(scope.key, 100);
  expect(() => journal.save(scope.key, 100, [intent,intent])).toThrow();
  journal.open(scope.key, 100);
  expect(() => journal.save(scope.key, 100, Array(9).fill(intent))).toThrow();
  for (const malformed of ['x'.repeat(65_537), exact + ' ', exact.replace('"recurrence"','"administration"'),
    exact.replace('"version":1','"version":2'), exact.replace('"scope":"member-1"','"scope":null'),
    exact.replace('"observedAt":100','"observedAt":101'), exact.replace('"createdAt":100','"createdAt":101'),
    exact.replace('"createdAt":100','"createdAt":null'), exact.replace('"createdAt":100','"createdAt":-1'),
    exact.replace('"operationId":null','"operationId":"injected"'), exact.replace('"status":"pending"','"status":"unknown"'),
    exact.replace('"command":{','"command":{"actor":"x",')]) {
    values.set(RECURRENCE_JOURNAL_KEY, malformed);
    expect(() => journal.open(scope.key, 100)).toThrow();
  }
  values.set(RECURRENCE_JOURNAL_KEY, exact.replace('"scope":"member-1"','"scope":"' + '世'.repeat(22_000) + '"'));
  expect(() => journal.open(scope.key, 100)).toThrow();
  values.delete(RECURRENCE_JOURNAL_KEY); journal.open(scope.key, 100);
  values.set(RECURRENCE_JOURNAL_KEY, exact);
  expect(() => journal.save(scope.key, 100, [])).toThrow();
  provider.setItem.mockImplementationOnce(() => {});
  expect(() => journal.open('new', 100)).toThrow();
});

function http(deployment: 'native' | 'standalone' = 'standalone') {
  const applicationBase = deployment === 'native' ? '/api/hassio_ingress/' + 'b'.repeat(43) + '/' : '/';
  const origin = 'https://domus.example';
  const replies: Array<Readonly<{body: unknown; status?: number}>> = [];
  const fetch = vi.fn(async (path: string, _init: RequestInit) => {
    const reply = replies.shift()!;
    const raw = JSON.stringify(reply.body).replaceAll('"\$revision"', revision);
    const response = new Response(raw, {status: reply.status ?? 200,
      headers: {'Content-Type':'application/json','Cache-Control':'no-store'}});
    Object.defineProperty(response, 'url', {value: origin + path}); return response;
  });
  const enqueue = (body: unknown, status = 200) => {replies.push({body,status});};
  return {fetch, applicationBase, enqueue, server: new HttpRecurrenceServer({deployment, applicationBase, origin}, fetch)};
}
const targetWire = {occurrence_id:'occurrence', occurrence_revision:'$revision', definition_id:'definition',definition_revision:'$revision',
  zone:'Europe/Madrid', schedule:{schedule_id:'schedule',revision:'$revision',state:'active',nominal_kind:'time',
    local:'2026-12-01T09:15:00',zone:'Europe/Madrid',interval_days:30,visibility:'at_completion',missed_policy:{policy:'keep_visible',revision:0}},slot_key:'slot',actions:REVIEW_KINDS};
function receipt(result: unknown, historical = false) {
  return {state: historical ? 'historical' : 'committed', archived_by: historical ? 'restored' : null,
    operation_id:'original-op', created_at:100, result, message:'Saved.', action_required:'Review.'};
}
const preview = {plan_fingerprint:fingerprint, expires_at:200, plan:{snapshot:{request:{kind:'attach_relative'},
  source:{initial:{nominal:{local:'2026-12-01'}},previous:{nominal:{local:'2026-11-30'}},creates_first_occurrence:true,open_work_retained:[]}},
  backlog:{prospective_slots:[{}]}}};
const token = {csrf_token:'c'.repeat(64)};
const rejected = {state:'blocked',code:'request_forbidden',message:'Private',action_required:'Review.',correlation_id:'cor_safe'};

test.each(['native','standalone'] as const)('%s recurrence wire binds context and preserves original exact requests', async mode => {
  const f = http(mode);
  f.enqueue(targetWire); f.enqueue(token); f.enqueue(receipt(preview)); f.enqueue(receipt(preview, true));
  expect(await f.server.target(context, work.occurrenceId).result).toEqual(work);
  expect(await f.server.send(context, intent).result).toEqual({operationId:'original-op',historical:false,preview:{
    fingerprint,expiresAt:200,retained:0,planned:1,cancelled:null,previous:'2026-11-30',destination:'2026-12-01',createsFirst:true,replacementSlots:[],retainedDates:[],cancelledDates:[]}});
  expect(await f.server.original(context,intent).result).toMatchObject({historical:true});
  const [path, request] = f.fetch.mock.calls[2];
  expect(path).toBe(f.applicationBase + 'api/v1/tasks/recurrence/reviews/attachment/preview');
  expect(request.body).toContain('"definition_revision":' + revision);
  expect(request.body).toContain('"occurrence_revision":' + revision);
  expect(new Headers(request.headers).get('Idempotency-Key')).toBe(intent.key);
  expect(new Headers(request.headers).get('X-Domus-Context')).toContain(context.subject);
  expect(f.fetch.mock.calls[3][0]).toBe(f.applicationBase + 'api/v1/tasks/recurrence/reviews/requests/recurrence.review.preview/original-key');
  const apply: ReviewRecord = {...intent, command:{step:'apply',selection:attachment,previewKey:intent.key,fingerprint}};
  f.enqueue(token); f.enqueue(receipt({kind:'attach_relative',plan_fingerprint:fingerprint}));
  expect(await f.server.send(context, apply).result).toMatchObject({preview:null});
  expect(f.fetch.mock.calls[5][1].body).toContain('"preview_key":"original-key"');
});

test('receipt projection handles optional plans and distinguishes definite rejection from uncertain writes', async () => {
  const f = http();
  f.enqueue({...targetWire, schedule:null, slot_key:null, actions:['attachment']});
  expect(await f.server.target(context, work.occurrenceId).result).toMatchObject({schedule:null,slotKey:null});
  f.enqueue({...targetWire, schedule:{...targetWire.schedule,interval_days:null,visibility:null}});
  expect(await f.server.target(context, work.occurrenceId).result).toMatchObject({schedule:{interval:null,visibility:null}});
  for (const value of [{...targetWire, occurrence_id:'foreign'}, {...targetWire,actions:null},
    {...targetWire,actions:Array(REVIEW_KINDS.length + 1).fill('attachment')}, {...targetWire,actions:['attachment','attachment']}]) {
    f.enqueue(value); await expect(f.server.target(context, work.occurrenceId).result).rejects.toThrow();
  }
  f.enqueue(receipt({...preview,plan:{request:{kind:'attach_relative'}}}));
  expect((await f.server.original(context,intent).result).preview).toMatchObject({planned:null,destination:null,retained:null,createsFirst:null});
  f.enqueue(receipt({...preview,plan:{request:{kind:'attach_relative'},source:{retained_work:[{}]},
    backlog:{pending_slots:[],next_slot:{nominal:{local:'2026-12-02'}}}}}));
  expect((await f.server.original(context,intent).result).preview).toMatchObject({planned:0,destination:'2026-12-02',retained:1});
  f.enqueue(token); f.enqueue(rejected,409);
  await expect(f.server.send(context,intent).result).rejects.toBeInstanceOf(ReviewRejected);
  f.enqueue(rejected,403);
  await expect(f.server.send(context,intent).result).rejects.toBeInstanceOf(ReviewRejected);
  f.enqueue(token); f.enqueue(rejected,503);
  await expect(f.server.send(context,intent).result).rejects.not.toBeInstanceOf(ReviewRejected);
  f.enqueue(token); f.enqueue(receipt({...preview,plan:{request:{kind:'unrelated'}}}));
  await expect(f.server.send(context,intent).result).rejects.not.toBeInstanceOf(ReviewRejected);
});

function owned<T>(value: T) {return {result:Promise.resolve(value),cancel:vi.fn()};}
function application() {
  const store = storage(), views = vi.fn<(value: ReviewView | null) => void>();
  const server = {target:vi.fn<ReviewServer['target']>(() => owned(work)),
    send:vi.fn<ReviewServer['send']>(() => owned(plan)), original:vi.fn<ReviewServer['original']>(() => owned(storedEffect))};
  let at = 100, serial = 0;
  const clock = {anchor:vi.fn(),now:()=>at};
  const controller = new RecurrenceReviewController(server,store.journal,clock,{requestKey:()=> 'key-' + ++serial},views);
  return {controller,server,clock,views,store, at:(value:number)=>{at=value;},
    view:()=>views.mock.calls.at(-1)?.[0]};
}
test('controller fences scope and explicitly recovers the original apply after response loss', async () => {
  const f = application(), c = f.controller;
  c.bind(null); c.close(); await c.open(); await c.preview(input); await c.apply(); await c.recover('missing'); c.forget('missing');
  expect(f.views).not.toHaveBeenCalled();
  c.bind(scope);
  await c.preview(input); await c.apply(); await c.recover('missing'); c.forget('missing');
  expect(f.server.send).not.toHaveBeenCalled();
  await c.open(); expect(f.view()?.target).toEqual(work);
  await c.preview({...input,date:'invalid'}); expect(f.view()?.notice).toBe('invalid');
  await c.preview(input); expect(f.view()?.result?.receipt).toEqual(plan);
  f.server.send.mockReturnValueOnce({result:Promise.reject(new Error('lost response')),cancel:vi.fn()});
  await c.apply();
  const pending = f.view()!.records.find(item=>item.status==='pending')!;
  expect(pending.command).toEqual({step:'apply',selection:attachment,previewKey:'key-1',fingerprint});
  expect(f.view()?.notice).toBe('uncertain');
  c.forget(pending.key);
  await c.preview(input);
  expect(f.server.send).toHaveBeenCalledTimes(2);
  c.bind(null); expect(f.view()).toBeNull();
  c.bind({...scope,occurrenceId:null}); await c.open();
  expect(f.server.target).toHaveBeenCalledTimes(1);
  await c.recover(pending.key);
  expect(f.server.original).toHaveBeenLastCalledWith(context,pending);
  expect(f.view()?.result?.receipt).toEqual(storedEffect);
  c.forget(pending.key);
  expect(f.view()?.records).toHaveLength(1);
  await c.recover('key-1');
  expect(f.view()?.notice).toBe('uncertain');
  c.close(); expect(f.view()?.open).toBe(false);
  c.bind({...scope,key:'other'}); expect(f.view()?.records).toEqual([]);
});

test('controller handles expiry, blocked authority, unavailable storage and callbacks retired in flight', async () => {
  const f = application(), c = f.controller;
  c.bind(scope);
  const waiting = Promise.withResolvers<ReviewTarget>(), cancel = vi.fn();
  f.server.target.mockReturnValueOnce({result:waiting.promise,cancel});
  const active = c.open();
  c.close(); await c.open();
  c.bind({...scope,readOnly:true});
  expect(cancel).toHaveBeenCalledOnce();
  waiting.resolve(work); await active;
  expect(f.view()?.target).toBeNull();
  await c.open(); await c.preview(input); await c.apply();
  expect(f.server.send).not.toHaveBeenCalled();
  c.bind({...scope,serverTime:110}); expect(f.clock.anchor).toHaveBeenLastCalledWith(110);
  await c.open();
  f.server.send.mockReturnValueOnce({result:Promise.reject(new ReviewRejected()),cancel:vi.fn()});
  await c.preview(input);
  expect(f.view()?.notice).toBe('rejected'); expect(f.view()?.records).toEqual([]);
  await c.preview(input); f.at(200); await c.apply(); expect(f.view()?.notice).toBe('expired');
  f.server.send.mockReturnValueOnce(owned({...plan, preview:{...plan.preview!, expiresAt:300}}));
  await c.preview(input); f.at(300); c.bind(scope);
  expect(f.view()?.notice).toBe('expired');
  f.at(scope.expiresAt); await c.open();
  f.at(300);
  f.server.target.mockReturnValueOnce({result:Promise.reject(new Error()),cancel:vi.fn()});
  await c.open(); expect(f.view()?.notice).toBe('unavailable');
  c.bind(null); f.store.provider.getItem.mockImplementationOnce(()=>{throw new Error();});
  c.bind(scope); expect(f.view()?.notice).toBe('journal');
  await c.open(); await c.preview(input); expect(f.view()?.records).toEqual([]);
});

const mounted: HTMLElement[] = [];
afterEach(() => {for (const node of mounted.splice(0)) node.remove();});

test('review component shows bounded impacts, closed actions, literal content and original recovery in both languages', async () => {
  const widget = document.createElement('domus-recurrence-review'), dispatch = vi.fn();
  widget.addEventListener('domus-review-intent', dispatch); document.body.append(widget); mounted.push(widget);
  const root = widget.shadowRoot ?? (await widget.updateComplete, widget.shadowRoot!);
  const buttons = (text: string) => [...root.querySelectorAll('button')].find(item => item.textContent === text)!;
  const update = async (view: Partial<ReviewView>) => {widget.view = {...widget.view!,...view}; await widget.updateComplete;};
  const select = async (kind: string) => {
    const control = root.querySelector<HTMLSelectElement>('form select')!;
    control.value = kind; control.dispatchEvent(new Event('change')); await widget.updateComplete;
  };
  expect(root.querySelector('section')).toBeNull();
  const empty: ReviewView = {open:false,busy:false,readOnly:false,selected:false,target:null,records:[],result:null,notice:null};
  await update(empty); expect(root.querySelector('section')).toBeNull();
  await update({selected:true});
  buttons('Review scheduling').click(); expect(dispatch).toHaveBeenLastCalledWith(expect.objectContaining({detail:{type:'open'}}));
  await update({open:true,busy:true,readOnly:true});
  expect(buttons('Close schedule review').disabled).toBe(true); expect(root.textContent).toContain('Checking the schedule.');
  await update({busy:false,selected:false});
  expect(root.textContent).toContain('Select a task');
  await update({selected:true});
  expect(root.textContent).toContain('No scheduling action');
  await update({target:{...work,schedule:null},readOnly:false});
  const get = (name:string) => root.querySelector<HTMLInputElement>('[name=' + name + ']')!;
  get('date').value = input.date; get('interval').value = '7';
  root.querySelector('form')!.dispatchEvent(new Event('submit',{cancelable:true}));
  expect(dispatch).toHaveBeenLastCalledWith(expect.objectContaining({detail:{type:'preview',draft:{...input,
    interval:'7',fold:'household',reason:'',rrule:''}}}));
  await update({target:work});
  await select('relative-settings'); expect(get('interval').value).toBe('30');
  await select('fixed-state'); expect(root.textContent).toContain('Pause new generation');
  await select('fixed-pattern'); expect(get('pattern')).not.toBeNull(); expect(get('time').required).toBe(true);
  await select('fixed-replacement'); expect(get('pattern')).not.toBeNull(); expect(get('reason')).not.toBeNull();
  await select('fixed-exclude'); expect(get('reason')).not.toBeNull(); expect(get('date')).not.toBeNull();
  await select('fixed-add'); expect(get('pattern')).toBeNull(); expect(get('time').required).toBe(true);
  await select('fixed-skip'); expect(get('reason')).not.toBeNull();
  await select('reschedule'); expect(get('reason')).not.toBeNull(); expect(get('date')).not.toBeNull();
  await update({target:{...work,schedule:{...work.schedule!,state:'paused',nominal:{kind:'date',local:'2026-12-01'}}}});
  await select('state'); expect(root.textContent).toContain('Resume generation');
  await select('fixed-pattern'); expect(get('time')).toBeNull();
  await select('adoption'); expect(get('reason')).toBeNull();
  root.querySelector('form')!.dispatchEvent(new Event('submit',{cancelable:true}));
  expect(dispatch).toHaveBeenLastCalledWith(expect.objectContaining({detail:{type:'preview',
    draft:expect.objectContaining({kind:'adoption',visibility:'at_completion',choice:'adopt',fold:'keep_fold'})}}));
  await update({records:[intent],notice:'uncertain'});
  expect(root.querySelector('details')!.open).toBe(true);
  buttons('Check original schedule request').click();
  expect(dispatch).toHaveBeenLastCalledWith(expect.objectContaining({detail:{type:'recover',key:intent.key}}));
  const received:ReviewRecord = {...intent,status:'received',operationId:'preview-op'};
  await update({records:[received],result:{record:{...received,command:{step:'preview',
    selection:reviewSelection({...work,schedule:{...work.schedule!,state:'paused'}},{...input,kind:'state'})}},receipt:plan}});
  expect(root.textContent).toContain('Resume generation');
  for (const kind of ['attachment','fixed-state','reschedule','fixed-pattern','fixed-replacement','fixed-exclude','fixed-add'] as const) {
    await update({records:[received],result:{record:{...received,command:{step:'preview',selection:reviewSelection(work,{...input,kind,time:'09:15'})}},
      receipt:kind === 'fixed-replacement' ? {...plan,preview:{...plan.preview!,cancelled:3,
        retainedDates:['2026-11-30'],cancelledDates:['2026-12-01'],
        replacementSlots:[{local:'2026-12-02',replaces:true},{local:'2026-12-03',replaces:false}]}} : plan},notice:null});
    expect(root.textContent).toContain('Existing work retained 0');
    expect(root.textContent).toContain('Upcoming slots in the review 1');
    expect(root.textContent).toContain('New local date or time 2026-12-01');
    if (kind === 'fixed-replacement') {
      expect(root.textContent).toContain('Original occurrences to cancel 3');
      expect(root.querySelector('[aria-label="Existing work retained"]')!.textContent).toBe('2026-11-30');
      expect(root.querySelector('[aria-label="Original occurrences to cancel"]')!.textContent).toBe('2026-12-01');
      expect(root.textContent).toContain('2026-12-02 · Replaces existing work');
      expect(root.textContent).toContain('2026-12-03 · Adds an occurrence');
    }
    if (kind === 'reschedule') {
      expect(root.textContent).toContain(input.reason); expect(root.querySelector('img')).toBeNull();
    }
  }
  buttons('Apply reviewed change').click();
  expect(dispatch).toHaveBeenLastCalledWith(expect.objectContaining({detail:{type:'apply'}}));
  buttons('Dismiss schedule request').click();
  expect(dispatch).toHaveBeenLastCalledWith(expect.objectContaining({detail:{type:'forget',key:intent.key}}));
  buttons('Review another change').click();
  buttons('Close schedule review').click();
  expect(dispatch).toHaveBeenLastCalledWith(expect.objectContaining({detail:{type:'close'}}));
  widget.language='es';
  await update({target:null,selected:false,result:{record:received,receipt:{...plan,preview:{...plan.preview!,
    previous:'2026-11-30',destination:null,retained:null,planned:null,createsFirst:true}}}});
  expect(root.textContent).toContain('Este cambio crea'); expect(root.textContent).toContain('Fecha u hora local anterior');
  await update({result:{record:received,receipt:{...plan,preview:{...plan.preview!,createsFirst:null}}}});
  expect(root.textContent).not.toContain('Este cambio crea');
  await update({result:{record:received,receipt:{...plan,historical:true}}});
  expect(root.textContent).toContain('se procesó antes de la restauración');
  expect(buttons('Aplicar cambio revisado')).toBeUndefined();
  await update({result:{record:received,receipt:storedEffect}});
  expect(root.textContent).toContain('Cambio de programación guardado');
});

test('a preview and an applied effect retain their original identities across recovery, expiry and storage faults', async () => {
  const f = application(), c = f.controller;
  c.bind(scope); c.bind({...scope,occurrenceId:null}); c.bind(scope);
  await c.open(); await c.preview(input);
  f.server.send.mockReturnValueOnce(owned(storedEffect)); await c.apply();
  await c.apply(); expect(f.view()?.notice).toBe('expired');
  f.server.original.mockReturnValueOnce(owned(plan)); await c.recover('key-1');
  await c.apply(); expect(f.server.send).toHaveBeenCalledTimes(2);
  expect(f.view()?.notice).toBe('uncertain');
  f.server.original.mockReturnValueOnce(owned({...plan,historical:true})); await c.recover('key-1');
  await c.apply(); expect(f.view()?.notice).toBe('expired');
  f.server.original.mockReturnValueOnce(owned(storedEffect));
  f.store.provider.setItem.mockImplementationOnce(()=>{throw new Error('write failed');});
  await c.recover('key-2'); expect(f.view()?.notice).toBe('journal');
  c.forget('key-2'); expect(f.view()?.notice).toBe('journal');
  await c.preview(input); expect(f.view()?.notice).toBe('journal');
  c.bind(null); c.bind(scope); await c.open();
  f.server.send.mockImplementationOnce(() => {
    f.store.provider.setItem.mockImplementationOnce(()=>{throw new Error('write failed');});
    return {result:Promise.reject(new ReviewRejected()),cancel:vi.fn()};
  });
  await c.preview(input); expect(f.view()?.notice).toBe('journal');
  c.bind(null); c.bind(scope);
  f.at(JOURNAL_LIFETIME + 100);
  const extended = {...scope, expiresAt:JOURNAL_LIFETIME + 1000};
  c.bind(extended); expect(f.view()?.records).toHaveLength(0);
  await c.open(); await c.preview(input);
  f.at(2*JOURNAL_LIFETIME + 100);
  f.store.provider.setItem.mockImplementationOnce(()=>{throw new Error('write failed');});
  c.bind({...extended,expiresAt:3*JOURNAL_LIFETIME}); expect(f.view()?.notice).toBe('journal');
  c.bind(extended);
});

test('an original result arriving beyond its verified lease never becomes visible', async () => {
  const f = application(), c = f.controller;
  c.bind(scope);
  const read = Promise.withResolvers<ReviewTarget>();
  f.server.target.mockReturnValueOnce({result:read.promise,cancel:vi.fn()});
  const waiting = c.open();
  c.bind(scope);
  f.at(scope.expiresAt); read.resolve(work); await waiting;
  expect(f.view()?.target).toBeNull();
  const failure = Promise.withResolvers<ReviewTarget>();
  f.at(100); f.server.target.mockReturnValueOnce({result:failure.promise,cancel:vi.fn()});
  const retired = c.open(); c.bind(null); failure.reject(new Error('late rejection')); await retired;
  expect(f.view()).toBeNull();
});

test('batch plan labels replacements and added dates from the actual reviewed projection', async () => {
  const f = http();
  const command: ReviewRecord = {...intent,command:{step:'preview',selection:reviewSelection(work,{...input,kind:'fixed-replacement'})}};
  const result = {...preview,plan:{request:{kind:'fixed_replacement'},source:{cancelled_work:[{deadline:{nominal:{local:'2026-11-30'}}}],retained_work:[],
    prospective_slots:[{planned:{nominal:{local:'2026-12-01'}},replaces:'work-a'},
      {planned:{nominal:{local:'2026-12-02'}},replaces:null}]}}};
  f.enqueue(receipt(result));
  expect((await f.server.original(context,command).result).preview).toMatchObject({cancelled:1,planned:2,cancelledDates:['2026-11-30'],retainedDates:[],
    replacementSlots:[{local:'2026-12-01',replaces:true},{local:'2026-12-02',replaces:false}]});
  for (const prospective_slots of [null,Array(101).fill({}),[{planned:null,replaces:null}]]) {
    f.enqueue(receipt({...result,plan:{...result.plan,source:{prospective_slots}}}));
    await expect(f.server.original(context,command).result).rejects.toThrow();
  }
  for (const retained_work of [null,Array(201).fill({}),[{deadline:null}]]) {
    f.enqueue(receipt({...result,plan:{...result.plan,source:{...result.plan.source,retained_work}}}));
    await expect(f.server.original(context,command).result).rejects.toThrow();
  }
});


test.each(['fixed-exclude','fixed-add'] as const)('%s posts the typed exception and retains the exact original', async kind => {
  const f = http('native');
  const selection = reviewSelection(work, {...input, kind, time:'09:15'});
  const request: ReviewRecord = {...intent, command:{step:'preview',selection}};
  const original = {plan_fingerprint:fingerprint,expires_at:200,plan:{request:{kind:'fixed_exception'},source:{}}};
  f.enqueue(token); f.enqueue(receipt(original)); f.enqueue(receipt(original,true));
  expect((await f.server.send(context, request).result).preview?.fingerprint).toBe(fingerprint);
  const [url, options] = f.fetch.mock.calls[1]!;
  expect(String(url)).toContain('/fixed-exception/preview');
  expect(String(options?.body)).toContain('"schedule_revision":9007199254740993');
  expect(JSON.parse(String(options?.body))).toMatchObject({effect:kind === 'fixed-exclude' ? 'exclude' : 'add',
    nominal:{kind:'time',local:'2026-12-01T09:15'},reason:input.reason});
  expect((await f.server.original(context, request).result).historical).toBe(true);
  expect(String(f.fetch.mock.calls[2]![0])).toContain('/requests/recurrence.review.preview/original-key');
});


test('the household fold remains explicit in recovered review payloads', () => {
  expect(reviewSelection(work, {...input, fold:'household'}).body).toMatchObject({repeated_time:'household'});
  for (const kind of ['relative-settings','fixed-pattern','fixed-replacement'] as const) {
    const draft = {...input, kind, time:'02:30', fold:'household' as const};
    const selected = reviewSelection(work, draft);
    expect(selected.body).toMatchObject({use_household_fold:true});
    expect(reviewCommand({step:'preview',selection:selected}).selection).toEqual(selected);
    expect(() => reviewCommand({step:'preview',selection:{...selected,body:{...selected.body,use_household_fold:false}}})).toThrow();
    expect(reviewSelection(work, {...draft,fold:'keep_fold'}).body).not.toHaveProperty('use_household_fold');
  }
});

test('recurrence receipt reads both UTC appearances and keeps exact and date-only slots separate', async () => {
  const f = http(), local = '2026-10-25T02:30';
  const slot = (resolution: string, offset_seconds: number) => ({nominal:{local}, resolved:{resolution, offset_seconds}});
  const get = (prospective_slots: unknown) => {
    f.enqueue(receipt({...preview,plan:{request:{kind:'attach_relative'},
      source:{repeated_time:'second_instant'},backlog:{prospective_slots}}}));
    return f.server.original(context,intent).result;
  };
  await expect(get([slot('fold_second',3600),slot('exact',7200),{nominal:{local},resolved:null},
    {planned:slot('fold_first',-14400)}])).resolves.toMatchObject({preview:{repeatedTime:'second_instant',
      repeatedSlots:[{local,offset:3600,fold:'second_instant'},{local,offset:-14400,fold:'first_instant'}]}});
  for (const invalid of [slot('fold_first',86400),slot('fold_first',-86400), {resolved:{resolution:'fold_second',offset_seconds:0}}]) {
    await expect(get([invalid])).rejects.toThrow();
  }
  await expect(get(Array(101).fill(slot('exact',0)))).rejects.toThrow();
  f.enqueue(receipt({...preview,plan:{request:{kind:'attach_relative'},
    source:{prospective_slots:[{planned:slot('fold_second',3600),replaces:null}]}}}));
  await expect(f.server.original(context,intent).result).resolves.toMatchObject({preview:{
    repeatedSlots:[{local,offset:3600,fold:'second_instant'}]}});
  f.enqueue(receipt({...preview,plan:{request:{kind:'attach_relative'},
    source:{initial:slot('fold_second',3600)}}}));
  await expect(f.server.original(context,intent).result).resolves.toMatchObject({preview:{
    repeatedSlots:[{local,offset:3600,fold:'second_instant'}]}});

});

test('preview announces the repeated appearance and its exact offset in Spanish', async () => {
  const widget = document.createElement('domus-recurrence-review');
  widget.language = 'es';
  widget.view = {open:true,busy:false,readOnly:false,selected:true,target:work,records:[],notice:null,
    result:{record:intent,receipt:{...plan,preview:{...plan.preview!,repeatedTime:'second_instant',
      repeatedSlots:[{local:'2026-10-25T02:30',offset:3600,fold:'second_instant'},
        {local:'1900-11-04T02:30',offset:-3661,fold:'first_instant'}]}}}};
  document.body.append(widget); mounted.push(widget);
  await widget.updateComplete;
  expect(widget.shadowRoot?.textContent).toContain('Segunda aparición · UTC+01:00');
  expect(widget.shadowRoot?.textContent).toContain('Primera aparición · UTC−01:01:01');
});

test('missed policy uses exact scoped revisions and stays explicit in the request journal', async () => {
  const draft = {...input, kind:'fixed-missed-policy' as const, missedPolicy:'skip_after_review' as const};
  const selected = reviewSelection(work, reviewDraft(draft));
  expect(selected.body).toEqual({schedule_id:'schedule',schedule_revision:revision,
    policy_revision:'0',missed_occurrence_policy:'skip_after_review'});
  expect(reviewCommand({step:'preview', selection:selected}).selection).toEqual(selected);
  expect(() => reviewDraft({...draft,missedPolicy:'automatic'})).toThrow();
  expect(() => reviewSelection({...work,schedule:{...work.schedule!,missedPolicy:undefined}}, draft)).toThrow();
  const f = http();
  f.enqueue({...targetWire,schedule:{...targetWire.schedule,missed_policy:{policy:'skip_after_review',revision:'$revision'}}});
  const scoped = await f.server.target(context, work.occurrenceId).result;
  expect(scoped.schedule?.missedPolicy?.revision).toBe(revision);
  const original = reviewSelection(scoped, {...draft,missedPolicy:'keep_visible'});
  f.enqueue(token); f.enqueue(receipt({...preview,plan:{request:{kind:'fixed_missed_policy'}}}));
  await f.server.send(context, {...intent,command:{step:'preview',selection:original}}).result;
  expect(f.fetch.mock.calls[2][1].body).toContain('"policy_revision":' + revision);
  f.enqueue({...targetWire,schedule:{...targetWire.schedule,missed_policy:null}});
  await expect(f.server.target(context, work.occurrenceId).result).rejects.toThrow();
  f.enqueue({...targetWire,actions:['fixed-state'],schedule:{...targetWire.schedule,missed_policy:null}});
  expect((await f.server.target(context, work.occurrenceId).result).schedule?.missedPolicy).toBeUndefined();
});

test('the policy editor requires a preview and states the effect in Spanish', async () => {
  const widget = document.createElement('domus-recurrence-review'), dispatch = vi.fn();
  widget.language = 'es';
  const target = {...work,actions:['fixed-missed-policy'] as const};
  widget.view = {open:true,busy:false,readOnly:false,selected:true,target,records:[],notice:null,result:null};
  widget.addEventListener('domus-review-intent', dispatch);
  document.body.append(widget); mounted.push(widget);
  await widget.updateComplete;
  const root = widget.shadowRoot!;
  const control = root.querySelector<HTMLSelectElement>('[name="missedPolicy"]')!;
  expect(control.value).toBe('keep_visible');
  control.value = 'skip_after_review';
  root.querySelector('form')!.dispatchEvent(new Event('submit',{cancelable:true}));
  expect(dispatch).toHaveBeenLastCalledWith(expect.objectContaining({detail:{type:'preview',
    draft:expect.objectContaining({kind:'fixed-missed-policy',missedPolicy:'skip_after_review'})}}));
  const selection = reviewSelection(work,{...input,kind:'fixed-missed-policy',missedPolicy:'skip_after_review'});
  widget.view = {...widget.view!,result:{record:{...intent,command:{step:'preview',selection}},receipt:plan}};
  await widget.updateComplete;
  expect(root.textContent).toContain('Permitir omitir tras revisar');
  expect(root.textContent).toContain('Las tareas vencidas siguen visibles');
  widget.view = {...widget.view!,result:null,target:{...target,schedule:{...work.schedule!,missedPolicy:undefined}}};
  await widget.updateComplete;
  expect(root.querySelector<HTMLSelectElement>('[name="missedPolicy"]')?.value).toBe('keep_visible');
});
