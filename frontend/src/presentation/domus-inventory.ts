import {LitElement, css, html, nothing} from 'lit';
import type {PropertyValues} from 'lit';
import {live} from 'lit/directives/live.js';
import {registerButton} from '@vypdev/ha-ui/button';
import {buttonState} from '@vypdev/ha-ui/button-contracts';
import {registerCard} from '@vypdev/ha-ui/card';
import {cardState} from '@vypdev/ha-ui/card-contracts';
import {registerFeedback} from '@vypdev/ha-ui/feedback';
import {feedbackState} from '@vypdev/ha-ui/feedback-contracts';
import type {InventoryError, InventoryState} from '../application/inventory-controller';
import {BASE_UNITS, intakeQuantity} from '../domain/inventory';
import type {BaseUnit, InventoryCommand, ProductStock} from '../domain/inventory';
import {taskText} from '../domain/tasks';
import {inventoryMessage} from './inventory-messages';
import type {InventoryMessage} from './inventory-messages';
import type {Language} from './messages';

export type InventoryIntent = {readonly type: 'refresh' | 'more' | 'recover'}
  | {readonly type: 'submit'; readonly command: InventoryCommand};

const QUANTITY_ERRORS = new Set<InventoryError>([
  'inventory_stock_capacity', 'invalid_inventory_receipt', 'invalid_material_quantity', 'invalid_material_precision',
]);

export class DomusInventory extends LitElement {
  static properties = {
    view: {attribute:false}, language: {attribute:false}, nameDraft: {state:true}, unit: {state:true},
    selected: {state:true}, amount: {state:true}, review: {state:true}, invalid: {state:true},
  };

  static styles = css`
    :host {display:grid;gap:16px;--vyp-ha-surface:var(--surface);--vyp-ha-text:var(--text);
      --vyp-ha-text-secondary:var(--muted);--vyp-ha-border:var(--line);--vyp-ha-primary:var(--accent)}
    h2, h3, p {margin:0} form, label, article, .products {display:grid;gap:8px}
    article + article {border-block-start:1px solid var(--line);padding-block-start:12px}
    article {overflow-wrap:anywhere}
    dl {display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px;margin:0}
    dt {font-weight:650} dd {margin:0}
    input,select {font:inherit;color:inherit;background:var(--surface);padding:8px;border:1px solid var(--line);
      border-radius:8px;min-width:0}
    .actions {display:flex;flex-wrap:wrap;gap:8px}
    a {color:var(--accent)} :focus-visible {outline:3px solid var(--accent);outline-offset:3px}
  `;

  declare view: InventoryState | null;
  declare language: Language;
  private declare nameDraft: string;
  private declare unit: BaseUnit;
  private declare selected: string | null;
  private declare amount: string;
  private declare review: string | null;
  private declare invalid: 'name' | 'quantity' | null;

  constructor() {
    super();
    this.view = null;
    this.language = 'en';
    this.nameDraft = '';
    this.unit = 'piece';
    this.selected = null;
    this.amount = '';
    this.review = null;
    this.invalid = null;
  }

  protected willUpdate(changed: PropertyValues<this>): void {
    if (!changed.has('view')) return;
    const previous = changed.get('view'), current = this.view;
    if (previous?.scope.key !== current?.scope.key) {
      this.nameDraft = '';
      this.unit = 'piece';
      this.select(null);
    }
    const result = current?.result;
    if (result && result !== previous?.result && result.kind !== 'rejected') {
      if (result.intake === null) this.nameDraft = '';
      else this.select(result.productId);
    }
  }

  private text(key: InventoryMessage): string {return inventoryMessage(key, this.language);}
  private quantity(value: string): string {return this.language === 'es' ? value.replace('.', ',') : value;}
  private intent(detail: InventoryIntent): void {
    this.dispatchEvent(new CustomEvent('domus-inventory-intent', {detail, bubbles:true, composed:true}));
  }
  private select(id: string | null): void {
    this.selected = id;
    this.amount = '';
    this.review = null;
    this.invalid = null;
  }

  private button(key: InventoryMessage, action: () => void, disabled: boolean) {
    return html`<vyp-ha-button .state=${buttonState({label:this.text(key), variant:'outlined'})}
      ?disabled=${disabled} @ha-press-request=${action}></vyp-ha-button>`;
  }

  private submitButton(key: InventoryMessage, disabled: boolean) {
    return html`<vyp-ha-button type="submit" .state=${buttonState({label:this.text(key), variant:'primary'})}
      ?disabled=${disabled}></vyp-ha-button>`;
  }

  private error(id: string, key: InventoryMessage) {
    return html`<p role="alert" id=${id}>${this.text(key)}</p>`;
  }

  private registration(blocked: boolean) {
    const invalid = this.invalid === 'name';
    return html`<vyp-ha-card .state=${cardState({title:this.text('register'), headingLevel:3})}>
      <form novalidate @submit=${(event: SubmitEvent) => {
        event.preventDefault();
        if (blocked) return;
        try {taskText(this.nameDraft, 160, true);} catch {this.invalid = 'name'; return;}
        this.intent({type:'submit', command:{action:'inventory.register-product', name:this.nameDraft, base_unit:this.unit}});
      }}>
        <label>${this.text('productName')}<input maxlength="160" required .value=${live(this.nameDraft)}
          aria-invalid=${invalid} aria-describedby=${invalid ? 'inventory-name-error' : nothing} ?disabled=${blocked}
          @input=${(event: InputEvent) => {this.nameDraft = (event.target as HTMLInputElement).value; this.invalid = null;}}></label>
        ${invalid ? this.error('inventory-name-error', 'invalidName') : nothing}
        <label>${this.text('unit')}<select .value=${live(this.unit)} ?disabled=${blocked} aria-describedby="inventory-unit-help"
          @change=${(event: Event) => {this.unit = (event.target as HTMLSelectElement).value as BaseUnit;}}>
          ${BASE_UNITS.map(unit => html`<option .value=${unit}>${this.text(unit)}</option>`)}
        </select></label>
        <p id="inventory-unit-help">${this.text('permanent')}</p>
        ${this.submitButton('register', blocked)}
      </form>
    </vyp-ha-card>`;
  }

