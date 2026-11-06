/** Pure task intents preserve original user data; validation never grants authority. */
import {revisionValue} from './administration';
import type {Revision} from './administration';

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
export interface TaskMaterialUsage {readonly line_id: string; readonly quantity: string;}
export const TASK_STATES = ['draft', 'available', 'assigned', 'in_progress', 'blocked', 'completed', 'cancelled', 'skipped'] as const;
export type TaskState = typeof TASK_STATES[number];
export const TASK_PRIORITIES = ['low', 'normal', 'high', 'urgent'] as const;
export type TaskPriority = typeof TASK_PRIORITIES[number];
export type TaskCommand =
  Readonly<{action: 'task.create'; payload: Readonly<{expected_revision: 0; title: string; description: string; priority: TaskPriority}>}>
  | Readonly<{action: 'task.claim'; occurrenceId: string; payload: Readonly<{expected_revision: Revision}>}>
  | Readonly<{action: 'task.complete'; occurrenceId: string; payload: Readonly<{expected_revision: Revision;
    performer_ids: readonly string[]; performed_at: string; material_usages: readonly TaskMaterialUsage[] | null}>}>
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
    const item = fields(value, action === 'task.create' ? ['action', 'payload'] : ['action', 'occurrenceId', 'payload']);
    if (action === 'task.create') {
      const body = fields(item.payload, ['expected_revision', 'title', 'description', 'priority']);
      requireValue(body.expected_revision === 0);
      return Object.freeze({action, payload: Object.freeze({expected_revision: 0,
        title: taskText(body.title, TASK_TEXT_LIMITS.title, true), description: taskText(body.description, TASK_TEXT_LIMITS.description, false, true),
        priority: choice(body.priority, TASK_PRIORITIES)})});
    }
    const occurrenceId = taskIdentifier(item.occurrenceId);
    if (action === 'task.claim') {
      const body = fields(item.payload, ['expected_revision']);
      return Object.freeze({action, occurrenceId, payload: Object.freeze({expected_revision: revisionValue(body.expected_revision)})});
    }
    if (action === 'task.complete') {
      const body = fields(item.payload, ['expected_revision', 'performer_ids', 'performed_at', 'material_usages']);
      requireValue(Array.isArray(body.performer_ids) && body.performer_ids.length >= 1 && body.performer_ids.length <= 32);
      const performers = body.performer_ids.map(taskIdentifier);
      requireValue(new Set(performers).size === performers.length);
      return Object.freeze({action, occurrenceId, payload: Object.freeze({expected_revision: revisionValue(body.expected_revision),
        performer_ids: Object.freeze(performers), performed_at: taskTime(body.performed_at), material_usages: usages(body.material_usages)})});
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
}
export interface TaskPage {readonly items: readonly TaskSummary[]; readonly nextCursor: string | null;}
export interface TaskMaterial {readonly lineId: string; readonly label: string; readonly plannedQuantity: string; readonly precision: number;}
export interface TaskCycleSummary {
  readonly cycleId: string; readonly verification: 'none' | 'pending' | 'approved' | 'rejected';
  readonly performedAt: string; readonly performerIds: readonly string[];
}
export interface TaskDetail extends TaskSummary {
  readonly description: string; readonly priority: TaskPriority; readonly allowedActions: readonly string[];
  readonly cycle: TaskCycleSummary | null; readonly materials: readonly TaskMaterial[];
  readonly materialRecording: 'review_on_completion' | 'separate_recording';
  readonly dependencyReviewRequired: boolean;
  readonly pendingMaterials: boolean;
}
export interface TaskAccess {
  readonly householdId: string; readonly memberId: string; readonly canCreate: boolean;
}
export interface TaskReceipt {
  readonly kind: 'receipt'; readonly stage: 'committed' | 'historical'; readonly operationId: string;
  readonly action: TaskCommand['action']; readonly occurrenceId: string; readonly revision: Revision;
  readonly state: TaskState; readonly cycle: TaskCycleSummary | null;
  readonly archivedBy: string | null;
}
