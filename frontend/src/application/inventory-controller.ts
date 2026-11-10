/** Manage only current household scope and the original unresolved stock command. */
import {inventoryCommand} from '../domain/inventory';
import type {BaseUnit, InventoryCommand, InventoryReport, MovementHistory, PurchaseReceipts, Purchases, PurchaseSessionDetail, PurchaseSessions, ShoppingAction, ShoppingList, ShoppingSources} from '../domain/inventory';
import type {JournalContext} from '../domain/journal';
import type {EntryEntropy, EntryRead} from './ports';

export const INVENTORY_ERRORS = ['permission_denied', 'idempotency_conflict', 'invalid_request',
  'invalid_task_text', 'invalid_inventory_unit', 'invalid_inventory_receipt', 'invalid_material_quantity',
  'invalid_material_precision', 'inventory_product_missing', 'inventory_stock_capacity',
  'invalid_inventory_reason', 'inventory_insufficient_stock', 'inventory_movement_missing',
  'inventory_correction_requires_intake', 'inventory_intake_corrected', 'invalid_replenishment_bounds',
  'invalid_revision', 'revision_conflict', 'invalid_shopping_item', 'shopping_purchase_open',
  'shopping_purchase_missing', 'shopping_receipt_missing', 'shopping_receipt_exceeds_purchase',
  'shopping_balance_closed', 'shopping_receipt_untracked', 'shopping_receipt_posted',
  'shopping_receipt_voided', 'shopping_receipt_balance_cancelled', 'shopping_extra_missing', 'shopping_extra_cleared',
  'invalid_shopping_session', 'shopping_session_missing'] as const;
export type InventoryError = typeof INVENTORY_ERRORS[number] | 'rejected';

export interface InventoryScope {readonly key: string; readonly context: JournalContext; readonly readOnly: boolean;}
export interface InventoryRequest {readonly key: string; readonly scope: string; readonly command: InventoryCommand;}
export type InventoryResult = Readonly<{
  kind: 'committed' | 'historical'; operationId: string; productId: string | null;
  replenishmentSaved?: true;
  shoppingAction?: ShoppingAction;
  sessionId?: string;
  movement: Readonly<{movementId: string; quantity: string; unit: BaseUnit;
    action: 'inventory.intake' | 'inventory.adjust' | 'inventory.correct-intake'}> | null;
}> | Readonly<{kind: 'rejected'; reason: InventoryError; command: InventoryCommand}>;
export interface InventoryServer {
  read(scope: InventoryScope, cursor: string | null): EntryRead<InventoryReport>;
  history(scope: InventoryScope, productId: string, cursor: string | null): EntryRead<MovementHistory>;
  purchases(scope: InventoryScope, cursor: string | null): EntryRead<Purchases>;
  purchaseReceipts(scope: InventoryScope, purchaseId: string, cursor: string | null): EntryRead<PurchaseReceipts>;
  purchaseSessions(scope: InventoryScope, cursor: string | null): EntryRead<PurchaseSessions>;
  purchaseSession(scope: InventoryScope, sessionId: string): EntryRead<PurchaseSessionDetail>;
  shoppingList(scope: InventoryScope, cursor: string | null): EntryRead<ShoppingList>;
  shoppingSources(scope: InventoryScope, productId: string, cursor: string | null): EntryRead<ShoppingSources>;
  send(scope: InventoryScope, request: InventoryRequest): EntryRead<InventoryResult>;
  original(scope: InventoryScope, request: InventoryRequest): EntryRead<InventoryResult | null>;
}
export interface InventoryJournal {
  open(scope: string): InventoryRequest | null;
  save(request: InventoryRequest): void;
  clear(request: InventoryRequest): void;
}
export interface InventoryState {
  readonly scope: InventoryScope;
  readonly report: InventoryReport | null;
  readonly history: MovementHistory | null;
  readonly purchases?: Purchases | null;
  readonly purchaseReceipts?: PurchaseReceipts | null;
  readonly purchaseSessions?: PurchaseSessions | null;
  readonly purchaseSession?: PurchaseSessionDetail | null;
  readonly shoppingList?: ShoppingList | null;
  readonly shoppingSources?: ShoppingSources | null;
  readonly pending: boolean;
  readonly busy: boolean;
  readonly result: InventoryResult | null;
  readonly notice: 'unavailable' | 'uncertain' | null;
}

function mayWrite(report: InventoryReport | null, action: InventoryCommand['action']): boolean {
  if (action === 'shopping.add-extra') return report?.mayRequest === true;
  if (action === 'shopping.purchase' || action === 'shopping.receive' || action === 'shopping.clear-extra'
    || action === 'shopping.record-session' || action === 'shopping.cancel-balance' || action === 'shopping.void-receipt')
    return report?.mayShop === true;
  return report?.mayManage === true;
}

export class InventoryController {
  private view: InventoryState | null = null;
  private owned: EntryRead<unknown> | null = null;
  private request: InventoryRequest | null = null;

