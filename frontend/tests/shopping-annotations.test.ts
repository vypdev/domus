import {afterEach, expect, test, vi} from 'vitest';
import {inventoryCommand, shoppingNote, shoppingPriority, SHOPPING_PRIORITIES} from '../src/domain/inventory';
import {InventorySessionJournal, INVENTORY_JOURNAL_KEY} from '../src/adapters/inventory-journal';
import {InventoryController} from '../src/application/inventory-controller';
import {HttpInventoryServer} from '../src/adapters/inventory-http';
import type {EntryEndpoint} from '../src/adapters/http-values';
import {SHOPPING_PAGE_MAX_BYTES} from '../src/adapters/json-values';
import corpus from './fixtures/entry-wire.json';
import type {InventoryRequest, InventoryResult, InventoryScope, InventoryServer, InventoryState} from '../src/application/inventory-controller';
import type {InventoryReport} from '../src/domain/inventory';
import type {EntryRead} from '../src/application/ports';
import {InventorySessionJournal as PreviousJournal, InventoryController as PreviousController,
  INVENTORY_JOURNAL_KEY as PREVIOUS_KEY} from './fixtures/edge72-inventory-journal.mjs';
import '../src/presentation/domus-shopping-list';
import '../src/presentation/domus-inventory';

afterEach(() => document.body.replaceChildren());

const scope: InventoryScope = {key:'shopping-home', context:{installationId:'047cc6fb-dfb0-4fa4-b3c3-e0fe54d116b6',
  channel:'edge', subject:'a'.repeat(32)}, readOnly:false};
const legacy = {action:'shopping.add-extra', product_id:'product', name:null, quantity:'2'} as const;
const annotated = {...legacy, note:'Keep\r\n\t😀 <img src=x onerror=alert(1)>', priority:'high'} as const;
const report: InventoryReport = {mayManage:false, mayShop:false, mayRequest:true, products:[], locations:[], cursor:null};
const saved: InventoryResult = {kind:'committed', operationId:'operation', productId:null,
  shoppingAction:'shopping.add-extra', movement:null};
const read = <T>(value:T):EntryRead<T> => ({result:Promise.resolve(value), cancel:vi.fn()});
function storage() {
  const values = new Map<string,string>();
  return {values, getItem:(key:string) => values.get(key) ?? null,
    setItem:vi.fn((key:string,value:string) => {values.set(key,value);}),
    removeItem:vi.fn((key:string) => {values.delete(key);})};
}
function server(): InventoryServer {
  return {read:() => read(report), barcode:vi.fn(), history:vi.fn(), purchases:vi.fn(), purchaseReceipts:vi.fn(),
    purchaseSessions:vi.fn(), purchaseSession:vi.fn(), shoppingList:vi.fn(), shoppingSources:vi.fn(),
    send:vi.fn(() => read(saved)), original:vi.fn(() => read(null))};
}

test('manual annotation values preserve literal codepoints without changing legacy or purchase commands', () => {
  for (const value of ['', '  ', '\t\r\n', '~\u00a0 text', '😀'.repeat(1000), annotated.note]) expect(shoppingNote(value)).toBe(value);
  for (const value of SHOPPING_PRIORITIES) expect(shoppingPriority(value)).toBe(value);
  for (const value of [null, 0, {}, [], '😀'.repeat(1001), '\ud800', '\udfff', 'ok\u007f'])
    expect(() => shoppingNote(value)).toThrow('invalid_shopping_note');
  for (let code = 0; code < 32; code++) if (![9,10,13].includes(code))
    expect(() => shoppingNote('a'+String.fromCharCode(code))).toThrow('invalid_shopping_note');
  for (let code=0x80;code<=0x9f;code++) {
    const note='before'+String.fromCharCode(code)+'after';
    expect(()=>shoppingNote(note)).toThrow('invalid_shopping_note');
    expect(()=>inventoryCommand({...legacy,note})).toThrow('invalid_shopping_note');
  }
  for (const value of [undefined, null, 1, [], {}, '', 'HIGH', ' normal ', 'red'])
    expect(() => shoppingPriority(value)).toThrow('invalid_shopping_priority');
  expect(inventoryCommand(legacy)).toEqual(legacy);
  expect(JSON.stringify(inventoryCommand(legacy))).toBe(JSON.stringify(legacy));
  for (const extra of [{}, {note:''}, {priority:'normal'}, {note:annotated.note,priority:'urgent'}]) {
    const command = {...legacy,...extra};
    expect(inventoryCommand(command)).toEqual(command);
    expect(inventoryCommand({...command,product_id:null,name:'Untracked'})).toEqual({...command,product_id:null,name:'Untracked'});
  }
  for (const extra of [{note:undefined}, {priority:undefined}, {note:null}, {priority:'red'}, {note:'\u0000'},
    {annotation:{note:'text',priority:'high'}}, {other:'forged'}])
    expect(() => inventoryCommand({...legacy,...extra})).toThrow();
  expect(() => inventoryCommand({...annotated,action:'shopping.purchase'})).toThrow();
});

