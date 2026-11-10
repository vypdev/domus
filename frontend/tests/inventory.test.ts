import {afterEach, expect, test, vi} from 'vitest';
import {HttpInventoryServer} from '../src/adapters/inventory-http';
import {INVENTORY_JOURNAL_KEY, InventorySessionJournal} from '../src/adapters/inventory-journal';
import {InventoryController} from '../src/application/inventory-controller';
import type {InventoryRequest, InventoryResult, InventoryScope, InventoryState} from '../src/application/inventory-controller';
import type {EntryRead} from '../src/application/ports';
import {adjustmentQuantity, intakeQuantity, inventoryCommand} from '../src/domain/inventory';
import type {InventoryReport, MovementHistory} from '../src/domain/inventory';
import '../src/presentation/domus-inventory';
import corpus from './fixtures/entry-wire.json';

const context = {installationId:'047cc6fb-dfb0-4fa4-b3c3-e0fe54d116b6', channel:'edge' as const, subject:'a'.repeat(32)};
const scope: InventoryScope = {key:'verified', context, readOnly:false};
const register = {action:'inventory.register-product', name:'Olive oil', base_unit:'millilitre'} as const;
const intake = {action:'inventory.intake', product_id:'product', quantity:'1.250001'} as const;
const request: InventoryRequest = {key:'original', scope:scope.key, command:intake};
const savedProduct = {product_id:'product', name:register.name, base_unit:register.base_unit};
const savedMovement = {product_id:'product', movement_id:'movement', base_unit:register.base_unit, quantity:intake.quantity};
const committed = {kind:'committed', operationId:'operation', productId:'product',
  movement:{movementId:'movement', unit:register.base_unit, quantity:intake.quantity, action:intake.action}} as const;
const adjust = {action:'inventory.adjust', product_id:'product', quantity:'-0.000001', reason:'Counted one less'} as const;
const reverse = {action:'inventory.correct-intake', product_id:'product', movement_id:'movement', reason:'Duplicate'} as const;
const wireMovement = {movement_id:'movement', kind:'intake', quantity:'1.250001', member_id:'member', author_alias:null,
  created_at:'100', reason:null, task_occurrence_id:null, corrects:null, corrected_by:null};
const wireHistory = {product_id:'product', product_name:'Olive oil', base_unit:'millilitre',
  movements:[wireMovement], next_cursor:'older'};
const history: MovementHistory = {productId:'product', productName:'Olive oil', unit:'millilitre', cursor:'older',
  movements:[{id:'movement', kind:'intake', quantity:'1.250001', memberId:'member', authorAlias:null, createdAt:'100',
    reason:null, occurrenceId:null, corrects:null, correctedBy:null}]};
const wireProduct = {...savedProduct, recorded:'999999999999.999999', reserved:'0.000001', available:'999999999999.999998'};
const wire = {location_id:'pantry', may_manage:true, products:[wireProduct], next_cursor:'next'};
const report: InventoryReport = {mayManage:true, products:[{id:'product', name:'Olive oil', unit:'millilitre',
  recorded:'999999999999.999999', reserved:'0.000001', available:'999999999999.999998'}], cursor:'next'};
const failure = (code:string) => ({state:'blocked', code, message:'Blocked.', action_required:'Review.', correlation_id:'cor_test'});
const csrf = {csrf_token:'c'.repeat(64)};
const receipt = (result:unknown, state = 'committed') => ({state, archived_by:state === 'historical' ? 'restore' : null,
  operation_id:'operation', created_at:100, result, message:'Saved.', action_required:'Review.'});
const read = <T>(result:T): EntryRead<T> => ({result:Promise.resolve(result), cancel:vi.fn()});
const lost = <T>(): EntryRead<T> => ({result:Promise.reject(new Error('lost')), cancel:vi.fn()});

