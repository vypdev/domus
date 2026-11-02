import type {AdministrationCommand} from '../domain/administration-commands';
import type {AdministrationJournalView, AdministrationOutcome} from '../domain/administration-journal';
import type {JournalContext} from '../domain/journal';
import type {AdministrationAccess, AdministrationCapabilities, AdministrationPolicy, AdministrationReceipt,
  Directory, OwnPreferences, PublicPresentation, Roster} from '../domain/administration-views';
import type {CommandResult, EntryRead, HouseholdFacts} from './ports';

export interface AdministrationRequest {readonly key: string; readonly command: AdministrationCommand;}
export interface AdministrationOriginal extends AdministrationRequest {readonly operationId: string | null;}
export type AdministrationCommandResult = AdministrationReceipt | Exclude<CommandResult, {kind: 'receipt'}>;
export interface AdministrationServer {
  capabilities(expected: JournalContext): EntryRead<AdministrationCapabilities>;
  authorization(expected: JournalContext): EntryRead<AdministrationAccess>;
  household(expected: JournalContext): EntryRead<HouseholdFacts>;
  policy(expected: JournalContext): EntryRead<AdministrationPolicy>;
  roster(expected: JournalContext): EntryRead<Roster>;
  directory(expected: JournalContext): EntryRead<Directory>;
  presentation(memberId: string, expected: JournalContext): EntryRead<PublicPresentation>;
  preferences(expected: JournalContext): EntryRead<OwnPreferences>;
  original(request: AdministrationOriginal, expected: JournalContext): EntryRead<AdministrationReceipt>;
  operation(request: AdministrationOriginal, expected: JournalContext): EntryRead<AdministrationReceipt>;
  send(request: AdministrationRequest, expected: JournalContext): Promise<AdministrationCommandResult>;
}

/** Only a fresh server-verified context may open the current view. Storage is never authority. */
export interface AdministrationJournalPort {
  open(context: JournalContext, now: number): AdministrationJournalView;
  prepare(key: string, command: AdministrationCommand, now: number): AdministrationJournalView;
  record(key: string, outcome: AdministrationOutcome, now: number): AdministrationJournalView;
  forget(key: string, now: number): AdministrationJournalView;
  detach(): void;
}
