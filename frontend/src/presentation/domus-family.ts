import {LitElement, css, html, nothing} from 'lit';
import type {PropertyValues} from 'lit';
import {registerCard} from '@vypdev/ha-ui/card';
import {cardState} from '@vypdev/ha-ui/card-contracts';
import {registerButton} from '@vypdev/ha-ui/button';
import {buttonState} from '@vypdev/ha-ui/button-contracts';
import {registerFeedback} from '@vypdev/ha-ui/feedback';
import {feedbackState} from '@vypdev/ha-ui/feedback-contracts';
import type {FamilyPeriod, FamilyView} from '../application/family-controller';
import {displayPoints} from '../domain/point-allocation';
import {allocationDetails} from './allocation-details';
import type {ParticipantName} from './allocation-details';
import {civilDate, DATE_MAX, DATE_MIN} from '../domain/calendar';
import {familyMessage} from './family-messages';
import type {FamilyMessage} from './family-messages';
import type {Language} from './messages';

export type FamilyIntent = {readonly type: 'refresh' | 'more'}
  | {readonly type: 'period'; readonly mode: FamilyPeriod; readonly anchor: string};

export class DomusFamily extends LitElement {
  static properties = {names: {attribute: false}, view: {attribute: false}, language: {attribute: false}, today: {attribute: false},
    scopeKey: {attribute: false}, mode: {state: true}, anchor: {state: true}};
  static styles = css`
    :host {display:grid;gap:16px;--vyp-ha-surface:var(--surface);--vyp-ha-text:var(--text);
      --vyp-ha-text-secondary:var(--muted);--vyp-ha-border:var(--line);--vyp-ha-primary:var(--accent)}
    form {display:flex;align-items:end;flex-wrap:wrap;gap:12px;margin-block-end:16px}
    label {display:grid;gap:4px;font-weight:650} input,select {font:inherit;color:inherit;background:var(--surface);
      padding:8px;border:1px solid var(--line);border-radius:8px;max-width:100%}
    dl {display:grid;grid-template-columns:minmax(0,2fr) minmax(0,1fr);gap:8px 16px;margin:0}
    dd {margin:0} dt {color:var(--muted)} dl,li {overflow-wrap:anywhere}
    ol {list-style:none;padding:0;margin:0 0 16px} li+li {border-block-start:1px solid var(--line);margin-block-start:12px;padding-block-start:12px}
    li p {margin:0 0 8px} h2 {margin:0} :focus-visible {outline:3px solid var(--accent);outline-offset:3px}
  `;
  declare names: readonly ParticipantName[];
  declare view: FamilyView | null;
  declare language: Language;
  declare today: string;
  declare scopeKey: string | null;
  private declare mode: FamilyPeriod;
  private declare anchor: string;

  constructor() {
    super(); this.names = []; this.view = null; this.language = 'en'; this.today = DATE_MIN; this.scopeKey = null;
    this.mode = 'week'; this.anchor = DATE_MIN;
  }

  protected willUpdate(changed: PropertyValues<this>): void {
    if (changed.has('scopeKey')) {this.mode = 'week'; this.anchor = this.today;}
  }

  private text(key: FamilyMessage): string {return familyMessage(key, this.language);}

  private intent(detail: FamilyIntent): void {
    this.dispatchEvent(new CustomEvent('domus-family-intent', {detail, bubbles: true, composed: true}));
  }

  private period(event: SubmitEvent): void {
    event.preventDefault();
    if (civilDate(this.anchor)) this.intent({type: 'period', mode: this.mode, anchor: this.anchor});
  }

  private points(minor: number, precision: 0 | 2 = 2): string {
    return displayPoints(minor, this.language, precision);
  }

