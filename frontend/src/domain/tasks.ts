/** Pure task intents preserve original user data; validation never grants authority. */
import {revisionValue} from './administration';
import type {Revision} from './administration';
import {civilDate} from './civil-date';
import {allocationFingerprint, allocationPerformers, manualPointShares} from './point-allocation';
import type {ManualShare} from './point-allocation';

export const TASK_TEXT_LIMITS = Object.freeze({title: 160, description: 4000, reason: 1000});

export class TaskInputError extends Error {
  constructor() {super('invalid_task_input'); this.name = 'TaskInputError';}
}
function requireValue(condition: unknown): asserts condition {if (!condition) throw new TaskInputError();}
export function taskIdentifier(value: unknown): string {
  requireValue(typeof value === 'string' && /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/u.test(value)); return value;
}
export function hasTaskText(value: string): boolean {
  return /\P{White_Space}/u.test(value);
}
export function taskText(value: unknown, maximum: number, required: boolean, multiline = false): string {
  requireValue(typeof value === 'string' && Array.from(value).length <= maximum
    && (!required || hasTaskText(value))
    && !/[\uD800-\uDFFF\u007F]/u.test(value)
    && !(multiline ? /[\u0000-\u0008\u000B\u000C\u000E-\u001F]/u : /[\u0000-\u001F]/u).test(value));
  return value;
}
export function taskTime(value: unknown): string {
  requireValue(typeof value === 'string' && value.length <= 19 && /^(?:0|[1-9][0-9]*)$/u.test(value)
    && BigInt(value) <= 9_223_372_036_854_775_807n); return value;
}
export function taskQuantity(value: unknown): string {
  requireValue(typeof value === 'string' && /^(?:0|[1-9][0-9]{0,11})(?:\.[0-9]{0,5}[1-9])?$/u.test(value)); return value;
}
/** Normalize a human decimal entry only before preparing an immutable command. Zero is explicit. */
export function taskQuantityInput(value: string, precision: number): string | null {
  const trimmed = value.trim();
  if (trimmed.length > 64 || !/^[0-9]+(?:[.,][0-9]+)?$/u.test(trimmed)) return null;
  const [whole, fraction = ''] = trimmed.replace(',', '.').split('.');
  const integer = whole.replace(/^0+(?=[0-9])/u, ''), decimal = fraction.replace(/0+$/u, '');
  if (decimal.length > precision) return null;
  try {return taskQuantity(integer + (decimal ? '.' + decimal : ''));} catch {return null;}
}
export interface TaskMaterialSelection {readonly reference_id: string; readonly planned_quantity: string;}
export function taskMaterialSelections(value: unknown): readonly TaskMaterialSelection[] {
  requireValue(Array.isArray(value) && value.length <= 32);
  const seen = new Set<string>();
  return Object.freeze(Array.from(value, raw => {
    const item = fields(raw, ['reference_id', 'planned_quantity']), reference_id = taskIdentifier(item.reference_id);
    requireValue(!seen.has(reference_id)); seen.add(reference_id);
    return Object.freeze({reference_id, planned_quantity: taskQuantity(item.planned_quantity)});
  }));
}
export function taskBasePointAmount(value: unknown): number {
  requireValue(typeof value === 'number' && Number.isInteger(value) && value >= 0 && value <= 1_000_000);
  return value;
}
export interface TaskMaterialUsage {readonly line_id: string; readonly quantity: string;}
export function taskAssignees(value: unknown): readonly string[] {
  requireValue(Array.isArray(value) && value.length <= 32);
  const ids = Array.from(value, taskIdentifier);
  requireValue(new Set(ids).size === ids.length);
  return Object.freeze(ids);
}
export const TASK_STATES = ['draft', 'available', 'assigned', 'in_progress', 'blocked', 'completed', 'cancelled', 'skipped'] as const;
export type TaskState = typeof TASK_STATES[number];
export const TASK_PROGRESS_TARGETS = ['in_progress', 'blocked', 'assigned', 'available'] as const;
export type TaskProgressTarget = typeof TASK_PROGRESS_TARGETS[number];
export const TASK_PRIORITIES = ['low', 'normal', 'high', 'urgent'] as const;
export type TaskPriority = typeof TASK_PRIORITIES[number];
type ScheduledStart = Readonly<{kind: 'date' | 'time'; local: string}>;
export type TaskScheduleDraft =
  Readonly<{kind: 'fixed'; start: ScheduledStart; rrule: string}>
  | Readonly<{kind: 'relative'; start: ScheduledStart; interval_days: number; visibility: 'at_completion' | 'at_verification'}>;
