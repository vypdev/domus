import type {InventoryJournal, InventoryRequest} from '../application/inventory-controller';
import {inventoryCommand} from '../domain/inventory';
import {check, fields, identifier, text} from './json-values';
import {ScopedCommandJournal} from './scoped-command-journal';
import type {OwnedStorage} from './session-journal';

export const INVENTORY_JOURNAL_KEY = 'domus.inventory.v1';

function decode(raw: string): InventoryRequest {
  // Allow the bounded note plus the existing scope even when both require JSON escaping.
  // The slot, canonical ordering and exact original legacy bytes remain unchanged.
  check(raw.length <= 12288);
  const value = fields(JSON.parse(raw), ['key', 'scope', 'command'], []);
  const request = {key: identifier(value.key), scope: text(value.scope, 1024), command: inventoryCommand(value.command)};
  check(JSON.stringify(request) === raw);
  return request;
}

export class InventorySessionJournal extends ScopedCommandJournal<InventoryRequest> implements InventoryJournal {
  constructor(storage: OwnedStorage) {super(storage, INVENTORY_JOURNAL_KEY, decode);}
}
