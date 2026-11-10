import {LitElement, css, html, nothing} from 'lit';
import type {PropertyValues} from 'lit';
import {repeat} from 'lit/directives/repeat.js';
import {registerButton} from '@vypdev/ha-ui/button';
import {buttonState} from '@vypdev/ha-ui/button-contracts';
import type {InventoryState} from '../application/inventory-controller';
import {MAX_SESSION_ITEMS, MIN_SESSION_ITEMS, intakeQuantity} from '../domain/inventory';
import type {BaseUnit, ExtraAttribution, InventoryCommand, SessionSelection, ShoppingItem, ShoppingSource} from '../domain/inventory';
import {taskText} from '../domain/tasks';
import {inventoryMessage} from './inventory-messages';
import type {InventoryMessage} from './inventory-messages';
import {instant} from './messages';
import type {Language} from './messages';

export type ShoppingListIntent = {readonly type: 'shopping-list' | 'more-shopping-list' | 'more-shopping-sources'}
  | {readonly type: 'shopping-sources'; readonly productId: string}
  | {readonly type: 'submit'; readonly command: InventoryCommand};

const SOURCE_LABELS = {pantry:'pantrySource', task:'taskSource', extra:'manualSource'} as const;

interface SessionDraft {
  readonly key: string;
  readonly item: ShoppingItem;
  readonly quantity: string;
}

function itemKey(item: ShoppingItem): string {
  return item.productId === null ? 'extra:' + item.extraId : 'product:' + item.productId;
}

export class DomusShoppingList extends LitElement {
  static properties = {view:{attribute:false}, language:{attribute:false}, selected:{state:true}, error:{state:true},
    sessionDraft:{state:true}, sessionError:{state:true}};

  static styles = css`
    section, form, label, li {display:grid;gap:8px}
    ol {display:grid;gap:12px;margin:0;padding:0;list-style:none}
    li + li {padding-block-start:8px;border-block-start:1px solid var(--line)}
    h4, h5, p, dl, dd {margin:0}
    dl {display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px}
    dt {font-weight:650}
    input,select {font:inherit;color:inherit;background:var(--surface);padding:8px;border:1px solid var(--line);
      border-radius:8px;min-width:0}
    li {overflow-wrap:anywhere}
    :focus-visible {outline:3px solid var(--accent);outline-offset:3px}
  `;

  declare view: InventoryState;
  declare language: Language;
  private declare selected: string;
  private declare error: 'invalidName' | 'invalidQuantity' | null;
  private declare sessionDraft: readonly SessionDraft[];
  private declare sessionError: string | null;

  constructor() {
    super();
    this.selected = '';
    this.error = null;
    this.sessionDraft = [];
    this.sessionError = null;
  }

  protected updated(changed: PropertyValues<this>): void {
    if (!changed.has('view')) return;
    const previous = changed.get('view'), {result, shoppingSources} = this.view;
    if (shoppingSources && shoppingSources.item.productId !== previous?.shoppingSources?.item.productId)
      this.renderRoot.querySelector<HTMLElement>('#shopping-sources-title')?.focus();
    if (result?.kind === 'committed' && result.shoppingAction === 'shopping.record-session' && result !== previous?.result) {
      this.sessionDraft = [];
      this.sessionError = null;
    }
    if (result?.kind === 'committed' && result.shoppingAction === 'shopping.add-extra' && result !== previous?.result) {
      this.selected = '';
      this.error = null;
      this.renderRoot.querySelector<HTMLFormElement>('#shopping-extra-form')?.reset();
    }
  }

  private text(key: InventoryMessage): string {return inventoryMessage(key, this.language);}

  private amount(quantity: string, unit: BaseUnit): string {
    return (this.language === 'es' ? quantity.replace('.', ',') : quantity) + ' ' + this.text(unit);
  }

  private intent(detail: ShoppingListIntent): void {
    this.dispatchEvent(new CustomEvent('domus-inventory-intent', {detail, bubbles:true, composed:true}));
  }

  private button(key: InventoryMessage, blocked: boolean, detail?: ShoppingListIntent | (() => void)) {
    return html`<vyp-ha-button type=${detail ? 'button' : 'submit'}
      .state=${buttonState({label:this.text(key), variant:detail ? 'outlined' : 'primary'})} ?disabled=${blocked}
      @ha-press-request=${typeof detail === 'function' ? detail : detail ? () => this.intent(detail) : nothing}></vyp-ha-button>`;
  }

