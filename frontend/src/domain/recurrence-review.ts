/** Closed, lossless browser inputs for the reviewed scheduling protocol. */
import {revisionValue} from './administration';
import type {Revision} from './administration';
import {civilDate} from './calendar';
import {taskIdentifier, taskText} from './tasks';

export const REVIEW_KINDS = ['attachment', 'adoption', 'state', 'relative-settings', 'fixed-state',
  'fixed-pattern', 'fixed-replacement', 'fixed-exclude', 'fixed-add', 'reschedule', 'fixed-skip'] as const;
export const VISIBILITIES = ['at_completion', 'at_verification'] as const;
export const ATTACHMENT_CHOICES = ['adopt', 'retain_manual'] as const;
export const FOLD_CHOICES = ['first_instant', 'second_instant'] as const;
export const ATTACHMENT_FOLDS = ['household', ...FOLD_CHOICES] as const;
export const REVIEW_FOLDS = ['keep_fold', 'household'] as const;
export type FoldPolicy = typeof FOLD_CHOICES[number];
export type ReviewKind = typeof REVIEW_KINDS[number];
export type Visibility = typeof VISIBILITIES[number];
export type ReviewStep = 'preview' | 'apply';
export type NominalKind = 'date' | 'time';
type Nominal = Readonly<{kind: NominalKind; local: string}>;
type ScheduleIdentity = Readonly<{schedule_id: string; schedule_revision: Revision}>;
type WorkIdentity = Readonly<{occurrence_id: string; occurrence_revision: Revision}>;
type SlotIdentity = ScheduleIdentity & WorkIdentity & Readonly<{slot_key: string; reason: string}>;
type RelativeSettings = Readonly<{interval_days: number; visibility: Visibility}>;
type ReviewedFold = Readonly<{use_household_fold?: true}>;
export type ReviewSelection =
  | Readonly<{kind: 'attachment'; body: WorkIdentity & RelativeSettings & Readonly<{
    definition_id: string; definition_revision: Revision; initial: Nominal; zone: string;
    repeated_time: typeof ATTACHMENT_FOLDS[number]; choice: typeof ATTACHMENT_CHOICES[number];
  }>}>
  | Readonly<{kind: 'adoption'; body: ScheduleIdentity & WorkIdentity}>
  | Readonly<{kind: 'state' | 'fixed-state'; body: ScheduleIdentity & Readonly<{target: 'active' | 'paused'}>}>
  | Readonly<{kind: 'relative-settings'; body: ScheduleIdentity & RelativeSettings & ReviewedFold}>
  | Readonly<{kind: 'fixed-pattern'; body: ScheduleIdentity & ReviewedFold & Readonly<{start: Nominal; rrule: string}>}>
  | Readonly<{kind: 'fixed-replacement'; body: ScheduleIdentity & ReviewedFold & Readonly<{start: Nominal; rrule: string; reason: string}>}>
  | Readonly<{kind: 'fixed-exclude' | 'fixed-add'; body: ScheduleIdentity & Readonly<{nominal: Nominal; reason: string}>}>
  | Readonly<{kind: 'fixed-skip'; body: SlotIdentity}>
  | Readonly<{kind: 'reschedule'; body: SlotIdentity & Readonly<{destination: Nominal}>}>;
export type ReviewCommand =
  | Readonly<{step: 'preview'; selection: ReviewSelection}>
  | Readonly<{step: 'apply'; selection: ReviewSelection; previewKey: string; fingerprint: string}>;
export interface ReviewSchedule {
  readonly id: string; readonly revision: Revision; readonly state: 'active' | 'paused' | 'retired';
  readonly nominal: Nominal; readonly zone: string;
  readonly interval: number | null; readonly visibility: Visibility | null;
}
export interface ReviewTarget {
  readonly occurrenceId: string; readonly occurrenceRevision: Revision;
  readonly definitionId: string; readonly definitionRevision: Revision; readonly zone: string;
  readonly schedule: ReviewSchedule | null; readonly slotKey: string | null; readonly actions: readonly ReviewKind[];
}
export interface ReviewDraft {
  readonly kind: ReviewKind; readonly date: string; readonly time: string; readonly zone: string;
  readonly interval: string; readonly visibility: Visibility; readonly choice: typeof ATTACHMENT_CHOICES[number];
  readonly fold: typeof ATTACHMENT_FOLDS[number] | 'keep_fold'; readonly reason: string; readonly rrule: string;
}

