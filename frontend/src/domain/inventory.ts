/** Catalog commands and exact base-unit quantities shared by the protected workspace. */
import {taskIdentifier, taskQuantity, taskText} from './tasks';
import {revisionValue} from './administration';
import type {Revision} from './administration';

export const BASE_UNITS = ['piece', 'gram', 'millilitre'] as const;
export type BaseUnit = typeof BASE_UNITS[number];
export type ReplenishmentRevision = Revision | '0';
export type ShoppingAction = 'shopping.purchase' | 'shopping.receive' | 'shopping.post-receipt'
  | 'shopping.return-receipt' | 'shopping.correct-posted-receipt' | 'shopping.void-receipt' | 'shopping.cancel-balance' | 'shopping.add-extra' | 'shopping.clear-extra' | 'shopping.record-session';

export const MIN_SESSION_ITEMS = 2;
export const MAX_SESSION_ITEMS = 16;

export interface SessionSelection {
  readonly product_id: string | null;
  readonly extra_id: string | null;
  readonly quantity: string;
}

export type InventoryCommand =
  | Readonly<{action: 'inventory.register-product'; name: string; base_unit: BaseUnit}>
  | Readonly<{action: 'inventory.intake'; product_id: string; quantity: string}>
  | Readonly<{action: 'inventory.adjust'; product_id: string; quantity: string; reason: string}>
  | Readonly<{action: 'inventory.correct-intake'; product_id: string; movement_id: string; reason: string}>
  | Readonly<{action: 'inventory.configure-replenishment'; product_id: string; minimum: string;
    target: string; expected_revision: ReplenishmentRevision}>
  | Readonly<{action: 'shopping.purchase'; product_id: string | null; name: string | null; quantity: string}>
  | Readonly<{action: 'shopping.add-extra'; product_id: string | null; name: string | null; quantity: string}>
  | Readonly<{action: 'shopping.receive'; purchase_id: string; quantity: string; expected_revision: Revision}>
  | Readonly<{action: 'shopping.cancel-balance'; purchase_id: string; reason: string; expected_revision: Revision}>
  | Readonly<{action: 'shopping.void-receipt'; purchase_id: string; receipt_id: string; reason: string;
    expected_revision: Revision}>
  | Readonly<{action: 'shopping.correct-posted-receipt'; purchase_id: string; receipt_id: string; reason: string;
    expected_revision: Revision}>
  | Readonly<{action: 'shopping.return-receipt'; purchase_id: string; receipt_id: string; reason: string;
    expected_revision: Revision}>
  | Readonly<{action: 'shopping.post-receipt'; purchase_id: string; receipt_id: string}>
  | Readonly<{action: 'shopping.clear-extra'; extra_id: string}>
  | Readonly<{action: 'shopping.record-session'; items: readonly SessionSelection[]}>;

export const MOVEMENT_KINDS = ['intake', 'task_consumption', 'task_correction', 'adjustment', 'intake_correction'] as const;
export type MovementKind = typeof MOVEMENT_KINDS[number];
export const STOCK_REASON_LIMIT = 240;

export interface StockMovement {
  readonly id: string;
  readonly quantity: string;
  readonly kind: MovementKind;
  readonly memberId: string;
  readonly authorAlias: string | null;
  readonly createdAt: string;
  readonly reason: string | null;
  readonly occurrenceId: string | null;
  readonly corrects: string | null;
  readonly correctedBy: string | null;
  readonly shoppingReceipt: boolean;
  readonly returnOf: string | null;
}

export interface MovementHistory {
  readonly productId: string;
  readonly productName: string;
  readonly unit: BaseUnit;
  readonly movements: readonly StockMovement[];
  readonly cursor: string | null;
}

export interface ProductStock {
  readonly id: string;
  readonly referenceId: string;
  readonly name: string;
  readonly unit: BaseUnit;
  readonly recorded: string;
  readonly reserved: string;
  readonly available: string;
  readonly replenishment: Replenishment;
  readonly outstandingPurchase: string;
  readonly shoppingNeeded: string;
}

export interface Replenishment {
  readonly sourceId: string;
  readonly minimum: string;
  readonly target: string;
  readonly revision: ReplenishmentRevision;
  readonly needed: string;
}

export interface InventoryReport {
  readonly mayManage: boolean;
  readonly mayShop: boolean;
  readonly mayRequest: boolean;
  readonly products: readonly ProductStock[];
  readonly cursor: string | null;
}

export interface Purchase {
  readonly id: string;
  readonly productId: string | null;
  readonly name: string;
  readonly unit: BaseUnit;
  readonly purchased: string;
  readonly received: string;
  readonly remaining: string;
  readonly pendingStock: string;
  readonly cancelled: string;
  readonly revision: Revision;
  readonly memberId: string;
  readonly authorAlias: string | null;
  readonly createdAt: string;
}

