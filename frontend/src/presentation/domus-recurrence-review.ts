import {LitElement, html, nothing} from 'lit';
import {keyed} from 'lit/directives/keyed.js';
import type {PropertyValues} from 'lit';
import type {ReviewView} from '../application/recurrence-review-controller';
import {ATTACHMENT_CHOICES, FOLD_CHOICES, VISIBILITIES} from '../domain/recurrence-review';
import type {ReviewDraft, ReviewKind, ReviewTarget} from '../domain/recurrence-review';
import {reviewMessage} from './recurrence-messages';
import type {ReviewMessage} from './recurrence-messages';
import type {Language} from './messages';
import {styles} from './styles';

export type ReviewIntent = Readonly<{type: 'open' | 'close' | 'apply'}>
  | Readonly<{type: 'preview'; draft: ReviewDraft}>
  | Readonly<{type: 'recover' | 'forget'; key: string}>;

export class DomusRecurrenceReview extends LitElement {
  static properties = {view: {attribute: false}, language: {attribute: false}, action: {state: true}};
  static styles = styles;
  declare view: ReviewView | null;
  declare language: Language;
  private declare action: ReviewKind | null;

  constructor() {super(); this.view = null; this.language = 'en'; this.action = null;}
  protected willUpdate(changed: PropertyValues<this>): void {
    if (changed.has('view') && changed.get('view')?.target !== this.view?.target) {
      this.action = this.view?.target?.actions[0] ?? null;
    }
  }
  private text(key: ReviewMessage): string {return reviewMessage(key, this.language);}
  private intent(detail: ReviewIntent): void {
    this.dispatchEvent(new CustomEvent('domus-review-intent', {detail: Object.freeze(detail), bubbles: true, composed: true}));
  }
  private button(label: ReviewMessage, type: 'open' | 'close' | 'apply', disabled: boolean) {
    return html`<button type="button" ?disabled=${disabled} @click=${() => this.intent({type})}>${this.text(label)}</button>`;
  }
  private select<T extends ReviewMessage>(label: ReviewMessage, options: readonly T[], selected: T) {
    return html`<label>${this.text(label)}<select name=${label}>
      ${options.map(value => html`<option value=${value} .selected=${value === selected}>${this.text(value)}</option>`)}
    </select></label>`;
  }
  private submit(event: SubmitEvent, kind: ReviewKind): void {
    event.preventDefault();
    const data = new FormData(event.currentTarget as HTMLFormElement);
    const value = (key: ReviewMessage) => String(data.get(key) ?? '');
    this.intent({type: 'preview', draft: {
      kind, date: value('date'), time: value('time'), zone: value('zone'), interval: value('interval'),
      visibility: (value('visibility') || 'at_completion') as ReviewDraft['visibility'],
      choice: (value('choice') || 'adopt') as ReviewDraft['choice'],
      fold: (value('fold') || 'first_instant') as ReviewDraft['fold'], reason: value('reason'), rrule: value('pattern'),
    }});
  }
  private form(target: ReviewTarget, kind: ReviewKind, disabled: boolean) {
    const schedule = target.schedule, relative = kind === 'attachment' || kind === 'relative-settings';
    const pattern = kind === 'fixed-pattern' || kind === 'fixed-replacement';
    const nominal = kind === 'attachment' || kind === 'reschedule' || pattern;
    const state = kind === 'state' || kind === 'fixed-state';
    const fieldsKey = JSON.stringify([target.occurrenceId, target.occurrenceRevision, schedule?.revision, kind]);
    return html`<form @submit=${(event: SubmitEvent) => this.submit(event, kind)}>
      <label>${this.text('action')}<select .value=${kind} @change=${(event: Event) => {this.action = (event.target as HTMLSelectElement).value as ReviewKind;}}>
        ${target.actions.map(action => html`<option value=${action} .selected=${action === kind}>${this.text(action)}</option>`)}
      </select></label>
      ${keyed(fieldsKey, html`
      ${state && schedule ? html`<p>${this.text(schedule.state)} · ${this.text(schedule.state === 'active' ? 'pause' : 'resume')}</p>` : nothing}
      ${nominal ? html`<label>${this.text('date')}<input type="date" name="date" .value=${schedule?.nominal.local.slice(0,10) ?? ''} required></label>` : nothing}
      ${nominal && schedule?.nominal.kind !== 'date' ? html`<label>${this.text('time')}<input type="time" step="0.001" name="time"
        .value=${schedule?.nominal.local.slice(11) ?? ''} ?required=${schedule?.nominal.kind === 'time'}></label>` : nothing}
      ${relative ? html`<label>${this.text('interval')}<input type="number" min="1" max="36600" name="interval" required .value=${String(schedule?.interval ?? 30)}></label>
        ${this.select('visibility', VISIBILITIES, schedule?.visibility ?? 'at_completion')}` : nothing}
      ${kind === 'attachment' ? html`<label>${this.text('zone')}<input name="zone" required maxlength="128" .value=${target.zone}></label>
        ${this.select('choice', ATTACHMENT_CHOICES, 'adopt')}${this.select('fold', FOLD_CHOICES, 'first_instant')}` : nothing}
      ${pattern ? html`<label>${this.text('pattern')}<input name="pattern" required maxlength="2048"></label>` : nothing}
      ${kind === 'reschedule' || kind === 'fixed-skip' || kind === 'fixed-replacement' ? html`<label>${this.text('reason')}<textarea name="reason" required maxlength="1000"></textarea></label>` : nothing}
      `)}
      <button type="submit" ?disabled=${disabled}>${this.text('preview')}</button>
    </form>`;
  }
  private dates(label: ReviewMessage, dates: readonly string[]) {
    return dates.length ? html`<ul aria-label=${this.text(label)}>${dates.map(date => html`<li>${date}</li>`)}</ul>` : nothing;
  }
  private result(value: NonNullable<ReviewView['result']>, disabled: boolean) {
    const {record, receipt} = value, plan = receipt.preview;
    const selection = record.command.selection;
    const body = selection.body;
    return html`<section aria-labelledby="recurrence-result">
      <h3 id="recurrence-result">${this.text(receipt.historical ? 'historical' : plan === null ? 'approved' : 'review')}</h3>
      <p>${this.text(selection.kind)}</p>
      ${plan !== null && !receipt.historical ? html`
        ${'target' in body ? html`<p>${this.text(body.target === 'paused' ? 'pause' : 'resume')}</p>` : nothing}
        ${'interval_days' in body ? html`<p>${this.text('interval')} ${body.interval_days} · ${this.text(body.visibility)}</p>` : nothing}
        ${'rrule' in body ? html`<p>${body.rrule}</p>` : nothing}
        ${'reason' in body ? html`<p>${body.reason}</p>` : nothing}
        ${plan.retained === null ? nothing : html`<p>${this.text('retained')} ${plan.retained}</p>`}
        ${this.dates('retained', plan.retainedDates)}
        ${plan.cancelled === null ? nothing : html`<p>${this.text('cancelled')} ${plan.cancelled}</p>`}
        ${this.dates('cancelled', plan.cancelledDates)}
        ${plan.planned === null ? nothing : html`<p>${this.text('planned')} ${plan.planned}</p>`}
        ${plan.replacementSlots.length ? html`<ul>${plan.replacementSlots.map(slot =>
          html`<li>${slot.local} · ${this.text(slot.replaces ? 'replacesWork' : 'addsWork')}</li>`)}</ul>` : nothing}
        ${plan.previous === null ? nothing : html`<p>${this.text('previous')} ${plan.previous}</p>`}
        ${plan.destination === null ? nothing : html`<p>${this.text('destination')} ${plan.destination}</p>`}
        ${plan.createsFirst === null ? nothing : html`<p>${this.text(plan.createsFirst ? 'creates' : 'keeps')}</p>`}
        ${this.button('apply', 'apply', disabled)}` : nothing}
      <details><summary>${this.text('technical')}</summary><p>${receipt.operationId}</p></details>
    </section>`;
  }
  protected render() {
    const view = this.view;
    if (view === null || !view.selected && view.records.length === 0 && !view.open) return nothing;
    const disabled = view.busy || view.readOnly || view.records.some(item => item.status === 'pending');
    return html`<section class="card" aria-labelledby="recurrence-title" aria-busy=${view.busy}>
      <h2 id="recurrence-title">${this.text('title')}</h2>
      ${view.open ? html`
        ${view.busy ? html`<p role="status">${this.text('waiting')}</p>` : nothing}
        ${view.readOnly ? html`<p>${this.text('readonly')}</p>` : nothing}
        ${view.result !== null ? this.result(view.result, disabled)
          : view.target && this.action ? this.form(view.target, this.action, disabled)
          : !view.busy ? html`<p>${this.text(view.selected ? 'none' : 'empty')}</p>` : nothing}
        ${view.result && view.selected ? this.button('again', 'open', view.busy) : nothing}
        ${this.button('close', 'close', view.busy)}` : this.button('open', 'open', view.busy)}
      ${view.notice === null ? nothing : html`<p role="alert">${this.text(view.notice)}</p>`}
      ${view.records.length === 0 ? nothing : html`<details ?open=${view.records.some(item => item.status === 'pending')}>
        <summary>${this.text('operations')}</summary><ul>${view.records.map(item => html`<li>${this.text(item.command.selection.kind)}
          <button type="button" ?disabled=${view.busy} @click=${() => this.intent({type: 'recover', key: item.key})}>${this.text('recover')}</button>
          ${item.status === 'received' ? html`<button type="button" ?disabled=${view.busy}
            @click=${() => this.intent({type: 'forget', key: item.key})}>${this.text('forget')}</button>` : nothing}
        </li>`)}</ul></details>`}
    </section>`;
  }
}
customElements.define('domus-recurrence-review', DomusRecurrenceReview);
declare global {interface HTMLElementTagNameMap {'domus-recurrence-review': DomusRecurrenceReview;}}
