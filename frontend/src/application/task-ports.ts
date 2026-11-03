import type {TaskAccess, TaskCommand, TaskDetail, TaskPage, TaskReceipt} from '../domain/tasks';
import type {JournalContext} from '../domain/journal';
import type {CommandResult, EntryRead} from './ports';

export interface TaskRequest {readonly key: string; readonly command: TaskCommand;}
export interface TaskOriginal extends TaskRequest {readonly operationId: string | null;}
export type TaskCommandResult = TaskReceipt | Exclude<CommandResult, {kind: 'receipt'}>;
export interface TaskServer {
  access(expected: JournalContext): EntryRead<TaskAccess>;
  list(expected: JournalContext, cursor: string | null): EntryRead<TaskPage>;
  detail(occurrenceId: string, householdId: string, expected: JournalContext): EntryRead<TaskDetail>;
  original(request: TaskOriginal, expected: JournalContext): EntryRead<TaskReceipt>;
  send(request: TaskRequest, expected: JournalContext): Promise<TaskCommandResult>;
}

export interface TaskJournalScope {
  readonly context: JournalContext; readonly householdId: string; readonly memberId: string;
}
export interface TaskRecord extends TaskRequest {
  readonly scope: TaskJournalScope; readonly createdAt: number; readonly expiresAt: number;
  readonly stage: 'prepared' | 'uncertain' | 'committed' | 'historical' | 'rejected';
  readonly operationId: string | null;
}
export interface TaskJournalPort {
  open(scope: TaskJournalScope, now: number): readonly TaskRecord[];
  prepare(key: string, command: TaskCommand, now: number): readonly TaskRecord[];
  record(key: string, stage: Exclude<TaskRecord['stage'], 'prepared'>, operationId: string | null, now: number): readonly TaskRecord[];
  forget(key: string, now: number): readonly TaskRecord[];
  detach(): void;
}
