import {setupPayload} from './entry';
import type {SetupPayload} from './entry';

export const JOURNAL_LIFETIME = 3_600_000;
export const JOURNAL_MAX_RECORDS = 8;
export const JOURNAL_MAX_BYTES = 65_536;
export interface JournalContext {
  readonly installationId: string;
  readonly channel: 'stable' | 'edge';
  readonly subject: string;
}
export type JournalCommand = Readonly<{action: 'setup'; payload: SetupPayload}>
  | Readonly<{action: 'enroll'; payload: Readonly<{expected_revision: 0}>}>;
export type RequestStage = 'prepared' | 'uncertain' | 'committed' | 'historical' | 'rejected';
export type JournalRecord = JournalCommand & Readonly<{key: string; createdAt: number;
  expiresAt: number; stage: RequestStage; operationId: string | null}>;
export interface Journal {
  readonly version: 1;
  readonly context: JournalContext;
  readonly observedAt: number;
  readonly records: readonly JournalRecord[];
}
export type JournalFault = 'invalid_journal' | 'invalid_journal_time' | 'journal_too_large'
  | 'journal_capacity' | 'duplicate_request' | 'request_not_found' | 'unresolved_request'
  | 'original_operation_changed';
export class JournalError extends Error {
  constructor(readonly code: JournalFault) {super(code); this.name = 'JournalError';}
}
type Fields = Record<string, unknown>;
function invalid(): never {throw new JournalError('invalid_journal');}
function object(value: unknown, keys: readonly string[]): Fields {
  if (typeof value !== 'object' || value === null || Array.isArray(value)
      || Object.keys(value).length !== keys.length || !keys.every(key => Object.hasOwn(value, key)))
    return invalid();
  return value as Fields;
}
function identifier(value: unknown): value is string {
  return typeof value === 'string' && /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/u.test(value);
}
function scope(value: unknown): JournalContext {
  const item = object(value, ['installationId', 'channel', 'subject']);
  if (typeof item.installationId !== 'string'
      || !/^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$/u.test(item.installationId)
      || (item.channel !== 'stable' && item.channel !== 'edge') || !identifier(item.subject))
    return invalid();
  return Object.freeze({installationId: item.installationId, channel: item.channel, subject: item.subject});
}
function time(value: unknown): number {
  if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < 0)
    throw new JournalError('invalid_journal_time');
  return value;
}
function command(value: unknown): JournalCommand {
  const item = object(value, ['action', 'payload']);
  if (item.action === 'setup') {
    const body = object(item.payload, ['name', 'time_zone', 'expected_revision', 'mapping_mode']);
    if (!setupPayload(body.name, body.time_zone).ok || body.expected_revision !== 0
        || body.mapping_mode !== 'all_ha_administrators') return invalid();
    // Validation never substitutes normalized values for the original submitted command.
    return Object.freeze({action: 'setup', payload: Object.freeze({name: body.name as string,
      time_zone: body.time_zone as string, expected_revision: 0, mapping_mode: 'all_ha_administrators'})});
  }
  if (item.action !== 'enroll') return invalid();
  const body = object(item.payload, ['expected_revision']);
  if (body.expected_revision !== 0) return invalid();
  return Object.freeze({action: 'enroll', payload: Object.freeze({expected_revision: 0})});
}
function record(value: unknown, observedAt: number): JournalRecord {
  const item = object(value, ['key', 'action', 'payload', 'createdAt', 'expiresAt', 'stage', 'operationId']);
  if (!identifier(item.key) || !['prepared', 'uncertain', 'committed', 'historical', 'rejected']
    .includes(item.stage as string)) return invalid();
  const createdAt = time(item.createdAt), expiresAt = time(item.expiresAt);
  if (createdAt > observedAt || expiresAt !== createdAt + JOURNAL_LIFETIME)
    throw new JournalError('invalid_journal_time');
  const known = item.stage === 'committed' || item.stage === 'historical';
  if (known ? !identifier(item.operationId) : item.operationId !== null) return invalid();
  return Object.freeze({...command({action: item.action, payload: item.payload}), key: item.key,
    createdAt, expiresAt, stage: item.stage as RequestStage, operationId: item.operationId as string | null});
}
function snapshot(context: JournalContext, observedAt: number, records: JournalRecord[]): Journal {
  return Object.freeze({version: 1, context, observedAt, records: Object.freeze(records)});
}
export function emptyJournal(context: JournalContext, now: number): Journal {
  return snapshot(scope(context), time(now), []);
}
export function inspectJournal(value: unknown, expected: JournalContext, now: number):
  Readonly<{kind: 'current' | 'context_changed'; journal: Journal}> {
  const context = scope(expected); now = time(now);
  const item = object(value, ['version', 'context', 'observedAt', 'records']);
  if (item.version !== 1) return invalid();
  const original = scope(item.context);
  if (original.installationId !== context.installationId || original.channel !== context.channel
      || original.subject !== context.subject)
    return Object.freeze({kind: 'context_changed', journal: emptyJournal(context, now)});
  const observedAt = time(item.observedAt);
  if (now < observedAt) throw new JournalError('invalid_journal_time');
  if (!Array.isArray(item.records) || item.records.length > JOURNAL_MAX_RECORDS) return invalid();
  const records = item.records.map(value => record(value, observedAt));
  if (new Set(records.map(item => item.key)).size !== records.length)
    throw new JournalError('duplicate_request');
  return Object.freeze({kind: 'current', journal: snapshot(context, now,
    records.filter(item => now < item.expiresAt))});
}
function current(journal: Journal, now: number): Journal {
  return inspectJournal(journal, journal.context, now).journal;
}
export function appendRequest(journal: Journal, key: string, input: JournalCommand, now: number): Journal {
  const prior = current(journal, now);
  if (prior.records.length >= JOURNAL_MAX_RECORDS) throw new JournalError('journal_capacity');
  if (prior.records.some(item => item.key === key)) throw new JournalError('duplicate_request');
  const next = record({...command(input), key, createdAt: now, expiresAt: now + JOURNAL_LIFETIME,
    stage: 'prepared', operationId: null}, now);
  return snapshot(prior.context, now, [...prior.records, next]);
}
function target(journal: Journal, key: string): JournalRecord {
  const item = journal.records.find(item => item.key === key);
  if (!item) throw new JournalError('request_not_found');
  return item;
}
export function recordOutcome(journal: Journal, key: string,
  outcome: Readonly<{stage: Exclude<RequestStage, 'prepared'>; operationId: string | null}>, now: number): Journal {
  const prior = current(journal, now), original = target(prior, key);
  const fields = object(outcome, ['stage', 'operationId']);
  if (fields.stage === 'prepared') return invalid();
  const next = record({...original, ...fields}, now);
  if (original.operationId !== null && original.operationId !== next.operationId)
    throw new JournalError('original_operation_changed');
  return snapshot(prior.context, now, prior.records.map(item => item.key === key ? next : item));
}
export function discardRequest(journal: Journal, key: string, now: number): Journal {
  const prior = current(journal, now), original = target(prior, key);
  if (original.stage === 'prepared' || original.stage === 'uncertain')
    throw new JournalError('unresolved_request');
  return snapshot(prior.context, now, prior.records.filter(item => item.key !== key));
}
