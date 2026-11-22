import {afterEach, expect, test, vi} from 'vitest';
import type {InventoryState} from '../src/application/inventory-controller';
import {inventoryCommand} from '../src/domain/inventory';
import '../src/presentation/domus-shopping-workspace';

const owned: HTMLElement[] = [];
afterEach(() => {vi.restoreAllMocks(); for (const node of owned.splice(0)) node.remove();});
const initial: InventoryState = {
  scope:{key:'verified-owner', context:{installationId:'047cc6fb-dfb0-4fa4-b3c3-e0fe54d116b6', channel:'edge', subject:'a'.repeat(32)}, readOnly:false},
  report:{products:[], locations:[], cursor:null, mayManage:true, mayShop:true, mayRequest:true},
  history:null, shoppingList:{items:[], cursor:null}, pending:false, busy:false, result:null, notice:null,
};
async function mount() {
  const node = document.createElement('domus-shopping-workspace');
  document.body.append(node); owned.push(node); await node.updateComplete;
  return node;
}

test('Shopping renders its own loading, failure and recovery actions without issuing automatic intents', async () => {
  const node = await mount(), events: CustomEvent[] = [];
  node.addEventListener('domus-inventory-intent', event => events.push(event as CustomEvent));
  expect(node.shadowRoot!.textContent).toBe('');
  node.view = {...initial, report:null, busy:true}; await node.updateComplete;
  expect(node.shadowRoot!.querySelector('h2')!.textContent).toBe('Shopping');
  expect(node.shadowRoot!.textContent).toContain('Loading Shopping.');
  const refresh = node.shadowRoot!.querySelector('vyp-ha-button')!;
  await refresh.updateComplete;
  refresh.shadowRoot!.querySelector('button')!.click();
  expect(events).toHaveLength(0);
  node.view = {...initial, report:null, notice:'unavailable', pending:true}; await node.updateComplete;
  const buttons = [...node.shadowRoot!.querySelectorAll('vyp-ha-button')];
  for (const button of buttons) {await button.updateComplete; button.shadowRoot!.querySelector('button')!.click();}
  expect(events.map(event => event.detail)).toEqual([{type:'refresh'}, {type:'recover'}]);
  expect(events.every(event => event.bubbles && event.composed)).toBe(true);
  expect(node.shadowRoot!.querySelector('vyp-ha-feedback')).not.toBeNull();
  expect(node.shadowRoot!.querySelector('vyp-ha-feedback')!.state?.message)
    .toBe('Shopping is unavailable. Refresh Shopping to check the current information.');
  node.language = 'es'; await node.updateComplete;
  expect(node.shadowRoot!.querySelector('h2')!.textContent).toBe('Compras');
  expect(node.shadowRoot!.querySelector('a')!.getAttribute('href')).toBe('#inventory');
  expect(node.shadowRoot!.querySelector('vyp-ha-feedback')!.state?.message)
    .toBe('Compras no está disponible. Actualiza Compras para consultar la información actual.');
  node.view = {...initial, report:null, busy:true}; await node.updateComplete;
  expect(node.shadowRoot!.textContent).toContain('Cargando Compras.');
});

test('a retained Shopping form survives same-owner view updates and is retired for a new scope', async () => {
  const node = await mount(); node.view = initial; await node.updateComplete;
  const shopping = node.shadowRoot!.querySelector('domus-shopping')!; await shopping.updateComplete;
  const list = shopping.shadowRoot!.querySelector('domus-shopping-list')!; await list.updateComplete;
  const field = list.shadowRoot!.querySelector('vyp-ha-textarea')!; await field.updateComplete;
  const note = field.shadowRoot!.querySelector('textarea')!;
  const literal = '  Keep literal\nTab\t😀 <em>text</em>  ';
  note.value = literal; note.dispatchEvent(new InputEvent('input', {bubbles:true, composed:true}));
  await list.updateComplete; await field.updateComplete;
  node.view = {...initial, busy:true}; await node.updateComplete; await shopping.updateComplete; await list.updateComplete;
  expect(node.shadowRoot!.querySelector('domus-shopping')).toBe(shopping);
  expect(field.value).toBe(literal);
  node.view = {...initial, report:null, retainedReport:initial.report,
    retainedShopping:{shoppingList:initial.shoppingList}, notice:'unavailable'};
  await node.updateComplete; await shopping.updateComplete; await list.updateComplete; await field.updateComplete;
  expect(node.shadowRoot!.querySelector('domus-shopping')).toBe(shopping);
  expect(field.value).toBe(literal);
  expect(note.disabled).toBe(true);
  expect(node.shadowRoot!.textContent).toContain('last loaded information');
  node.view = initial;
  await node.updateComplete; await shopping.updateComplete; await list.updateComplete; await field.updateComplete;
  expect(field.value).toBe(literal);
  expect(note.disabled).toBe(false);
  node.view = {...initial, scope:{...initial.scope, key:'another-owner'}}; await node.updateComplete;
  const replacement = node.shadowRoot!.querySelector('domus-shopping')!;
  expect(replacement).not.toBe(shopping);
  await replacement.updateComplete;
  const freshList = replacement.shadowRoot!.querySelector('domus-shopping-list')!; await freshList.updateComplete;
  expect(freshList.shadowRoot!.querySelector('vyp-ha-textarea')!.value).toBe('');
  node.view = null; await node.updateComplete;
  expect(node.shadowRoot!.querySelector('domus-shopping')).toBeNull();
});

