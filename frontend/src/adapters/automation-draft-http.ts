/** Validate protected draft responses and correlate receipts to their original request. */
import type {AutomationDraftServer, DraftCondition, DraftOutcome, DraftRequest, DraftScope, DraftSummary, SavedAutomationDraft} from '../application/automation-drafts';
import {revisionValue} from '../domain/administration';
import {taskText} from '../domain/tasks';
import {manualRule} from './automation-preview-http';
import {BoundedHTTP, readFailure} from './http-transport';
import type {FetchTransport} from './http-transport';
import {csrf, failure} from './http-values';
import type {EntryEndpoint} from './http-values';
import {boolean, check, choice, fields, identifier, integer, text} from './json-values';
import type {Fields} from './json-values';

const BASE = 'automation/drafts';
const STATUS = ['rule_id', 'revision', 'state', 'enabled'] as const;

function errorCode(value: unknown): string {
  failure(value);
  return (value as {code: string}).code;
}

function inactive(row: Fields) {
  check(row.state === 'draft' && row.enabled === false);
  return {id: identifier(row.rule_id), revision: revisionValue(row.revision)};
}

function summary(value: unknown): DraftSummary {
  const row = fields(value, [...STATUS, 'title'], []);
  return {...inactive(row), title: taskText(row.title, 160, true)};
}

function condition(value: unknown): DraftCondition {
  const row = fields(value, ['kind'], ['child', 'children', 'product_id']);
  switch (choice(row.kind, ['stock_below_minimum', 'not', 'all', 'any'] as const)) {
    case 'stock_below_minimum':
      return {kind: 'stock_below_minimum', product_id: identifier(fields(row, ['kind', 'product_id'], []).product_id)};
    case 'not':
      return {kind: 'not', child: condition(fields(row, ['kind', 'child'], []).child)};
    case 'all':
    case 'any': {
      const {children} = fields(row, ['kind', 'children'], []);
      check(Array.isArray(children) && children.length > 0 && children.length <= 62);
      return {kind: row.kind as 'all' | 'any', children: children.map(condition)};
    }
  }
}

function receipt(value: unknown, scope: DraftScope, request: DraftRequest): DraftOutcome {
  const row = fields(value, ['state', 'archived_by', 'operation_id', 'created_at', 'result', 'message', 'action_required'], []);
  const kind = choice(row.state, ['committed', 'historical'] as const);
  if (kind === 'historical' || row.archived_by !== null) identifier(row.archived_by);
  integer(row.created_at, 0);
  text(row.message, 2048);
  text(row.action_required, 4096);
  const result = fields(row.result, [...STATUS, 'member_id'], []);
  const fact = inactive(result);
  check(result.member_id === scope.memberId
    && (request.ruleId === null || request.ruleId === fact.id)
    && BigInt(fact.revision) === BigInt(request.revision) + 1n);
  return {...fact, kind, operationId: identifier(row.operation_id)};
}

export class HttpAutomationDrafts implements AutomationDraftServer {
  private readonly network: BoundedHTTP;
  constructor(target: EntryEndpoint, transport: FetchTransport) {this.network = new BoundedHTTP(target, transport);}

  list(scope: DraftScope, after: string | null) {
    return this.network.owned(async signal => {
      const route = after === null ? BASE : BASE + '?cursor=' + encodeURIComponent(after);
      const page = fields(await this.network.get(route, scope.context, signal), ['drafts', 'next_cursor'], []);
      check(Array.isArray(page.drafts) && page.drafts.length <= 25);
      const drafts = page.drafts.map(summary);
      check(new Set(drafts.map(draft => draft.id)).size === drafts.length);
      return {drafts, next: page.next_cursor === null ? null : text(page.next_cursor, 512)};
    });
  }

  reopen(scope: DraftScope, id: string) {
    return this.network.owned(async signal => {
      const row = fields(await this.network.get(BASE + '/' + identifier(id), scope.context, signal),
        [...STATUS, 'version', 'trigger', 'condition', 'action'], []);
      const fact = inactive(row);
      const trigger = fields(row.trigger, ['kind'], []);
      const action = fields(row.action, ['kind', 'title'], []);
      check(fact.id === id && integer(row.version, 1) === 1
        && trigger.kind === 'manual' && action.kind === 'task.create');
      return {...fact, title: taskText(action.title, 160, true),
        condition: row.condition === null ? null : condition(row.condition)};
    });
  }

  send(scope: DraftScope, request: DraftRequest) {
    return this.network.owned<DraftOutcome>(async signal => {
      const token = csrf(await this.network.get('auth/csrf', scope.context, signal));
      const body = JSON.stringify({...manualRule(request.rule),
        rule_id: request.ruleId, expected_revision: request.revision});
      const reply = await this.network.request(BASE, 'POST', scope.context, body, identifier(request.key), token, signal);
      if (reply.status === 200) return receipt(reply.value, scope, request);
      if ([404, 409, 422].includes(reply.status)) {
        const code = errorCode(reply.value);
        return {kind: code === 'revision_conflict' ? 'conflict' : 'rejected'};
      }
      return readFailure(reply.status, reply.value);
    });
  }

  previewSaved(scope: DraftScope, draft: SavedAutomationDraft) {
    return this.network.owned(async signal => {
      const token = csrf(await this.network.get('auth/csrf', scope.context, signal));
      const body = JSON.stringify({...manualRule({title: draft.title, productId: null}), condition: draft.condition});
      const reply = await this.network.request('automation/preview', 'POST', scope.context, body, null, token, signal);
      if (reply.status !== 200) return readFailure(reply.status, reply.value);
      const result = fields(reply.value, ['version', 'trigger', 'task_title', 'would_create', 'conditions'], []);
      check(integer(result.version, 1) === 1 && result.trigger === 'manual' && result.task_title === draft.title
        && Array.isArray(result.conditions) && result.conditions.length <= 62);
      return boolean(result.would_create);
    });
  }

  original(scope: DraftScope, request: DraftRequest) {
    return this.network.owned<DraftOutcome>(async signal => {
      const reply = await this.network.request(BASE + '/requests/' + identifier(request.key),
        'GET', scope.context, null, null, null, signal);
      if (reply.status === 200) return receipt(reply.value, scope, request);
      if (reply.status === 404 && errorCode(reply.value) === 'operation_missing') return {kind: 'missing'};
      return readFailure(reply.status, reply.value);
    });
  }
}
