import {LitElement, css, html, nothing} from 'lit';
import type {PropertyValues} from 'lit';
import {live} from 'lit/directives/live.js';
import {registerButton} from '@vypdev/ha-ui/button';
import {buttonState} from '@vypdev/ha-ui/button-contracts';
import {registerCard} from '@vypdev/ha-ui/card';
import {cardState} from '@vypdev/ha-ui/card-contracts';
import {registerField} from '@vypdev/ha-ui/field';
import type {FieldValueEvent} from '@vypdev/ha-ui/field';
import {textFieldState} from '@vypdev/ha-ui/field-contracts';
import {registerSelect} from '@vypdev/ha-ui/select';
import type {SelectValueEvent} from '@vypdev/ha-ui/select';
import {selectState} from '@vypdev/ha-ui/select-contracts';
import {registerFeedback} from '@vypdev/ha-ui/feedback';
import {feedbackState} from '@vypdev/ha-ui/feedback-contracts';
import type {InventoryError, InventoryState} from '../application/inventory-controller';
import {BASE_UNITS, MAX_LOCATION_NAME, STOCK_REASON_LIMIT, adjustmentQuantity, intakeQuantity, locationName, policyQuantity, stockUnits} from '../domain/inventory';
import type {BaseUnit, MovementHistory, ProductStock, ReplenishmentRevision, StockMovement, StockTotals, StorageLocation} from '../domain/inventory';
import {taskText} from '../domain/tasks';
import {inventoryMessage} from './inventory-messages';
import type {InventoryMessage} from './inventory-messages';
import './domus-shopping';
import type {ShoppingIntent} from './domus-shopping';
import type {ShoppingListIntent} from './domus-shopping-list';
import {instant} from './messages';
import type {Language} from './messages';

export type InventoryIntent = {readonly type: 'refresh' | 'more' | 'recover' | 'more-history' | 'close-history'}
  | {readonly type: 'history'; readonly productId: string}
  | ShoppingIntent | ShoppingListIntent;

const QUANTITY_ERRORS = new Set<InventoryError>([
  'inventory_stock_capacity', 'invalid_inventory_receipt', 'invalid_material_quantity', 'invalid_material_precision',
]);

const MOVEMENT_SAVED = {
  'inventory.intake': 'added',
  'inventory.adjust': 'adjusted',
  'inventory.correct-intake': 'reversed',
  'inventory.transfer': 'moved',
} as const;

const SHOPPING_SAVED = {
  'shopping.purchase': 'purchaseSaved',
  'shopping.receive': 'arrivalSaved',
  'shopping.cancel-balance': 'cancelSaved',
  'shopping.void-receipt': 'voidSaved',
  'shopping.correct-posted-receipt': 'postedCorrectionSaved',
  'shopping.return-receipt': 'returnSaved',
  'shopping.post-receipt': 'stockPosted',
  'shopping.add-extra': 'extraAdded',
  'shopping.clear-extra': 'extraCleared',
  'shopping.record-session': 'sessionSaved',
} as const;

interface TransferDraft {
  readonly productId: string;
  readonly source: string | null;
  readonly destination: string | null;
  readonly amount: string;
  readonly reviewed: boolean;
  readonly error: 'selectLocation' | 'invalidQuantity' | 'insufficientTransfer' | null;
}

interface PolicyEditor {
  readonly productId: string;
  readonly revision: ReplenishmentRevision;
  readonly minimum: string;
  readonly target: string;
  readonly error: 'invalidQuantity' | 'invalid_replenishment_bounds' | null;
}

export class DomusInventory extends LitElement {
  static properties = {
    view: {attribute:false}, language: {attribute:false}, nameDraft: {state:true}, unit: {state:true},
    selected: {state:true}, amount: {state:true}, review: {state:true}, invalid: {state:true},
    editor: {state:true}, reason: {state:true}, adjustment: {state:true},
    policyEditor: {state:true}, locationDraft: {state:true}, locationInvalid: {state:true}, transferDraft: {state:true},
  };

