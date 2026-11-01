import {JournalStorageError} from '../application/ports';
import type {CommandJournal, JournalOutcome} from '../application/ports';
import {appendRequest, discardRequest, emptyJournal, inspectJournal, JournalError,
  JOURNAL_MAX_BYTES, recordOutcome} from '../domain/journal';
import type {Journal, JournalCommand, JournalContext} from '../domain/journal';

export const ENTRY_JOURNAL_KEY = 'domus.entry.journal.v1';
export interface OwnedStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}
function decode(raw: string): unknown {
  if (raw.length > JOURNAL_MAX_BYTES || new TextEncoder().encode(raw).byteLength > JOURNAL_MAX_BYTES)
    throw new JournalError('journal_too_large');
  let value: unknown;
  try {value = JSON.parse(raw);}
  catch {throw new JournalError('invalid_journal');}
  // Own writes use this canonical form; duplicates/alternate encodings cannot silently change meaning.
  if (JSON.stringify(value) !== raw) throw new JournalError('invalid_journal');
  return value;
}

/** All provider access is bounded to one owned key. No global host/storage discovery occurs here. */
export class SessionJournal implements CommandJournal {
  private active: Readonly<{journal: Journal; encoded: string}> | null = null;
  constructor(private readonly storage: OwnedStorage | undefined) {}

  private provider(): OwnedStorage {
    if (this.storage === undefined) throw new JournalStorageError('storage_unavailable');
    return this.storage;
  }
  private read(): string | null {
    try {
      const raw = this.provider().getItem(ENTRY_JOURNAL_KEY);
      if (raw !== null && typeof raw !== 'string') throw new JournalStorageError('storage_unavailable');
      return raw;
    }
    catch {throw new JournalStorageError('storage_unavailable');}
  }
  private persist(expected: string | null, journal: Journal): Journal {
    this.active = null;
    if (this.read() !== expected) throw new JournalStorageError('storage_changed');
    const encoded = JSON.stringify(journal);
    decode(encoded);
    try {this.provider().setItem(ENTRY_JOURNAL_KEY, encoded);}
    catch {throw new JournalStorageError('storage_unavailable');}
    if (this.read() !== encoded) throw new JournalStorageError('storage_unconfirmed');
    this.active = {journal, encoded};
    return journal;
  }
  open(context: JournalContext, now: number): Journal {
    this.active = null;
    const raw = this.read();
    const journal = raw === null ? emptyJournal(context, now)
      : inspectJournal(decode(raw), context, now).journal;
    return this.persist(raw, journal);
  }
  private change(update: (journal: Journal) => Journal): Journal {
    const prior = this.active;
    this.active = null;
    if (prior === null) throw new JournalStorageError('journal_not_open');
    return this.persist(prior.encoded, update(prior.journal));
  }
  prepare(key: string, command: JournalCommand, now: number): Journal {
    return this.change(journal => appendRequest(journal, key, command, now));
  }
  record(key: string, outcome: JournalOutcome, now: number): Journal {
    return this.change(journal => recordOutcome(journal, key, outcome, now));
  }
  forget(key: string, now: number): Journal {
    return this.change(journal => discardRequest(journal, key, now));
  }
  detach(): void {this.active = null;}
  clear(): void {
    this.active = null;
    try {this.provider().removeItem(ENTRY_JOURNAL_KEY);}
    catch {throw new JournalStorageError('storage_unavailable');}
    if (this.read() !== null) throw new JournalStorageError('storage_unconfirmed');
  }
}
