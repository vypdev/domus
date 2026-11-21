import {expect, test, vi} from 'vitest';
import {HttpDailyAutomation} from '../src/adapters/automation-daily-http';
import {draftCondition} from '../src/adapters/automation-condition-values';
import {dailyInstant} from '../src/application/automation-daily';
import type {DailyRequest, DailyReview} from '../src/application/automation-daily';
import {active, envelope, inactive, one, point, policy, response, scope, target, three, times, two,
  wireError, wireReview, wireTime} from './automation-daily-fixtures';

const request: DailyRequest = {kind: 'enable', ruleId: 'rule', ruleRevision: two,
  controlRevision: '0', scheduleRevision: '0', reviewed: point(), key: 'enable', scope: scope.key};
const result = {rule_id: 'rule', rule_revision: '2', control_revision: '1', schedule_revision: '1', enabled: true,
  grant_id: 'grant', approved_next: wireTime(point(), true), member_id: 'member'};

test('active daily discovery is independently scoped and never mistakes a manual state or malformed response for a daily grant', async () => {
  let value: unknown = null;
  const transport = vi.fn(async (route: string) => response(route, value));
  const server = new HttpDailyAutomation(target, transport);
  await expect(server.active(scope, 'rule').result).resolves.toBeNull();
  value = wireReview({...active, ruleRevision: one, mayEnable: false});
  await expect(server.active(scope, 'rule').result).resolves.toMatchObject({ruleRevision: one, mayEnable: false});
  expect(transport.mock.lastCall?.[0]).toBe('/api/v1/automation/drafts/rule/daily/active');
  for (const invalid of [wireReview(), wireReview(active), wireReview({...active, activeTrigger: 'manual'}), {}]) {
    value = invalid;
    await expect(server.active(scope, 'rule').result).rejects.toThrow();
  }
});

test('daily review is scoped to the exact saved revision and preserves approved, changed and unavailable timing', async () => {
  let value: unknown = wireReview();
  const transport = vi.fn(async (route: string) => response(route, value));
  const server = new HttpDailyAutomation(target, transport);
  await expect(server.review(scope, 'rule', two).result).resolves.toEqual(inactive);
  expect(transport.mock.lastCall?.[0]).toBe('/api/v1/automation/drafts/rule/daily?revision=2');
  value = wireReview(active);
  await expect(server.review(scope, 'rule', two).result).resolves.toEqual(active);
  const changed: DailyReview = {...active,
    conditionProducts: ['soap'], condition: {kind: 'not', child: {kind: 'stock_below_minimum', product_id: 'soap'}},
    proposedPolicy: {...policy, zone: 'UTC', revision: two},
    proposedTimes: times.map(item => ({...item, policy: {...policy, zone: 'UTC', revision: two}, offsetSeconds: 0})),
    policyChanged: true, approvedUnavailable: true, approvedTimes: null,
    suppression: {first: point(), throughMs: dailyInstant(point()) + 86400000}};
  value = wireReview(changed);
  await expect(server.review(scope, 'rule', two).result).resolves.toEqual(changed);
  const unrelated = {...active, proposedPolicy: {...policy, revision: two},
    proposedTimes: times.map(item => ({...item, policy: {...policy, revision: two}}))};
  value = wireReview(unrelated);
  await expect(server.review(scope, 'rule', two).result).resolves.toEqual(unrelated);
  const unavailable = {...active, proposedUnavailable: true, proposedTimes: [], approvedTimes: null, approvedUnavailable: true};
  value = wireReview(unavailable);
  await expect(server.review(scope, 'rule', two).result).resolves.toEqual(unavailable);
});

test('daily review accepts real gap and fold facts, including the approved first and second occurrence policies', async () => {
  for (const resolution of ['gap_first_valid', 'fold_first', 'fold_second'] as const) {
    const approvedPolicy = {...policy, repeatedTime: resolution === 'fold_second' ? 'second_instant' as const : 'first_instant' as const};
    const day = resolution === 'gap_first_valid' ? '2026-03-29' : '2026-10-25';
    const nominal = day + 'T02:30:00';
    const first = {...point(), policy: approvedPolicy, nominal, resolvedLocal: resolution === 'gap_first_valid' ? day + 'T03:00:00' : nominal,
      resolution, offsetSeconds: resolution === 'fold_second' ? 3600 : 7200};
    const future = [26, 27, 28, 29].map(date => ({...point(), policy: approvedPolicy,
      nominal: `2026-11-${date}T02:30:00`, resolvedLocal: `2026-11-${date}T02:30:00`}));
    const review = {...inactive, requestedTime: '02:30', proposedPolicy: approvedPolicy, proposedTimes: [first, ...future]};
    const server = new HttpDailyAutomation(target, async route => response(route, wireReview(review)));
    await expect(server.review(scope, 'rule', two).result).resolves.toEqual(review);
  }
});

