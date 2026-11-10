/** Scoped reward reads and original-result recovery use the bounded same-origin transport. */
import {REWARD_ERRORS} from '../application/rewards-controller';
import type {RewardError, RewardRequest, RewardResult, RewardsScope, RewardsServer} from '../application/rewards-controller';
import {REDEMPTION_STAGES, rewardCommand, rewardCost, rewardRoles} from '../domain/rewards';
import type {Redemption, RedemptionStage, RewardCommand, RewardOffer, RewardReport} from '../domain/rewards';
import {BoundedHTTP} from './http-transport';
import type {FetchTransport} from './http-transport';
import {csrf, failure} from './http-values';
import type {EntryEndpoint} from './http-values';
import {boolean, check, choice, fields, identifier, integer, responseNonnegativeRevision, responseRevision, text} from './json-values';

const BASE = 'family/rewards';
const DATE_MAX = 8_640_000_000_000_000;

function timestamp(value: unknown): number {
  const time = integer(value, 0); check(time <= DATE_MAX); return time;
}

function offer(value: unknown, eligible: boolean): RewardOffer {
  const row = fields(value, ['offer_id','title','cost_minor','enabled','eligible_roles','revision'], []);
  return {id: identifier(row.offer_id), title: text(row.title, 160), cost: rewardCost(integer(row.cost_minor, 1)),
    enabled: boolean(row.enabled), eligible, roles: rewardRoles(row.eligible_roles), revision: responseRevision(row.revision)};
}

function decision(value: unknown): number | null {
  if (value === null) return null;
  const row = fields(value, ['actor_member_id','at'], []);
  identifier(row.actor_member_id); return timestamp(row.at);
}

function redemption(value: unknown, member: string): Redemption {
  const row = fields(value, ['redemption_id','member_id','offer_id','title','offer_revision','cost_minor','requested_at',
    'stage','revision','approval','closed','cancellation_reason'], []);
  check(row.member_id === member); identifier(row.offer_id); responseRevision(row.offer_revision);
  const stage = choice(row.stage, REDEMPTION_STAGES), requestedAt = timestamp(row.requested_at);
  const approvedAt = decision(row.approval), closedAt = decision(row.closed);
  const cancellationReason = row.cancellation_reason === null ? null : text(row.cancellation_reason, 1000);
  check((stage === 'cancelled') === (cancellationReason !== null)
    && (stage === 'delivered' || stage === 'cancelled') === (closedAt !== null)
    && (stage === 'cancelled' || (stage === 'requested') === (approvedAt === null))
    && (approvedAt === null || approvedAt >= requestedAt) && (closedAt === null || closedAt >= (approvedAt ?? requestedAt)));
  return {id: identifier(row.redemption_id), title: text(row.title, 160), cost: rewardCost(integer(row.cost_minor, 1)),
    stage, revision: responseRevision(row.revision), requestedAt, approvedAt, closedAt, cancellationReason};
}

function report(value: unknown, member: string): RewardReport {
  const row = fields(value, ['enabled','revision','may_manage','balance','catalog','requests','next_cursor'], []);
  const enabled = boolean(row.enabled), revision = responseNonnegativeRevision(row.revision);
  const balance = fields(row.balance, ['posted_minor','reserved_minor'], []);
  const posted = integer(balance.posted_minor, -Number.MAX_SAFE_INTEGER), reserved = integer(balance.reserved_minor, 0);
  const available = posted - reserved;
  check(Number.isSafeInteger(available) && (!enabled || revision !== '0'));
  check(Array.isArray(row.catalog) && row.catalog.length <= 64 && Array.isArray(row.requests) && row.requests.length <= 25);
  const catalog = row.catalog.map(raw => {
    const item = fields(raw, ['offer','eligible'], []);
    return offer(item.offer, boolean(item.eligible));
  });
  const requests = row.requests.map(raw => redemption(raw, member));
  check(new Set(catalog.map(item => item.id)).size === catalog.length && new Set(requests.map(item => item.id)).size === requests.length);
  return {enabled, revision, posted, reserved, available, mayManage: boolean(row.may_manage),
    catalog, requests, cursor: row.next_cursor === null ? null : text(row.next_cursor, 512)};
}

function nextRevision(raw: unknown, expected: string): boolean {
  return BigInt(responseRevision(raw)) === BigInt(expected) + 1n;
}

