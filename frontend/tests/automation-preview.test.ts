import {afterEach, expect, test, vi} from 'vitest';
import {AutomationPreviewController} from '../src/application/automation-preview';
import type {AutomationPreviewView} from '../src/application/automation-preview';
import {EntryReadError} from '../src/application/ports';
import {HttpAutomationPreview} from '../src/adapters/automation-preview-http';
import type {InventoryReport, ProductStock} from '../src/domain/inventory';
import '../src/presentation/domus-automation-preview';

const context = {installationId: '01234567-89ab-cdef-0123-456789abcdef', channel: 'edge' as const, subject: 'a'.repeat(32)};
const scope = {key: 'first', context, householdId: 'home', readOnly: false};
const tea = {id: 'tea', name: 'Tea'} as ProductStock;
const coffee = {id: 'coffee', name: 'Coffee'} as ProductStock;
const TITLE = 'Buy <b>tea</b>';
const settled = <T>(value: T) => ({result: Promise.resolve(value), cancel: vi.fn()});
const failed = (error: unknown) => ({result: Promise.reject(error), cancel: vi.fn()});
const page = (products: readonly ProductStock[], cursor: string | null): InventoryReport =>
  ({products, cursor, locations: [], mayManage: true, mayShop: true, mayRequest: true});
const ready = (overrides: Partial<Extract<AutomationPreviewView, {state:'ready'}>> = {}) => ({
  state: 'ready' as const, title: '', selected: null, catalog: {products: [tea], after: null, next: 'next'},
  catalogUnavailable: false, busy: null, result: null, issue: null, ...overrides,
});

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const result = new Promise<T>((done, fail) => {resolve = done; reject = fail;});
  return {result, resolve, reject, cancel: vi.fn()};
}

test('manual preview keeps the draft through validation, read retries and product paging', async () => {
  const access = vi.fn().mockImplementation(() => settled(undefined));
  const preview = vi.fn().mockImplementationOnce(() => settled(true))
    .mockImplementationOnce(() => failed(new EntryReadError('unavailable')))
    .mockImplementationOnce(() => settled(false)).mockImplementationOnce(() => settled(true));
  const read = vi.fn().mockImplementationOnce(() => failed(new Error('catalog unavailable')))
    .mockImplementationOnce(() => settled(page([tea], 'next')))
    .mockImplementationOnce(() => failed(new Error('next page unavailable')))
    .mockImplementationOnce(() => settled(page([coffee], null)))
    .mockImplementationOnce(() => settled(page([tea], 'next')));
  const publish = vi.fn();
  const controller = new AutomationPreviewController({access, preview}, {read}, publish);
  await controller.handle({type:'retry'});
  controller.bind(scope, false);
  await controller.handle({type:'retry'});
  expect(access).not.toHaveBeenCalled();
  controller.bind(scope, true);
  controller.bind(scope, true);
  await controller.handle({type:'retry'});
  expect(access).toHaveBeenCalledOnce();
  const emptyCatalog = {products:[], after:null, next:null};
  const unavailableCatalog = ready({catalog:emptyCatalog, catalogUnavailable:true});
  await vi.waitFor(() => expect(publish).toHaveBeenLastCalledWith(unavailableCatalog));
  await controller.handle({type:'title', value:TITLE});
  await controller.handle({type:'preview'});
  expect(preview).toHaveBeenLastCalledWith(context, {title:TITLE, productId:null});
  expect(publish).toHaveBeenLastCalledWith({...unavailableCatalog, title:TITLE, result:true});
  await controller.handle({type:'retry'});
  await vi.waitFor(() => expect(publish).toHaveBeenLastCalledWith(ready({title:TITLE})));
  await controller.handle({type:'title', value:''});
  expect(access).toHaveBeenCalledWith(context, 'home');
  expect(read).toHaveBeenLastCalledWith(scope, null);
  await controller.handle(undefined);
  await controller.handle({type:'first'});
  await controller.handle({type:'title', value: 2} as never);
  await controller.handle({type:'product', value:'foreign'});
  expect(publish).toHaveBeenLastCalledWith(ready());

  await controller.handle({type:'preview'});
  expect(publish).toHaveBeenLastCalledWith(ready({issue:'title'}));
  expect(preview).toHaveBeenCalledOnce();
  await controller.handle({type:'title', value:TITLE});
  await controller.handle({type:'product', value:tea.id});
  await controller.handle({type:'next'});
  expect(publish).toHaveBeenLastCalledWith(ready({title:TITLE, selected:tea, catalogUnavailable:true}));
  await controller.handle({type:'next'});
  const second = {products: [coffee], after:'next', next:null};
  expect(publish).toHaveBeenLastCalledWith(ready({title:TITLE, selected:tea, catalog:second}));
  await controller.handle({type:'next'});
  await controller.handle({type:'preview'});
  expect(preview).toHaveBeenLastCalledWith(context, {title:TITLE, productId:tea.id});
  expect(publish).toHaveBeenLastCalledWith(ready({title:TITLE, selected:tea, catalog:second, issue:'preview'}));
  await controller.handle({type:'preview'});
  expect(publish).toHaveBeenLastCalledWith(ready({title:TITLE, selected:tea, catalog:second, result:false}));
  await controller.handle({type:'first'});
  expect(publish).toHaveBeenLastCalledWith(ready({title:TITLE, selected:tea, result:false}));
  await controller.handle({type:'product', value:null});
  await controller.handle({type:'preview'});
  expect(preview).toHaveBeenLastCalledWith(context, {title:TITLE, productId:null});
  expect(publish).toHaveBeenLastCalledWith(ready({title:TITLE, result:true}));
});

