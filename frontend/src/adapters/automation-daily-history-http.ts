import type {DraftScope} from '../application/automation-drafts';
import type {ScheduledAutomationRun} from '../application/automation-daily-history';
import type {AutomationRunHistoryServer, AutomationRunPage} from '../application/automation-run-history';
import {DAILY_RESOLUTIONS} from '../application/automation-schedule-preview';
import {revisionValue} from '../domain/administration';
import {BoundedHTTP, readFailure} from './http-transport';
import type {FetchTransport} from './http-transport';
import {failure} from './http-values';
import type {EntryEndpoint} from './http-values';
import {boolean, check, choice, fields, identifier, integer, text} from './json-values';
import {dailyLocal, MAX_DAILY_INSTANT} from './automation-daily-values';

function run(value: unknown): ScheduledAutomationRun {
  const row = fields(value, ['trigger_key', 'rule_revision', 'control_revision', 'requested_local', 'resolved_local',
    'scheduled_at', 'time_zone', 'resolution', 'admitted_at', 'outcome', 'finished_at', 'historical', 'task_created',
    'task_occurrence_id', 'operation_id'], []);
  const key = text(row.trigger_key, 64), timeZone = text(row.time_zone, 128);
  const requestedLocal = dailyLocal(row.requested_local), resolvedLocal = dailyLocal(row.resolved_local);
  const scheduledAt = integer(row.scheduled_at, 0), admittedAt = integer(row.admitted_at, 0);
  const outcome = choice(row.outcome, ['queued', 'created', 'no_task', 'cancelled', 'denied'] as const);
  const finishedAt = row.finished_at === null ? null : integer(row.finished_at, 0);
  const historical = boolean(row.historical), taskCreated = boolean(row.task_created);
  const taskOccurrenceId = row.task_occurrence_id === null ? null : identifier(row.task_occurrence_id);
  const operationId = row.operation_id === null ? null : identifier(row.operation_id);
  const resolution = choice(row.resolution, DAILY_RESOLUTIONS);
  check(/^[a-f0-9]{64}$/u.test(key) && /^[A-Za-z0-9_+\-/]+$/u.test(timeZone)
    && timeZone.split('/').every(part => part.length > 0)
    && scheduledAt <= MAX_DAILY_INSTANT && admittedAt <= MAX_DAILY_INSTANT
    && (finishedAt === null || finishedAt <= MAX_DAILY_INSTANT)
    && (outcome === 'queued') === (finishedAt === null) && taskCreated === (outcome === 'created')
    && (taskOccurrenceId === null || (taskCreated && !historical))
    && (operationId !== null || outcome === 'queued')
    && (resolution === 'gap_first_valid' ? Date.parse(resolvedLocal + 'Z') > Date.parse(requestedLocal + 'Z')
      : Date.parse(resolvedLocal + 'Z') === Date.parse(requestedLocal + 'Z')));
  return {key, ruleRevision: revisionValue(row.rule_revision), controlRevision: revisionValue(row.control_revision),
    requestedLocal, resolvedLocal, scheduledAt, timeZone, resolution, admittedAt, outcome, finishedAt,
    historical, taskOccurrenceId, operationId};
}

export class HttpDailyAutomationHistory implements AutomationRunHistoryServer<ScheduledAutomationRun> {
  private readonly network: BoundedHTTP;
  constructor(target: EntryEndpoint, transport: FetchTransport) {this.network = new BoundedHTTP(target, transport);}

  page(scope: DraftScope, ruleId: string, after: string | null) {
    return this.network.owned<AutomationRunPage<ScheduledAutomationRun> | 'expired'>(async signal => {
      const reply = await this.network.request('automation/drafts/' + identifier(ruleId) + '/daily/runs'
        + (after === null ? '' : '?cursor=' + encodeURIComponent(after)), 'GET', scope.context, null, null, null, signal);
      if (after !== null && (reply.status === 409 || reply.status === 422)) {
        failure(reply.value);
        if (['task_cursor_expired', 'invalid_task_cursor'].includes((reply.value as {code: string}).code)) return 'expired';
      }
      if (reply.status !== 200) return readFailure(reply.status, reply.value);
      const row = fields(reply.value, ['rule_id', 'items', 'next_cursor'], []);
      check(identifier(row.rule_id) === ruleId && Array.isArray(row.items) && row.items.length <= 25);
      const items = row.items.map(item => run(item));
      check(new Set(items.map(item => item.key)).size === items.length);
      let previous: ScheduledAutomationRun | null = null;
      for (const item of items) {
        check(previous === null || previous.admittedAt > item.admittedAt
          || (previous.admittedAt === item.admittedAt && previous.key > item.key));
        previous = item;
      }
      const next = row.next_cursor === null ? null : text(row.next_cursor, 2048);
      check(next === null || (items.length > 0 && next !== after));
      return {items, next};
    });
  }
}
