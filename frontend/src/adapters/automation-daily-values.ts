/** Preserve the approved temporal evidence, including provider identity and exact revisions. */
import {dailyInstant} from '../application/automation-daily';
import type {DailyPolicy, DailyReview, ReviewedDailyTime} from '../application/automation-daily';
import {DAILY_RESOLUTIONS, isDailyTime} from '../application/automation-schedule-preview';
import {revisionValue} from '../domain/administration';
import {civilDate} from '../domain/civil-date';
import {taskText} from '../domain/tasks';
import {boolean, check, choice, fields, identifier, integer, responseRevision, text} from './json-values';
import {draftCondition} from './automation-condition-values';

export const MAX_DAILY_INSTANT = 253_402_300_799_999;

export function dailyLocal(value: unknown): string {
  const local = text(value, 26);
  check(/^\d{4}-\d{2}-\d{2}T(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9](?:\.[0-9]{3}(?:000)?)?$/u.test(local)
    && civilDate(local.slice(0, 10)));
  return local;
}

export function dailyPolicy(value: unknown, receipt = false): DailyPolicy {
  const row = fields(value, ['zone', 'data_identity', 'repeated_time', 'revision'], []);
  const zone = text(row.zone, 128), dataIdentity = text(row.data_identity, 128);
  check(/^[A-Za-z0-9_+\-/]+$/u.test(zone) && zone.split('/').every(part => part.length > 0)
    && /^[A-Za-z0-9:/_.\-]+$/u.test(dataIdentity));
  return {zone, dataIdentity, repeatedTime: choice(row.repeated_time, ['first_instant', 'second_instant'] as const),
    revision: receipt ? responseRevision(row.revision) : revisionValue(row.revision)};
}

export function dailyTime(value: unknown, receipt = false): ReviewedDailyTime {
  const row = fields(value, ['nominal', 'policy', 'resolved_local', 'offset_seconds', 'resolution', 'zone_digest'], []);
  const nominal = dailyLocal(row.nominal), resolvedLocal = dailyLocal(row.resolved_local);
  const policy = dailyPolicy(row.policy, receipt), offsetSeconds = integer(row.offset_seconds, -86399);
  const resolution = choice(row.resolution, DAILY_RESOLUTIONS), zoneDigest = text(row.zone_digest, 64);
  check(offsetSeconds <= 86399 && /^[a-f0-9]{64}$/u.test(zoneDigest)
    && (resolution === 'gap_first_valid' ? Date.parse(resolvedLocal + 'Z') > Date.parse(nominal + 'Z')
      : Date.parse(resolvedLocal + 'Z') === Date.parse(nominal + 'Z'))
    && (resolution !== 'fold_first' || policy.repeatedTime === 'first_instant')
    && (resolution !== 'fold_second' || policy.repeatedTime === 'second_instant'));
  const result = {nominal, policy, resolvedLocal, offsetSeconds, resolution, zoneDigest};
  check(dailyInstant(result) >= 0 && dailyInstant(result) <= MAX_DAILY_INSTANT);
  return result;
}

export function dailyTimeBody(value: ReviewedDailyTime) {
  const {policy} = value;
  return {nominal: value.nominal,
    policy: {zone: policy.zone, data_identity: policy.dataIdentity, repeated_time: policy.repeatedTime, revision: policy.revision},
    resolved_local: value.resolvedLocal, offset_seconds: value.offsetSeconds, resolution: value.resolution,
    zone_digest: value.zoneDigest};
}

function samePolicy(left: DailyPolicy, right: DailyPolicy): boolean {
  return left.zone === right.zone && left.dataIdentity === right.dataIdentity && left.repeatedTime === right.repeatedTime;
}
function upcoming(value: unknown, policy: DailyPolicy | null): readonly ReviewedDailyTime[] {
  check(policy !== null && Array.isArray(value) && value.length === 5);
  const times = value.map(item => dailyTime(item));
  let previousInstant = -1, previousDate = '';
  for (const item of times) {
    check(samePolicy(item.policy, policy) && item.policy.revision === policy.revision
      && dailyInstant(item) > previousInstant && item.nominal.slice(0, 10) > previousDate);
    previousInstant = dailyInstant(item); previousDate = item.nominal.slice(0, 10);
  }
  return times;
}

