/** Original administration intents survive retirement; views expose only the freshly verified context. */
import {administrationCommand} from './administration-commands';
import type {AdministrationCommand} from './administration-commands';
import {JournalError, JOURNAL_LIFETIME, JOURNAL_MAX_RECORDS} from './journal';
import type {JournalContext, RequestStage} from './journal';

export type AdministrationRecord = AdministrationCommand & Readonly<{context: JournalContext;
  key: string; createdAt: number; expiresAt: number; stage: RequestStage; operationId: string | null}>;
export interface AdministrationJournal {
  readonly namespace: 'administration'; readonly version: 1; readonly observedAt: number;
  readonly records: readonly AdministrationRecord[];
}
export interface AdministrationJournalView {
  readonly context: JournalContext; readonly observedAt: number; readonly records: readonly AdministrationRecord[];
}
export type AdministrationOutcome = Readonly<{stage: Exclude<RequestStage, 'prepared'>; operationId: string | null}>;
type Fields = Record<string, unknown>;
function check(condition: unknown): asserts condition {
  if (!condition) throw new JournalError('invalid_journal');
}
function fields(value: unknown, required: readonly string[], optional: readonly string[] = []): Fields {
  check(typeof value === 'object' && value !== null && !Array.isArray(value));
  check(required.every(key => Object.hasOwn(value, key))
    && Object.keys(value).every(key => required.includes(key) || optional.includes(key)));
  return value as Fields;
}
function identifier(value: unknown): string {
  check(typeof value === 'string' && /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/u.test(value)); return value;
}
function scope(value: unknown): JournalContext {
  const item = fields(value, ['installationId', 'channel', 'subject']);
  check(typeof item.installationId === 'string'
    && /^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$/u.test(item.installationId)
    && (item.channel === 'stable' || item.channel === 'edge')
    && typeof item.subject === 'string' && /^[a-f0-9]{32}$/u.test(item.subject));
  return Object.freeze({installationId: item.installationId, channel: item.channel, subject: item.subject});
}
function time(value: unknown): number {
  if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < 0)
    throw new JournalError('invalid_journal_time');
  return value;
}
function same(left: JournalContext, right: JournalContext): boolean {
  return left.installationId === right.installationId && left.channel === right.channel && left.subject === right.subject;
}
function record(value: unknown, observedAt: number): AdministrationRecord {
  const item = fields(value, ['context', 'key', 'action', 'payload', 'createdAt', 'expiresAt', 'stage', 'operationId'], ['memberId']);
  const context = scope(item.context), key = identifier(item.key);
  const createdAt = time(item.createdAt), expiresAt = time(item.expiresAt);
  if (createdAt > observedAt || expiresAt !== createdAt + JOURNAL_LIFETIME)
    throw new JournalError('invalid_journal_time');
  check(['prepared', 'uncertain', 'committed', 'historical', 'rejected'].includes(item.stage as string));
  const known = item.stage === 'committed' || item.stage === 'historical';
  if (known) identifier(item.operationId); else check(item.operationId === null);
  const input = Object.hasOwn(item, 'memberId') ? {action: item.action, memberId: item.memberId, payload: item.payload}
    : {action: item.action, payload: item.payload};
  const command = administrationCommand(input);
  return Object.freeze({...command, context, key, createdAt, expiresAt,
    stage: item.stage as RequestStage, operationId: item.operationId as string | null});
}
function snapshot(observedAt: number, records: readonly AdministrationRecord[]): AdministrationJournal {
  return Object.freeze({namespace: 'administration', version: 1, observedAt, records: Object.freeze(records)});
}
export function emptyAdministrationJournal(now: number): AdministrationJournal {return snapshot(time(now), []);}
export function inspectAdministrationJournal(value: unknown, now: number): AdministrationJournal {
  try {
    now = time(now);
    const item = fields(value, ['namespace', 'version', 'observedAt', 'records']);
    check(item.namespace === 'administration' && item.version === 1);
    const observedAt = time(item.observedAt);
    if (now < observedAt) throw new JournalError('invalid_journal_time');
    check(Array.isArray(item.records) && item.records.length <= JOURNAL_MAX_RECORDS);
    const records = item.records.map(value => record(value, observedAt));
    const keys = records.map(item => JSON.stringify([item.context.installationId, item.context.channel, item.context.subject, item.key]));
    if (new Set(keys).size !== records.length) throw new JournalError('duplicate_request');
    return snapshot(now, records.filter(item => now < item.expiresAt));
  } catch (error) {
    if (error instanceof JournalError) throw error;
    throw new JournalError('invalid_journal');
  }
}
export function administrationView(journal: AdministrationJournal, context: JournalContext, now: number): AdministrationJournalView {
  const current = inspectAdministrationJournal(journal, now), selected = scope(context);
  return Object.freeze({context: selected, observedAt: current.observedAt,
    records: Object.freeze(current.records.filter(item => same(item.context, selected)))});
}
export function prepareAdministration(journal: AdministrationJournal, context: JournalContext,
  key: string, command: AdministrationCommand, now: number): AdministrationJournal {
  const prior = inspectAdministrationJournal(journal, now), selected = scope(context);
  if (prior.records.length >= JOURNAL_MAX_RECORDS) throw new JournalError('journal_capacity');
  if (prior.records.some(item => same(item.context, selected) && item.key === key)) throw new JournalError('duplicate_request');
  const next = record({...administrationCommand(command), context: selected, key, createdAt: now,
    expiresAt: now + JOURNAL_LIFETIME, stage: 'prepared', operationId: null}, now);
  return snapshot(now, [...prior.records, next]);
}
function target(journal: AdministrationJournal, context: JournalContext, key: string): AdministrationRecord {
  const selected = scope(context);
  const original = journal.records.find(item => same(item.context, selected) && item.key === key);
  if (!original) throw new JournalError('request_not_found');
  return original;
}
export function recordAdministration(journal: AdministrationJournal, context: JournalContext,
  key: string, outcome: AdministrationOutcome, now: number): AdministrationJournal {
  const prior = inspectAdministrationJournal(journal, now), original = target(prior, context, key);
  const change = fields(outcome, ['stage', 'operationId']);
  check(change.stage !== 'prepared');
  const next = record({...original, ...change}, now);
  if (original.operationId !== null && original.operationId !== next.operationId) throw new JournalError('original_operation_changed');
  return snapshot(now, prior.records.map(item => item === original ? next : item));
}
export function forgetAdministration(journal: AdministrationJournal, context: JournalContext,
  key: string, now: number): AdministrationJournal {
  const prior = inspectAdministrationJournal(journal, now), original = target(prior, context, key);
  if (original.stage === 'prepared' || original.stage === 'uncertain') throw new JournalError('unresolved_request');
  return snapshot(now, prior.records.filter(item => item !== original));
}
