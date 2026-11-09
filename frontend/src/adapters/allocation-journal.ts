import type {AllocationJournal, AllocationRequest} from '../application/allocation-controller';
import {revisionValue} from '../domain/administration';
import {allocationPolicy} from './allocation-values';
import {check, fields, identifier, text} from './json-values';
import type {OwnedStorage} from './session-journal';

export const ALLOCATION_JOURNAL_KEY = 'domus.allocation.v1';

function decode(raw: string): AllocationRequest {
  check(raw.length <= 2048);
  const item = fields(JSON.parse(raw), ['key','scope','definitionId','revision','policy'], []);
  const request = {key: identifier(item.key), scope: text(item.scope, 1024),
    definitionId: item.definitionId === null ? null : identifier(item.definitionId),
    revision: item.revision === '0' ? '0' as const : revisionValue(item.revision),
    policy: item.policy === null ? null : allocationPolicy(item.policy)};
  check((request.definitionId !== null || request.policy !== null) && JSON.stringify(request) === raw);
  return request;
}

export class AllocationSessionJournal implements AllocationJournal {
  constructor(private readonly storage: OwnedStorage) {}

  open(scope: string): AllocationRequest | null {
    const raw = this.storage.getItem(ALLOCATION_JOURNAL_KEY);
    if (raw === null) return null;
    const request = decode(raw);
    if (request.scope === scope) return request;
    this.clear(request); return null;
  }

  save(request: AllocationRequest): void {
    const raw = JSON.stringify(request);
    decode(raw); check(this.storage.getItem(ALLOCATION_JOURNAL_KEY) === null);
    this.storage.setItem(ALLOCATION_JOURNAL_KEY, raw);
    check(this.storage.getItem(ALLOCATION_JOURNAL_KEY) === raw);
  }

  clear(request: AllocationRequest): void {
    check(this.storage.getItem(ALLOCATION_JOURNAL_KEY) === JSON.stringify(request));
    this.storage.removeItem(ALLOCATION_JOURNAL_KEY);
    check(this.storage.getItem(ALLOCATION_JOURNAL_KEY) === null);
  }
}
