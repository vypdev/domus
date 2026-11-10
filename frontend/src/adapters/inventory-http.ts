/** Bounded same-origin Inventory reads and exact original-command recovery. */
import {INVENTORY_ERRORS} from '../application/inventory-controller';
import type {InventoryError, InventoryRequest, InventoryResult, InventoryScope, InventoryServer} from '../application/inventory-controller';
import {BASE_UNITS, MOVEMENT_KINDS, STOCK_REASON_LIMIT, inventoryCommand, positiveQuantity, replenishmentRevision, signedQuantity, stockUnits} from '../domain/inventory';
import type {InventoryCommand, InventoryReport, MovementHistory, ProductStock, Purchase, Purchases, PurchaseReceipts, Replenishment, StockMovement} from '../domain/inventory';
import {revisionValue} from '../domain/administration';
import {taskQuantity, taskTime} from '../domain/tasks';
import {BoundedHTTP} from './http-transport';
import type {FetchTransport} from './http-transport';
import {csrf, failure} from './http-values';
import type {EntryEndpoint} from './http-values';
import {boolean, check, choice, fields, identifier, integer, text} from './json-values';

const BASE = 'inventory';

function replenishment(value: unknown, id: string, unit: ProductStock['unit'], available: string): Replenishment {
  const row = fields(value, ['source_id','minimum','target','revision','needed'], []);
  const minimum = taskQuantity(row.minimum), target = taskQuantity(row.target), needed = taskQuantity(row.needed);
  const revision = replenishmentRevision(row.revision);
  const minimumUnits = stockUnits(minimum), targetUnits = stockUnits(target), availableUnits = stockUnits(available);
  check(row.source_id === id);
  check(minimumUnits <= targetUnits);
  check(revision !== '0' || (minimum === '0' && target === '0'));
  check(unit !== 'piece' || [minimum, target].every(amount => !amount.includes('.')));
  check(stockUnits(needed) === (availableUnits < minimumUnits ? targetUnits - availableUnits : 0n));
  return {sourceId:id, minimum, target, revision, needed};
}

function product(value: unknown): ProductStock {
  const row = fields(value, ['product_id','name','base_unit','recorded','reserved','available',
    'replenishment','outstanding_purchase','shopping_needed'], []);
  const id = identifier(row.product_id);
  const unit = choice(row.base_unit, BASE_UNITS), recorded = taskQuantity(row.recorded);
  const reserved = taskQuantity(row.reserved), available = taskQuantity(row.available);
  check(stockUnits(recorded) === stockUnits(reserved) + stockUnits(available));
  check(unit !== 'piece' || [recorded, reserved, available].every(amount => !amount.includes('.')));
  const policy = replenishment(row.replenishment, id, unit, available);
  const outstandingPurchase = taskQuantity(row.outstanding_purchase), shoppingNeeded = taskQuantity(row.shopping_needed);
  const gap = stockUnits(policy.needed) - stockUnits(outstandingPurchase);
  check(stockUnits(shoppingNeeded) === (gap < 0n ? 0n : gap));
  check(unit !== 'piece' || !outstandingPurchase.includes('.'));
  return {id, name: text(row.name, 160), unit, recorded, reserved, available,
    replenishment:policy, outstandingPurchase, shoppingNeeded};
}

function report(value: unknown): InventoryReport {
  const row = fields(value, ['location_id','may_manage','may_shop','products','next_cursor'], []);
  check(row.location_id === 'pantry' && Array.isArray(row.products) && row.products.length <= 25);
  const products = row.products.map(product);
  check(new Set(products.map(item => item.id)).size === products.length);
  return {mayManage: boolean(row.may_manage), mayShop:boolean(row.may_shop), products,
    cursor: cursorValue(row.next_cursor)};
}

function nullableId(value: unknown): string | null {return value === null ? null : identifier(value);}
function cursorValue(value: unknown): string | null {return value === null ? null : text(value, 512);}

function attribution(row: Record<string, unknown>) {
  return {memberId:identifier(row.member_id),
    authorAlias:row.author_alias === null ? null : text(row.author_alias, 80), createdAt:taskTime(row.created_at)};
}

function movement(value: unknown): StockMovement {
  const row = fields(value, ['movement_id','quantity','kind','member_id','author_alias','created_at',
    'reason','task_occurrence_id','corrects','corrected_by'], []);
  return {
    id: identifier(row.movement_id), quantity: signedQuantity(row.quantity), kind: choice(row.kind, MOVEMENT_KINDS),
    ...attribution(row), reason: row.reason === null ? null : text(row.reason, STOCK_REASON_LIMIT),
    occurrenceId: nullableId(row.task_occurrence_id), corrects: nullableId(row.corrects), correctedBy: nullableId(row.corrected_by),
  };
}

function history(value: unknown, productId: string): MovementHistory {
  const row = fields(value, ['product_id','product_name','base_unit','movements','next_cursor'], []);
  check(row.product_id === productId && Array.isArray(row.movements) && row.movements.length <= 25);
  const movements = row.movements.map(movement);
  check(new Set(movements.map(item => item.id)).size === movements.length);
  return {productId, productName: text(row.product_name, 160), unit: choice(row.base_unit, BASE_UNITS),
    movements, cursor: cursorValue(row.next_cursor)};
}

