/** Keep manual execution tied to current context, strict revisions and the original receipt. */
import type {DraftScope} from '../application/automation-drafts';
import type {AutomationConfiguration, AutomationExecutionOutcome, AutomationExecutionRequest,
  AutomationExecutionServer} from '../application/automation-execution';
import {revisionValue} from '../domain/administration';
import {taskText} from '../domain/tasks';
import {BoundedHTTP, readFailure} from './http-transport';
import type {FetchTransport} from './http-transport';
import {csrf, failure} from './http-values';
import type {EntryEndpoint} from './http-values';
import {boolean, check, choice, fields, identifier, integer, text} from './json-values';

const BASE = 'automation/drafts/';

function errorCode(value: unknown): string {
  failure(value);
  return (value as {code: string}).code;
}

function configuration(value: unknown, id: string): AutomationConfiguration {
  const row = fields(value, ['rule_id', 'latest_revision', 'latest_title', 'control'], ['latest_manual']);
  check(identifier(row.rule_id) === id && (row.latest_manual === undefined || row.latest_manual === false));
  const latestRevision = revisionValue(row.latest_revision);
  const latestTitle = taskText(row.latest_title, 160, true);
  const latest = {id, latestRevision, latestTitle,
    ...(row.latest_manual === false ? {latestManual: false as const} : {})};
  if (row.control === null) return {...latest, control: null};
  const info = fields(row.control, ['rule_revision', 'control_revision', 'enabled', 'title'], ['trigger']);
  check(info.trigger === undefined || info.trigger === 'daily');
  const ruleRevision = revisionValue(info.rule_revision);
  check(BigInt(ruleRevision) <= BigInt(latestRevision));
  const control = {ruleRevision, controlRevision: revisionValue(info.control_revision),
    enabled: boolean(info.enabled), title: taskText(info.title, 160, true),
    ...(info.trigger === 'daily' ? {trigger: 'daily' as const} : {})};
  return {...latest, control};
}

function receipt(value: unknown, scope: DraftScope, request: AutomationExecutionRequest): AutomationExecutionOutcome {
  const row = fields(value, ['state', 'archived_by', 'operation_id', 'created_at', 'result', 'message', 'action_required'], []);
  const kind = choice(row.state, ['committed', 'historical'] as const);
  check((kind === 'historical') === (row.archived_by !== null));
  if (row.archived_by !== null) identifier(row.archived_by);
  integer(row.created_at, 0);
  text(row.message, 2048);
  text(row.action_required, 4096);
  const operationId = identifier(row.operation_id);
  const common = ['rule_id', 'rule_revision', 'control_revision', 'member_id'];
  if (request.kind === 'configure') {
    const result = fields(row.result, [...common, 'enabled'], []);
    const ruleRevision = revisionValue(result.rule_revision);
    check(result.member_id === scope.memberId && identifier(result.rule_id) === request.ruleId
      && ruleRevision === request.ruleRevision && boolean(result.enabled) === request.enabled
      && BigInt(revisionValue(result.control_revision)) === BigInt(request.controlRevision) + 1n);
    return {kind, operationId, ruleRevision, action: 'configure', enabled: request.enabled};
  }
  const result = fields(row.result, [...common, 'run_id', 'condition_matched', 'task_occurrence_id', 'task_operation_id'], []);
  const ruleRevision = revisionValue(result.rule_revision);
  check(result.member_id === scope.memberId && identifier(result.rule_id) === request.ruleId
    && ruleRevision === request.ruleRevision && revisionValue(result.control_revision) === request.controlRevision);
  identifier(result.run_id);
  const taskOccurrenceId = result.task_occurrence_id === null ? null : identifier(result.task_occurrence_id);
  const taskOperationId = result.task_operation_id === null ? null : identifier(result.task_operation_id);
  check((taskOccurrenceId !== null) === boolean(result.condition_matched)
    && (taskOccurrenceId === null) === (taskOperationId === null));
  return {kind, operationId, ruleRevision, action: 'run', taskOccurrenceId};
}

export class HttpAutomationExecution implements AutomationExecutionServer {
  private readonly network: BoundedHTTP;
  constructor(target: EntryEndpoint, transport: FetchTransport) {this.network = new BoundedHTTP(target, transport);}

  state(scope: DraftScope, id: string) {
    return this.network.owned(async signal => configuration(
      await this.network.get(BASE + identifier(id) + '/execution', scope.context, signal), id));
  }

  send(scope: DraftScope, request: AutomationExecutionRequest) {
    return this.network.owned<AutomationExecutionOutcome>(async signal => {
      const token = csrf(await this.network.get('auth/csrf', scope.context, signal));
      const configure = request.kind === 'configure';
      const route = BASE + identifier(request.ruleId) + (configure ? '/execution' : '/runs');
      const body = JSON.stringify(configure
        ? {rule_revision: request.ruleRevision, expected_control_revision: request.controlRevision, enabled: request.enabled}
        : {rule_revision: request.ruleRevision, control_revision: request.controlRevision});
      const reply = await this.network.request(route, 'POST', scope.context, body, identifier(request.key), token, signal);
      if (reply.status === 200) return receipt(reply.value, scope, request);
      if ([404, 409, 422].includes(reply.status)) {
        const code = errorCode(reply.value);
        return {kind: code === 'revision_conflict' ? 'stale' : code === 'automation_disabled' ? 'disabled' : 'rejected'};
      }
      return readFailure(reply.status, reply.value);
    });
  }

  original(scope: DraftScope, request: AutomationExecutionRequest) {
    return this.network.owned<AutomationExecutionOutcome>(async signal => {
      const route = 'automation/execution/requests/' + request.kind + '/' + identifier(request.key);
      const reply = await this.network.request(route, 'GET', scope.context, null, null, null, signal);
      if (reply.status === 200) return receipt(reply.value, scope, request);
      if (reply.status === 404 && errorCode(reply.value) === 'operation_missing') return {kind: 'missing'};
      return readFailure(reply.status, reply.value);
    });
  }
}