export interface PhysicalReceiptVoid extends ExtraAttribution {
  readonly reason: string;
}

export interface PostedReceiptCorrection extends PhysicalReceiptVoid {
  readonly movementId: string;
  readonly legacy: boolean;
}

export interface ReceiptReturn extends PhysicalReceiptVoid {
  readonly movementId: string;
}

export interface PhysicalReceipt {
  readonly id: string;
  readonly quantity: string;
  readonly memberId: string;
  readonly authorAlias: string | null;
  readonly createdAt: string;
  readonly movementId: string | null;
  readonly voided: PhysicalReceiptVoid | null;
  readonly correction: PostedReceiptCorrection | null;
  readonly returned: ReceiptReturn | null;
}

export interface Purchases {
  readonly items: readonly Purchase[];
  readonly cursor: string | null;
}

export interface PurchaseCancellation extends ExtraAttribution {
  readonly quantity: string;
  readonly reason: string;
}

export interface PurchaseReceipts {
  readonly purchase: Purchase;
  readonly items: readonly PhysicalReceipt[];
  readonly cancellation: PurchaseCancellation | null;
  readonly cursor: string | null;
}

export interface ExtraAttribution {
  readonly memberId: string;
  readonly authorAlias: string | null;
  readonly createdAt: string;
}

export interface PurchaseSession extends ExtraAttribution {
  readonly id: string;
}

export interface PurchaseSessions {
  readonly items: readonly PurchaseSession[];
  readonly cursor: string | null;
}

export interface PurchaseSessionDetail {
  readonly session: PurchaseSession;
  readonly items: readonly Purchase[];
}

export interface ShoppingItem {
  readonly productId: string | null;
  readonly extraId: string | null;
  readonly name: string;
  readonly unit: BaseUnit;
  readonly pantry: string;
  readonly tasks: string;
  readonly manual: string;
  readonly total: string;
  readonly attribution: ExtraAttribution | null;
}

export interface ShoppingList {
  readonly items: readonly ShoppingItem[];
  readonly cursor: string | null;
}

export const SHOPPING_SOURCE_KINDS = ['pantry','task','extra'] as const;
export interface ShoppingSource {
  readonly id: string;
  readonly kind: typeof SHOPPING_SOURCE_KINDS[number];
  readonly originId: string;
  readonly lineId: string | null;
  readonly name: string;
  readonly quantity: string;
  readonly reserved: string;
  readonly stock: string;
  readonly incoming: string;
  readonly toBuy: string;
  readonly attribution: ExtraAttribution | null;
}

export interface ShoppingSources {
  readonly item: ShoppingItem;
  readonly items: readonly ShoppingSource[];
  readonly cursor: string | null;
}

function hasFields(record: Record<string, unknown>, fields: readonly string[]): boolean {
  return Object.keys(record).length === fields.length && fields.every(key => Object.hasOwn(record, key));
}

export function positiveQuantity(value: unknown): string {
  const quantity = taskQuantity(value);
  if (quantity === '0') throw new Error('invalid_inventory_quantity');
  return quantity;
}

function sessionSelection(value: unknown): SessionSelection {
  if (value === null || typeof value !== 'object' || Array.isArray(value))
    throw new Error('invalid_inventory_command');
  const item = value as Record<string, unknown>;
  if (!hasFields(item, ['product_id','extra_id','quantity']) || (item.product_id === null) === (item.extra_id === null))
    throw new Error('invalid_inventory_command');
  return {product_id:item.product_id === null ? null : taskIdentifier(item.product_id),
    extra_id:item.extra_id === null ? null : taskIdentifier(item.extra_id), quantity:positiveQuantity(item.quantity)};
}

