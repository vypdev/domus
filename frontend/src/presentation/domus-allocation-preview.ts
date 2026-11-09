import {LitElement, css, html, nothing} from 'lit';
import type {PropertyValues} from 'lit';
import {registerButton} from '@vypdev/ha-ui/button';
import {buttonState} from '@vypdev/ha-ui/button-contracts';
import type {AllocationView} from '../application/allocation-controller';
import {minorPoints} from '../domain/point-allocation';
import type {AllocationInput, ManualShare, ReviewedAllocation} from '../domain/point-allocation';
import {allocationDetails} from './allocation-details';
import type {ParticipantName} from './allocation-details';
import {familyMessage} from './family-messages';
import type {FamilyMessage} from './family-messages';
import type {Language} from './messages';

export class DomusAllocationPreview extends LitElement {
  static properties = {view: {attribute: false}, language: {attribute: false}, names: {attribute: false},
    ownId: {attribute: false}, disabled: {attribute: false}, selected: {state: true}, amounts: {state: true}};
  static styles = css`
    :host {display:block;margin-block:12px;--vyp-ha-surface:var(--surface);--vyp-ha-text:var(--text);
      --vyp-ha-text-secondary:var(--muted);--vyp-ha-border:var(--line);--vyp-ha-primary:var(--accent)}
    label {display:flex;align-items:center;gap:8px;margin-block:8px;overflow-wrap:anywhere}
    fieldset {border:0;padding:0;margin:8px 0} legend,summary {font-weight:650}
    input {max-width:100%;font:inherit;color:inherit;background:var(--surface)}
    input[type="text"] {padding:8px;border:1px solid var(--line);border-radius:8px;width:9ch}
    dl {display:grid;grid-template-columns:minmax(0,2fr) minmax(0,1fr);gap:6px;margin:0}
    dd {margin:0} :focus-visible {outline:3px solid var(--accent);outline-offset:3px}
  `;
  declare view: AllocationView | null;
  declare language: Language;
  declare names: readonly ParticipantName[];
  declare ownId: string;
  declare disabled: boolean;
  private declare selected: readonly string[];
  private declare amounts: Readonly<Record<string, string>>;

  constructor() {
    super(); this.view = null; this.language = 'en'; this.names = []; this.ownId = '';
    this.disabled = false; this.selected = []; this.amounts = {};
  }

  protected willUpdate(changed: PropertyValues<this>): void {
    const previous = changed.get('view')?.scope, current = this.view?.scope;
    if (changed.has('ownId') || changed.has('view') && (previous?.key !== current?.key
        || previous?.work?.occurrenceId !== current?.work?.occurrenceId
        || previous?.work?.revision !== current?.work?.revision)) {
      this.selected = [this.ownId]; this.amounts = {};
    }
  }

  private previouslyBlocked = false;
  protected updated(): void {
    const blocked = this.needsReview && this.reviewed === undefined;
    if (blocked !== this.previouslyBlocked) {
      this.previouslyBlocked = blocked;
      this.dispatchEvent(new Event('domus-allocation-draft', {bubbles: true, composed: true}));
    }
  }

  private get manual(): boolean {
    const settings = this.view?.settings;
    return (settings?.override?.policy ?? settings?.household?.policy)?.mode === 'manual';
  }

  get needsReview(): boolean {
    return this.manual || this.selected.length !== 1 || this.selected[0] !== this.ownId;
  }

  private get draft(): AllocationInput | null {
    const performerIds = this.selected;
    if (performerIds.length === 0) return null;
    if (!this.manual) return {performerIds};
    const manualShares: ManualShare[] = [];
    for (const member_id of performerIds) {
      const amount_minor = minorPoints(this.amounts[member_id] ?? '');
      if (amount_minor === null) return null;
      manualShares.push({member_id, amount_minor});
    }
    return {performerIds, manualShares};
  }

  get reviewed(): ReviewedAllocation | undefined {
    const completion = this.view?.review?.completion, draft = this.draft;
    if (completion === undefined || draft === null || JSON.stringify(draft.performerIds) !== JSON.stringify(completion.performerIds)
      || JSON.stringify(draft.manualShares) !== JSON.stringify(completion.manualShares)) return undefined;
    return completion;
  }

  private text(key: FamilyMessage): string {return familyMessage(key, this.language);}

  protected render() {
    const view = this.view;
    if (!view?.scope.work?.canComplete || this.ownId === '') return nothing;
    const disabled = this.disabled || view.scope.readOnly || view.busy;
    const draft = this.draft;
    const notice = view.notice === 'unavailable' ? 'policyUnavailable' : view.notice;
    return html`<details ?open=${this.manual}><summary>${this.text('preview')}</summary>
      <p>${this.text('reviewed')}</p>
      <fieldset ?disabled=${disabled}><legend>${this.text('performers')}</legend>
        ${this.names.map(person => {
          const checked = this.selected.includes(person.id);
          return html`<label><input type="checkbox" .checked=${checked} ?disabled=${!checked && this.selected.length >= 32}
            @change=${(event: Event) => {
              this.selected = (event.target as HTMLInputElement).checked
                ? [...this.selected, person.id].sort() : this.selected.filter(id => id !== person.id);
            }}>${person.name}</label>
            ${this.manual && checked ? html`<label>${person.name} · ${this.text('manual')}
              <input type="text" inputmode="decimal" maxlength="8" .value=${this.amounts[person.id] ?? ''}
                @input=${(event: InputEvent) => {
                  this.amounts = {...this.amounts, [person.id]: (event.target as HTMLInputElement).value};
                }}></label>` : nothing}`;
        })}
      </fieldset>
      ${this.manual && draft === null ? html`<p>${this.text('invalidAmounts')}</p>` : nothing}
      <vyp-ha-button .state=${buttonState({label: this.text('preview'), variant: 'outlined'})}
        ?disabled=${disabled || draft === null} @ha-press-request=${() => {
          if (draft !== null) this.dispatchEvent(new CustomEvent<AllocationInput>('domus-allocation-preview', {detail: draft, bubbles: true, composed: true}));
        }}></vyp-ha-button>
      ${notice === null ? nothing : html`<p role="status">${this.text(notice)}</p>`}
      ${this.reviewed === undefined ? nothing : html`<div role="status">${allocationDetails(view.review!.evidence, this.language, this.names, true)}</div>`}
    </details>`;
  }
}
registerButton();
customElements.define('domus-allocation-preview', DomusAllocationPreview);
declare global {interface HTMLElementTagNameMap {'domus-allocation-preview': DomusAllocationPreview;}}