  private intake(product: ProductStock, blocked: boolean) {
    const state = this.view!.result;
    const fieldError = this.review !== null && state?.kind === 'rejected' && QUANTITY_ERRORS.has(state.reason)
      ? state.reason : null;
    const invalid = this.invalid === 'quantity' || fieldError !== null;
    return html`<form novalidate @submit=${(event: SubmitEvent) => {
      event.preventDefault();
      if (blocked) return;
      const quantity = intakeQuantity(this.amount, product.unit);
      if (quantity === null) {this.invalid = 'quantity'; return;}
      if (this.review !== quantity) {this.review = quantity; return;}
      this.intent({type:'submit', command:{action:'inventory.intake', product_id:product.id, quantity}});
    }}>
      <label>${this.text('quantity')}<input inputmode=${product.unit === 'piece' ? 'numeric' : 'decimal'} maxlength="19"
        required aria-invalid=${invalid} aria-describedby=${invalid ? 'inventory-quantity-help inventory-quantity-error' : 'inventory-quantity-help'}
        .value=${live(this.amount)} ?disabled=${blocked} @input=${(event: InputEvent) => {
          this.amount = (event.target as HTMLInputElement).value;
          this.invalid = null;
          this.review = null;
        }}></label>
      <p id="inventory-quantity-help">${this.text(product.unit === 'piece' ? 'pieceGuide' : 'decimalGuide')}</p>
      ${invalid ? this.error('inventory-quantity-error', fieldError ?? 'invalidQuantity') : nothing}
      ${this.review === null ? nothing : html`<p role="status">${product.name} · ${this.quantity(this.review)} ${this.text(product.unit)}.
        ${this.text('reviewBody')}</p>`}
      ${this.submitButton(this.review === null ? 'review' : 'confirm', blocked)}
    </form>`;
  }

  private product(product: ProductStock, manage: boolean, blocked: boolean) {
    return html`<article tabindex="-1" id=${'product-' + product.id} aria-labelledby=${'name-' + product.id}>
      <h3 id=${'name-' + product.id}>${product.name}</h3>
      <p>${this.text('unit')} · ${this.text(product.unit)}</p>
      <dl>${(['recorded', 'reserved', 'available'] as const).map(key => html`
        <dt>${this.text(key)}</dt><dd>${this.quantity(product[key])}</dd>`)}</dl>
      ${!manage ? nothing : this.selected === product.id ? this.intake(product, blocked)
        : this.button('intake', () => this.select(product.id), blocked)}
    </article>`;
  }

  protected render() {
    const view = this.view;
    if (view === null) return nothing;
    const {report, result, busy, notice, pending} = view;
    const blocked = view.scope.readOnly || busy || pending;
    const manage = report?.mayManage === true && !view.scope.readOnly;
    const saved = result !== null && result.kind !== 'rejected' ? result : null;
    const message = result?.kind === 'rejected' ? result.reason : notice;
    return html`<h2>${this.text('title')}</h2>
      ${message === null ? nothing : html`<vyp-ha-feedback
        .state=${feedbackState({kind:'notice', tone:'warning', message:this.text(message)})}></vyp-ha-feedback>`}
      ${saved === null ? nothing : html`<p role="status">${this.text(saved.kind === 'historical'
        ? 'historical' : saved.intake === null ? 'registered' : 'added')}
        ${saved.intake === null ? nothing : html`${this.quantity(saved.intake.quantity)} ${this.text(saved.intake.unit)}`}</p>
        ${report?.products.some(product => product.id === saved.productId) ? html`<a href=${'#product-' + saved.productId}
          @click=${(event: MouseEvent) => {
            event.preventDefault();
            this.renderRoot.querySelector<HTMLElement>('article[id="product-' + saved.productId + '"]')?.focus();
          }}>${this.text('viewProduct')}</a>` : nothing}
        <details><summary>${this.text('receipt')}</summary>
          <p>${this.text('operation')} <code>${saved.operationId}</code></p>
          ${saved.intake === null ? nothing : html`<p>${this.text('movement')} <code>${saved.intake.movementId}</code></p>`}
        </details>`}
      <div class="actions">${this.button('refresh', () => this.intent({type:'refresh'}), busy)}
        ${pending ? this.button('recover', () => this.intent({type:'recover'}), busy) : nothing}</div>
      ${busy && report === null ? html`<p role="status">${this.text('loading')}</p>` : nothing}
      ${report === null ? nothing : html`
        ${manage ? this.registration(blocked) : nothing}
        <vyp-ha-card .state=${cardState({title:this.text('pantry'), headingLevel:3})}>
          ${report.products.length === 0 ? html`<p>${this.text('empty')}</p>`
            : html`<div class="products">${report.products.map(product => this.product(product, manage, blocked))}</div>`}
          ${report.cursor === null ? nothing : this.button('more', () => this.intent({type:'more'}), busy)}
        </vyp-ha-card>`}
    `;
  }
}

registerButton();
registerCard();
registerFeedback();
customElements.define('domus-inventory', DomusInventory);

declare global {
  interface HTMLElementTagNameMap {'domus-inventory': DomusInventory;}
}