function http(replies: readonly (readonly [number, unknown])[], deployment: 'native' | 'standalone' = 'standalone') {
  const endpoint = {...corpus[deployment].endpoint, deployment};
  let index = 0;
  const fetch = vi.fn(async (path: string, _init: RequestInit) => {
    const [status,payload] = replies[index++];
    const response = new Response(JSON.stringify(payload), {status, headers:{'Content-Type':'application/json','Cache-Control':'no-store'}});
    Object.defineProperty(response, 'url', {value:endpoint.origin + path});
    return response;
  });
  return {server:new HttpInventoryServer(endpoint, fetch), fetch};
}

test('only supported closed commands and exact positive decimal drafts cross the boundary', () => {
  expect(inventoryCommand(register)).toEqual(register);
  expect(inventoryCommand(intake)).toEqual(intake);
  for (const bad of [null, 1, [], {}, {name:'x',base_unit:'piece',other:'forged'}, {...register,base_unit:'litre'},
    {action:register.action,base_unit:'piece',actor:'forged'}, {action:register.action,name:'x',actor:'forged'},
    {...intake,location_id:'another'}, {action:intake.action,quantity:'1',location_id:'another'},
    {action:intake.action,product_id:'product',location_id:'another'}, {...intake,quantity:'0'},
    {...intake,product_id:'../other'}, {...intake,quantity:'2.50'}, {action:'read',x:1,y:2}])
    expect(() => inventoryCommand(bad)).toThrow();
  expect(intakeQuantity(' 1,250001 ', 'millilitre')).toBe('1.250001');
  expect(intakeQuantity('2.000000', 'gram')).toBe('2');
  expect(intakeQuantity('12', 'piece')).toBe('12');
  expect(intakeQuantity('0', 'piece')).toBeNull();
  expect(intakeQuantity('0.000000', 'gram')).toBeNull();
  expect(intakeQuantity('2.5', 'piece')).toBeNull();
  expect(intakeQuantity('0.0000001', 'gram')).toBeNull();
});

test.each(['native','standalone'] as const)('exact catalog and original receipt use bounded %s endpoints', async mode => {
  const whole = {product_id:'other', name:'Boxes', base_unit:'piece', recorded:'2', reserved:'0', available:'2'};
  const {server, fetch} = http([
    [200,wire], [200,{...wire,products:[whole],next_cursor:null}],
    [200,csrf], [200,receipt(savedProduct)], [200,csrf], [200,receipt(savedMovement)],
    [200,receipt(savedMovement,'historical')], [200,{...receipt(savedMovement),archived_by:'restore'}],
    [404,failure('operation_missing')],
    [404,failure('unrecognized')], [403,failure('permission_denied')],
    [200,csrf], [409,failure('inventory_stock_capacity')],
    [200,csrf], [422,failure('unrecognized')],
    [200,csrf], [503,failure('unavailable')],
  ],mode);
  expect(await server.read(scope,null).result).toEqual(report);
  expect((await server.read(scope,'next/+?').result).products[0].unit).toBe('piece');
  expect(await server.send(scope,{...request,command:register}).result)
    .toEqual({kind:'committed',operationId:'operation',productId:'product',movement:null});
  expect(await server.send(scope,request).result).toEqual(committed);
  expect(await server.original(scope,request).result).toEqual({...committed,kind:'historical'});
  expect(await server.original(scope,request).result).toEqual(committed);
  expect(await server.original(scope,request).result).toBeNull();
  await expect(server.original(scope,request).result).rejects.toMatchObject({code:'unavailable'});
  await expect(server.original(scope,request).result).rejects.toMatchObject({code:'unavailable'});
  expect(await server.send(scope,request).result).toEqual({kind:'rejected',reason:'inventory_stock_capacity',command:intake});
  expect(await server.send(scope,request).result).toEqual({kind:'rejected',reason:'rejected',command:intake});
  await expect(server.send(scope,request).result).rejects.toMatchObject({code:'unavailable'});
  expect(fetch.mock.calls[1][0]).toContain('cursor=next%2F%2B%3F');
  const headers = new Headers(fetch.mock.calls[5][1].headers);
  expect(headers.get('Idempotency-Key')).toBe('original');
  expect(headers.get('X-CSRF-Token')).toBe('c'.repeat(64));
  expect(headers.get('X-Domus-Context')).toContain(context.subject);
  expect(fetch.mock.calls[5][1].body).toBe(JSON.stringify(intake));
});

