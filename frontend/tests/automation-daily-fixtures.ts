import {vi} from 'vitest';
import type {DailyPolicy, DailyReview, DailyScope, ReviewedDailyTime} from '../src/application/automation-daily';
import type {EntryRead} from '../src/application/ports';
import {EntryReadError} from '../src/application/ports';
import {revisionValue} from '../src/domain/administration';

export const one = revisionValue('1'), two = revisionValue('2'), three = revisionValue('3');
export const scope: DailyScope = {key: 'daily-owner', memberId: 'member', readOnly: false, authorization: 'member-policy-1', timing: 'home-policy-1',
  context: {installationId: '01234567-89ab-cdef-0123-456789abcdef', channel: 'edge', subject: 'a'.repeat(32)}};
export const selection = {id: 'rule', revision: two, dailyTime: '07:30'};
export const policy: DailyPolicy = {zone: 'Europe/Madrid', dataIdentity: 'tzdata:2026b', repeatedTime: 'first_instant', revision: one};
export const point = (day = 22): ReviewedDailyTime => ({nominal: `2026-11-${day}T07:30:00`, policy,
  resolvedLocal: `2026-11-${day}T07:30:00`, offsetSeconds: 3600, resolution: 'exact', zoneDigest: 'a'.repeat(64)});
export const times = [22, 23, 24, 25, 26].map(day => point(day));
export const inactive: DailyReview = {ruleId: 'rule', ruleRevision: two, title: 'Check the soap', requestedTime: '07:30',
  controlRevision: '0', scheduleRevision: '0', enabled: false, activeTrigger: null, activeRevision: null, activeTitle: null,
  conditionProducts: [], condition: null, mayEnable: true, approvedPolicy: null, proposedPolicy: policy,
  approvedTimes: null, proposedTimes: times, proposedUnavailable: false, approvedUnavailable: false, policyChanged: false, next: null, suppression: null};
export const active: DailyReview = {...inactive, controlRevision: three, scheduleRevision: two, enabled: true,
  activeTrigger: 'daily', activeRevision: one, activeTitle: 'Old daily task', approvedPolicy: policy, approvedTimes: times, next: point()};
export const target = {origin: 'https://domus.example', deployment: 'standalone' as const, applicationBase: '/'};
export const settled = <T>(value: T): EntryRead<T> => ({result: Promise.resolve(value), cancel: vi.fn()});
export const failed = (error: unknown = new EntryReadError('unavailable')): EntryRead<never> => ({result: Promise.reject(error), cancel: vi.fn()});
export function wireTime(value = point(), numericPolicy = false) {
  return {nominal: value.nominal, policy: {zone: value.policy.zone, data_identity: value.policy.dataIdentity,
    repeated_time: value.policy.repeatedTime, revision: numericPolicy ? Number(value.policy.revision) : value.policy.revision},
    resolved_local: value.resolvedLocal, offset_seconds: value.offsetSeconds, resolution: value.resolution, zone_digest: value.zoneDigest};
}
export function wireReview(value = inactive) {
  return {rule_id: value.ruleId, rule_revision: value.ruleRevision, title: value.title, requested_time: value.requestedTime,
    control_revision: value.controlRevision, schedule_revision: value.scheduleRevision, enabled: value.enabled,
    active_trigger: value.activeTrigger, active_rule_revision: value.activeRevision, active_title: value.activeTitle,
    grant_owner: 'household_rule', capability: 'task.create', condition_product_ids: value.conditionProducts, condition: value.condition,
    may_enable: value.mayEnable,
    approved_policy: value.approvedPolicy === null ? null : wireTime({...point(), policy: value.approvedPolicy}).policy,
    proposed_policy: wireTime({...point(), policy: value.proposedPolicy}).policy,
    approved_times: value.approvedTimes?.map(item => wireTime(item)) ?? null,
    proposed_times: value.proposedTimes.map(item => wireTime(item)), proposed_unavailable: value.proposedUnavailable, approved_unavailable: value.approvedUnavailable,
    policy_changed: value.policyChanged, next_time: value.next === null ? null : wireTime(value.next),
    suppression: value.suppression === null ? null : {first: wireTime(value.suppression.first), through_ms: value.suppression.throughMs}};
}
export function response(route: string, data: unknown, status = 200): Response {
  const reply = new Response(JSON.stringify(data), {status, headers: {'Content-Type': 'application/json', 'Cache-Control': 'no-store'}});
  Object.defineProperty(reply, 'url', {value: target.origin + route});
  return reply;
}
export const wireError = (code: string) => ({state: 'blocked', code, message: 'Request blocked.', action_required: 'Review the current state.', correlation_id: 'cor_request'});
export const envelope = (result: unknown, historical = false) => ({state: historical ? 'historical' : 'committed',
  archived_by: historical ? 'restore' : null, operation_id: 'operation', created_at: 1_795_296_000_000,
  result, message: 'Operation recorded.', action_required: 'Review the result.'});