test('a malformed, crossed or contradictory daily review cannot become permission to execute', async () => {
  let value: unknown;
  const server = new HttpDailyAutomation(target, async route => response(route, value));
  const valid = wireReview(), enabled = wireReview(active), planned = wireTime();
  const invalid = [
    {...valid, rule_id: 'foreign'}, {...valid, rule_revision: '1'}, {...valid, rule_revision: 2},
    {...valid, rule_revision: '02'}, {...valid, requested_time: '24:00'}, {...valid, capability: 'admin'},
    {...valid, grant_owner: 'member'}, {...valid, enabled: true}, {...valid, approved_unavailable: true},
    {...valid, active_trigger: 'manual'}, {...valid, active_rule_revision: '1'}, {...valid, active_title: 'Forged'},
    {...enabled, control_revision: '0'}, {...valid, schedule_revision: '1'}, {...enabled, next_time: null},
    {...enabled, policy_changed: true}, {...enabled, approved_times: null},
    {...valid, approved_times: [planned, planned, planned, planned, planned]},
    {...valid, proposed_times: []}, {...valid, proposed_times: [planned, planned, planned, planned, planned]},
    {...valid, proposed_unavailable: true},
    {...valid, proposed_times: [wireTime(point(23)), ...valid.proposed_times.slice(1)]},
    {...valid, proposed_times: [{...planned, policy: {...planned.policy, revision: '2'}}, ...valid.proposed_times.slice(1)]},
    {...valid, proposed_times: [{...planned, nominal: '2026-11-22T07:30:59', resolved_local: '2026-11-22T07:30:59'}, ...valid.proposed_times.slice(1)]},
    {...valid, proposed_times: [{...planned, nominal: '2026-02-30T07:30:00'}, ...valid.proposed_times.slice(1)]},
    {...valid, proposed_policy: {...valid.proposed_policy, zone: 'Europe//Madrid'}},
    {...valid, proposed_policy: {...valid.proposed_policy, data_identity: 'invalid data'}},
    {...valid, proposed_policy: {...valid.proposed_policy, repeated_time: 'guess'}},
    {...valid, condition_product_ids: ['duplicate', 'duplicate']}, {...valid, condition_product_ids: Array(65).fill('product')},
    {...valid, condition: {kind: 'task.delete'}},
    {...enabled, suppression: {first: planned, through_ms: 1}},
    {...valid, suppression: {first: planned, through_ms: dailyInstant(point())}},
    {...enabled, suppression: {first: planned, through_ms: 253402300800000}},
    {...valid, admin: true},
  ];
  for (const bad of invalid) {value = bad; await expect(server.review(scope, 'rule', two).result).rejects.toThrow();}
  for (const changed of [
    {offset_seconds: 86400}, {zone_digest: 'not-a-digest'}, {resolution: 'fold_second'},
    {resolution: 'gap_first_valid'}, {resolution: 'fold_first', policy: {...planned.policy, repeated_time: 'second_instant'}},
    {nominal: '1969-12-31T23:00:00'}, {nominal: '1970-01-01T00:00:00', resolved_local: '1970-01-01T00:00:00', offset_seconds: 1},
    {nominal: '9999-12-31T23:59:59.999000', resolved_local: '9999-12-31T23:59:59.999000', offset_seconds: -1},
    {nominal: '2026-11-22T07:30:00.000001'},
  ]) {
    value = {...valid, proposed_times: [{...planned, ...changed}, ...valid.proposed_times.slice(1)]};
    await expect(server.review(scope, 'rule', two).result).rejects.toThrow();
  }
});