test('the genuine Edge72 journal and current journal retain exactly the same unannotated pending bytes', () => {
  const local = storage(), old = new PreviousJournal(local), current = new InventorySessionJournal(local);
  expect(PREVIOUS_KEY).toBe(INVENTORY_JOURNAL_KEY);
  const request: InventoryRequest = {key:'legacy-original', scope:scope.key, command:legacy};
  old.save(request);
  const raw = local.values.get(INVENTORY_JOURNAL_KEY);
  expect(raw).toBe(JSON.stringify(request));
  expect(current.open(scope.key)).toEqual(request);
  expect(local.values.get(INVENTORY_JOURNAL_KEY)).toBe(raw);
  current.clear(request);current.save(request);
  expect(local.values.get(INVENTORY_JOURNAL_KEY)).toBe(raw);
  expect(old.open(scope.key)).toEqual(request);
  old.clear(request);
  expect(local.values.size).toBe(0);
});

test.each(['committed','historical','missing'] as const)('cold re-upgrade recovers the same annotated operation after Edge72 blocks it (%s)', async outcome => {
  const local = storage(), current = new InventorySessionJournal(local);
  const request: InventoryRequest = {key:'annotated-original', scope:scope.key, command:annotated};
  current.save(request);
  const raw = local.values.get(INVENTORY_JOURNAL_KEY);
  const old = new PreviousJournal(local), previousServer = server(), oldPublish = vi.fn<(state:InventoryState|null) => void>();
  expect(() => old.open(scope.key)).toThrow();
  expect(() => old.save(request)).toThrow();
  expect(() => old.open('another-home')).toThrow();
  const previous = new PreviousController(previousServer,old,{requestKey:() => 'forbidden-new-key'},oldPublish);
  previous.bind(scope);
  await vi.waitFor(() => expect(oldPublish.mock.lastCall?.[0]).toMatchObject({report,pending:true,notice:'unavailable'}));
  await previous.submit(legacy);await previous.recover();
  expect(previousServer.send).not.toHaveBeenCalled();expect(previousServer.original).not.toHaveBeenCalled();
  expect(local.values.get(INVENTORY_JOURNAL_KEY)).toBe(raw);
  expect(local.removeItem).not.toHaveBeenCalled();
  previous.bind(null);
  const currentServer = server(), publish = vi.fn<(state:InventoryState|null) => void>();
  currentServer.original = vi.fn(() => read(outcome === 'missing' ? null : {...saved,kind:outcome}));
  const coldJournal = new InventorySessionJournal(local);
  expect(coldJournal.open(scope.key)).toEqual(request);
  const app = new InventoryController(currentServer,coldJournal,{requestKey:() => 'must-not-replace'},publish);
  app.bind(scope);
  await vi.waitFor(() => expect(publish.mock.lastCall?.[0]).toMatchObject({report,pending:true,busy:false}));
  await app.recover();
  expect(currentServer.original).toHaveBeenCalledExactlyOnceWith(scope,request);
  if (outcome === 'missing') expect(currentServer.send).toHaveBeenCalledExactlyOnceWith(scope,request);
  else expect(currentServer.send).not.toHaveBeenCalled();
  expect(publish.mock.lastCall?.[0]).toMatchObject({pending:false,result:{kind:outcome === 'historical' ? 'historical' : 'committed'}});
  expect(local.values.size).toBe(0);
  app.bind(null);
});