export interface TaskSchedulePolicy {
  readonly zone: string;
  readonly data_identity: string;
  readonly repeated_time: 'first_instant' | 'second_instant';
  readonly revision: Revision;
}
type TaskSchedule = Readonly<{draft: TaskScheduleDraft; policy: TaskSchedulePolicy}>;
type TaskCreationOverrides = Readonly<{point_value_minor: number}>;
export const CATEGORY_ACTIONS = ['task.category.create', 'task.category.rename', 'task.category.archive'] as const;
export type CategoryCommand =
  Readonly<{action: 'task.category.create'; payload: Readonly<{expected_revision: 0; label: string}>}>
  | Readonly<{action: 'task.category.rename'; categoryId: string; payload: Readonly<{expected_revision: Revision; label: string}>}>
  | Readonly<{action: 'task.category.archive'; categoryId: string; payload: Readonly<{expected_revision: Revision}>}>;
export function isCategoryCommand(command: TaskCommand): command is CategoryCommand {
  return CATEGORY_ACTIONS.includes(command.action as CategoryCommand['action']);
}
export function categoryLabel(value: unknown): string {
  requireValue(typeof value === 'string' && Array.from(value).length <= 256 && !/[\p{Cc}\p{Cs}]/u.test(value));
  const label = value.replace(/^\p{White_Space}+|\p{White_Space}+$/gu, '').normalize('NFC');
  requireValue(label.length > 0 && Array.from(label).length <= 80);
  return label;
}
export type TaskCommand = CategoryCommand |
  Readonly<{action: 'task.create'; payload: Readonly<{expected_revision: 0; title: string; description: string; priority: TaskPriority;
    category_id?: string; schedule?: TaskSchedule; overrides?: TaskCreationOverrides; materials?: readonly TaskMaterialSelection[]}>}>
  | Readonly<{action: 'task.material.settle'; occurrenceId: string; intentId: string; payload: Readonly<{
    expected_revision: Revision; cycle_id: string; action: 'post'; reason: '';
  }> | Readonly<{expected_revision: Revision; cycle_id: string; action: 'correct'; quantity: string; reason: string}>}>
  | Readonly<{action: 'task.claim'; occurrenceId: string; payload: Readonly<{expected_revision: Revision}>}>
  | Readonly<{action: 'task.assign'; occurrenceId: string; payload: Readonly<{expected_revision: Revision; assignee_ids: readonly string[]}>}>
  | Readonly<{action: 'task.transition'; occurrenceId: string; payload: Readonly<{
    expected_revision: Revision; target: TaskProgressTarget; reason: string}>}>
  | Readonly<{action: 'task.complete'; occurrenceId: string; payload: Readonly<{expected_revision: Revision;
    performer_ids: readonly string[]; performed_at: string; material_usages: readonly TaskMaterialUsage[] | null;
    allocation_fingerprint?: string; manual_shares?: readonly ManualShare[]}>}>
  | Readonly<{action: 'task.verify'; occurrenceId: string; payload: Readonly<{expected_revision: Revision;
    cycle_id: string; decision: 'approved' | 'rejected'; reason: string}>}>
  | Readonly<{action: 'task.reopen'; occurrenceId: string; payload: Readonly<{expected_revision: Revision; cycle_id: string; reason: string}>}>;
