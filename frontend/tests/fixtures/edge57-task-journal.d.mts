import type {OwnedStorage} from '../../src/adapters/session-journal';
import type {Deployment} from '../../src/domain/entry';
import type {EntryClock, EntryEntropy, EntryServer} from '../../src/application/ports';
import type {TaskServer} from '../../src/application/task-ports';
/** The fixture exposes only the previous-client methods exercised by compatibility tests. */
export const TASK_JOURNAL_KEY: string;
export class TaskSessionJournal {
  constructor(storage: OwnedStorage | undefined);
  open(scope: unknown, now: number): readonly unknown[];
}
export class TaskController {
  constructor(deployment: Deployment, identity: Pick<EntryServer, 'session'>, server: TaskServer,
    journal: TaskSessionJournal, clock: EntryClock, entropy: EntryEntropy);
  refresh(): Promise<void>;
  create(title: unknown, description: unknown, priority: 'normal'): Promise<void>;
  close(): void;
  get view(): Readonly<{records: readonly unknown[] | null; notice: string | null}>;
}