  constructor(private readonly server: InventoryServer, private readonly journal: InventoryJournal,
    private readonly entropy: EntryEntropy, private readonly publish: (state: InventoryState | null) => void) {}

  bind(scope: InventoryScope | null): void {
    const previous = this.view?.scope;
    if (scope?.key === previous?.key && scope?.readOnly === previous?.readOnly) return;
    this.owned?.cancel();
    this.owned = null;
    this.request = null;
    this.view = scope === null ? null : {scope, report: null, history: null, pending: false, busy: false, result: null, notice: null};
    this.publish(this.view);
    if (scope === null) return;
    try {
      this.request = this.journal.open(scope.key);
      this.set({pending: this.request !== null});
    } catch {this.set({pending: true, notice: 'unavailable'});}
    void this.refresh();
  }

  async refresh(): Promise<void> {
    const state = this.view;
    await this.load(null);
    if (state?.history && this.view?.scope === state.scope && this.view.history)
      await this.showHistory(state.history.productId);
    if (state?.purchases && this.view?.scope === state.scope && this.view.purchases)
      await this.showPurchases();
    if (state?.purchaseSessions && this.view?.scope === state.scope && this.view.purchaseSessions)
      await this.showPurchaseSessions();
    if (state?.purchaseSession && this.view?.scope === state.scope && this.view.purchaseSession)
      await this.showPurchaseSession(state.purchaseSession.session.id);
    if (state?.purchaseReceipts && this.view?.scope === state.scope && this.view.purchaseReceipts)
      await this.showPurchaseReceipts(state.purchaseReceipts.purchase.id);
    if (state?.shoppingList && this.view?.scope === state.scope && this.view.shoppingList)
      await this.showShoppingList();
    if (state?.shoppingSources && this.view?.scope === state.scope && this.view.shoppingSources)
      await this.showShoppingSources(state.shoppingSources.item.productId!);
  }

  async showHistory(productId: string): Promise<void> {await this.loadHistory(productId, null);}

  async moreHistory(): Promise<void> {
    const history = this.view?.history;
    if (history?.cursor) await this.loadHistory(history.productId, history.cursor);
  }

  closeHistory(): void {
    if (this.view && this.owned === null) this.set({history: null});
  }

  async more(): Promise<void> {
    const cursor = this.view?.report?.cursor;
    if (cursor) await this.load(cursor);
  }

  async showPurchases(): Promise<void> {await this.loadPurchases(null);}

  async morePurchases(): Promise<void> {
    const cursor = this.view?.purchases?.cursor;
    if (cursor) await this.loadPurchases(cursor);
  }

  async showPurchaseReceipts(purchaseId: string): Promise<void> {
    await this.loadPurchaseReceipts(purchaseId, null);
  }

  async morePurchaseReceipts(): Promise<void> {
    const page = this.view?.purchaseReceipts;
    if (page?.cursor) await this.loadPurchaseReceipts(page.purchase.id, page.cursor);
  }

  async showPurchaseSessions(more = false): Promise<void> {
    const state = this.view;
    if (state === null || state.report === null || this.owned !== null) return;
    const cursor = more ? state.purchaseSessions?.cursor : null;
    if (more && !cursor) return;
    const loaded = await this.run(this.server.purchaseSessions(state.scope, cursor!), page => {
      this.set({purchaseSessions:more ? {...page, items:[...state.purchaseSessions!.items, ...page.items]} : page,
        notice:state.pending ? state.notice : null});
    }, 'unavailable');
    if (!loaded && this.view?.scope === state.scope) this.set({purchaseSessions:null});
  }

  async showPurchaseSession(sessionId: string): Promise<void> {
    const state = this.view;
    if (state === null || state.report === null || this.owned !== null) return;
    const loaded = await this.run(this.server.purchaseSession(state.scope, sessionId), page => {
      this.set({purchaseSession:page, notice:state.pending ? state.notice : null});
    }, 'unavailable');
    if (!loaded && this.view?.scope === state.scope) this.set({purchaseSession:null});
  }

  async showShoppingList(more = false): Promise<void> {
    const state = this.view;
    if (state === null || state.report === null || this.owned !== null) return;
    const cursor = more ? state.shoppingList?.cursor : null;
    if (more && !cursor) return;
    const loaded = await this.run(this.server.shoppingList(state.scope, cursor!), page => {
      this.set({shoppingList:more ? {...page, items:[...state.shoppingList!.items, ...page.items]} : page,
        notice:state.pending ? state.notice : null});
    }, 'unavailable');
    if (!loaded && this.view?.scope === state.scope) this.set({shoppingList:null, shoppingSources:null});
  }

