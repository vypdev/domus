import type {AutomationExecutionJournal, AutomationExecutionRequest} from '../application/automation-execution';
import {revisionValue} from '../domain/administration';
import {boolean, check, choice, fields, identifier, text} from './json-values';
import {ScopedCommandJournal} from './scoped-command-journal';
import type {OwnedStorage} from './session-journal';

export const AUTOMATION_EXECUTION_JOURNAL_KEY = 'domus.automation-execution.v1';

function decode(raw: string): AutomationExecutionRequest {
  check(raw.length <= 4096);
  const row = fields(JSON.parse(raw), ['kind', 'ruleId', 'ruleRevision', 'controlRevision', 'key', 'scope'], ['enabled']);
  const kind = choice(row.kind, ['configure', 'run'] as const);
  const ruleId = identifier(row.ruleId), ruleRevision = revisionValue(row.ruleRevision);
  const key = identifier(row.key), scope = text(row.scope, 1024);
  const request: AutomationExecutionRequest = kind === 'configure'
    ? {kind, ruleId, ruleRevision, controlRevision: row.controlRevision === '0' ? '0' : revisionValue(row.controlRevision),
      enabled: boolean(row.enabled), key, scope}
    : {kind, ruleId, ruleRevision, controlRevision: revisionValue(row.controlRevision), key, scope};
  check(JSON.stringify(request) === raw);
  return request;
}

export class AutomationExecutionSessionJournal extends ScopedCommandJournal<AutomationExecutionRequest>
  implements AutomationExecutionJournal {
  constructor(storage: OwnedStorage) {super(storage, AUTOMATION_EXECUTION_JOURNAL_KEY, decode);}
}