test('escaped maximum notes and scopes fit a bounded journal without accepting malformed or reordered packets', () => {
  const local = storage(), journal = new InventorySessionJournal(local);
  const request: InventoryRequest = {key:'k'.repeat(128), scope:'\u0000'.repeat(1024),
    command:{action:'shopping.add-extra', product_id:null, name:'"'.repeat(160), quantity:'999999999999',
      note:'"'.repeat(1000),priority:'urgent'}};
  expect(JSON.stringify(request).length).toBeGreaterThan(8192);
  expect(JSON.stringify(request).length).toBeLessThan(12288);
  journal.save(request);expect(journal.open(request.scope)).toEqual(request);
  const valid = local.values.get(INVENTORY_JOURNAL_KEY)!;
  const command = request.command as typeof annotated;
  for (const raw of ['x'.repeat(12289), JSON.stringify({...request,command:{...command,note:'😀'.repeat(1001)}}),
    JSON.stringify({...request,command:{...command,priority:'forged'}}),
    JSON.stringify({...request,command:{...command,other:'forged'}}),
    JSON.stringify({...request,command:{priority:command.priority,...legacy,note:command.note}})]) {
    local.values.set(INVENTORY_JOURNAL_KEY,raw);
    expect(() => journal.open(request.scope)).toThrow();
    expect(local.values.get(INVENTORY_JOURNAL_KEY)).toBe(raw);
  }
  local.values.set(INVENTORY_JOURNAL_KEY,valid);journal.clear(request);
});

const attribution = {member_id:'requester',author_alias:'Requester',created_at:'100'};
const product = {product_id:'product',extra_id:null,name:'Tea',base_unit:'piece',
  pantry:'0',tasks:'0',manual:'2',total:'2',attribution:null};
const extra = {product_id:null,extra_id:'free',name:'Tea',base_unit:'piece',
  pantry:'0',tasks:'0',manual:'1',total:'1',attribution};
const source = {source_id:'source-one',kind:'extra',origin_id:'extra-one',line_id:null,name:'Tea',
  quantity:'1',reserved:'0',stock:'0',incoming:'0',to_buy:'1',attribution};
const page = {items:[{item:product,annotation:null},{item:extra,annotation:{note:annotated.note,priority:'urgent'}}],next_cursor:null};
const sources = {item:product,sources:[{source,annotation:{note:'First request',priority:'high'}},
  {source:{...source,source_id:'source-two',origin_id:'extra-two'},annotation:{note:'Second\nrequest',priority:'low'}}],next_cursor:null};
function http(value:unknown,deployment:'native'|'standalone'='standalone',raw?:string,length?:number) {
  const endpoint = {...corpus[deployment].endpoint,deployment} as EntryEndpoint;
  const fetch = vi.fn(async (path:string,_init:RequestInit) => {
    const headers = new Headers({'Content-Type':'application/json','Cache-Control':'no-store'});
    if (length !== undefined) headers.set('Content-Length',String(length));
    const response = new Response(raw ?? JSON.stringify(value),{status:200,headers});
    Object.defineProperty(response,'url',{value:endpoint.origin+path});return response;
  });
  return {server:new HttpInventoryServer(endpoint,fetch),fetch};
}

test.each(['native','standalone'] as const)('annotated reads preserve independent request notes without synthesizing aggregate metadata (%s)', async deployment => {
  const list = http(page,deployment), detail = http(sources,deployment);
  expect((await list.server.shoppingList(scope,'next-page').result).items).toMatchObject([
    {productId:'product',annotation:null},
    {extraId:'free',annotation:{note:annotated.note,priority:'urgent'}}]);
  expect((await detail.server.shoppingSources(scope,'product',null).result).items).toMatchObject([
    {originId:'extra-one',annotation:{note:'First request',priority:'high'}},
    {originId:'extra-two',annotation:{note:'Second\nrequest',priority:'low'}}]);
  expect(list.fetch.mock.calls[0][0]).toContain('/inventory/shopping-list/annotated?limit=25&cursor=next-page');
  expect(detail.fetch.mock.calls[0][0]).toContain('/inventory/shopping-list/product/sources/annotated?limit=25');
});

test('strict annotation decoders reject unsupported or misplaced metadata before exposing a partial page', async () => {
  for (const items of [[extra], [{item:extra}], [{item:extra,annotation:null}],
    [{item:product,annotation:{note:'Wrong aggregate',priority:'high'}}],
    ...[{}, {note:'text'}, {note:'text',priority:'red'}, {note:'\ud800',priority:'high'},
      {note:'😀'.repeat(1001),priority:'normal'}, {note:'\u0000',priority:'normal'},
      {note:'text',priority:'normal',private:'forged'}].map(annotation => [{item:extra,annotation}])])
    await expect(http({...page,items}).server.shoppingList(scope,null).result).rejects.toMatchObject({code:'invalid_response'});
  for (const items of [[source], [{source,annotation:null}],
    [{source:{...source,kind:'pantry',attribution:null},annotation:{note:'Forged',priority:'high'}}],
    [{source,annotation:{note:'valid',priority:'invalid'}}]])
    await expect(http({...sources,sources:items}).server.shoppingSources(scope,'product',null).result)
      .rejects.toMatchObject({code:'invalid_response'});
  const nonmanual = {source:{...source,kind:'pantry',attribution:null},annotation:null};
  expect((await http({...sources,sources:[nonmanual]}).server.shoppingSources(scope,'product',null).result).items[0])
    .toMatchObject({kind:'pantry',annotation:null});
});