  async showShoppingSources(productId: string, more = false): Promise<void> {
    const state = this.view;
    if (state === null || state.shoppingList == null || this.owned !== null) return;
    const cursor = more ? state.shoppingSources?.cursor : null;
    if (more && !cursor) return;
    const loaded = await this.run(this.server.shoppingSources(state.scope, productId, cursor!), page => {
      this.set({shoppingSources:more ? {...page, items:[...state.shoppingSources!.items, ...page.items]} : page,
        notice:state.pending ? state.notice : null});
    }, 'unavailable');
    if (!loaded && this.view?.scope === state.scope) this.set({shoppingSources:null});
  }

  async moreShoppingSources(): Promise<void> {
    const productId = this.view?.shoppingSources?.item.productId;
    if (productId) await this.showShoppingSources(productId, true);
  }

  async submit(value: unknown): Promise<void> {
    const state = this.view;
    if (state === null || state.scope.readOnly || state.pending || state.report === null || this.owned !== null) return;
    let request: InventoryRequest;
    try {
      const command = inventoryCommand(value);
      if (!mayWrite(state.report, command.action)) return;
      request = {key: this.entropy.requestKey(), scope: state.scope.key, command};
      this.journal.save(request);
    } catch {this.set({notice: 'unavailable'}); return;}
    this.request = request;
    this.set({pending: true, notice: null, result: null});
    await this.send(state.scope, request);
  }

  async recover(): Promise<void> {
    const scope = this.view?.scope, request = this.request;
    if (!scope || request === null || this.owned !== null) return;
    const read = await this.run(this.server.original(scope, request), result => {
      if (result !== null) this.finish(request, result);
    }, 'uncertain');
    if (!read || this.view?.scope !== scope) return;
    if (this.request === null) await this.refresh();
    else if (!scope.readOnly && mayWrite(this.view.report, request.command.action)) await this.send(scope, request);
  }

  private set(patch: Partial<InventoryState>): void {
    this.view = {...this.view!, ...patch};
    this.publish(this.view);
  }

  private async load(cursor: string | null): Promise<void> {
    const state = this.view;
    if (state === null || this.owned !== null) return;
    const loaded = await this.run(this.server.read(state.scope, cursor), page => {
      this.set({report: cursor === null ? page : {...page, products: [...state.report!.products, ...page.products]},
        notice: state.pending ? state.notice : null});
    }, 'unavailable');
    if (!loaded && this.view?.scope === state.scope)
      this.set({report:null, history:null, purchases:null, purchaseReceipts:null,
        shoppingList:null, shoppingSources:null, purchaseSessions:null, purchaseSession:null});
  }

  private async loadPurchases(cursor: string | null): Promise<void> {
    const state = this.view;
    if (state === null || state.report === null || this.owned !== null) return;
    const loaded = await this.run(this.server.purchases(state.scope, cursor), page => {
      this.set({purchases: cursor === null ? page : {...page, items:[...state.purchases!.items, ...page.items]},
        notice: state.pending ? state.notice : null});
    }, 'unavailable');
    if (!loaded && this.view?.scope === state.scope) this.set({purchases:null, purchaseReceipts:null});
  }

  private async loadPurchaseReceipts(purchaseId: string, cursor: string | null): Promise<void> {
    const state = this.view;
    if (state === null || (state.purchases == null && state.purchaseSession == null) || this.owned !== null) return;
    const loaded = await this.run(this.server.purchaseReceipts(state.scope, purchaseId, cursor), page => {
      this.set({purchaseReceipts: cursor === null ? page : {...page, items:[...state.purchaseReceipts!.items, ...page.items]},
        notice: state.pending ? state.notice : null});
    }, 'unavailable');
    if (!loaded && this.view?.scope === state.scope) this.set({purchaseReceipts:null});
  }

  private async loadHistory(productId: string, cursor: string | null): Promise<void> {
    const state = this.view;
    if (state === null || state.report === null || this.owned !== null) return;
    const loaded = await this.run(this.server.history(state.scope, productId, cursor), page => {
      const history = cursor === null ? page : {...page, movements: [...state.history!.movements, ...page.movements]};
      this.set({history, notice: state.pending ? state.notice : null});
    }, 'unavailable');
    if (!loaded && this.view?.scope === state.scope) this.set({history: null});
  }

  private async send(scope: InventoryScope, request: InventoryRequest): Promise<void> {
    if (await this.run(this.server.send(scope, request), result => this.finish(request, result), 'uncertain'))
      await this.refresh();
  }

  private finish(request: InventoryRequest, result: InventoryResult): void {
    this.journal.clear(request);
    this.request = null;
    this.set({pending: false, notice: null, result});
  }

  private async run<T>(owned: EntryRead<T>, use: (value: T) => void,
    notice: 'unavailable' | 'uncertain'): Promise<boolean> {
    this.owned = owned;
    this.set({busy: true});
    try {
      const value = await owned.result;
      if (this.owned !== owned) return false;
      use(value);
      return true;
    } catch {
      if (this.owned === owned) this.set({notice});
      return false;
    } finally {
      if (this.owned === owned) {
        this.owned = null;
        this.set({busy: false});
      }
    }
  }
}
