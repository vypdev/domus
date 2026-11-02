/** One owned storage key, global bounds and readback fencing; no network or automatic mutation. */
import {JournalStorageError} from '../application/ports';
import type {AdministrationJournalPort} from '../application/administration-ports';
import {administrationView, emptyAdministrationJournal, forgetAdministration,
  inspectAdministrationJournal, prepareAdministration, recordAdministration} from '../domain/administration-journal';
import type {AdministrationJournal, AdministrationJournalView, AdministrationOutcome} from '../domain/administration-journal';
import type {AdministrationCommand} from '../domain/administration-commands';
import {JournalError, JOURNAL_MAX_BYTES} from '../domain/journal';
import type {JournalContext} from '../domain/journal';
import type {OwnedStorage} from './session-journal';

export const ADMINISTRATION_JOURNAL_KEY = 'domus.administration.journal.v1';
function decode(raw: string): unknown {
  if (raw.length > JOURNAL_MAX_BYTES || new TextEncoder().encode(raw).byteLength > JOURNAL_MAX_BYTES)
    throw new JournalError('journal_too_large');
  let value: unknown;
  try {value = JSON.parse(raw);} catch {throw new JournalError('invalid_journal');}
  if (JSON.stringify(value) !== raw) throw new JournalError('invalid_journal');
  return value;
}
export class AdministrationSessionJournal implements AdministrationJournalPort {
  private active: Readonly<{journal: AdministrationJournal; encoded: string; context: JournalContext}> | null = null;
  constructor(private readonly storage: OwnedStorage | undefined) {}

  private provider(): OwnedStorage {
    if (this.storage === undefined) throw new JournalStorageError('storage_unavailable');
    return this.storage;
  }
  private read(): string | null {
    try {
      const raw = this.provider().getItem(ADMINISTRATION_JOURNAL_KEY);
      if (raw !== null && typeof raw !== 'string') throw new JournalStorageError('storage_unavailable');
      return raw;
    } catch {throw new JournalStorageError('storage_unavailable');}
  }
  private persist(expected: string | null, journal: AdministrationJournal, context: JournalContext): AdministrationJournalView {
    this.active = null;
    const view = administrationView(journal, context, journal.observedAt);
    if (this.read() !== expected) throw new JournalStorageError('storage_changed');
    const encoded = JSON.stringify(journal); decode(encoded);
    try {this.provider().setItem(ADMINISTRATION_JOURNAL_KEY, encoded);}
    catch {throw new JournalStorageError('storage_unavailable');}
    if (this.read() !== encoded) throw new JournalStorageError('storage_unconfirmed');
    this.active = {journal, encoded, context: view.context};
    return view;
  }
  open(context: JournalContext, now: number): AdministrationJournalView {
    this.active = null;
    const raw = this.read();
    const journal = raw === null ? emptyAdministrationJournal(now) : inspectAdministrationJournal(decode(raw), now);
    return this.persist(raw, journal, context);
  }
  private change(update: (journal: AdministrationJournal, context: JournalContext) => AdministrationJournal): AdministrationJournalView {
    const prior = this.active; this.active = null;
    if (prior === null) throw new JournalStorageError('journal_not_open');
    return this.persist(prior.encoded, update(prior.journal, prior.context), prior.context);
  }
  prepare(key: string, command: AdministrationCommand, now: number): AdministrationJournalView {
    return this.change((journal, context) => prepareAdministration(journal, context, key, command, now));
  }
  record(key: string, outcome: AdministrationOutcome, now: number): AdministrationJournalView {
    return this.change((journal, context) => recordAdministration(journal, context, key, outcome, now));
  }
  forget(key: string, now: number): AdministrationJournalView {
    return this.change((journal, context) => forgetAdministration(journal, context, key, now));
  }
  detach(): void {this.active = null;}
}