test('the same bounded condition language is used for saved drafts and exact daily review', () => {
  const leaf = {kind: 'stock_below_minimum', product_id: 'soap'};
  let deep: unknown = leaf;
  for (let index = 0; index < 7; index++) deep = {kind: 'all', children: [deep]};
  expect(draftCondition(deep)).toEqual(deep);
  expect(() => draftCondition({kind: 'not', child: deep})).toThrow();
  const maximum = {kind: 'any', children: Array.from({length: 61}, () => leaf)};
  expect(draftCondition(maximum)).toEqual(maximum);
  expect(() => draftCondition({...maximum, children: [...maximum.children, leaf]})).toThrow();
  expect(() => draftCondition({kind: 'all', children: []})).toThrow();
  expect(() => draftCondition({kind: 'all', children: Array(63).fill(leaf)})).toThrow();
  expect(draftCondition(null)).toBeNull();
});

test('writes preserve reviewed evidence and verify the original current or historical receipt under current membership', async () => {
  let value: unknown = envelope(result), status = 200;
  const transport = vi.fn(async (route: string, init: RequestInit) => response(route,
    route.endsWith('/auth/csrf') ? {csrf_token: 'c'.repeat(64)} : value, route.endsWith('/auth/csrf') ? 200 : status));
  const server = new HttpDailyAutomation(target, transport);
  const expected = {kind: 'committed', action: 'enable', ruleId: 'rule', ruleRevision: two, operationId: 'operation', next: point()};
  await expect(server.send(scope, request).result).resolves.toEqual(expected);
  expect(transport.mock.lastCall?.[0]).toBe('/api/v1/automation/drafts/rule/daily/enable');
  expect(JSON.parse(String(transport.mock.lastCall?.[1].body))).toEqual({rule_revision: '2',
    expected_control_revision: '0', expected_schedule_revision: '0', reviewed: wireTime()});
  expect(new Headers(transport.mock.lastCall?.[1].headers).get('idempotency-key')).toBe('enable');
  value = envelope(result, true);
  await expect(server.original(scope, request).result).resolves.toEqual({...expected, kind: 'historical'});
  expect(transport.mock.lastCall?.[0]).toBe('/api/v1/automation/daily/requests/enable/enable');
  const disable: DailyRequest = {kind: 'disable', ruleId: 'rule', ruleRevision: one, controlRevision: three,
    scheduleRevision: two, key: 'disable', scope: scope.key};
  value = envelope({...result, rule_revision: '1', control_revision: '4', schedule_revision: '3', enabled: false});
  await expect(server.send(scope, disable).result).resolves.toMatchObject({action: 'disable', ruleRevision: one});
  expect(JSON.parse(String(transport.mock.lastCall?.[1].body))).toEqual({rule_revision: '1',
    expected_control_revision: '3', expected_schedule_revision: '2'});
  value = envelope(result);
  await expect(server.send(scope, {...request, kind: 'adopt'}).result).resolves.toMatchObject({action: 'adopt'});
  for (const [code, kind] of [['revision_conflict', 'stale'], ['automation_timing_review_changed', 'timing_changed'],
    ['automation_disabled', 'disabled'], ['idempotency_conflict', 'rejected']]) {
    status = 409; value = wireError(code);
    await expect(server.send(scope, request).result).resolves.toEqual({kind});
  }
  status = 404; value = wireError('operation_missing');
  await expect(server.original(scope, request).result).resolves.toEqual({kind: 'missing'});
  status = 403; value = wireError('permission_denied');
  await expect(server.send(scope, request).result).rejects.toMatchObject({code: 'forbidden'});
  await expect(server.original(scope, request).result).rejects.toMatchObject({code: 'forbidden'});
  status = 404; value = wireError('automation_draft_missing');
  await expect(server.original(scope, request).result).rejects.toThrow();
});

test('crossed, expanded, changed or ambiguous receipts cannot confirm the daily command', async () => {
  let value: unknown;
  const server = new HttpDailyAutomation(target, async route => response(route, value));
  for (const bad of [
    envelope({...result, rule_id: 'other'}), envelope({...result, rule_revision: '1'}),
    envelope({...result, control_revision: '2'}), envelope({...result, schedule_revision: '2'}),
    envelope({...result, enabled: false}), envelope({...result, member_id: 'other-member'}),
    envelope({...result, approved_next: wireTime({...point(), zoneDigest: 'b'.repeat(64)}, true)}),
    envelope({...result, approved_next: wireTime()}), envelope({...result, admin: true}),
    {...envelope(result), state: 'historical'}, {...envelope(result), archived_by: 'restore'},
    {...envelope(result), created_at: 253402300800000},
  ]) {value = bad; await expect(server.original(scope, request).result).rejects.toThrow();}
});