  private extraForm(blocked: boolean) {
    const products = this.view.report!.products;
    const product = products.find(item => item.id === this.selected);
    const unit = product?.unit ?? 'piece';
    const error = this.error;
    return html`<form id="shopping-extra-form" novalidate @submit=${(event: SubmitEvent) => {
      event.preventDefault();
      if (blocked) return;
      const fields = new FormData(event.currentTarget as HTMLFormElement);
      const quantity = intakeQuantity(String(fields.get('quantity')), unit);
      if (quantity === null) {this.error = 'invalidQuantity'; return;}
      let name: string | null = null;
      if (product === undefined) {
        try {name = taskText(fields.get('name'), 160, true);}
        catch {this.error = 'invalidName'; return;}
      }
      this.error = null;
      this.intent({type:'submit', command:{action:'shopping.add-extra', product_id:product?.id ?? null, name, quantity}});
    }}>
      <label>${this.text('extraItem')}<select .value=${this.selected} ?disabled=${blocked}
        @change=${(event: Event) => {this.selected = (event.target as HTMLSelectElement).value; this.error = null;}}>
        <option value="">${this.text('freeItem')}</option>
        ${products.map(item => html`<option value=${item.id}>${item.name}</option>`)}
      </select></label>
      ${product === undefined ? html`<label>${this.text('extraName')}<input name="name" maxlength="160" ?disabled=${blocked}
        aria-invalid=${error === 'invalidName'} aria-describedby="shopping-extra-error"></label>` : nothing}
      <label>${this.text('extraQuantity')} · ${this.text(unit)}
        <input name="quantity" inputmode="decimal" maxlength="20" ?disabled=${blocked}
          aria-invalid=${error === 'invalidQuantity'} aria-describedby="shopping-extra-error">
      </label>
      <span id="shopping-extra-error" role="alert">${error === null ? nothing : this.text(error)}</span>
      ${this.button('addExtra', blocked)}
    </form>`;
  }

  private canSelect(key: string): boolean {
    return this.sessionDraft.length < MAX_SESSION_ITEMS && this.sessionDraft.every(draft => draft.key !== key);
  }

  private addToSession(item: ShoppingItem): void {
    const key = itemKey(item);
    if (!this.canSelect(key)) return;
    this.sessionDraft = [...this.sessionDraft, {key,item,quantity:item.total}];
  }

  private submitSession(event: SubmitEvent, blocked: boolean): void {
    event.preventDefault();
    if (blocked || this.sessionDraft.length < MIN_SESSION_ITEMS) return;
    const items: SessionSelection[] = [];
    for (const {key, item, quantity: entered} of this.sessionDraft) {
      const quantity = intakeQuantity(entered, item.unit);
      if (quantity === null) {this.sessionError = key; return;}
      items.push({product_id:item.productId, extra_id:item.extraId, quantity});
    }
    this.sessionError = null;
    this.intent({type:'submit',command:{action:'shopping.record-session',items}});
  }

  private sessionForm(blocked: boolean) {
    return html`<form id="purchase-session-form" aria-labelledby="purchase-session-form-title" novalidate
      @submit=${(event: SubmitEvent) => this.submitSession(event, blocked)}>
      <h5 id="purchase-session-form-title">${this.text('recordSession')}</h5>
      <p>${this.text('sessionItemLimit')}</p>
      ${repeat(this.sessionDraft, draft => draft.key, ({key,item,quantity}) => html`<div>
        <label>${item.name} · ${this.text(item.unit)}<input name="quantity" inputmode="decimal"
          .value=${quantity} ?disabled=${blocked} maxlength="20" aria-invalid=${this.sessionError === key}
          aria-describedby="purchase-session-error" @input=${(event: Event) => {
            const value = (event.target as HTMLInputElement).value;
            this.sessionDraft = this.sessionDraft.map(draft => draft.key === key ? {...draft,quantity:value} : draft);
          }}></label>
        ${this.button('removeFromSession', blocked, () => {
          this.sessionDraft = this.sessionDraft.filter(draft => draft.key !== key);
          this.sessionError = null;
        })}
      </div>`)}
      <span id="purchase-session-error" role="alert">${this.sessionError === null ? nothing : this.text('invalidQuantity')}</span>
      ${this.button('saveSession', blocked || this.sessionDraft.length < MIN_SESSION_ITEMS)}
    </form>`;
  }

