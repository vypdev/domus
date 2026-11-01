import type {Journal, JournalCommand, JournalContext, RequestStage} from '../domain/journal';
import type {Authorization, Deployment, EntrySession} from '../domain/entry';

export type JournalOutcome = Readonly<{stage: Exclude<RequestStage, 'prepared'>; operationId: string | null}>;
/** Open only after fresh server context/current-state reads. The journal grants no authority. */
export interface CommandJournal {
  open(context: JournalContext, now: number): Journal;
  prepare(key: string, command: JournalCommand, now: number): Journal;
  record(key: string, outcome: JournalOutcome, now: number): Journal;
  forget(key: string, now: number): Journal;
  detach(): void;
  clear(): void;
}
export type JournalStorageFault = 'storage_unavailable' | 'storage_changed'
  | 'storage_unconfirmed' | 'journal_not_open';
export class JournalStorageError extends Error {
  constructor(readonly code: JournalStorageFault) {super(code); this.name = 'JournalStorageError';}
}

/** Cancellation releases an owned read; it never claims to undo a command. */
export interface EntryRead<T> {readonly result: Promise<T>; cancel(): void;}
export interface VerifiedEntrySession extends EntrySession {
  readonly context: JournalContext;
  readonly deployment: Deployment;
}
export interface HouseholdFacts {
  readonly householdId: string;
  readonly name: string;
  readonly timeZone: string;
  readonly revision: number;
}
export type ReadFault = 'authentication_required' | 'forbidden' | 'unavailable' | 'invalid_response';
export class EntryReadError extends Error {
  constructor(readonly code: ReadFault) {super(code); this.name = 'EntryReadError';}
}
export type JsonValue = null | boolean | number | string | readonly JsonValue[]
  | Readonly<{[key: string]: JsonValue}>;
export interface EntryReceipt {
  readonly kind: 'receipt';
  readonly stage: 'committed' | 'historical';
  readonly operationId: string;
  readonly archivedBy: string | null;
  readonly createdAt: number;
  readonly result: Readonly<{[key: string]: JsonValue}>;
}
export interface EntryOperation extends EntryReceipt {
  readonly delivery: 'pending' | 'delivered' | 'suppressed';
}
export type CommandResult = EntryReceipt
  | Readonly<{kind: 'rejected'; reason: ReadFault | 'conflict' | 'invalid_input'; correlationId: string | null}>
  | Readonly<{kind: 'uncertain'}>;
/** Strict immutable facts bound to expected context; a mismatch fails closed, never selects an actor. */
export interface EntryServer {
  session(): EntryRead<VerifiedEntrySession | null>;
  authorization(expected: JournalContext): EntryRead<Authorization>;
  household(expected: JournalContext): EntryRead<HouseholdFacts>;
  operation(action: JournalCommand['action'], operationId: string, expected: JournalContext): EntryRead<EntryOperation>;
  send(request: JournalCommand & Readonly<{key: string}>, expected: JournalContext): Promise<CommandResult>;
  logout(): Promise<Readonly<{upstreamRevoked: boolean | null}>>;
}
export interface EntryClock {anchor(serverTime: number): void; now(): number;}
export interface EntryEntropy {requestKey(): string;}
