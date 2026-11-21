import type {DailyJournal, DailyRequest} from '../application/automation-daily';
import {revisionValue} from '../domain/administration';
import {administrationJSON, check, choice, fields, text, identifier} from './json-values';
import {dailyTime} from './automation-daily-values';
import {ScopedCommandJournal} from './scoped-command-journal';
import type {OwnedStorage} from './session-journal';

export const DAILY_AUTOMATION_JOURNAL_KEY = 'domus.automation-daily.v1';

function decode(raw: string): DailyRequest {
  check(raw.length <= 4096);
  const row = fields(administrationJSON(raw), ['kind', 'ruleId', 'ruleRevision', 'controlRevision', 'scheduleRevision',
    'key', 'scope'], ['reviewed']);
  const kind = choice(row.kind, ['enable', 'disable', 'adopt'] as const);
  check((kind === 'disable') === (row.reviewed === undefined));
  let reviewed;
  if (row.reviewed !== undefined) {
    const item = fields(row.reviewed, ['nominal', 'policy', 'resolvedLocal', 'offsetSeconds', 'resolution', 'zoneDigest'], []);
    const policy = fields(item.policy, ['zone', 'dataIdentity', 'repeatedTime', 'revision'], []);
    reviewed = dailyTime({nominal: item.nominal, policy: {zone: policy.zone, data_identity: policy.dataIdentity,
      repeated_time: policy.repeatedTime, revision: policy.revision}, resolved_local: item.resolvedLocal,
      offset_seconds: item.offsetSeconds, resolution: item.resolution, zone_digest: item.zoneDigest});
  }
  const request: DailyRequest = {kind, ruleId: identifier(row.ruleId), ruleRevision: revisionValue(row.ruleRevision),
    controlRevision: row.controlRevision === '0' ? '0' : revisionValue(row.controlRevision),
    scheduleRevision: row.scheduleRevision === '0' ? '0' : revisionValue(row.scheduleRevision),
    ...(reviewed === undefined ? {} : {reviewed}), key: identifier(row.key), scope: text(row.scope, 1024)};
  check(JSON.stringify(request) === raw);
  return request;
}

export class DailyAutomationSessionJournal extends ScopedCommandJournal<DailyRequest> implements DailyJournal {
  constructor(storage: OwnedStorage) {super(storage, DAILY_AUTOMATION_JOURNAL_KEY, decode);}
}
