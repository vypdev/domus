import type {TaskState} from '../domain/tasks';
import type {OverviewView} from './overview-read';

export interface TaskOverviewItem {
  readonly id: string;
  readonly title: string;
  readonly state: TaskState;
  readonly deadline?: TaskOverviewDeadline;
}

export type TaskOverviewDeadline =
  | Readonly<{day: string; instant: null; zone: string}>
  | Readonly<{day: null; instant: number; zone: string}>;

export interface TaskOverviewGroup {
  readonly total: number;
  readonly items: readonly TaskOverviewItem[];
}

export interface TaskOverview {
  readonly assigned: TaskOverviewGroup;
  readonly unclaimed: TaskOverviewGroup;
  readonly dueToday: TaskOverviewGroup;
  readonly overdue: TaskOverviewGroup;
  readonly upcomingMaintenance: TaskOverviewGroup;
}

export type TaskOverviewView = OverviewView<TaskOverview>;