export function inventoryCommand(value: unknown): InventoryCommand {
  if (value === null || typeof value !== 'object' || Array.isArray(value))
    throw new Error('invalid_inventory_command');
  const record = value as Record<string, unknown>;
  const {action} = record;
  if (Object.keys(record).length === 3 && Object.hasOwn(record, 'action')) {
    if (action === 'inventory.register-product' && Object.hasOwn(record, 'name') && Object.hasOwn(record, 'base_unit')) {
      const base_unit = record.base_unit as BaseUnit;
      if (BASE_UNITS.includes(base_unit)) return {action, name: taskText(record.name, 160, true), base_unit};
    }
    if (action === 'inventory.intake' && Object.hasOwn(record, 'product_id') && Object.hasOwn(record, 'quantity')) {
      const quantity = taskQuantity(record.quantity);
      if (quantity !== '0') return {action, product_id: taskIdentifier(record.product_id), quantity};
    }
  }
  if (Object.keys(record).length === 4 && Object.hasOwn(record, 'action')
      && Object.hasOwn(record, 'product_id') && Object.hasOwn(record, 'reason')) {
    if (action === 'inventory.adjust' && Object.hasOwn(record, 'quantity')) {
      return {action, product_id: taskIdentifier(record.product_id), quantity: signedQuantity(record.quantity),
        reason: taskText(record.reason, STOCK_REASON_LIMIT, true)};
    }
    if (action === 'inventory.correct-intake' && Object.hasOwn(record, 'movement_id')) {
      return {action, product_id: taskIdentifier(record.product_id), movement_id: taskIdentifier(record.movement_id),
        reason: taskText(record.reason, STOCK_REASON_LIMIT, true)};
    }
  }
  const policyKeys = ['action', 'product_id', 'minimum', 'target', 'expected_revision'];
  if (action === 'inventory.configure-replenishment' && Object.keys(record).length === policyKeys.length
      && policyKeys.every(key => Object.hasOwn(record, key))) {
    return {action, product_id: taskIdentifier(record.product_id), minimum: taskQuantity(record.minimum),
      target: taskQuantity(record.target), expected_revision: replenishmentRevision(record.expected_revision)};
  }
  if ((action === 'shopping.purchase' || action === 'shopping.add-extra')
      && hasFields(record, ['action','product_id','name','quantity'])) {
    const product_id = record.product_id === null ? null : taskIdentifier(record.product_id);
    const name = record.name === null ? null : taskText(record.name, 160, true);
    if ((product_id === null) !== (name === null))
      return {action, product_id, name, quantity: positiveQuantity(record.quantity)};
  }
  if (action === 'shopping.receive' && hasFields(record, ['action','purchase_id','quantity','expected_revision'])) {
    return {action, purchase_id:taskIdentifier(record.purchase_id), quantity:positiveQuantity(record.quantity),
      expected_revision:revisionValue(record.expected_revision)};
  }
  if (action === 'shopping.cancel-balance' && hasFields(record, ['action','purchase_id','reason','expected_revision'])) {
    return {action, purchase_id:taskIdentifier(record.purchase_id), reason:taskText(record.reason, STOCK_REASON_LIMIT, true),
      expected_revision:revisionValue(record.expected_revision)};
  }
  if ((action === 'shopping.void-receipt' || action === 'shopping.correct-posted-receipt' || action === 'shopping.return-receipt')
      && hasFields(record, ['action','purchase_id','receipt_id','reason','expected_revision'])) {
    return {action, purchase_id:taskIdentifier(record.purchase_id), receipt_id:taskIdentifier(record.receipt_id),
      reason:taskText(record.reason, STOCK_REASON_LIMIT, true), expected_revision:revisionValue(record.expected_revision)};
  }
  if (action === 'shopping.post-receipt' && hasFields(record, ['action','purchase_id','receipt_id'])) {
    return {action, purchase_id:taskIdentifier(record.purchase_id), receipt_id:taskIdentifier(record.receipt_id)};
  }
  if (action === 'shopping.clear-extra' && hasFields(record, ['action','extra_id']))
    return {action, extra_id:taskIdentifier(record.extra_id)};
  if (action === 'shopping.record-session' && hasFields(record, ['action','items']) && Array.isArray(record.items)
      && record.items.length >= MIN_SESSION_ITEMS && record.items.length <= MAX_SESSION_ITEMS) {
    const items = record.items.map(sessionSelection);
    if (new Set(items.map(item => JSON.stringify([item.product_id,item.extra_id]))).size === items.length)
      return {action, items};
  }
  throw new Error('invalid_inventory_command');
}

export function replenishmentRevision(value: unknown): ReplenishmentRevision {
  return value === '0' ? value : revisionValue(value);
}

export function signedQuantity(value: unknown): string {
  const negative = typeof value === 'string' && value.startsWith('-');
  const amount = taskQuantity(negative ? value.slice(1) : value);
  if (amount === '0') throw new Error('invalid_inventory_quantity');
  return negative ? '-' + amount : amount;
}

export function adjustmentQuantity(value: string, unit: BaseUnit): string | null {
  const trimmed = value.trim();
  const quantity = intakeQuantity(trimmed.replace(/^[+-]/u, ''), unit);
  if (quantity === null) return null;
  return trimmed.startsWith('-') ? '-' + quantity : quantity;
}

export function intakeQuantity(value: string, unit: BaseUnit): string | null {
  const quantity = policyQuantity(value, unit);
  return quantity === '0' ? null : quantity;
}

export function policyQuantity(value: string, unit: BaseUnit): string | null {
  const match = /^(0|[1-9][0-9]{0,11})(?:[.,]([0-9]{1,6}))?$/u.exec(value.trim());
  if (match === null || (unit === 'piece' && match[2] !== undefined)) return null;
  const fraction = match[2]?.replace(/0+$/u, '') ?? '';
  return fraction ? match[1] + '.' + fraction : match[1];
}

export function stockUnits(quantity: string): bigint {
  const [whole, fraction = ''] = quantity.split('.');
  return BigInt(whole) * 1_000_000n + BigInt(fraction.padEnd(6, '0'));
}
