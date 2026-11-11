/** Same-origin task transport with bounded reads and no automatic write retry. */
import {EntryReadError} from '../application/ports';
import type {TaskCommandResult, TaskOriginal, TaskRequest, TaskServer} from '../application/task-ports';
import type {TaskOverview, TaskOverviewDeadline, TaskOverviewGroup} from '../application/task-overview';
import {civilDate} from '../domain/civil-date';
import type {JournalContext} from '../domain/journal';
import {isCategoryCommand} from '../domain/tasks';
import type {TaskCommand, TaskState} from '../domain/tasks';
import {taskSchedulePolicy, taskText, taskTime, TASK_TEXT_LIMITS} from '../domain/tasks';
import {BoundedHTTP, reason} from './http-transport';
import type {FetchTransport} from './http-transport';
import type {EntryEndpoint} from './http-values';
import {assertion, csrf, failure} from './http-values';
import {boolean, check, choice, fields, identifier, integer, responseRevision, text} from './json-values';
import {taskCategoryCatalog, taskCommandBody, taskDetail, taskPage, taskReceipt, taskRequest} from './task-values';
function route(command: TaskCommand): string {
  if (command.action === 'task.create') return command.payload.schedule === undefined
    ? 'tasks/definitions' : 'tasks/recurrence/creation/' + command.payload.schedule.draft.kind;
  if (isCategoryCommand(command)) {
    if (command.action === 'task.category.create') return 'tasks/categories';
    const item = 'tasks/categories/' + command.categoryId;
    return command.action === 'task.category.archive' ? item + '/archive' : item;
  }
  const action = command.action.slice(5);
  return 'tasks/occurrences/' + command.occurrenceId + '/' + action;
}
const ASSIGNED_STATES = ['assigned', 'in_progress', 'blocked'] as const;
const DEADLINE_STATES = ['available', ...ASSIGNED_STATES] as const;
const OVERVIEW_FIELDS = ['occurrence_id', 'title', 'state'] as const;

function overviewDeadline(value: unknown): TaskOverviewDeadline {
  const row = fields(value, ['local_date', 'instant_ms', 'time_zone'], []);
  const zone = text(row.time_zone, 128);
  try {
    new Intl.DateTimeFormat('en', {timeZone: zone});
    if (row.local_date !== null) {
      check(civilDate(row.local_date) && row.instant_ms === null);
      return {day: row.local_date, instant: null, zone};
    }
    const instant = Number(taskTime(row.instant_ms));
    check(instant <= 253_402_300_799_999);
    return {day: null, instant, zone};
  } catch {
    throw new EntryReadError('invalid_response');
  }
}

function overviewGroup(value: unknown, states: readonly TaskState[], dated = false): TaskOverviewGroup {
  const group = fields(value, ['total', 'items'], []);
  const total = integer(group.total, 0);
  check(Array.isArray(group.items) && group.items.length === Math.min(total, 25));
  const items = group.items.map(value => {
    const item = fields(value, dated ? [...OVERVIEW_FIELDS, 'deadline'] : OVERVIEW_FIELDS, []);
    const work = {id: identifier(item.occurrence_id), title: taskText(item.title, TASK_TEXT_LIMITS.title, true),
      state: choice(item.state, states)};
    return dated ? {...work, deadline: overviewDeadline(item.deadline)} : work;
  });
  check(new Set(items.map(item => item.id)).size === items.length);
  return {total, items};
}