type Fields = Record<string, unknown>;
function requireReview(condition: unknown): asserts condition {if (!condition) throw new Error('invalid_review_input');}
function fields(value: unknown, keys: readonly string[], optional: readonly string[] = []): Fields {
  requireReview(typeof value === 'object' && value !== null && !Array.isArray(value)
    && keys.every(key => Object.hasOwn(value, key))
    && Object.keys(value).every(key => keys.includes(key) || optional.includes(key)));
  return value as Fields;
}
const FOLD_OVERRIDE = ['use_household_fold'] as const;
function reviewedFold(body: Fields): ReviewedFold {
  if (!Object.hasOwn(body, 'use_household_fold')) return {};
  requireReview(body.use_household_fold === true);
  return {use_household_fold: true};
}
function option<T extends string>(value: unknown, options: readonly T[]): T {
  requireReview(options.includes(value as T)); return value as T;
}
function nominal(value: unknown): Nominal {
  const input = fields(value, ['kind','local']);
  const kind = option(input.kind, ['date','time'] as const), local = input.local;
  requireReview(typeof local === 'string');
  requireReview(kind === 'date' ? civilDate(local) : civilDate(local.slice(0, 10)) &&
    /^\d{4}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d(?:\.\d{1,3})?)?$/u.test(local));
  return Object.freeze({kind, local});
}
const SCHEDULE = ['schedule_id','schedule_revision'];
const WORK = ['occurrence_id','occurrence_revision'];
const RELATIVE = ['interval_days','visibility'];
const SLOT = [...SCHEDULE,...WORK,'slot_key','reason'];

function work(body: Fields): WorkIdentity {
  return {occurrence_id: taskIdentifier(body.occurrence_id), occurrence_revision: revisionValue(body.occurrence_revision)};
}
function schedule(body: Fields): ScheduleIdentity {
  return {schedule_id: taskIdentifier(body.schedule_id), schedule_revision: revisionValue(body.schedule_revision)};
}
function relative(body: Fields): RelativeSettings {
  const interval = body.interval_days;
  requireReview(typeof interval === 'number' && Number.isInteger(interval) && interval >= 1 && interval <= 36600);
  return {interval_days: interval, visibility: option(body.visibility, VISIBILITIES)};
}
function selection(value: unknown): ReviewSelection {
  const input = fields(value, ['kind','body']), kind = option(input.kind, REVIEW_KINDS);
  switch (kind) {
    case 'attachment': {
      const body = fields(input.body, [...WORK,...RELATIVE,'definition_id','definition_revision','initial','zone','repeated_time','choice']);
      return Object.freeze({kind, body: Object.freeze({...work(body), ...relative(body),
        definition_id: taskIdentifier(body.definition_id), definition_revision: revisionValue(body.definition_revision),
        initial: nominal(body.initial), zone: taskText(body.zone, 128, true),
        repeated_time: option(body.repeated_time, ATTACHMENT_FOLDS), choice: option(body.choice, ATTACHMENT_CHOICES)})});
    }
    case 'adoption': {
      const body = fields(input.body, [...SCHEDULE,...WORK]);
      return Object.freeze({kind, body: Object.freeze({...schedule(body), ...work(body)})});
    }
    case 'state': case 'fixed-state': {
      const body = fields(input.body, [...SCHEDULE,'target']);
      return Object.freeze({kind, body: Object.freeze({...schedule(body), target: option(body.target, ['active','paused'] as const)})});
    }
    case 'relative-settings': {
      const body = fields(input.body, [...SCHEDULE,...RELATIVE], FOLD_OVERRIDE);
      return Object.freeze({kind, body: Object.freeze({...schedule(body), ...relative(body), ...reviewedFold(body)})});
    }
    case 'fixed-pattern': case 'fixed-replacement': {
      const body = fields(input.body, kind === 'fixed-replacement' ? [...SCHEDULE,'start','rrule','reason'] : [...SCHEDULE,'start','rrule'], FOLD_OVERRIDE);
      const pattern = {...schedule(body), ...reviewedFold(body), start: nominal(body.start), rrule: taskText(body.rrule, 2048, true)};
      return kind === 'fixed-replacement'
        ? Object.freeze({kind, body: Object.freeze({...pattern, reason: taskText(body.reason, 1000, true, true)})})
        : Object.freeze({kind, body: Object.freeze(pattern)});
    }
    case 'fixed-exclude': case 'fixed-add': {
      const body = fields(input.body, [...SCHEDULE,'nominal','reason']);
      return Object.freeze({kind, body: Object.freeze({...schedule(body), nominal: nominal(body.nominal),
        reason: taskText(body.reason, 1000, true, true)})});
    }
    default: {
      const body = fields(input.body, kind === 'reschedule' ? [...SLOT,'destination'] : SLOT);
      const slot = {...schedule(body), ...work(body), slot_key: taskIdentifier(body.slot_key), reason: taskText(body.reason, 1000, true, true)};
      return kind === 'reschedule' ? Object.freeze({kind, body: Object.freeze({...slot, destination: nominal(body.destination)})})
        : Object.freeze({kind, body: Object.freeze(slot)});
    }
  }
}
export function reviewFingerprint(value: unknown): string {
  requireReview(typeof value === 'string' && /^[a-f0-9]{64}$/u.test(value)); return value;
}
export function reviewCommand(value: unknown): ReviewCommand {
  requireReview(typeof value === 'object' && value !== null);
  const step = (value as Fields).step;
  if (step === 'preview') return Object.freeze({step, selection: selection(fields(value, ['step','selection']).selection)});
  requireReview(step === 'apply');
  const input = fields(value, ['step','selection','previewKey','fingerprint']);
  return Object.freeze({step, selection: selection(input.selection), previewKey: taskIdentifier(input.previewKey),
    fingerprint: reviewFingerprint(input.fingerprint)});
}

