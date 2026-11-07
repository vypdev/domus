/** The calendar retires private results whenever its verified scope changes. */
import type {CalendarPage, CalendarQuery} from '../domain/calendar';
import type {JournalContext} from '../domain/journal';
import type {EntryRead} from './ports';

export interface CalendarScope {
  readonly key: string;
  readonly context: JournalContext;
  readonly memberId: string;
}
export interface CalendarView {
  readonly status: 'idle' | 'loading' | 'ready' | 'unavailable';
  readonly page: CalendarPage | null;
}
export interface CalendarServer {
  read(context: JournalContext, memberId: string, query: CalendarQuery, cursor: string | null): EntryRead<CalendarPage>;
}

export class CalendarController {
  private scope: CalendarScope | null = null;
  private pending: EntryRead<CalendarPage> | null = null;
  private query: CalendarQuery | null = null;
  private state: CalendarView = {status: 'idle', page: null};

  constructor(private readonly server: CalendarServer, private readonly publish: (state: CalendarView) => void) {}

  bind(scope: CalendarScope | null): void {
    if (this.scope?.key === scope?.key) return;
    this.scope = scope; this.pending?.cancel(); this.pending = null; this.query = null;
    this.set({status: 'idle', page: null});
  }

  async load(query: CalendarQuery): Promise<void> {
    if (this.scope === null) return;
    this.query = Object.freeze({...query});
    await this.request(this.scope, this.query, null, null);
  }

  async more(): Promise<void> {
    const previous = this.state.page;
    if (this.scope === null || this.query === null || !previous?.cursor || this.pending !== null) return;
    await this.request(this.scope, this.query, previous.cursor, previous);
  }

  private set(state: CalendarView): void {this.state = state; this.publish(state);}

  private async request(scope: CalendarScope, query: CalendarQuery, cursor: string | null, previous: CalendarPage | null): Promise<void> {
    this.pending?.cancel();
    const pending = this.server.read(scope.context, scope.memberId, query, cursor);
    this.pending = pending; this.set({status: 'loading', page: previous});
    try {
      const result = await pending.result;
      if (this.pending !== pending) return;
      const entries = previous === null ? result.entries :
        [...new Map([...previous.entries, ...result.entries].map(item => [item.id, item])).values()];
      this.set({status: 'ready', page: {...result, entries}});
    } catch {
      if (this.pending === pending) this.set({status: 'unavailable', page: previous});
    } finally {
      if (this.pending === pending) this.pending = null;
    }
  }
}