export class HttpTaskServer implements TaskServer {
  private readonly network: BoundedHTTP;
  constructor(target: EntryEndpoint, transport: FetchTransport) {this.network = new BoundedHTTP(target, transport);}
  access(expected: JournalContext) {
    return this.network.owned(async signal => {
      const access = fields(await this.network.get('tasks/access', expected, signal), ['household_id', 'member_id', 'can_create'], ['can_review_schedule','schedule_policy','category_catalog','can_record_for_others','can_manage_points']);
      const policy = access.schedule_policy == null ? null : fields(access.schedule_policy, ['zone','data_identity','repeated_time','revision'], []);
      const householdId = identifier(access.household_id);
      const catalog = access.category_catalog === undefined ? {} : {categoryCatalog: taskCategoryCatalog(access.category_catalog, householdId)};
      return Object.freeze({...catalog, householdId, memberId: identifier(access.member_id), canCreate: boolean(access.can_create),
        canReviewSchedule: access.can_review_schedule === undefined ? false : boolean(access.can_review_schedule),
        ...access.can_record_for_others === undefined ? {} : {canRecordForOthers: boolean(access.can_record_for_others)},
        ...access.can_manage_points === undefined ? {} : {canManagePoints: boolean(access.can_manage_points)},
        ...policy === null ? {} : {schedulePolicy: taskSchedulePolicy({...policy, revision: responseRevision(policy.revision)})}});
    });
  }
  overview(expected: JournalContext) {
    return this.network.owned<TaskOverview>(async signal => {
      const result = fields(await this.network.get('tasks/overview', expected, signal),
        ['assigned', 'unclaimed', 'due_today', 'overdue', 'upcoming_maintenance'], []);
      const dueToday = overviewGroup(result.due_today, DEADLINE_STATES, true);
      const overdue = overviewGroup(result.overdue, DEADLINE_STATES, true);
      const upcomingMaintenance = overviewGroup(result.upcoming_maintenance, DEADLINE_STATES, true);
      const deadlineItems = [...dueToday.items, ...overdue.items, ...upcomingMaintenance.items];
      check(new Set(deadlineItems.map(item => item.id)).size === deadlineItems.length);
      return {assigned: overviewGroup(result.assigned, ASSIGNED_STATES),
        unclaimed: overviewGroup(result.unclaimed, ['available']), dueToday, overdue, upcomingMaintenance};
    });
  }
  list(expected: JournalContext, cursor: string | null) {
    return this.network.owned(async signal => {
      check(cursor === null || typeof cursor === 'string' && cursor.length > 0 && cursor.length <= 512);
      const query = new URLSearchParams({limit: '25'}); if (cursor !== null) query.set('cursor', cursor);
      return taskPage(await this.network.get('tasks/occurrences?' + query.toString(), expected, signal));
    });
  }
  detail(occurrenceId: string, householdId: string, expected: JournalContext) {
    return this.network.owned(async signal => {
      const id = identifier(occurrenceId), home = identifier(householdId);
      return taskDetail(await this.network.get('tasks/occurrences/' + id, expected, signal), id, home);
    });
  }
  original(value: TaskOriginal, expected: JournalContext) {
    return this.network.owned(async signal => {
      const input = taskRequest(value, true);
      const schedule = input.command.action === 'task.create' ? input.command.payload.schedule : undefined;
      const request = schedule === undefined
        ? (isCategoryCommand(input.command) ? 'tasks/categories/requests/' : 'tasks/requests/') + input.command.action
        : 'tasks/recurrence/creation/requests/recurrence.' + schedule.draft.kind + '.create';
      return taskReceipt(await this.network.get(request + '/' + input.key, expected, signal), input, true);
    });
  }
  async send(value: TaskRequest, expected: JournalContext): Promise<TaskCommandResult> {
    let posted = false;
    return this.network.owned(async signal => {
      let input: TaskRequest;
      try {input = taskRequest(value, false);}
      catch {return Object.freeze({kind: 'rejected' as const, reason: 'invalid_input' as const, correlationId: null});}
      let token: string;
      try {assertion(expected); token = csrf(await this.network.get('auth/csrf', expected, signal));}
      catch (error) {return Object.freeze({kind: 'rejected' as const, reason: error instanceof EntryReadError ? error.code : 'unavailable' as const, correlationId: null});}
      try {
        const body = taskCommandBody(input.command);
        if (signal.aborted) throw new EntryReadError('unavailable');
        posted = true;
        const method = input.command.action === 'task.category.rename' ? 'PUT' : 'POST';
        const reply = await this.network.request(route(input.command), method, expected, body, input.key, token, signal);
        if (reply.status === 200) return taskReceipt(reply.value, input, false);
        if ([401,403,409,422,503].includes(reply.status)) return Object.freeze({kind: 'rejected' as const,
          reason: reason(reply.status), correlationId: failure(reply.value)});
      } catch {/* An unbound or missing reply cannot establish absence of the committed effect. */}
      return Object.freeze({kind: 'uncertain' as const});
    }).result.catch(() => posted ? Object.freeze({kind: 'uncertain' as const})
      : Object.freeze({kind: 'rejected' as const, reason: 'unavailable' as const, correlationId: null}));
  }
}
