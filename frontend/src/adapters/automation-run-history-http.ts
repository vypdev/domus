import type {DraftScope} from '../application/automation-drafts';
import type {AutomationRun, AutomationRunHistoryServer, AutomationRunPage} from '../application/automation-run-history';
import {revisionValue} from '../domain/administration';
import {BoundedHTTP, readFailure} from './http-transport';
import type {FetchTransport} from './http-transport';
import {failure} from './http-values';
import type {EntryEndpoint} from './http-values';
import {boolean, check, fields, identifier, integer, text} from './json-values';

function run(value: unknown): AutomationRun {
  const row = fields(value, ['operation_id', 'created_at', 'rule_revision', 'condition_matched',
    'task_created', 'historical', 'task_occurrence_id'], []);
  const taskCreated = boolean(row.task_created), historical = boolean(row.historical);
  const taskOccurrenceId = row.task_occurrence_id === null ? null : identifier(row.task_occurrence_id);
  const time = integer(row.created_at, 0);
  check(time <= 8_640_000_000_000_000 && boolean(row.condition_matched) === taskCreated
    && (taskOccurrenceId === null || (taskCreated && !historical)));
  return {operationId: identifier(row.operation_id), revision: revisionValue(row.rule_revision),
    time, historical, taskCreated, taskOccurrenceId};
}

export class HttpAutomationRunHistory implements AutomationRunHistoryServer {
  private readonly network: BoundedHTTP;

  constructor(target: EntryEndpoint, transport: FetchTransport) {
    this.network = new BoundedHTTP(target, transport);
  }

  page(scope: DraftScope, ruleId: string, after: string | null) {
    return this.network.owned<AutomationRunPage | 'expired'>(async signal => {
      const route = 'automation/drafts/' + identifier(ruleId) + '/runs'
        + (after === null ? '' : '?cursor=' + encodeURIComponent(after));
      const reply = await this.network.request(route, 'GET', scope.context, null, null, null, signal);
      if (reply.status === 422 && after !== null) {
        failure(reply.value);
        if ((reply.value as {code: string}).code === 'invalid_task_cursor') return 'expired';
      }
      if (reply.status !== 200) return readFailure(reply.status, reply.value);
      const page = fields(reply.value, ['rule_id', 'items', 'next_cursor'], []);
      check(page.rule_id === ruleId && Array.isArray(page.items) && page.items.length <= 25);
      const items = page.items.map(run);
      const next = page.next_cursor === null ? null : text(page.next_cursor, 512);
      check(new Set(items.map(item => item.operationId)).size === items.length
        && (next === null || (items.length === 25 && next.length > 0 && next !== after)));
      return {items, next};
    });
  }
}
