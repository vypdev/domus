import {expect, test, vi} from 'vitest';
import {CalendarController} from '../src/application/calendar-controller';
import type {CalendarScope} from '../src/application/calendar-controller';
import {CALENDAR_MODES, DATE_MAX, WEEK_STARTS, calendarDays, calendarPeriod, calendarQuery, calendarToday, civilDate} from '../src/domain/calendar';
import type {CalendarEntry, CalendarPage, CalendarQuery} from '../src/domain/calendar';

const query: CalendarQuery = {start: '2026-11-01', end: '2026-12-01', kind: '', timing: '', state: '', priority: '', category: '', own: false};
const scope: CalendarScope = {key: 'one', memberId: 'member', context: {installationId: 'installation', channel: 'edge', subject: 'subject'}};
const row: CalendarEntry = {id: 'planned:one', kind: 'planned', title: 'Original', day: query.start, time: null, zone: null,
  nominal: null, resolved: null, verification: null, relativeReviewRequired: false};

test('civil calendar boundaries use the household day across DST and constrain untrusted intent', () => {
  expect(calendarToday(Date.UTC(2026, 10, 1, 1), 'America/New_York')).toBe('2026-10-31');
  expect(calendarToday(Date.UTC(2026, 10, 1, 1), 'Europe/Madrid')).toBe('2026-11-01');
  expect(calendarPeriod('month', '2024-02-29')).toEqual({start: '2024-02-01', end: '2024-03-01'});
  expect(calendarPeriod('week', '1970-01-01')).toEqual({start: '1970-01-01', end: '1970-01-05'});
  expect(calendarPeriod('week', '2026-11-01')).toEqual({start: '2026-10-26', end: '2026-11-02'});
  expect(calendarPeriod('agenda', '2026-11-01')).toEqual({start: '2026-11-01', end: '2026-12-02'});
  expect(calendarDays(calendarPeriod('day', '2026-11-01'))).toEqual(['2026-11-01']);
  for (const value of [undefined, '', '1969-12-31', '2026-11-31', '2026-99-01']) expect(civilDate(value)).toBe(false);
  // The selectable-anchor ceiling does not cap an exclusive period end.
  expect(calendarPeriod('month', DATE_MAX)).toEqual({start: '9998-12-01', end: '9999-01-01'});
  expect(civilDate('9999-01-01')).toBe(true);
  for (const mode of CALENDAR_MODES) for (const weekStart of WEEK_STARTS) {
    const period = calendarPeriod(mode, DATE_MAX, weekStart);
    expect(calendarQuery({...query, ...period})).toBe(true);
    expect(calendarDays(period).length).toBeGreaterThan(0);
  }
  expect(calendarQuery(query)).toBe(true);
  expect(calendarQuery({...query, kind: 'due', timing: 'manual', state: 'available', priority: 'normal'})).toBe(true);
  for (const value of [null, 0, {...query, other: false}, {...query, start: ''}, {...query, end: ''},
    {...query, end: query.start}, {...query, end: '2028-11-01'}, {...query, kind: 'other'}, {...query, timing: 'other'},
    {...query, state: 'other'}, {...query, priority: 'other'}, {...query, category: false}, {...query, category: 'x'.repeat(65)},
    {...query, own: 1}]) expect(calendarQuery(value)).toBe(false);
});

test('calendar cancels superseded reads, clears prior members and paginates under the same verified scope', async () => {
  const calls: Array<ReturnType<typeof Promise.withResolvers<CalendarPage>> & {cancel: ReturnType<typeof vi.fn>}> = [];
  const server = {read: vi.fn((_context, _member, _query, _cursor) => {
    const pending = {...Promise.withResolvers<CalendarPage>(), cancel: vi.fn()}; calls.push(pending);
    return {result: pending.promise, cancel: pending.cancel};
  })};
  const publish = vi.fn();
  const controller = new CalendarController(server, publish);
  await controller.load(query); await controller.more(); controller.bind(null);
  expect(server.read).not.toHaveBeenCalled();
  controller.bind(scope); controller.bind({...scope}); await controller.more();
  expect(publish).toHaveBeenCalledExactlyOnceWith({status: 'idle', page: null});
  const stale = controller.load(query);
  const read = controller.load(query);
  expect(calls[0].cancel).toHaveBeenCalledOnce();
  calls[0].resolve({entries: [row], count: 1, occurrenceCount: 1, cursor: null, pending: false}); await stale;
  expect(publish).toHaveBeenLastCalledWith({status: 'loading', page: null});
  const page = {entries: [row], count: 2, occurrenceCount: 2, cursor: 'cursor-1', pending: true};
  calls[1].resolve(page); await read;
  expect(publish).toHaveBeenLastCalledWith({status: 'ready', page});
  const more = controller.more();
  expect(server.read).toHaveBeenLastCalledWith(scope.context, scope.memberId, query, 'cursor-1');
  await controller.more();
  const next = {...row, title: 'Updated'};
  const other = {...row, id: 'due:two', kind: 'due' as const};
  calls[2].resolve({entries: [next, other], count: 2, occurrenceCount: 2, cursor: null, pending: false}); await more;
  expect(publish).toHaveBeenLastCalledWith({status: 'ready', page: {entries: [next, other], count: 2, occurrenceCount: 2, cursor: null, pending: false}});
  await controller.more(); expect(calls).toHaveLength(3);
  const fail = controller.load(query);
  calls[3].reject(new Error('current error')); await fail;
  expect(publish).toHaveBeenLastCalledWith({status: 'unavailable', page: null});
  const previousMember = controller.load(query);
  controller.bind({...scope, key: 'two', memberId: 'new'});
  calls[4].reject(new Error('stale error')); await previousMember;
  expect(calls[4].cancel).toHaveBeenCalledOnce();
  expect(publish).toHaveBeenLastCalledWith({status: 'idle', page: null});
  controller.bind(null);
});