type Fields = Record<string, unknown>;
function fields(value: unknown, keys: readonly string[]): Fields {
  requireValue(typeof value === 'object' && value !== null && !Array.isArray(value)
    && keys.every(key => Object.hasOwn(value, key)) && Object.keys(value).length === keys.length);
  return value as Fields;
}
function choice<T extends string>(value: unknown, options: readonly T[]): T {
  requireValue(typeof value === 'string' && options.includes(value as T)); return value as T;
}
export function taskSchedulePolicy(value: unknown): TaskSchedulePolicy {
  const body = fields(value, ['zone', 'data_identity', 'repeated_time', 'revision']);
  const {zone, data_identity} = body;
  requireValue(typeof zone === 'string' && /^[A-Za-z0-9_+/-]{1,128}$/u.test(zone));
  requireValue(typeof data_identity === 'string' && /^[A-Za-z0-9:/_.-]{1,128}$/u.test(data_identity));
  return Object.freeze({zone, data_identity, repeated_time: choice(body.repeated_time, ['first_instant', 'second_instant']),
    revision: revisionValue(body.revision)});
}
export function taskScheduleDraft(value: unknown): TaskScheduleDraft {
  const kind = choice((value as Fields)?.kind, ['fixed','relative']);
  const body = fields(value, kind === 'fixed' ? ['kind','start','rrule'] : ['kind','start','interval_days','visibility']);
  const date = fields(body.start, ['kind','local']);
  const startKind = choice(date.kind, ['date','time']), local = date.local;
  requireValue(typeof local === 'string' && (startKind === 'date' ? civilDate(local)
    : civilDate(local.slice(0, 10)) && /^\d{4}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d$/u.test(local)));
  const start = Object.freeze({kind: startKind, local});
  if (kind === 'fixed') return Object.freeze({kind, start, rrule: taskText(body.rrule, 2048, true)});
  const interval = body.interval_days;
  requireValue(typeof interval === 'number' && Number.isInteger(interval) && interval >= 1 && interval <= 36600);
  return Object.freeze({kind, start, interval_days: interval, visibility: choice(body.visibility, ['at_completion','at_verification'])});
}
function usages(value: unknown): readonly TaskMaterialUsage[] | null {
  if (value === null) return null;
  requireValue(Array.isArray(value) && value.length <= 32);
  const seen = new Set<string>();
  return Object.freeze(value.map(raw => {
    const item = fields(raw, ['line_id', 'quantity']), line_id = taskIdentifier(item.line_id);
    requireValue(!seen.has(line_id)); seen.add(line_id);
    return Object.freeze({line_id, quantity: taskQuantity(item.quantity)});
  }));
}
/** Invalid or open-ended data cannot become a network command. No normalization replaces the original. */
export function taskCommand(value: unknown): TaskCommand | undefined {
  try {
    requireValue(typeof value === 'object' && value !== null && !Array.isArray(value));
    const action = (value as Fields).action;
    if (action === 'task.category.create' || action === 'task.category.rename' || action === 'task.category.archive') {
      const item = fields(value, action === 'task.category.create' ? ['action', 'payload'] : ['action', 'categoryId', 'payload']);
      const body = fields(item.payload, action === 'task.category.archive' ? ['expected_revision'] : ['expected_revision', 'label']);
      if (action === 'task.category.archive') return Object.freeze({action, categoryId: taskIdentifier(item.categoryId),
        payload: Object.freeze({expected_revision: revisionValue(body.expected_revision)})});
      categoryLabel(body.label);
      const label = body.label as string;
      if (action === 'task.category.create') {
        requireValue(body.expected_revision === 0);
        return Object.freeze({action, payload: Object.freeze({expected_revision: 0, label})});
      }
      return Object.freeze({action, categoryId: taskIdentifier(item.categoryId),
        payload: Object.freeze({expected_revision: revisionValue(body.expected_revision), label})});
    }
    const item = fields(value, action === 'task.create' ? ['action', 'payload']
      : action === 'task.material.settle' ? ['action', 'occurrenceId', 'intentId', 'payload'] : ['action', 'occurrenceId', 'payload']);
    if (action === 'task.create') {
      requireValue(typeof item.payload === 'object' && item.payload !== null);
      const hasSchedule = Object.hasOwn(item.payload, 'schedule');
      const hasCategory = Object.hasOwn(item.payload, 'category_id');
      const hasOverrides = Object.hasOwn(item.payload, 'overrides');
      const hasMaterials = Object.hasOwn(item.payload, 'materials');
      const body = fields(item.payload, ['expected_revision', 'title', 'description', 'priority',
        ...hasSchedule ? ['schedule'] : [], ...hasCategory ? ['category_id'] : [], ...hasOverrides ? ['overrides'] : [],
        ...hasMaterials ? ['materials'] : []]);
      requireValue(body.expected_revision === 0);
      const schedule = hasSchedule ? fields(body.schedule, ['draft', 'policy']) : null;
      let overrides: TaskCreationOverrides | undefined;
      if (hasOverrides) {
        const {point_value_minor} = fields(body.overrides, ['point_value_minor']);
        overrides = Object.freeze({point_value_minor: taskBasePointAmount(point_value_minor)});
      }
      return Object.freeze({action, payload: Object.freeze({expected_revision: 0,
        title: taskText(body.title, TASK_TEXT_LIMITS.title, true), description: taskText(body.description, TASK_TEXT_LIMITS.description, false, true),
        priority: choice(body.priority, TASK_PRIORITIES),
        ...overrides === undefined ? {} : {overrides},
        ...hasMaterials ? {materials: taskMaterialSelections(body.materials)} : {},
        ...hasCategory ? {category_id: taskIdentifier(body.category_id)} : {}, ...schedule === null ? {} : {
          schedule: Object.freeze({draft: taskScheduleDraft(schedule.draft), policy: taskSchedulePolicy(schedule.policy)})
        }})});
    }
    const occurrenceId = taskIdentifier(item.occurrenceId);
    if (action === 'task.material.settle') {
      const correct = (item.payload as Fields)?.action === 'correct';
      const body = fields(item.payload, ['expected_revision', 'cycle_id', 'action', 'reason', ...correct ? ['quantity'] : []]);
      const base = {expected_revision: revisionValue(body.expected_revision), cycle_id: taskIdentifier(body.cycle_id)};
      const intentId = taskIdentifier(item.intentId);
      if (correct) return Object.freeze({action, occurrenceId, intentId, payload: Object.freeze({...base, action: 'correct',
        quantity: taskQuantity(body.quantity), reason: taskText(body.reason, TASK_TEXT_LIMITS.reason, true, true)})});
      requireValue(body.action === 'post' && body.reason === '');
      return Object.freeze({action, occurrenceId, intentId, payload: Object.freeze({...base, action: 'post', reason: ''})});
    }
    if (action === 'task.assign') {
      const body = fields(item.payload, ['expected_revision', 'assignee_ids']);
      return Object.freeze({action, occurrenceId, payload: Object.freeze({expected_revision: revisionValue(body.expected_revision),
        assignee_ids: taskAssignees(body.assignee_ids)})});
    }
    if (action === 'task.transition') {
      const body = fields(item.payload, ['expected_revision', 'target', 'reason']);
      const target = choice(body.target, TASK_PROGRESS_TARGETS);
      const reason = taskText(body.reason, TASK_TEXT_LIMITS.reason, target === 'blocked', true);
      requireValue(target === 'blocked' || reason === '');
      return Object.freeze({action, occurrenceId, payload: Object.freeze({
        expected_revision: revisionValue(body.expected_revision), target, reason})});
    }
    if (action === 'task.claim') {
      const body = fields(item.payload, ['expected_revision']);
      return Object.freeze({action, occurrenceId, payload: Object.freeze({expected_revision: revisionValue(body.expected_revision)})});
    }
    if (action === 'task.complete') {
      requireValue(typeof item.payload === 'object' && item.payload !== null);
      const base = item.payload;
      const hasFingerprint = Object.hasOwn(base, 'allocation_fingerprint'), hasManual = Object.hasOwn(base, 'manual_shares');
      const body = fields(base, ['expected_revision', 'performer_ids', 'performed_at', 'material_usages',
        ...hasFingerprint ? ['allocation_fingerprint'] : [], ...hasManual ? ['manual_shares'] : []]);
      const performer_ids = allocationPerformers(body.performer_ids, taskIdentifier);
      return Object.freeze({action, occurrenceId, payload: Object.freeze({expected_revision: revisionValue(body.expected_revision),
        performer_ids, performed_at: taskTime(body.performed_at), material_usages: usages(body.material_usages),
        ...hasFingerprint ? {allocation_fingerprint: allocationFingerprint(body.allocation_fingerprint)} : {},
        ...hasManual ? {manual_shares: manualPointShares(body.manual_shares, performer_ids)} : {}})});
    }
    if (action === 'task.verify' || action === 'task.reopen') {
      const body = fields(item.payload, action === 'task.verify'
        ? ['expected_revision', 'cycle_id', 'decision', 'reason'] : ['expected_revision', 'cycle_id', 'reason']);
      const payload = {expected_revision: revisionValue(body.expected_revision), cycle_id: taskIdentifier(body.cycle_id),
        reason: taskText(body.reason, TASK_TEXT_LIMITS.reason, action === 'task.reopen' || body.decision === 'rejected', true)};
      return action === 'task.verify' ? Object.freeze({action, occurrenceId,
        payload: Object.freeze({...payload, decision: choice(body.decision, ['approved', 'rejected'])})})
        : Object.freeze({action, occurrenceId, payload: Object.freeze(payload)});
    }
    throw new TaskInputError();
  } catch {return undefined;}
}