  static styles = css`
    :host {display:grid;gap:16px;--vyp-ha-surface:var(--surface);--vyp-ha-surface-raised:var(--surface);
      --vyp-ha-text:var(--text);--vyp-ha-text-secondary:var(--muted);--vyp-ha-border:var(--line);
      --vyp-ha-primary:var(--accent);--vyp-ha-on-accent:var(--surface);--vyp-ha-focus-ring:3px solid var(--accent)}
    h2, h3, p {margin:0} form, label, article, .products {display:grid;gap:8px}
    article + article {border-block-start:1px solid var(--line);padding-block-start:12px}
    article {scroll-margin-block-start:68px} article,code {overflow-wrap:anywhere}
    dl {display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px;margin:0}
    dt {font-weight:650} dd {margin:0}
    input,select {font:inherit;color:inherit;background:var(--surface);padding:8px;border:1px solid var(--line);
      border-radius:8px;min-width:0}
    .actions {display:flex;flex-wrap:wrap;gap:8px}
    ol {padding:0;margin:0;list-style:none;display:grid;gap:12px}
    li {overflow-wrap:anywhere;border-block-start:1px solid var(--line);padding-block-start:12px}
    .history {scroll-margin-block-start:68px}
    .history-content, .location-content, .location-balances {display:grid;gap:12px}
    .location-balances {grid-template-columns:repeat(auto-fit,minmax(min(100%,170px),1fr))}
    .location-stock {border:1px solid var(--line);border-radius:8px;padding:12px;overflow-wrap:anywhere}
    .location-stock h5 {font-size:inherit;margin:0 0 8px}
    .location-content ul {margin:0;padding-inline-start:20px}
    .location-content li {border:none;padding:0}
    a {color:var(--accent)} :focus-visible {outline:3px solid var(--accent);outline-offset:3px}
  `;

