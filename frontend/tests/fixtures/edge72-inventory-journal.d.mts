import type {OwnedStorage} from '../../src/adapters/session-journal';
import type {InventoryServer,InventoryRequest,InventoryScope,InventoryState} from '../../src/application/inventory-controller';
import type {EntryEntropy} from '../../src/application/ports';
/** Actual previous-client methods exercised by compatibility tests; no whole-app rollback claim. */
export const INVENTORY_JOURNAL_KEY:string;
export class InventorySessionJournal {
  constructor(storage:OwnedStorage);
  open(scope:string):InventoryRequest|null;
  save(request:InventoryRequest):void;
  clear(request:InventoryRequest):void;
}
export class InventoryController {
  constructor(server:InventoryServer,journal:InventorySessionJournal,entropy:EntryEntropy,publish:(state:InventoryState|null)=>void);
  bind(scope:InventoryScope|null):void;
  submit(value:unknown):Promise<void>;
  recover():Promise<void>;
}