export function dailyReview(value: unknown, ruleId: string, ruleRevision: string | null): DailyReview {
  const row = fields(value, ['rule_id', 'rule_revision', 'title', 'requested_time', 'control_revision', 'schedule_revision',
    'enabled', 'active_trigger', 'active_rule_revision', 'active_title', 'grant_owner', 'capability', 'condition_product_ids', 'condition',
    'may_enable', 'approved_policy', 'proposed_policy', 'approved_times', 'proposed_times', 'proposed_unavailable', 'approved_unavailable',
    'policy_changed', 'next_time', 'suppression'], []);
  const actualRevision = revisionValue(row.rule_revision);
  check(identifier(row.rule_id) === ruleId && (ruleRevision === null || actualRevision === ruleRevision)
    && isDailyTime(row.requested_time) && row.grant_owner === 'household_rule' && row.capability === 'task.create');
  const controlRevision = row.control_revision === '0' ? '0' : revisionValue(row.control_revision);
  const scheduleRevision = row.schedule_revision === '0' ? '0' : revisionValue(row.schedule_revision);
  const enabled = boolean(row.enabled), approvedUnavailable = boolean(row.approved_unavailable);
  const activeTrigger = row.active_trigger === null ? null : choice(row.active_trigger, ['manual', 'daily'] as const);
  const activeRevision = row.active_rule_revision === null ? null : revisionValue(row.active_rule_revision);
  const activeTitle = row.active_title === null ? null : taskText(row.active_title, 160, true);
  check((activeTrigger === null) === (activeRevision === null) && (activeTrigger === null) === (activeTitle === null)
    && (activeTrigger === null || controlRevision !== '0'));
  const proposedPolicy = dailyPolicy(row.proposed_policy);
  const approvedPolicy = row.approved_policy === null ? null : dailyPolicy(row.approved_policy);
  const approvedTimes = row.approved_times === null ? null : upcoming(row.approved_times, approvedPolicy);
  const proposedUnavailable = boolean(row.proposed_unavailable);
  let proposedTimes: readonly ReviewedDailyTime[];
  if (proposedUnavailable) {
    check(Array.isArray(row.proposed_times) && row.proposed_times.length === 0);
    proposedTimes = [];
  } else proposedTimes = upcoming(row.proposed_times, proposedPolicy);
  const next = row.next_time === null ? null : dailyTime(row.next_time);
  const policyChanged = boolean(row.policy_changed);
  check(proposedTimes.every(item => item.nominal === item.nominal.slice(0, 10) + 'T' + row.requested_time + ':00')
    && (approvedPolicy === null) === (scheduleRevision === '0') && (next === null) === (scheduleRevision === '0')
    && enabled === (activeTrigger === 'daily' && scheduleRevision !== '0')
    && (approvedPolicy === null ? !approvedUnavailable && approvedTimes === null && !policyChanged
      : (approvedUnavailable === (approvedTimes === null) && samePolicy(next!.policy, approvedPolicy)
        && next!.policy.revision === approvedPolicy.revision && policyChanged === !samePolicy(approvedPolicy, proposedPolicy))));
  check(Array.isArray(row.condition_product_ids) && row.condition_product_ids.length <= 64);
  const conditionProducts = row.condition_product_ids.map(item => identifier(item));
  check(new Set(conditionProducts).size === conditionProducts.length);
  let suppression = null;
  if (row.suppression !== null) {
    const stopped = fields(row.suppression, ['first', 'through_ms'], []);
    const first = dailyTime(stopped.first), throughMs = integer(stopped.through_ms, 0);
    check(approvedPolicy !== null && throughMs <= MAX_DAILY_INSTANT && throughMs >= dailyInstant(first));
    suppression = {first, throughMs};
  }
  return {ruleId, ruleRevision: revisionValue(row.rule_revision), title: taskText(row.title, 160, true),
    requestedTime: row.requested_time, controlRevision, scheduleRevision, enabled, activeTrigger, activeRevision, activeTitle,
    mayEnable: boolean(row.may_enable), conditionProducts, condition: draftCondition(row.condition), approvedPolicy, proposedPolicy, approvedTimes, proposedTimes,
    proposedUnavailable, approvedUnavailable, policyChanged, next, suppression};
}
