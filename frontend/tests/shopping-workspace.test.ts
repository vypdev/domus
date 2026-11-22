import {afterEach, expect, test} from 'vitest';
import type {InventoryState} from '../src/application/inventory-controller';
import '../src/presentation/domus-shopping-workspace';

const owned: HTMLElement[] = [];
afterEach(() => {for (const node of owned.splice(0)) node.remove();});
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
  expect(node.shadowRoot!.textContent).toContain('Loading');
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