test('wire replies reject mismatched totals, quantities, identities and unsupported units', async () => {
  for (const value of [
    {...wire,location_id:'elsewhere'}, {...wire,products:{}}, {...wire,products:Array(26).fill(wireProduct)},
    {...wire,products:[wireProduct,wireProduct]}, {...wire,products:[{...wireProduct,available:'1'}]},
    {...wire,products:[{...wireProduct,base_unit:'piece'}]}, {...wire,products:[{...wireProduct,base_unit:'litre'}]},
  ]) await expect(http([[200,value]]).server.read(scope,null).result).rejects.toMatchObject({code:'invalid_response'});
  for (const result of [{...savedMovement, product_id:'other'}, {...savedMovement, quantity:'1'}])
    await expect(http([[200,receipt(result)]]).server.original(scope,request).result).rejects.toMatchObject({code:'invalid_response'});
  for (const result of [{...savedProduct, name:'other'}, {...savedProduct, base_unit:'gram'}])
    await expect(http([[200,receipt(result)]]).server.original(scope,{...request,command:register}).result)
      .rejects.toMatchObject({code:'invalid_response'});
  await expect(http([[200,{...receipt(savedMovement),archived_by:42}]]).server.original(scope,request).result)
    .rejects.toMatchObject({code:'invalid_response'});
});

function journal() {
  const values = new Map<string,string>();
  const journal = new InventorySessionJournal({getItem:key => values.get(key) ?? null,
    setItem:(key,value) => {values.set(key,value);}, removeItem:key => {values.delete(key);}});
  return {values,journal};
}

test('the browser journal accepts only an exact canonical request and retires old scopes', () => {
  const {journal:storage, values} = journal();
  expect(storage.open(scope.key)).toBeNull();
  storage.save(request);
  expect(storage.open(scope.key)).toEqual(request);
  expect(storage.open('other')).toBeNull();
  expect(values.has(INVENTORY_JOURNAL_KEY)).toBe(false);
  for (const invalid of ['x'.repeat(4097), JSON.stringify(request,null,1), JSON.stringify({...request, extra:true})]) {
    values.set(INVENTORY_JOURNAL_KEY,invalid);
    expect(() => storage.open(scope.key)).toThrow();
  }
});

function controller() {
  const local = journal(), publish = vi.fn<(state:InventoryState|null) => void>();
  const load = vi.fn((): EntryRead<InventoryReport> => read(report));
  const send = vi.fn((_scope: InventoryScope, _request: InventoryRequest): EntryRead<InventoryResult> => read(committed));
  const original = vi.fn((_scope: InventoryScope, _request: InventoryRequest): EntryRead<InventoryResult|null> => read(null));
  const movements = vi.fn((_scope: InventoryScope, _product: string, _cursor: string|null): EntryRead<MovementHistory> => read(history));
  const controller = new InventoryController({read:load,history:movements,send,original},local.journal,{requestKey:() => request.key},publish);
  const current = () => publish.mock.lastCall?.[0];
  return {...local, controller, load, movements, send, original, current};
}

