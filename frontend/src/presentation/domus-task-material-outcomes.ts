import {LitElement, css, html, nothing} from 'lit';
import {registerField} from '@vypdev/ha-ui/field';
import type {FieldValueEvent} from '@vypdev/ha-ui/field';
import {textFieldState} from '@vypdev/ha-ui/field-contracts';
import {registerButton} from '@vypdev/ha-ui/button';
import {buttonState} from '@vypdev/ha-ui/button-contracts';
import type {Revision} from '../domain/administration';
import {taskQuantityInput, taskText, TASK_TEXT_LIMITS} from '../domain/tasks';
import type {TaskDetail, TaskMaterialOutcome} from '../domain/tasks';
import type {Language} from './messages';
import {materialMessage, materialSource, materialUnit} from './task-material-messages';
import type {TaskMaterialMessage} from './task-material-messages';
export interface MaterialRecordingDraft {readonly revision: Revision; readonly quantity: string; readonly reason: string;}
export type MaterialRecordingDrafts = Readonly<Record<string, MaterialRecordingDraft>>;
export interface MaterialSettlementIntent {
  readonly occurrenceId: string; readonly intentId: string; readonly cycleId: string; readonly revision: Revision;
  readonly quantity?: string; readonly reason?: string;
}
export class DomusTaskMaterialOutcomes extends LitElement {
  static properties = {work: {attribute:false}, drafts: {attribute:false}, disabled: {attribute:false}, language: {attribute:false}};
  static styles = css`:host{display:block;margin-block:24px;min-width:0}h4{margin-block:0 8px}h5{font-size:1rem;margin-block:0 12px}
    p{line-height:1.5}ul{padding:0;list-style:none}li{padding:16px;border:1px solid var(--line);border-radius:12px;margin-block:12px;overflow-wrap:anywhere}
    dl{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:8px}dd{margin:0}form{display:grid;gap:12px}
    vyp-ha-button{--vyp-ha-button-height:44px}.status{font-weight:600}small{color:var(--muted)}`;
  declare work: TaskDetail | null;
  declare drafts: MaterialRecordingDrafts;
  declare disabled: boolean;
  declare language: Language;
  constructor() {super(); this.work = null; this.drafts = {}; this.disabled = false; this.language = 'en';}
  private text(key: TaskMaterialMessage): string {return materialMessage(key, this.language);}
  private draft(value: TaskMaterialOutcome): MaterialRecordingDraft {
    return this.drafts[value.intentId] ?? {revision:value.revision, quantity:'', reason:''};
  }
  private change(value: TaskMaterialOutcome, patch: Partial<MaterialRecordingDraft>): void {
    this.dispatchEvent(new CustomEvent('domus-material-recording-draft', {
      detail:{intentId:value.intentId, draft:Object.freeze({...this.draft(value), ...patch})}, bubbles:true, composed:true}));
  }
  private settle(value: TaskMaterialOutcome, quantity?: string, reason?: string): void {
    this.dispatchEvent(new CustomEvent<MaterialSettlementIntent>('domus-material-settlement-intent', {
      detail:{occurrenceId:this.work!.occurrenceId, intentId:value.intentId, cycleId:value.cycleId,
        revision:this.draft(value).revision, ...quantity === undefined ? {} : {quantity, reason}}, bubbles:true, composed:true}));
  }
  protected render() {
    const work = this.work, values = work?.materialOutcomes;
    if (!work || !values?.length) return nothing;
    const allowed = work.allowedActions.includes('materials.settle');
    return html`<section aria-labelledby="material-outcomes-heading"><h4 id="material-outcomes-heading" tabindex="-1">${this.text('outcomes')}</h4>
      <p>${this.text('independent')}</p><ul>${values.map((value, index) => {
        const line = work.materials.find(item => item.lineId === value.lineId)!;
        const pending = value.state.startsWith('pending_'), missing = value.state === 'pending_recording' && value.quantity === null && value.confirmedQuantity === null;
        const draft = this.draft(value), changed = draft.revision !== value.revision;
        const quantity = taskQuantityInput(draft.quantity, line.precision);
        let reasonValid = true; try {taskText(draft.reason, TASK_TEXT_LIMITS.reason, true, true);} catch {reasonValid = false;}
        const amount = (quantity: string | null) => quantity === null ? this.text('notRecorded')
          : (this.language === 'es' ? quantity.replace('.', ',') : quantity) + ' ' + materialUnit(line.unitId, this.language, quantity);
        return html`<li data-material-intent=${value.intentId}><h5>${line.label || this.text('unreviewed')}</h5>
          <p>${materialUnit(line.unitId, this.language)} · ${materialSource(line.locationId, this.language)}</p>
          <p class="status" role="status">${this.text(value.state)}</p>
          <dl><dt>${this.text('planned')}</dt><dd>${amount(line.plannedQuantity)}</dd>
            <dt>${this.text('actual')}</dt><dd>${amount(value.quantity)}</dd>
            <dt>${this.text('confirmed')}</dt><dd>${value.state === 'not_used' ? this.text('noMovement')
              : value.confirmedQuantity === null ? this.text('notConfirmed') : amount(value.confirmedQuantity)}</dd></dl>
          ${pending && value.confirmedQuantity !== null && value.quantity !== value.confirmedQuantity
            ? html`<p>${this.text('pendingTotal')}: ${amount(value.quantity)}</p>` : nothing}
          ${value.pendingReason ? html`<p>${this.text(value.pendingReason as TaskMaterialMessage)}</p>` : nothing}
          ${pending && !allowed ? html`<p role="status">${this.text('denied')}</p>` : nothing}
          ${pending && changed ? html`<p role="alert">${this.text('changed')}</p>
            <vyp-ha-button .state=${buttonState({label:this.text('review')})} ?disabled=${this.disabled}
              @click=${() => this.change(value, {revision:value.revision})}></vyp-ha-button>` : nothing}
          ${missing ? html`<form novalidate @submit=${(event: SubmitEvent) => {event.preventDefault();
            if (!this.disabled && allowed && !changed && quantity !== null && reasonValid) this.settle(value, quantity, draft.reason);}}>
            <vyp-ha-field id=${'material-actual-' + index} .value=${draft.quantity} ?disabled=${this.disabled}
              .state=${textFieldState({label:this.text('actual'), inputMode:'decimal', maxLength:64, required:true,
                description:this.text(line.precision === 0 ? 'whole' : 'decimal'),
                error:draft.quantity !== '' && quantity === null ? this.text('invalidQuantity') : ''})}
              @ha-value-request=${(event: FieldValueEvent) => this.change(value, {quantity:event.detail.value})}></vyp-ha-field>
            <vyp-ha-field .value=${draft.reason} ?disabled=${this.disabled}
              .state=${textFieldState({label:this.text('reason'), maxLength:TASK_TEXT_LIMITS.reason * 2, required:true, description:this.text('reasonHelp')})}
              @ha-value-request=${(event: FieldValueEvent) => this.change(value, {reason:event.detail.value})}></vyp-ha-field>
            <vyp-ha-button .state=${buttonState({label:this.text('record'),variant:'primary'})} ?disabled=${this.disabled || !allowed || changed || quantity === null || !reasonValid}
              @click=${() => {if (!this.disabled && allowed && !changed && quantity !== null && reasonValid) this.settle(value, quantity, draft.reason);}}></vyp-ha-button>
          </form>` : pending && value.quantity !== null ? html`<vyp-ha-button
            .state=${buttonState({label:this.text('settle'),variant:'primary'})} ?disabled=${this.disabled || !allowed || changed}
            @click=${() => {if (!this.disabled && allowed && !changed) this.settle(value);}}></vyp-ha-button>` : nothing}
        </li>`;
      })}</ul></section>`;
  }
}
registerField(); registerButton();
customElements.define('domus-task-material-outcomes', DomusTaskMaterialOutcomes);
declare global {interface HTMLElementTagNameMap {'domus-task-material-outcomes': DomusTaskMaterialOutcomes;}}
