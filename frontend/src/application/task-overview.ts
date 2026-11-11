import type {JournalContext} from '../domain/journal';
import type {TaskState} from '../domain/tasks';
import {EntryReadError} from './ports';
import type {EntryRead} from './ports';

export interface TaskOverviewItem {
  readonly id: string;
  readonly title: string;
  readonly state: TaskState;
}

export interface TaskOverviewGroup {
  readonly total: number;
  readonly items: readonly TaskOverviewItem[];
}

export interface TaskOverview {
  readonly assigned: TaskOverviewGroup;
  readonly unclaimed: TaskOverviewGroup;
}

export type TaskOverviewView = Readonly<{state: 'loading' | 'denied' | 'unavailable'}>
  | Readonly<{state: 'ready'; overview: TaskOverview}>;

interface OverviewScope {
  readonly key: string;
  readonly context: JournalContext;
}

export interface TaskOverviewServer {
  overview(context: JournalContext): EntryRead<TaskOverview>;
}

/** Retire private results before switching contexts or starting a retry. */
export class TaskOverviewController {
  private scope: OverviewScope | null = null;
  private pending: EntryRead<TaskOverview> | null = null;

  constructor(private readonly server: TaskOverviewServer,
    private readonly publish: (view: TaskOverviewView | null) => void) {}

  bind(scope: OverviewScope | null): void {
    if (this.scope?.key === scope?.key) return;
    this.scope = scope;
    if (scope !== null) {
      void this.refresh();
      return;
    }
    this.pending?.cancel();
    this.pending = null;
    this.publish(null);
  }

  async refresh(): Promise<void> {
    if (this.scope === null) return;
    this.pending?.cancel();
    const pending = this.server.overview(this.scope.context);
    this.pending = pending;
    this.publish({state: 'loading'});
    try {
      const overview = await pending.result;
      if (this.pending === pending) this.publish({state: 'ready', overview});
    } catch (error) {
      if (this.pending !== pending) return;
      const denied = error instanceof EntryReadError
        && (error.code === 'forbidden' || error.code === 'authentication_required');
      this.publish({state: denied ? 'denied' : 'unavailable'});
    } finally {
      if (this.pending === pending) this.pending = null;
    }
  }
}
