import type {AutomationDraftJournal, DraftRequest} from '../application/automation-drafts';
import {isDailyTime} from '../application/automation-schedule-preview';
import {revisionValue} from '../domain/administration';
import {taskText} from '../domain/tasks';
import {check, fields, identifier, text} from './json-values';
import {ScopedCommandJournal} from './scoped-command-journal';
import type {OwnedStorage} from './session-journal';

export const AUTOMATION_DRAFT_JOURNAL_KEY = 'domus.automation-draft.v1';

function decode(raw: string): DraftRequest {
  check(raw.length <= 4096);
  const row = fields(JSON.parse(raw), ['key', 'scope', 'ruleId', 'revision', 'rule'], []);
  const rule = fields(row.rule, ['title', 'productId'], ['dailyTime']);
  const dailyTime = rule.dailyTime;
  check(dailyTime === undefined || isDailyTime(dailyTime));
  const ruleId = row.ruleId === null ? null : identifier(row.ruleId);
  const revision = ruleId === null && row.revision === '0' ? '0' : revisionValue(row.revision);
  check((ruleId === null) === (revision === '0'));
  const request: DraftRequest = {key: identifier(row.key), scope: text(row.scope, 1024), ruleId, revision,
    rule: {title: taskText(rule.title, 160, true), productId: rule.productId === null ? null : identifier(rule.productId),
      ...(dailyTime === undefined ? {} : {dailyTime})}};
  check(JSON.stringify(request) === raw);
  return request;
}

export class AutomationDraftSessionJournal extends ScopedCommandJournal<DraftRequest> implements AutomationDraftJournal {
  constructor(storage: OwnedStorage) {super(storage, AUTOMATION_DRAFT_JOURNAL_KEY, decode);}
}