  declare view: InventoryState | null;
  declare language: Language;
  private declare nameDraft: string;
  private declare unit: BaseUnit;
  private declare selected: string | null;
  private declare amount: string;
  private declare review: string | null;
  private declare invalid: 'name' | 'quantity' | 'adjustment' | 'reason' | null;
  private declare editor: {productId: string; original: StockMovement | null} | null;
  private declare reason: string;
  private declare adjustment: string;
  private declare policyEditor: PolicyEditor | null;
  private declare locationDraft: string;
  private declare locationInvalid: boolean;
  private declare transferDraft: TransferDraft | null;

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
    this.editor = null;
    this.reason = '';
    this.adjustment = '';
    this.policyEditor = null;
    this.locationDraft = "";
    this.locationInvalid = false;
    this.transferDraft = null;
  }

  protected willUpdate(changed: PropertyValues<this>): void {
    if (!changed.has('view')) return;
    const previous = changed.get('view'), current = this.view;
    if (previous?.scope.key !== current?.scope.key) {
      this.nameDraft = '';
      this.unit = 'piece';
      this.select(null);
      this.editor = null;
      this.policyEditor = null;
      this.locationDraft = "";
      this.locationInvalid = false;
      this.transferDraft = null;
    }
    if (previous?.history?.productId !== current?.history?.productId) {
      this.editor = null;
      if (current?.history && current.history.productId !== this.transferDraft?.productId) this.transferDraft = null;
    }
    const result = current?.result;
    if (result && result !== previous?.result) {
      if (result.kind === 'rejected') {
        if (result.command.action === 'inventory.configure-replenishment' && result.reason === 'revision_conflict')
          this.policyEditor = null;
      } else if (result.locationSaved) this.locationDraft = '';
      else if (result.replenishmentSaved) this.policyEditor = null;
      else if (result.movement === null) {
        if (!result.shoppingAction) this.nameDraft = '';
      }
      else if (result.movement.action === 'inventory.intake') this.select(result.productId);
      else if (result.movement.action === 'inventory.transfer') this.transferDraft = null;
      else this.editor = null;
    }
  }

  protected updated(changed: PropertyValues<this>): void {
    if (!changed.has('view')) return;
    const product = this.view?.history?.productId;
    if (product && product !== changed.get('view')?.history?.productId)
      this.renderRoot.querySelector<HTMLElement>('.history')?.focus();
    const result = this.view?.result;
    if (result && result !== changed.get('view')?.result && result.kind !== 'rejected') {
      if (result.locationSaved) this.renderRoot.querySelector<HTMLFormElement>('.location-content form')?.reset();
      if (result.movement?.action === 'inventory.transfer')
        this.renderRoot.querySelector<HTMLElement>('.history')?.focus();
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
    const fieldError = state?.kind === 'rejected' && state.command.action === 'inventory.intake'
      && state.command.product_id === product.id && state.command.quantity === this.review
      && QUANTITY_ERRORS.has(state.reason) ? state.reason : null;
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

  private signed(value: string): string {
    return (value.startsWith('-') ? '' : '+') + this.quantity(value);
  }

  private editStock(productId: string, original: StockMovement | null): void {
    this.editor = {productId, original};
    this.reason = '';
    this.adjustment = '';
    this.invalid = null;
    void this.updateComplete.then(() => this.renderRoot.querySelector<HTMLInputElement>('.history form input')?.focus());
  }

  private stockForm(history: MovementHistory, editor: NonNullable<DomusInventory['editor']>, blocked: boolean) {
    const original = editor.original;
    return html`<form novalidate @submit=${(event: SubmitEvent) => {
      event.preventDefault();
      if (blocked) return;
      try {taskText(this.reason, STOCK_REASON_LIMIT, true);} catch {this.invalid = 'reason'; return;}
      if (original !== null) {
        this.intent({type:'submit', command:{action:'inventory.correct-intake', product_id:history.productId,
          movement_id:original.id, reason:this.reason}});
        return;
      }
      const quantity = adjustmentQuantity(this.adjustment, history.unit);
      if (quantity === null) {this.invalid = 'adjustment'; return;}
      this.intent({type:'submit', command:{action:'inventory.adjust', product_id:history.productId,
        quantity, reason:this.reason}});
    }}>
      ${original === null ? html`
        <label>${this.text('adjustmentQuantity')}<input required maxlength="20" .value=${live(this.adjustment)}
          aria-invalid=${this.invalid === 'adjustment'} aria-describedby="stock-adjustment-help"
          ?disabled=${blocked} @input=${(event: InputEvent) => {
            this.adjustment = (event.target as HTMLInputElement).value; this.invalid = null;
          }}></label>
        <p id="stock-adjustment-help">${this.text('adjustmentGuide')}</p>
        ${this.invalid === 'adjustment' ? this.error('stock-adjustment-error', 'invalidQuantity') : nothing}
      ` : html`<p>${this.text('reversalGuide')} −${this.quantity(original.quantity)} ${this.text(history.unit)}.
        <code>${original.id}</code></p>`}
      <label>${this.text('reason')}<input required maxlength=${STOCK_REASON_LIMIT} .value=${live(this.reason)}
        aria-invalid=${this.invalid === 'reason'} ?disabled=${blocked} @input=${(event: InputEvent) => {
          this.reason = (event.target as HTMLInputElement).value; this.invalid = null;
        }}></label>
      ${this.invalid === 'reason' ? this.error('stock-reason-error', 'invalid_inventory_reason') : nothing}
      <div class="actions">${this.submitButton(original === null ? 'saveAdjustment' : 'confirmReversal', blocked)}
        ${this.button('cancel', () => {this.editor = null;}, blocked)}</div>
    </form>`;
  }

  private locations(locations: readonly StorageLocation[], manage: boolean, blocked: boolean) {
    return html`<vyp-ha-card .state=${cardState({title:this.text('locations'), headingLevel:3})}>
      <div class="location-content">
        <ul><li>${this.text('pantry')}</li>${locations.map(item => html`<li>${item.name}</li>`)}</ul>
        ${manage ? html`<form novalidate @submit=${(event: SubmitEvent) => {
          event.preventDefault();
          if (blocked) return;
          let name: string;
          try {name = locationName(this.locationDraft.trim());}
          catch {
            this.locationInvalid = true;
            this.renderRoot.querySelector<HTMLElement>('.location-content vyp-ha-field')?.focus();
            return;
          }
          this.intent({type:'submit', command:{action:'inventory.add-location', name}});
        }}>
          <vyp-ha-field .value=${this.locationDraft} ?disabled=${blocked}
            .state=${textFieldState({label:this.text('locationName'), required:true, maxLength:MAX_LOCATION_NAME,
              error:this.locationInvalid ? this.text('invalid_inventory_location_name') : ''})}
            @ha-value-request=${(event: FieldValueEvent) => {
              this.locationDraft = event.detail.value;
              this.locationInvalid = false;
            }}></vyp-ha-field>
          ${this.submitButton('addLocation', blocked)}
        </form>` : nothing}
      </div>
    </vyp-ha-card>`;
  }

  private beginTransfer(productId: string): void {
    if (this.transferDraft?.productId !== productId)
      this.transferDraft = {productId, source:'pantry', destination:null, amount:'', reviewed:false, error:null};
    if (this.view?.history?.productId !== productId) this.intent({type:'history', productId});
    else void this.updateComplete.then(() => this.renderRoot.querySelector<HTMLElement>('.history')?.focus());
  }

  private changeTransfer(draft: TransferDraft, patch: Partial<TransferDraft>): void {
    this.transferDraft = {...draft, ...patch, reviewed:false, error:null};
  }

  private transferForm(history: MovementHistory, draft: TransferDraft, blocked: boolean) {
    const origin = history.locations.find(item => item.id === draft.source);
    const destination = history.locations.find(item => item.id === draft.destination);
    const options = history.locations.map(item => ({value:item.id, label:item.name ?? this.text('pantry'), disabled:false}));
    return html`<form class="transfer-form" aria-label=${this.text('moveStock')} novalidate @submit=${(event: SubmitEvent) => {
      event.preventDefault();
      if (blocked) return;
      if (!origin || !destination) {this.transferDraft = {...draft, error:'selectLocation'}; return;}
      const quantity = intakeQuantity(draft.amount, history.unit);
      if (quantity === null) {this.transferDraft = {...draft, error:'invalidQuantity'}; return;}
      if (stockUnits(quantity) > stockUnits(origin.stock.available)) {
        this.transferDraft = {...draft, error:'insufficientTransfer', reviewed:false};
        return;
      }
      if (!draft.reviewed) {this.transferDraft = {...draft, reviewed:true, error:null}; return;}
      this.intent({type:'submit', command:{action:'inventory.transfer', product_id:history.productId,
        source_location:origin.id, destination_location:destination.id, quantity}});
    }}>
      <vyp-ha-select .value=${draft.source} ?disabled=${blocked}
        .state=${selectState({label:this.text('sourceLocation'), options, required:true, clearable:false,
          placeholder:this.text('selectLocation'), requiredMessage:this.text('selectLocation')})}
        @ha-select-request=${(event: SelectValueEvent) => {
          const source = event.detail.value as string | null;
          this.changeTransfer(draft, {source, destination:source === draft.destination ? null : draft.destination});
        }}></vyp-ha-select>
      <vyp-ha-select .value=${draft.destination} ?disabled=${blocked}
        .state=${selectState({label:this.text('destinationLocation'), required:true, clearable:false,
          placeholder:this.text('selectLocation'), requiredMessage:this.text('selectLocation'),
          options:options.map(item => ({...item, disabled:item.value === draft.source}))})}
        @ha-select-request=${(event: SelectValueEvent) =>
          this.changeTransfer(draft, {destination:event.detail.value as string | null})}></vyp-ha-select>
      ${origin ? html`<p>${this.text('available')} · ${this.quantity(origin.stock.available)} ${this.text(history.unit)}</p>` : nothing}
      <vyp-ha-field .value=${draft.amount} ?disabled=${blocked}
        .state=${textFieldState({label:this.text('transferQuantity'), required:true, maxLength:19,
          description:this.text(history.unit === 'piece' ? 'wholeTransfer' : 'decimalTransfer')})}
        @ha-value-request=${(event: FieldValueEvent) => this.changeTransfer(draft, {amount:event.detail.value})}></vyp-ha-field>
      ${draft.error ? this.error('transfer-error', draft.error) : nothing}
      ${draft.reviewed && origin && destination ? html`<p role="status">${history.productName} · ${draft.amount}
        ${this.text(history.unit)} · ${origin.name ?? this.text('pantry')} → ${destination.name ?? this.text('pantry')}</p>` : nothing}
      <div class="actions">${this.submitButton(draft.reviewed ? 'confirmTransfer' : 'reviewTransfer', blocked)}
        ${this.button('cancel', () => {
          this.transferDraft = null;
          void this.updateComplete.then(() => this.renderRoot.querySelector<HTMLElement>('.history')?.focus());
        }, blocked)}</div>
    </form>`;
  }

  private balances(history: MovementHistory) {
    const stock = (name: string, totals: StockTotals) => html`<div class="location-stock">
      <h5>${name}</h5><dl>${(['recorded','reserved','available'] as const).map(key => html`
        <dt>${this.text(key)}</dt><dd>${this.quantity(totals[key])} ${this.text(history.unit)}</dd>`)}</dl>
    </div>`;
    return html`<h4>${this.text('stockByLocation')}</h4>
      <div class="location-balances">
        ${stock(this.text('householdTotal'), history.total)}
        ${history.locations.map(item => stock(item.name ?? this.text('pantry'), item.stock))}
      </div>`;
  }

  private historyRow(entry: StockMovement, history: MovementHistory, manage: boolean, blocked: boolean) {
    const linked = entry.transfer;
    const name = (id: string) => history.locations.find(item => item.id === id)?.name ?? this.text('pantry');
    return html`<li>
      <p><strong>${this.signed(entry.quantity)} ${this.text(history.unit)}</strong> · ${this.text(entry.returnOf !== null ? 'returnMovement' : entry.kind === 'intake' ? 'intakeMovement' : entry.kind)}</p>
      ${linked === null ? nothing : html`<p>${name(linked.source)} → ${name(linked.destination)}</p>`}
      <dl>
        <dt>${this.text('author')}</dt><dd>${entry.authorAlias ?? entry.memberId}</dd>
        <dt>${this.text('date')}</dt><dd>${instant(Number(entry.createdAt), this.language)}</dd>
        ${entry.reason === null ? nothing : html`<dt>${this.text('reason')}</dt><dd>${entry.reason}</dd>`}
      </dl>
      <details><summary>${this.text('movementDetails')}</summary>
        <p>${this.text('movement')} <code>${entry.id}</code></p>
        ${linked === null ? nothing : html`<p>${this.text('linkedMovement')}
          <code>${entry.id === linked.withdrawalId ? linked.depositId : linked.withdrawalId}</code></p>`}
        ${entry.returnOf === null ? nothing : html`<p>${this.text('originalMovement')} <code>${entry.returnOf}</code></p>`}
        ${entry.corrects === null ? nothing : html`<p>${this.text('originalMovement')} <code>${entry.corrects}</code></p>`}
        ${entry.correctedBy === null ? nothing : html`<p>${this.text('correctedBy')} <code>${entry.correctedBy}</code></p>`}
        ${entry.occurrenceId === null ? nothing : html`<p>${this.text('taskOccurrence')} <code>${entry.occurrenceId}</code></p>`}
      </details>
      ${manage && entry.kind === 'intake' && entry.correctedBy === null
        ? entry.shoppingReceipt ? html`<p>${this.text('correctReceiptInShopping')}</p>`
          : this.button('reverseIntake', () => this.editStock(history.productId, entry), blocked) : nothing}
    </li>`;
  }

  private history(history: MovementHistory, manage: boolean, busy: boolean, blocked: boolean) {
    const editor = this.editor, transfer = this.transferDraft;
    return html`<section class="history" tabindex="-1" aria-label=${this.text('history') + ' · ' + history.productName}>
      <vyp-ha-card .state=${cardState({title:this.text('history'), headingLevel:3})}><div class="history-content">
        <h4>${history.productName}</h4>
        ${manage && transfer?.productId === history.productId ? this.transferForm(history, transfer, blocked) : nothing}
        <div class="actions">
          ${manage && history.locations.length > 1 && transfer === null
            ? this.button('moveStock', () => this.beginTransfer(history.productId), blocked) : nothing}
          ${manage ? this.button('adjust', () => this.editStock(history.productId, null), blocked) : nothing}
          ${this.button('closeHistory', () => {this.transferDraft = null; this.intent({type:'close-history'});}, busy)}
        </div>
        ${this.balances(history)}
        ${manage && editor?.productId === history.productId ? this.stockForm(history, editor, blocked) : nothing}
        ${history.movements.length === 0 ? html`<p>${this.text('emptyHistory')}</p>`
          : html`<ol>${history.movements.map(entry => this.historyRow(entry, history, manage, blocked))}</ol>`}
        ${history.cursor === null ? nothing : this.button('moreHistory', () => this.intent({type:'more-history'}), busy)}
      </div></vyp-ha-card>
    </section>`;
  }

  private editPolicy(product: ProductStock): void {
    const {minimum, target, revision} = product.replenishment;
    this.policyEditor = {productId:product.id, revision, minimum:this.quantity(minimum),
      target:this.quantity(target), error:null};
    void this.updateComplete.then(() => this.renderRoot.querySelector<HTMLInputElement>('.replenishment-form input')?.focus());
  }

  private policyForm(product: ProductStock, editor: PolicyEditor, blocked: boolean) {
    const helpId = 'replenishment-help-' + product.id, errorId = 'replenishment-error-' + product.id;
    return html`<form class="replenishment-form" novalidate @submit=${(event: SubmitEvent) => {
      event.preventDefault();
      if (blocked) return;
      const minimum = policyQuantity(editor.minimum, product.unit), target = policyQuantity(editor.target, product.unit);
      if (minimum === null || target === null) {
        this.policyEditor = {...editor, error:'invalidQuantity'};
        return;
      }
      if (stockUnits(minimum) > stockUnits(target)) {
        this.policyEditor = {...editor, error:'invalid_replenishment_bounds'};
        return;
      }
      this.intent({type:'submit', command:{action:'inventory.configure-replenishment', product_id:product.id,
        expected_revision:editor.revision, minimum, target}});
    }}>
      ${(['minimum','target'] as const).map(field => html`<label>${this.text(field)}
        <input required maxlength="19" inputmode=${product.unit === 'piece' ? 'numeric' : 'decimal'}
          .value=${live(editor[field])} ?disabled=${blocked} aria-invalid=${editor.error !== null}
          aria-describedby=${editor.error === null ? helpId : helpId + ' ' + errorId}
          @input=${(event: InputEvent) => {
            this.policyEditor = {...this.policyEditor!, [field]:(event.target as HTMLInputElement).value, error:null};
          }}></label>`)}
      <p id=${helpId}>${this.text('replenishmentGuide')}</p>
      ${editor.error === null ? nothing : this.error(errorId, editor.error)}
      <div class="actions">${this.submitButton('saveReplenishment', blocked)}
        ${this.button('cancel', () => {this.policyEditor = null;}, blocked)}</div>
    </form>`;
  }

  private product(product: ProductStock, manage: boolean, busy: boolean, blocked: boolean) {
    const policy = product.replenishment, editor = this.policyEditor;
    return html`<article tabindex="-1" id=${'product-' + product.id} aria-labelledby=${'name-' + product.id}>
      <h3 id=${'name-' + product.id}>${product.name}</h3>
      <p>${this.text('unit')} · ${this.text(product.unit)}</p>
      <dl>${(['recorded', 'reserved', 'available'] as const).map(key => html`
        <dt>${this.text(key)}</dt><dd>${this.quantity(product[key])}</dd>`)}</dl>
      <p>${this.text('minimum')} · ${this.quantity(policy.minimum)} ${this.text(product.unit)}</p>
      <p>${this.text('target')} · ${this.quantity(policy.target)} ${this.text(product.unit)}</p>
      <p>${policy.minimum === '0' ? this.text('replenishmentDisabled')
        : policy.needed === '0' ? this.text('replenishmentSatisfied')
        : html`<strong>${this.text('needed')} · ${this.quantity(policy.needed)} ${this.text(product.unit)}</strong>`}</p>
      ${product.outstandingPurchase === '0' ? nothing : html`
        <p>${this.text('outstandingPurchase')} · ${this.quantity(product.outstandingPurchase)} ${this.text(product.unit)}</p>
        <p>${this.text('shoppingNeeded')} · ${this.quantity(product.shoppingNeeded)} ${this.text(product.unit)}</p>`}
      <div class="actions">
        ${this.button('showHistory', () => this.intent({type:'history', productId:product.id}), busy)}
        ${manage && this.view!.report!.locations.length > 0
          ? this.button('moveStock', () => this.beginTransfer(product.id), blocked) : nothing}
        ${manage && this.selected !== product.id ? this.button('intake', () => this.select(product.id), blocked) : nothing}
        ${manage && editor?.productId !== product.id ? this.button('editReplenishment', () => this.editPolicy(product), blocked) : nothing}
      </div>
      ${manage && this.selected === product.id ? this.intake(product, blocked) : nothing}
      ${manage && editor?.productId === product.id ? this.policyForm(product, editor, blocked) : nothing}
    </article>`;
  }

  protected render() {
    const view = this.view;
    if (view === null) return nothing;
    const {report, history, result, busy, notice, pending} = view;
    const blocked = view.scope.readOnly || busy || pending;
    const manage = report?.mayManage === true && !view.scope.readOnly;
    const saved = result !== null && result.kind !== 'rejected' ? result : null;
    const movement = saved?.movement;
    const message = result?.kind === 'rejected'
      ? result.reason === 'inventory_stock_capacity' && result.command.action === 'shopping.post-receipt'
        ? 'shoppingPostingCapacity' : result.reason
      : notice;
    return html`<h2>${this.text('title')}</h2>
      ${message === null ? nothing : html`<vyp-ha-feedback
        .state=${feedbackState({kind:'notice', tone:'warning', message:this.text(message)})}></vyp-ha-feedback>`}
      ${saved === null ? nothing : html`<p role="status">${this.text(saved.kind === 'historical'
        ? 'historical' : movement ? MOVEMENT_SAVED[movement.action] : saved.shoppingAction
          ? SHOPPING_SAVED[saved.shoppingAction] : saved.replenishmentSaved ? 'replenishmentSaved' : saved.locationSaved ? 'locationSaved' : 'registered')}
        ${movement ? html`${this.quantity(movement.quantity)} ${this.text(movement.unit)}` : nothing}</p>
        ${report?.products.some(product => product.id === saved.productId) ? html`<a href=${'#product-' + saved.productId}
          @click=${(event: MouseEvent) => {
            event.preventDefault();
            this.renderRoot.querySelector<HTMLElement>('article[id="product-' + saved.productId + '"]')?.focus();
          }}>${this.text('viewProduct')}</a>` : nothing}
        <details><summary>${this.text('receipt')}</summary>
          <p>${this.text('operation')} <code>${saved.operationId}</code></p>
          ${movement ? html`<p>${this.text('movement')} <code>${movement.movementId}</code></p>` : nothing}
        </details>`}
      <div class="actions">${this.button('refresh', () => this.intent({type:'refresh'}), busy)}
        ${pending ? this.button('recover', () => this.intent({type:'recover'}), busy) : nothing}</div>
      ${busy && report === null ? html`<p role="status">${this.text('loading')}</p>` : nothing}
      ${report === null ? nothing : html`
        ${manage ? this.registration(blocked) : nothing}
        ${this.locations(report.locations, manage, blocked)}
        <vyp-ha-card .state=${cardState({title:this.text('pantry'), headingLevel:3})}>
          ${report.products.length === 0 ? html`<p>${this.text('empty')}</p>`
            : html`<div class="products">${report.products.map(product => this.product(product, manage, busy, blocked))}</div>`}
          ${report.cursor === null ? nothing : this.button('more', () => this.intent({type:'more'}), busy)}
        </vyp-ha-card>
        <domus-shopping .view=${view} .language=${this.language}></domus-shopping>`}
      ${history === null ? nothing : this.history(history, manage, busy, blocked)}
    `;
  }
}

registerButton();
registerCard();
registerFeedback();
registerField();
registerSelect();
customElements.define('domus-inventory', DomusInventory);

declare global {
  interface HTMLElementTagNameMap {'domus-inventory': DomusInventory;}
}
