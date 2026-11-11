import {afterEach, expect, test, vi} from 'vitest';
import {HttpInventoryServer} from '../src/adapters/inventory-http';
import {INVENTORY_JOURNAL_KEY, InventorySessionJournal} from '../src/adapters/inventory-journal';
import {InventoryController} from '../src/application/inventory-controller';
import type {InventoryRequest, InventoryResult, InventoryScope, InventoryState} from '../src/application/inventory-controller';
import type {EntryRead} from '../src/application/ports';
import {adjustmentQuantity, intakeQuantity, inventoryCommand} from '../src/domain/inventory';
import {revisionValue} from '../src/domain/administration';
import type {InventoryReport, MovementHistory, Purchase, PurchaseReceipts, Purchases, PurchaseSessions, PurchaseSessionDetail} from '../src/domain/inventory';
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
  created_at:'100', reason:null, task_occurrence_id:null, corrects:null, corrected_by:null, shopping_receipt:false, return_of:null, transfer:null};
const historyStock = {recorded:'1.250001', reserved:'0', available:'1.250001'};
const wireHistory = {product_id:'product', product_name:'Olive oil', base_unit:'millilitre',
  movements:[wireMovement], next_cursor:'older', total:historyStock,
  locations:[{location_id:'pantry', name:null, stock:historyStock}]};
const history: MovementHistory = {productId:'product', productName:'Olive oil', unit:'millilitre', cursor:'older', total:historyStock,
  locations:[{id:'pantry', name:null, stock:historyStock}], movements:[{id:'movement', kind:'intake', quantity:'1.250001', memberId:'member', authorAlias:null, createdAt:'100',
    reason:null, occurrenceId:null, corrects:null, correctedBy:null, shoppingReceipt:false, returnOf:null, transfer:null}]};
const emptyPolicy = {source_id:'product', minimum:'0', target:'0', revision:'0', needed:'0'} as const;
const policy = {action:'inventory.configure-replenishment', product_id:'product', minimum:'1.250001',
  target:'2.000001', expected_revision:'0'} as const;
const buy = {action:'shopping.purchase', product_id:'product', name:null, quantity:'6.000001'} as const;
const arrive = {action:'shopping.receive', purchase_id:'purchase', quantity:'4.000001',
  expected_revision:revisionValue('2')} as const;
const postReceipt = {action:'shopping.post-receipt', purchase_id:'purchase', receipt_id:'arrival'} as const;
const wirePurchase = {purchase_id:'purchase', product_id:'product', name:'Olive oil', base_unit:'millilitre',
  purchased:'6.000001', received:'4.000001', remaining:'2', pending_stock:'4.000001', cancelled:'0', revision:'2',
  member_id:'member', author_alias:'Shopper', created_at:'100'};
const wireArrival = {receipt_id:'arrival', quantity:'4.000001', member_id:'member', author_alias:null,
  created_at:'101', movement_id:null, voided:null, correction:null, returned:null};
const purchase: Purchase = {id:'purchase', productId:'product', name:'Olive oil', unit:'millilitre',
  purchased:'6.000001', received:'4.000001', remaining:'2', pendingStock:'4.000001', cancelled:'0',
  revision:arrive.expected_revision, memberId:'member', authorAlias:'Shopper', createdAt:'100'};
const purchases: Purchases = {items:[purchase],cursor:'older'};
const purchaseReceipts: PurchaseReceipts = {purchase,items:[{
  id:'arrival', quantity:'4.000001', memberId:'member', authorAlias:null, createdAt:'101', movementId:null, voided:null, correction:null, returned:null,
}],cancellation:null,cursor:'older'};
const savedPolicy = {product_id:'product', minimum:policy.minimum, target:policy.target, revision:'1'};
const wireProduct = {...savedProduct, reference_id:'reference', recorded:'999999999999.999999', reserved:'0.000001',
  available:'999999999999.999998', replenishment:emptyPolicy, outstanding_purchase:'0', shopping_needed:'0'};
const wire = {location_id:'pantry', may_manage:true, may_shop:true, may_request:true, products:[wireProduct], next_cursor:'next', locations:[]};
const report: InventoryReport = {mayManage:true, mayShop:true, mayRequest:true, products:[{id:'product', referenceId:'reference', name:'Olive oil', unit:'millilitre',
  recorded:'999999999999.999999', reserved:'0.000001', available:'999999999999.999998',
  outstandingPurchase:'0', shoppingNeeded:'0',
  replenishment:{sourceId:'product', minimum:'0', target:'0', revision:'0', needed:'0'}}], cursor:'next', locations:[]};
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
  const whole = {...wireProduct, product_id:'other', name:'Boxes', base_unit:'piece', recorded:'2', reserved:'0', available:'2',
    replenishment:{...emptyPolicy,source_id:'other'}};
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

test('replenishment decodes an exact projection and recovers only its original matching settings', async () => {
  const available = {...wireProduct, recorded:'2', reserved:'1.25', available:'0.75'};
  const replenishment = {...emptyPolicy, minimum:policy.minimum, target:policy.target, needed:'1.250001', revision:'1'};
  const item = {...available,replenishment,shopping_needed:replenishment.needed};
  const operation = {...request,command:policy};
  const {server,fetch} = http([
    [200,{...wire,products:[item]}],
    [200,csrf], [200,receipt(savedPolicy)],
    [200,receipt(savedPolicy,'historical')],
  ]);
  expect((await server.read(scope,null).result).products[0].replenishment).toEqual({
    sourceId:'product',minimum:policy.minimum,target:policy.target,needed:'1.250001',revision:'1',
  });
  expect(await server.send(scope,operation).result).toMatchObject({kind:'committed',replenishmentSaved:true});
  expect(await server.original(scope,operation).result).toMatchObject({kind:'historical',replenishmentSaved:true});
  expect(fetch.mock.calls[2][1].body).toBe(JSON.stringify(policy));
  expect(fetch.mock.calls[3][0]).toContain('inventory/requests/inventory.configure-replenishment/original');
  expect(inventoryCommand({...policy,expected_revision:'9223372036854775807'})).toMatchObject({
    expected_revision:'9223372036854775807',
  });
  for (const command of [
    {...policy, actor:'forged'}, {...policy,expected_revision:'01'}, {...policy,expected_revision:0},
    {...policy,minimum:undefined}, {...policy,target:'1.0000001'},
    {action:policy.action, product_id:'product', target:'2', expected_revision:'0', extra:'forged'},
  ]) expect(() => inventoryCommand(command)).toThrow();
  const journalInstance = journal().journal;
  journalInstance.save(operation);
  expect(journalInstance.open(scope.key)).toEqual(operation);
  for (const product of [
    {...item,replenishment:{...replenishment, source_id:'other'}},
    {...item,replenishment:{...replenishment, target:'1'}},
    {...item,replenishment:{...replenishment, revision:'0'}},
    {...item,replenishment:{...replenishment, minimum:'0', revision:'0'}},
    {...item,replenishment:{...replenishment, needed:'0'}},
    {...item,base_unit:'piece',recorded:'1',available:'1',reserved:'0'},
    {...item,base_unit:'piece',recorded:'1',available:'1',reserved:'0',
      replenishment:{...replenishment,minimum:'1'}},
  ]) await expect(http([[200,{...wire,products:[product]}]]).server.read(scope,null).result)
    .rejects.toMatchObject({code:'invalid_response'});
  for (const altered of [{product_id:'other'}, {minimum:'0'}, {target:'0'}, {revision:'2'}])
    await expect(http([[200,receipt({...savedPolicy,...altered})]]).server.original(scope,operation).result)
      .rejects.toMatchObject({code:'invalid_response'});
});

test('shopping commands and original receipts keep purchase, arrival and posting identities separate', async () => {
  const free = {...buy, product_id:null, name:'Apples', quantity:'1'};
  for (const value of [buy, free, arrive, postReceipt]) expect(inventoryCommand(value)).toEqual(value);
  for (const invalid of [
    {...buy, extra:true}, {...buy, product_id:null}, {...buy,name:'Both'}, {...buy,quantity:'0'},
    {...buy, name:undefined}, {...arrive, extra:true}, {...arrive, expected_revision:'0'},
    {...arrive,quantity:'0'}, {...postReceipt,extra:true}, {...postReceipt,receipt_id:'../different'},
  ]) expect(() => inventoryCommand(invalid)).toThrow();
  const buyResult = {purchase_id:'purchase'};
  const arrivalResult = {...buyResult,receipt_id:'arrival'};
  const postResult = {...arrivalResult,movement_id:'movement'};
  const {server, fetch} = http([
    [200,csrf], [200,receipt(buyResult)], [200,receipt(arrivalResult,'historical')], [200,receipt(postResult)],
  ]);
  expect(await server.send(scope,{...request,command:buy}).result).toMatchObject({
    kind:'committed', shoppingAction:buy.action, productId:null,
  });
  expect(await server.original(scope,{...request,command:arrive}).result).toMatchObject({
    kind:'historical', shoppingAction:arrive.action,
  });
  expect(await server.original(scope,{...request,command:postReceipt}).result).toMatchObject({
    kind:'committed', shoppingAction:postReceipt.action,
  });
  expect(fetch.mock.calls[2][0]).toContain('inventory/requests/shopping.receive/original');
  for (const payload of [{...postResult,purchase_id:'other'},{...postResult,receipt_id:'other'}])
    await expect(http([[200,receipt(payload)]]).server.original(scope,{...request,command:postReceipt}).result)
      .rejects.toMatchObject({code:'invalid_response'});
  const local = journal();
  local.journal.save({...request,command:postReceipt});
  expect(local.journal.open(scope.key)).toEqual({...request,command:postReceipt});
});

