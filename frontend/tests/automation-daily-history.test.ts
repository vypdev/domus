import {expect, test} from 'vitest';
import {HttpDailyAutomationHistory} from '../src/adapters/automation-daily-history-http';
import {response, scope, target, wireError} from './automation-daily-fixtures';

const queued = {trigger_key: 'f'.repeat(64), rule_revision: '1', control_revision: '2',
  requested_local: '2026-11-22T07:30:00', resolved_local: '2026-11-22T07:30:00', scheduled_at: 1795329000000,
  time_zone: 'Europe/Madrid', resolution: 'exact', admitted_at: 1795329000200, outcome: 'queued',
  finished_at: null, historical: false, task_created: false, task_occurrence_id: null, operation_id: 'admit-operation'};
const page = (items: unknown[], next: string | null = null) => ({rule_id: 'rule', items, next_cursor: next});

test('scheduled history keeps current, historical and waiting facts separate and preserves safe task links', async () => {
  let data = page([queued]), status = 200;
  const routes: string[] = [];
  const server = new HttpDailyAutomationHistory(target, async route => {routes.push(route); return response(route, data, status);});
  const read = () => server.page(scope, 'rule', null).result;
  await expect(read()).resolves.toMatchObject({items: [{key: queued.trigger_key, outcome: 'queued', finishedAt: null,
    historical: false, taskOccurrenceId: null}], next: null});
  expect(routes[0]).toBe('/api/v1/automation/drafts/rule/daily/runs');
  for (const outcome of ['created', 'no_task', 'cancelled', 'denied']) {
    data = page([{...queued, outcome, finished_at: queued.admitted_at - 1000, task_created: outcome === 'created',
      task_occurrence_id: outcome === 'created' ? 'created-task' : null, operation_id: 'run-operation'}]);
    await expect(read()).resolves.toMatchObject({items: [{outcome, taskOccurrenceId: outcome === 'created' ? 'created-task' : null}]});
  }
  data = page([{...queued, historical: true, operation_id: null}]);
  await expect(read()).resolves.toMatchObject({items: [{outcome: 'queued', historical: true}]});
  data = page([{...queued, outcome: 'created', task_created: true, finished_at: queued.admitted_at,
    historical: true, task_occurrence_id: null}]);
  await expect(read()).resolves.toMatchObject({items: [{outcome: 'created', historical: true, taskOccurrenceId: null}]});
  data = page([{...queued, trigger_key: 'e'.repeat(64), resolution: 'gap_first_valid',
    requested_local: '2026-03-29T02:30:00', resolved_local: '2026-03-29T03:00:00'},
  {...queued, trigger_key: 'd'.repeat(64)}], 'next&cursor');
  await expect(server.page(scope, 'rule', 'prior&cursor').result).resolves.toMatchObject({next: 'next&cursor'});
  expect(routes.at(-1)).toContain('?cursor=prior%26cursor');
  for (const [code, selectedStatus] of [['invalid_task_cursor', 422], ['task_cursor_expired', 409]] as const) {
    status = selectedStatus; data = wireError(code) as unknown as typeof data;
    await expect(server.page(scope, 'rule', 'old').result).resolves.toBe('expired');
  }
  status = 403; data = wireError('permission_denied') as unknown as typeof data;
  await expect(read()).rejects.toMatchObject({code: 'forbidden'});
  status = 422; data = wireError('invalid_page_size') as unknown as typeof data;
  await expect(server.page(scope, 'rule', 'cursor').result).rejects.toThrow();
  await expect(read()).rejects.toThrow();
});

test('daily history rejects foreign, reordered, repeated, expanded and contradictory run facts', async () => {
  let data: unknown;
  const server = new HttpDailyAutomationHistory(target, async route => response(route, data));
  for (const bad of [
    {...page([]), rule_id: 'foreign'}, page(Array(26).fill(queued)), page([queued, queued]),
    page([{...queued, trigger_key: 'e'.repeat(64)}, queued]),
    page([queued, {...queued, admitted_at: queued.admitted_at + 1}]), page([], 'cursor'), page([queued], 'cursor'),
    page([queued, {...queued, admitted_at: queued.admitted_at - 1}]),
  ]) {
    data = bad;
    await expect(server.page(scope, 'rule', 'cursor').result).rejects.toThrow();
  }
  for (const changes of [
    {trigger_key: 'not-digest'}, {rule_revision: '0'}, {control_revision: '02'}, {time_zone: 'Europe//Madrid'},
    {scheduled_at: 253402300800000}, {admitted_at: 253402300800000}, {finished_at: 253402300800000},
    {outcome: 'created', task_created: true}, {outcome: 'queued', finished_at: queued.admitted_at},
    {task_created: true}, {historical: true, task_occurrence_id: 'private-task'},
    {task_occurrence_id: 'fake-task'}, {outcome: 'no_task', finished_at: queued.admitted_at, operation_id: null},
    {resolution: 'gap_first_valid'}, {resolved_local: '2026-11-22T07:31:00'}, {admin: true},
  ]) {
    data = page([{...queued, ...changes}]);
    await expect(server.page(scope, 'rule', null).result).rejects.toThrow();
  }
});
