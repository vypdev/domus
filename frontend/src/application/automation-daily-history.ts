import type {Revision} from '../domain/administration';
import type {DAILY_RESOLUTIONS} from './automation-schedule-preview';
import type {AutomationRunHistoryView} from './automation-run-history';

export interface ScheduledAutomationRun {
  readonly key: string;
  readonly ruleRevision: Revision;
  readonly controlRevision: Revision;
  readonly requestedLocal: string;
  readonly resolvedLocal: string;
  readonly scheduledAt: number;
  readonly timeZone: string;
  readonly resolution: typeof DAILY_RESOLUTIONS[number];
  readonly admittedAt: number;
  readonly outcome: 'queued' | 'created' | 'no_task' | 'cancelled' | 'denied';
  readonly finishedAt: number | null;
  readonly historical: boolean;
  readonly taskOccurrenceId: string | null;
  readonly operationId: string | null;
}
export type DailyHistoryView = AutomationRunHistoryView<ScheduledAutomationRun>;
