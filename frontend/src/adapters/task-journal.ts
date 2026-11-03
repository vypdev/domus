/** One owned session-storage key retains bounded original task requests, never credentials. */
import {JournalStorageError} from '../application/ports';
import type {TaskJournalPort, TaskJournalScope, TaskRecord} from '../application/task-ports';
import {emptyJournal, JournalError, JOURNAL_LIFETIME, JOURNAL_MAX_BYTES, JOURNAL_MAX_RECORDS} from '../domain/journal';
import {taskCommand, taskIdentifier} from '../domain/tasks';
import type {TaskCommand} from '../domain/tasks';
import type {OwnedStorage} from './session-journal';
export const TASK_JOURNAL_KEY = 'domus.tasks.journal.v1';
interface State {readonly namespace: 'tasks'; readonly version: 1; readonly observedAt: number; readonly records: readonly TaskRecord[];}
function requireValue(condition: unknown): asserts condition {if (!condition) throw new JournalError('invalid_journal');}
function object(value: unknown, keys: readonly string[]): Record<string, unknown> {
  requireValue(typeof value === 'object' && value !== null && !Array.isArray(value)
    && Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key)));
  return value as Record<string, unknown>;
}
function time(value: unknown): number {
  if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < 0) throw new JournalError('invalid_journal_time');
  return value;
}
function scope(value: unknown): TaskJournalScope {
  const item = object(value, ['context', 'householdId', 'memberId']);
  return Object.freeze({context: emptyJournal(item.context as TaskJournalScope['context'], 0).context,
    householdId: taskIdentifier(item.householdId), memberId: taskIdentifier(item.memberId)});
}
export function taskScopeKey(value: TaskJournalScope): string {
  const selected = scope(value);
  return JSON.stringify([selected.context.installationId, selected.context.channel, selected.context.subject, selected.householdId, selected.memberId]);
}
function record(value: unknown, observedAt: number): TaskRecord {
  const item = object(value, ['key', 'command', 'scope', 'createdAt', 'expiresAt', 'stage', 'operationId']);
  const command = taskCommand(item.command); requireValue(command !== undefined);
  const createdAt = time(item.createdAt), expiresAt = time(item.expiresAt);
  if (createdAt > observedAt || expiresAt !== createdAt + JOURNAL_LIFETIME) throw new JournalError('invalid_journal_time');
  requireValue(['prepared', 'uncertain', 'committed', 'historical', 'rejected'].includes(item.stage as string));
  const known = item.stage === 'committed' || item.stage === 'historical';
  const operationId = known ? taskIdentifier(item.operationId) : null; requireValue(known || item.operationId === null);
  return Object.freeze({key: taskIdentifier(item.key), command, scope: scope(item.scope), createdAt, expiresAt,
    stage: item.stage as TaskRecord['stage'], operationId});
}
function snapshot(now: number, records: readonly TaskRecord[]): State {
  return Object.freeze({namespace: 'tasks', version: 1, observedAt: time(now), records: Object.freeze(records)});
}
function inspect(value: unknown, now: number): State {
  const item = object(value, ['namespace', 'version', 'observedAt', 'records']);
  requireValue(item.namespace === 'tasks' && item.version === 1);
  const observedAt = time(item.observedAt); if (time(now) < observedAt) throw new JournalError('invalid_journal_time');
  requireValue(Array.isArray(item.records) && item.records.length <= JOURNAL_MAX_RECORDS);
  const records = item.records.map(raw => record(raw, observedAt));
  const identities = records.map(item => JSON.stringify([taskScopeKey(item.scope), item.key]));
  if (new Set(identities).size !== records.length) throw new JournalError('duplicate_request');
  return snapshot(now, records.filter(item => now < item.expiresAt));
}
function decode(raw: string): unknown {
  if (raw.length > JOURNAL_MAX_BYTES || new TextEncoder().encode(raw).byteLength > JOURNAL_MAX_BYTES)
    throw new JournalError('journal_too_large');
  try {const value: unknown = JSON.parse(raw); requireValue(JSON.stringify(value) === raw); return value;}
  catch {throw new JournalError('invalid_journal');}
}
export class TaskSessionJournal implements TaskJournalPort {
  private active: Readonly<{scope: TaskJournalScope; state: State; encoded: string}> | null = null;
  constructor(private readonly storage: OwnedStorage | undefined) {}
  private read(): string | null {
    try {if (this.storage === undefined) throw Error(); const raw = this.storage.getItem(TASK_JOURNAL_KEY);
      if (raw !== null && typeof raw !== 'string') throw Error(); return raw;
    } catch {throw new JournalStorageError('storage_unavailable');}
  }
  private persist(expected: string | null, state: State, selected: TaskJournalScope): readonly TaskRecord[] {
    this.active = null;
    if (this.read() !== expected) throw new JournalStorageError('storage_changed');
    const encoded = JSON.stringify(state); decode(encoded);
    try {this.storage!.setItem(TASK_JOURNAL_KEY, encoded);} catch {throw new JournalStorageError('storage_unavailable');}
    if (this.read() !== encoded) throw new JournalStorageError('storage_unconfirmed');
    this.active = {scope: selected, state, encoded};
    const key = taskScopeKey(selected); return Object.freeze(state.records.filter(item => taskScopeKey(item.scope) === key));
  }
  open(value: TaskJournalScope, now: number): readonly TaskRecord[] {
    this.active = null; const selected = scope(value), raw = this.read();
    return this.persist(raw, raw === null ? snapshot(now, []) : inspect(decode(raw), now), selected);
  }
  private change(now: number, update: (state: State, selected: TaskJournalScope) => readonly TaskRecord[]): readonly TaskRecord[] {
    const prior = this.active; this.active = null;
    if (prior === null) throw new JournalStorageError('journal_not_open');
    return this.persist(prior.encoded, snapshot(now, update(inspect(prior.state, now), prior.scope)), prior.scope);
  }
  prepare(key: string, command: TaskCommand, now: number): readonly TaskRecord[] {
    return this.change(now, (state, selected) => {
      if (state.records.length >= JOURNAL_MAX_RECORDS) throw new JournalError('journal_capacity');
      if (state.records.some(item => taskScopeKey(item.scope) === taskScopeKey(selected) && item.key === key)) throw new JournalError('duplicate_request');
      return [...state.records, record({key, command, scope: selected, createdAt: now, expiresAt: now + JOURNAL_LIFETIME, stage: 'prepared', operationId: null}, now)];
    });
  }
  private target(state: State, selected: TaskJournalScope, key: string): TaskRecord {
    const original = state.records.find(item => taskScopeKey(item.scope) === taskScopeKey(selected) && item.key === key);
    if (!original) throw new JournalError('request_not_found'); return original;
  }
  record(key: string, stage: Exclude<TaskRecord['stage'], 'prepared'>, operationId: string | null, now: number): readonly TaskRecord[] {
    return this.change(now, (state, selected) => {
      const original = this.target(state, selected, key);
      requireValue(stage !== ('prepared' as string));
      const next = record({...original, stage, operationId}, now);
      if (original.operationId !== null && original.operationId !== next.operationId) throw new JournalError('original_operation_changed');
      return state.records.map(item => item === original ? next : item);
    });
  }
  forget(key: string, now: number): readonly TaskRecord[] {
    return this.change(now, (state, selected) => {
      const original = this.target(state, selected, key);
      if (original.stage === 'prepared' || original.stage === 'uncertain') throw new JournalError('unresolved_request');
      return state.records.filter(item => item !== original);
    });
  }
  detach(): void {this.active = null;}
}
