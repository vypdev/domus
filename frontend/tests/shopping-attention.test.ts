import {afterEach, expect, test, vi} from 'vitest';
import {HttpInventoryServer} from '../src/adapters/inventory-http';
import type {ShoppingAttentionView} from '../src/application/shopping-attention';
import '../src/presentation/domus-shopping-attention';

const context = {installationId:'01234567-89ab-cdef-0123-456789abcdef', channel:'edge' as const, subject:'a'.repeat(32)};
const endpoint = {origin:'https://domus.test', deployment:'standalone' as const, applicationBase:'/'};
const wireItem = {product_id:'oil', extra_id:null, name:'Oil <b>for cooking</b>', base_unit:'millilitre', total:'2.000001'};
const wireExtra = {product_id:null, extra_id:'oil', name:wireItem.name, base_unit:'piece', total:'1'};
const item = {productId:'oil', extraId:null, name:wireItem.name, unit:'millilitre' as const, total:'2.000001'};
const group = (row: object) => ({total:1, items:[row]});

function reply(path: string, body: unknown): Response {
  const response = new Response(JSON.stringify(body), {headers:{'Content-Type':'application/json','Cache-Control':'no-store'}});
  Object.defineProperty(response, 'url', {value:endpoint.origin + path});
  return response;
}

test('shopping attention preserves the exact authorized count, amounts, order and distinct row identities', async () => {
  const rows = [wireItem, wireExtra, ...Array.from({length:23}, (_, index) => ({...wireItem, product_id:'item-' + index}))];
  const read = vi.fn(async (path: string, init: RequestInit) => {
    expect(path).toBe('/api/v1/inventory/shopping-attention');
    expect(init.method).toBe('GET');
    expect(new Headers(init.headers).get('X-Domus-Context'))
      .toBe('v1:' + context.installationId + ':edge:' + context.subject);
    return reply(path, {total:28, items:rows});
  });
  const server = new HttpInventoryServer(endpoint, read);
  const data = await server.shoppingAttention(context).result;
  expect(data.total).toBe(28);
  expect(data.items).toHaveLength(25);
  expect(data.items.slice(0, 2)).toEqual([item, {...item, productId:null, extraId:'oil', unit:'piece', total:'1'}]);
  expect(data.items[24].productId).toBe('item-22');
});

test.each([
  {total:1, items:null},
  {total:1, items:[]},
  group({...wireItem, total:'0'}),
  group({...wireItem, base_unit:'piece'}),
  group({...wireItem, extra_id:'extra'}),
  group({...wireExtra, extra_id:null}),
  group({...wireExtra, base_unit:'gram'}),
  {total:2, items:[wireItem, wireItem]},
])('fails closed when the shopping summary is malformed or incomplete', async body => {
  const server = new HttpInventoryServer(endpoint, async path => reply(path, body));
  await expect(server.shoppingAttention(context).result).rejects.toMatchObject({code:'invalid_response'});
});

afterEach(() => document.querySelectorAll('domus-shopping-attention').forEach(element => element.remove()));

test('the shopping card distinguishes pending, denied and failed reads and localizes exact amounts', async () => {
  const element = document.createElement('domus-shopping-attention');
  document.body.append(element);
  const show = (view: ShoppingAttentionView) => {element.view = view; return element.updateComplete;};
  const root = element.shadowRoot!;
  const message = () => root.querySelector('vyp-ha-feedback')!.state!.message;
  const heading = () => root.querySelector('vyp-ha-card')!.state.title;
  const retry = vi.fn();
  element.addEventListener('domus-shopping-attention-retry', retry);
  await element.updateComplete;
  expect(root.querySelector('vyp-ha-card')).toBeNull();
  await show({state:'loading'});
  expect(message()).toContain('Loading the shopping summary');
  await show({state:'denied'});
  expect(message()).toContain('current household access');
  expect(root.querySelector('a')).toBeNull();
  await show({state:'unavailable'});
  expect(message()).toContain('could not be loaded');
  root.querySelector('vyp-ha-button')!.dispatchEvent(new Event('ha-press-request'));
  expect(retry).toHaveBeenCalledOnce();
  await show({state:'ready',data:{total:0,items:[]}});
  expect(heading()).toBe('Items to buy · 0');
  expect(root.querySelector('p')!.textContent).toBe('There are no items to buy.');
  await show({state:'ready',data:{total:1,items:[item]}});
  expect(root.querySelector('a')?.textContent).toContain('2.000001');
  expect(root.querySelector('a')?.getAttribute('href')).toBe('#inventory-shopping/product:oil');
  expect(root.querySelector('b')).toBeNull();

  element.language = 'es';
  await show({state:'ready',data:{total:26,items:Array.from({length:25}, (_, index) => ({...item, productId:'p' + index}))}});
  expect(heading()).toBe('Artículos por comprar · 26');
  expect(root.querySelector('a')?.textContent).toContain('2,000001');
  expect(root.querySelectorAll('a')).toHaveLength(25);
  expect(root.querySelector('p')?.textContent).toContain('primeros 25 artículos');
});
