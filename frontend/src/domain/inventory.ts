/** Catalog commands and exact base-unit quantities shared by the protected workspace. */
import {taskIdentifier, taskQuantity, taskText} from './tasks';
import {revisionValue} from './administration';
import type {Revision} from './administration';

export const BASE_UNITS = ['piece', 'gram', 'millilitre'] as const;
export type BaseUnit = typeof BASE_UNITS[number];
export type ReplenishmentRevision = Revision | '0';

export type InventoryCommand =
  | Readonly<{action: 'inventory.register-product'; name: string; base_unit: BaseUnit}>
  | Readonly<{action: 'inventory.intake'; product_id: string; quantity: string}>
  | Readonly<{action: 'inventory.adjust'; product_id: string; quantity: string; reason: string}>
  | Readonly<{action: 'inventory.correct-intake'; product_id: string; movement_id: string; reason: string}>
  | Readonly<{action: 'inventory.configure-replenishment'; product_id: string; minimum: string;
    target: string; expected_revision: ReplenishmentRevision}>;

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
  readonly name: string;
  readonly unit: BaseUnit;
  readonly recorded: string;
  readonly reserved: string;
  readonly available: string;
  readonly replenishment: Replenishment;
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
  readonly products: readonly ProductStock[];
  readonly cursor: string | null;
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
