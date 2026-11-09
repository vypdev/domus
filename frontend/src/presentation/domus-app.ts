import {LitElement, html, nothing} from 'lit';
import {guard} from 'lit/directives/guard.js';
import {live} from 'lit/directives/live.js';
import {navigationState} from '@vypdev/ha-ui/contracts';
import {registerTabs} from '@vypdev/ha-ui/tabs';
import type {NavigationSelectionEvent} from '@vypdev/ha-ui/tabs';
import type {PropertyValues} from 'lit';
import type {EntryView} from '../application/entry-controller';
import type {TaskView} from '../application/task-controller';
import './domus-tasks';
import './domus-calendar';
import type {CalendarPreferenceView} from '../application/calendar-preferences';
import './domus-recurrence-review';
import type {ReviewView} from '../application/recurrence-review-controller';
import type {CalendarView} from '../application/calendar-controller';
import {DATE_MIN} from '../domain/calendar';
import type {AdministrationView} from '../application/administration-controller';
import './domus-administration';
import type {Deployment} from '../domain/entry';
import type {JournalRecord} from '../domain/journal';
import {instant, language, message} from './messages';
import type {Language, MessageKey} from './messages';
import {styles} from './styles';

export type WorkspaceDestination = 'overview' | 'tasks' | 'calendar' | 'household';

export type EntryIntent = Readonly<{type: 'refresh' | 'request_membership' | 'logout' | 'sign_in' | 'reopen'}>
  | Readonly<{type: 'setup'; name: string; timeZone: string}>
  | Readonly<{type: 'recover' | 'dismiss'; key: string}>
  | Readonly<{type: 'language'; language: Language}>;

