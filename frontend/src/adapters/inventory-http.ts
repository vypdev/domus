/** Bounded same-origin Inventory reads and exact original-command recovery. */
import {INVENTORY_ERRORS} from '../application/inventory-controller';
import type {InventoryError, InventoryRequest, InventoryResult, InventoryScope, InventoryServer} from '../application/inventory-controller';
import {BASE_UNITS, inventoryCommand, stockUnits} from '../domain/inventory';
import type {InventoryCommand, InventoryReport, ProductStock} from '../domain/inventory';
import {taskQuantity} from '../domain/tasks';
import {BoundedHTTP} from './http-transport';
import type {FetchTransport} from './http-transport';
import {csrf, failure} from './http-values';
import type {EntryEndpoint} from './http-values';
import {boolean, check, choice, fields, identifier, integer, text} from './json-values';

const BASE = 'inventory';

function product(value: unknown): ProductStock {
  const row = fields(value, ['product_id','name','base_unit','recorded','reserved','available'], []);
  const unit = choice(row.base_unit, BASE_UNITS), recorded = taskQuantity(row.recorded);
  const reserved = taskQuantity(row.reserved), available = taskQuantity(row.available);
  check(stockUnits(recorded) === stockUnits(reserved) + stockUnits(available));
  check(unit !== 'piece' || [recorded, reserved, available].every(amount => !amount.includes('.')));
  return {id: identifier(row.product_id), name: text(row.name, 160), unit, recorded, reserved, available};
}

function report(value: unknown): InventoryReport {
  const row = fields(value, ['location_id','may_manage','products','next_cursor'], []);
  check(row.location_id === 'pantry' && Array.isArray(row.products) && row.products.length <= 25);
  const products = row.products.map(product);
  check(new Set(products.map(item => item.id)).size === products.length);
  return {mayManage: boolean(row.may_manage), products, cursor: row.next_cursor === null ? null : text(row.next_cursor, 512)};
}

function receipt(value: unknown, command: InventoryCommand): InventoryResult {
  const row = fields(value, ['state','archived_by','operation_id','created_at','result','message','action_required'], []);
  const kind = choice(row.state, ['committed','historical'] as const);
  if (row.archived_by !== null || kind === 'historical') identifier(row.archived_by);
  const operationId = identifier(row.operation_id);
  integer(row.created_at, 0);
  if (command.action === 'inventory.register-product') {
    const result = fields(row.result, ['product_id','name','base_unit'], []);
    check(result.name === command.name && result.base_unit === command.base_unit);
    return {kind, operationId, productId: identifier(result.product_id), intake: null};
  }
  const result = fields(row.result, ['product_id','movement_id','base_unit','quantity'], []);
  const unit = choice(result.base_unit, BASE_UNITS);
  check(result.product_id === command.product_id && result.quantity === command.quantity);
  return {kind, operationId, productId: command.product_id,
    intake: {movementId: identifier(result.movement_id), unit, quantity: command.quantity}};
}

function fault(value: unknown): InventoryError {
  failure(value);
  const {code} = value as {code: InventoryError};
  return INVENTORY_ERRORS.some(known => known === code) ? code : 'rejected';
}

export class HttpInventoryServer implements InventoryServer {
  private readonly network: BoundedHTTP;
  constructor(target: EntryEndpoint, transport: FetchTransport) {this.network = new BoundedHTTP(target, transport);}

  read(scope: InventoryScope, cursor: string | null) {
    return this.network.owned(async signal => {
      const query = new URLSearchParams({limit: '25'});
      if (cursor !== null) query.set('cursor', text(cursor, 512));
      return report(await this.network.get(BASE + '?' + query.toString(), scope.context, signal));
    });
  }

  send(scope: InventoryScope, request: InventoryRequest) {
    return this.network.owned(async (signal): Promise<InventoryResult> => {
      const command = inventoryCommand(request.command);
      const token = csrf(await this.network.get('auth/csrf', scope.context, signal));
      const reply = await this.network.request(BASE + '/commands', 'POST', scope.context, JSON.stringify(command),
        identifier(request.key), token, signal);
      if (reply.status === 200) return receipt(reply.value, command);
      if ([401,403,404,409,422].includes(reply.status)) return {kind: 'rejected', reason: fault(reply.value), command};
      throw new Error('inventory_unavailable');
    });
  }

  original(scope: InventoryScope, request: InventoryRequest) {
    return this.network.owned(async signal => {
      const command = inventoryCommand(request.command);
      const reply = await this.network.request(BASE + '/requests/' + command.action + '/' + identifier(request.key),
        'GET', scope.context, null, null, null, signal);
      if (reply.status === 200) return receipt(reply.value, command);
      failure(reply.value);
      if (reply.status === 404 && (reply.value as {code: unknown}).code === 'operation_missing') return null;
      throw new Error('inventory_unavailable');
    });
  }
}
