/** Closed reward intents and exact minor-unit view facts. */
import {revisionValue} from './administration';
import type {Revision} from './administration';
import {MEMBER_ROLES} from './administration-commands';
import type {MemberRole} from './administration-commands';
import {taskIdentifier, taskText} from './tasks';

export const REWARD_ACTIONS = ['reward.configure', 'reward.offer', 'reward.request', 'reward.approve', 'reward.deliver', 'reward.cancel'] as const;
export const REDEMPTION_STAGES = ['requested', 'approved', 'funding_hold', 'delivered', 'cancelled'] as const;
export type RewardAction = typeof REWARD_ACTIONS[number];
export type RedemptionStage = typeof REDEMPTION_STAGES[number];
export type RewardRevision = Revision | '0';

export type RewardCommand =
  | Readonly<{action: 'reward.configure'; enabled: boolean; expected_revision: RewardRevision}>
  | Readonly<{action: 'reward.offer'; offer_id: string | null; title: string; cost_minor: number;
    enabled: boolean; eligible_roles: readonly MemberRole[]; expected_revision: RewardRevision}>
  | Readonly<{action: 'reward.request'; offer_id: string; expected_revision: Revision}>
  | Readonly<{action: 'reward.approve' | 'reward.deliver'; redemption_id: string}>
  | Readonly<{action: 'reward.cancel'; redemption_id: string; expected_revision: Revision; reason: string}>;

export interface RewardOffer {
  readonly id: string;
  readonly title: string;
  readonly cost: number;
  readonly enabled: boolean;
  readonly eligible: boolean;
  readonly roles: readonly MemberRole[];
  readonly revision: Revision;
}
export interface Redemption {
  readonly id: string;
  readonly title: string;
  readonly cost: number;
  readonly stage: RedemptionStage;
  readonly revision: Revision;
  readonly requestedAt: number;
  readonly approvedAt: number | null;
  readonly closedAt: number | null;
  readonly cancellationReason: string | null;
}
export interface RewardReport {
  readonly enabled: boolean;
  readonly revision: RewardRevision;
  readonly mayManage: boolean;
  readonly posted: number;
  readonly reserved: number;
  readonly available: number;
  readonly catalog: readonly RewardOffer[];
  readonly requests: readonly Redemption[];
  readonly cursor: string | null;
}

export function managementAction(action: RewardAction): boolean {
  return action !== 'reward.request' && action !== 'reward.cancel';
}

function requireValue(condition: unknown): asserts condition {
  if (!condition) throw new Error('invalid_reward_command');
}
function fields(value: Record<string, unknown>, required: readonly string[]): void {
  requireValue(Object.keys(value).length === required.length && required.every(key => Object.hasOwn(value, key)));
}
function enabledValue(value: unknown): boolean {
  requireValue(typeof value === 'boolean'); return value;
}
export function rewardRoles(value: unknown): readonly MemberRole[] {
  requireValue(Array.isArray(value) && value.length > 0 && value.length <= MEMBER_ROLES.length);
  requireValue(value.every(role => MEMBER_ROLES.includes(role)) && new Set(value).size === value.length);
  return Object.freeze([...value]);
}
export function rewardCost(value: unknown): number {
  requireValue(typeof value === 'number' && Number.isInteger(value) && value >= 1 && value <= 1_000_000);
  return value;
}
function initialRevision(value: unknown): RewardRevision {return value === '0' ? '0' : revisionValue(value);}

export function rewardCommand(value: unknown): RewardCommand {
  requireValue(value !== null && typeof value === 'object' && !Array.isArray(value));
  const record = value as Record<string, unknown>;
  const {action} = record;
  switch (action) {
    case 'reward.configure':
      fields(record, ['action', 'enabled', 'expected_revision']);
      return {action, enabled: enabledValue(record.enabled), expected_revision: initialRevision(record.expected_revision)};
    case 'reward.offer':
      fields(record, ['action', 'offer_id', 'title', 'cost_minor', 'enabled', 'eligible_roles', 'expected_revision']);
      return {action, offer_id: record.offer_id === null ? null : taskIdentifier(record.offer_id),
        title: taskText(record.title, 160, true), cost_minor: rewardCost(record.cost_minor),
        enabled: enabledValue(record.enabled), eligible_roles: rewardRoles(record.eligible_roles),
        expected_revision: initialRevision(record.expected_revision)};
    case 'reward.request':
      fields(record, ['action', 'offer_id', 'expected_revision']);
      return {action, offer_id: taskIdentifier(record.offer_id), expected_revision: revisionValue(record.expected_revision)};
    case 'reward.approve':
    case 'reward.deliver':
      fields(record, ['action', 'redemption_id']);
      return {action, redemption_id: taskIdentifier(record.redemption_id)};
    case 'reward.cancel':
      fields(record, ['action', 'redemption_id', 'expected_revision', 'reason']);
      return {action, redemption_id: taskIdentifier(record.redemption_id),
        expected_revision: revisionValue(record.expected_revision), reason: taskText(record.reason, 1000, true)};
    default: throw new Error('invalid_reward_command');
  }
}