/** Owned rendering only; intents cross a semantic boundary and never grant command authority. */
export class DomusApp extends LitElement {
  static properties = {recurrenceReview: {attribute:false}, calendar: {attribute:false}, calendarPreference: {attribute:false}, calendarScopeKey: {attribute:false}, calendarToday: {attribute:false}, tasks: {attribute: false}, view: {attribute: false}, administration: {attribute:false}, deployment: {attribute: false}, language: {attribute: false},
    workspaceDestination: {attribute: false}, nameDraft: {state: true}, zoneDraft: {state: true}};
  static styles = styles;
  declare view: EntryView | null;
  declare administration:AdministrationView|null;
  declare tasks: TaskView | null;
  declare calendar: CalendarView | null;
  declare recurrenceReview: ReviewView | null;
  declare calendarPreference: CalendarPreferenceView | null;
  declare calendarScopeKey: string | null;
  declare calendarToday: string;
  declare deployment: Deployment;
  declare language: Language;
  declare workspaceDestination: WorkspaceDestination | null;
  private declare nameDraft: string;
  private declare zoneDraft: string;
  private draftScope: string | null = null;
  private focusDestination: WorkspaceDestination | null = null;
  constructor() {
    super(); this.view = null; this.administration = null; this.tasks = null; this.deployment = 'standalone'; this.language = 'en';
    this.recurrenceReview = null; this.calendar = null; this.calendarPreference = null; this.calendarScopeKey = null; this.calendarToday = DATE_MIN;
    this.workspaceDestination = null; this.nameDraft = ''; this.zoneDraft = '';
  }
  disconnectedCallback(): void {super.disconnectedCallback(); this.dispatchEvent(new Event('domus-detached'));}
  private text(key: MessageKey): string {return message(key, this.language);}
  private intent(detail: EntryIntent): void {
    this.dispatchEvent(new CustomEvent<EntryIntent>('domus-intent', {detail: Object.freeze(detail), bubbles: true, composed: true}));
  }
  protected willUpdate(changed: PropertyValues<this>): void {
    if (!changed.has('view')) return;
    const context = this.view?.session?.context;
    const scope = context ? `${context.installationId}:${context.channel}:${context.subject}` : null;
    if (this.view?.phase === 'closed' || (scope !== null && this.draftScope !== null && scope !== this.draftScope)) {
      this.nameDraft = ''; this.zoneDraft = ''; this.draftScope = null;
    }
    if (this.view?.phase !== 'closed' && scope !== null) this.draftScope = scope;
  }
  protected updated(changed: PropertyValues<this>): void {
    this.lang = this.language;
    if (changed.has('view') && this.view?.fields.length)
      this.shadowRoot?.querySelector<HTMLInputElement>('#' + this.view.fields[0])?.focus();
    const destination = this.hasWorkspace() ? this.workspaceDestination : null;
    if (destination !== this.focusDestination) {
      this.focusDestination = destination;
      if (destination !== null) this.focusWorkspace(destination);
    }
  }
  private hasWorkspace(): boolean {
    return this.view?.decision?.state === 'active' && this.view.phase !== 'closed' &&
      this.view.notice !== 'context_changed' && (this.view.busy || this.administration !== null || this.tasks !== null);
  }
  private focusWorkspace(destination: WorkspaceDestination): void {
    this.renderRoot.querySelector<HTMLElement>('#' + destination)!.focus();
  }
  private repeatWorkspaceSelection(event: NavigationSelectionEvent): void {
    const destination = this.workspaceDestination;
    if (destination !== null && event.detail.kind === 'navigation' && event.detail.id === destination) {
      // A same-fragment activation has no hashchange. Keep native behavior for all other links.
      event.preventDefault();
      this.focusWorkspace(destination);
    }
  }
  private workspaceNavigation() {
    const state = navigationState({
      kind: 'navigation', label: this.text('workspaceNavigation'), selected: this.workspaceDestination ?? 'overview',
      scrollStartLabel: this.text('workspaceScrollStart'), scrollEndLabel: this.text('workspaceScrollEnd'),
      items: [
        {id: 'overview', href: '#overview', label: this.text('workspaceOverview'),
          iconPath: 'M3 3h8v8H3zM13 3h8v8h-8zM3 13h8v8H3zM13 13h8v8h-8z'},
        {id: 'tasks', href: '#tasks', label: this.text('navigationTasks'),
          iconPath: 'M3 3h18v18H3zM7 12l3 3 7-7'},
        {id: 'calendar', href: '#calendar', label: this.text('navigationCalendar'),
          iconPath: 'M3 5h18v16H3zM3 10h18M7 2v5M17 2v5'},
        {id: 'household', href: '#household', label: this.text('workspaceHousehold'),
          iconPath: 'M3 11l9-8 9 8v10h-6v-7H9v7H3z'},
      ],
    });
    return html`<vyp-ha-tabs class="workspace-nav" .state=${state}
      @ha-selection-request=${this.repeatWorkspaceSelection}></vyp-ha-tabs>`;
  }
  private button(key: MessageKey, type: 'refresh' | 'request_membership' | 'logout' | 'sign_in' | 'reopen', primary = false) {
    return html`<button type="button" class=${primary ? 'primary' : ''}
      ?disabled=${(this.view?.phase !== 'closed' && this.view?.busy === true) || (type === 'request_membership' && this.view?.journal === null)}
      @click=${() => this.intent({type})}>${this.text(key)}</button>`;
  }
  private setup() {
    const invalid = this.view!.fields;
    return html`<section class="card" aria-labelledby="mapping-title"><h2 id="mapping-title">${this.text('mappingTitle')}</h2>
      <p>${this.text('mappingBody')}</p><p class="help">${this.text('setupImpact')}</p>
      <form novalidate @submit=${(event: SubmitEvent) => {event.preventDefault(); this.intent({type: 'setup', name: this.nameDraft, timeZone: this.zoneDraft});}}>
        ${(['name', 'time_zone'] as const).map(field => html`<div class="field"><label for=${field}>${this.text(field)}</label>
          <input id=${field} name=${field} type="text" autocomplete="off" maxlength=${field === 'name' ? 320 : 256}
            .value=${live(field === 'name' ? this.nameDraft : this.zoneDraft)} ?disabled=${this.view!.busy}
            aria-invalid=${invalid.includes(field) ? 'true' : 'false'} aria-describedby=${field + '-help' + (invalid.includes(field) ? ' ' + field + '-error' : '')}
            @input=${(event: InputEvent) => {const value = (event.target as HTMLInputElement).value;
              if (field === 'name') this.nameDraft = value; else this.zoneDraft = value;}}>
          <small id=${field + '-help'}>${this.text(field === 'name' ? 'nameHelp' : 'zoneHelp')}</small>
          ${invalid.includes(field) ? html`<p class="error" id=${field + '-error'} role="alert">${this.text(`field_${field}`)}</p>` : nothing}</div>`)}
        <div class="actions"><button class="primary" type="submit" ?disabled=${this.view!.busy || this.view!.journal === null}>${this.text('create')}</button></div>
      </form></section>`;
  }
  private outcome() {
    const result = this.view?.outcome;
    if (!result) return nothing;
    const stage = result.kind === 'receipt' ? result.stage : result.kind;
    const body = stage === 'committed' ? 'committedBody' : stage === 'historical' ? 'historicalBody'
      : stage === 'uncertain' ? 'uncertainBody' : 'rejectedBody';
    return html`<section class="note" role="status"><h2>${this.text(`outcome_${stage}`)}</h2><p>${this.text(body)}</p>
      ${result.kind === 'receipt' ? html`<p><small>${this.text('operation')}: <code>${result.operationId}</code></small></p>` : nothing}
      ${result.kind === 'rejected' ? html`<p>${this.text(`error_${result.reason}`)}</p>
        ${result.correlationId ? html`<p><small>${this.text('correlation')}: <code>${result.correlationId}</code></small></p>` : nothing}` : nothing}</section>`;
  }
  private request(record: JournalRecord) {
    return html`<li><div class="request-title"><span>${this.text(record.action === 'setup' ? 'setupRequest' : 'enrollRequest')}</span>
      <span>${this.text(`stage_${record.stage}`)}</span></div>
      <p class="help">${this.text('requestDeadline')}: ${instant(record.expiresAt, this.language)}</p>
      ${record.operationId ? html`<p><small>${this.text('operation')}: <code>${record.operationId}</code></small></p>` : nothing}
      <div class="actions">${record.stage !== 'rejected' ? html`<button type="button" ?disabled=${this.view!.busy}
        @click=${() => this.intent({type: 'recover', key: record.key})}>${this.text('check')}</button>` : nothing}
      ${record.stage !== 'prepared' && record.stage !== 'uncertain' ? html`<button type="button" ?disabled=${this.view!.busy}
        @click=${() => this.intent({type: 'dismiss', key: record.key})}>${this.text('dismiss')}</button>` : nothing}</div></li>`;
  }
  protected render() {
    const view = this.view, closed = view?.phase === 'closed';
    const loading = view === null || view.phase === 'idle' || view.phase === 'loading' || view.phase === 'sending';
    const workspace = this.hasWorkspace();
    const decision = view?.decision, state = decision?.state ?? 'unavailable';
    const taskWorkspace = workspace && this.workspaceDestination === 'tasks' && this.tasks?.phase === 'ready' && this.tasks.access !== null;
    const unresolved = view?.journal?.records.some(record => record.stage === 'prepared' || record.stage === 'uncertain') === true;
    return html`<main><header><div class="brand"><svg class="logo" viewBox="0 0 48 48" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2.5">
      <path d="M8 23 24 9l16 14v16H8Z"/><path d="M19 39V25h10v14"/></svg><div><div class="wordmark">DOMUS</div><div class="tagline">${this.text('tagline')}</div></div></div>
      <label class="language">${this.text('language')}<select aria-label=${this.text('language')} .value=${this.language}
        @change=${(event: Event) => {this.language = language((event.target as HTMLSelectElement).value, 'en'); this.intent({type: 'language', language: this.language});}}>
        <option value="en">${this.text('english')}</option><option value="es">${this.text('spanish')}</option></select></label></header>
      ${workspace ? guard([this.language, this.workspaceDestination], () => this.workspaceNavigation()) : nothing}
      <section id="overview" tabindex="-1" aria-labelledby="entry-title" aria-busy=${loading || view!.busy}>
        <div class="eyebrow">${view?.session ? this.text(view.session.context.channel === 'stable' ? 'stable' : 'edge') : 'Domus'}</div>
        <h1 id="entry-title">${taskWorkspace && !closed && !loading && view?.household ? view.household.name : this.text(closed ? 'closed' : loading ? 'loading' : `state_${state}`)}</h1>
        ${!taskWorkspace || closed || loading ? html`<p class="intro" role="status" aria-live="polite">${this.text(closed ? 'closedBody' : loading ? 'loadingBody' : `body_${state}`)}</p>` : nothing}
        ${view?.session && !taskWorkspace ? html`<span class="badge">${this.text('verified')}</span><span class="badge">${this.text(view.session.access === 'read_only' ? 'readOnly' : 'full')}</span>` : nothing}
        ${decision?.readOnly ? html`<div class="note warning"><h2>${this.text('readOnly')}</h2><p>${this.text('grace')}</p>
          <p><strong>${this.text('deadline')}:</strong> ${instant(view!.session!.expiresAt, this.language)}</p></div>` : nothing}
        ${view?.notice ? html`<p class="note" role="status">${this.text(`notice_${view.notice}`)}</p>` : nothing}
        ${view?.cleanup === 'unconfirmed' ? html`<p class="note warning" role="alert">${this.text('cleanup')}</p>` : nothing}
        ${taskWorkspace && view?.outcome?.kind === 'receipt' && view.outcome.stage === 'committed'
          ? html`<details><summary>${this.text('outcome_committed')}</summary>${this.outcome()}</details>` : this.outcome()}
        ${!loading && !closed && decision?.action === 'create_household' ? this.setup() : nothing}
        ${!loading && !closed && !taskWorkspace && view?.household ? html`<section class="card"><h2>${this.text('state_active')}</h2><dl>
          <dt>${this.text('householdName')}</dt><dd>${view.household.name}</dd><dt>${this.text('householdZone')}</dt><dd>${view.household.timeZone}</dd>
          <dt>${this.text('revision')}</dt><dd>${view.household.revision}</dd></dl></section>` : nothing}
        <div class="actions">${closed ? this.button(this.deployment === 'native' ? 'reopen' : 'signIn', this.deployment === 'native' ? 'reopen' : 'sign_in', true)
          : !loading && decision?.action === 'sign_in' ? this.button('signIn', 'sign_in', true)
          : !loading && decision?.action === 'reopen_home_assistant' ? this.button('reopen', 'reopen', true)
          : !loading ? html`${decision?.action === 'request_membership' ? this.button('join', 'request_membership', true) : nothing}
            ${!taskWorkspace ? this.button('refresh', 'refresh', decision?.action === 'refresh') : nothing}` : nothing}</div>
        ${!loading && decision?.action === 'contact_administrator' ? html`<p class="help">${this.text('contact')}</p>` : nothing}
        ${!closed && view?.busy ? html`<p class="busy" role="status">${this.text('busy')}</p>` : nothing}
      </section>
      <section id="tasks" tabindex="-1" aria-label=${this.text('navigationTasks')}
        ?hidden=${!workspace || this.workspaceDestination !== 'tasks'}>
        <domus-tasks .view=${this.tasks} .language=${this.language}
          .retired=${closed || view?.notice === 'context_changed' || view?.phase === 'ready' && decision?.state !== 'active'}></domus-tasks>
        <domus-recurrence-review .view=${this.recurrenceReview} .language=${this.language}></domus-recurrence-review>
      </section>
      <section id="calendar" tabindex="-1" aria-label=${this.text('navigationCalendar')}
        ?hidden=${!workspace || this.workspaceDestination !== 'calendar'}>
        <domus-calendar .preference=${this.calendarPreference} .view=${this.calendar} .language=${this.language} .today=${this.calendarToday}
          .scopeKey=${this.calendarScopeKey} .categories=${this.tasks?.access?.categoryCatalog?.categories}></domus-calendar>
      </section>
      <div id="household" tabindex="-1" ?hidden=${!workspace || this.workspaceDestination !== 'household'} role=${workspace ? 'group' : nothing}
        aria-label=${workspace ? this.text('workspaceHousehold') : nothing}>
        <domus-administration .view=${this.administration} .language=${this.language}
          .pending=${view?.busy===true&&(decision?.state==='active'||this.administration!==null)}
          .retired=${closed||view?.notice==='context_changed'||(view?.phase==='ready'&&decision?.state!=='active')}></domus-administration>
      </div>
      ${view?.journal?.records.length ? taskWorkspace && !unresolved
        ? html`<details><summary>${this.text('journalTitle')}</summary><p class="help">${this.text('journalBody')}</p><ul class="requests">${view.journal.records.map(record => this.request(record))}</ul></details>`
        : html`<section class="card" aria-labelledby="requests-title"><h2 id="requests-title">${this.text('journalTitle')}</h2>
          <p class="help">${this.text('journalBody')}</p><ul class="requests">${view.journal.records.map(record => this.request(record))}</ul></section>` : nothing}
      ${view?.session ? html`<details><summary>${this.text('details')}</summary><dl><dt>${this.text('status')}</dt><dd>${this.text(`state_${state}`)}</dd>
        <dt>${this.text('access')}</dt><dd>${this.text(view.session.access === 'read_only' ? 'readOnly' : 'full')}</dd></dl>
        <h2>${this.text('permissions')}</h2>${view.authorization?.permissions.length ? html`<ul>${view.authorization.permissions.map(permission => html`<li><code>${permission}</code></li>`)}</ul>`
          : html`<p>${this.text('noPermissions')}</p>`}</details>` : nothing}
      ${!closed && view?.session ? html`<footer>${this.button(this.deployment === 'native' ? 'leave' : 'logout', 'logout')}</footer>` : nothing}
    </main>`;
  }
}
registerTabs();
customElements.define('domus-app', DomusApp);
declare global {interface HTMLElementTagNameMap {'domus-app': DomusApp;}}
