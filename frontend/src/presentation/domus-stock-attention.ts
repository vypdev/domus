import {LitElement, css, html, nothing} from 'lit';
import {registerButton} from '@vypdev/ha-ui/button';
import {buttonState} from '@vypdev/ha-ui/button-contracts';
import {registerCard} from '@vypdev/ha-ui/card';
import {cardState} from '@vypdev/ha-ui/card-contracts';
import {registerFeedback} from '@vypdev/ha-ui/feedback';
import {feedbackState} from '@vypdev/ha-ui/feedback-contracts';
import type {StockAttentionItem, StockAttentionView} from '../application/stock-attention';
import {inventoryMessage, inventoryUnitMessage} from './inventory-messages';
import type {Language} from './messages';

const COPY = {
  en: {
    heading: 'Products below minimum',
    empty: 'No products below minimum.',
    loading: 'Loading the inventory summary…',
    denied: 'Your current household access does not allow viewing stock.',
    unavailable: 'The inventory summary could not be loaded.',
    retry: 'Retry inventory summary',
    open: 'Open Inventory',
  },
  es: {
    heading: 'Productos por debajo del mínimo',
    empty: 'No hay productos por debajo del mínimo.',
    loading: 'Cargando el resumen de inventario…',
    denied: 'Tu acceso actual al hogar no permite ver las existencias.',
    unavailable: 'No se pudo cargar el resumen de inventario.',
    retry: 'Volver a cargar el resumen de inventario',
    open: 'Abrir Inventario',
  },
} as const;

type CopyKey = keyof typeof COPY.en;

export class DomusStockAttention extends LitElement {
  static properties = {view: {attribute: false}, language: {attribute: false}};
  static styles = css`
    :host {display:block;--vyp-ha-surface:var(--surface);--vyp-ha-surface-raised:var(--surface);
      --vyp-ha-text:var(--text);--vyp-ha-text-secondary:var(--muted);--vyp-ha-border:var(--line);
      --vyp-ha-primary:var(--accent);--vyp-ha-focus-ring:3px solid var(--accent)}
    vyp-ha-card {margin-block-start:16px}
    vyp-ha-card::part(heading) {text-wrap:balance}
    ul {list-style:none;padding:0;margin:0}
    li {padding-block:9px;overflow-wrap:anywhere}
    li+li {border-block-start:1px solid var(--line)}
    p {margin:0}
    li p {color:var(--muted);margin-block-start:4px}
    a {display:inline-flex;align-items:center;min-height:44px;margin-block-start:8px;color:var(--accent)}
    a:focus-visible {outline:3px solid var(--accent);outline-offset:3px}
    vyp-ha-feedback + vyp-ha-button {margin-block-start:8px}
  `;

  declare view: StockAttentionView | null;
  declare language: Language;

  constructor() {super(); this.view = null; this.language = 'en';}

  private text(key: CopyKey): string {return COPY[this.language][key];}

  private quantity(item: StockAttentionItem, value: string): string {
    const amount = this.language === 'es' ? value.replace('.', ',') : value;
    return amount + ' ' + inventoryMessage(inventoryUnitMessage(item.unit, value), this.language);
  }

  protected render() {
    const view = this.view;
    if (view === null) return nothing;
    const title = view.state === 'ready'
      ? this.text('heading') + ' · ' + new Intl.NumberFormat(this.language).format(view.data.total)
      : this.text('heading');
    return html`<vyp-ha-card .state=${cardState({title, headingLevel:2})}>
      ${view.state === 'ready' ? html`
        ${view.data.total === 0 ? html`<p>${this.text('empty')}</p>` :
          html`<ul>${view.data.items.map(item => html`<li><strong>${item.name}</strong>
            <p>${inventoryMessage('available', this.language)} ${this.quantity(item, item.available)} ·
              ${inventoryMessage('minimum', this.language)} ${this.quantity(item, item.minimum)}</p>
          </li>`)}</ul>`}
        <a href="#inventory">${this.text('open')}</a>`
        : html`<vyp-ha-feedback .state=${view.state === 'loading'
          ? feedbackState({kind:'loading', message:this.text('loading')})
          : feedbackState({kind:'notice', tone:'warning', message:this.text(view.state)})}></vyp-ha-feedback>
          ${view.state === 'unavailable' ? html`<vyp-ha-button
            .state=${buttonState({label:this.text('retry'), variant:'outlined'})}
            @ha-press-request=${() => this.dispatchEvent(new Event('domus-stock-attention-retry', {
              bubbles:true, composed:true,
            }))}></vyp-ha-button>` : nothing}`}
    </vyp-ha-card>`;
  }
}

registerButton(); registerCard(); registerFeedback();
customElements.define('domus-stock-attention', DomusStockAttention);
declare global {interface HTMLElementTagNameMap {'domus-stock-attention': DomusStockAttention;}}