export interface TaskSummary {
  readonly occurrenceId: string; readonly definitionId: string; readonly definitionRevision: Revision;
  readonly title: string; readonly state: TaskState; readonly revision: Revision;
  readonly assigneeIds: readonly string[]; readonly dueAt: string | null; readonly currentCycleId: string | null;
  readonly dueDate?: string;
}
export interface TaskPage {readonly items: readonly TaskSummary[]; readonly nextCursor: string | null;}
export interface TaskMaterial {readonly lineId: string; readonly label: string; readonly plannedQuantity: string; readonly precision: number;
  readonly unitId?: string; readonly locationId?: string;}
export const TASK_MATERIAL_STATES = ['pending_recording', 'pending_authorization', 'pending_regularization', 'pending_processing',
  'not_used', 'posted', 'corrected', 'dismissed'] as const;
export interface TaskMaterialOutcome {
  readonly intentId: string; readonly cycleId: string; readonly lineId: string; readonly revision: Revision;
  readonly submittedQuantity: string | null; readonly quantity: string | null;
  readonly state: typeof TASK_MATERIAL_STATES[number]; readonly pendingReason: string | null;
  readonly confirmedQuantity: string | null; readonly confirmedEffectRevision: Revision | null;
  readonly effectRevision: string; readonly movementId: string | null; readonly postedAt: string | null;
}
export interface TaskCycleSummary {
  readonly cycleId: string; readonly verification: 'none' | 'pending' | 'approved' | 'rejected';
  readonly performedAt: string; readonly performerIds: readonly string[];
}
export interface TaskMaterialCycle {
  readonly cycle: TaskCycleSummary; readonly closedAt: string | null;
  readonly materialOutcomes: readonly TaskMaterialOutcome[]; readonly allowedActions: readonly string[];
}
export interface TaskMaterialHistory {
  readonly items: readonly TaskMaterialCycle[]; readonly nextCursor: string | null;
}
export interface TaskDetail extends TaskSummary {
  readonly description: string; readonly priority: TaskPriority; readonly allowedActions: readonly string[];
  readonly stateReason?: string;
  readonly completionPoints?: 'automatic' | 'manual' | 'manager_required';
  readonly cycle: TaskCycleSummary | null; readonly materials: readonly TaskMaterial[];
  readonly materialRecording: 'review_on_completion' | 'separate_recording';
  readonly dependencyReviewRequired: boolean;
  readonly pendingMaterials: boolean; readonly categoryLabel?: string | null;
  readonly materialOutcomes?: readonly TaskMaterialOutcome[];
}
export interface TaskCategory {readonly id: string; readonly label: string; readonly revision: Revision;}
export interface TaskCategoryCatalog {readonly categories: readonly TaskCategory[]; readonly canManage: boolean;}
export interface TaskAccess {
  readonly householdId: string; readonly memberId: string; readonly canCreate: boolean; readonly canReviewSchedule: boolean;
  readonly canRecordForOthers?: boolean; readonly canManagePoints?: boolean; readonly canConfigure?: boolean;
  readonly canLinkMaterials?: boolean;
  readonly schedulePolicy?: TaskSchedulePolicy;
  readonly categoryCatalog?: TaskCategoryCatalog;
}
export interface TaskWorkReceipt {
  readonly kind: 'receipt'; readonly stage: 'committed' | 'historical'; readonly operationId: string;
  readonly action: Exclude<TaskCommand['action'], 'task.material.settle'>; readonly occurrenceId: string | null; readonly revision: Revision;
  readonly state: TaskState | 'active' | 'archived'; readonly cycle: TaskCycleSummary | null;
  readonly archivedBy: string | null;
  readonly basePointsMinor?: number;
  readonly assigneeIds?: readonly string[];
  readonly stateReason?: string;
}
export interface TaskMaterialReceipt {
  readonly kind: 'receipt'; readonly stage: 'committed' | 'historical'; readonly operationId: string;
  readonly action: 'task.material.settle'; readonly occurrenceId: string; readonly intentId: string;
  readonly material: TaskMaterialOutcome; readonly cycle: TaskCycleSummary; readonly archivedBy: string | null;
}
export type TaskReceipt = TaskWorkReceipt | TaskMaterialReceipt;