test('a denied read hides retained household facts and keeps an unresolved operation explicit', async () => {
  const node = await mount();
  node.view = {...initial, accessDenied:true, retainedReport:initial.report, pending:true, notice:'uncertain'};
  await node.updateComplete;
  expect(node.shadowRoot!.querySelector('domus-shopping')).toBeNull();
  expect(node.shadowRoot!.querySelector('vyp-ha-feedback')!.state?.message).toContain('access');
  expect(node.shadowRoot!.querySelector('p[role=status]')).not.toBeNull();
  expect(node.shadowRoot!.querySelectorAll('vyp-ha-button')).toHaveLength(2);
});

test('stale Shopping sources are disabled until the current catalog is available', async () => {
  const node = await mount();
  const current = {...initial, shoppingList:{items:[{productId:'tea', extraId:null, name:'Tea', unit:'piece' as const,
    total:'2', pantry:'0', tasks:'0', manual:'2', attribution:null}], cursor:null}};
  node.view = current; await node.updateComplete;
  const shopping = node.shadowRoot!.querySelector('domus-shopping')!; await shopping.updateComplete;
  const list = shopping.shadowRoot!.querySelector('domus-shopping-list')!; await list.updateComplete;
  const source = () => [...list.shadowRoot!.querySelectorAll('vyp-ha-button')].find(button => button.state.label === 'Show shopping sources')!;
  const events = vi.fn(); node.addEventListener('domus-inventory-intent', events);
  await source().updateComplete; expect(source().disabled).toBe(false);
  node.view = {...current, report:null, retainedReport:current.report, retainedShopping:{shoppingList:current.shoppingList}, notice:'unavailable'};
  await node.updateComplete; await shopping.updateComplete; await list.updateComplete; await source().updateComplete;
  expect(source().disabled).toBe(true); source().shadowRoot!.querySelector('button')!.click();
  expect(events).not.toHaveBeenCalled();
  node.view = current;
  await node.updateComplete; await shopping.updateComplete; await list.updateComplete; await source().updateComplete;
  expect(source().disabled).toBe(false); source().shadowRoot!.querySelector('button')!.click();
  expect(events.mock.lastCall?.[0].detail).toEqual({type:'shopping-sources', productId:'tea'});
});

test.each(['en','es'] as const)('denied commands explain the actual Shopping and stock grants in %s', async language => {
  const node = await mount(); node.language = language;
  const examples = [
    [{action:'shopping.purchase',product_id:'tea',name:null,quantity:'1'},
      language === 'en' ? 'Shopping was not changed. Ask a household member with shopping management access.'
        : 'Compras no ha cambiado. Pide ayuda a un miembro del hogar que pueda gestionar las compras.'],
    ...['shopping.return-receipt','shopping.correct-posted-receipt'].map(action => [
      {action,purchase_id:'purchase',receipt_id:'receipt',reason:'Correction',expected_revision:'1'},
      language === 'en' ? 'Nothing was changed. Ask a household member with both shopping and inventory management access.'
        : 'No ha cambiado nada. Pide ayuda a un miembro del hogar que pueda gestionar tanto las compras como el inventario.',
    ]),
    [{action:'shopping.post-receipt',purchase_id:'purchase',receipt_id:'receipt'},
      language === 'en' ? 'Stock was not changed. Ask a household member with inventory management access.'
        : 'El stock no ha cambiado. Pide ayuda a un miembro del hogar que pueda gestionar el inventario.'],
  ] as const;
  for (const [raw,message] of examples) {
    node.view = {...initial,result:{kind:'rejected',reason:'permission_denied',command:inventoryCommand(raw)}};
    await node.updateComplete;
    expect(node.shadowRoot!.querySelector('vyp-ha-feedback')!.state?.message).toBe(message);
  }
});

test('item entry scroll waits for nested layout and respects a later user focus or a retired item', async () => {
  const frames: FrameRequestCallback[] = [];
  vi.spyOn(window, 'requestAnimationFrame').mockImplementation(callback => {frames.push(callback); return frames.length;});
  const node = document.createElement('domus-shopping-list');
  owned.push(node); node.language = 'en'; node.view = initial; document.body.append(node); await node.updateComplete;
  node.view = {...initial, shoppingFocus:{key:'product:gone', found:false}}; await node.updateComplete;
  const title = node.shadowRoot!.querySelector<HTMLElement>('#shopping-list-title')!;
  const scroll = vi.spyOn(title, 'scrollIntoView');
  expect(node.shadowRoot!.activeElement).toBe(title);
  const later = document.createElement('button'); document.body.append(later); owned.push(later); later.focus();
  for (const callback of frames.splice(0)) callback(0);
  expect(scroll).not.toHaveBeenCalled(); expect(document.activeElement).toBe(later);
  // A refresh may retire the requested row before the focus continuation runs.
  node.view = {...initial, shoppingFocus:{key:'product:gone', found:true}}; await node.updateComplete;
  for (const callback of frames.splice(0)) callback(0);
  expect(scroll).not.toHaveBeenCalled(); expect(document.activeElement).toBe(later);
  node.view = {...initial, shoppingFocus:{key:'product:gone', found:false}}; await node.updateComplete;
  for (const callback of frames.splice(0)) callback(0);
  expect(scroll).toHaveBeenCalledWith({block:'center'}); expect(node.shadowRoot!.activeElement).toBe(title);
});