test('controller reloads authoritative stock, pages within scope, and blocks denied or uncertain writes', async () => {
  const f = controller(), app = f.controller;
  await app.submit(intake);
  await app.refresh();
  await app.more();
  await app.recover();
  app.bind(scope);
  app.bind(scope);
  await app.submit(intake);
  await vi.waitFor(() => expect(f.current()?.report).toBe(report));
  f.load.mockReturnValueOnce(read({...report, products:[], cursor:null}));
  await app.more();
  expect(f.current()?.report?.products).toEqual(report.products);
  await app.more();
  expect(f.load).toHaveBeenCalledTimes(2);
  f.load.mockReturnValueOnce(read({...report, mayManage:false}));
  await app.refresh();
  await app.submit(intake);
  expect(f.send).not.toHaveBeenCalled();
  f.load.mockReturnValueOnce(lost());
  await app.refresh();
  expect(f.current()).toMatchObject({report:null,notice:'unavailable'});
  await app.refresh();
  await app.submit({bad:true});
  expect(f.current()).toMatchObject({notice:'unavailable'});
  f.send.mockReturnValueOnce(lost());
  await app.submit(intake);
  expect(f.current()).toMatchObject({pending:true,notice:'uncertain'});
  await app.refresh();
  expect(f.current()?.notice).toBe('uncertain');
  await app.submit(intake);
  expect(f.send).toHaveBeenCalledOnce();
  app.bind(null);
  expect(f.current()).toBeNull();
});

test('recovery looks up the same key after reload and only resends under current write authority', async () => {
  const f = controller(), app = f.controller;
  f.journal.save(request);
  app.bind({...scope,readOnly:true});
  await vi.waitFor(() => expect(f.current()?.busy).toBe(false));
  await app.submit(intake);
  await app.recover();
  expect(f.send).not.toHaveBeenCalled();
  expect(f.original.mock.lastCall?.[1]).toEqual(request);
  app.bind(scope);
  await vi.waitFor(() => expect(f.current()?.busy).toBe(false));
  f.original.mockReturnValueOnce(lost());
  await app.recover();
  expect(f.current()?.notice).toBe('uncertain');
  f.load.mockReturnValueOnce(read({...report,mayManage:false}));
  await app.refresh();
  await app.recover();
  expect(f.send).not.toHaveBeenCalled();
  await app.refresh();
  await app.recover();
  expect(f.send.mock.lastCall).toEqual([scope,request]);
  expect(f.current()).toMatchObject({result:committed,pending:false});
  expect(f.journal.open(scope.key)).toBeNull();
  app.bind(null);
  f.journal.save(request);
  app.bind(scope);
  await vi.waitFor(() => expect(f.current()?.busy).toBe(false));
  f.original.mockReturnValueOnce(read({...committed,kind:'historical'}));
  await app.recover();
  expect(f.current()?.result?.kind).toBe('historical');
  f.values.set(INVENTORY_JOURNAL_KEY,'broken');
  app.bind({...scope,key:'other'});
  expect(f.current()).toMatchObject({pending:true,notice:'unavailable'});
});

test('retired reads and recovered results cannot populate a different identity', async () => {
  const f = controller(), app = f.controller;
  const cancel = vi.fn();
  let resolve!: (value:InventoryReport)=>void;
  f.load.mockReturnValueOnce({result:new Promise(done => {resolve = done;}),cancel});
  app.bind(scope);
  app.bind({...scope,key:'other'});
  await vi.waitFor(() => expect(f.current()?.busy).toBe(false));
  resolve({...report, mayManage:false});
  await Promise.resolve();
  expect(cancel).toHaveBeenCalledOnce();
  expect(f.current()?.report).toBe(report);
  let reject!: (error:Error)=>void;
  f.load.mockReturnValueOnce({result:new Promise((_done,fail) => {reject = fail;}),cancel});
  const retiring = app.refresh();
  app.bind(scope);
  reject(new Error('retired'));
  await retiring;
  await vi.waitFor(() => expect(f.current()?.report).toBe(report));
  app.bind(null);
  f.journal.save(request);
  app.bind(scope);
  await vi.waitFor(() => expect(f.current()?.busy).toBe(false));
  let original!: (value:InventoryResult)=>void;
  f.original.mockReturnValueOnce({result:new Promise(done => {original=done;}),cancel});
  const recovering = app.recover();
  await app.recover();
  app.bind(null);
  original(committed);
  await recovering;
  expect(f.current()).toBeNull();
  expect(f.journal.open(scope.key)).toEqual(request);
});

