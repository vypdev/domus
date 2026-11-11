import {LitElement, css, html, nothing} from 'lit';
import {registerButton} from '@vypdev/ha-ui/button';
import {buttonState} from '@vypdev/ha-ui/button-contracts';
import {registerCard} from '@vypdev/ha-ui/card';
import {cardState} from '@vypdev/ha-ui/card-contracts';
import {registerFeedback} from '@vypdev/ha-ui/feedback';
import {feedbackState} from '@vypdev/ha-ui/feedback-contracts';
import type {TaskOverviewDeadline, TaskOverviewGroup, TaskOverviewView} from '../application/task-overview';
import type {Language} from './messages';
import {taskDay, taskMessage} from './task-messages';
import type {TaskMessageKey} from './task-messages';

type OverviewIntent = {readonly type: 'refresh'} | {readonly type: 'select'; readonly occurrenceId: string};

export class DomusTaskOverview extends LitElement {
  static properties = {view: {attribute: false}, language: {attribute: false}};
  static styles = css`
    :host {--vyp-ha-surface:var(--surface);--vyp-ha-surface-raised:var(--surface);--vyp-ha-text:var(--text);
      --vyp-ha-text-secondary:var(--muted);--vyp-ha-border:var(--line);--vyp-ha-primary:var(--accent);
      --vyp-ha-focus-ring:3px solid var(--accent)}
    section {margin-block-start:20px} h2 {margin-block:0 12px}
    .groups {display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,16rem),1fr));gap:12px}
    vyp-ha-card::part(heading) {text-wrap:balance}
    ul {list-style:none;margin:0;padding:0} li+li {border-block-start:1px solid var(--line)}
    vyp-ha-button {--vyp-ha-button-padding:8px}
    vyp-ha-feedback + vyp-ha-button {margin-block-start:8px}
  `;

  declare view: TaskOverviewView | null;
  declare language: Language;

  constructor() {super(); this.view = null; this.language = 'en';}

  private text(key: TaskMessageKey): string {return taskMessage(key, this.language);}

  private intent(detail: OverviewIntent): void {
    this.dispatchEvent(new CustomEvent<OverviewIntent>('domus-task-overview-intent', {
      detail, bubbles: true, composed: true,
    }));
  }

  private deadlineLabel(deadline: TaskOverviewDeadline): string {
    return deadline.day === null
      ? new Intl.DateTimeFormat(this.language,
        {dateStyle: 'medium', timeStyle: 'short', timeZone: deadline.zone}).format(deadline.instant)
      : taskDay(deadline.day, this.language);
  }

  private group(key: 'overviewAssigned' | 'overviewUnclaimed' | 'overviewDueToday' | 'overviewOverdue' | 'overviewMaintenance',
    group: TaskOverviewGroup) {
    const total = new Intl.NumberFormat(this.language).format(group.total);
    return html`<vyp-ha-card .state=${cardState({title: this.text(key) + ' · ' + total, headingLevel: 3})}>
      ${group.total === 0 ? html`<p>${this.text('overviewEmpty')}</p>` : html`<ul>${group.items.map(item => {
        const title = item.title.replace(/[\u007f-\u009f]/gu, ' ');
        const state = this.text(`state_${item.state}`);
        const label = item.deadline === undefined ? title + ' · ' + state
          : title + ' · ' + this.deadlineLabel(item.deadline) + ' · ' + state;
        return html`<li><vyp-ha-button .state=${buttonState({label, variant: 'plain'})}
          @ha-press-request=${() => this.intent({type: 'select', occurrenceId: item.id})}></vyp-ha-button></li>`;
      })}</ul>`}
      ${group.total > group.items.length ? html`<p>${this.text('overviewMore')}</p>` : nothing}
    </vyp-ha-card>`;
  }

  protected render() {
    const view = this.view;
    if (view === null) return nothing;
    return html`<section aria-labelledby="overview-task-title">
      <h2 id="overview-task-title">${this.text('overviewHeading')}</h2>
      ${view.state === 'ready' ? html`<div class="groups">
        ${this.group('overviewOverdue', view.data.overdue)}
        ${this.group('overviewDueToday', view.data.dueToday)}
        ${this.group('overviewMaintenance', view.data.upcomingMaintenance)}
        ${this.group('overviewAssigned', view.data.assigned)}
        ${this.group('overviewUnclaimed', view.data.unclaimed)}
      </div>` : html`<vyp-ha-feedback .state=${view.state === 'loading'
        ? feedbackState({kind: 'loading', message: this.text('overviewLoading')})
        : feedbackState({kind: 'notice', tone: 'warning',
          message: this.text(view.state === 'denied' ? 'overviewDenied' : 'overviewUnavailable')})}></vyp-ha-feedback>
        ${view.state === 'unavailable' ? html`<vyp-ha-button
          .state=${buttonState({label: this.text('overviewRetry'), variant: 'outlined'})}
          @ha-press-request=${() => this.intent({type: 'refresh'})}></vyp-ha-button>` : nothing}`}
    </section>`;
  }
}

registerButton(); registerCard(); registerFeedback();
customElements.define('domus-task-overview', DomusTaskOverview);
declare global {interface HTMLElementTagNameMap {'domus-task-overview': DomusTaskOverview;}}
