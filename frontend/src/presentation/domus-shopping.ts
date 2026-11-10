import {LitElement, css, html, nothing} from 'lit';
import type {PropertyValues} from 'lit';
import {registerButton} from '@vypdev/ha-ui/button';
import {buttonState} from '@vypdev/ha-ui/button-contracts';
import {registerCard} from '@vypdev/ha-ui/card';
import {cardState} from '@vypdev/ha-ui/card-contracts';
import type {InventoryState} from '../application/inventory-controller';
import {STOCK_REASON_LIMIT, intakeQuantity, stockUnits} from '../domain/inventory';
import type {BaseUnit, InventoryCommand, PhysicalReceipt, ProductStock, Purchase, PurchaseReceipts, PurchaseSession} from '../domain/inventory';
import {taskText} from '../domain/tasks';
import {inventoryMessage} from './inventory-messages';
import type {InventoryMessage} from './inventory-messages';
import {instant} from './messages';
import type {Language} from './messages';
import './domus-shopping-list';

export type ShoppingIntent = {readonly type: 'purchases' | 'more-purchases' | 'more-purchase-receipts'
    | 'purchase-sessions' | 'more-purchase-sessions'}
  | {readonly type: 'purchase-receipts'; readonly purchaseId: string}
  | {readonly type: 'purchase-session'; readonly sessionId: string}
  | {readonly type: 'submit'; readonly command: InventoryCommand};

export class DomusShopping extends LitElement {
  static properties = {view:{attribute:false}, language:{attribute:false}, selected:{state:true},
    purchaseError:{state:true}, arrivalError:{state:true}, cancelError:{state:true}};

  static styles = css`
    .shopping, form, label, li {display:grid;gap:8px}
    ol {display:grid;gap:12px;margin:0;padding:0;list-style:none}
    li + li {padding-block-start:8px;border-block-start:1px solid var(--line)}
    h4, h5, p, dl {margin:0} dl {display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px}
    dd {margin:0} dt {font-weight:650}
    input,select {font:inherit;color:inherit;background:var(--surface);padding:8px;border:1px solid var(--line);
      border-radius:8px;min-width:0}
    li,code {overflow-wrap:anywhere}
    :focus-visible {outline:3px solid var(--accent);outline-offset:3px}
  `;

  declare view: InventoryState;
  declare language: Language;
  private declare selected: string;
  private declare purchaseError: 'invalidName' | 'invalidQuantity' | null;
  private declare cancelError: boolean;
  private declare arrivalError: 'invalidQuantity' | 'shopping_receipt_exceeds_purchase' | null;

  constructor() {
    super();
    this.selected = '';
    this.purchaseError = null;
    this.arrivalError = null;
    this.cancelError = false;
  }

  protected updated(changed: PropertyValues<this>): void {
    if (!changed.has('view')) return;
    const previous = changed.get('view'), {result, purchaseReceipts, purchaseSession} = this.view;
    if (purchaseSession && purchaseSession.session.id !== previous?.purchaseSession?.session.id)
      this.renderRoot.querySelector<HTMLElement>('#purchase-session-title')?.focus();
    if (purchaseReceipts && purchaseReceipts.purchase.id !== previous?.purchaseReceipts?.purchase.id) {
      this.arrivalError = null;
      this.cancelError = false;
      this.renderRoot.querySelector<HTMLElement>('#purchase-receipts-title')?.focus();
      this.renderRoot.querySelector<HTMLFormElement>('#arrival-form')?.reset();
      this.renderRoot.querySelector<HTMLFormElement>('#cancel-form')?.reset();
      const confirmation = this.renderRoot.querySelector<HTMLDetailsElement>('#cancel-confirmation');
      if (confirmation) confirmation.open = false;
    }
    if (result?.kind === 'committed' && result !== previous?.result) {
      if (result.shoppingAction === 'shopping.purchase') {
        this.selected = '';
        this.renderRoot.querySelector<HTMLFormElement>('#purchase-form')?.reset();
      }
      if (result.shoppingAction === 'shopping.receive')
        this.renderRoot.querySelector<HTMLFormElement>('#arrival-form')?.reset();
    }
  }