test('a full 25-note Unicode page fits its explicit bounded budget while unrelated reads retain the standard cap', async () => {
  const notes = Array.from({length:25},(_,i) => ({item:{...extra,extra_id:'free-'+i},
    annotation:{note:'😀'.repeat(1000),priority:'normal'}}));
  const value = {items:notes,next_cursor:'more'}, raw = JSON.stringify(value);
  expect(new TextEncoder().encode(raw).byteLength).toBeGreaterThan(65536);
  const loaded = await http(value).server.shoppingList(scope,null).result;
  expect(loaded.items).toHaveLength(25);expect(loaded.items[24].annotation?.note).toBe(notes[24].annotation.note);
  const fullSources = {item:product,sources:notes.map((note,i) => ({source:{...source,source_id:'source-'+i,origin_id:'extra-'+i},annotation:note.annotation})),next_cursor:null};
  expect((await http(fullSources).server.shoppingSources(scope,'product',null).result).items).toHaveLength(25);
  await expect(http(value).server.read(scope,null).result).rejects.toMatchObject({code:'invalid_response'});
  for (const declaredLength of [undefined,SHOPPING_PAGE_MAX_BYTES+1]) {
    const tooLarge = ' '.repeat(SHOPPING_PAGE_MAX_BYTES)+raw;
    await expect(http(null,'standalone',tooLarge,declaredLength).server.shoppingList(scope,null).result)
      .rejects.toMatchObject({code:'invalid_response'});
  }
});

async function shoppingForm() {
  const node = document.createElement('domus-shopping-list');node.language='en';
  const view: InventoryState = {scope,report,history:null,busy:false,pending:false,result:null,notice:null,
    shoppingList:{items:[],cursor:null}};
  node.view=view;document.body.append(node);await node.updateComplete;
  const form = node.shadowRoot!.querySelector<HTMLFormElement>('#shopping-extra-form')!;
  const name = form.querySelector<HTMLElementTagNameMap['vyp-ha-field']>('vyp-ha-field[name="name"]')!;
  const quantity = form.querySelector<HTMLInputElement>('input[name="quantity"]')!;
  return {node,view,form,name,quantity};
}

test.each(['en','es'] as const)('manual extra names retain the full domain value, correct invalid drafts and fence disabled edits (%s)', async language => {
  const {node,view,form,name,quantity}=await shoppingForm();node.language=language;await node.updateComplete;
  const events=vi.fn();node.addEventListener('domus-inventory-intent',events);quantity.value='1';
  const edit=(value:string)=>name.dispatchEvent(new CustomEvent('ha-value-request',{detail:{value,reason:'input'}}));
  const full='😀'.repeat(160);edit(full+'X');form.dispatchEvent(new Event('submit',{cancelable:true}));await node.updateComplete;
  expect(events).not.toHaveBeenCalled();expect(name.value).toBe(full+'X');expect(name.state.error).toContain('160');
  node.view={...view,pending:true};await node.updateComplete;
  edit('Late edit');expect(name.value).toBe(full+'X');
  node.view=view;await node.updateComplete;edit(full);form.dispatchEvent(new Event('submit',{cancelable:true}));
  expect(events.mock.lastCall?.[0].detail.command).toMatchObject({action:'shopping.add-extra',product_id:null,name:full,quantity:'1'});
  expect(new FormData(form).get('name')).toBe(full);
});

test('checking an earlier committed outcome preserves the unrelated manual-request draft', async () => {
  const {node,view,name,quantity} = await shoppingForm();
  name.value='Later request';quantity.value='2';
  node.view={...view,result:saved};await node.updateComplete;await node.updateComplete;
  expect(name.value).toBe('Later request');expect(quantity.value).toBe('2');
});

test('a draft edited after submission stays intact even if the values return to the submitted text', async () => {
  const {node,view,form,name,quantity} = await shoppingForm();
  name.value='My request';quantity.value='2';form.dispatchEvent(new Event('submit',{cancelable:true}));
  for (const value of ['Another draft','My request']) {
    name.value=value;name.dispatchEvent(new Event('input',{bubbles:true}));
  }
  node.view={...view,result:saved};await node.updateComplete;await node.updateComplete;
  expect(name.value).toBe('My request');expect(quantity.value).toBe('2');
});

