import {afterEach, expect, test, vi} from 'vitest';
import type {HaTextField} from '@vypdev/ha-ui/field';
import type {InventoryState, InventoryResult} from '../src/application/inventory-controller';
import {revisionValue} from '../src/domain/administration';
import type {InventoryCommand, StorageLocation} from '../src/domain/inventory';
import '../src/presentation/domus-storage-locations';

const scope = {key:'home', context:{installationId:'047cc6fb-dfb0-4fa4-b3c3-e0fe54d116b6',
  channel:'edge' as const,subject:'a'.repeat(32)}, readOnly:false};
const cupboard: StorageLocation = {id:'cupboard',name:'Cupboard',revision:revisionValue('1'),
  archived:false,archiveBlockedReason:null};
const shelf: StorageLocation = {...cupboard,id:'shelf',name:'Shelf',archived:true};
const initial: InventoryState = {scope,report:{mayManage:true,mayShop:true,mayRequest:true,
  products:[],locations:[cupboard,shelf],cursor:null},history:null,busy:false,pending:false,result:null,notice:null};
const rename = {action:'inventory.rename-location',location_id:'cupboard',name:'Drawer',expected_revision:revisionValue('1')} as const;
const mounted: HTMLElement[] = [];
afterEach(()=>{for(const node of mounted.splice(0))node.remove();});

async function fixture(language:'en'|'es'='en', view:InventoryState|null=initial) {
  const node=document.createElement('domus-storage-locations');node.language=language;node.view=view;
  document.body.append(node);mounted.push(node);const events=vi.fn();node.addEventListener('domus-inventory-intent',events);
  const root=node.shadowRoot!;
  const settle=async()=>{
    await node.updateComplete;
    for(let frame=0;frame<2;frame++)await new Promise<void>(resolve=>requestAnimationFrame(()=>resolve()));
    await node.updateComplete;
  };
  const assign=async(patch:Partial<InventoryState>)=>{node.view={...node.view!,...patch};await settle();};
  const locations=async(items:readonly StorageLocation[])=>assign({report:{...(node.view!.report??initial.report!),locations:items}});
  const button=(label:string)=>[...root.querySelectorAll('vyp-ha-button')].find(item=>item.state.label===label)!;
  const press=async(label:string)=>{const control=button(label);expect(control).toBeDefined();control.dispatchEvent(new Event('ha-press-request'));await settle();};
  const field=(form='review')=>root.querySelector<HaTextField>('.location-'+form+' vyp-ha-field')!;
  const input=async(value:string,form='review')=>{field(form).dispatchEvent(new CustomEvent('ha-value-request',{detail:{value,reason:'input'}}));await settle();};
  const submit=async(form='review')=>{root.querySelector<HTMLFormElement>('.location-'+form)!.dispatchEvent(new Event('submit',{cancelable:true}));await settle();};
  const changed=(action:'rename'|'archive'|'restore',location:StorageLocation,kind:'committed'|'historical'='committed'):InventoryResult=>({kind,operationId:'operation',productId:null,movement:null,
    locationChanged:{action:('inventory.'+action+'-location') as 'inventory.rename-location'|'inventory.archive-location'|'inventory.restore-location',location}});
  await settle();return {node,root,events,settle,assign,locations,button,press,field,input,submit,changed};
}

test('locations render only current household data and explain current read-only and management permissions',async()=>{
  const f=await fixture('en',null);expect(f.root.querySelector('vyp-ha-card')).toBeNull();
  f.node.view={...initial,report:null};await f.settle();expect(f.root.querySelector('ul')).toBeNull();
  await f.assign(initial);expect(f.root.textContent).toContain('Pantry');
  expect(f.root.querySelectorAll('[data-location-id]')).toHaveLength(2);
  expect(f.root.querySelector('details')!.open).toBe(false);
  await f.assign({report:{...initial.report!,mayManage:false}});
  expect(f.root.querySelector('form')).toBeNull();expect(f.root.textContent).toContain('inventory manager');
  await f.assign({scope:{...scope,readOnly:true}});expect(f.root.textContent).toContain('read only');
  await f.assign({scope,report:initial.report});await f.input('Private draft','add');await f.press('Rename Cupboard');await f.input('Private name');
  await f.assign({scope:{...scope,key:'different-home'},report:{...initial.report!,locations:[]}});
  expect(f.field('add').value).toBe('');expect(f.root.querySelector('.location-review')).toBeNull();
  expect(f.root.textContent).not.toContain('Private');expect(f.root.querySelector('details')).toBeNull();
});