  private text(key: InventoryMessage): string {return inventoryMessage(key, this.language);}
  private amount(quantity: string, unit: BaseUnit): string {
    return (this.language === 'es' ? quantity.replace('.', ',') : quantity) + ' ' + this.text(unit);
  }
  private intent(detail: ShoppingIntent): void {
    this.dispatchEvent(new CustomEvent('domus-inventory-intent', {detail, bubbles:true, composed:true}));
  }
  private button(key: InventoryMessage, blocked: boolean, detail?: ShoppingIntent) {
    return html`<vyp-ha-button type=${detail ? 'button' : 'submit'}
      .state=${buttonState({label:this.text(key), variant:detail ? 'outlined' : 'primary'})} ?disabled=${blocked}
      @ha-press-request=${detail ? () => this.intent(detail) : nothing}></vyp-ha-button>`;
  }

  private purchaseForm(products: readonly ProductStock[], blocked: boolean) {
    const product = products.find(item => item.id === this.selected);
    const unit = product?.unit ?? 'piece';
    return html`<form id="purchase-form" novalidate @submit=${(event: SubmitEvent) => {
      event.preventDefault();
      if (blocked) return;
      const fields = new FormData(event.currentTarget as HTMLFormElement);
      const quantity = intakeQuantity(String(fields.get('quantity')), unit);
      if (quantity === null) {this.purchaseError = 'invalidQuantity'; return;}
      let name: string | null = null;
      if (product === undefined) {
        try {name = taskText(fields.get('name'), 160, true);}
        catch {this.purchaseError = 'invalidName'; return;}
      }
      this.purchaseError = null;
      this.intent({type:'submit',command:{action:'shopping.purchase',product_id:product?.id ?? null,name,quantity}});
    }}>
      <label>${this.text('shoppingItem')}<select .value=${this.selected} ?disabled=${blocked}
        @change=${(event: Event) => {this.selected = (event.target as HTMLSelectElement).value; this.purchaseError = null;}}>
        <option value="">${this.text('freeItem')}</option>
        ${products.map(item => html`<option value=${item.id} ?disabled=${item.outstandingPurchase !== '0'}>${item.name}</option>`)}
      </select></label>
      ${product === undefined
        ? html`<label>${this.text('freeItemName')}<input name="name" required maxlength="160" ?disabled=${blocked}
            aria-invalid=${this.purchaseError === 'invalidName'}
            aria-describedby=${this.purchaseError === 'invalidName' ? 'purchase-error' : nothing}></label>`
        : html`<p>${this.text('shoppingNeeded')} · ${this.amount(product.shoppingNeeded, unit)}</p>`}
      <label>${this.text('purchaseQuantity')}<input name="quantity" required maxlength="19"
        inputmode=${unit === 'piece' ? 'numeric' : 'decimal'} ?disabled=${blocked}
        aria-invalid=${this.purchaseError === 'invalidQuantity'}
        aria-describedby=${this.purchaseError === 'invalidQuantity' ? 'purchase-error' : nothing}></label>
      <p>${this.text('unit')} · ${this.text(unit)}</p>
      ${this.purchaseError === null ? nothing : html`<p role="alert" id="purchase-error">${this.text(this.purchaseError)}</p>`}
      ${this.button('recordPurchase', blocked)}
    </form>`;
  }

  private facts(purchase: Purchase) {
    return html`<dl>${(['purchased', 'received', 'remaining', 'pendingStock'] as const).map(key =>
      html`<dt>${this.text(key)}</dt><dd>${this.amount(purchase[key], purchase.unit)}</dd>`)}
      ${purchase.cancelled === '0' ? nothing : html`<dt>${this.text('cancelled')}</dt>
        <dd>${this.amount(purchase.cancelled, purchase.unit)}</dd>`}</dl>
      <p>${purchase.authorAlias ?? purchase.memberId} · ${instant(Number(purchase.createdAt), this.language)}</p>`;
  }

