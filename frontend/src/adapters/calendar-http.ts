/** Calendar HTTP reads are context-bound and use the shared bounded JSON transport. */
import {CALENDAR_KINDS, CALENDAR_TIMINGS, calendarQuery, civilDate} from '../domain/calendar';
import type {CalendarEntry, CalendarPage, CalendarQuery} from '../domain/calendar';
import {TASK_PRIORITIES, TASK_STATES} from '../domain/tasks';
import type {JournalContext} from '../domain/journal';
import type {CalendarServer} from '../application/calendar-controller';
import {BoundedHTTP} from './http-transport';
import type {FetchTransport} from './http-transport';
import type {EntryEndpoint} from './http-values';
import {boolean, check, choice, fields, identifier, integer, text} from './json-values';

function optional<T>(value: unknown, decode: (raw: unknown) => T): T | null {
  return value === null ? null : decode(value);
}

function entry(value: unknown): CalendarEntry {
  const row = fields(value, ['entry_id','kind','timing','occurrence_id','title','state','priority','categories',
    'member_ids','schedule_id','slot_key','local_date','local_time','instant_ms','time_zone','nominal_local',
    'resolved_local','verification','relative_review_required'], ['category_id']);
  const kind = choice(row.kind, CALENDAR_KINDS), id = text(row.entry_id, 140);
  check(id.startsWith(kind + ':')); identifier(id.slice(kind.length + 1)); identifier(row.occurrence_id);
  choice(row.timing, CALENDAR_TIMINGS); choice(row.state, TASK_STATES); choice(row.priority, TASK_PRIORITIES);
  check(Array.isArray(row.categories) && row.categories.length <= 16 && Array.isArray(row.member_ids) && row.member_ids.length <= 100);
  const categories = row.categories.map(label => text(label, 80));
  if (row.category_id !== undefined) {
    const categoryId = optional(row.category_id, identifier);
    check(categories.length === (categoryId === null ? 0 : 1));
  }
  row.member_ids.forEach(identifier);
  optional(row.schedule_id, identifier); optional(row.slot_key, identifier);
  check(civilDate(row.local_date));
  optional(row.instant_ms, raw => integer(raw, 0));
  return Object.freeze({id, kind, title: text(row.title, 160), day: row.local_date,
    time: optional(row.local_time, raw => text(raw, 16)), zone: optional(row.time_zone, raw => text(raw, 128)),
    nominal: optional(row.nominal_local, raw => text(raw, 28)), resolved: optional(row.resolved_local, raw => text(raw, 28)),
    categoryLabel: categories[0] ?? null, verification: optional(row.verification, raw => choice(raw, ['none','pending','approved','rejected'] as const)),
    relativeReviewRequired: boolean(row.relative_review_required)});
}

function page(value: unknown, expected: CalendarQuery): CalendarPage {
  const row = fields(value, ['period','time_zone','entries','count','occurrence_count','next_cursor','pending'], []);
  const range = fields(row.period, ['start','end'], []);
  check(range.start === expected.start && range.end === expected.end);
  text(row.time_zone, 128);
  check(Array.isArray(row.entries) && row.entries.length <= 25);
  const entries = row.entries.map(entry), count = integer(row.count, 0);
  const occurrenceCount = integer(row.occurrence_count, count === 0 ? 0 : 1);
  check(occurrenceCount <= count);
  check(count >= entries.length && new Set(entries.map(item => item.id)).size === entries.length);
  return Object.freeze({entries: Object.freeze(entries), count, occurrenceCount, pending: boolean(row.pending),
    cursor: optional(row.next_cursor, raw => text(raw, 512))});
}

export class HttpCalendarServer implements CalendarServer {
  private readonly network: BoundedHTTP;
  constructor(target: EntryEndpoint, transport: FetchTransport) {this.network = new BoundedHTTP(target, transport);}
  read(expected: JournalContext, member: string, value: CalendarQuery, cursor: string | null) {
    return this.network.owned(async signal => {
      check(calendarQuery(value));
      const query = new URLSearchParams({start: value.start, end: value.end, limit: '25'});
      for (const name of ['kind','timing','state','priority','category'] as const) {
        if (value[name] !== '') query.set(name, value[name]);
      }
      if (value.own) query.set('member_id', identifier(member));
      if (cursor !== null) query.set('cursor', text(cursor, 512));
      const result = await this.network.get('tasks/calendar?' + query.toString(), expected, signal);
      return page(result, value);
    });
  }
}