test.each(['scope','replacement','programmatic'] as const)('an earlier form submission cannot clear another draft owner (%s)', async change => {
  const current = await shoppingForm(), {node,view,form,name,quantity} = current;
  name.value='Submitted';quantity.value='2';form.dispatchEvent(new Event('submit',{cancelable:true}));
  if (change === 'replacement') {
    node.view={...view,shoppingList:null};await node.updateComplete;
    node.view=view;await node.updateComplete;
    node.shadowRoot!.querySelector<HTMLElementTagNameMap['vyp-ha-field']>('vyp-ha-field[name="name"]')!.value='New form';
  } else if (change === 'programmatic') name.value='Later programmatic draft';
  const next = change === 'scope' ? {...view,scope:{...scope,key:'another-home'}} : view;
  const before = node.shadowRoot!.querySelector<HTMLElementTagNameMap['vyp-ha-field']>('vyp-ha-field[name="name"]')!.value;
  node.view={...next,result:saved};await node.updateComplete;await node.updateComplete;
  expect(node.shadowRoot!.querySelector<HTMLElementTagNameMap['vyp-ha-field']>('vyp-ha-field[name="name"]')!.value).toBe(before);
});

test.each(['historical','rejected'] as const)('a resolved %s request retires its form ownership without clearing the draft', async kind => {
  const {node,view,form,name,quantity} = await shoppingForm();
  name.value='Keep this draft';quantity.value='2';form.dispatchEvent(new Event('submit',{cancelable:true}));
  const result = kind === 'historical' ? {...saved,kind:'historical' as const}
    : {kind:'rejected' as const,reason:'permission_denied' as const,command:legacy};
  node.view={...view,result};await node.updateComplete;await node.updateComplete;
  expect(name.value).toBe('Keep this draft');expect(quantity.value).toBe('2');
  node.view={...view,result:saved};await node.updateComplete;await node.updateComplete;
  expect(name.value).toBe('Keep this draft');expect(quantity.value).toBe('2');
});

test('the shared priority selector keeps closed defaults, all four labels and the exact submitted choice', async () => {
  const {node,view,form,name,quantity} = await shoppingForm();
  const select = form.querySelector('vyp-ha-select')!;await select.updateComplete;
  expect(select.value).toBe('normal');expect(select.defaultValue).toBe('normal');
  expect(select.state.label).toBe('Priority');
  expect(select.state.options.map(option => option.label)).toEqual(['Low','Normal','High','Urgent']);
  const intents = vi.fn();node.addEventListener('domus-inventory-intent',intents);
  name.value='Tea';quantity.value='2';
  const choose = async (value:unknown, reason = 'change') => {
    select.dispatchEvent(new CustomEvent('ha-select-request',{detail:{value,reason}}));
    await node.updateComplete;await select.updateComplete;
  };
  for (const priority of SHOPPING_PRIORITIES) {
    await choose(priority);expect(select.value).toBe(priority);
    expect(new FormData(form).get('priority')).toBe(priority);
    form.dispatchEvent(new Event('submit',{cancelable:true}));
    expect(intents.mock.lastCall?.[0].detail).toEqual({type:'submit',command:{action:'shopping.add-extra',
      product_id:null,name:'Tea',quantity:'2',note:'',priority}});
  }
  for (const invalid of [null, [], 'red']) {
    await choose(invalid);expect(select.value).toBe('urgent');expect(select.state.error).toContain('Choose Low');
  }
  await choose('normal','unsupported');expect(select.value).toBe('urgent');
  await choose('high');expect(select.state.error).toBe('');
  node.view={...view,pending:true};await node.updateComplete;
  await choose('low');expect(select.disabled).toBe(true);expect(select.value).toBe('high');
  node.language='es';node.view=view;await node.updateComplete;await select.updateComplete;
  expect(select.state.label).toBe('Prioridad');
  expect(select.state.options.map(option => option.label)).toEqual(['Baja','Normal','Alta','Urgente']);
  // Changing a priority after submission retains the new draft even when the old result arrives.
  node.view={...view,result:saved};await node.updateComplete;await node.updateComplete;
  expect(name.value).toBe('Tea');expect(quantity.value).toBe('2');expect(select.value).toBe('high');
});