export function reviewDraft(value: unknown): ReviewDraft {
  const input = fields(value, ['kind','date','time','zone','interval','visibility','choice','fold','reason','rrule']);
  for (const key of ['date','time','zone','interval','reason','rrule']) requireReview(typeof input[key] === 'string');
  option(input.kind, REVIEW_KINDS); option(input.visibility, VISIBILITIES); option(input.choice, ATTACHMENT_CHOICES); option(input.fold, [...ATTACHMENT_FOLDS, 'keep_fold']);
  return Object.freeze(input as unknown as ReviewDraft);
}

export function reviewSelection(target: ReviewTarget, draft: ReviewDraft): ReviewSelection {
  const kind = draft.kind;
  requireReview(target.actions.includes(kind));
  const work = {occurrence_id: target.occurrenceId, occurrence_revision: target.occurrenceRevision};
  const relative = {interval_days: Number(draft.interval), visibility: draft.visibility};
  const local = draft.time === '' ? {kind: 'date', local: draft.date} : {kind: 'time', local: draft.date + 'T' + draft.time};
  if (kind === 'attachment') return selection({kind, body: {...work,...relative, definition_id: target.definitionId,
    definition_revision: target.definitionRevision, initial: local, zone: draft.zone, repeated_time: draft.fold, choice: draft.choice}});
  requireReview(target.schedule !== null);
  const schedule = {schedule_id: target.schedule.id, schedule_revision: target.schedule.revision};
  if (kind === 'adoption') return selection({kind, body: {...schedule,...work}});
  if (kind === 'state' || kind === 'fixed-state') return selection({kind, body: {...schedule,
    target: target.schedule.state === 'active' ? 'paused' : 'active'}});
  const fold = draft.fold === 'household' ? {use_household_fold: true} : {};
  if (kind === 'relative-settings') return selection({kind, body: {...schedule,...relative,...fold}});
  if (kind === 'fixed-pattern' || kind === 'fixed-replacement') {
    const pattern = {...schedule, ...fold, start: local, rrule: draft.rrule};
    return selection({kind, body: kind === 'fixed-replacement' ? {...pattern, reason: draft.reason} : pattern});
  }
  if (kind === 'fixed-exclude' || kind === 'fixed-add') {
    requireReview(local.kind === target.schedule.nominal.kind);
    return selection({kind, body: {...schedule, nominal: local, reason: draft.reason}});
  }
  const slot = {...schedule,...work,slot_key: target.slotKey,reason: draft.reason};
  return selection({kind, body: kind === 'reschedule' ? {...slot, destination: local} : slot});
}