const mounted: HTMLElement[] = [];
afterEach(() => {for (const node of mounted.splice(0)) node.remove();});
function component() {
  const node = document.createElement('domus-inventory'); document.body.append(node); mounted.push(node);
  const root = node.shadowRoot!, events = vi.fn();
  node.addEventListener('domus-inventory-intent',events);
  const press = (label:string) => {
    const control = [...root.querySelectorAll('vyp-ha-button')].find(item => item.state.label === label);
    expect(control).toBeDefined();
    control!.dispatchEvent(new Event('ha-press-request'));
  };
  const input = (form:HTMLFormElement,value:string) => {
    const field = form.querySelector('input')!;
    field.value=value; field.dispatchEvent(new Event('input'));
  };
  const submit = (form:HTMLFormElement) => form.dispatchEvent(new Event('submit',{cancelable:true}));
  return {node,root,events,press,input,submit};
}
const initial: InventoryState = {scope,report:null,history:null,busy:false,pending:false,result:null,notice:null};

test('inventory exposes scoped empty, read-only and failure states with accessible draft review', async () => {
  const {node,root,events,press,input,submit} = component();
  await node.updateComplete;
  expect(root.textContent).not.toContain('Inventory');
  node.view = {...initial,busy:true};
  await node.updateComplete;
  expect(root.textContent).toContain('Loading inventory.');
  node.view = {...initial,pending:true,notice:'uncertain'};
  await node.updateComplete;
  press('Recover original request'); press('Refresh inventory');
  expect(events.mock.calls.map(([event]) => event.detail)).toEqual([{type:'recover'},{type:'refresh'}]);
  node.view = {...initial,report:{...report,mayManage:false,products:[],cursor:null}};
  await node.updateComplete;
  expect(root.textContent).toContain('There are no registered products.');
  expect(root.querySelector('form')).toBeNull();
  node.view = {...initial,scope:{...scope,readOnly:true},report};
  await node.updateComplete;
  expect(root.querySelector('form')).toBeNull();
  node.view = {...initial,report};
  await node.updateComplete;
  press('Show more products');
  const registration = root.querySelector('form')!;
  submit(registration);
  await node.updateComplete;
  expect(registration.querySelector('[role=alert]')?.textContent).toContain('Enter a product name');
  input(registration, register.name);
  const unit = registration.querySelector('select')!;
  unit.value = register.base_unit; unit.dispatchEvent(new Event('change'));
  submit(registration);
  expect(events.mock.lastCall?.[0].detail).toEqual({type:'submit',command:register});
  press('Record stock intake'); await node.updateComplete;
  const entry = root.querySelector<HTMLFormElement>('article form')!;
  submit(entry); await node.updateComplete;
  expect(entry.querySelector('input')?.getAttribute('aria-invalid')).toBe('true');
  input(entry,'1,250001'); submit(entry); await node.updateComplete;
  expect(entry.textContent).toContain('1.250001 millilitres');
  submit(entry);
  expect(events.mock.lastCall?.[0].detail).toEqual({type:'submit',command:intake});
  node.view = {...node.view,busy:true};
  await node.updateComplete;
  const count = events.mock.calls.length;
  submit(registration); submit(entry);
  expect(events.mock.calls).toHaveLength(count);
  node.view = {...node.view,busy:false,result:{kind:'rejected',reason:'inventory_stock_capacity',command:intake}};
  await node.updateComplete;
  expect(entry.querySelector('input')?.value).toBe('1,250001');
  expect(entry.querySelector('[role=alert]')?.textContent).toContain('enter a smaller amount');
  expect(root.querySelector('vyp-ha-feedback')?.state?.message).toContain('Stock was not changed');
  node.view = {...node.view,result:{kind:'rejected',reason:'inventory_stock_capacity',
    command:{...intake,product_id:'other'}}};
  await node.updateComplete;
  expect(entry.querySelector('[role=alert]')).toBeNull();
  node.view = {...node.view,result:{kind:'rejected',reason:'invalid_task_text',command:register}};
  await node.updateComplete;
  expect(entry.querySelector('[role=alert]')).toBeNull();
  input(entry,'2'); submit(entry); await node.updateComplete;
  node.view = {...node.view,result:{kind:'rejected',reason:'inventory_stock_capacity',command:intake}};
  await node.updateComplete;
  expect(entry.querySelector('[role=alert]')).toBeNull();
  input(entry,'1,250001'); submit(entry); await node.updateComplete;
  node.view = {...node.view,result:{kind:'rejected',reason:'permission_denied',command:intake}};
  await node.updateComplete;
  expect(entry.querySelector('[role=alert]')).toBeNull();
});