test('a committed unchanged priority draft clears only its own form and returns to normal', async () => {
  const {node,view,form,name,quantity} = await shoppingForm();
  const select = form.querySelector('vyp-ha-select')!;await select.updateComplete;
  select.dispatchEvent(new CustomEvent('ha-select-request',{detail:{value:'urgent',reason:'change'}}));
  await node.updateComplete;await select.updateComplete;
  name.value='Tea';quantity.value='1';form.dispatchEvent(new Event('submit',{cancelable:true}));
  node.view={...view,busy:true,result:saved};await node.updateComplete;await node.updateComplete;await select.updateComplete;
  expect(name.value).toBe('');expect(quantity.value).toBe('');expect(select.value).toBe('normal');
});

test('manual notes and textual priorities stay literal, attributable and absent from aggregate or automatic rows', async () => {
  const {node,view} = await shoppingForm();
  const task = {id:'automatic',kind:'pantry' as const,originId:'product',lineId:null,name:'Automatic',quantity:'1',
    reserved:'0',stock:'0',incoming:'0',toBuy:'1',attribution:null,annotation:{note:'MUST NOT APPEAR',priority:'urgent' as const}};
  node.view={...view,shoppingList:{items:[{productId:null,extraId:'free',name:'Tea',unit:'piece',pantry:'0',tasks:'0',
    manual:'1',total:'1',attribution:{memberId:'requester',authorAlias:'Requester',createdAt:'100'},annotation:{note:annotated.note,priority:'urgent'}},
    {productId:'product',extraId:null,name:'Tea aggregate',unit:'piece',pantry:'1',tasks:'0',manual:'0',total:'1',
      attribution:null,annotation:{note:'MUST NOT APPEAR',priority:'high'}}],cursor:null},
    shoppingSources:{item:{productId:'product',extraId:null,name:'Tea',unit:'piece',pantry:'1',tasks:'0',manual:'2',total:'3',attribution:null},
      items:[task,{...task,id:'manual-one',kind:'extra',attribution:{memberId:'requester',authorAlias:'Requester',createdAt:'100'},annotation:{note:'Separate\nsource',priority:'low'}},
        {...task,id:'manual-two',kind:'extra',attribution:{memberId:'requester',authorAlias:'Requester',createdAt:'100'},annotation:{note:'',priority:'high'}}],cursor:null}};
  await node.updateComplete;
  const root = node.shadowRoot!;
  expect([...root.querySelectorAll('.manual-note')].map(element => element.textContent)).toEqual([annotated.note,'Separate\nsource']);
  expect(root.querySelector('img')).toBeNull();expect(root.querySelector('a')).toBeNull();
  expect(root.textContent).not.toContain('MUST NOT APPEAR');
  expect(root.textContent).toContain('Requester');
  for (const label of ['Priority: Urgent','Priority: Low','Priority: High']) expect(root.textContent).toContain(label);
  node.language='es';await node.updateComplete;
  for (const label of ['Prioridad: Urgente','Prioridad: Baja','Prioridad: Alta']) expect(root.textContent).toContain(label);
});

test('legacy projected extras without annotation data keep their quantity and author without invented metadata', async () => {
  const {node,view} = await shoppingForm();
  const item = {productId:null,extraId:'legacy-extra',name:'Legacy tea',unit:'piece' as const,pantry:'0',tasks:'0',
    manual:'2',total:'2',attribution:{memberId:'requester',authorAlias:'Legacy requester',createdAt:'100'}};
  for (const annotation of [undefined,null]) {
    node.view={...view,shoppingList:{items:[{...item,annotation}],cursor:null}};await node.updateComplete;
    expect(node.shadowRoot!.textContent).toContain('Legacy tea');
    expect(node.shadowRoot!.textContent).toContain('2 pieces');
    expect(node.shadowRoot!.textContent).toContain('Legacy requester');
    expect(node.shadowRoot!.querySelector('.manual-annotation')).toBeNull();
  }
});

test('a denied manual request explains shopping access instead of asking for stock-management rights', async () => {
  const node=document.createElement('domus-inventory');node.language='en';
  node.view={scope,report,history:null,busy:false,pending:false,notice:null,
    result:{kind:'rejected',reason:'permission_denied',command:annotated}};
  document.body.append(node);await node.updateComplete;
  const feedback=node.shadowRoot!.querySelector('vyp-ha-feedback')!;
  await feedback.updateComplete;
  expect(feedback.state!.message).toContain('adding shopping requests');
  expect(feedback.state!.message).toContain('household administrator');
  expect(feedback.state!.message).not.toContain('inventory management');
  node.language='es';await node.updateComplete;
  expect(feedback.state!.message).toContain('solicitudes de compra');
  expect(feedback.state!.message).toContain('administradora del hogar');
});

