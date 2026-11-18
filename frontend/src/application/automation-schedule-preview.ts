import type {JournalContext} from '../domain/journal';
import {EntryReadError} from './ports';
import type {EntryRead} from './ports';

const DAILY_TIME = /^(?:[01][0-9]|2[0-3]):[0-5][0-9]$/u;
export function isDailyTime(value: unknown): value is string {
  return typeof value === 'string' && value.length === 5 && DAILY_TIME.test(value);
}
export const DAILY_RESOLUTIONS = ['exact', 'gap_first_valid', 'fold_first', 'fold_second'] as const;

export interface DailyAutomationTime {
  readonly requestedDate: string;
  readonly resolvedLocal: string;
  readonly instantMs: number;
  readonly resolution: typeof DAILY_RESOLUTIONS[number];
}
export interface SchedulePreviewScope {
  readonly key: string;
  readonly context: JournalContext;
  readonly timeZone: string;
}
export interface AutomationScheduleServer {
  daily(scope: SchedulePreviewScope, time: string): EntryRead<readonly DailyAutomationTime[]>;
}
export type SchedulePreviewIntent = Readonly<{type: 'time'; value: string}> | Readonly<{type: 'preview'}>;
export interface SchedulePreviewView {
  readonly timeZone: string;
  readonly input: string;
  readonly busy: boolean;
  readonly issue: 'invalid' | 'unavailable' | 'denied' | null;
  readonly result: readonly DailyAutomationTime[] | null;
}

export class AutomationSchedulePreviewController {
  private scope: SchedulePreviewScope | null = null;
  private view: SchedulePreviewView | null = null;
  private request: EntryRead<readonly DailyAutomationTime[]> | null = null;

  constructor(private readonly server: AutomationScheduleServer,
    private readonly publish: (view: SchedulePreviewView | null) => void) {}

  bind(scope: SchedulePreviewScope | null): void {
    if (this.scope?.key === scope?.key && this.scope?.timeZone === scope?.timeZone) return;
    this.cancel();
    this.scope = scope;
    this.view = scope === null ? null : {timeZone: scope.timeZone, input: '', busy: false, issue: null, result: null};
    this.publish(this.view);
  }

  private cancel(): void {
    this.request?.cancel();
    this.request = null;
  }

  private update(patch: Partial<SchedulePreviewView>): void {
    this.view = {...this.view!, ...patch};
    this.publish(this.view);
  }

  async handle(intent: SchedulePreviewIntent): Promise<void> {
    const scope = this.scope, view = this.view;
    if (scope === null || view === null) return;
    if (intent.type === 'time') {
      this.cancel();
      this.update({input: intent.value, busy: false, issue: null, result: null});
      return;
    }
    if (this.request !== null) return;
    if (!isDailyTime(view.input)) {
      this.update({issue: 'invalid'});
      return;
    }
    const request = this.server.daily(scope, view.input);
    this.request = request;
    this.update({busy: true, issue: null, result: null});
    try {
      const result = await request.result;
      if (this.request !== request) return;
      this.update({busy: false, result});
    } catch (error) {
      if (this.request !== request) return;
      const denied = error instanceof EntryReadError
        && (error.code === 'forbidden' || error.code === 'authentication_required');
      this.update({busy: false, issue: denied ? 'denied' : 'unavailable'});
    } finally {
      if (this.request === request) this.request = null;
    }
  }
}