test('receipt details preserve exact quantities, product focus, and historical outcomes in both locales', async () => {
  const {node,root,press} = component();
  node.view = {...initial,report:{...report,products:[{...report.products[0],unit:'piece',recorded:'2',reserved:'1',available:'1'}]},
    result:{kind:'committed',operationId:'new-op',productId:'product',movement:null}};
  await node.updateComplete;
  expect(root.textContent).toContain('Product registered.');
  expect(root.textContent).not.toContain('Stock movement');
  press('Record stock intake');
  await node.updateComplete;
  expect(root.querySelector('article input')?.getAttribute('inputmode')).toBe('numeric');
  expect(root.textContent).toContain('positive whole number');
  node.language='es'; node.view={...initial,report,result:committed};
  await node.updateComplete;
  expect(root.textContent).toContain('1,250001 mililitros');
  expect(root.textContent).toContain('Movimiento de stock');
  root.querySelector('a')!.click();
  expect(root.activeElement?.id).toBe('product-product');
  node.view={...initial,report:{...report,products:[]},result:{...committed,kind:'historical'}};
  await node.updateComplete;
  expect(root.textContent).toContain('anterior a la restauración');
  expect(root.querySelector('a')).toBeNull();
});

test('adjustment drafts and journal commands retain exact signed decimal values', () => {
  expect(inventoryCommand(adjust)).toEqual(adjust);
  expect(inventoryCommand(reverse)).toEqual(reverse);
  for (const value of [
    {...adjust, quantity:'-0'}, {...adjust, quantity:2}, {...adjust, quantity:'-0.0000001'},
    {...adjust, reason:' '}, {...reverse, movement_id:'../foreign'},
    {action:adjust.action, product_id:'product', reason:'Count', actor:'forged'},
    {action:reverse.action, product_id:'product', reason:'Count', quantity:'-1'},
    {action:reverse.action, product_id:'product', movement_id:'movement', actor:'forged'},
    {action:reverse.action, movement_id:'movement', reason:'Count', actor:'forged'},
    {product_id:'product', movement_id:'movement', reason:'Count', actor:'forged'},
  ]) expect(() => inventoryCommand(value)).toThrow();
  expect(adjustmentQuantity(' -1,250001 ', 'gram')).toBe('-1.250001');
  expect(adjustmentQuantity('+2', 'piece')).toBe('2');
  expect(adjustmentQuantity('-0', 'gram')).toBeNull();
  expect(adjustmentQuantity('1.5', 'piece')).toBeNull();
  const stored = journal().journal;
  stored.save({...request, command:reverse});
  expect(stored.open(scope.key)).toEqual({...request, command:reverse});
});