async function noteForm() {
  const current = await shoppingForm();
  const note = current.form.querySelector('vyp-ha-textarea')!;
  await note.updateComplete;
  const edit = async (value:unknown, reason:unknown = 'input') => {
    note.dispatchEvent(new CustomEvent('ha-value-request',{detail:{value,reason}}));
    await current.node.updateComplete;await note.updateComplete;
  };
  return {...current,note,edit};
}

test('the published multiline note keeps literal codepoints, localized help and actionable correction', async () => {
  const {node,view,form,name,quantity,note,edit} = await noteForm();
  name.value='Literal request';quantity.value='2';
  const intents=vi.fn();node.addEventListener('domus-inventory-intent',intents);
  expect(note.value).toBe('');expect(note.defaultValue).toBe('');expect(note.name).toBe('note');
  expect(note.state.label).toBe('Note (optional)');expect(note.state.maxLength).toBe(1000);
  expect(note.state.description).toContain('Line breaks and tabs');
  for (const value of ['',annotated.note,'😀'.repeat(1000)]) {
    await edit(value);expect(note.value).toBe(value);
    expect(new FormData(form).get('note')).toBe(value);
    form.dispatchEvent(new Event('submit',{cancelable:true}));
    expect(intents.mock.lastCall?.[0].detail.command).toEqual({action:'shopping.add-extra',product_id:null,
      name:'Literal request',quantity:'2',note:value,priority:'normal'});
  }
  const submitted=intents.mock.calls.length;
  await edit('😀'.repeat(1001));
  expect(note.value).toBe('😀'.repeat(1001));expect(note.validity.tooLong).toBe(true);
  // Show the correction while editing, before blur can move the touch submit target.
  expect(note.state.error).toContain('1,000');
  form.dispatchEvent(new Event('submit',{cancelable:true}));
  await node.updateComplete;await note.updateComplete;
  expect(intents).toHaveBeenCalledTimes(submitted);
  expect(note.state.error).toContain('1,000');expect(node.shadowRoot!.activeElement).toBe(note);
  expect(name.value).toBe('Literal request');expect(quantity.value).toBe('2');
  for (const value of ['\u0000','\u0001','\u007f','\ud800',null,
    ...Array.from({length:32},(_,index)=>String.fromCharCode(0x80+index))]) {
    await edit(value);expect(note.value).toBe('😀'.repeat(1001));
    expect(note.state.error).toContain('unsupported control characters');
  }
  await edit('corrected');expect(note.state.error).toBe('');
  await edit('forged','unsupported');expect(note.value).toBe('corrected');expect(note.state.error).not.toBe('');
  await edit('Again\n\t😀');
  node.language='es';await node.updateComplete;await note.updateComplete;
  expect(note.value).toBe('Again\n\t😀');expect(note.state.label).toBe('Nota (opcional)');
  expect(note.state.description).toContain('saltos de línea');
  for (const flags of [{pending:true},{busy:true}]) {
    node.view={...view,...flags};await node.updateComplete;await note.updateComplete;
    await edit('must not replace');expect(note.value).toBe('Again\n\t😀');expect(note.disabled).toBe(true);
  }
  node.view={...view,scope:{...scope,readOnly:true}};await node.updateComplete;
  expect(node.shadowRoot!.querySelector('vyp-ha-textarea')).toBeNull();
});

test.each(['rejected','historical','uncertain'] as const)('notes and priorities survive %s without a replacement command', async kind => {
  const {node,view,form,name,quantity,note,edit} = await noteForm();
  name.value='Keep draft';quantity.value='2';await edit(annotated.note);
  const priority=form.querySelector('vyp-ha-select')!;
  priority.dispatchEvent(new CustomEvent('ha-select-request',{detail:{value:'urgent',reason:'change'}}));
  await node.updateComplete;
  const intents=vi.fn();node.addEventListener('domus-inventory-intent',intents);
  form.dispatchEvent(new Event('submit',{cancelable:true}));
  const command=intents.mock.lastCall![0].detail.command;
  const result=kind==='rejected'?{kind:'rejected' as const,reason:'permission_denied' as const,command}
    :kind==='historical'?{...saved,kind:'historical' as const}:null;
  node.view={...view,result,pending:kind==='uncertain',notice:kind==='uncertain'?'unavailable':null};
  await node.updateComplete;await note.updateComplete;await priority.updateComplete;
  expect(name.value).toBe('Keep draft');expect(quantity.value).toBe('2');
  expect(note.value).toBe(annotated.note);expect(priority.value).toBe('urgent');
  expect(intents).toHaveBeenCalledTimes(1);
  if(kind!=='uncertain') {
    node.view={...view,result:saved};await node.updateComplete;await node.updateComplete;
    expect(note.value).toBe(annotated.note);expect(priority.value).toBe('urgent');
  }
});

