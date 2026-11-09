/** Exact minor points and the closed policy choices shared by the Family and Tasks views. */
import type {Revision} from './administration';

export const ALLOCATION_MODES = ['conserve_total', 'equal_share', 'full_per_participant', 'manual'] as const;
export const SHARE_ROUNDINGS = ['floor', 'ceil', 'half_up'] as const;
export type AllocationMode = typeof ALLOCATION_MODES[number];
export type ShareRounding = typeof SHARE_ROUNDINGS[number];
export type AllocationPolicy = Readonly<{mode: AllocationMode; precision: 0 | 2; rounding: ShareRounding | null}>;
export type ManualShare = Readonly<{member_id: string; amount_minor: number}>;
export type AllocationShare = readonly [memberId: string, amountMinor: number];
export interface AllocationEvidence extends AllocationPolicy {
  readonly policyRevision: Revision | '0';
  readonly taskOverride: boolean;
  readonly base: number;
  readonly total: number;
  readonly shares: readonly AllocationShare[];
}

export function minorPoints(value: string): number | null {
  const parts = /^([0-9]{1,5})(?:[.,]([0-9]{1,2}))?$/u.exec(value.trim());
  if (parts === null) return null;
  const amount = Number(parts[1]) * 100 + Number((parts[2] ?? '').padEnd(2, '0'));
  return amount <= 1_000_000 ? amount : null;
}

export function displayPoints(minor: number, language: 'en' | 'es', precision: 0 | 2 = 2): string {
  const magnitude = BigInt(Math.abs(minor));
  const whole = new Intl.NumberFormat(language).format(magnitude / 100n);
  const fraction = precision === 0 ? '' : (language === 'es' ? ',' : '.') + (magnitude % 100n).toString().padStart(2, '0');
  return (minor < 0 ? '−' : '') + whole + fraction;
}

export type PolicyRevision = Revision | '0';
export interface PolicySetting {readonly policy: AllocationPolicy | null; readonly revision: Revision;}
export interface AllocationSettings {readonly household: PolicySetting | null; readonly override: PolicySetting | null;}
export interface AllocationInput {
  readonly performerIds: readonly string[];
  readonly manualShares?: readonly ManualShare[];
}
export interface AllocationPreview extends AllocationEvidence {readonly fingerprint: string;}
export interface ReviewedAllocation extends AllocationInput {
  readonly occurrenceId: string;
  readonly revision: Revision;
  readonly fingerprint: string;
}

function check(value: unknown): asserts value {
  if (!value) throw new Error('invalid_points_allocation');
}

export function allocationFingerprint(value: unknown): string {
  check(typeof value === 'string' && /^[a-f0-9]{64}$/u.test(value));
  return value;
}

export function allocationPerformers(value: unknown, identifier: (value: unknown) => string): readonly string[] {
  check(Array.isArray(value) && value.length >= 1 && value.length <= 32);
  const ids = value.map(identifier);
  check(new Set(ids).size === ids.length);
  return Object.freeze(ids);
}

export function manualPointShares(value: unknown, performers: readonly string[]): readonly ManualShare[] {
  check(Array.isArray(value) && value.length === performers.length);
  const seen = new Set<string>();
  return Object.freeze(value.map(raw => {
    check(raw !== null && typeof raw === 'object' && !Array.isArray(raw) && Object.keys(raw).length === 2
      && Object.hasOwn(raw, 'member_id') && Object.hasOwn(raw, 'amount_minor'));
    const {member_id, amount_minor} = raw as ManualShare;
    check(performers.includes(member_id) && !seen.has(member_id) && Number.isInteger(amount_minor)
      && amount_minor >= 0 && amount_minor <= 1_000_000);
    seen.add(member_id);
    return Object.freeze({member_id, amount_minor});
  }));
}
