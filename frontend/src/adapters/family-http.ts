/** Family reports use the same context assertion and bounded JSON decoder as other private reads. */
import type {FamilyEntry, FamilyPendingEntry, FamilyReport, FamilyServer, FamilySpending, FamilyWeek} from '../application/family-controller';
import {calendarPeriod, civilDate} from '../domain/calendar';
import type {CalendarPeriod} from '../domain/calendar';
import {rewardCost} from '../domain/rewards';
import type {JournalContext} from '../domain/journal';
import {allocationEvidence} from './allocation-values';
import {BoundedHTTP} from './http-transport';
import type {FetchTransport} from './http-transport';
import type {EntryEndpoint} from './http-values';
import {check, choice, fields, identifier, integer, text} from './json-values';

function optional<T>(value: unknown, decode: (raw: unknown) => T): T | null {
  return value === null ? null : decode(value);
}

function timestamp(value: unknown): number {
  const parsed = integer(value, 0);
  check(parsed <= 8_640_000_000_000_000);
  return parsed;
}

function entry(value: unknown): FamilyEntry {
  const row = fields(value, ['event_id','cycle_id','occurrence_id','title','amount_minor','performed_at',
    'verified_at','posted_at','reverses','policy_version','allocation'], []);
  identifier(row.cycle_id); identifier(row.occurrence_id); identifier(row.policy_version);
  const reverses = optional(row.reverses, identifier);
  const amount = integer(row.amount_minor, -Number.MAX_SAFE_INTEGER);
  check(reverses === null ? amount >= 0 : amount <= 0);
  return {id: identifier(row.event_id), title: text(row.title, 160), amount,
    performedAt: timestamp(row.performed_at), verifiedAt: optional(row.verified_at, timestamp),
    postedAt: timestamp(row.posted_at), reverses, allocation: allocationEvidence(row.allocation)};
}

function pendingEntry(value: unknown): FamilyPendingEntry {
  const row = fields(value, ['cycle_id','title','performed_at','state','allocation'], []);
  return {id: identifier(row.cycle_id), title: text(row.title, 160),
    performedAt: timestamp(row.performed_at), state: choice(row.state, ['verification','posting'] as const),
    allocation: allocationEvidence(row.allocation)};
}

function spendingEntry(value: unknown): FamilySpending {
  const row = fields(value, ['redemption_id','title','cost_minor','posted_at'], []);
  return {redemptionId: identifier(row.redemption_id), title: text(row.title, 160),
    cost: rewardCost(integer(row.cost_minor, 1)), postedAt: timestamp(row.posted_at)};
}

function week(value: unknown): FamilyWeek {
  const row = fields(value, ['period','earned_minor','completed_count'], []);
  const range = fields(row.period, ['start','end'], []);
  check(civilDate(range.start));
  const period = calendarPeriod('week', range.start);
  check(range.start === period.start && range.end === period.end);
  return {period, earned:integer(row.earned_minor, -Number.MAX_SAFE_INTEGER),
    completed:integer(row.completed_count, 0)};
}

function report(value: unknown, expected: CalendarPeriod): FamilyReport {
  const row = fields(value, ['period','time_zone','posted_minor','available_minor','reserved_minor',
    'spent_in_period_minor','spending_count','spending','earned_minor',
    'pending_verification_minor','pending_posting_minor','completed_count','tracked_count','elapsed_ms',
    'pending_count','pending','history','next_cursor'], []);
  const range = fields(row.period, ['start','end'], []);
  check(range.start === expected.start && range.end === expected.end);
  check(Array.isArray(row.history) && row.history.length <= 8);
  check(Array.isArray(row.pending) && row.pending.length <= 4);
  const pending = row.pending.map(pendingEntry), pendingCount = integer(row.pending_count, 0);
  check(pending.length === Math.min(4, pendingCount) && new Set(pending.map(item => item.id)).size === pending.length);
  const completed = integer(row.completed_count, 0), tracked = integer(row.tracked_count, 0);
  const posted = integer(row.posted_minor, -Number.MAX_SAFE_INTEGER);
  const available = integer(row.available_minor, -Number.MAX_SAFE_INTEGER);
  const reserved = integer(row.reserved_minor, 0);
  check(tracked <= completed && pendingCount <= completed && available === posted - reserved);
  check(Array.isArray(row.spending) && row.spending.length <= 4);
  const spendingCount = integer(row.spending_count, 0), spentInPeriod = integer(row.spent_in_period_minor, 0);
  const spending = row.spending.map(spendingEntry), shown = spending.reduce((sum, item) => sum + item.cost, 0);
  check(spending.length === Math.min(spendingCount, 4) && new Set(spending.map(item => item.redemptionId)).size === spending.length);
  check(spendingCount === spending.length ? spentInPeriod === shown : spentInPeriod > shown);
  const zone = text(row.time_zone, 128);
  new Intl.DateTimeFormat('en', {timeZone: zone});
  const history = row.history.map(entry);
  check(new Set(history.map(item => item.id)).size === history.length);
  return {period: expected, zone, posted, available, reserved, spentInPeriod, spendingCount, spending,
    earned: integer(row.earned_minor, -Number.MAX_SAFE_INTEGER),
    pendingVerification: integer(row.pending_verification_minor, 0),
    pendingPosting: integer(row.pending_posting_minor, 0), completed, tracked,
    elapsed: integer(row.elapsed_ms, 0), pendingCount, pending, history,
    cursor: optional(row.next_cursor, raw => text(raw, 512))};
}

export class HttpFamilyServer implements FamilyServer {
  private readonly network: BoundedHTTP;
  constructor(target: EntryEndpoint, transport: FetchTransport) {this.network = new BoundedHTTP(target, transport);}
  overview(context: JournalContext) {
    return this.network.owned(async signal => week(await this.network.get('family/overview', context, signal)));
  }
  read(context: JournalContext, period: CalendarPeriod, cursor: string | null) {
    return this.network.owned(async signal => {
      const query = new URLSearchParams({start: period.start, end: period.end, limit: '8'});
      if (cursor !== null) query.set('cursor', cursor);
      return report(await this.network.get('family?' + query.toString(), context, signal), period);
    });
  }
}
