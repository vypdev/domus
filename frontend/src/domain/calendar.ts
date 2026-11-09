/** Calendar modes and range arithmetic operate on civil dates, independent of host time. */
import {TASK_PRIORITIES, TASK_STATES} from './tasks';
import type {TaskPriority, TaskState} from './tasks';

export const WEEK_STARTS = ['monday', 'sunday'] as const;
export type WeekStart = typeof WEEK_STARTS[number];
export const CALENDAR_MODES = ['month', 'week', 'day', 'agenda'] as const;
export const CALENDAR_KINDS = ['planned', 'due', 'performed', 'approval'] as const;
export const CALENDAR_TIMINGS = ['manual', 'fixed_calendar', 'completion_relative'] as const;
export type CalendarMode = typeof CALENDAR_MODES[number];
export type CalendarKind = typeof CALENDAR_KINDS[number];
export type CalendarTiming = typeof CALENDAR_TIMINGS[number];
export interface CalendarPeriod {readonly start: string; readonly end: string;}
export interface CalendarQuery extends CalendarPeriod {
  readonly kind: CalendarKind | '';
  readonly timing: CalendarTiming | '';
  readonly state: TaskState | '';
  readonly priority: TaskPriority | '';
  readonly category: string;
  readonly own: boolean;
}
export interface CalendarEntry {
  readonly id: string;
  readonly kind: CalendarKind;
  readonly title: string;
  readonly day: string;
  readonly time: string | null;
  readonly zone: string | null;
  readonly nominal: string | null;
  readonly resolved: string | null;
  readonly verification: string | null;
  readonly relativeReviewRequired: boolean;
}
export interface CalendarPage {
  readonly entries: readonly CalendarEntry[];
  readonly count: number;
  readonly occurrenceCount: number;
  readonly cursor: string | null;
  readonly pending: boolean;
}

const DAY = 86_400_000;
export const DATE_MIN = '1970-01-01';
export const DATE_MAX = '9998-12-01';

export function civilDate(value: unknown): value is string {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/u.test(value) || value < DATE_MIN) return false;
  const parsed = Date.parse(value + 'T00:00:00Z');
  return Number.isFinite(parsed) && new Date(parsed).toISOString().slice(0, 10) === value;
}

function stamp(value: number): string {return new Date(value).toISOString().slice(0, 10);}

export function calendarWeekOffset(value: Date, weekStart: WeekStart): number {
  return (value.getUTCDay() + (weekStart === 'monday' ? 6 : 0)) % 7;
}

export function calendarPeriod(mode: CalendarMode, anchor: string, weekStart: WeekStart = 'monday'): CalendarPeriod {
  const value = new Date(anchor + 'T00:00:00Z');
  const at = value.getTime();
  if (mode === 'month') {
    return {start: stamp(Date.UTC(value.getUTCFullYear(), value.getUTCMonth(), 1)),
      end: stamp(Date.UTC(value.getUTCFullYear(), value.getUTCMonth() + 1, 1))};
  }
  if (mode === 'week') {
    const first = at - calendarWeekOffset(value, weekStart) * DAY;
    return {start: stamp(Math.max(0, first)), end: stamp(first + 7 * DAY)};
  }
  return {start: anchor, end: stamp(at + (mode === 'day' ? 1 : 31) * DAY)};
}

export function calendarDays(period: CalendarPeriod): readonly string[] {
  const days = (Date.parse(period.end) - Date.parse(period.start)) / DAY;
  return Array.from({length: days}, (_, index) => stamp(Date.parse(period.start) + index * DAY));
}

export function calendarQuery(value: unknown): value is CalendarQuery {
  if (typeof value !== 'object' || value === null || Object.keys(value).length !== 8) return false;
  const entry = value as CalendarQuery;
  return civilDate(entry.start) && civilDate(entry.end) && entry.start < entry.end
    && Date.parse(entry.end) - Date.parse(entry.start) <= 366 * DAY
    && (entry.kind === '' || CALENDAR_KINDS.includes(entry.kind))
    && (entry.timing === '' || CALENDAR_TIMINGS.includes(entry.timing))
    && (entry.state === '' || TASK_STATES.includes(entry.state))
    && (entry.priority === '' || TASK_PRIORITIES.includes(entry.priority))
    && typeof entry.category === 'string' && Array.from(entry.category).length <= 64
    && typeof entry.own === 'boolean';
}

export function calendarToday(time: number, zone: string): string {
  const parts = new Intl.DateTimeFormat('en', {timeZone: zone, year: 'numeric', month: '2-digit', day: '2-digit'}).formatToParts(time);
  const part = (kind: Intl.DateTimeFormatPartTypes) => parts.find(item => item.type === kind)!.value;
  return part('year') + '-' + part('month') + '-' + part('day');
}
