import {LitElement, css, html, nothing} from 'lit';
import {registerButton} from '@vypdev/ha-ui/button';
import {buttonState} from '@vypdev/ha-ui/button-contracts';
import {registerCard} from '@vypdev/ha-ui/card';
import {cardState} from '@vypdev/ha-ui/card-contracts';
import {registerFeedback} from '@vypdev/ha-ui/feedback';
import {feedbackState} from '@vypdev/ha-ui/feedback-contracts';
import type {ShoppingAttentionView} from '../application/shopping-attention';
import {shoppingItemKey} from '../domain/inventory';
import {inventoryMessage, inventoryUnitMessage} from './inventory-messages';
import type {Language} from './messages';

const COPY = {
  en: {
    heading: 'Items to buy',
    empty: 'There are no items to buy.',
    loading: 'Loading the shopping summary…',
    denied: 'Your current household access does not allow viewing the shopping list.',
    unavailable: 'The shopping summary could not be loaded.',
    retry: 'Retry shopping summary',
    truncated: 'Showing the first 25 items in the shared shopping list.',
  },
  es: {
    heading: 'Artículos por comprar',
    empty: 'No quedan artículos por comprar.',
    loading: 'Cargando el resumen de compras…',
    denied: 'Tu acceso actual al hogar no permite ver la lista de compras.',
    unavailable: 'No se pudo cargar el resumen de compras.',
    retry: 'Volver a cargar el resumen de compras',
    truncated: 'Se muestran los primeros 25 artículos de la lista compartida de compras.',
  },
} as const;

export class DomusShoppingAttention extends LitElement {
  static properties = {view:{attribute:false}, language:{attribute:false}};
  static styles = css`
    :host {display:block;--vyp-ha-surface:var(--surface);--vyp-ha-surface-raised:var(--surface);
      --vyp-ha-text:var(--text);--vyp-ha-text-secondary:var(--muted);--vyp-ha-border:var(--line);
      --vyp-ha-primary:var(--accent);--vyp-ha-focus-ring:3px solid var(--accent)}
    vyp-ha-card {margin-block-start:16px}
    ul {list-style:none;padding:0;margin:0}
    li+li {border-block-start:1px solid var(--line)}
    p {margin:0}
    ul + p {margin-block-start:8px}
    a {display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:4px 12px;
      min-height:44px;color:var(--accent);overflow-wrap:anywhere}
    a:focus-visible {outline:3px solid var(--accent);outline-offset:3px}
    vyp-ha-feedback + vyp-ha-button {margin-block-start:8px}
  `;

  declare view: ShoppingAttentionView | null;
  declare language: Language;

  constructor() {super(); this.view = null; this.language = 'en';}

  protected render() {
    const view = this.view;
    if (view === null) return nothing;
    const copy = COPY[this.language];
    const title = view.state === 'ready'
      ? copy.heading + ' · ' + new Intl.NumberFormat(this.language).format(view.data.total)
      : copy.heading;
    return html`<vyp-ha-card .state=${cardState({title, headingLevel:2})}>
      ${view.state === 'ready' ? html`
        ${view.data.total === 0 ? html`<p>${copy.empty}</p>`
          : html`<ul>${view.data.items.map(item => html`<li>
            <a href=${'#shopping/' + shoppingItemKey(item)}><span>${item.name}</span>
              <span>${this.language === 'es' ? item.total.replace('.', ',') : item.total}
                ${inventoryMessage(inventoryUnitMessage(item.unit, item.total), this.language)}</span></a>
          </li>`)}</ul>`}
        ${view.data.total > 25 ? html`<p>${copy.truncated}</p>` : nothing}`
        : html`<vyp-ha-feedback .state=${view.state === 'loading'
          ? feedbackState({kind:'loading', message:copy.loading})
          : feedbackState({kind:'notice', tone:'warning', message:copy[view.state]})}></vyp-ha-feedback>
          ${view.state === 'unavailable' ? html`<vyp-ha-button
            .state=${buttonState({label:copy.retry, variant:'outlined'})}
            @ha-press-request=${() => this.dispatchEvent(new Event('domus-shopping-attention-retry', {
              bubbles:true, composed:true,
            }))}></vyp-ha-button>` : nothing}`}
    </vyp-ha-card>`;
  }
}

registerButton(); registerCard(); registerFeedback();
customElements.define('domus-shopping-attention', DomusShoppingAttention);
declare global {interface HTMLElementTagNameMap {'domus-shopping-attention': DomusShoppingAttention;}}