test('history transport scopes its route and decodes attribution, links and exact receipts', async () => {
  const changed = {...wireMovement, movement_id:'compensation', kind:'intake_correction', quantity:'-1.250001',
    author_alias:'Kitchen lead', reason:'Duplicate', task_occurrence_id:'occurrence', corrects:'movement', corrected_by:'later'};
  const adjusted = {...savedMovement, quantity:adjust.quantity, corrects:null};
  const corrected = {...savedMovement, movement_id:changed.movement_id, quantity:changed.quantity, corrects:reverse.movement_id};
  const {server,fetch} = http([
    [200,wireHistory], [200,{...wireHistory, movements:[changed],next_cursor:null}],
    [200,csrf], [200,receipt(adjusted)], [200,receipt(corrected)],
  ]);
  expect(await server.history(scope,'product',null).result).toEqual(history);
  const older = await server.history(scope,'product','older/+?').result;
  expect(older).toMatchObject({cursor:null, movements:[{
    id:'compensation', quantity:'-1.250001', authorAlias:'Kitchen lead', reason:'Duplicate',
    occurrenceId:'occurrence', corrects:'movement', correctedBy:'later',
  }]});
  expect(fetch.mock.calls[1][0]).toContain('inventory/products/product/movements?limit=25&cursor=older%2F%2B%3F');
  expect(await server.send(scope,{...request,command:adjust}).result)
    .toMatchObject({movement:{action:adjust.action, quantity:adjust.quantity}});
  expect(await server.original(scope,{...request,command:reverse}).result)
    .toMatchObject({movement:{action:reverse.action, movementId:'compensation', quantity:'-1.250001'}});
  for (const value of [
    {...wireHistory, product_id:'other'}, {...wireHistory, movements:{}},
    {...wireHistory, movements:Array(26).fill(wireMovement)},
    {...wireHistory, movements:[wireMovement, wireMovement]},
    {...wireHistory, movements:[{...wireMovement, kind:'unknown'}]},
  ]) await expect(http([[200,value]]).server.history(scope,'product',null).result)
    .rejects.toMatchObject({code:'invalid_response'});
  for (const [command, payload] of [
    [adjust,{...adjusted,corrects:'movement'}],
    [reverse,{...corrected,corrects:'different'}],
    [reverse,{...corrected,quantity:'1.250001'}],
  ] as const) await expect(http([[200,receipt(payload)]]).server.original(scope,{...request,command}).result)
    .rejects.toMatchObject({code:'invalid_response'});
});

test('history paging and refresh retire stale reads and keep the current product', async () => {
  const f = controller(), app = f.controller;
  await app.showHistory('product');
  await app.moreHistory();
  app.closeHistory();
  app.bind(scope);
  await app.showHistory('product'); // A catalog request owns the read.
  await vi.waitFor(() => expect(f.current()?.busy).toBe(false));
  await app.showHistory('product');
  expect(f.current()?.history).toBe(history);
  f.movements.mockReturnValueOnce(read({...history, cursor:null, movements:[]}));
  await app.moreHistory();
  expect(f.current()?.history).toEqual({...history, cursor:null});
  await app.moreHistory();
  await app.refresh();
  expect(f.movements.mock.lastCall).toEqual([scope,'product',null]);
  expect(f.current()?.history).toBe(history);
  f.load.mockReturnValueOnce(lost());
  await app.refresh();
  expect(f.current()).toMatchObject({report:null,history:null});
  await app.showHistory('product');
  expect(f.movements).toHaveBeenCalledTimes(3);
  await app.refresh();
  f.movements.mockReturnValueOnce(lost());
  await app.showHistory('product');
  expect(f.current()).toMatchObject({history:null,notice:'unavailable'});
  await app.showHistory('product');
  expect(f.current()?.notice).toBeNull();
  app.closeHistory();
  expect(f.current()?.history).toBeNull();
  app.bind(null);
  f.journal.save(request);
  app.bind(scope);
  await vi.waitFor(() => expect(f.current()?.busy).toBe(false));
  f.original.mockReturnValueOnce(lost());
  await app.recover();
  await app.showHistory('product');
  expect(f.current()).toMatchObject({history,pending:true,notice:'uncertain'});
  const cancel = vi.fn();
  let resolve!: (value:MovementHistory) => void;
  f.movements.mockReturnValueOnce({result:new Promise(done => {resolve = done;}),cancel});
  const loading = app.showHistory('product');
  app.closeHistory();
  expect(f.current()?.history).toBe(history);
  app.bind(null);
  resolve(history);
  await loading;
  expect(cancel).toHaveBeenCalledOnce();
  expect(f.current()).toBeNull();
});

