import {LitElement, css, html, nothing} from 'lit';
import {keyed} from 'lit/directives/keyed.js';
import {registerButton} from '@vypdev/ha-ui/button';
import {buttonState} from '@vypdev/ha-ui/button-contracts';
import type {InventoryState} from '../application/inventory-controller';
import {shoppingReadSnapshot} from '../application/inventory-controller';
import {inventoryOperationFeedback} from './inventory-operation-feedback';
import {inventoryMessage} from './inventory-messages';
import type {InventoryMessage} from './inventory-messages';
import type {Language} from './messages';
import './domus-shopping';

/** Shopping presentation; command authority and recovery stay with InventoryController. */
export class DomusShoppingWorkspace extends LitElement {
  static properties = {view:{attribute:false}, language:{attribute:false}};
  static styles = css`
    :host {display:grid;gap:16px;--vyp-ha-surface:var(--surface);--vyp-ha-surface-raised:var(--surface);
      --vyp-ha-text:var(--text);--vyp-ha-text-secondary:var(--muted);--vyp-ha-border:var(--line);
      --vyp-ha-primary:var(--accent);--vyp-ha-on-accent:var(--surface);--vyp-ha-focus-ring:3px solid var(--accent)}
    h2,p {margin:0} .actions {display:flex;flex-wrap:wrap;gap:8px}
    a {color:var(--accent)} :focus-visible {outline:3px solid var(--accent);outline-offset:3px}
    code {overflow-wrap:anywhere}
  `;
  declare view: InventoryState | null;
  declare language: Language;
  constructor() {super(); this.view = null; this.language = 'en';}
  private text(key: InventoryMessage): string {return inventoryMessage(key, this.language);}
  private button(key: 'refresh' | 'recover') {
    return html`<vyp-ha-button .state=${buttonState({label:this.text(key === 'refresh' ? 'refreshShopping' : 'recoverShopping'), variant:'outlined'})}
      ?disabled=${this.view!.busy} @ha-press-request=${() => {
        this.dispatchEvent(new CustomEvent('domus-inventory-intent',
          {detail:{type:key}, bubbles:true, composed:true}));
      }}></vyp-ha-button>`;
  }
  protected render() {
    const view = this.view;
    if (view === null) return nothing;
    const report = view.accessDenied ? null : view.report ?? view.retainedReport;
    return html`<h2>${this.text('shopping')}</h2>
      <p><a href="#inventory">${this.text('openInventory')}</a></p>
      ${inventoryOperationFeedback(view, this.language, nothing, 'shoppingUnavailable')}
      ${!view.accessDenied && view.retainedReport != null ? html`<p role="status">${this.text('staleInventory')}</p>` : nothing}
      <div class="actions">${this.button('refresh')}${view.pending ? this.button('recover') : nothing}</div>
      ${view.busy && view.report === null ? html`<p role="status">${this.text('shoppingLoading')}</p>` : nothing}
      ${report == null ? nothing : keyed(view.scope.key,
        html`<domus-shopping .view=${view.report === null || view.retainedShopping != null
          ? {...view, ...shoppingReadSnapshot(view), report} : view} .language=${this.language}></domus-shopping>`)}`;
  }
}

registerButton();
customElements.define('domus-shopping-workspace', DomusShoppingWorkspace);
declare global {interface HTMLElementTagNameMap {'domus-shopping-workspace': DomusShoppingWorkspace;}}
