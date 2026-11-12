import type {JournalContext} from '../domain/journal';
import {EntryReadError} from './ports';
import type {EntryRead} from './ports';

export type OverviewView<T> = Readonly<{state: 'loading' | 'denied' | 'unavailable'}>
  | Readonly<{state: 'ready'; data: T}>;

interface OverviewScope {
  readonly key: string;
  readonly context: JournalContext;
}

/** Retire private results before switching contexts or starting a retry. */
export class OverviewReadController<T> {
  private scope: OverviewScope | null = null;
  private pending: EntryRead<T> | null = null;

  constructor(private readonly read: (context: JournalContext) => EntryRead<T>,
    private readonly publish: (view: OverviewView<T> | null) => void) {}

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
    const pending = this.read(this.scope.context);
    this.pending = pending;
    this.publish({state: 'loading'});
    try {
      const data = await pending.result;
      if (this.pending === pending) this.publish({state: 'ready', data});
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
