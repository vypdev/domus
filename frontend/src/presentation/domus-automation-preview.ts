import {LitElement, css, html, nothing} from 'lit';
import type {PropertyValues} from 'lit';
import {registerButton} from '@vypdev/ha-ui/button';
import {buttonState} from '@vypdev/ha-ui/button-contracts';
import {registerCard} from '@vypdev/ha-ui/card';
import {cardState} from '@vypdev/ha-ui/card-contracts';
import {registerFeedback} from '@vypdev/ha-ui/feedback';
import {feedbackState} from '@vypdev/ha-ui/feedback-contracts';
import {registerField} from '@vypdev/ha-ui/field';
import type {FieldValueEvent} from '@vypdev/ha-ui/field';
import {textFieldState} from '@vypdev/ha-ui/field-contracts';
import {registerSelect} from '@vypdev/ha-ui/select';
import type {SelectValueEvent} from '@vypdev/ha-ui/select';
import {selectState} from '@vypdev/ha-ui/select-contracts';
import type {AutomationPreviewIntent, AutomationPreviewView} from '../application/automation-preview';
import type {Language} from './messages';

const COPY = {
  en: {
    heading: 'Automation preview',
    description: 'Simulate a manual rule that proposes one task. Previewing makes no changes.',
    title: 'Proposed task title',
    titleInvalid: 'Enter a task title of 1 to 160 characters.',
    condition: 'Stock below minimum (optional)',
    noCondition: 'No stock condition',
    noProducts: 'No products on this page.',
    clearCondition: 'Remove stock condition',
    findProduct: 'Find a product',
    noMatches: 'No matching products.',
    first: 'First products',
    next: 'Next products',
    preview: 'Preview rule',
    loading: 'Loading automation preview…',
    previewing: 'Checking the rule…',
    products: 'Loading products…',
    denied: 'Your current household permissions do not allow automation previews.',
    unavailable: 'Automation preview is unavailable. Try again.',
    productsUnavailable: 'Could not load products. Try again.',
    previewUnavailable: 'Could not preview the rule. Check the selected product and try again.',
    retry: 'Try again',
    wouldCreate: 'Would create this task',
    noAction: 'No task would be created',
    matched: 'Available stock is below the minimum.',
    unmatched: 'The stock condition did not match.',
  },
  es: {
    heading: 'Vista previa de automatización',
    description: 'Simula una regla manual que propone una tarea. La vista previa no aplica cambios.',
    title: 'Título de la tarea propuesta',
    titleInvalid: 'Introduce un título de 1 a 160 caracteres.',
    condition: 'Existencias por debajo del mínimo (opcional)',
    noCondition: 'Sin condición de existencias',
    noProducts: 'No hay productos en esta página.',
    clearCondition: 'Quitar la condición de existencias',
    findProduct: 'Buscar un producto',
    noMatches: 'No hay productos que coincidan.',
    first: 'Primeros productos',
    next: 'Siguientes productos',
    preview: 'Previsualizar regla',
    loading: 'Cargando la vista previa de automatización…',
    previewing: 'Comprobando la regla…',
    products: 'Cargando productos…',
    denied: 'Tus permisos actuales del hogar no permiten previsualizar automatizaciones.',
    unavailable: 'La vista previa de automatización no está disponible. Vuelve a intentarlo.',
    productsUnavailable: 'No se pudieron cargar los productos. Vuelve a intentarlo.',
    previewUnavailable: 'No se pudo previsualizar la regla. Comprueba el producto y vuelve a intentarlo.',
    retry: 'Volver a intentar',
    wouldCreate: 'Se crearía esta tarea',
    noAction: 'No se crearía ninguna tarea',
    matched: 'Las existencias disponibles están por debajo del mínimo.',
    unmatched: 'No se cumple la condición de existencias.',
  },
} as const;

type CopyKey = keyof typeof COPY.en;

export class DomusAutomationPreview extends LitElement {
  static properties = {view: {attribute: false}, language: {attribute: false}};
  static styles = css`
    :host {display:block;--vyp-ha-surface:var(--surface);--vyp-ha-surface-raised:var(--surface);--vyp-ha-text:var(--text);
      --vyp-ha-text-secondary:var(--muted);--vyp-ha-border:var(--line);--vyp-ha-primary:var(--accent);
      --vyp-ha-on-accent:var(--surface);--vyp-ha-focus-ring:3px solid var(--accent)}
    form {display:grid;gap:14px}
    .actions {display:flex;flex-wrap:wrap;align-items:center;gap:8px}
    p {margin:0;overflow-wrap:anywhere}
    .result {border-block-start:1px solid var(--line);padding-block-start:12px}
    .result p+p {margin-block-start:6px}
    vyp-ha-card {margin-block-end:16px}
    vyp-ha-feedback + .actions {margin-block-start:12px}
  `;

