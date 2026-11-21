import type {DraftCondition} from '../application/automation-drafts';
import {check, choice, fields, identifier} from './json-values';

export function draftCondition(value: unknown): DraftCondition | null {
  let nodes = 2; // Trigger and task are also part of the closed rule's 64-node limit.
  const read = (input: unknown, depth: number): DraftCondition => {
    check(depth <= 8 && ++nodes <= 64);
    const row = fields(input, ['kind'], ['child', 'children', 'product_id']);
    switch (choice(row.kind, ['stock_below_minimum', 'not', 'all', 'any'] as const)) {
      case 'stock_below_minimum':
        return {kind: 'stock_below_minimum', product_id: identifier(fields(row, ['kind', 'product_id'], []).product_id)};
      case 'not':
        return {kind: 'not', child: read(fields(row, ['kind', 'child'], []).child, depth + 1)};
      case 'all':
      case 'any': {
        const {children} = fields(row, ['kind', 'children'], []);
        check(Array.isArray(children) && children.length > 0 && children.length <= 62);
        return {kind: row.kind as 'all' | 'any', children: children.map(child => read(child, depth + 1))};
      }
    }
  };
  return value === null ? null : read(value, 1);
}
