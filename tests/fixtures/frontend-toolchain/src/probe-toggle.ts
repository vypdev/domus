import {LitElement, css, html} from 'lit';
/** Isolated framework probe, not Domus product source. */
export class ProbeToggle extends LitElement {
  static properties = {active: {type: Boolean, reflect: true}};
  static styles = css`button {min-height:44px;min-width:160px;font:inherit;border-radius:8px} button:focus-visible {outline:3px solid #175f3f}`;
  declare active: boolean;
  constructor() { super(); this.active = false; }
  toggle() {
    this.active = !this.active;
    this.dispatchEvent(new CustomEvent('probe-change', {detail: this.active, bubbles: true, composed: true}));
  }
  render() {
    return html`<button type="button" aria-pressed=${this.active} @click=${this.toggle}>${this.active ? 'Enabled' : 'Disabled'}</button>`;
  }
}
customElements.define('probe-toggle', ProbeToggle);

declare global {
  interface HTMLElementTagNameMap {"probe-toggle": ProbeToggle}
  interface HTMLElementEventMap {"probe-change": CustomEvent<boolean>}
}
