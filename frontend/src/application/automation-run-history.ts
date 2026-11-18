import type {Revision} from '../domain/administration';
import type {DraftScope} from './automation-drafts';
import {EntryReadError} from './ports';
import type {EntryRead} from './ports';

export interface AutomationRun {
  readonly operationId: string;
  readonly time: number;
  readonly revision: Revision;
  readonly taskCreated: boolean;
  readonly historical: boolean;
  readonly taskOccurrenceId: string | null;
}
export interface AutomationRunPage {
  readonly items: readonly AutomationRun[];
  readonly next: string | null;
}
export interface AutomationRunHistoryServer {
  page(scope: DraftScope, ruleId: string, after: string | null): EntryRead<AutomationRunPage | 'expired'>;
}
export type AutomationRunHistoryIntent = 'open' | 'close' | 'older' | 'latest' | 'retry';
export interface AutomationRunHistoryView {
  readonly phase: 'closed' | 'loading' | 'ready' | 'unavailable' | 'expired' | 'denied';
  readonly items: readonly AutomationRun[];
  readonly hasOlder: boolean;
  readonly timeZone: string;
}

export interface AutomationRunHistoryScope extends DraftScope {
  readonly authorization: string;
}

type Selection = Readonly<{scope: AutomationRunHistoryScope; ruleId: string; timeZone: string}>;

export class AutomationRunHistoryController {
  private selection: Selection | null = null;
  private request: EntryRead<AutomationRunPage | 'expired'> | null = null;
  private view: AutomationRunHistoryView | null = null;
  private next: string | null = null;
  private attempted: string | null = null;

  constructor(private readonly server: AutomationRunHistoryServer,
    private readonly publish: (view: AutomationRunHistoryView | null) => void) {}

  bind(scope: AutomationRunHistoryScope | null, ruleId: string | null, timeZone: string | null): void {
    const previous = this.selection;
    if (scope === null || ruleId === null || timeZone === null) {
      this.selection = null;
      this.clear(null);
    } else if (previous?.scope.key !== scope.key || previous.scope.readOnly !== scope.readOnly
      || previous.scope.authorization !== scope.authorization || previous.ruleId !== ruleId || previous.timeZone !== timeZone) {
      this.selection = {scope, ruleId, timeZone};
      this.clear(timeZone);
    }
  }

  private clear(timeZone: string | null): void {
    this.request?.cancel();
    this.request = null;
    this.next = null;
    this.attempted = null;
    this.view = timeZone === null ? null : {phase: 'closed', items: [], hasOlder: false, timeZone};
    this.publish(this.view);
  }

  private show(phase: AutomationRunHistoryView['phase'], items: readonly AutomationRun[], timeZone: string): void {
    this.view = {phase, items, hasOlder: this.next !== null, timeZone};
    this.publish(this.view);
  }

  async handle(intent: AutomationRunHistoryIntent): Promise<void> {
    const selection = this.selection, view = this.view;
    if (selection === null || view === null) return;
    if (intent === 'close') {
      this.clear(selection.timeZone);
      return;
    }
    if (this.request !== null) return;
    switch (intent) {
      case 'open':
        if (view.phase === 'closed') await this.load(selection, null, []);
        break;
      case 'older':
        if (view.phase === 'ready' && this.next !== null) await this.load(selection, this.next, view.items);
        break;
      case 'latest':
        if (view.phase === 'ready' || view.phase === 'expired') await this.load(selection, null, view.items);
        break;
      case 'retry':
        if (view.phase === 'unavailable') await this.load(selection, this.attempted, view.items);
        break;
    }
  }

  private async load({scope, ruleId, timeZone}: Selection, cursor: string | null,
    prior: readonly AutomationRun[]): Promise<void> {
    this.attempted = cursor;
    const request = this.server.page(scope, ruleId, cursor);
    this.request = request;
    this.show('loading', prior, timeZone);
    try {
      const page = await request.result;
      if (this.request !== request) return;
      this.request = null;
      if (page === 'expired') {
        this.next = null;
        this.show('expired', [], timeZone);
      } else {
        this.next = page.next;
        this.show('ready', page.items, timeZone);
      }
    } catch (error) {
      if (this.request !== request) return;
      this.request = null;
      if (error instanceof EntryReadError && (error.code === 'forbidden' || error.code === 'authentication_required')) {
        this.next = null;
        this.show('denied', [], timeZone);
      } else {
        this.show('unavailable', prior, timeZone);
      }
    }
  }
}
