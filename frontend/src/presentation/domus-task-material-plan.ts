import {LitElement, css, html, nothing} from 'lit';
import {registerField} from '@vypdev/ha-ui/field';
import type {FieldValueEvent} from '@vypdev/ha-ui/field';
import {textFieldState} from '@vypdev/ha-ui/field-contracts';
import {registerSelect} from '@vypdev/ha-ui/select';
import type {SelectValueEvent} from '@vypdev/ha-ui/select';
import {selectState} from '@vypdev/ha-ui/select-contracts';
import {registerButton} from '@vypdev/ha-ui/button';
import {buttonState} from '@vypdev/ha-ui/button-contracts';
import type {TaskMaterialPlanView} from '../application/task-material-planning';
import {taskQuantityInput} from '../domain/tasks';
import {materialMessage, materialSource, materialUnit} from './task-material-messages';
import type {TaskMaterialMessage} from './task-material-messages';
import type {Language} from './messages';
export type MaterialPlanIntent = Readonly<{action: 'load' | 'more' | 'clear'}>
  | Readonly<{action: 'add' | 'remove'; referenceId: string}>
  | Readonly<{action: 'edit'; referenceId: string; input: string}>;
export class DomusTaskMaterialPlan extends LitElement {
  static properties = {view: {attribute: false}, language: {attribute: false}, disabled: {attribute: false}};
  static styles = css`:host{display:block;margin-block:24px;min-width:0}h4{margin-block:0 8px}p{line-height:1.5}
    ul{padding:0;list-style:none}li{border:1px solid var(--line);padding:16px;border-radius:12px;margin-block:12px;overflow-wrap:anywhere}
    .actions{display:flex;gap:12px;flex-wrap:wrap;margin-block:12px}vyp-ha-button{--vyp-ha-button-height:44px}small{color:var(--muted)}`;
  declare view: TaskMaterialPlanView | null;
  declare language: Language;
  declare disabled: boolean;
  constructor() {super(); this.view = null; this.language = 'en'; this.disabled = false;}
  private text(key: TaskMaterialMessage): string {return materialMessage(key, this.language);}
  private intent(detail: MaterialPlanIntent): void {
    this.dispatchEvent(new CustomEvent('domus-material-plan-intent', {detail, bubbles: true, composed: true}));
  }
  protected render() {
    const view = this.view;
    if (view === null || !view.canLink && view.rows.length === 0) return nothing;
    const blocked = this.disabled || view.busy || view.readOnly;
    return html`<section aria-labelledby="material-plan-heading" aria-busy=${view.busy}><h4 id="material-plan-heading">${this.text('plan')}</h4>
      <p>${this.text('planHelp')}</p>
      ${view.rows.length ? html`<vyp-ha-button .state=${buttonState({label:this.text('clear'),variant:'outlined'})} ?disabled=${this.disabled || view.busy}
        @click=${() => this.intent({action:'clear'})}></vyp-ha-button>` : nothing}
      ${!view.open ? html`<vyp-ha-button .state=${buttonState({label:this.text('open')})} ?disabled=${blocked}
        @click=${() => this.intent({action:'load'})}></vyp-ha-button>` : html`
        <div class="actions"><vyp-ha-button .state=${buttonState({label:this.text('refresh')})} ?disabled=${blocked || !view.canLink}
          @click=${() => this.intent({action:'load'})}></vyp-ha-button>
          ${view.cursor ? html`<vyp-ha-button .state=${buttonState({label:this.text('more')})} ?disabled=${blocked}
            @click=${() => this.intent({action:'more'})}></vyp-ha-button>` : nothing}</div>
        ${view.choices.length ? html`<vyp-ha-select .value=${null} ?disabled=${blocked || view.rows.length >= 32}
          .state=${selectState({label:this.text('product'), placeholder:this.text('choose'), clearable:false,
            options:view.choices.map(choice => ({value:choice.referenceId, label:choice.name + ' · ' + materialUnit(choice.unit, this.language),
              disabled:view.rows.some(row => row.referenceId === choice.referenceId)}))})}
          @ha-select-request=${(event: SelectValueEvent) => {if (typeof event.detail.value === 'string') this.intent({action:'add', referenceId:event.detail.value});}}
          ></vyp-ha-select>` : view.notice === null && !view.busy ? html`<p>${this.text('empty')}</p>` : nothing}`}
      ${view.notice ? html`<p role="alert">${this.text(view.notice)}</p>` : nothing}
      <ul>${view.rows.map((row, index) => {
        const precision = row.choice?.unit === 'piece' ? 0 : 6;
        const invalid = row.choice !== null && taskQuantityInput(row.input, precision) === null;
        return html`<li><strong>${row.choice?.name ?? this.text('unreviewed')}</strong>
          ${row.choice ? html`<p>${materialUnit(row.choice.unit, this.language)} · ${materialSource('pantry', this.language)}</p>` : nothing}
          <vyp-ha-field id=${'material-plan-' + index} .value=${row.input} ?disabled=${blocked || row.choice === null || !view.canLink}
            .state=${textFieldState({label:this.text('planned'), inputMode:'decimal', maxLength:64, description:this.text('quantityHelp'),
              error:invalid ? this.text('invalidQuantity') : ''})}
            @ha-value-request=${(event: FieldValueEvent) => this.intent({action:'edit', referenceId:row.referenceId, input:event.detail.value})}></vyp-ha-field>
          <small>${this.text(precision === 0 ? 'whole' : 'decimal')}</small>
          <div class="actions"><vyp-ha-button .state=${buttonState({label:this.text('remove')})} ?disabled=${this.disabled || view.busy}
            @click=${() => this.intent({action:'remove', referenceId:row.referenceId})}></vyp-ha-button></div></li>`;
      })}</ul>${view.rows.length >= 32 ? html`<p role="status">${this.text('limit')}</p>` : nothing}
    </section>`;
  }
}
registerField(); registerSelect(); registerButton();
customElements.define('domus-task-material-plan', DomusTaskMaterialPlan);
declare global {interface HTMLElementTagNameMap {'domus-task-material-plan': DomusTaskMaterialPlan;}}