test('navigation retains a draft, reloads products, cancels stale outcomes and rechecks access', async () => {
  const obsolete = deferred<boolean>(), lateFailure = deferred<boolean>();
  const access = vi.fn().mockImplementationOnce(() => settled(undefined))
    .mockImplementationOnce(() => failed(new Error('HA unavailable')))
    .mockImplementationOnce(() => settled(undefined)).mockImplementationOnce(() => settled(undefined))
    .mockImplementationOnce(() => failed(new EntryReadError('authentication_required')));
  const read = vi.fn().mockImplementationOnce(() => settled(page([tea], 'next')))
    .mockImplementationOnce(() => settled(page([tea, coffee], null)))
    .mockImplementationOnce(() => settled(page([tea], 'next')));
  const preview = vi.fn().mockReturnValueOnce(obsolete).mockReturnValueOnce(lateFailure)
    .mockImplementationOnce(() => failed(new EntryReadError('forbidden')));
  const publish = vi.fn();
  const controller = new AutomationPreviewController({access, preview}, {read}, publish);
  controller.bind(scope, true);
  await vi.waitFor(() => expect(publish).toHaveBeenLastCalledWith(ready()));
  await controller.handle({type:'title', value:TITLE});
  const first = controller.handle({type:'preview'});
  expect(publish).toHaveBeenLastCalledWith(ready({title:TITLE, busy:'preview'}));
  await controller.handle({type:'title', value:'ignored during request'});
  controller.bind(scope);
  expect(obsolete.cancel).toHaveBeenCalledOnce();
  obsolete.resolve(true);
  await first;
  expect(publish).toHaveBeenLastCalledWith(null);

  controller.bind(scope, true);
  await vi.waitFor(() => expect(publish).toHaveBeenLastCalledWith({state:'unavailable'}));
  await controller.handle({type:'retry'});
  await vi.waitFor(() => expect(publish).toHaveBeenLastCalledWith(ready({title:TITLE,
    catalog:{products:[tea, coffee], after:null, next:null}})));
  const second = controller.handle({type:'preview'});
  const secondContext = {...context, subject:'b'.repeat(32)};
  controller.bind({...scope, key:'second', context:secondContext}, true);
  expect(lateFailure.cancel).toHaveBeenCalledOnce();
  lateFailure.reject(new Error('late'));
  await second;
  await vi.waitFor(() => expect(publish).toHaveBeenLastCalledWith(ready()));
  await controller.handle({type:'title', value:'New draft'});
  await controller.handle({type:'preview'});
  expect(publish).toHaveBeenLastCalledWith({state:'denied'});
  expect(preview).toHaveBeenLastCalledWith(secondContext, {title:'New draft', productId:null});
  await controller.handle({type:'retry'});
  expect(publish).toHaveBeenLastCalledWith({state:'denied'});
  controller.bind(null);
  expect(publish).toHaveBeenLastCalledWith(null);
});