test('an unchanged committed busy request resets its own note and priority together', async () => {
  const {node,view,form,name,quantity,note,edit} = await noteForm();
  name.value='Owned request';quantity.value='1';await edit(annotated.note);
  const priority=form.querySelector('vyp-ha-select')!;
  priority.dispatchEvent(new CustomEvent('ha-select-request',{detail:{value:'high',reason:'change'}}));
  await node.updateComplete;
  form.dispatchEvent(new Event('submit',{cancelable:true}));
  node.view={...view,busy:true,result:saved};await node.updateComplete;await node.updateComplete;
  await note.updateComplete;await priority.updateComplete;
  expect(name.value).toBe('');expect(quantity.value).toBe('');
  expect(note.value).toBe('');expect(priority.value).toBe('normal');
});

test.each([false,true])('an earlier committed request preserves a later note draft (submitted=%s)', async submitted => {
  const {node,view,form,name,quantity,note,edit} = await noteForm();
  name.value='Later request';quantity.value='1';await edit('Original\n😀');
  if(submitted) {
    form.dispatchEvent(new Event('submit',{cancelable:true}));
    await edit('Different note');await edit('Original\n😀');
  }
  node.view={...view,result:saved};await node.updateComplete;await node.updateComplete;await note.updateComplete;
  expect(note.value).toBe('Original\n😀');expect(name.value).toBe('Later request');expect(quantity.value).toBe('1');
});

test('prohibited native insertion keeps the accepted note and explains how to correct it', async () => {
  const {node,note,edit} = await noteForm();await edit('Keep\n😀');
  const native=note.shadowRoot!.querySelector('textarea')!;
  const event=new InputEvent('beforeinput',{inputType:'insertText',data:'bad\u0001',bubbles:true,composed:true,cancelable:true});
  native.dispatchEvent(event);await node.updateComplete;await note.updateComplete;
  expect(event.defaultPrevented).toBe(true);expect(note.value).toBe('Keep\n😀');
  expect(note.state.error).toContain('unsupported control characters');
  const valid=new InputEvent('beforeinput',{inputType:'insertText',data:'\t\n😀',bubbles:true,composed:true,cancelable:true});
  native.dispatchEvent(valid);expect(valid.defaultPrevented).toBe(false);
  native.value='Keep\n😀bad\u0001';
  native.dispatchEvent(new InputEvent('input',{inputType:'insertText',data:'bad\u0001',bubbles:true,composed:true}));
  await node.updateComplete;await note.updateComplete;
  expect(note.value).toBe('Keep\n😀');expect(native.value).toBe('Keep\n😀');
  expect(note.state.error).toContain('unsupported control characters');
  for(let code=0x80;code<=0x9f;code++){
    const inserted='bad'+String.fromCharCode(code);
    const blocked=new InputEvent('beforeinput',{inputType:'insertText',data:inserted,bubbles:true,composed:true,cancelable:true});
    native.dispatchEvent(blocked);await node.updateComplete;await note.updateComplete;
    expect(blocked.defaultPrevented).toBe(true);expect(note.value).toBe('Keep\n😀');
    native.value='Keep\n😀'+inserted;
    native.dispatchEvent(new InputEvent('input',{inputType:'insertText',data:inserted,bubbles:true,composed:true}));
    await node.updateComplete;await note.updateComplete;
    expect(note.value).toBe('Keep\n😀');expect(native.value).toBe('Keep\n😀');
    expect(note.state.error).toContain('unsupported control characters');
  }
  const removal=new InputEvent('beforeinput',{inputType:'deleteContentBackward',bubbles:true,composed:true,cancelable:true});
  native.dispatchEvent(removal);expect(removal.defaultPrevented).toBe(false);
  const transfer=new DataTransfer();transfer.setData('text/plain','bad\u0001');
  const paste=new InputEvent('beforeinput',{inputType:'insertFromPaste',dataTransfer:transfer,bubbles:true,composed:true,cancelable:true});
  native.dispatchEvent(paste);await node.updateComplete;expect(paste.defaultPrevented).toBe(true);
  node.view={...node.view,pending:true};await node.updateComplete;
  const blocked=new InputEvent('beforeinput',{inputType:'insertText',data:'bad\u0001',bubbles:true,composed:true,cancelable:true});
  native.dispatchEvent(blocked);expect(blocked.defaultPrevented).toBe(false);expect(note.value).toBe('Keep\n😀');
});