function stageFrom(result: unknown, command: RewardCommand, scope: RewardsScope): RedemptionStage | null {
  if (command.action === 'reward.configure') {
    const row = fields(result, ['enabled','revision'], []);
    check(row.enabled === command.enabled && nextRevision(row.revision, command.expected_revision));
    return null;
  }
  if (command.action === 'reward.offer') {
    const saved = offer(result, true);
    check((command.offer_id === null || saved.id === command.offer_id) && saved.title === command.title
      && saved.cost === command.cost_minor && saved.enabled === command.enabled
      && JSON.stringify(saved.roles) === JSON.stringify(command.eligible_roles)
      && BigInt(saved.revision) === BigInt(command.expected_revision) + 1n);
    return null;
  }
  const own = command.action === 'reward.request' || command.action === 'reward.cancel';
  const row = fields(result, ['redemption_id','stage','revision', ...own ? ['requester_member_id'] : []], []);
  const id = identifier(row.redemption_id);
  if (own) check(row.requester_member_id === scope.memberId);
  if (command.action === 'reward.request') {
    check(row.stage === 'requested' && nextRevision(row.revision, '0'));
    return 'requested';
  }
  check(id === command.redemption_id);
  if (command.action === 'reward.cancel') {
    check(row.stage === 'cancelled' && nextRevision(row.revision, command.expected_revision));
    return 'cancelled';
  }
  responseRevision(row.revision);
  return command.action === 'reward.approve'
    ? choice(row.stage, ['approved','funding_hold'] as const)
    : choice(row.stage, ['delivered'] as const);
}

function receipt(value: unknown, command: RewardCommand, scope: RewardsScope): RewardResult {
  const row = fields(value, ['state','archived_by','operation_id','created_at','result','message','action_required'], []);
  const kind = choice(row.state, ['committed','historical'] as const);
  check(kind === 'historical' ? identifier(row.archived_by) : row.archived_by === null);
  identifier(row.operation_id); timestamp(row.created_at);
  return {kind, stage: stageFrom(row.result, command, scope)};
}

function body(command: RewardCommand): string {
  if (!('expected_revision' in command)) return JSON.stringify(command);
  const {expected_revision, ...payload} = command;
  return '{"expected_revision":' + expected_revision + ',' + JSON.stringify(payload).slice(1);
}

function fault(value: unknown): RewardError {
  failure(value);
  const {code} = value as {code: RewardError};
  return REWARD_ERRORS.some(known => known === code) ? code : 'rejected';
}

export class HttpRewardsServer implements RewardsServer {
  private readonly network: BoundedHTTP;
  constructor(target: EntryEndpoint, transport: FetchTransport) {this.network = new BoundedHTTP(target, transport);}

  read(scope: RewardsScope, cursor: string | null) {
    return this.network.owned(async signal => {
      const query = new URLSearchParams({limit: '25'});
      if (cursor !== null) query.set('cursor', text(cursor, 512));
      return report(await this.network.get(BASE + '?' + query.toString(), scope.context, signal), scope.memberId);
    });
  }

  send(scope: RewardsScope, original: RewardRequest) {
    return this.network.owned(async (signal): Promise<RewardResult> => {
      const command = rewardCommand(original.command);
      const token = csrf(await this.network.get('auth/csrf', scope.context, signal));
      const reply = await this.network.request(BASE + '/commands', 'POST', scope.context, body(command),
        identifier(original.key), token, signal);
      if (reply.status === 200) return receipt(reply.value, command, scope);
      if ([401,403,409,422].includes(reply.status)) return {kind: 'rejected', reason: fault(reply.value)};
      throw new Error('reward_unavailable');
    });
  }

  original(scope: RewardsScope, original: RewardRequest) {
    return this.network.owned(async signal => {
      const command = rewardCommand(original.command);
      const reply = await this.network.request(BASE + '/requests/' + command.action + '/' + identifier(original.key),
        'GET', scope.context, null, null, null, signal);
      if (reply.status === 200) return receipt(reply.value, command, scope);
      failure(reply.value);
      if (reply.status === 404 && (reply.value as {code: unknown}).code === 'operation_missing') return null;
      throw new Error('reward_unavailable');
    });
  }
}
