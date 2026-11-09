import {ALLOCATION_MODES, SHARE_ROUNDINGS, allocationFingerprint} from '../domain/point-allocation';
import type {AllocationEvidence, AllocationPolicy, AllocationPreview, AllocationShare} from '../domain/point-allocation';
import {boolean, check, choice, fields, identifier, integer, responseNonnegativeRevision} from './json-values';

export function allocationPolicy(value: unknown): AllocationPolicy {
  const row = fields(value, ['mode', 'precision', 'rounding'], []);
  const mode = choice(row.mode, ALLOCATION_MODES);
  const precision = typeof row.precision === 'number' ? row.precision : integer(row.precision, 0);
  check(precision === 0 || precision === 2);
  const rounding = row.rounding === null ? null : choice(row.rounding, SHARE_ROUNDINGS);
  check((mode === 'equal_share') === (rounding !== null));
  return {mode, precision, rounding};
}

export function allocationShares(value: unknown, total: number): readonly AllocationShare[] {
  check(Array.isArray(value) && value.length >= 1 && value.length <= 32);
  const shares = value.map((row): AllocationShare => {
    check(Array.isArray(row) && row.length === 2);
    const amount = integer(row[1], 0); check(amount <= 1_000_000);
    return [identifier(row[0]), amount];
  });
  check(new Set(shares.map(row => row[0])).size === shares.length && shares.reduce((sum, row) => sum + row[1], 0) === total);
  return shares;
}

export function allocationEvidence(value: unknown): AllocationEvidence {
  const row = fields(value, ['mode', 'precision', 'rounding', 'policy_revision', 'task_override', 'base_minor', 'total_minor', 'shares'], []);
  const policy = allocationPolicy({mode: row.mode, precision: row.precision, rounding: row.rounding});
  const total = integer(row.total_minor, 0);
  return {...policy, policyRevision: responseNonnegativeRevision(row.policy_revision), taskOverride: boolean(row.task_override),
    base: integer(row.base_minor, 0), total, shares: allocationShares(row.shares, total)};
}

export function allocationPreview(value: unknown, performers: readonly string[]): AllocationPreview {
  const row = fields(value, ['allocation', 'actual_total', 'fingerprint'], []);
  const allocation = allocationEvidence(row.allocation);
  check(integer(row.actual_total, 0) === allocation.total && allocation.shares.length === performers.length
    && allocation.shares.every(([id]) => performers.includes(id)));
  return {...allocation, fingerprint: allocationFingerprint(row.fingerprint)};
}
