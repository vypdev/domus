/** Bounded same-origin Inventory reads and exact original-command recovery. */
import {INVENTORY_ERRORS} from '../application/inventory-controller';
import type {InventoryError, InventoryRequest, InventoryResult, InventoryScope, InventoryServer} from '../application/inventory-controller';
import type {StockAttention} from '../application/stock-attention';
import {BASE_UNITS, MAX_LOCATION_NAME, MAX_NAMED_LOCATIONS, MAX_SESSION_ITEMS, MIN_SESSION_ITEMS, MOVEMENT_KINDS, SHOPPING_SOURCE_KINDS, STOCK_REASON_LIMIT, inventoryCommand, positiveQuantity, purchaseStoreName, replenishmentRevision, signedQuantity, stockUnits} from '../domain/inventory';
import type {BaseUnit, InventoryCommand, InventoryReport, LocationStock, MovementHistory, ProductStock, Purchase, PurchaseCancellation, Purchases, PurchaseReceipts, PurchaseSession, PurchaseSessionDetail, PurchaseSessions, Replenishment, ShoppingItem, ShoppingList, ShoppingSource, ShoppingSources, StockMovement, StockTotals, StockTransfer, StorageLocation} from '../domain/inventory';
import type {JournalContext} from '../domain/journal';
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
  const row = fields(value, ['product_id','reference_id','name','base_unit','recorded','reserved','available',
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
  return {id, referenceId:identifier(row.reference_id), name: text(row.name, 160), unit, recorded, reserved, available,
    replenishment:policy, outstandingPurchase, shoppingNeeded};
}

function namedLocation(value: unknown): StorageLocation {
  const row = fields(value, ['location_id','name'], []);
  const id = identifier(row.location_id);
  check(id !== 'pantry');
  return {id, name:text(row.name, MAX_LOCATION_NAME)};
}

function report(value: unknown): InventoryReport {
  const row = fields(value, ['location_id','may_manage','may_shop','may_request','products','next_cursor','locations'], []);
  check(row.location_id === 'pantry' && Array.isArray(row.products) && row.products.length <= 25);
  check(Array.isArray(row.locations) && row.locations.length <= MAX_NAMED_LOCATIONS);
  const locations = row.locations.map(namedLocation);
  check(new Set(locations.map(item => item.id)).size === locations.length);
  const products = row.products.map(product);
  check(new Set(products.map(item => item.id)).size === products.length);
  return {mayManage: boolean(row.may_manage), mayShop:boolean(row.may_shop), mayRequest:boolean(row.may_request), products,
    cursor: cursorValue(row.next_cursor), locations};
}

function stockAttention(value: unknown): StockAttention {
  const group = fields(value, ['total', 'items'], []);
  const total = integer(group.total, 0);
  check(Array.isArray(group.items) && group.items.length === Math.min(total, 25));
  const items = group.items.map(value => {
    const row = fields(value, ['product_id', 'name', 'base_unit', 'available', 'minimum'], []);
    const unit = choice(row.base_unit, BASE_UNITS), available = taskQuantity(row.available);
    const minimum = taskQuantity(row.minimum);
    check(stockUnits(available) < stockUnits(minimum)
      && (unit !== 'piece' || (!available.includes('.') && !minimum.includes('.'))));
    return {id:identifier(row.product_id), name:text(row.name, 160), unit, available, minimum};
  });
  check(new Set(items.map(item => item.id)).size === items.length);
  return {total, items};
}

function nullableId(value: unknown): string | null {return value === null ? null : identifier(value);}
function cursorValue(value: unknown): string | null {return value === null ? null : text(value, 512);}

function attribution(row: Record<string, unknown>) {
  return {memberId:identifier(row.member_id),
    authorAlias:row.author_alias === null ? null : text(row.author_alias, 80), createdAt:taskTime(row.created_at)};
}

function transfer(row: Record<string, unknown>): StockTransfer {
  const source = identifier(row.source_location), destination = identifier(row.destination_location);
  const withdrawalId = identifier(row.withdrawal_id), depositId = identifier(row.deposit_id);
  check(source !== destination && withdrawalId !== depositId);
  return {id:identifier(row.transfer_id), productId:identifier(row.product_id),
    source, destination, withdrawalId, depositId};
}

const TRANSFER_FIELDS = ['transfer_id','product_id','source_location','destination_location',
  'withdrawal_id','deposit_id'];

function movement(value: unknown): StockMovement {
  const row = fields(value, ['movement_id','quantity','kind','member_id','author_alias','created_at',
    'reason','task_occurrence_id','corrects','corrected_by','shopping_receipt','return_of','transfer'], []);
  const id = identifier(row.movement_id), quantity = signedQuantity(row.quantity), kind = choice(row.kind, MOVEMENT_KINDS);
  const linked = row.transfer === null ? null : transfer(fields(row.transfer, TRANSFER_FIELDS, []));
  check((kind === 'transfer') === (linked !== null));
  if (linked) check(id === (quantity.startsWith('-') ? linked.withdrawalId : linked.depositId));
  return {
    id, quantity, kind,
    ...attribution(row), reason: row.reason === null ? null : text(row.reason, STOCK_REASON_LIMIT),
    occurrenceId: nullableId(row.task_occurrence_id), corrects: nullableId(row.corrects), correctedBy: nullableId(row.corrected_by),
    shoppingReceipt:boolean(row.shopping_receipt), returnOf:nullableId(row.return_of), transfer:linked,
  };
}

const STOCK_FIELDS = ['recorded','reserved','available'] as const;

function stockTotals(value: unknown, unit: BaseUnit, parse: (value: unknown) => string): StockTotals {
  const row = fields(value, STOCK_FIELDS, []);
  const recorded = parse(row.recorded), reserved = parse(row.reserved), available = parse(row.available);
  check(stockUnits(recorded) === stockUnits(reserved) + stockUnits(available));
  check(unit !== 'piece' || [recorded, reserved, available].every(amount => !amount.includes('.')));
  return {recorded, reserved, available};
}

function aggregateQuantity(value: unknown): string {
  check(typeof value === 'string' && /^(?:0|[1-9][0-9]{0,13})(?:\.[0-9]{0,5}[1-9])?$/u.test(value));
  return value;
}

function locationStock(value: unknown, unit: BaseUnit): LocationStock {
  const row = fields(value, ['location_id','name','stock'], []);
  const id = identifier(row.location_id);
  check((id === 'pantry') === (row.name === null));
  return {id, name:row.name === null ? null : text(row.name, MAX_LOCATION_NAME),
    stock:stockTotals(row.stock, unit, taskQuantity)};
}

function history(value: unknown, productId: string): MovementHistory {
  const row = fields(value, ['product_id','product_name','base_unit','movements','next_cursor','locations','total'], []);
  check(row.product_id === productId && Array.isArray(row.movements) && row.movements.length <= 25);
  check(Array.isArray(row.locations) && row.locations.length > 0 && row.locations.length <= MAX_NAMED_LOCATIONS + 1);
  const unit = choice(row.base_unit, BASE_UNITS);
  const locations = row.locations.map(item => locationStock(item, unit));
  const locationIds = new Set(locations.map(item => item.id));
  check(locationIds.size === locations.length && locationIds.has('pantry'));
  const total = stockTotals(row.total, unit, aggregateQuantity);
  check(STOCK_FIELDS.every(key => stockUnits(total[key]) ===
    locations.reduce((sum, location) => sum + stockUnits(location.stock[key]), 0n)));
  const movements = row.movements.map(movement);
  check(new Set(movements.map(item => item.id)).size === movements.length);
  check(movements.every(({transfer}) => transfer === null ||
    (transfer.productId === productId && locationIds.has(transfer.source) && locationIds.has(transfer.destination))));
  return {productId, productName: text(row.product_name, 160), unit, movements, locations, total,
    cursor: cursorValue(row.next_cursor)};
}

function purchase(value: unknown): Purchase {
  const row = fields(value, ['purchase_id','product_id','name','base_unit','purchased','received','remaining',
    'pending_stock','cancelled','revision','member_id','author_alias','created_at'], []);
  const productId = nullableId(row.product_id), unit = choice(row.base_unit, BASE_UNITS);
  const purchased = positiveQuantity(row.purchased), received = taskQuantity(row.received);
  const remaining = taskQuantity(row.remaining), pendingStock = taskQuantity(row.pending_stock);
  const cancelled = taskQuantity(row.cancelled);
  check(stockUnits(purchased) === stockUnits(received) + stockUnits(remaining) + stockUnits(cancelled));
  check(cancelled === '0' || remaining === '0');
  check(stockUnits(pendingStock) <= stockUnits(received));
  check(productId !== null || (unit === 'piece' && pendingStock === '0'));
  check(unit !== 'piece' || [purchased, received, remaining, pendingStock, cancelled].every(amount => !amount.includes('.')));
  return {id:identifier(row.purchase_id), productId, name:text(row.name, 160), unit, purchased, received, remaining,
    pendingStock, cancelled, revision:revisionValue(row.revision), ...attribution(row)};
}

function purchases(value: unknown): Purchases {
  const row = fields(value, ['purchases','next_cursor'], []);
  check(Array.isArray(row.purchases) && row.purchases.length <= 25);
  const items = row.purchases.map(purchase);
  check(new Set(items.map(item => item.id)).size === items.length);
  return {items, cursor:cursorValue(row.next_cursor)};
}

function cancellation(value: unknown): PurchaseCancellation | null {
  if (value === null) return null;
  const row = fields(value, ['quantity','reason','member_id','author_alias','created_at'], []);
  return {quantity:positiveQuantity(row.quantity), reason:text(row.reason, STOCK_REASON_LIMIT), ...attribution(row)};
}

function purchaseReceipts(value: unknown, purchaseId: string): PurchaseReceipts {
  const row = fields(value, ['purchase','receipts','cancellation','next_cursor'], []);
  const selected = purchase(row.purchase);
  check(selected.id === purchaseId && Array.isArray(row.receipts) && row.receipts.length <= 25);
  const items = row.receipts.map(value => {
    const entry = fields(value, ['receipt_id','quantity','member_id','author_alias','created_at','movement_id','voided','correction','returned'], []);
    const movementId = nullableId(entry.movement_id);
    let voided = null;
    if (entry.voided !== null) {
      check(selected.productId !== null && movementId === null);
      const correction = fields(entry.voided, ['reason','member_id','author_alias','created_at'], []);
      voided = {reason:text(correction.reason, STOCK_REASON_LIMIT), ...attribution(correction)};
    }
    let correction = null;
    if (entry.correction !== null) {
      check(selected.productId !== null && movementId !== null);
      const row = fields(entry.correction, ['movement_id','reason','member_id','author_alias','created_at','legacy'], []);
      const correctionId = identifier(row.movement_id);
      check(correctionId !== movementId);
      correction = {movementId:correctionId, reason:text(row.reason, STOCK_REASON_LIMIT),
        ...attribution(row), legacy:boolean(row.legacy)};
    }
    let returned = null;
    if (entry.returned !== null) {
      check(selected.productId !== null && movementId !== null && correction === null);
      const row = fields(entry.returned, ['movement_id','reason','member_id','author_alias','created_at'], []);
      const returnId = identifier(row.movement_id);
      check(returnId !== movementId);
      returned = {movementId:returnId, reason:text(row.reason, STOCK_REASON_LIMIT), ...attribution(row)};
    }
    return {id:identifier(entry.receipt_id), quantity:positiveQuantity(entry.quantity), ...attribution(entry),
      movementId, voided, correction, returned};
  });
  check(new Set(items.map(item => item.id)).size === items.length);
  const balance = cancellation(row.cancellation);
  check((balance?.quantity ?? '0') === selected.cancelled);
  return {purchase:selected, items, cancellation:balance, cursor:cursorValue(row.next_cursor)};
}

function purchaseSession(value: unknown): PurchaseSession {
  const row = fields(value, ['session_id','member_id','author_alias','created_at'], ['store_name']);
  const storeName = row.store_name == null ? null : purchaseStoreName(row.store_name);
  return {id:identifier(row.session_id), storeName, ...attribution(row)};
}

function purchaseSessions(value: unknown): PurchaseSessions {
  const row = fields(value, ['sessions','next_cursor'], []);
  check(Array.isArray(row.sessions) && row.sessions.length <= 25);
  const items = row.sessions.map(purchaseSession);
  check(new Set(items.map(item => item.id)).size === items.length);
  return {items, cursor:cursorValue(row.next_cursor)};
}

function purchaseSessionDetail(value: unknown, id: string): PurchaseSessionDetail {
  const row = fields(value, ['session','items'], []);
  const session = purchaseSession(row.session);
  check(session.id === id && Array.isArray(row.items)
    && row.items.length >= MIN_SESSION_ITEMS && row.items.length <= MAX_SESSION_ITEMS);
  const items = row.items.map(purchase);
  check(new Set(items.map(item => item.id)).size === items.length);
  check(items.every(item => item.memberId === session.memberId && item.createdAt === session.createdAt));
  return {session, items};
}

function shoppingAmount(value: unknown, unit: BaseUnit): string {
  const amount = text(value, 39);
  check(/^(0|[1-9][0-9]{0,31})(?:\.[0-9]{0,5}[1-9])?$/u.test(amount));
  check(unit !== 'piece' || !amount.includes('.'));
  return amount;
}

function extraAttribution(value: unknown) {
  return value === null ? null : attribution(fields(value, ['member_id','author_alias','created_at'], []));
}

function shoppingItem(value: unknown): ShoppingItem {
  const row = fields(value, ['product_id','extra_id','name','base_unit','pantry','tasks','manual','total','attribution'], []);
  const productId = nullableId(row.product_id), extraId = nullableId(row.extra_id), unit = choice(row.base_unit, BASE_UNITS);
  const pantry = shoppingAmount(row.pantry, unit), tasks = shoppingAmount(row.tasks, unit);
  const manual = shoppingAmount(row.manual, unit), total = shoppingAmount(row.total, unit);
  const author = extraAttribution(row.attribution);
  check(stockUnits(total) === stockUnits(pantry) + stockUnits(tasks) + stockUnits(manual));
  check(productId === null ? extraId !== null && author !== null && unit === 'piece'
    && pantry === '0' && tasks === '0' && manual !== '0' : extraId === null && author === null);
  return {productId, extraId, name:text(row.name, 160), unit, pantry, tasks, manual, total, attribution:author};
}

function shoppingList(value: unknown): ShoppingList {
  const row = fields(value, ['items','next_cursor'], []);
  check(Array.isArray(row.items) && row.items.length <= 25);
  const items = row.items.map(shoppingItem);
  check(new Set(items.map(item => item.productId === null ? 'extra:' + item.extraId : 'product:' + item.productId)).size === items.length);
  return {items, cursor:cursorValue(row.next_cursor)};
}

function shoppingSource(value: unknown, unit: BaseUnit): ShoppingSource {
  const row = fields(value, ['source_id','kind','origin_id','line_id','name','quantity','reserved',
    'stock','incoming','to_buy','attribution'], []);
  const kind = choice(row.kind, SHOPPING_SOURCE_KINDS), lineId = nullableId(row.line_id);
  const quantity = shoppingAmount(row.quantity, unit), reserved = shoppingAmount(row.reserved, unit);
  const stock = shoppingAmount(row.stock, unit), incoming = shoppingAmount(row.incoming, unit);
  const toBuy = shoppingAmount(row.to_buy, unit), author = extraAttribution(row.attribution);
  check(stockUnits(quantity) === stockUnits(reserved) + stockUnits(stock) + stockUnits(incoming) + stockUnits(toBuy));
  check((kind === 'task') === (lineId !== null));
  check((kind === 'extra') === (author !== null));
  return {id:identifier(row.source_id), kind, originId:identifier(row.origin_id), lineId, name:text(row.name, 160),
    quantity, reserved, stock, incoming, toBuy, attribution:author};
}

function shoppingSources(value: unknown, productId: string): ShoppingSources {
  const row = fields(value, ['item','sources','next_cursor'], []);
  const item = shoppingItem(row.item);
  check(item.productId === productId && Array.isArray(row.sources) && row.sources.length <= 25);
  const items = row.sources.map(source => shoppingSource(source, item.unit));
  check(new Set(items.map(source => source.id)).size === items.length);
  return {item, items, cursor:cursorValue(row.next_cursor)};
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
  if (command.action === 'shopping.void-receipt' || command.action === 'shopping.correct-posted-receipt'
      || command.action === 'shopping.return-receipt') {
    const keys = ['purchase_id','receipt_id','quantity','revision'];
    if (command.action !== 'shopping.void-receipt') keys.push('movement_id');
    const result = fields(row.result, keys, []);
    if (command.action !== 'shopping.void-receipt') identifier(result.movement_id);
    check(result.purchase_id === command.purchase_id && result.receipt_id === command.receipt_id);
    check(taskQuantity(result.quantity) !== '0');
    check(BigInt(revisionValue(result.revision)) === BigInt(command.expected_revision) + 1n);
    return {kind, operationId, productId:null, movement:null, shoppingAction:command.action};
  }
  if (command.action === 'shopping.cancel-balance') {
    const result = fields(row.result, ['purchase_id','cancelled','revision'], []);
    check(result.purchase_id === command.purchase_id);
    check(taskQuantity(result.cancelled) !== '0');
    check(BigInt(revisionValue(result.revision)) === BigInt(command.expected_revision) + 1n);
    return {kind, operationId, productId:null, movement:null, shoppingAction:command.action};
  }
  if (command.action === 'shopping.record-session') {
    const result = fields(row.result, ['session_id','purchase_ids'], ['store_name']);
    check(result.store_name === command.store_name);
    check(Array.isArray(result.purchase_ids) && result.purchase_ids.length === command.items.length);
    check(new Set(result.purchase_ids.map(identifier)).size === command.items.length);
    return {kind, operationId, productId:null, movement:null, shoppingAction:command.action,
      sessionId:identifier(result.session_id)};
  }
  if (command.action === 'shopping.add-extra' || command.action === 'shopping.clear-extra') {
    const extra = identifier(fields(row.result, ['extra_id'], []).extra_id);
    if (command.action === 'shopping.clear-extra') check(extra === command.extra_id);
    return {kind, operationId, productId:null, movement:null, shoppingAction:command.action};
  }
  if (command.action === 'inventory.add-location') {
    const location = namedLocation(row.result);
    check(location.name === command.name);
    return {kind, operationId, productId:null, movement:null, locationSaved:true};
  }
  if (command.action === 'inventory.transfer') {
    const result = fields(row.result, [...TRANSFER_FIELDS,'base_unit','quantity'], []);
    const linked = transfer(result), quantity = positiveQuantity(result.quantity);
    check(linked.productId === command.product_id && linked.source === command.source_location
      && linked.destination === command.destination_location && quantity === command.quantity);
    return {kind, operationId, productId:linked.productId,
      movement:{movementId:linked.withdrawalId, unit:choice(result.base_unit, BASE_UNITS), quantity, action:command.action}};
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

  stockAttention(context: JournalContext) {
    return this.network.owned(async signal => stockAttention(await this.network.get(BASE + '/stock-attention', context, signal)));
  }

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

  purchaseSessions(scope: InventoryScope, cursor: string | null) {
    return this.network.owned(async signal => {
      return purchaseSessions(await this.network.get(BASE + '/purchase-sessions' + pageQuery(cursor), scope.context, signal));
    });
  }

  purchaseSession(scope: InventoryScope, sessionId: string) {
    return this.network.owned(async signal => {
      const route = BASE + '/purchase-sessions/' + identifier(sessionId);
      return purchaseSessionDetail(await this.network.get(route, scope.context, signal), sessionId);
    });
  }

  shoppingList(scope: InventoryScope, cursor: string | null) {
    return this.network.owned(async signal => {
      return shoppingList(await this.network.get(BASE + '/shopping-list' + pageQuery(cursor), scope.context, signal));
    });
  }

  shoppingSources(scope: InventoryScope, productId: string, cursor: string | null) {
    return this.network.owned(async signal => {
      const route = BASE + '/shopping-list/' + identifier(productId) + '/sources' + pageQuery(cursor);
      return shoppingSources(await this.network.get(route, scope.context, signal), productId);
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