  declare view: AutomationPreviewView | null;
  declare language: Language;

  constructor() {super(); this.view = null; this.language = 'en';}

  private text(key: CopyKey): string {return COPY[this.language][key];}

  private intent(detail: AutomationPreviewIntent): void {
    this.dispatchEvent(new CustomEvent<AutomationPreviewIntent>('domus-automation-preview-intent', {
      detail, bubbles: true, composed: true,
    }));
  }

  protected updated(changed: PropertyValues<this>): void {
    if (changed.has('view') && this.view?.state === 'ready' && this.view.issue === 'title')
      this.renderRoot.querySelector<HTMLElement>('vyp-ha-field')!.focus();
  }

  private feedback(key: CopyKey, loading = false) {
    return html`<vyp-ha-feedback .state=${loading
      ? feedbackState({kind: 'loading', message: this.text(key)})
      : feedbackState({kind: 'notice', tone: 'warning', message: this.text(key)})}></vyp-ha-feedback>`;
  }

  private button(key: CopyKey, type: 'retry' | 'first' | 'next', disabled = false) {
    return html`<vyp-ha-button .state=${buttonState({label: this.text(key), variant: 'outlined'})}
      ?disabled=${disabled} @ha-press-request=${() => this.intent({type})}></vyp-ha-button>`;
  }

  private form(view: Extract<AutomationPreviewView, {state: 'ready'}>) {
    const blocked = view.busy !== null;
    const products = new Map(view.catalog.products.map(product => [product.id, product]));
    if (view.selected !== null) products.set(view.selected.id, view.selected);
    const options = Array.from(products.values(), product => ({
      value: product.id, label: product.name.replace(/[\u007f-\u009f]/gu, '�'),
    }));
    return html`<form novalidate @submit=${(event: SubmitEvent) => {
      event.preventDefault();
      if (!blocked) this.intent({type: 'preview'});
    }}>
      <p>${this.text('description')}</p>
      <vyp-ha-field .value=${view.title} ?disabled=${blocked}
        .state=${textFieldState({label: this.text('title'), required: true, maxLength: 320,
          error: view.issue === 'title' ? this.text('titleInvalid') : ''})}
        @ha-value-request=${(event: FieldValueEvent) => this.intent({type: 'title', value: event.detail.value})}>
      </vyp-ha-field>
      <vyp-ha-select .value=${view.selected?.id ?? null} ?disabled=${blocked}
        .state=${selectState({label: this.text('condition'), options, placeholder: this.text('noCondition'),
          emptyMessage: this.text('noProducts'), clearLabel: this.text('clearCondition'), searchLabel: this.text('findProduct'),
          searchPlaceholder: this.text('findProduct'), notFoundMessage: this.text('noMatches')})}
        @ha-select-request=${(event: SelectValueEvent) => this.intent({type: 'product', value: event.detail.value as string | null})}>
      </vyp-ha-select>
      ${view.catalog.after !== null || view.catalog.next !== null ? html`<div class="actions">
        ${view.catalog.after !== null ? this.button('first', 'first', blocked) : nothing}
        ${view.catalog.next !== null ? this.button('next', 'next', blocked) : nothing}
      </div>` : nothing}
      <div class="actions"><vyp-ha-button type="submit" ?disabled=${blocked}
        .state=${buttonState({label: this.text('preview'), variant: 'primary'})}></vyp-ha-button></div>
      ${view.busy === 'preview' ? this.feedback('previewing', true)
        : view.busy === 'products' ? this.feedback('products', true) : nothing}
      ${view.issue === 'products' ? this.feedback('productsUnavailable')
        : view.issue === 'preview' ? this.feedback('previewUnavailable') : nothing}
      ${view.result === null ? nothing : html`<div class="result" role="status">
        <p><strong>${this.text(view.result ? 'wouldCreate' : 'noAction')}</strong></p><p>${view.title}</p>
        ${view.selected === null ? nothing : html`<p>${view.selected.name} ·
          ${this.text(view.result ? 'matched' : 'unmatched')}</p>`}
      </div>`}
    </form>`;
  }

  protected render() {
    const view = this.view;
    if (view === null) return nothing;
    return html`<vyp-ha-card .state=${cardState({title: this.text('heading'), headingLevel: 2})}>
      ${view.state === 'ready' ? this.form(view)
        : view.state === 'loading' ? this.feedback('loading', true)
        : this.feedback(view.state)}
      ${view.state === 'unavailable' ? html`<div class="actions">${this.button('retry', 'retry')}</div>` : nothing}
    </vyp-ha-card>`;
  }
}

registerButton(); registerCard(); registerFeedback(); registerField(); registerSelect();
customElements.define('domus-automation-preview', DomusAutomationPreview);
declare global {interface HTMLElementTagNameMap {'domus-automation-preview': DomusAutomationPreview;}}
