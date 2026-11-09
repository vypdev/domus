import {LitElement, css, html, nothing} from 'lit';
import type {PropertyValues} from 'lit';
import {live} from 'lit/directives/live.js';
import {registerCard} from '@vypdev/ha-ui/card';
import {cardState} from '@vypdev/ha-ui/card-contracts';
import {registerButton} from '@vypdev/ha-ui/button';
import {buttonState} from '@vypdev/ha-ui/button-contracts';
import type {AllocationView} from '../application/allocation-controller';
import {ALLOCATION_MODES, SHARE_ROUNDINGS} from '../domain/point-allocation';
import type {AllocationMode, AllocationPolicy, ShareRounding} from '../domain/point-allocation';
import {familyMessage} from './family-messages';
import type {FamilyMessage} from './family-messages';
import type {Language} from './messages';

export type AllocationSettingsIntent = {readonly type: 'refresh' | 'recover'}
  | {readonly type: 'save'; readonly policy: AllocationPolicy | null};
const DEFAULT: AllocationPolicy = {mode: 'conserve_total', precision: 0, rounding: null};

export class DomusAllocationSettings extends LitElement {
  static properties = {view: {attribute: false}, language: {attribute: false}, draft: {state: true}};
  static styles = css`
    :host {display:block;margin-block:16px;--vyp-ha-surface:var(--surface);--vyp-ha-text:var(--text);
      --vyp-ha-text-secondary:var(--muted);--vyp-ha-border:var(--line);--vyp-ha-primary:var(--accent)}
    h3 {margin:0} form {display:flex;flex-wrap:wrap;gap:12px;align-items:end}
    label {display:grid;gap:4px;font-weight:650} select {font:inherit;color:inherit;background:var(--surface);
      padding:8px;border:1px solid var(--line);border-radius:8px;max-width:100%}
    :focus-visible {outline:3px solid var(--accent);outline-offset:3px}
  `;
  declare view: AllocationView | null;
  declare language: Language;
  private declare draft: AllocationPolicy;

  constructor() {super(); this.view = null; this.language = 'en'; this.draft = DEFAULT;}
  private text(key: FamilyMessage): string {return familyMessage(key, this.language);}
  private intent(detail: AllocationSettingsIntent): void {
    this.dispatchEvent(new CustomEvent('domus-allocation-settings', {detail, bubbles: true, composed: true}));
  }

  protected willUpdate(changed: PropertyValues<this>): void {
    const previous = changed.get('view'), current = this.view;
    if (changed.has('view') && (previous?.settings !== current?.settings || previous?.scope.definitionId !== current?.scope.definitionId)) {
      this.draft = current?.settings?.override?.policy ?? current?.settings?.household?.policy ?? DEFAULT;
    }
  }

  protected render() {
    const view = this.view;
    if (!view?.scope.canManage) return nothing;
    const task = view.scope.definitionId !== null, settings = view.settings;
    const readOnly = view.scope.readOnly || view.busy || view.pending;
    const notice = view.notice === 'unavailable' ? 'policyUnavailable' : view.notice;
    const draft = this.draft;
    return html`<vyp-ha-card .state=${cardState({title: this.text(task ? 'taskPolicy' : 'configuration'), headingLevel: 3})}>
      <div aria-busy=${view.busy}>
        ${notice === null ? nothing : html`<p role="status">${this.text(notice)}</p>`}
        ${view.pending ? html`<vyp-ha-button .state=${buttonState({label: this.text('checkRequest'), variant: 'outlined'})}
          ?disabled=${view.busy} @ha-press-request=${() => this.intent({type: 'recover'})}></vyp-ha-button>` : nothing}
        ${settings === null ? html`<vyp-ha-button .state=${buttonState({label: this.text('refresh'), variant: 'outlined'})}
          ?disabled=${view.busy} @ha-press-request=${() => this.intent({type: 'refresh'})}></vyp-ha-button>` : html`
          ${task && !settings.override?.policy ? html`<p>${this.text('inherited')}</p>` : nothing}
          ${settings.household === null ? html`<p>${this.text('legacyDefault')}</p>` : nothing}
          <form @submit=${(event: SubmitEvent) => {event.preventDefault(); this.intent({type: 'save', policy: this.draft});}}>
            <label>${this.text('policyMode')}<select .value=${live(draft.mode)} ?disabled=${readOnly} @change=${(event: Event) => {
              const mode = (event.target as HTMLSelectElement).value as AllocationMode;
              this.draft = {...this.draft, mode, rounding: mode === 'equal_share' ? 'half_up' : null};
            }}>${ALLOCATION_MODES.map(mode => html`<option .value=${mode}>${this.text(mode)}</option>`)}</select></label>
            <label>${this.text('precision')}<select .value=${live(String(draft.precision))} ?disabled=${readOnly} @change=${(event: Event) => {
              this.draft = {...this.draft, precision: (event.target as HTMLSelectElement).value === '0' ? 0 : 2};
            }}><option value="0">${this.text('whole')}</option><option value="2">${this.text('decimals')}</option></select></label>
            ${draft.mode !== 'equal_share' ? nothing : html`<label>${this.text('rounding')}
              <select .value=${live(draft.rounding!)} ?disabled=${readOnly} @change=${(event: Event) => {
                this.draft = {...this.draft, rounding: (event.target as HTMLSelectElement).value as ShareRounding};
              }}>${SHARE_ROUNDINGS.map(rounding => html`<option .value=${rounding}>${this.text(rounding)}</option>`)}</select></label>`}
            <vyp-ha-button type="submit" .state=${buttonState({label: this.text('save'), variant: 'primary'})}
              ?disabled=${readOnly}></vyp-ha-button>
            ${settings.override?.policy ? html`<vyp-ha-button .state=${buttonState({label: this.text('clear'), variant: 'outlined'})}
              ?disabled=${readOnly} @ha-press-request=${() => this.intent({type: 'save', policy: null})}></vyp-ha-button>` : nothing}
          </form>`}
      </div></vyp-ha-card>`;
  }
}
registerCard(); registerButton();
customElements.define('domus-allocation-settings', DomusAllocationSettings);
declare global {interface HTMLElementTagNameMap {'domus-allocation-settings': DomusAllocationSettings;}}
