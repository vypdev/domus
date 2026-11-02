import type {AdministrationCommand} from '../domain/administration-commands';
import type {AdministrationJournalView, AdministrationOutcome} from '../domain/administration-journal';
import type {JournalContext} from '../domain/journal';

/** Only a fresh server-verified context may open the current view. Storage is never authority. */
export interface AdministrationJournalPort {
  open(context: JournalContext, now: number): AdministrationJournalView;
  prepare(key: string, command: AdministrationCommand, now: number): AdministrationJournalView;
  record(key: string, outcome: AdministrationOutcome, now: number): AdministrationJournalView;
  forget(key: string, now: number): AdministrationJournalView;
  detach(): void;
}
