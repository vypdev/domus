import {afterEach, expect, test, vi} from 'vitest';
import {HttpInventoryServer} from '../src/adapters/inventory-http';
import type {StockAttentionView} from '../src/application/stock-attention';
import '../src/presentation/domus-stock-attention';

const context = {installationId:'01234567-89ab-cdef-0123-456789abcdef', channel:'edge' as const, subject:'a'.repeat(32)};
const endpoint = {origin:'https://domus.test', deployment:'standalone' as const, applicationBase:'/'};
const wireProduct = {product_id:'filters', name:'Filters <b>for tea</b>', base_unit:'piece', available:'1', minimum:'2'};
const product = {id:'filters', name:wireProduct.name, unit:'piece' as const, available:'1', minimum:'2'};
const group = (row: object) => ({total:1, items:[row]});

function reply(path: string, body: unknown): Response {
  const response = new Response(JSON.stringify(body), {headers:{'Content-Type':'application/json','Cache-Control':'no-store'}});
  Object.defineProperty(response, 'url', {value:endpoint.origin + path});
  return response;
}

test('the Inventory adapter reads a protected exact count and bounded product facts', async () => {
  const rows = Array.from({length:25}, (_, index) => ({...wireProduct, product_id:'product-' + index}));
  const network = vi.fn(async (path: string, init: RequestInit) => {
    expect(path).toBe('/api/v1/inventory/stock-attention');
    expect(init.method).toBe('GET');
    expect(new Headers(init.headers).get('X-Domus-Context')).toBe('v1:' + context.installationId + ':edge:' + context.subject);
    return reply(path, {total:30, items:rows});
  });
  const view = await new HttpInventoryServer(endpoint, network).stockAttention(context).result;
  expect(view.total).toBe(30);
  expect(view.items).toHaveLength(25);
  expect(view.items[0]).toEqual({...product, id:'product-0'});
});

test.each([
  {total:1, items:null},
  {total:1, items:[]},
  group({...wireProduct, available:'2'}),
  group({...wireProduct, available:'0.5'}),
  group({...wireProduct, minimum:'1.5'}),
  group({...wireProduct, base_unit:'crate'}),
  {total:2, items:[wireProduct, wireProduct]},
])('rejects malformed or inconsistent stock attention data', async body => {
  const server = new HttpInventoryServer(endpoint, async path => reply(path, body));
  await expect(server.stockAttention(context).result).rejects.toMatchObject({code:'invalid_response'});
});

test('decodes empty inventory and exact fractional stock quantities', async () => {
  const empty = new HttpInventoryServer(endpoint, async path => reply(path, {total:0, items:[]}));
  await expect(empty.stockAttention(context).result).resolves.toEqual({total:0, items:[]});
  const fractional = new HttpInventoryServer(endpoint, async path => reply(path,
    group({...wireProduct, base_unit:'gram', available:'0.125', minimum:'0.25'})));
  await expect(fractional.stockAttention(context).result).resolves.toEqual({
    total:1, items:[{...product, unit:'gram', available:'0.125', minimum:'0.25'}],
  });
});

afterEach(() => document.querySelectorAll('domus-stock-attention').forEach(element => element.remove()));

test('stock attention displays localized exact quantities and a real Inventory link', async () => {
  const element = document.createElement('domus-stock-attention');
  document.body.append(element);
  const show = (view: StockAttentionView) => {element.view = view; return element.updateComplete;};
  const root = element.shadowRoot!;
  const message = () => root.querySelector('vyp-ha-feedback')!.state!.message;
  const retries = vi.fn();
  element.addEventListener('domus-stock-attention-retry', retries);
  await element.updateComplete;
  expect(root.querySelector('vyp-ha-card')).toBeNull();
  await show({state:'loading'});
  expect(message()).toContain('Loading the inventory summary');
  await show({state:'denied'});
  expect(message()).toContain('current household access');
  expect(root.querySelector('a')).toBeNull();
  await show({state:'unavailable'});
  expect(message()).toContain('could not be loaded');
  const retry = root.querySelector('vyp-ha-button')!;
  await retry.updateComplete;
  retry.shadowRoot!.querySelector('button')!.click();
  expect(retries).toHaveBeenCalledOnce();

  await show({state:'ready',data:{total:0,items:[]}});
  expect(root.querySelector('vyp-ha-card')!.state.title).toBe('Products below minimum · 0');
  expect(root.querySelector('p')!.textContent).toBe('No products below minimum.');
  expect(root.querySelector('a')!.getAttribute('href')).toBe('#inventory');
  await show({state:'ready',data:{total:1,items:[product]}});
  expect(root.querySelector('li strong')!.textContent).toBe(product.name);
  expect(root.querySelector('li b')).toBeNull();
  expect(root.querySelector('li p')!.textContent).toContain('Available stock 1 piece');
  element.language = 'es';
  await show({state:'ready',data:{total:1,items:[{...product,unit:'gram',available:'0.125',minimum:'1'}]}});
  expect(root.querySelector('vyp-ha-card')!.state.title).toBe('Productos por debajo del mínimo · 1');
  expect(root.querySelector('a')!.textContent).toBe('Abrir Inventario');
  expect(root.querySelector('li p')!.textContent).toContain('0,125 gramos');
  expect(root.querySelector('li p')!.textContent).toContain('1 gramo');
});
