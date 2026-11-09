/** Protected recurrence routes use exact wire revisions and the shared bounded HTTP transport. */
import {ReviewRejected} from '../application/recurrence-review-controller';
import type {ReviewReceipt, ReviewRecord, ReviewServer} from '../application/recurrence-review-controller';
import type {JournalContext} from '../domain/journal';
import {FOLD_CHOICES, REVIEW_KINDS, VISIBILITIES, reviewCommand, reviewFingerprint} from '../domain/recurrence-review';
import type {ReviewTarget} from '../domain/recurrence-review';
import {BoundedHTTP} from './http-transport';
import type {FetchTransport} from './http-transport';
import {csrf, failure} from './http-values';
import type {EntryEndpoint} from './http-values';
import {boolean, check, choice, fields, identifier, integer, responseRevision, text} from './json-values';

const BASE = 'tasks/recurrence/reviews/';
const EFFECT = {attachment: 'attach_relative', adoption: 'adopt_manual', state: 'relative_state',
  'relative-settings': 'relative_settings', 'fixed-state': 'fixed_state', 'fixed-pattern': 'fixed_pattern', 'fixed-replacement': 'fixed_replacement',
  'fixed-exclude': 'fixed_exception', 'fixed-add': 'fixed_exception', reschedule: 'reschedule', 'fixed-skip': 'fixed_skip'} as const;

function target(value: unknown, occurrenceId: string): ReviewTarget {
  const item = fields(value, ['occurrence_id','occurrence_revision','definition_id','definition_revision','zone','schedule','slot_key','actions'], []);
  check(item.occurrence_id === occurrenceId && Array.isArray(item.actions) && item.actions.length <= REVIEW_KINDS.length);
  const actions = item.actions.map(action => choice(action, REVIEW_KINDS));
  check(new Set(actions).size === actions.length);
  const raw = item.schedule === null ? null : fields(item.schedule, ['schedule_id','revision','state','nominal_kind','local','zone','interval_days','visibility'], []);
  const schedule = raw === null ? null : Object.freeze({id: identifier(raw.schedule_id), revision: responseRevision(raw.revision),
    state: choice(raw.state, ['active','paused','retired'] as const),
    nominal: Object.freeze({kind: choice(raw.nominal_kind, ['date','time'] as const), local: text(raw.local, 32)}),
    zone: text(raw.zone, 128), interval: raw.interval_days === null ? null : integer(raw.interval_days, 1),
    visibility: raw.visibility === null ? null : choice(raw.visibility, VISIBILITIES)});
  return Object.freeze({occurrenceId, occurrenceRevision: responseRevision(item.occurrence_revision),
    definitionId: identifier(item.definition_id), definitionRevision: responseRevision(item.definition_revision),
    zone: text(item.zone, 128), schedule, slotKey: item.slot_key === null ? null : identifier(item.slot_key), actions: Object.freeze(actions)});
}
function object(value: unknown): Record<string, unknown> {
  check(typeof value === 'object' && value !== null && !Array.isArray(value)); return value as Record<string, unknown>;
}
function local(value: unknown): string | null {
  if (value === undefined || value === null) return null;
  return text(object(object(value).nominal).local, 32);
}
function size(value: unknown): number | null {
  if (value === undefined || value === null) return null;
  check(Array.isArray(value)); return value.length;
}
function replacements(value: unknown): NonNullable<ReviewReceipt['preview']>['replacementSlots'] {
  if (value === undefined) return [];
  check(Array.isArray(value) && value.length <= 100);
  return Object.freeze(value.map(item => {
    const slot = fields(item, ['planned','replaces'], []), date = local(slot.planned);
    check(date !== null);
    if (slot.replaces !== null) identifier(slot.replaces);
    return Object.freeze({local: date, replaces: slot.replaces !== null});
  }));
}
function repeatedSlots(values: unknown): NonNullable<NonNullable<ReviewReceipt['preview']>['repeatedSlots']> {
  check(Array.isArray(values) && values.length <= 100);
  return Object.freeze(values.flatMap(value => {
    const item = object(value), slot = object(item.planned ?? item);
    if (slot.resolved === undefined || slot.resolved === null) return [];
    const resolved = object(slot.resolved);
    if (resolved.resolution !== 'fold_first' && resolved.resolution !== 'fold_second') return [];
    const date = local(slot), offset = integer(resolved.offset_seconds, -86400);
    check(date !== null && offset < 86400);
    return [Object.freeze({local: date, offset,
      fold: resolved.resolution === 'fold_first' ? 'first_instant' as const : 'second_instant' as const})];
  }));
}
function affectedDates(value: unknown): readonly string[] {
  check(Array.isArray(value) && value.length <= 200);
  return Object.freeze(value.map(item => {
    const date = local(object(item).deadline);
    check(date !== null); return date;
  }));
}
function receipt(value: unknown, request: ReviewRecord): ReviewReceipt {
  const root = fields(value, ['state','archived_by','operation_id','created_at','result','message','action_required'], []);
  const historical = choice(root.state, ['committed','historical']) === 'historical';
  check(historical ? identifier(root.archived_by) : root.archived_by === null);
  const result = object(root.result), operationId = identifier(root.operation_id);
  const fingerprint = reviewFingerprint(result.plan_fingerprint);
  const command = request.command, kind = EFFECT[command.selection.kind];
  if (command.step === 'apply') {
    check(result.kind === kind && fingerprint === command.fingerprint);
    return {operationId, historical, preview: null};
  }
  const plan = object(result.plan), snapshot = plan.snapshot === undefined ? plan : object(plan.snapshot);
  const payload = object(snapshot.request), source = snapshot.source === undefined ? snapshot : object(snapshot.source);
  check(payload.kind === kind);
  const backlog = plan.backlog === undefined ? {} : object(plan.backlog);
  const folds = repeatedSlots(source.prospective_slots ?? backlog.prospective_slots ??
    (source.initial === undefined ? [] : [source.initial]));
  return {operationId, historical, preview: {fingerprint, expiresAt: integer(result.expires_at, 0),
    ...(source.repeated_time === undefined ? {} : {repeatedTime: choice(source.repeated_time, FOLD_CHOICES)}),
    ...(folds.length ? {repeatedSlots: folds} : {}),
    retained: size(source.open_work_retained ?? source.retained_work ?? source.retained_occurrences),
    planned: size(backlog.prospective_slots ?? backlog.pending_slots ?? source.prospective_slots),
    cancelled: size(source.cancelled_work), replacementSlots: replacements(source.prospective_slots),
    retainedDates: command.selection.kind === 'fixed-replacement' ? affectedDates(source.retained_work) : [],
    cancelledDates: command.selection.kind === 'fixed-replacement' ? affectedDates(source.cancelled_work) : [],
    previous: local(source.previous ?? source.original), destination: local(source.destination ?? source.initial ?? backlog.next_slot),
    createsFirst: source.creates_first_occurrence === undefined ? null : boolean(source.creates_first_occurrence)}};
}
function body(request: ReviewRecord): string {
  const command = reviewCommand(request.command);
  const values: Record<string, unknown> = {...command.selection.body};
  if (command.selection.kind === 'fixed-exclude' || command.selection.kind === 'fixed-add') {
    values.effect = command.selection.kind === 'fixed-exclude' ? 'exclude' : 'add';
  }
  if (command.step === 'apply') Object.assign(values, {preview_key: command.previewKey, plan_fingerprint: command.fingerprint});
  return '{' + Object.entries(values).map(([key, value]) =>
    JSON.stringify(key) + ':' + (key.endsWith('_revision') ? value : JSON.stringify(value))).join(',') + '}';
}