test('protected shopping pages and Pantry supply have exact bounded responses', async () => {
  const free = {...wirePurchase, product_id:null, name:'Apples', base_unit:'piece',
    purchased:'2', received:'2', remaining:'0', pending_stock:'0'};
  const page = {purchases:[wirePurchase],next_cursor:'older'};
  const details = {purchase:wirePurchase,receipts:[wireArrival],cancellation:null,next_cursor:'older'};
  const {server,fetch} = http([
    [200,page], [200,{...page,purchases:[free],next_cursor:null}], [200,details],
    [200,{...details,receipts:[{...wireArrival,movement_id:'movement'}],next_cursor:null}],
    [200,{...wire,products:[{...wireProduct,outstanding_purchase:'1'}]}],
  ]);
  expect(await server.purchases(scope,null).result).toEqual(purchases);
  expect((await server.purchases(scope,'older/+').result).items[0]).toMatchObject({productId:null,unit:'piece'});
  expect(await server.purchaseReceipts(scope,'purchase',null).result).toEqual(purchaseReceipts);
  expect((await server.purchaseReceipts(scope,'purchase','older/+').result).items[0].movementId).toBe('movement');
  expect((await server.read(scope,null).result).products[0].outstandingPurchase).toBe('1');
  expect(fetch.mock.calls[1][0]).toContain('inventory/purchases?limit=25&cursor=older%2F%2B');
  expect(fetch.mock.calls[3][0]).toContain('inventory/purchases/purchase/receipts?limit=25&cursor=older%2F%2B');
  for (const invalid of [
    {...page,purchases:{}}, {...page,purchases:Array(26).fill(wirePurchase)},
    {...page,purchases:[wirePurchase,wirePurchase]},
    ...[
      {...wirePurchase,remaining:'1'}, {...wirePurchase,pending_stock:'5'},
      {...wirePurchase,product_id:null}, {...free,pending_stock:'1'},
      {...free,purchased:'2.000001',remaining:'0.000001'},
    ].map(item => ({...page,purchases:[item]})),
  ]) await expect(http([[200,invalid]]).server.purchases(scope,null).result).rejects.toMatchObject({code:'invalid_response'});
  for (const invalid of [
    {...details,purchase:{...wirePurchase,purchase_id:'other'}}, {...details,receipts:{}},
    {...details,receipts:Array(26).fill(wireArrival)}, {...details,receipts:[wireArrival,wireArrival]},
  ]) await expect(http([[200,invalid]]).server.purchaseReceipts(scope,'purchase',null).result)
    .rejects.toMatchObject({code:'invalid_response'});
  for (const invalid of [
    {...wireProduct,shopping_needed:'1'},
    {...wireProduct,base_unit:'piece',recorded:'2',available:'2',reserved:'0',outstanding_purchase:'0.1'},
  ]) await expect(http([[200,{...wire,products:[invalid]}]]).server.read(scope,null).result)
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
  const buys = vi.fn((_scope: InventoryScope, _cursor: string|null): EntryRead<Purchases> => read(purchases));
  const arrivals = vi.fn((_scope: InventoryScope, _id:string, _cursor: string|null): EntryRead<PurchaseReceipts> => read(purchaseReceipts));
  const controller = new InventoryController({read:load,history:movements,purchases:buys,purchaseReceipts:arrivals,
    purchaseSessions:() => lost(),purchaseSession:() => lost(),shoppingList:() => lost(),shoppingSources:() => lost(),send,original},
    local.journal,{requestKey:() => request.key},publish);
  const current = () => publish.mock.lastCall?.[0];
  return {...local, controller, load, movements, buys, arrivals, send, original, current};
}

test('shopping reads and writes stay within the current authorized session and use original recovery', async () => {
  const f = controller(), app = f.controller;
  await app.showPurchases(); await app.morePurchases();
  await app.showPurchaseReceipts('purchase'); await app.morePurchaseReceipts();
  app.bind(scope);
  await vi.waitFor(() => expect(f.current()?.busy).toBe(false));
  await app.showPurchaseReceipts('purchase');
  const reading = app.showPurchases();
  await app.showPurchases();
  await reading;
  expect(f.buys).toHaveBeenCalledOnce();
  f.buys.mockReturnValueOnce(read({items:[],cursor:null}));
  await app.morePurchases(); await app.morePurchases();
  const detail = app.showPurchaseReceipts('purchase');
  await app.showPurchaseReceipts('purchase');
  await detail;
  expect(f.arrivals).toHaveBeenCalledOnce();
  f.arrivals.mockReturnValueOnce(read({...purchaseReceipts,items:[],cursor:null}));
  await app.morePurchaseReceipts(); await app.morePurchaseReceipts();
  expect(f.current()?.purchaseReceipts?.items).toEqual(purchaseReceipts.items);
  f.load.mockReturnValueOnce(read({...report,mayManage:false}));
  await app.refresh();
  await app.submit(postReceipt);
  expect(f.send).not.toHaveBeenCalled();
  f.send.mockReturnValueOnce(lost());
  await app.submit(buy);
  expect(f.send.mock.lastCall?.[1].command).toEqual(buy);
  await app.showPurchases(); await app.showPurchaseReceipts('purchase');
  expect(f.current()).toMatchObject({pending:true,notice:'uncertain'});
  await app.recover();
  expect(f.current()?.pending).toBe(false);
  expect(f.send.mock.lastCall?.[1].command).toEqual(buy);
  f.arrivals.mockReturnValueOnce(lost());
  await app.showPurchaseReceipts('purchase');
  expect(f.current()?.purchaseReceipts).toBeNull();
  f.buys.mockReturnValueOnce(lost());
  await app.showPurchases();
  expect(f.current()?.purchases).toBeNull();
  f.load.mockReturnValueOnce(lost());
  await app.refresh();
  await app.showPurchases();
  expect(f.current()?.report).toBeNull();
});

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

test('Shopping distinguishes tracked stock posting from an untracked receipt and retains the original operations', async () => {
  const {node,root,events,submit} = component();
  const open = {...initial,report};
  node.view = open;
  await node.updateComplete;
  const element = root.querySelector('domus-shopping')!;
  await element.updateComplete;
  const shop = element.shadowRoot!;
  const press = (label:string) => {
    const control = [...shop.querySelectorAll('vyp-ha-button')].find(button => button.state.label === label);
    expect(control).toBeDefined();
    control!.dispatchEvent(new Event('ha-press-request'));
  };
  const assign = async (state: InventoryState) => {
    node.view = state; await node.updateComplete; await element.updateComplete;
  };
  const command = () => events.mock.lastCall?.[0].detail;
  press('Show purchases');
  expect(command()).toEqual({type:'purchases'});
  const empty = {...open,purchases:{items:[],cursor:null},report:{...report,mayShop:false}};
  await assign(empty);
  expect(shop.textContent).toContain('There are no purchases recorded.');
  expect(shop.querySelector('form')).toBeNull();

  const extra = {...report.products[0],id:'other',name:'Tinned beans',outstandingPurchase:'1'};
  const shopping = {...open,report:{...report,products:[...report.products,extra]},purchases};
  await assign(shopping);
  press('Show older purchases');
  expect(command()).toEqual({type:'more-purchases'});
  press('Show physical receipts');
  expect(command()).toEqual({type:'purchase-receipts',purchaseId:'purchase'});
  const purchaseForm = shop.querySelector<HTMLFormElement>('#purchase-form')!;
  const quantity = purchaseForm.querySelector<HTMLInputElement>('input[name=quantity]')!;
  submit(purchaseForm); await element.updateComplete;
  expect(purchaseForm.querySelector('[role=alert]')?.textContent).toContain('Enter a quantity');
  quantity.value = '2';
  submit(purchaseForm); await element.updateComplete;
  expect(purchaseForm.querySelector('[role=alert]')?.textContent).toContain('Enter a product name');
  purchaseForm.querySelector<HTMLInputElement>('input[name=name]')!.value = 'Apples';
  submit(purchaseForm); await element.updateComplete;
  expect(command()).toEqual({type:'submit',command:{action:buy.action,product_id:null,name:'Apples',quantity:'2'}});
  const select = purchaseForm.querySelector('select')!;
  expect(select.querySelector<HTMLOptionElement>('option[value=other]')?.disabled).toBe(true);
  select.value='product'; select.dispatchEvent(new Event('change'));
  await element.updateComplete;
  expect(purchaseForm.textContent).toContain('Still to buy for Pantry');
  quantity.value='6,000001';
  submit(purchaseForm);
  expect(command()).toEqual({type:'submit',command:buy});
  const committedPurchase = {kind:'committed',operationId:'buy',movement:null,productId:null,shoppingAction:buy.action} as const;
  await assign({...shopping,result:committedPurchase});
  expect(root.textContent).toContain('Purchase recorded.');
  expect(select.value).toBe('');
  const tracked = {...shopping,purchaseReceipts:{...purchaseReceipts,items:[]}};
  await assign(tracked);
  expect(shop.activeElement?.tagName).toBe('H4');
  expect(shop.textContent).toContain('No physical receipts recorded.');
  const form = shop.querySelector<HTMLFormElement>('#arrival-form')!;
  const amount = form.querySelector('input')!;
  submit(form); await element.updateComplete;
  expect(form.querySelector('[role=alert]')?.textContent).toContain('Enter a quantity');
  amount.value='3';
  submit(form); await element.updateComplete;
  expect(form.querySelector('[role=alert]')?.textContent).toContain('no greater than');
  amount.value='1,25';
  const before = events.mock.calls.length;
  await assign({...tracked,pending:true});
  submit(form); submit(purchaseForm);
  expect(events).toHaveBeenCalledTimes(before);
  await assign({...tracked,purchaseReceipts});
  submit(form);
  expect(command()).toEqual({type:'submit',command:{...arrive,quantity:'1.25'}});
  press('Show older receipts');
  expect(command()).toEqual({type:'more-purchase-receipts'});
  press('Post to Pantry');
  expect(command()).toEqual({type:'submit',command:postReceipt});
  await assign({...tracked,purchaseReceipts,result:{kind:'rejected',reason:'inventory_stock_capacity',command:postReceipt}});
  expect(root.querySelector('vyp-ha-feedback')?.state?.message).toContain('physical receipt is saved');
  node.language = 'es';
  const posted = {...purchaseReceipts,items:[{...purchaseReceipts.items[0],movementId:'movement'}],cursor:null};
  await assign({...shopping,purchaseReceipts:posted,result:{...committedPurchase,shoppingAction:arrive.action}});
  expect(shop.textContent).toContain('Contabilizado en Despensa.');
  expect(shop.textContent).toContain('4,000001 mililitros');
  expect(shop.textContent).toContain('movement');
  expect(root.textContent).toContain('Recepción física registrada.');
  const free = {...purchase, id:'free',productId:null,unit:'piece' as const,received:'2',remaining:'0',
    pendingStock:'0',authorAlias:null};
  await assign({...shopping,scope:{...scope,readOnly:true},purchaseReceipts:{purchase:free,items:purchaseReceipts.items,cancellation:null,cursor:null}});
  expect(shop.querySelector('form')).toBeNull();
  expect(shop.textContent).toContain('Artículo sin seguimiento recibido.');
});

test('the policy form validates exact drafts, preserves its revision and limits editing to managers', async () => {
  const {node,root,events,press,submit} = component();
  const product = report.products[0];
  const stock = {...report,products:[{...product,unit:'piece' as const}]};
  node.view = {...initial,report:{...stock,mayManage:false}};
  await node.updateComplete;
  expect(root.textContent).toContain('Replenishment is off.');
  expect([...root.querySelectorAll('vyp-ha-button')].map(button => button.state.label)).not.toContain('Edit replenishment');
  node.view = {...initial,report:stock};
  await node.updateComplete;
  press('Edit replenishment'); await node.updateComplete;
  let form = root.querySelector<HTMLFormElement>('.replenishment-form')!;
  expect(form.querySelector('input')?.inputMode).toBe('numeric');
  expect(root.activeElement).toBe(form.querySelector('input'));
  press('Cancel'); await node.updateComplete;
  expect(root.querySelector('.replenishment-form')).toBeNull();
  node.language = 'es';
  const enabled = {...product.replenishment,minimum:'1.25',target:'2',revision:'1' as typeof product.replenishment.revision,needed:'0.75'};
  const next = {...report,products:[{...product,replenishment:enabled}]};
  node.view = {...initial,report:next};
  await node.updateComplete;
  expect(root.textContent).toContain('Reponer · 0,75 mililitros');
  press('Editar reposición'); await node.updateComplete;
  form = root.querySelector<HTMLFormElement>('.replenishment-form')!;
  const [minimum,target] = form.querySelectorAll('input');
  const set = async (field: HTMLInputElement, value:string) => {
    field.value=value; field.dispatchEvent(new Event('input')); await node.updateComplete;
  };
  expect(minimum.value).toBe('1,25');
  expect(minimum.inputMode).toBe('decimal');
  await set(minimum,'');
  submit(form); await node.updateComplete;
  expect(form.querySelector('[role=alert]')?.textContent).toContain('Introduce una cantidad');
  await set(minimum,'3');
  submit(form); await node.updateComplete;
  expect(form.querySelector('[role=alert]')?.textContent).toContain('igual o superior al mínimo');
  await set(minimum,'0');
  await set(target,'4,25');
  node.view = {...node.view,busy:true};
  await node.updateComplete;
  submit(form);
  expect(events).not.toHaveBeenCalled();
  node.view = {...node.view,busy:false};
  await node.updateComplete;
  submit(form);
  const command = {action:policy.action,product_id:'product',minimum:'0',target:'4.25',expected_revision:enabled.revision} as const;
  expect(events.mock.lastCall?.[0].detail).toEqual({type:'submit',command});
  node.view = {...initial,report:next,result:{kind:'rejected',reason:'revision_conflict',command}};
  await node.updateComplete;
  expect(root.querySelector('.replenishment-form')).toBeNull();
  expect(root.querySelector('vyp-ha-feedback')?.state?.message).toContain('ha cambiado');
  press('Editar reposición'); await node.updateComplete;
  node.view = {...initial,report:{...next,products:[{...product,replenishment:{...enabled,needed:'0'}}]},
    result:{kind:'committed',operationId:'policy',productId:'product',movement:null,replenishmentSaved:true}};
  await node.updateComplete;
  expect(root.querySelector('.replenishment-form')).toBeNull();
  expect(root.textContent).toContain('Se ha guardado la configuración de reposición.');
  expect(root.textContent).toContain('No hace falta reponer.');
});

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
  expect(root.activeElement).toBe(form().querySelector('input'));
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

const addExtra = {action:'shopping.add-extra', product_id:'product', name:null, quantity:'2.000002'} as const;
const clearExtra = {action:'shopping.clear-extra', extra_id:'extra'} as const;
const extraAuthor = {member_id:'member', author_alias:'Shopper', created_at:'100'};
const wireShoppingItem = {product_id:'product',extra_id:null,name:'Olive oil',base_unit:'millilitre',
  pantry:'4',tasks:'0',manual:'2.000002',total:'6.000002',attribution:null};
const wireFreeExtra = {product_id:null,extra_id:'free',name:'Olive oil',base_unit:'piece',
  pantry:'0',tasks:'0',manual:'1',total:'1',attribution:extraAuthor};
const wireTaskSource = {source_id:'task-source',kind:'task',origin_id:'occurrence',line_id:'line',name:'Make dinner',
  quantity:'1.25',reserved:'0.25',stock:'0.5',incoming:'0.5',to_buy:'0',attribution:null};
const wireExtraSource = {source_id:'extra-source',kind:'extra',origin_id:'extra',line_id:null,name:'Olive oil',
  quantity:'2.000002',reserved:'0',stock:'0',incoming:'0',to_buy:'2.000002',attribution:{...extraAuthor,author_alias:null}};
const wireList = {items:[wireShoppingItem,wireFreeExtra],next_cursor:'list-more'};
const wireSources = {item:wireShoppingItem,sources:[wireTaskSource,wireExtraSource],next_cursor:'sources-more'};

async function shoppingPages() {
  const {server} = http([[200,wireList],[200,wireSources]]);
  return {shoppingList:await server.shoppingList(scope,null).result,
    shoppingSources:await server.shoppingSources(scope,'product',null).result};
}

test('shared Shopping decodes bounded pages, exact quantities, linked sources and original extra operations', async () => {
  const {server,fetch} = http([
    [200,wireList],[200,wireSources],[200,csrf],[200,receipt({extra_id:'extra'})],
    [200,receipt({extra_id:'extra'},'historical')],[200,csrf],[200,receipt({extra_id:'wrong'})],
  ],'native');
  expect(await server.shoppingList(scope,'previous').result).toMatchObject({cursor:'list-more',
    items:[{productId:'product',total:'6.000002'},{extraId:'free',attribution:{authorAlias:'Shopper'}}]});
  expect(await server.shoppingSources(scope,'product',null).result).toMatchObject({cursor:'sources-more',
    items:[{kind:'task',lineId:'line',toBuy:'0'},{kind:'extra',originId:'extra',toBuy:'2.000002'}]});
  expect(fetch.mock.calls[0][0]).toMatch(/inventory\/shopping-list\?limit=25&cursor=previous$/u);
  expect(fetch.mock.calls[1][0]).toMatch(/inventory\/shopping-list\/product\/sources\?limit=25$/u);
  expect(await server.send(scope,{...request,command:addExtra}).result).toMatchObject({shoppingAction:addExtra.action});
  expect(await server.original(scope,{...request,command:clearExtra}).result).toMatchObject({kind:'historical',shoppingAction:clearExtra.action});
  await expect(server.send(scope,{...request,command:clearExtra}).result).rejects.toThrow();
  expect(() => inventoryCommand({...clearExtra,forged:true})).toThrow();
  expect(() => inventoryCommand({...addExtra,product_id:null})).toThrow();
  const huge = {...wireShoppingItem,pantry:'0',manual:'999999999999999.999999',total:'999999999999999.999999'};
  expect(await http([[200,{...wireList,items:[huge]}]]).server.shoppingList(scope,null).result)
    .toMatchObject({items:[{total:'999999999999999.999999'}]});

  for (const value of [
    {...wireList,items:{}}, {...wireList,items:Array(26).fill(wireShoppingItem)},
    {...wireList,items:[wireShoppingItem,wireShoppingItem]},
    ...[
      {...wireShoppingItem,total:'6'}, {...wireShoppingItem,total:'06.000002'},
      {...wireShoppingItem,extra_id:'also-extra'}, {...wireShoppingItem,attribution:extraAuthor},
      {...wireFreeExtra,extra_id:null}, {...wireFreeExtra,attribution:null},
      {...wireFreeExtra,base_unit:'gram'}, {...wireFreeExtra,pantry:'1',total:'2'},
      {...wireFreeExtra,tasks:'1',total:'2'}, {...wireFreeExtra,manual:'0',total:'0'},
      {...wireFreeExtra,manual:'0.5',total:'0.5'},
    ].map(item => ({...wireList,items:[item]})),
  ]) await expect(http([[200,value]]).server.shoppingList(scope,null).result).rejects.toThrow();
  for (const value of [
    {...wireSources,item:wireFreeExtra}, {...wireSources,sources:{}},
    {...wireSources,sources:Array(26).fill(wireTaskSource)}, {...wireSources,sources:[wireTaskSource,wireTaskSource]},
    ...[{...wireTaskSource,reserved:'0'}, {...wireTaskSource,line_id:null},
      {...wireExtraSource,attribution:null}].map(source => ({...wireSources,sources:[source]})),
  ]) await expect(http([[200,value]]).server.shoppingSources(scope,'product',null).result).rejects.toThrow();
});

test('shared Shopping loads pages only in scope and recovers requests with their current grants', async () => {
  const pages = await shoppingPages();
  const local = journal(), publish = vi.fn<(state:InventoryState|null) => void>();
  const load = vi.fn(():EntryRead<InventoryReport> => read(report));
  const list = vi.fn((_scope:InventoryScope,_cursor:string|null) => read(pages.shoppingList));
  const sources = vi.fn((_scope:InventoryScope,_id:string,_cursor:string|null) => read(pages.shoppingSources));
  const send = vi.fn((_scope:InventoryScope,_request:InventoryRequest):EntryRead<InventoryResult> => lost());
  const original = vi.fn((_scope:InventoryScope,_request:InventoryRequest):EntryRead<InventoryResult|null> => read(null));
  const app = new InventoryController({read:load,history:() => lost(),purchases:() => lost(),
    purchaseReceipts:() => lost(),purchaseSessions:() => lost(),purchaseSession:() => lost(),
    shoppingList:list,shoppingSources:sources,send,original},
    local.journal,{requestKey:() => 'extra-operation'},publish);
  const state = () => publish.mock.lastCall?.[0];
  await app.showShoppingList(); await app.showShoppingSources('product'); await app.moreShoppingSources();
  app.bind(scope);
  await app.showShoppingList();
  await vi.waitFor(() => expect(state()?.busy).toBe(false));
  await app.showShoppingSources('product'); await app.showShoppingList(true);
  expect(list).not.toHaveBeenCalled(); expect(sources).not.toHaveBeenCalled();
  await app.showShoppingList();
  list.mockReturnValueOnce(read({items:[],cursor:null}));
  await app.showShoppingList(true); await app.showShoppingList(true);
  expect(list).toHaveBeenLastCalledWith(scope,'list-more');
  expect(state()?.shoppingList?.items).toEqual(pages.shoppingList.items);
  const first = app.showShoppingSources('product');
  await app.showShoppingSources('product');
  await first;
  sources.mockReturnValueOnce(read({...pages.shoppingSources,items:[],cursor:null}));
  await app.moreShoppingSources(); await app.moreShoppingSources();
  expect(sources).toHaveBeenLastCalledWith(scope,'product','sources-more');
  expect(state()?.shoppingSources?.items).toEqual(pages.shoppingSources.items);

  load.mockReturnValueOnce(read({...report,mayRequest:false,mayShop:false}));
  await app.refresh();
  await app.submit(addExtra); await app.submit(clearExtra);
  expect(send).not.toHaveBeenCalled();
  await app.refresh();
  await app.submit(addExtra);
  expect(state()).toMatchObject({pending:true,notice:'uncertain'});
  await app.showShoppingList();
  await app.showShoppingSources('product');
  expect(local.journal.open(scope.key)?.command).toEqual(addExtra);
  await app.recover();
  expect(send).toHaveBeenCalledTimes(2);
  const added = {kind:'committed',operationId:'extra-operation',productId:null,
    movement:null,shoppingAction:addExtra.action} as const;
  original.mockReturnValueOnce(read(added));
  await app.recover();
  expect(state()).toMatchObject({result:added,pending:false});
  send.mockReturnValueOnce(read({...added,shoppingAction:clearExtra.action}));
  await app.submit(clearExtra);
  expect(send.mock.lastCall?.[1].command).toEqual(clearExtra);
  sources.mockReturnValueOnce(lost());
  await app.showShoppingSources('product');
  expect(state()?.shoppingSources).toBeNull();
  list.mockReturnValueOnce(lost());
  await app.showShoppingList();
  expect(state()?.shoppingList).toBeNull();
  list.mockReturnValueOnce(lost());
  const interrupted = app.showShoppingList();
  app.bind(null);
  await interrupted;
  expect(state()).toBeNull();
});

test('shared Shopping renders bilingual per-source totals and controls for authorized users', async () => {
  const pages = await shoppingPages();
  const {node,root,events,submit} = component();
  const open = {...initial,report};
  node.view = open;
  await node.updateComplete;
  const shopping = root.querySelector('domus-shopping')!;
  await shopping.updateComplete;
  const list = shopping.shadowRoot!.querySelector('domus-shopping-list')!;
  await list.updateComplete;
  const panel = list.shadowRoot!;
  const buttons = (label:string) => [...panel.querySelectorAll('vyp-ha-button')].filter(button => button.state.label === label);
  const press = (label:string, index=0) => buttons(label)[index]!.dispatchEvent(new Event('ha-press-request'));
  const command = () => events.mock.lastCall?.[0].detail;
  const assign = async (state:InventoryState) => {
    node.view=state; await node.updateComplete; await shopping.updateComplete; await list.updateComplete;
  };
  press('Show shared shopping list');
  expect(command()).toEqual({type:'shopping-list'});
  await assign({...open,shoppingList:{items:[],cursor:null},shoppingSources:{...pages.shoppingSources,items:[],cursor:null},
    report:{...report,mayRequest:false,mayShop:false}});
  expect(panel.textContent).toContain('There are no shopping needs');
  expect(panel.textContent).toContain('There are no current sources');
  expect(panel.querySelector('form')).toBeNull();
  const current = {...open,...pages};
  await assign(current);
  expect(panel.textContent).toContain('6.000002 millilitres');
  expect(panel.textContent).toContain('Tasks · Make dinner');
  expect(panel.textContent).toContain('member ·');
  expect(panel.textContent).toContain('Shopper ·');
  press('Show shopping sources');
  expect(command()).toEqual({type:'shopping-sources',productId:'product'});
  press('Show more shopping items');
  expect(command()).toEqual({type:'more-shopping-list'});
  press('Show more sources');
  expect(command()).toEqual({type:'more-shopping-sources'});
  press('Clear manual extra');
  expect(command()).toEqual({type:'submit',command:{...clearExtra,extra_id:'free'}});
  press('Clear manual extra',1);
  expect(command()).toEqual({type:'submit',command:clearExtra});
  const form = panel.querySelector('form')!;
  const name = form.querySelector<HTMLInputElement>('input[name="name"]')!;
  const quantity = form.querySelector<HTMLInputElement>('input[name="quantity"]')!;
  const selector = form.querySelector('select')!;
  quantity.value='0.5'; submit(form); await list.updateComplete;
  expect(quantity.getAttribute('aria-invalid')).toBe('true');
  quantity.value='1'; submit(form); await list.updateComplete;
  expect(name.getAttribute('aria-invalid')).toBe('true');
  name.value='Olive oil'; submit(form); await list.updateComplete;
  expect(command()).toEqual({type:'submit',command:{...addExtra,product_id:null,name:'Olive oil',quantity:'1'}});
  selector.value='product'; selector.dispatchEvent(new Event('change')); await list.updateComplete;
  quantity.value='2.000002'; submit(form); await list.updateComplete;
  expect(command()).toEqual({type:'submit',command:addExtra});
  await assign({...current,pending:true});
  events.mockClear(); submit(form);
  expect(events).not.toHaveBeenCalled();
  await assign({...current,result:{kind:'committed',operationId:'op',productId:null,movement:null,shoppingAction:addExtra.action}});
  await list.updateComplete;
  expect(selector.value).toBe('');
  expect(quantity.value).toBe('');
  expect(root.textContent).toContain('Manual extra added.');
  await assign({...current,result:{kind:'committed',operationId:'op-clear',productId:null,movement:null,shoppingAction:clearExtra.action}});
  expect(root.textContent).toContain('Manual extra cleared.');
  node.language='es';
  await assign({...current,scope:{...scope,readOnly:true}});
  expect(panel.textContent).toContain('6,000002 mililitros');
  expect(panel.textContent).toContain('Tareas · Make dinner');
  expect(panel.querySelector('form')).toBeNull();
  expect(buttons('Retirar extra manual')).toHaveLength(0);
});

const sessionItem = {product_id:'product',extra_id:null,quantity:'2.000001'} as const;
const sessionExtra = {product_id:null,extra_id:'free',quantity:'1'} as const;
const recordSession = {action:'shopping.record-session',items:[sessionItem,sessionExtra]} as const;
const wireSession = {session_id:'session',member_id:'member',author_alias:'Shopper',created_at:'100'};
const sessionPage = {sessions:[wireSession],next_cursor:'older-sessions'};
const freePurchase = {...wirePurchase,purchase_id:'other-purchase',product_id:null,base_unit:'piece',
  name:'Lemons',purchased:'1',received:'1',remaining:'0',pending_stock:'0'};
const wireSessionDetail = {session:wireSession,items:[wirePurchase,freePurchase]};
const sessionReceipt = {session_id:'session',purchase_ids:['purchase','other-purchase']};
const sessionSaved = {kind:'committed',operationId:'operation',productId:null,movement:null,
  shoppingAction:recordSession.action,sessionId:'session'} as const;

test('purchase sessions admit distinct bounded selections and validate attributed history and original receipts', async () => {
  expect(inventoryCommand(recordSession)).toEqual(recordSession);
  for (const bad of [
    {...recordSession,wrong:true}, {...recordSession,items:{}}, {...recordSession,items:[sessionItem]},
    {...recordSession,items:Array(17).fill(sessionItem)}, {...recordSession,items:[sessionItem,sessionItem]},
    ...[null,[],1,{...sessionExtra,name:'forged'}, {...sessionExtra,product_id:'both'},
      {...sessionExtra,extra_id:null}, {...sessionExtra,quantity:'0'}]
      .map(item => ({...recordSession,items:[sessionItem,item]})),
  ]) expect(() => inventoryCommand(bad)).toThrow();

  const {server,fetch} = http([[200,sessionPage],[200,wireSessionDetail],[200,csrf],
    [200,receipt(sessionReceipt)],[200,receipt(sessionReceipt,'historical')]],'native');
  expect(await server.purchaseSessions(scope,'previous').result).toMatchObject({
    items:[{id:'session',authorAlias:'Shopper',createdAt:'100'}],cursor:'older-sessions',
  });
  expect(await server.purchaseSession(scope,'session').result).toMatchObject({
    session:{id:'session'},items:[{id:'purchase',pendingStock:'4.000001'},{id:'other-purchase',pendingStock:'0'}],
  });
  expect(fetch.mock.calls[0][0]).toMatch(/inventory\/purchase-sessions\?limit=25&cursor=previous$/u);
  expect(fetch.mock.calls[1][0]).toMatch(/inventory\/purchase-sessions\/session$/u);
  expect(await server.send(scope,{...request,command:recordSession}).result).toEqual(sessionSaved);
  expect(await server.original(scope,{...request,command:recordSession}).result).toEqual({...sessionSaved,kind:'historical'});

  for (const invalid of [null,Array(26).fill(wireSession),[wireSession,wireSession]]) {
    const response = {...sessionPage,sessions:invalid};
    await expect(http([[200,response]]).server.purchaseSessions(scope,null).result).rejects.toThrow();
  }
  for (const invalid of [
    {...wireSessionDetail,session:{...wireSession,session_id:'different'}},
    ...[{},[wirePurchase],Array(17).fill(wirePurchase),[wirePurchase,wirePurchase],
      [wirePurchase,{...freePurchase,created_at:'101'}],[wirePurchase,{...freePurchase,member_id:'foreign'}]]
      .map(items => ({...wireSessionDetail,items})),
  ]) await expect(http([[200,invalid]]).server.purchaseSession(scope,'session').result).rejects.toThrow();

  for (const purchase_ids of [null,['purchase'],['purchase','purchase'],['purchase','../foreign']]) {
    const {server} = http([[200,csrf],[200,receipt({...sessionReceipt,purchase_ids})]]);
    await expect(server.send(scope,{...request,command:recordSession}).result).rejects.toThrow();
  }
});

test('session history stays in scope and opens independent per-item receipts after an original recovery', async () => {
  const adapter = http([[200,sessionPage],[200,wireSessionDetail]]).server;
  const history = await adapter.purchaseSessions(scope,null).result;
  const detail = await adapter.purchaseSession(scope,'session').result;
  const local = journal(), publish = vi.fn<(state:InventoryState|null) => void>();
  const load = vi.fn(():EntryRead<InventoryReport> => read(report));
  const sessions = vi.fn((_scope:InventoryScope,_cursor:string|null):EntryRead<PurchaseSessions> => read(history));
  const session = vi.fn((_scope:InventoryScope,_id:string):EntryRead<PurchaseSessionDetail> => read(detail));
  const arrivals = vi.fn((_scope:InventoryScope,_id:string,_cursor:string|null) => read(purchaseReceipts));
  const send = vi.fn((_scope:InventoryScope,_request:InventoryRequest):EntryRead<InventoryResult> => lost());
  const original = vi.fn((_scope:InventoryScope,_request:InventoryRequest) => read(sessionSaved));
  const app = new InventoryController({read:load,history:() => lost(),purchases:() => lost(),
    purchaseReceipts:arrivals,purchaseSessions:sessions,purchaseSession:session,shoppingList:() => lost(),
    shoppingSources:() => lost(),send,original},local.journal,{requestKey:() => 'session-operation'},publish);
  const state = () => publish.mock.lastCall?.[0];
  await app.showPurchaseSessions(); await app.showPurchaseSession('session');
  app.bind(scope);
  await Promise.all([app.showPurchaseSessions(),app.showPurchaseSession('session')]);
  await vi.waitFor(() => expect(state()?.busy).toBe(false));
  await app.showPurchaseSessions(true);
  expect(sessions).not.toHaveBeenCalled(); expect(session).not.toHaveBeenCalled();
  await app.showPurchaseSessions();
  sessions.mockReturnValueOnce(read({items:[],cursor:null}));
  await app.showPurchaseSessions(true); await app.showPurchaseSessions(true);
  expect(sessions).toHaveBeenLastCalledWith(scope,'older-sessions');
  expect(state()?.purchaseSessions?.items).toEqual(history.items);
  await app.showPurchaseSession('session');
  await app.showPurchaseReceipts('purchase');
  expect(arrivals).toHaveBeenLastCalledWith(scope,'purchase',null);

  load.mockReturnValueOnce(read({...report,mayShop:false}));
  await app.refresh(); await app.submit(recordSession);
  expect(send).not.toHaveBeenCalled();
  await app.refresh(); await app.submit(recordSession);
  expect(local.journal.open(scope.key)?.command).toEqual(recordSession);
  await app.showPurchaseSessions(); await app.showPurchaseSession('session');
  await app.recover();
  expect(state()).toMatchObject({result:sessionSaved,pending:false});

  sessions.mockReturnValueOnce(lost());
  await app.showPurchaseSessions();
  expect(state()?.purchaseSessions).toBeNull();
  session.mockReturnValueOnce(lost());
  await app.showPurchaseSession('session');
  expect(state()?.purchaseSession).toBeNull();
  sessions.mockReturnValueOnce(lost());
  const pendingList = app.showPurchaseSessions();
  app.bind(null);
  await pendingList;
  app.bind(scope);
  await vi.waitFor(() => expect(state()?.busy).toBe(false));
  session.mockReturnValueOnce(lost());
  const pendingDetail = app.showPurchaseSession('session');
  app.bind(null);
  await pendingDetail;
  expect(state()).toBeNull();
});

test('a manager reviews exact session quantities, retains a rejected draft and opens grouped receipts', async () => {
  const {shoppingList} = await shoppingPages();
  const wireHistory = {sessions:[wireSession,{...wireSession,session_id:'other',author_alias:null}],next_cursor:'older'};
  const adapter = http([[200,wireHistory],[200,wireSessionDetail]]).server;
  const history = await adapter.purchaseSessions(scope,null).result;
  const detail = await adapter.purchaseSession(scope,'session').result;
  const {node,root,events,submit} = component();
  const open = {...initial,report,shoppingList};
  node.view = open;
  await node.updateComplete;
  const shopping = root.querySelector('domus-shopping')!;
  await shopping.updateComplete;
  const list = shopping.shadowRoot!.querySelector('domus-shopping-list')!;
  await list.updateComplete;
  const panel = list.shadowRoot!, card = shopping.shadowRoot!;
  const button = (container:ShadowRoot,label:string,index=0) =>
    [...container.querySelectorAll('vyp-ha-button')].filter(element => element.state.label === label)[index]!;
  const press = (container:ShadowRoot,label:string,index=0) => button(container,label,index).dispatchEvent(new Event('ha-press-request'));
  const command = () => events.mock.lastCall?.[0].detail;
  const assign = async (state:InventoryState) => {
    node.view=state; await node.updateComplete; await shopping.updateComplete; await list.updateComplete;
  };
  press(card,'Show purchase sessions');
  expect(command()).toEqual({type:'purchase-sessions'});
  await assign({...open,purchaseSessions:{items:[],cursor:null}});
  expect(card.textContent).toContain('There are no purchase sessions recorded.');
  const draft = () => panel.querySelector<HTMLFormElement>('#purchase-session-form')!;
  const quantities = () => [...draft().querySelectorAll<HTMLInputElement>('input')];
  press(panel,'Add to purchase session');
  await list.updateComplete;
  expect(button(panel,'Record purchase session').disabled).toBe(true);
  events.mockClear(); submit(draft());
  expect(events).not.toHaveBeenCalled();
  press(panel,'Add to purchase session'); // A duplicate request can arrive before its disabled state is rendered.
  press(panel,'Add to purchase session',1);
  await list.updateComplete;
  expect(quantities().map(input => input.value)).toEqual(['6.000002','1']);
  const enter = (index:number,value:string) => {
    const input = quantities()[index];
    input.value=value;
    input.dispatchEvent(new Event('input'));
  };
  enter(1,'0.5'); await list.updateComplete;
  submit(draft()); await list.updateComplete;
  expect(quantities()[1].getAttribute('aria-invalid')).toBe('true');
  press(panel,'Remove from session',1);
  await list.updateComplete;
  expect(quantities()).toHaveLength(1);
  press(panel,'Add to purchase session',1);
  await list.updateComplete;
  enter(0,'2,000001'); await list.updateComplete;
  submit(draft()); await list.updateComplete;
  expect(command()).toEqual({type:'submit',command:recordSession});
  await assign({...open,pending:true});
  events.mockClear(); submit(draft());
  expect(events).not.toHaveBeenCalled();
  await assign({...open,result:{kind:'rejected',reason:'shopping_purchase_open',command:recordSession}});
  expect(quantities()[0].value).toBe('2,000001');
  await assign({...open,result:sessionSaved,purchaseSessions:history});
  await list.updateComplete;
  expect(panel.querySelector('#purchase-session-form')).toBeNull();
  expect(root.textContent).toContain('Purchase session recorded.');
  press(card,'Show recorded session');
  expect(command()).toEqual({type:'purchase-session',sessionId:'session'});
  press(card,'Show session items');
  expect(command()).toEqual({type:'purchase-session',sessionId:'session'});
  press(card,'Show older sessions');
  expect(command()).toEqual({type:'more-purchase-sessions'});
  await assign({...open,purchaseSessions:history,purchaseSession:detail,purchaseReceipts});
  expect(card.textContent).toContain('Shopper ·');
  expect(card.textContent).toContain('member ·');
  expect(card.textContent).toContain('4.000001 millilitres');
  press(card,'Show physical receipts');
  expect(command()).toEqual({type:'purchase-receipts',purchaseId:'purchase'});
  node.language='es';
  await assign({...open,purchaseSessions:history,purchaseSession:detail});
  expect(card.textContent).toContain('Artículos de la sesión');

  const lots = {items:Array.from({length:17},(_,index) => ({...shoppingList.items[0],productId:'p'+index})),cursor:null};
  await assign({...open,shoppingList:lots});
  for (let index=0;index<16;index++) press(panel,'Añadir a la sesión de compra',index);
  await list.updateComplete;
  expect(quantities()).toHaveLength(16);
  expect(button(panel,'Añadir a la sesión de compra',16).disabled).toBe(true);
  await assign({...open,scope:{...scope,readOnly:true}});
  expect(panel.querySelector('#purchase-session-form')).toBeNull();
});

const cancelBalance = {action:'shopping.cancel-balance',purchase_id:'purchase',
  reason:'Supplier cancelled the rest',expected_revision:arrive.expected_revision} as const;
const wireCancellation = {quantity:'2',reason:cancelBalance.reason,
  member_id:'shopper',author_alias:'Marta',created_at:'102'};
const cancelledReceipt = {purchase_id:'purchase',cancelled:'2',revision:'3'};

test('balance cancellation uses a revisioned command and validates its original receipt and history', async () => {
  expect(inventoryCommand(cancelBalance)).toEqual(cancelBalance);
  for (const malformed of [{...cancelBalance,quantity:'2'},{...cancelBalance,reason:'  '},
    {...cancelBalance,expected_revision:'0'}]) {
    expect(() => inventoryCommand(malformed)).toThrow();
  }
  const original = {...request,command:cancelBalance};
  const local = journal();
  local.journal.save(original);
  expect(local.journal.open(scope.key)).toEqual(original);
  const {server,fetch} = http([[200,csrf],[200,receipt(cancelledReceipt)],[200,receipt(cancelledReceipt,'historical')]]);
  expect(await server.send(scope,original).result).toMatchObject({kind:'committed',shoppingAction:cancelBalance.action});
  expect(await server.original(scope,original).result).toMatchObject({kind:'historical',shoppingAction:cancelBalance.action});
  expect(fetch.mock.calls[2][0]).toContain('inventory/requests/shopping.cancel-balance/original');
  for (const invalid of [{...cancelledReceipt,purchase_id:'other'},{...cancelledReceipt,cancelled:'0'},
    {...cancelledReceipt,revision:'4'}]) {
    await expect(http([[200,receipt(invalid)]]).server.original(scope,original).result)
      .rejects.toMatchObject({code:'invalid_response'});
  }
  const closed = {...wirePurchase,remaining:'0',cancelled:'2',revision:'3'};
  const detail = {purchase:closed,receipts:[wireArrival],cancellation:wireCancellation,next_cursor:null};
  expect(await http([[200,detail]]).server.purchaseReceipts(scope,'purchase',null).result).toMatchObject({
    purchase:{cancelled:'2',remaining:'0',pendingStock:'4.000001'},
    cancellation:{quantity:'2',reason:cancelBalance.reason,memberId:'shopper',authorAlias:'Marta'},
    items:[{id:'arrival'}],
  });
  for (const invalid of [{...detail,cancellation:null},
    {...detail,cancellation:{...wireCancellation,quantity:'1'}},
    {...detail,purchase:{...closed,purchased:'7.000001',remaining:'1'}}]) {
    await expect(http([[200,invalid]]).server.purchaseReceipts(scope,'purchase',null).result)
      .rejects.toMatchObject({code:'invalid_response'});
  }
});

test('only a shopper can cancel and the purchase and receipt views reload after commitment', async () => {
  const f = controller(), app = f.controller;
  f.load.mockReturnValueOnce(read({...report,mayShop:false}));
  app.bind(scope);
  await vi.waitFor(() => expect(f.current()?.busy).toBe(false));
  await app.submit(cancelBalance);
  expect(f.send).not.toHaveBeenCalled();
  f.load.mockReturnValue(read({...report,mayManage:false}));
  await app.refresh();
  await app.showPurchases();
  await app.showPurchaseReceipts('purchase');
  await app.submit(cancelBalance);
  expect(f.send.mock.lastCall?.[1].command).toEqual(cancelBalance);
  expect(f.buys).toHaveBeenCalledTimes(2);
  expect(f.arrivals).toHaveBeenCalledTimes(2);
});

test('purchase details confirm the exact remaining amount, require a reason, and show the attributed cancellation', async () => {
  const {node,root,events,submit} = component();
  const open = {...initial,report:{...report,mayManage:false},purchaseReceipts};
  node.view = open;
  await node.updateComplete;
  const element = root.querySelector('domus-shopping')!;
  const shop = element.shadowRoot!;
  const assign = async (state:InventoryState) => {
    node.view = state;
    await node.updateComplete;
    await element.updateComplete;
  };
  await assign(open);
  const form = shop.querySelector<HTMLFormElement>('#cancel-form')!;
  const disclosure = shop.querySelector<HTMLDetailsElement>('#cancel-confirmation')!;
  const reason = form.querySelector('input')!;
  disclosure.open = true;
  expect(form.textContent).toContain('2 millilitres');
  submit(form);
  await element.updateComplete;
  expect(form.querySelector('[role=alert]')?.textContent).toContain('Enter a reason');
  expect(events).not.toHaveBeenCalled();
  reason.value = cancelBalance.reason;
  await assign({...open,pending:true});
  submit(form);
  expect(events).not.toHaveBeenCalled();
  await assign(open);
  submit(form);
  expect(events.mock.lastCall?.[0].detail).toEqual({type:'submit',command:cancelBalance});
  expect(disclosure.open).toBe(true);
  await assign({...open,purchaseReceipts:{...purchaseReceipts,purchase:{...purchase,id:'other'}}});
  expect(disclosure.open).toBe(false);
  expect(reason.value).toBe('');
  await assign({...open,report:{...report,mayShop:false}});
  expect(shop.querySelector('#cancel-form')).toBeNull();
  node.language = 'es';
  const cancellation = {quantity:'2',reason:cancelBalance.reason,memberId:'shopper',authorAlias:'Marta',createdAt:'102'};
  const closed = {...purchaseReceipts,purchase:{...purchase,remaining:'0',cancelled:'2'},cancellation};
  await assign({...open,purchaseReceipts:closed,result:{kind:'committed',operationId:'cancel',
    productId:null,movement:null,shoppingAction:cancelBalance.action}});
  expect(shop.querySelector('#cancel-form')).toBeNull();
  expect(shop.textContent).toContain('Cancelado');
  expect(shop.textContent).toContain(cancelBalance.reason);
  expect(shop.textContent).toContain('Marta');
  expect(root.textContent).toContain('Saldo pendiente cancelado.');
  await assign({...open,purchaseReceipts:{...closed,cancellation:{...cancellation,authorAlias:null}}});
  expect(shop.textContent).toContain('shopper');
});

const voidReceipt = {action:'shopping.void-receipt', purchase_id:'purchase', receipt_id:'arrival',
  reason:'Only three units arrived', expected_revision:arrive.expected_revision} as const;
const wireVoid = {reason:voidReceipt.reason,member_id:'shopper',author_alias:'Marta',created_at:'102'};
const voidResult = {purchase_id:'purchase',receipt_id:'arrival',quantity:'4.000001',revision:'3'};

test('the void command and original response bind the exact receipt, amount and purchase revision', async () => {
  expect(inventoryCommand(voidReceipt)).toEqual(voidReceipt);
  for (const malformed of [{...voidReceipt,quantity:'4'},{...voidReceipt,reason:' '},
    {...voidReceipt,receipt_id:' '},{...voidReceipt,expected_revision:'0'}]) {
    expect(() => inventoryCommand(malformed)).toThrow();
  }
  const original = {...request,command:voidReceipt};
  const local = journal();
  local.journal.save(original);
  expect(local.journal.open(scope.key)).toEqual(original);
  const {server,fetch} = http([[200,csrf],[200,receipt(voidResult)],[200,receipt(voidResult,'historical')]]);
  expect(await server.send(scope,original).result).toMatchObject({kind:'committed',shoppingAction:voidReceipt.action});
  expect(await server.original(scope,original).result).toMatchObject({kind:'historical',shoppingAction:voidReceipt.action});
  expect(fetch.mock.calls[2][0]).toContain('inventory/requests/shopping.void-receipt/original');
  for (const invalid of [{...voidResult,purchase_id:'foreign'},{...voidResult,receipt_id:'foreign'},
    {...voidResult,quantity:'0'},{...voidResult,revision:'4'}]) {
    await expect(http([[200,receipt(invalid)]]).server.original(scope,original).result)
      .rejects.toMatchObject({code:'invalid_response'});
  }
  const corrected = {...wirePurchase,received:'0',remaining:'6.000001',pending_stock:'0',revision:'3'};
  const arrival = {...wireArrival,voided:wireVoid};
  const detail = {purchase:corrected,receipts:[arrival],cancellation:null,next_cursor:null};
  expect(await http([[200,detail]]).server.purchaseReceipts(scope,'purchase',null).result).toMatchObject({
    purchase:{received:'0',remaining:'6.000001',pendingStock:'0'},
    items:[{id:'arrival',quantity:'4.000001',movementId:null,voided:{reason:voidReceipt.reason,authorAlias:'Marta'}}],
  });
  for (const invalid of [{...detail,receipts:[{...arrival,movement_id:'posted'}]},
    {...detail,purchase:{...corrected,product_id:null,base_unit:'piece',purchased:'6',remaining:'6'}}]) {
    await expect(http([[200,invalid]]).server.purchaseReceipts(scope,'purchase',null).result)
      .rejects.toMatchObject({code:'invalid_response'});
  }
});

test('voiding uses current shopping authority and refreshes the original receipt list', async () => {
  const f = controller(), app = f.controller;
  f.load.mockReturnValueOnce(read({...report,mayShop:false}));
  app.bind(scope);
  await vi.waitFor(() => expect(f.current()?.busy).toBe(false));
  await app.submit(voidReceipt);
  expect(f.send).not.toHaveBeenCalled();
  f.load.mockReturnValue(read({...report,mayManage:false}));
  await app.refresh();
  await app.showPurchases();
  await app.showPurchaseReceipts('purchase');
  await app.submit(voidReceipt);
  expect(f.send.mock.lastCall?.[1].command).toEqual(voidReceipt);
  expect(f.arrivals).toHaveBeenCalledTimes(2);
});

test('only a pending tracked receipt can be voided with a reason, and its history remains visible', async () => {
  const {node,root,events,submit} = component();
  const open = {...initial,report,purchaseReceipts};
  node.view = open;
  await node.updateComplete;
  const element = root.querySelector('domus-shopping')!;
  const shop = element.shadowRoot!;
  const assign = async (state:InventoryState) => {
    node.view = state;
    await node.updateComplete;
    await element.updateComplete;
  };
  await assign(open);
  const form = shop.querySelector<HTMLFormElement>('.receipt-void-form')!;
  const reason = form.querySelector('input')!;
  expect(form.textContent).toContain('4.000001 millilitres');
  submit(form);
  await element.updateComplete;
  expect(form.querySelector('[role=alert]')?.textContent).toContain('Enter a reason');
  expect(events).not.toHaveBeenCalled();
  reason.value = voidReceipt.reason;
  await assign({...open,pending:true});
  submit(form);
  expect(events).not.toHaveBeenCalled();
  await assign(open);
  submit(form);
  expect(events.mock.lastCall?.[0].detail).toEqual({type:'submit',command:voidReceipt});
  await assign({...open,report:{...report,mayShop:false}});
  expect(shop.querySelector('.receipt-void-form')).toBeNull();
  const closed = {...purchaseReceipts,purchase:{...purchase,remaining:'0',cancelled:'2'}};
  await assign({...open,purchaseReceipts:closed});
  expect(shop.querySelector('.receipt-void-form')).toBeNull();
  expect([...shop.querySelectorAll('vyp-ha-button')].map(button => button.state.label)).toContain('Post to Pantry');

  node.language = 'es';
  const corrected = {reason:voidReceipt.reason,memberId:'shopper',authorAlias:'Marta',createdAt:'102'};
  const history = {...purchaseReceipts,purchase:{...purchase,received:'0',pendingStock:'0',remaining:'6.000001'},
    items:[{...purchaseReceipts.items[0],voided:corrected}]};
  await assign({...open,purchaseReceipts:history,result:{kind:'committed',operationId:'void',
    productId:null,movement:null,shoppingAction:voidReceipt.action}});
  expect(shop.querySelector('.receipt-void-form')).toBeNull();
  expect(shop.textContent).toContain('Anulada antes de contabilizar en Despensa.');
  expect(shop.textContent).toContain(voidReceipt.reason);
  expect(shop.textContent).toContain('Marta');
  expect([...shop.querySelectorAll('vyp-ha-button')].map(button => button.state.label)).not.toContain('Contabilizar en Despensa');
  expect(root.textContent).toContain('Recepción física anulada.');
  await assign({...open,purchaseReceipts:{...history,items:[{...history.items[0],voided:{...corrected,authorAlias:null}}]}});
  expect(shop.textContent).toContain('shopper');
});

const correctPosted = {...voidReceipt, action:'shopping.correct-posted-receipt', expected_revision:revisionValue('3')} as const;
const postedResult = {...voidResult, movement_id:'compensation', revision:'4'};
const wirePostedCorrection = {...wireVoid, movement_id:'compensation', legacy:false};

test('posted receipt history and original correction receipts preserve both movement identities', async () => {
  expect(inventoryCommand(correctPosted)).toEqual(correctPosted);
  const original = {...request,command:correctPosted};
  const local = journal();
  local.journal.save(original);
  expect(local.journal.open(scope.key)).toEqual(original);
  const {server,fetch} = http([[200,csrf],[200,receipt(postedResult)],[200,receipt(postedResult,'historical')]]);
  expect(await server.send(scope,original).result).toMatchObject({kind:'committed',shoppingAction:correctPosted.action});
  expect(await server.original(scope,original).result).toMatchObject({kind:'historical',shoppingAction:correctPosted.action});
  expect(fetch.mock.calls[2][0]).toContain('inventory/requests/shopping.correct-posted-receipt/original');
  await expect(http([[200,receipt({...postedResult,movement_id:'?'})]]).server.original(scope,original).result)
    .rejects.toMatchObject({code:'invalid_response'});
  const corrected = {...wirePurchase,received:'0',remaining:'6.000001',pending_stock:'0',revision:'4'};
  const arrival = {...wireArrival,movement_id:'original',correction:wirePostedCorrection};
  const detail = {purchase:corrected,receipts:[arrival],cancellation:null,next_cursor:null};
  expect(await http([[200,detail]]).server.purchaseReceipts(scope,'purchase',null).result).toMatchObject({
    items:[{id:'arrival',movementId:'original',
      correction:{movementId:'compensation',authorAlias:'Marta',legacy:false}}],
  });
  const legacy = {...detail,receipts:[{...arrival,correction:{...wirePostedCorrection,legacy:true}}]};
  expect((await http([[200,legacy]]).server.purchaseReceipts(scope,'purchase',null).result).items[0].correction?.legacy)
    .toBe(true);
  for (const invalid of [
    {...detail,receipts:[{...arrival,movement_id:null}]},
    {...detail,receipts:[{...arrival,movement_id:'compensation'}]},
    {...detail,purchase:{...corrected,product_id:null,base_unit:'piece',purchased:'6',remaining:'6'}},
  ]) await expect(http([[200,invalid]]).server.purchaseReceipts(scope,'purchase',null).result)
    .rejects.toMatchObject({code:'invalid_response'});
});

test('the posted correction requires both current grants and refreshes receipt history', async () => {
  const f = controller(), app = f.controller;
  app.bind(scope);
  await vi.waitFor(() => expect(f.current()?.busy).toBe(false));
  for (const grants of [{mayManage:false,mayShop:true},{mayManage:true,mayShop:false}]) {
    f.load.mockReturnValueOnce(read({...report,...grants}));
    await app.refresh();
    await app.submit(correctPosted);
    expect(f.send).not.toHaveBeenCalled();
  }
  await app.refresh();
  await app.showPurchases();
  await app.showPurchaseReceipts('purchase');
  await app.submit(correctPosted);
  expect(f.send.mock.lastCall?.[1].command).toEqual(correctPosted);
  expect(f.arrivals).toHaveBeenCalledTimes(2);
});

test('posted receipt correction uses the shared reason form and keeps both history links', async () => {
  const {node,root,events,submit} = component();
  const posted = {...purchaseReceipts,purchase:{...purchase,revision:correctPosted.expected_revision,pendingStock:'0'},
    items:[{...purchaseReceipts.items[0],movementId:'original'}]};
  const stockHistory = {...history,movements:[{...history.movements[0],shoppingReceipt:true}]};
  const open = {...initial,report,purchaseReceipts:posted,history:stockHistory};
  node.view = open;
  await node.updateComplete;
  const element = root.querySelector('domus-shopping')!;
  const shop = element.shadowRoot!;
  const assign = async (state:InventoryState) => {
    node.view = state;
    await node.updateComplete;
    await element.updateComplete;
  };
  expect(root.textContent).toContain('Review this receipt in Shopping.');
  expect([...root.querySelectorAll('vyp-ha-button')].map(button => button.state.label)).not.toContain('Reverse this intake');
  await assign({...open,report:{...report,mayManage:false}});
  expect(shop.querySelector('.posted-receipt-correction-form')).toBeNull();
  await assign({...open,report:{...report,mayShop:false}});
  expect(shop.querySelector('.posted-receipt-correction-form')).toBeNull();
  await assign(open);
  const form = shop.querySelector<HTMLFormElement>('.posted-receipt-correction-form')!;
  expect(form.textContent).toContain('Quantity to reverse');
  expect(form.textContent).toContain('4.000001 millilitres');
  form.querySelector('input')!.value = correctPosted.reason;
  submit(form);
  expect(events.mock.lastCall?.[0].detail).toEqual({type:'submit',command:correctPosted});
  const correction = {movementId:'compensation',reason:correctPosted.reason,memberId:'shopper',
    authorAlias:'Marta',createdAt:'102',legacy:false};
  const corrected = {...posted,items:[{...posted.items[0],correction}]};
  await assign({...open,purchaseReceipts:corrected,result:{kind:'committed',operationId:'correct',
    productId:null,movement:null,shoppingAction:correctPosted.action}});
  expect(shop.querySelector('.posted-receipt-correction-form')).toBeNull();
  expect(shop.textContent).toContain('Corrected after Pantry posting.');
  expect(shop.textContent).toContain(correctPosted.reason);
  expect(shop.textContent).toContain('Marta');
  expect(shop.textContent).toContain('original');
  expect(shop.textContent).toContain('compensation');
  expect(root.textContent).toContain('Posted receipt corrected.');
  await assign({...open,purchaseReceipts:{...corrected,items:[{...corrected.items[0],correction:{...correction,legacy:true}}]}});
  expect(shop.textContent).toContain('Pantry entry reversed separately.');
  expect(shop.querySelector('.posted-receipt-correction-form')).toBeNull();
});

const returnReceipt = {...correctPosted,action:'shopping.return-receipt'} as const;
const wireReturn = {movement_id:'returned',reason:'Returned to supplier',
  member_id:'shopper',author_alias:'Marta',created_at:'104'};

test('physical return commands and transport keep the closed purchase and linked movement', async () => {
  expect(inventoryCommand(returnReceipt)).toEqual(returnReceipt);
  for (const malformed of [{...returnReceipt,quantity:'1'},{...returnReceipt,reason:' '},
    {...returnReceipt,expected_revision:'0'}]) expect(() => inventoryCommand(malformed)).toThrow();
  const original = {...request,command:returnReceipt};
  const local = journal();
  local.journal.save(original);
  expect(local.journal.open(scope.key)).toEqual(original);
  const {server} = http([[200,csrf],[200,receipt(postedResult)],[200,receipt(postedResult,'historical')]]);
  expect(await server.send(scope,original).result).toMatchObject({shoppingAction:returnReceipt.action,kind:'committed'});
  expect(await server.original(scope,original).result).toMatchObject({shoppingAction:returnReceipt.action,kind:'historical'});
  const closed = {...wirePurchase,received:wirePurchase.purchased,remaining:'0',pending_stock:'0',revision:'4'};
  const arrival = {...wireArrival,movement_id:'original',returned:wireReturn};
  const detail = {purchase:closed,receipts:[arrival],cancellation:null,next_cursor:null};
  expect(await http([[200,detail]]).server.purchaseReceipts(scope,'purchase',null).result).toMatchObject({
    purchase:{remaining:'0',pendingStock:'0'},items:[{movementId:'original',
      returned:{movementId:'returned',reason:wireReturn.reason,authorAlias:'Marta'}}],
  });
  for (const invalid of [
    {...detail,receipts:[{...arrival,movement_id:null}]},
    {...detail,receipts:[{...arrival,correction:wirePostedCorrection}]},
    {...detail,receipts:[{...arrival,returned:{...wireReturn,movement_id:'original'}}]},
    {...detail,purchase:{...closed,product_id:null,base_unit:'piece',purchased:'6',received:'6'}},
  ]) await expect(http([[200,invalid]]).server.purchaseReceipts(scope,'purchase',null).result)
    .rejects.toMatchObject({code:'invalid_response'});
  const withdrawal = {...wireMovement,kind:'adjustment',quantity:'-1.250001',reason:wireReturn.reason,return_of:'original'};
  expect((await http([[200,{...wireHistory,movements:[withdrawal]}]]).server.history(scope,'product',null).result).movements[0])
    .toMatchObject({returnOf:'original',quantity:'-1.250001'});
});

test('a physical return needs both grants and reloads receipt history', async () => {
  const f = controller(), app = f.controller;
  app.bind(scope);
  await vi.waitFor(() => expect(f.current()?.busy).toBe(false));
  for (const grants of [{mayManage:false,mayShop:true},{mayManage:true,mayShop:false}]) {
    f.load.mockReturnValueOnce(read({...report,...grants}));
    await app.refresh();
    await app.submit(returnReceipt);
    expect(f.send).not.toHaveBeenCalled();
  }
  await app.refresh();
  await app.showPurchases();
  await app.showPurchaseReceipts('purchase');
  await app.submit(returnReceipt);
  expect(f.send.mock.lastCall?.[1].command).toEqual(returnReceipt);
  expect(f.arrivals).toHaveBeenCalledTimes(2);
});

test('only a valid posting on a settled purchase exposes the full physical return', async () => {
  const {node,root,events,submit} = component();
  const settled = {...purchase,received:purchase.purchased,remaining:'0',pendingStock:'0',revision:returnReceipt.expected_revision};
  const posted = {...purchaseReceipts,purchase:settled,items:[{...purchaseReceipts.items[0],movementId:'original'}]};
  const open = {...initial,report,purchaseReceipts:posted};
  node.view = open;
  await node.updateComplete;
  const element = root.querySelector('domus-shopping')!;
  const shop = element.shadowRoot!;
  const assign = async (state:InventoryState) => {
    node.view = state;
    await node.updateComplete;
    await element.updateComplete;
  };
  await assign({...open,report:{...report,mayManage:false}});
  expect(shop.querySelector('.receipt-return-form')).toBeNull();
  await assign({...open,purchaseReceipts:{...posted,purchase:{...settled,pendingStock:'1'}}});
  expect(shop.querySelector('.receipt-return-form')).toBeNull();
  await assign({...open,purchaseReceipts:{...posted,purchase:{...settled,remaining:'1'}}});
  expect(shop.querySelector('.receipt-return-form')).toBeNull();
  await assign(open);
  const form = shop.querySelector<HTMLFormElement>('.receipt-return-form')!;
  expect(form.textContent).toContain('Quantity to return');
  expect(form.textContent).toContain('4.000001 millilitres');
  submit(form);
  await element.updateComplete;
  expect(form.querySelector('[role=alert]')?.textContent).toContain('Enter a reason');
  form.querySelector('input')!.value = returnReceipt.reason;
  submit(form);
  expect(events.mock.lastCall?.[0].detail).toEqual({type:'submit',command:returnReceipt});
  node.language = 'es';
  const returned = {movementId:'returned',reason:wireReturn.reason,memberId:'shopper',authorAlias:null,createdAt:'104'};
  await assign({...open,purchaseReceipts:{...posted,items:[{...posted.items[0],returned}]},
    history:{...history,movements:[{...history.movements[0],kind:'adjustment',quantity:'-1.250001',
      reason:wireReturn.reason,returnOf:'original'}]},
    result:{kind:'committed',operationId:'return',productId:null,movement:null,shoppingAction:returnReceipt.action}});
  expect(shop.querySelector('.receipt-return-form')).toBeNull();
  expect(shop.querySelector('.posted-receipt-correction-form')).toBeNull();
  expect(shop.textContent).toContain('Devuelto desde Despensa.');
  expect(shop.textContent).toContain(wireReturn.reason);
  expect(shop.textContent).toContain('shopper');
  expect(root.textContent).toContain('Devolución física registrada.');
  expect(root.textContent).toContain('Devolución de compra');
  expect(root.textContent).toContain('original');
  await assign({...open,purchaseReceipts:{...posted,items:[{...posted.items[0],returned:{...returned,authorAlias:'Marta'}}]}});
  expect(shop.textContent).toContain('Marta');
});

const addLocation = {action:'inventory.add-location', name:'Cupboard'} as const;
const moveStock = {action:'inventory.transfer', product_id:'product', source_location:'pantry',
  destination_location:'cupboard', quantity:'1.25'} as const;
const namedLocation = {location_id:'cupboard', name:'Cupboard'};
const locationLink = {transfer_id:'transfer', product_id:'product', source_location:'pantry',
  destination_location:'cupboard', withdrawal_id:'withdrawal', deposit_id:'deposit'};
const emptyStock = {recorded:'0',reserved:'0',available:'0'};
const locationHistory = {...wireHistory, total:historyStock, locations:[
  {location_id:'pantry',name:null,stock:emptyStock}, {...namedLocation,stock:historyStock},
], movements:[
  {...wireMovement, movement_id:'deposit',kind:'transfer',quantity:'1.25',transfer:locationLink},
  {...wireMovement, movement_id:'withdrawal',kind:'transfer',quantity:'-1.25',transfer:locationLink},
]};

test('location and transfer commands validate closed payloads and recover exact outcomes', async () => {
  expect(inventoryCommand(addLocation)).toEqual(addLocation);
  expect(inventoryCommand(moveStock)).toEqual(moveStock);
  for (const invalid of [
    {...addLocation,name:' Pantry'}, {...addLocation,name:'despensa'}, {...addLocation,name:'x'.repeat(81)},
    {...addLocation,extra:true}, {...moveStock,extra:true}, {...moveStock,source_location:'cupboard'},
    {...moveStock,quantity:'0'}, {...moveStock,destination_location:'../invalid'},
  ]) expect(() => inventoryCommand(invalid)).toThrow();
  const savedTransfer = {...locationLink, base_unit:'millilitre', quantity:moveStock.quantity};
  const {server} = http([
    [200,{...wire,locations:[namedLocation]}], [200,locationHistory],
    [200,csrf], [200,receipt(namedLocation)], [200,receipt(namedLocation,'historical')],
    [200,csrf], [200,receipt(savedTransfer)], [200,receipt(savedTransfer,'historical')],
    [200,receipt({...namedLocation,name:'Drawer'})],
    [200,receipt({...savedTransfer,product_id:'other'})],
    [200,receipt({...savedTransfer,source_location:'other'})],
    [200,receipt({...savedTransfer,destination_location:'other'})],
    [200,receipt({...savedTransfer,quantity:'2'})],
  ]);
  const locationRequest = {...request,command:addLocation}, transferRequest = {...request,command:moveStock};
  expect((await server.read(scope,null).result).locations).toEqual([{id:'cupboard',name:'Cupboard'}]);
  const view = await server.history(scope,'product',null).result;
  expect(view.total).toEqual(historyStock);
  expect(view.movements.map(item => [item.id,item.transfer?.id])).toEqual([['deposit','transfer'],['withdrawal','transfer']]);
  expect(await server.send(scope,locationRequest).result).toMatchObject({kind:'committed',locationSaved:true});
  expect(await server.original(scope,locationRequest).result).toMatchObject({kind:'historical',locationSaved:true});
  expect(await server.send(scope,transferRequest).result).toMatchObject({kind:'committed',
    movement:{movementId:'withdrawal',quantity:'1.25',action:'inventory.transfer'}});
  expect(await server.original(scope,transferRequest).result).toMatchObject({kind:'historical'});
  await expect(server.original(scope,locationRequest).result).rejects.toMatchObject({code:'invalid_response'});
  for (let index = 0; index < 4; index++)
    await expect(server.original(scope,transferRequest).result).rejects.toMatchObject({code:'invalid_response'});
});

test('bounded location projections reject conflicting links, totals and identities', async () => {
  for (const locations of [null,[namedLocation,namedLocation],[{...namedLocation,location_id:'pantry'}],
    Array.from({length:33}, (_, index) => ({...namedLocation,location_id:'loc-' + index}))]) {
    const {server} = http([[200,{...wire,locations}]]);
    await expect(server.read(scope,null).result).rejects.toMatchObject({code:'invalid_response'});
  }
  const row = locationHistory.movements[0];
  const linked = (patch:Record<string,unknown>) => [{...row,transfer:{...locationLink,...patch}}];
  const wrongTotal = {recorded:'2',reserved:'0',available:'2'};
  for (const patch of [
    {locations:null}, {locations:[]}, {locations:Array(34).fill(locationHistory.locations[0])},
    {locations:[locationHistory.locations[0], locationHistory.locations[0]]},
    {locations:[locationHistory.locations[1]]},
    {locations:[{...locationHistory.locations[0], name:'Untrusted'}]},
    {locations:[{...locationHistory.locations[0], stock:{...emptyStock,available:'1'}}]},
    {total:{...emptyStock,recorded:'0000'}}, {total:{...emptyStock,recorded:1}},
    {total:wrongTotal}, {base_unit:'piece'},
    {movements:[{...row,transfer:null}]}, {movements:[{...row,kind:'intake'}]},
    {movements:[{...row,movement_id:'wrong'}]}, {movements:linked({deposit_id:'withdrawal'})},
    {movements:linked({source_location:'cupboard'})}, {movements:linked({source_location:'missing'})},
    {movements:linked({destination_location:'missing'})}, {movements:linked({product_id:'other'})},
  ]) {
    const {server} = http([[200,{...locationHistory,...patch}]]);
    await expect(server.history(scope,'product',null).result).rejects.toMatchObject({code:'invalid_response'});
  }
  const large = '999999999999.999999';
  const stock = {recorded:large,reserved:'0',available:large};
  const total = '1999999999999.999998';
  const {server} = http([[200,{...locationHistory, total:{recorded:total,reserved:'0',available:total},
    locations:locationHistory.locations.map(item => ({...item,stock}))}]]);
  expect((await server.history(scope,'product',null).result).total.recorded).toBe(total);
});

test('the shared location and transfer controls retain drafts through rejection and show linked balances', async () => {
  const {node,root,events,press,submit} = component();
  const reportWithLocation = {...report,locations:[{id:'cupboard',name:'Cupboard'}]};
  const stockHistory: MovementHistory = {...history,locations:[...history.locations,
    {id:'cupboard',name:'Cupboard',stock:emptyStock}]};
  const setValue = (control:Element, type:string, value:string|null) =>
    control.dispatchEvent(new CustomEvent(type,{detail:{value}}));
  node.view = {...initial,report:reportWithLocation};
  await node.updateComplete;
  const locationForm = root.querySelector<HTMLFormElement>('.location-content form')!;
  const name = locationForm.querySelector('vyp-ha-field')!;
  submit(locationForm);
  await node.updateComplete;
  expect(name.state.error).toContain('Enter a location name');
  setValue(name,'ha-value-request',' Cupboard ');
  await node.updateComplete;
  submit(locationForm);
  expect(events.mock.lastCall?.[0].detail).toEqual({type:'submit',command:addLocation});
  node.view = {...node.view,result:{kind:'rejected',reason:'inventory_location_exists',command:addLocation}};
  await node.updateComplete;
  expect(name.value).toBe(' Cupboard ');
  expect(root.querySelector('vyp-ha-feedback')?.state?.message).toContain('already has this name');
  node.view = {...node.view,result:{kind:'committed',operationId:'loc',productId:null,movement:null,locationSaved:true}};
  await node.updateComplete;
  expect(name.value).toBe('');
  expect(root.textContent).toContain('Storage location added.');
  node.view = {...node.view,report:{...reportWithLocation,mayManage:false},
    result:{kind:'historical',operationId:'previous-location',productId:null,movement:null,locationSaved:true}};
  await node.updateComplete;
  expect(root.querySelector('.location-content form')).toBeNull();
  node.view = {...node.view,report:reportWithLocation,result:null};
  await node.updateComplete;

  press('Move stock');
  expect(events.mock.lastCall?.[0].detail).toEqual({type:'history',productId:'product'});
  node.view = {...node.view,history:stockHistory,result:null};
  await node.updateComplete;
  const form = root.querySelector<HTMLFormElement>('.transfer-form')!;
  const [source,destination] = form.querySelectorAll('vyp-ha-select');
  const quantity = form.querySelector('vyp-ha-field')!;
  expect(root.activeElement?.className).toBe('history');
  expect(destination.state.options).toContainEqual({value:'pantry',label:'Pantry',disabled:true});
  submit(form);
  await node.updateComplete;
  expect(form.textContent).toContain('Choose a location');
  setValue(source,'ha-select-request',null);
  await node.updateComplete;
  expect(form.textContent).not.toContain('Available stock');
  setValue(source,'ha-select-request','pantry');
  await node.updateComplete;
  setValue(destination,'ha-select-request','cupboard');
  await node.updateComplete;
  submit(form);
  await node.updateComplete;
  expect(form.textContent).toContain('Enter a quantity');
  setValue(quantity,'ha-value-request','2');
  await node.updateComplete;
  submit(form);
  await node.updateComplete;
  expect(form.textContent).toContain('no greater than the available stock');
  setValue(source,'ha-select-request','cupboard');
  await node.updateComplete;
  expect(destination.value).toBeNull();
  setValue(source,'ha-select-request','pantry');
  await node.updateComplete;
  setValue(destination,'ha-select-request','cupboard');
  await node.updateComplete;
  setValue(quantity,'ha-value-request','1,25');
  await node.updateComplete;
  submit(form);
  await node.updateComplete;
  expect(form.textContent).toMatch(/1\.25\s+millilitres/u);
  expect(form.textContent).toMatch(/Pantry\s+→\s+Cupboard/u);
  submit(form);
  expect(events.mock.lastCall?.[0].detail).toEqual({type:'submit',command:moveStock});
  node.view = {...node.view,busy:true};
  await node.updateComplete;
  const submissions = events.mock.calls.length;
  submit(form); submit(root.querySelector<HTMLFormElement>('.location-content form')!);
  expect(events.mock.calls).toHaveLength(submissions);
  node.view = {...node.view,busy:false,result:{kind:'rejected',reason:'inventory_insufficient_stock',command:moveStock}};
  await node.updateComplete;
  expect(quantity.value).toBe('1,25');
  press('Move stock');
  await node.updateComplete;
  expect(quantity.value).toBe('1,25');
  const cupboardStock = {recorded:'2',reserved:'0',available:'2'};
  node.view = {...node.view,history:{...stockHistory,unit:'piece',
    locations:[{id:'pantry',name:null,stock:emptyStock},{id:'cupboard',name:'Cupboard',stock:cupboardStock}]}};
  await node.updateComplete;
  expect(quantity.state.description).toContain('whole number');
  setValue(source,'ha-select-request','cupboard');
  await node.updateComplete;
  setValue(destination,'ha-select-request','pantry');
  await node.updateComplete;
  setValue(quantity,'ha-value-request','1');
  await node.updateComplete;
  submit(form);
  await node.updateComplete;
  expect(form.textContent).toMatch(/1\s+piece/u);
  expect(form.textContent).toMatch(/Cupboard\s+→\s+Pantry/u);
  press('Cancel');
  await node.updateComplete;
  expect(root.querySelector('.transfer-form')).toBeNull();
  const historyButton = [...root.querySelectorAll<HTMLElementTagNameMap['vyp-ha-button']>('.history vyp-ha-button')]
    .find(control => control.state.label === 'Move stock')!;
  historyButton.dispatchEvent(new Event('ha-press-request'));
  await node.updateComplete;
  expect(root.querySelector('.transfer-form')).not.toBeNull();
  const linked = {id:'transfer',productId:'product',source:'pantry',destination:'cupboard',
    withdrawalId:'withdrawal',depositId:'deposit'};
  const movement = history.movements[0];
  node.language = 'es';
  node.view = {...node.view,history:{...stockHistory,movements:[
    {...movement,id:'withdrawal',kind:'transfer',quantity:'-1',transfer:linked},
    {...movement,id:'deposit',kind:'transfer',quantity:'1',transfer:linked},
  ]},result:{kind:'committed',operationId:'move',productId:'product',
    movement:{movementId:'withdrawal',quantity:'1',unit:'millilitre',action:'inventory.transfer'}}};
  await node.updateComplete;
  expect(root.querySelector('.transfer-form')).toBeNull();
  expect(root.textContent).toMatch(/Se trasladó el stock.\s+1 mililitro/u);
  expect(root.textContent).toContain('+1 mililitro');
  expect(root.textContent).toContain('-1 mililitro');
  expect(root.textContent).toContain('Total del hogar');
  expect(root.textContent).toContain('Despensa → Cupboard');
  expect(root.textContent).toContain('Otro movimiento del traslado');
  press('Cerrar historial de movimientos');
  expect(events.mock.lastCall?.[0].detail).toEqual({type:'close-history'});
});
