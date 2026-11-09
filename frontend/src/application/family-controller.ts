/** Read only the current member's Family report and retire it with its verified scope. */
import {calendarPeriod} from '../domain/calendar';
import type {CalendarPeriod} from '../domain/calendar';
import type {JournalContext} from '../domain/journal';
import {EntryReadError} from './ports';
import type {EntryRead} from './ports';

export type FamilyPeriod = 'week' | 'month';
export interface FamilyEntry {
  readonly id: string;
  readonly title: string;
  readonly amount: number;
  readonly performedAt: number;
  readonly verifiedAt: number | null;
  readonly postedAt: number;
  readonly reverses: string | null;
}
export interface FamilyReport {
  readonly period: CalendarPeriod;
  readonly zone: string;
  readonly posted: number;
  readonly available: number;
  readonly earned: number;
  readonly pendingVerification: number;
  readonly pendingPosting: number;
  readonly completed: number;
  readonly tracked: number;
  readonly elapsed: number;
  readonly history: readonly FamilyEntry[];
  readonly cursor: string | null;
}
export interface FamilyServer {
  read(context: JournalContext, period: CalendarPeriod, cursor: string | null): EntryRead<FamilyReport>;
}
export interface FamilyScope {
  readonly key: string;
  readonly context: JournalContext;
  readonly today: string;
}
export interface FamilyView {
  readonly state: 'loading' | 'ready' | 'unavailable';
  readonly report: FamilyReport | null;
}

export class FamilyController {
  private scope: FamilyScope | null = null;
  private pending: EntryRead<FamilyReport> | null = null;
  private selection: CalendarPeriod | null = null;
  private report: FamilyReport | null = null;

  constructor(private readonly server: FamilyServer, private readonly publish: (view: FamilyView | null) => void) {}

  bind(scope: FamilyScope | null): void {
    if (this.scope?.key === scope?.key) return;
    this.scope = scope; this.pending?.cancel(); this.pending = null;
    this.selection = null; this.report = null;
    if (scope === null) this.publish(null);
    else void this.select('week', scope.today);
  }

  async select(period: FamilyPeriod, anchor: string): Promise<void> {
    this.selection = calendarPeriod(period, anchor);
    this.report = null;
    await this.load(null);
  }

  async refresh(): Promise<void> {await this.load(null);}

  async more(): Promise<void> {
    if (this.pending === null && this.report?.cursor) await this.load(this.report.cursor);
  }

  private async load(cursor: string | null): Promise<void> {
    if (this.scope === null || this.selection === null) return;
    this.pending?.cancel();
    const pending = this.server.read(this.scope.context, this.selection, cursor);
    this.pending = pending;
    this.publish({state: 'loading', report: this.report});
    try {
      const page = await pending.result;
      if (this.pending !== pending) return;
      // Older entries extend the original view. A concurrent posting belongs to the next refresh.
      const previous = this.report;
      this.report = cursor === null ? page : {...previous!, cursor: page.cursor,
        history: [...previous!.history, ...page.history]};
      this.publish({state: 'ready', report: this.report});
    } catch (error) {
      if (this.pending !== pending) return;
      if (!(error instanceof EntryReadError) || error.code !== 'unavailable') this.report = null;
      this.publish({state: 'unavailable', report: this.report});
    } finally {
      if (this.pending === pending) this.pending = null;
    }
  }
}
