import type {DraftScope} from '../application/automation-drafts';
import type {DailyOutcome, DailyRequest, DailyServer} from '../application/automation-daily';
import {revisionValue} from '../domain/administration';
import type {Revision} from '../domain/administration';
import {BoundedHTTP, readFailure} from './http-transport';
import type {FetchTransport} from './http-transport';
import {csrf, failure} from './http-values';
import type {EntryEndpoint} from './http-values';
import {boolean, check, choice, fields, identifier, integer, text} from './json-values';
import {dailyReview, dailyTime, dailyTimeBody, MAX_DAILY_INSTANT} from './automation-daily-values';

function receipt(value: unknown, scope: DraftScope, request: DailyRequest): DailyOutcome {
  const row = fields(value, ['state', 'archived_by', 'operation_id', 'created_at', 'result', 'message', 'action_required'], []);
  const kind = choice(row.state, ['committed', 'historical'] as const);
  check((kind === 'historical') === (row.archived_by !== null));
  if (row.archived_by !== null) identifier(row.archived_by);
  check(integer(row.created_at, 0) <= MAX_DAILY_INSTANT);
  text(row.message, 2048); text(row.action_required, 4096);
  const result = fields(row.result, ['rule_id', 'rule_revision', 'control_revision', 'schedule_revision',
    'enabled', 'grant_id', 'approved_next', 'member_id'], []);
  const next = dailyTime(result.approved_next, true);
  check(identifier(result.rule_id) === request.ruleId && revisionValue(result.rule_revision) === request.ruleRevision
    && BigInt(revisionValue(result.control_revision)) === BigInt(request.controlRevision) + 1n
    && BigInt(revisionValue(result.schedule_revision)) === BigInt(request.scheduleRevision) + 1n
    && boolean(result.enabled) === (request.kind !== 'disable') && result.member_id === scope.memberId);
  identifier(result.grant_id);
  if (request.reviewed !== undefined) check(JSON.stringify(next) === JSON.stringify(request.reviewed));
  return {kind, action: request.kind, ruleId: request.ruleId, ruleRevision: request.ruleRevision,
    operationId: identifier(row.operation_id), next};
}

function errorCode(value: unknown): string {failure(value); return (value as {code: string}).code;}

export class HttpDailyAutomation implements DailyServer {
  private readonly network: BoundedHTTP;
  constructor(target: EntryEndpoint, transport: FetchTransport) {this.network = new BoundedHTTP(target, transport);}

  active(scope: DraftScope, ruleId: string) {
    return this.network.owned(async signal => {
      const value = await this.network.get('automation/drafts/' + identifier(ruleId) + '/daily/active', scope.context, signal);
      if (value === null) return null;
      const review = dailyReview(value, ruleId, null);
      check(review.activeTrigger === 'daily' && review.activeRevision === review.ruleRevision);
      return review;
    });
  }

  review(scope: DraftScope, ruleId: string, revision: Revision) {
    return this.network.owned(async signal => dailyReview(await this.network.get(
      'automation/drafts/' + identifier(ruleId) + '/daily?revision=' + revisionValue(revision), scope.context, signal), ruleId, revision));
  }

  send(scope: DraftScope, request: DailyRequest) {
    return this.network.owned<DailyOutcome>(async signal => {
      const token = csrf(await this.network.get('auth/csrf', scope.context, signal));
      const body = {rule_revision: request.ruleRevision, expected_control_revision: request.controlRevision,
        expected_schedule_revision: request.scheduleRevision,
        ...(request.reviewed === undefined ? {} : {reviewed: dailyTimeBody(request.reviewed)})};
      const reply = await this.network.request('automation/drafts/' + identifier(request.ruleId) + '/daily/' + request.kind,
        'POST', scope.context, JSON.stringify(body), identifier(request.key), token, signal);
      if (reply.status === 200) return receipt(reply.value, scope, request);
      if ([404, 409, 422].includes(reply.status)) {
        const code = errorCode(reply.value);
        return {kind: code === 'revision_conflict' ? 'stale' : code === 'automation_timing_review_changed' ? 'timing_changed'
          : code === 'automation_disabled' ? 'disabled' : 'rejected'};
      }
      return readFailure(reply.status, reply.value);
    });
  }

  original(scope: DraftScope, request: DailyRequest) {
    return this.network.owned<DailyOutcome>(async signal => {
      const reply = await this.network.request('automation/daily/requests/' + request.kind + '/' + identifier(request.key),
        'GET', scope.context, null, null, null, signal);
      if (reply.status === 200) return receipt(reply.value, scope, request);
      if (reply.status === 404 && errorCode(reply.value) === 'operation_missing') return {kind: 'missing'};
      return readFailure(reply.status, reply.value);
    });
  }
}
