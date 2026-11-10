import type {RewardRequest, RewardsJournal} from '../application/rewards-controller';
import {rewardCommand} from '../domain/rewards';
import {check, fields, identifier, text} from './json-values';
import {ScopedCommandJournal} from './scoped-command-journal';
import type {OwnedStorage} from './session-journal';

export const REWARD_JOURNAL_KEY = 'domus.rewards.v1';

function decode(raw: string): RewardRequest {
  check(raw.length <= 4096);
  const item = fields(JSON.parse(raw), ['key', 'scope', 'command'], []);
  const request = {key: identifier(item.key), scope: text(item.scope, 1024), command: rewardCommand(item.command)};
  check(JSON.stringify(request) === raw);
  return request;
}
export class RewardsSessionJournal extends ScopedCommandJournal<RewardRequest> implements RewardsJournal {
  constructor(storage: OwnedStorage) {super(storage, REWARD_JOURNAL_KEY, decode);}
}