test.each(['en','es'] as const)('add drafts survive rejection, unrelated receipts, historical recovery and busy events (%s)',async language=>{
  const f=await fixture(language);await f.input('😀'.repeat(81),'add');await f.submit('add');
  expect(f.events).not.toHaveBeenCalled();expect(f.field('add').state.error).toContain('80');
  await f.input(' Cupboard ','add');await f.submit('add');expect(f.events.mock.lastCall?.[0].detail.command).toEqual({action:'inventory.add-location',name:'Cupboard'});
  await f.assign({result:{kind:'rejected',reason:'inventory_location_exists',command:{action:'inventory.add-location',name:'Cupboard'}}});
  expect(f.field('add').value).toBe(' Cupboard ');expect(f.root.activeElement).toBe(f.field('add'));
  const saved:InventoryResult={kind:'committed',operationId:'add',productId:null,movement:null,locationSaved:true,addedLocation:{id:'cupboard',name:'Cupboard'}};
  await f.assign({result:{...saved,kind:'historical'}});expect(f.field('add').value).toBe(' Cupboard ');
  await f.input('Later draft','add');await f.assign({result:saved});expect(f.field('add').value).toBe('Later draft');
  await f.assign({pending:true});await f.input('Forged edit','add');await f.submit('add');expect(f.field('add').value).toBe('Later draft');expect(f.events).toHaveBeenCalledTimes(1);
  await f.assign({pending:false,result:null});await f.input('Cupboard','add');await f.assign({busy:true,result:saved});expect(f.field('add').value).toBe('');
  await f.assign({busy:false});expect(f.root.activeElement?.getAttribute('data-location-id')).toBe('cupboard');
});

test('rename requires real bounded changes and preserves add and rename drafts through a rejected current write',async()=>{
  const f=await fixture();await f.input('Unrelated add','add');await f.press('Rename Cupboard');
  expect(f.field().value).toBe('Cupboard');expect(f.root.activeElement).toBe(f.field());
  expect(f.button('Save name').disabled).toBe(true);await f.submit();expect(f.events).not.toHaveBeenCalled();
  await f.input('😀'.repeat(81));await f.submit();expect(f.field().state.error).toContain('80');expect(f.events).not.toHaveBeenCalled();
  await f.input(' Drawer ');await f.submit();expect(f.events.mock.lastCall?.[0].detail.command).toEqual(rename);
  await f.assign({result:{kind:'rejected',reason:'inventory_location_exists',command:rename}});
  expect(f.field().value).toBe(' Drawer ');expect(f.field('add').value).toBe('Unrelated add');expect(f.field().state.error).toContain('already');
  await f.assign({busy:true});await f.input('Late event');await f.submit();await f.press('Cancel');
  expect(f.field().value).toBe(' Drawer ');expect(f.events).toHaveBeenCalledTimes(1);
  await f.assign({busy:false});await f.press('Cancel');expect(f.root.querySelector('.location-review')).toBeNull();
  expect(f.root.activeElement).toBe(f.button('Rename Cupboard'));await f.press('Rename Cupboard');expect(f.field().value).toBe('Cupboard');
  await f.input('Drawer');await f.submit();const current={...cupboard,name:'Drawer',revision:revisionValue('2')};
  await f.assign({report:{...initial.report!,locations:[current,shelf]},result:f.changed('rename',current)});
  expect(f.root.querySelector('.location-review')).toBeNull();expect(f.root.activeElement?.getAttribute('data-location-id')).toBe('cupboard');
  expect(f.field('add').value).toBe('Unrelated add');
});