const target = {origin:'https://domus.test', deployment:'standalone' as const, applicationBase:'/'};
const result = {version:1, trigger:'manual', task_title:TITLE, would_create:true, conditions:[]};
const condition = {path:[], kind:'stock_below_minimum', product_id:'tea', matched:false};
const conditioned = {...result, would_create:false, conditions:[condition]};
function response(path: string, value: unknown, status = 200): Response {
  const reply = new Response(JSON.stringify(value), {status,
    headers:{'Content-Type':'application/json', 'Cache-Control':'no-store'}});
  Object.defineProperty(reply, 'url', {value:target.origin + path});
  return reply;
}

test('HTTP preview sends the verified assertion and CSRF, and omits mutation receipts', async () => {
  const transport = vi.fn(async (path: string, init: RequestInit) => {
    expect((init.headers as Headers).get('X-Domus-Context')).toBe('v1:' + context.installationId + ':edge:' + context.subject);
    if (path.endsWith('preview-access')) return response(path, {household_id:'home'});
    if (path.endsWith('csrf')) return response(path, {csrf_token:'c'.repeat(64)});
    expect(init.method).toBe('POST');
    expect((init.headers as Headers).get('X-CSRF-Token')).toBe('c'.repeat(64));
    expect((init.headers as Headers).has('Idempotency-Key')).toBe(false);
    const body = JSON.parse(String(init.body));
    expect(body).toEqual({version:1, trigger:{kind:'manual'}, condition:body.condition, action:{kind:'task.create',title:TITLE}});
    if (body.condition === null) return response(path, result);
    expect(body.condition).toEqual({kind:'stock_below_minimum', product_id:'tea'});
    return response(path, conditioned);
  });
  const server = new HttpAutomationPreview(target, transport);
  await expect(server.access(context, 'home').result).resolves.toBeUndefined();
  await expect(server.access(context, 'foreign').result).rejects.toMatchObject({code:'invalid_response'});
  await expect(server.preview(context, {title:TITLE,productId:null}).result).resolves.toBe(true);
  await expect(server.preview(context, {title:TITLE,productId:'tea'}).result).resolves.toBe(false);
});

test.each([
  [null, {...result, version:2}], [null, {...result, trigger:'schedule'}],
  [null, {...result, task_title:'different'}], [null, {...result, would_create:'yes'}],
  [null, {...result, would_create:false}], [null, {...result, conditions:null}],
  ['tea', result], ['tea', {...conditioned, conditions:[{...condition, path:null}]}],
  ['tea', {...conditioned, conditions:[{...condition, path:[0]}]}],
  ['tea', {...conditioned, conditions:[{...condition, kind:'all'}]}],
  ['tea', {...conditioned, conditions:[{...condition, product_id:'foreign'}]}],
  ['tea', {...conditioned, conditions:[{...condition, matched:true}]}],
])('HTTP preview rejects an unrelated or invalid explanation for %s', async (productId, value) => {
  const server = new HttpAutomationPreview(target, async path => response(path,
    path.endsWith('csrf') ? {csrf_token:'c'.repeat(64)} : value));
  await expect(server.preview(context, {title:TITLE,productId}).result).rejects.toMatchObject({code:'invalid_response'});
});

test('HTTP preview propagates denial after authentication of a request', async () => {
  const server = new HttpAutomationPreview(target, async path => path.endsWith('csrf')
    ? response(path, {csrf_token:'c'.repeat(64)})
    : response(path, {state:'blocked', code:'permission_denied', message:'Denied.',
      action_required:'Review permissions.', correlation_id:'cor_123'}, 403));
  await expect(server.preview(context, {title:TITLE,productId:null}).result).rejects.toMatchObject({code:'forbidden'});
});

afterEach(() => document.querySelectorAll('domus-automation-preview').forEach(element => element.remove()));