  private author(value: ExtraAttribution | null) {
    if (value === null) return nothing;
    return html`<p>${value.authorAlias ?? value.memberId} · ${instant(Number(value.createdAt), this.language)}</p>`;
  }

  private clearButton(extraId: string, blocked: boolean) {
    return this.button('clearExtra', blocked, {type:'submit',command:{action:'shopping.clear-extra',extra_id:extraId}});
  }

  private item(item: ShoppingItem, mayClear: boolean, blocked: boolean) {
    const amount = (value: string) => this.amount(value, item.unit);
    return html`<li>
      <strong>${item.name}</strong>
      <dl>
        <dt>${this.text('toBuy')}</dt><dd>${amount(item.total)}</dd>
        <dt>${this.text('pantrySource')}</dt><dd>${amount(item.pantry)}</dd>
        <dt>${this.text('taskSource')}</dt><dd>${amount(item.tasks)}</dd>
        <dt>${this.text('manualSource')}</dt><dd>${amount(item.manual)}</dd>
      </dl>
      ${this.author(item.attribution)}
      ${mayClear ? this.button('addToSession', blocked || !this.canSelect(itemKey(item)), () => this.addToSession(item)) : nothing}
      ${item.productId !== null
        ? this.button('showSources', this.view.busy, {type:'shopping-sources', productId:item.productId})
        : mayClear ? this.clearButton(item.extraId!, blocked) : nothing}
    </li>`;
  }

  private source(source: ShoppingSource, unit: BaseUnit, mayClear: boolean, blocked: boolean) {
    const amount = (value: string) => this.amount(value, unit);
    return html`<li>
      <strong>${this.text(SOURCE_LABELS[source.kind])} · ${source.name}</strong>
      <dl>
        <dt>${this.text('quantity')}</dt><dd>${amount(source.quantity)}</dd>
        <dt>${this.text('reserved')}</dt><dd>${amount(source.reserved)}</dd>
        <dt>${this.text('fromStock')}</dt><dd>${amount(source.stock)}</dd>
        <dt>${this.text('fromIncoming')}</dt><dd>${amount(source.incoming)}</dd>
        <dt>${this.text('toBuy')}</dt><dd>${amount(source.toBuy)}</dd>
      </dl>
      ${this.author(source.attribution)}
      ${mayClear && source.kind === 'extra' ? this.clearButton(source.originId, blocked) : nothing}
    </li>`;
  }

  protected render() {
    const {report, shoppingList, shoppingSources, busy, pending, scope} = this.view;
    const blocked = busy || pending || scope.readOnly;
    const mayClear = report!.mayShop && !scope.readOnly;
    return html`<section aria-labelledby="shopping-list-title">
      <h4 id="shopping-list-title">${this.text('sharedShoppingList')}</h4>
      ${shoppingList == null ? this.button('showShoppingList', busy, {type:'shopping-list'}) : html`
        ${report!.mayRequest && !scope.readOnly ? this.extraForm(blocked) : nothing}
        ${shoppingList.items.length === 0 ? html`<p>${this.text('emptyShoppingList')}</p>`
          : html`<ol>${shoppingList.items.map(item => this.item(item, mayClear, blocked))}</ol>`}
        ${shoppingList.cursor === null ? nothing : this.button('moreShoppingList', busy, {type:'more-shopping-list'})}
        ${mayClear && this.sessionDraft.length > 0 ? this.sessionForm(blocked) : nothing}
        ${shoppingSources == null ? nothing : html`<section aria-labelledby="shopping-sources-title">
          <h5 id="shopping-sources-title" tabindex="-1">${this.text('showSources')} · ${shoppingSources.item.name}</h5>
          ${shoppingSources.items.length === 0 ? html`<p>${this.text('emptySources')}</p>`
            : html`<ol>${shoppingSources.items.map(source => this.source(source, shoppingSources.item.unit, mayClear, blocked))}</ol>`}
          ${shoppingSources.cursor === null ? nothing : this.button('moreSources', busy, {type:'more-shopping-sources'})}
        </section>`}
      `}
    </section>`;
  }
}

registerButton();
customElements.define('domus-shopping-list', DomusShoppingList);

declare global {
  interface HTMLElementTagNameMap {'domus-shopping-list': DomusShoppingList;}
}