  private arrivalForm(purchase: Purchase, blocked: boolean) {
    return html`<form id="arrival-form" novalidate @submit=${(event: SubmitEvent) => {
      event.preventDefault();
      if (blocked) return;
      const fields = new FormData(event.currentTarget as HTMLFormElement);
      const quantity = intakeQuantity(String(fields.get('quantity')), purchase.unit);
      if (quantity === null) {this.arrivalError = 'invalidQuantity'; return;}
      if (stockUnits(quantity) > stockUnits(purchase.remaining)) {
        this.arrivalError = 'shopping_receipt_exceeds_purchase'; return;
      }
      this.arrivalError = null;
      this.intent({type:'submit',command:{action:'shopping.receive',purchase_id:purchase.id,
        quantity,expected_revision:purchase.revision}});
    }}>
      <label>${this.text('arrivalQuantity')}<input name="quantity" required maxlength="19"
        inputmode=${purchase.unit === 'piece' ? 'numeric' : 'decimal'} ?disabled=${blocked}
        aria-invalid=${this.arrivalError !== null}
        aria-describedby=${this.arrivalError === null ? nothing : 'arrival-error'}></label>
      ${this.arrivalError === null ? nothing : html`<p role="alert" id="arrival-error">${this.text(this.arrivalError)}</p>`}
      ${this.button('recordArrival', blocked)}
    </form>`;
  }

  private cancellationForm(purchase: Purchase, blocked: boolean) {
    return html`<details id="cancel-confirmation"><summary>${this.text('cancelBalance')}</summary>
      <form id="cancel-form" novalidate @submit=${(event: SubmitEvent) => {
        event.preventDefault();
        if (blocked) return;
        const fields = new FormData(event.currentTarget as HTMLFormElement);
        let reason: string;
        try {reason = taskText(fields.get('reason'), STOCK_REASON_LIMIT, true);}
        catch {this.cancelError = true; return;}
        this.cancelError = false;
        this.intent({type:'submit', command:{action:'shopping.cancel-balance', purchase_id:purchase.id,
          reason, expected_revision:purchase.revision}});
      }}>
        <p>${this.text('cancellationAmount')} · <strong>${this.amount(purchase.remaining, purchase.unit)}</strong></p>
        <label>${this.text('reason')}<input name="reason" required maxlength=${STOCK_REASON_LIMIT} ?disabled=${blocked}
          aria-invalid=${this.cancelError} aria-describedby=${this.cancelError ? 'cancel-error' : nothing}></label>
        ${this.cancelError ? html`<p role="alert" id="cancel-error">${this.text('invalid_inventory_reason')}</p>` : nothing}
        ${this.button('confirmCancellation', blocked)}
      </form>
    </details>`;
  }

  private physicalReceipt(entry: PhysicalReceipt, purchase: Purchase, mayPost: boolean, blocked: boolean) {
    const tracked = purchase.productId !== null;
    return html`<li>
      <p><strong>${this.amount(entry.quantity, purchase.unit)}</strong> ·
        ${entry.authorAlias ?? entry.memberId} · ${instant(Number(entry.createdAt), this.language)}</p>
      <p>${this.text(tracked ? entry.movementId === null ? 'awaitingPosting' : 'posted' : 'untrackedReceived')}</p>
      <details><summary>${this.text('receipt')}</summary><code>${entry.id}</code>
        ${entry.movementId === null ? nothing : html`<p>${this.text('movement')} <code>${entry.movementId}</code></p>`}
      </details>
      ${tracked && entry.movementId === null && mayPost ? this.button('postToPantry', blocked,
        {type:'submit',command:{action:'shopping.post-receipt',purchase_id:purchase.id,receipt_id:entry.id}}) : nothing}
    </li>`;
  }

