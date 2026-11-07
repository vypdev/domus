/** Independent, bounded session storage for exact recurrence intents. */
import type {ReviewJournal, ReviewRecord} from '../application/recurrence-review-controller';
import {JOURNAL_LIFETIME, JOURNAL_MAX_BYTES, JOURNAL_MAX_RECORDS, JournalError} from '../domain/journal';
import {reviewCommand} from '../domain/recurrence-review';
import {taskIdentifier} from '../domain/tasks';
import type {OwnedStorage} from './session-journal';
import {check, choice, fields} from './json-values';

export const RECURRENCE_JOURNAL_KEY = 'domus.recurrence.journal.v1';

function bytes(raw: string): void {
  if (raw.length > JOURNAL_MAX_BYTES || new TextEncoder().encode(raw).byteLength > JOURNAL_MAX_BYTES)
    throw new JournalError('journal_too_large');
}
function time(value: unknown): number {
  check(typeof value === 'number' && Number.isSafeInteger(value) && value >= 0); return value;
}
function validate(value: unknown, now: number): readonly ReviewRecord[] {
  check(Array.isArray(value) && value.length <= JOURNAL_MAX_RECORDS);
  const records = value.map(raw => {
    const item = fields(raw, ['key','command','createdAt','status','operationId'], []);
    const createdAt = time(item.createdAt); check(createdAt <= now);
    const status = choice(item.status, ['pending','received'] as const);
    const operationId = status === 'received' ? taskIdentifier(item.operationId) : null;
    check(status === 'received' || item.operationId === null);
    return Object.freeze({key: taskIdentifier(item.key), command: reviewCommand(item.command), createdAt, status, operationId});
  });
  check(new Set(records.map(item => item.key)).size === records.length);
  return Object.freeze(records.filter(item => now - item.createdAt < JOURNAL_LIFETIME));
}
export class RecurrenceSessionJournal implements ReviewJournal {
  private active: Readonly<{scope: string; encoded: string; observedAt: number}> | null = null;
  constructor(private readonly storage: Pick<OwnedStorage, 'getItem' | 'setItem'>) {}
  detach(): void {this.active = null;}
  private persist(prior: string | null, scope: string, now: number, input: unknown): readonly ReviewRecord[] {
    this.detach();
    check(this.storage.getItem(RECURRENCE_JOURNAL_KEY) === prior);
    const records = validate(input, time(now));
    const encoded = JSON.stringify({namespace: 'recurrence', version: 1, scope, observedAt: now, records});
    bytes(encoded);
    this.storage.setItem(RECURRENCE_JOURNAL_KEY, encoded);
    check(this.storage.getItem(RECURRENCE_JOURNAL_KEY) === encoded);
    this.active = {scope, encoded, observedAt: now};
    return records;
  }
  open(scope: string, now: number): readonly ReviewRecord[] {
    this.detach();
    const raw = this.storage.getItem(RECURRENCE_JOURNAL_KEY);
    if (raw === null) return this.persist(null, scope, now, []);
    bytes(raw);
    const parsed: unknown = JSON.parse(raw);
    check(JSON.stringify(parsed) === raw);
    const state = fields(parsed, ['namespace','version','scope','observedAt','records'], []);
    check(state.namespace === 'recurrence' && state.version === 1 && typeof state.scope === 'string' && time(state.observedAt) <= time(now));
    const records = validate(state.records, time(state.observedAt));
    return this.persist(raw, scope, now, state.scope === scope ? records : []);
  }
  save(scope: string, now: number, records: readonly ReviewRecord[]): readonly ReviewRecord[] {
    const prior = this.active;
    check(prior?.scope === scope && now >= prior.observedAt);
    return this.persist(prior.encoded, scope, now, records);
  }
}