test('current revision changes and historical receipts require explicit review without replacing the later draft',async()=>{
  const f=await fixture();await f.press('Rename Cupboard');await f.input('Drawer');await f.submit();
  await f.input('Later draft');const current={...cupboard,name:'Drawer',revision:revisionValue('2')};
  await f.assign({report:{...initial.report!,locations:[current,shelf]},result:f.changed('rename',current)});
  expect(f.field().value).toBe('Later draft');expect(f.button('Save name').disabled).toBe(true);
  await f.submit();expect(f.events).toHaveBeenCalledTimes(1);await f.press('Review current location');await f.submit();
  expect(f.events.mock.lastCall?.[0].detail.command).toEqual({...rename,name:'Later draft',expected_revision:revisionValue('2')});
  await f.assign({result:f.changed('rename',current,'historical')});await f.submit();expect(f.events).toHaveBeenCalledTimes(2);
  await f.press('Review current location');await f.submit();expect(f.events).toHaveBeenCalledTimes(3);
  await f.locations([{...current,revision:revisionValue('3')},shelf]);await f.submit();expect(f.events).toHaveBeenCalledTimes(3);
  await f.press('Review current location');await f.submit();expect(f.events.mock.lastCall?.[0].detail.command.expected_revision).toBe('3');
  await f.assign({result:{kind:'rejected',reason:'inventory_location_missing',command:{...rename,location_id:'elsewhere'}}});
  expect(f.field().value).toBe('Later draft');await f.locations([shelf]);await f.submit();expect(f.events).toHaveBeenCalledTimes(4);
  expect(f.button('Save name').disabled).toBe(true);
});

test('archive rechecks all current eligibility and restoration keeps identity with an explicit confirmation',async()=>{
  const f=await fixture();await f.locations([{...cupboard,archiveBlockedReason:'inventory_location_not_empty'},shelf]);
  expect(f.button('Archive Cupboard').disabled).toBe(true);await f.press('Archive Cupboard');await f.submit();expect(f.events).not.toHaveBeenCalled();
  expect(f.root.textContent).toContain('stock');await f.locations([{...cupboard,archiveBlockedReason:'inventory_location_pending_effects'},shelf]);
  await f.submit();expect(f.events).not.toHaveBeenCalled();await f.locations([cupboard,shelf]);await f.submit();
  const archive:InventoryCommand={action:'inventory.archive-location',location_id:'cupboard',expected_revision:revisionValue('1')};
  expect(f.events.mock.lastCall?.[0].detail.command).toEqual(archive);
  await f.assign({result:{kind:'rejected',reason:'inventory_location_pending_effects',command:archive}});
  expect(f.root.activeElement?.localName).toBe('h4');
  const archived={...cupboard,archived:true,revision:revisionValue('2')};
  await f.assign({report:{...initial.report!,locations:[archived,shelf]},result:f.changed('archive',archived)});
  expect(f.root.querySelector('.location-review')).toBeNull();expect(f.root.querySelector('details')!.open).toBe(true);
  expect(f.root.activeElement?.getAttribute('data-location-id')).toBe('cupboard');
  await f.press('Restore Cupboard');expect(f.root.activeElement?.localName).toBe('h4');
  await f.submit();expect(f.events.mock.lastCall?.[0].detail.command).toEqual({action:'inventory.restore-location',location_id:'cupboard',expected_revision:'2'});
  await f.assign({result:f.changed('restore',archived,'historical')});await f.submit();expect(f.events).toHaveBeenCalledTimes(2);
  await f.press('Review current location');const restored={...cupboard,revision:revisionValue('3')};
  await f.assign({report:{...initial.report!,locations:[restored,shelf]},result:f.changed('restore',restored)});
  expect(f.root.querySelector('.location-review')).toBeNull();expect(f.root.activeElement?.getAttribute('data-location-id')).toBe('cupboard');
});