  private detail(page: PurchaseReceipts, mayShop: boolean, mayPost: boolean, blocked: boolean, busy: boolean) {
    const {purchase, items, cursor, cancellation} = page;
    return html`<section class="shopping" aria-labelledby="purchase-receipts-title">
      <h4 id="purchase-receipts-title" tabindex="-1">${this.text('physicalReceipts')} · ${purchase.name}</h4>
      ${this.facts(purchase)}
      ${mayShop && purchase.remaining !== '0'
        ? html`${this.arrivalForm(purchase, blocked)}${this.cancellationForm(purchase, blocked)}` : nothing}
      ${cancellation === null ? nothing : html`<div class="shopping">
        <h5>${this.text('balanceCancellation')}</h5>
        <p>${cancellation.authorAlias ?? cancellation.memberId} · ${instant(Number(cancellation.createdAt), this.language)}</p>
        <dl><dt>${this.text('reason')}</dt><dd>${cancellation.reason}</dd></dl>
      </div>`}
      ${items.length === 0 ? html`<p>${this.text('emptyReceipts')}</p>`
        : html`<ol>${items.map(entry => this.physicalReceipt(entry, purchase, mayPost, blocked))}</ol>`}
      ${cursor === null ? nothing : this.button('olderReceipts', busy, {type:'more-purchase-receipts'})}
    </section>`;
  }

  private sessionLabel(session: PurchaseSession): string {
    return (session.authorAlias ?? session.memberId) + ' · ' + instant(Number(session.createdAt), this.language);
  }

  private sessionHistory(busy: boolean) {
    const {purchaseSessions, purchaseSession, result} = this.view;
    const recent = result?.kind === 'committed' ? result.sessionId : undefined;
    return html`<section class="shopping" aria-labelledby="session-history-title">
      <h4 id="session-history-title">${this.text('sessionHistory')}</h4>
      ${recent ? this.button('showRecordedSession', busy, {type:'purchase-session',sessionId:recent}) : nothing}
      ${purchaseSessions == null ? this.button('showSessions', busy, {type:'purchase-sessions'}) : html`
        ${purchaseSessions.items.length === 0 ? html`<p>${this.text('emptySessions')}</p>` : html`<ol>
          ${purchaseSessions.items.map(session => html`<li><strong>${this.sessionLabel(session)}</strong>
            ${this.button('showSessionItems', busy, {type:'purchase-session',sessionId:session.id})}</li>`)}
        </ol>`}
        ${purchaseSessions.cursor === null ? nothing : this.button('moreSessions', busy, {type:'more-purchase-sessions'})}
      `}
      ${purchaseSession == null ? nothing : html`<section class="shopping" aria-labelledby="purchase-session-title">
        <h5 id="purchase-session-title" tabindex="-1">${this.text('sessionItems')} · ${this.sessionLabel(purchaseSession.session)}</h5>
        <ol>${purchaseSession.items.map(item => html`<li><strong>${item.name}</strong>${this.facts(item)}
          ${this.button('showReceipts', busy, {type:'purchase-receipts',purchaseId:item.id})}</li>`)}</ol>
      </section>`}
    </section>`;
  }

  protected render() {
    const {report, purchases, purchaseReceipts, busy, pending, scope} = this.view;
    const blocked = busy || pending || scope.readOnly;
    const mayShop = report!.mayShop && !scope.readOnly;
    const mayPost = report!.mayManage && !scope.readOnly;
    return html`<vyp-ha-card .state=${cardState({title:this.text('shopping'), headingLevel:3})}>
      <div class="shopping">
      <domus-shopping-list .view=${this.view} .language=${this.language}></domus-shopping-list>
      ${this.sessionHistory(busy)}
      ${purchases == null ? this.button('showPurchases', busy, {type:'purchases'}) : html`
        ${mayShop ? this.purchaseForm(report!.products, blocked) : nothing}
        ${purchases.items.length === 0 ? html`<p>${this.text('emptyPurchases')}</p>` : html`<ol>
          ${purchases.items.map(purchase => html`<li><strong>${purchase.name}</strong>${this.facts(purchase)}
            ${this.button('showReceipts', busy, {type:'purchase-receipts',purchaseId:purchase.id})}
          </li>`)}
        </ol>`}
        ${purchases.cursor === null ? nothing : this.button('olderPurchases', busy, {type:'more-purchases'})}
      `}
      ${purchaseReceipts == null ? nothing : this.detail(purchaseReceipts, mayShop, mayPost, blocked, busy)}
      </div>
    </vyp-ha-card>`;
  }
}

registerButton();
registerCard();
customElements.define('domus-shopping', DomusShopping);

declare global {
  interface HTMLElementTagNameMap {'domus-shopping': DomusShopping;}
}
