/** One exact in-flight calendar preference in its own closed storage namespace. */
import type {CalendarPreferenceJournal, PreferenceRequest} from '../application/calendar-preferences';
import {revisionValue} from '../domain/administration';
import {WEEK_STARTS} from '../domain/calendar';
import {JOURNAL_LIFETIME} from '../domain/journal';
import {check, choice, fields, identifier, text} from './json-values';
import type {OwnedStorage} from './session-journal';

export const CALENDAR_JOURNAL_KEY = 'domus.calendar-preference.v1';

function encode(request: PreferenceRequest): string {
  return JSON.stringify({namespace:CALENDAR_JOURNAL_KEY,key:request.key,scope:request.scope,createdAt:request.createdAt,
    weekStart:request.weekStart,revision:request.revision});
}
function decode(raw: string): PreferenceRequest {
  check(raw.length <= 2048 && new TextEncoder().encode(raw).length <= 2048);
  const value = fields(JSON.parse(raw), ['namespace','key','scope','createdAt','weekStart','revision'], []);
  check(value.namespace === CALENDAR_JOURNAL_KEY);
  const createdAt = value.createdAt;
  check(typeof createdAt === 'number' && Number.isSafeInteger(createdAt) && createdAt >= 0);
  const request = {key:identifier(value.key),scope:text(value.scope,512),createdAt,
    weekStart:choice(value.weekStart,WEEK_STARTS),revision:revisionValue(value.revision)};
  check(encode(request) === raw);
  return Object.freeze(request);
}

export class CalendarSessionJournal implements CalendarPreferenceJournal {
  constructor(private readonly storage: OwnedStorage) {}

  open(scope: string, now: number): PreferenceRequest | null {
    const raw = this.storage.getItem(CALENDAR_JOURNAL_KEY);
    if (raw === null) return null;
    const request = decode(raw);
    check(request.createdAt <= now);
    if (request.scope === scope && now - request.createdAt < JOURNAL_LIFETIME) return request;
    this.clear(request); return null;
  }

  save(request: PreferenceRequest): void {
    const raw = encode(request);
    decode(raw);
    check(this.storage.getItem(CALENDAR_JOURNAL_KEY) === null);
    this.storage.setItem(CALENDAR_JOURNAL_KEY,raw);
    check(this.storage.getItem(CALENDAR_JOURNAL_KEY) === raw);
  }

  clear(request: PreferenceRequest): void {
    check(this.storage.getItem(CALENDAR_JOURNAL_KEY) === encode(request));
    this.storage.removeItem(CALENDAR_JOURNAL_KEY);
    check(this.storage.getItem(CALENDAR_JOURNAL_KEY) === null);
  }
}
