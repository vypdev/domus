/** Exact allocation requests use the shared, scoped transport and checked receipts. */
import type {AllocationOutcome, AllocationRequest, AllocationScope, AllocationServer, AllocationWork} from '../application/allocation-controller';
import {revisionValue} from '../domain/administration';
import {allocationPerformers, manualPointShares} from '../domain/point-allocation';
import type {AllocationInput, AllocationSettings, PolicySetting} from '../domain/point-allocation';
import {allocationPolicy, allocationPreview} from './allocation-values';
import {BoundedHTTP} from './http-transport';
import type {FetchTransport} from './http-transport';
import {csrf, failure} from './http-values';
import type {EntryEndpoint} from './http-values';
import {check, choice, fields, identifier, responseRevision} from './json-values';

const BASE = 'family/allocation';

function setting(value: unknown): PolicySetting | null {
  if (value === null) return null;
  const item = fields(value, ['policy', 'revision'], []);
  return {policy: item.policy === null ? null : allocationPolicy(item.policy), revision: responseRevision(item.revision)};
}

function receipt(value: unknown, request: AllocationRequest): AllocationOutcome {
  const row = fields(value, ['state','archived_by','operation_id','created_at','result','message','action_required'], []);
  const state = choice(row.state, ['committed', 'historical'] as const);
  check(state === 'historical' ? identifier(row.archived_by) : row.archived_by === null);
  identifier(row.operation_id);
  const result = fields(row.result, ['definition_id', 'setting'], []);
  const committed = setting(result.setting);
  check(committed !== null && result.definition_id === request.definitionId
    && BigInt(committed.revision) === BigInt(request.revision) + 1n
    && JSON.stringify(committed.policy) === JSON.stringify(request.policy));
  return state === 'historical' ? 'historical' : 'saved';
}

export class HttpAllocationServer implements AllocationServer {
  private readonly network: BoundedHTTP;
  constructor(target: EntryEndpoint, transport: FetchTransport) {this.network = new BoundedHTTP(target, transport);}

  settings(scope: AllocationScope) {
    return this.network.owned(async (signal): Promise<AllocationSettings> => {
      const route = scope.definitionId === null ? BASE : BASE + '?definition_id=' + identifier(scope.definitionId);
      const row = fields(await this.network.get(route, scope.context, signal), ['household','override'], []);
      const household = setting(row.household), override = setting(row.override);
      check((household === null || household.policy !== null) && (scope.definitionId !== null || override === null));
      return {household, override};
    });
  }

  preview(scope: AllocationScope, work: AllocationWork, draft: AllocationInput) {
    return this.network.owned(async signal => {
      const token = csrf(await this.network.get('auth/csrf', scope.context, signal));
      const performer_ids = allocationPerformers(draft.performerIds, identifier);
      const payload = {occurrence_id: identifier(work.occurrenceId), performer_ids,
        ...draft.manualShares === undefined ? {} : {manual_shares: manualPointShares(draft.manualShares, performer_ids)}};
      const body = '{"expected_revision":' + revisionValue(work.revision) + ',' + JSON.stringify(payload).slice(1);
      const response = await this.network.request(BASE + '/preview', 'POST', scope.context, body, null, token, signal);
      if (response.status === 200) return allocationPreview(response.value, performer_ids);
      failure(response.value);
      if (response.status === 422 && (response.value as {code: unknown}).code === 'points_precision_two_required')
        return 'precisionRequired' as const;
      if ([401,403,409,422].includes(response.status)) return null;
      throw new Error('allocation_unavailable');
    });
  }

  save(scope: AllocationScope, request: AllocationRequest) {
    return this.network.owned(async (signal): Promise<AllocationOutcome> => {
      const token = csrf(await this.network.get('auth/csrf', scope.context, signal));
      const expected = request.revision === '0' ? '0' : revisionValue(request.revision);
      const body = '{"expected_revision":' + expected + ',' + JSON.stringify({
        definition_id: request.definitionId === null ? null : identifier(request.definitionId),
        policy: request.policy === null ? null : allocationPolicy(request.policy),
      }).slice(1);
      const response = await this.network.request(BASE, 'PUT', scope.context, body, identifier(request.key), token, signal);
      if (response.status === 200) return receipt(response.value, request);
      failure(response.value);
      if ([409,422].includes(response.status)) return 'rejected';
      throw new Error('allocation_unavailable');
    });
  }

  original(scope: AllocationScope, request: AllocationRequest) {
    return this.network.owned(async signal => {
      const reply = await this.network.request(BASE + '/requests/' + identifier(request.key), 'GET', scope.context, null, null, null, signal);
      if (reply.status === 200) return receipt(reply.value, request);
      failure(reply.value);
      if (reply.status === 404 && (reply.value as {code: unknown}).code === 'operation_missing') return null;
      throw new Error('allocation_unavailable');
    });
  }
}