test('history and signed stock forms expose links, actor, validation and current authority', async () => {
  const {node,root,events,press,submit} = component();
  node.view = {...initial, report};
  await node.updateComplete;
  press('Show movement history');
  expect(events.mock.lastCall?.[0].detail).toEqual({type:'history',productId:'product'});
  node.view = {...initial, report, history:{...history,movements:[],cursor:null}};
  await node.updateComplete;
  expect(root.activeElement?.className).toBe('history');
  expect(root.textContent).toContain('There are no movements for this product.');
  node.view = {...initial,report:{...report,mayManage:false},history};
  await node.updateComplete;
  expect(root.textContent).toContain('+1.250001 millilitres');
  expect(root.textContent).toContain('UTC');
  expect(root.textContent).toContain('member');
  expect([...root.querySelectorAll('vyp-ha-button')].map(item => item.state.label)).not.toContain('Reverse this intake');
  press('Show older movements');
  expect(events.mock.lastCall?.[0].detail).toEqual({type:'more-history'});
  press('Close movement history');
  expect(events.mock.lastCall?.[0].detail).toEqual({type:'close-history'});
  node.view = {...initial,report,history};
  await node.updateComplete;
  press('Adjust stock');
  await node.updateComplete;
  const form = () => root.querySelector<HTMLFormElement>('.history form')!;
  const fill = (value: string, index = 0) => {
    const field = form().querySelectorAll('input')[index];
    field.value=value; field.dispatchEvent(new Event('input'));
  };
  submit(form());
  await node.updateComplete;
  expect(form().textContent).toContain('Enter a reason');
  fill(adjust.reason,1);
  submit(form());
  await node.updateComplete;
  expect(form().textContent).toContain('Enter a quantity');
  fill('-0,000001');
  submit(form());
  expect(events.mock.lastCall?.[0].detail).toEqual({type:'submit',command:adjust});
  node.view = {...node.view,pending:true};
  await node.updateComplete;
  const count = events.mock.calls.length;
  submit(form());
  expect(events.mock.calls).toHaveLength(count);
  node.view = {...node.view,pending:false};
  await node.updateComplete;
  press('Cancel');
  await node.updateComplete;
  expect(form()).toBeNull();
  press('Reverse this intake');
  await node.updateComplete;
  expect(form().textContent).toContain('−1.250001');
  fill(reverse.reason);
  submit(form());
  expect(events.mock.lastCall?.[0].detail).toEqual({type:'submit',command:reverse});
  node.language = 'es';
  node.view = {...node.view,history:{...history,cursor:null,movements:[
    {...history.movements[0],correctedBy:'compensating'},
    {...history.movements[0],id:'compensating',kind:'intake_correction',quantity:'-1.250001',
      reason:'Duplicate',authorAlias:'Kitchen lead',corrects:'movement',occurrenceId:'occurrence'},
  ]},result:{...committed,movement:{...committed.movement,action:reverse.action,quantity:'-1.250001'}}};
  await node.updateComplete;
  expect(form()).toBeNull();
  for (const text of ['Entrada revertida', '-1,250001 mililitros', 'Kitchen lead', 'Duplicate', 'Movimiento original',
    'Movimiento compensatorio', 'Instancia de tarea']) expect(root.textContent).toContain(text);
});