export class HttpRecurrenceServer implements ReviewServer {
  private readonly network: BoundedHTTP;
  constructor(endpoint: EntryEndpoint, transport: FetchTransport) {this.network = new BoundedHTTP(endpoint, transport);}
  target(context: JournalContext, occurrenceId: string) {
    return this.network.owned(async signal => target(await this.network.get(BASE + 'targets/' + identifier(occurrenceId), context, signal), occurrenceId));
  }
  original(context: JournalContext, request: ReviewRecord) {
    return this.network.owned(async signal => receipt(await this.network.get(
      BASE + 'requests/recurrence.review.' + reviewCommand(request.command).step + '/' + identifier(request.key), context, signal), request));
  }
  send(context: JournalContext, request: ReviewRecord) {
    let rejection = false, posted = false;
    const owned = this.network.owned(async signal => {
      const command = reviewCommand(request.command), key = identifier(request.key), payload = body(request);
      const token = csrf(await this.network.get('auth/csrf', context, signal));
      posted = true;
      const kind = command.selection.kind;
      const route = kind === 'fixed-exclude' || kind === 'fixed-add' ? 'fixed-exception' : kind;
      const response = await this.network.request(BASE + route + '/' + command.step, 'POST', context, payload, key, token, signal);
      if (response.status === 200) return receipt(response.value, request);
      if ([401,403,409,422].includes(response.status)) {failure(response.value); rejection = true;}
      throw new Error('review_unavailable');
    });
    return {cancel: owned.cancel, result: owned.result.catch(error => {
      if (rejection || !posted) throw new ReviewRejected();
      throw error;
    })};
  }
}
