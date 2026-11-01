import type {Journal, JournalCommand, JournalContext, RequestStage} from '../domain/journal';

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