  protected render() {
    if (this.scopeKey === null) return nothing;
    const report = this.view?.report;
    const loading = this.view?.state === 'loading';
    const unavailable = this.view?.state === 'unavailable';
    const retry = html`<vyp-ha-button .state=${buttonState({label: this.text('refresh'), variant: 'outlined'})}
      ?disabled=${loading} @ha-press-request=${() => this.intent({type: 'refresh'})}></vyp-ha-button>`;
    const form = html`<form @submit=${this.period}>
      <label>${this.text('period')}<select .value=${this.mode} @change=${(e: Event) => {
        this.mode = (e.target as HTMLSelectElement).value as FamilyPeriod;
      }}><option value="week">${this.text('week')}</option><option value="month">${this.text('month')}</option></select></label>
      <label>${this.text('workDate')}<input type="date" required min=${DATE_MIN} max=${DATE_MAX}
        .value=${this.anchor} @input=${(e: Event) => {this.anchor = (e.target as HTMLInputElement).value;}}></label>
      <vyp-ha-button type="submit" .state=${buttonState({label: this.text('apply'), variant: 'primary'})}></vyp-ha-button>
    </form>`;
    const card = (key: FamilyMessage) => cardState({title: this.text(key), headingLevel: 3});
    const day = (value: number) => new Intl.DateTimeFormat(this.language,
      {timeZone: 'UTC', dateStyle: 'medium'}).format(value);
    const date = (value: number) => new Intl.DateTimeFormat(this.language,
      {timeZone: report!.zone, dateStyle: 'medium', timeStyle: 'short'}).format(value);
    return html`<h2>${this.text('title')}</h2>
      ${loading ? html`<vyp-ha-feedback .state=${feedbackState({kind: 'loading', message: this.text('loading')})}></vyp-ha-feedback>` : nothing}
      ${unavailable ? html`<vyp-ha-feedback .state=${feedbackState({kind: 'notice', tone: 'warning',
        title: this.text('unavailable'), message: this.text(report ? 'stale' : 'unavailableHelp')})}></vyp-ha-feedback>` : nothing}
      ${report ? html`
        <vyp-ha-card .state=${card('balance')}><dl>
          <dt>${this.text('available')}</dt><dd>${this.points(report.available)}</dd>
          <dt>${this.text('posted')}</dt><dd>${this.points(report.posted)}</dd>
          <dt>${this.text('reserved')}</dt><dd>${this.points(report.reserved)}</dd>
        </dl>${report.posted < 0 ? html`<p>${this.text('negative')}</p>` : nothing}</vyp-ha-card>` : nothing}
      <vyp-ha-card .state=${card('participation')}>${form}
        ${report ? html`<p>${day(Date.parse(report.period.start))} – ${day(Date.parse(report.period.end) - 86_400_000)} · ${report.zone}</p><dl>
          <dt>${this.text('earned')}</dt><dd>${this.points(report.earned)}</dd>
          <dt>${this.text('verification')}</dt><dd>${this.points(report.pendingVerification)}</dd>
          <dt>${this.text('posting')}</dt><dd>${this.points(report.pendingPosting)}</dd>
          <dt>${this.text('completed')}</dt><dd>${report.completed}</dd>
          <dt>${this.text('effort')}</dt><dd>${report.tracked === 0 ? this.text('unknownEffort')
            : html`${Math.round(report.elapsed / 60_000)} ${this.text('minutes')}
              <small>(${report.tracked}/${report.completed} ${this.text('tracked')})</small>`}</dd>
        </dl>` : nothing}
      </vyp-ha-card>
      ${report && report.pending.length > 0 ? html`<vyp-ha-card .state=${card('pendingWork')}>
        ${report.pendingCount > report.pending.length
          ? html`<p>${this.text('pendingShown')} (${report.pending.length}/${report.pendingCount})</p>` : nothing}
        <ol>${report.pending.map(entry => html`<li>
          <p><strong>${this.text(entry.state === 'verification' ? 'awaitingVerification' : 'awaitingPosting')}</strong>
            · ${entry.title}</p><dl><dt>${this.text('workDate')}</dt><dd>${date(entry.performedAt)}</dd></dl>
          <details><summary>${this.text('allocation')}</summary>
            ${allocationDetails(entry.allocation, this.language, this.names, true)}</details>
        </li>`)}</ol>
      </vyp-ha-card>` : nothing}
      ${report ? html`<vyp-ha-card .state=${card('history')}>
        ${report.history.length === 0 ? html`<p>${this.text('empty')}</p>` : html`<ol>${report.history.map(entry => html`
          <li><p><strong>${this.text(entry.reverses === null ? 'award' : 'reversal')} ${this.points(entry.amount)}</strong>
            · ${entry.title}</p><dl>
            <dt>${this.text('workDate')}</dt><dd>${date(entry.performedAt)}</dd>
            ${entry.verifiedAt === null ? nothing : html`<dt>${this.text('approved')}</dt><dd>${date(entry.verifiedAt)}</dd>`}
            <dt>${this.text('postingDate')}</dt><dd>${date(entry.postedAt)}</dd>
            ${entry.reverses === null ? nothing : html`<dt>${this.text('reversedEntry')}</dt><dd><code>${entry.reverses}</code></dd>`}
          </dl><details>
            <summary>${this.text('allocation')}</summary>
${allocationDetails(entry.allocation, this.language, this.names)}
          </details></li>`)}</ol>`}
        ${report.cursor === null ? nothing : html`<vyp-ha-button .state=${buttonState({label: this.text('more'), variant: 'outlined'})}
          ?disabled=${loading} @ha-press-request=${() => this.intent({type: 'more'})}></vyp-ha-button>`}
      </vyp-ha-card>` : nothing}
      ${report && report.spendingCount > 0 ? html`<vyp-ha-card .state=${card('spending')}>
        <p>${this.text('spendingTotal')} ${this.points(report.spentInPeriod)}</p>
        ${report.spendingCount > report.spending.length
          ? html`<p>${this.text('spendingShown')} (${report.spending.length}/${report.spendingCount})</p>` : nothing}
        <ol>${report.spending.map(entry => html`<li><strong>${this.points(-entry.cost)} · ${entry.title}</strong>
          <p>${this.text('postingDate')} ${date(entry.postedAt)} · <code>${entry.redemptionId}</code></p></li>`)}</ol>
      </vyp-ha-card>` : nothing}
      <div>${retry}</div>`;
  }
}

registerCard(); registerButton(); registerFeedback();
customElements.define('domus-family', DomusFamily);
declare global {interface HTMLElementTagNameMap {'domus-family': DomusFamily;}}