function purchase(value: unknown): Purchase {
  const row = fields(value, ['purchase_id','product_id','name','base_unit','purchased','received','remaining',
    'pending_stock','revision','member_id','author_alias','created_at'], []);
  const productId = nullableId(row.product_id), unit = choice(row.base_unit, BASE_UNITS);
  const purchased = positiveQuantity(row.purchased), received = taskQuantity(row.received);
  const remaining = taskQuantity(row.remaining), pendingStock = taskQuantity(row.pending_stock);
  check(stockUnits(purchased) === stockUnits(received) + stockUnits(remaining));
  check(stockUnits(pendingStock) <= stockUnits(received));
  check(productId !== null || (unit === 'piece' && pendingStock === '0'));
  check(unit !== 'piece' || [purchased, received, remaining, pendingStock].every(amount => !amount.includes('.')));
  return {id:identifier(row.purchase_id), productId, name:text(row.name, 160), unit, purchased, received, remaining,
    pendingStock, revision:revisionValue(row.revision), ...attribution(row)};
}

function purchases(value: unknown): Purchases {
  const row = fields(value, ['purchases','next_cursor'], []);
  check(Array.isArray(row.purchases) && row.purchases.length <= 25);
  const items = row.purchases.map(purchase);
  check(new Set(items.map(item => item.id)).size === items.length);
  return {items, cursor:cursorValue(row.next_cursor)};
}

function purchaseReceipts(value: unknown, purchaseId: string): PurchaseReceipts {
  const row = fields(value, ['purchase','receipts','next_cursor'], []);
  const selected = purchase(row.purchase);
  check(selected.id === purchaseId && Array.isArray(row.receipts) && row.receipts.length <= 25);
  const items = row.receipts.map(value => {
    const entry = fields(value, ['receipt_id','quantity','member_id','author_alias','created_at','movement_id'], []);
    return {id:identifier(entry.receipt_id), quantity:positiveQuantity(entry.quantity), ...attribution(entry),
      movementId:nullableId(entry.movement_id)};
  });
  check(new Set(items.map(item => item.id)).size === items.length);
  return {purchase:selected, items, cursor:cursorValue(row.next_cursor)};
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
    return {kind, operationId, productId: identifier(result.product_id), movement: null};
  }
  if (command.action === 'inventory.configure-replenishment') {
    const result = fields(row.result, ['product_id','minimum','target','revision'], []);
    check(result.product_id === command.product_id && result.minimum === command.minimum && result.target === command.target);
    check(BigInt(replenishmentRevision(result.revision)) === BigInt(command.expected_revision) + 1n);
    return {kind, operationId, productId: command.product_id, movement: null, replenishmentSaved:true};
  }
  if (command.action === 'shopping.purchase' || command.action === 'shopping.receive' || command.action === 'shopping.post-receipt') {
    const keys = command.action === 'shopping.purchase' ? ['purchase_id']
      : command.action === 'shopping.receive' ? ['purchase_id','receipt_id'] : ['purchase_id','receipt_id','movement_id'];
    const result = fields(row.result, keys, []);
    const purchaseId = identifier(result.purchase_id);
    if (command.action !== 'shopping.purchase') {
      check(purchaseId === command.purchase_id);
      identifier(result.receipt_id);
    }
    if (command.action === 'shopping.post-receipt') {
      check(result.receipt_id === command.receipt_id);
      identifier(result.movement_id);
    }
    return {kind, operationId, productId:null, movement:null, shoppingAction:command.action};
  }
  const action = command.action;
  const result = fields(row.result, ['product_id','movement_id','base_unit','quantity'],
    action === 'inventory.intake' ? [] : ['corrects']);
  const unit = choice(result.base_unit, BASE_UNITS), quantity = signedQuantity(result.quantity);
  check(result.product_id === command.product_id);
  if (action === 'inventory.correct-intake') {
    check(result.corrects === command.movement_id && quantity.startsWith('-'));
  } else {
    check(result.quantity === command.quantity);
    if (action === 'inventory.adjust') check(result.corrects === null);
  }
  return {kind, operationId, productId: command.product_id,
    movement: {movementId: identifier(result.movement_id), unit, quantity, action}};
}

function fault(value: unknown): InventoryError {
  failure(value);
  const {code} = value as {code: InventoryError};
  return INVENTORY_ERRORS.some(known => known === code) ? code : 'rejected';
}

function pageQuery(cursor: string | null): string {
  const query = new URLSearchParams({limit:'25'});
  if (cursor !== null) query.set('cursor', text(cursor, 512));
  return '?' + query.toString();
}

export class HttpInventoryServer implements InventoryServer {
  private readonly network: BoundedHTTP;
  constructor(target: EntryEndpoint, transport: FetchTransport) {this.network = new BoundedHTTP(target, transport);}

  read(scope: InventoryScope, cursor: string | null) {
    return this.network.owned(async signal => {
      return report(await this.network.get(BASE + pageQuery(cursor), scope.context, signal));
    });
  }

  history(scope: InventoryScope, productId: string, cursor: string | null) {
    return this.network.owned(async signal => {
      const route = BASE + '/products/' + identifier(productId) + '/movements' + pageQuery(cursor);
      return history(await this.network.get(route, scope.context, signal), productId);
    });
  }

  purchases(scope: InventoryScope, cursor: string | null) {
    return this.network.owned(async signal => {
      return purchases(await this.network.get(BASE + '/purchases' + pageQuery(cursor), scope.context, signal));
    });
  }

  purchaseReceipts(scope: InventoryScope, purchaseId: string, cursor: string | null) {
    return this.network.owned(async signal => {
      const route = BASE + '/purchases/' + identifier(purchaseId) + '/receipts' + pageQuery(cursor);
      return purchaseReceipts(await this.network.get(route, scope.context, signal), purchaseId);
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