test('preview component localizes draft, status and recovery, and keeps the title literal', async () => {
  const element = document.createElement('domus-automation-preview');
  document.body.append(element);
  const view = (value: AutomationPreviewView) => {element.view = value; return element.updateComplete;};
  const root = element.shadowRoot!;
  const feedback = () => root.querySelector('vyp-ha-feedback')!.state!.message;
  const messages = vi.fn();
  element.addEventListener('domus-automation-preview-intent', messages);
  const latest = () => messages.mock.calls.at(-1)?.[0]?.detail;
  const button = (label: string) => Array.from(root.querySelectorAll('vyp-ha-button')).find(item => item.state.label === label)!;
  const press = async (label: string) => {
    const item = button(label);
    await item.updateComplete;
    item.shadowRoot!.querySelector('button')!.click();
  };
  await element.updateComplete;
  expect(root.querySelector('vyp-ha-card')).toBeNull();
  await view({state:'loading'});
  expect(feedback()).toBe('Loading automation preview…');
  await view({state:'denied'});
  expect(feedback()).toContain('current household permissions');
  await view({state:'unavailable'});
  await press('Try again');
  expect(latest()).toEqual({type:'retry'});
  await view(ready());
  const form = root.querySelector('form')!;
  const field = root.querySelector('vyp-ha-field')!;
  const select = root.querySelector('vyp-ha-select')!;
  field.dispatchEvent(new CustomEvent('ha-value-request', {detail:{value:TITLE}}));
  expect(latest()).toEqual({type:'title', value:TITLE});
  select.dispatchEvent(new CustomEvent('ha-select-request', {detail:{value:'tea'}}));
  expect(latest()).toEqual({type:'product', value:'tea'});
  form.dispatchEvent(new SubmitEvent('submit', {cancelable:true}));
  expect(latest()).toEqual({type:'preview'});
  await press('Next products');
  expect(latest()).toEqual({type:'next'});
  await view(ready({issue:'title'}));
  expect(field.state.error).toContain('1 to 160');
  expect(root.activeElement).toBe(field);
  await view(ready({busy:'preview'}));
  expect(feedback()).toBe('Checking the rule…');
  const count = messages.mock.calls.length;
  form.dispatchEvent(new SubmitEvent('submit', {cancelable:true}));
  expect(messages).toHaveBeenCalledTimes(count);
  await view(ready({busy:'products'}));
  expect(feedback()).toBe('Loading products…');
  await view(ready({issue:'preview'}));
  expect(feedback()).toContain('Could not preview the rule');
  await view(ready({catalogUnavailable:true}));
  expect(feedback()).toContain('You can preview without a stock condition.');
  expect(select.hasAttribute('disabled')).toBe(false);
  await view(ready({catalogUnavailable:true, catalog:{products:[],after:null,next:null}}));
  expect(root.querySelector('vyp-ha-select')).toBeNull();
  await press('Try again');
  expect(latest()).toEqual({type:'retry'});
  await view(ready({title:TITLE,result:true,catalog:{products:[],after:null,next:null}}));
  expect(root.querySelector('.result')!.textContent).toContain('Would create this task');
  expect(root.querySelector('.result b')).toBeNull();
  expect(root.querySelector('.result')!.textContent).toContain(TITLE);
  element.language = 'es';
  await view(ready({catalogUnavailable:true, catalog:{products:[],after:null,next:null}}));
  expect(feedback()).toContain('Puedes previsualizar la regla sin una condición de existencias.');
  const picked = {...tea,name:'Té\u0080'};
  const catalog = {products:[coffee],after:'next',next:null};
  await view(ready({title:TITLE,result:false,catalog,selected:picked}));
  expect(root.querySelector('vyp-ha-select')!.state.options.map(option => option.label)).toEqual(['Coffee','Té�']);
  expect(root.querySelector('.result')!.textContent).toContain('No se cumple la condición de existencias.');
  expect(root.querySelector('.result')!.textContent).toContain('No se crearía ninguna tarea');
  await press('Primeros productos');
  expect(latest()).toEqual({type:'first'});
  await view(ready({title:TITLE,result:true,catalog,selected:picked}));
  expect(root.querySelector('.result')!.textContent).toContain('Las existencias disponibles están por debajo del mínimo.');
});