test('current permissions and state guard captured controls, and unrelated outcomes preserve the active editor',async()=>{
  const f=await fixture();const old=f.button('Rename Cupboard');await f.assign({scope:{...scope,readOnly:true}});
  old.dispatchEvent(new Event('ha-press-request'));await f.settle();expect(f.root.querySelector('.location-review')).toBeNull();
  await f.assign({scope});await f.press('Rename Cupboard');await f.input('Draft');
  await f.assign({result:f.changed('restore',shelf)});expect(f.field().value).toBe('Draft');
  await f.assign({result:{kind:'rejected',reason:'permission_denied',command:{action:'inventory.intake',product_id:'product',quantity:'1'}}});
  expect(f.field().value).toBe('Draft');await f.locations([{...cupboard,archived:true,revision:revisionValue('2')},shelf]);
  await f.submit();expect(f.events).not.toHaveBeenCalled();await f.press('Review current location');await f.submit();expect(f.events).not.toHaveBeenCalled();
  await f.press('Cancel');await f.press('Restore Shelf');
  await f.locations([cupboard,{...shelf,archived:false,revision:revisionValue('2')}]);
  await f.submit();expect(f.events).not.toHaveBeenCalled();
});

test('an add result leaves an independent rename draft intact, and recovered metadata can focus a row without opening an editor',async()=>{
  const f=await fixture();await f.input('Cupboard','add');await f.press('Rename Cupboard');await f.input('Independent rename');
  await f.assign({result:{kind:'committed',operationId:'add',productId:null,movement:null,addedLocation:{id:'cupboard',name:'Cupboard'}}});
  expect(f.field('add').value).toBe('');expect(f.field().value).toBe('Independent rename');
  await f.press('Cancel');await f.assign({result:f.changed('restore',shelf)});
  expect(f.root.querySelector('.location-review')).toBeNull();expect(f.root.activeElement?.getAttribute('data-location-id')).toBe('shelf');
  await f.assign({result:f.changed('restore',shelf,'historical')});
  expect(f.root.activeElement?.getAttribute('data-location-id')).toBe('shelf');
  await f.press('Restore Shelf');await f.press('Cancel');expect(f.root.activeElement).toBe(f.button('Restore Shelf'));
});

test('navigation immediately after rendering retires a queued location focus before the next household',async()=>{
  const f=await fixture();f.node.view={...initial,result:f.changed('restore',shelf)};
  const rendered=f.node.updateComplete;
  void rendered.then(()=>{f.node.view={...initial,scope:{...scope,key:'next-home'},report:{...initial.report!,locations:[]}};});
  await rendered;await f.settle();expect(f.root.activeElement).toBeNull();expect(f.root.querySelector('[data-location-id]')).toBeNull();
});

test('a command receipt arriving before its catalog refresh keeps focus pending until the archived row is rendered',async()=>{
  const f=await fixture();await f.press('Archive Cupboard');
  const archived={...cupboard,archived:true,revision:revisionValue('2')};
  await f.assign({result:f.changed('archive',archived)});
  expect(f.root.querySelector('.location-review')).toBeNull();expect(f.root.activeElement?.getAttribute('data-location-id')).not.toBe('cupboard');
  await f.assign({report:null});expect(f.root.querySelector('vyp-ha-card')).toBeNull();
  await f.locations([archived,shelf]);expect(f.root.querySelector('details')!.open).toBe(true);
  expect(f.root.activeElement?.getAttribute('data-location-id')).toBe('cupboard');
  await f.input('New location','add');await f.assign({result:{kind:'committed',operationId:'add',productId:null,movement:null,addedLocation:{id:'new',name:'New location'}}});
  expect(f.field('add').value).toBe('');await f.locations([archived,shelf,{...cupboard,id:'new',name:'New location'}]);
  expect(f.root.activeElement?.getAttribute('data-location-id')).toBe('new');
});
