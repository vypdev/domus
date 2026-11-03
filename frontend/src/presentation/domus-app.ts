import {LitElement, css, html, nothing} from 'lit';
import {live} from 'lit/directives/live.js';
import type {PropertyValues} from 'lit';
import type {EntryView} from '../application/entry-controller';
import type {TaskView} from '../application/task-controller';
import './domus-tasks';
import type {AdministrationView} from '../application/administration-controller';
import './domus-administration';
import type {Deployment} from '../domain/entry';
import type {JournalRecord} from '../domain/journal';
import {instant, language, message} from './messages';
import type {Language, MessageKey} from './messages';
import {styles} from './styles';

export type EntryIntent = Readonly<{type: 'refresh' | 'request_membership' | 'logout' | 'sign_in' | 'reopen'}>
  | Readonly<{type: 'setup'; name: string; timeZone: string}>
  | Readonly<{type: 'recover' | 'dismiss'; key: string}>
  | Readonly<{type: 'language'; language: Language}>;

/** Owned rendering only; intents cross a semantic boundary and never grant command authority. */
export class DomusApp extends LitElement {
  static properties = {tasks: {attribute: false}, section: {attribute: false}, view: {attribute: false}, administration: {attribute:false}, deployment: {attribute: false}, language: {attribute: false},
    nameDraft: {state: true}, zoneDraft: {state: true}};
  static styles = [styles, css`.workspace-nav {display:flex;gap:12px;margin:20px 0}.workspace-nav a {display:inline-flex;align-items:center;min-height:44px;padding:8px 20px;
    border:1px solid var(--line);border-radius:999px;text-decoration:none;color:var(--accent);font-weight:650}.workspace-nav a[aria-current=page] {background:var(--accent);color:var(--surface);border-color:var(--accent)}`];
  declare view: EntryView | null;
  declare administration:AdministrationView|null;
  declare tasks: TaskView | null;
  declare section: 'tasks' | 'household';
  declare deployment: Deployment;
  declare language: Language;
  private declare nameDraft: string;
  private declare zoneDraft: string;
  private draftScope: string | null = null;
  constructor() {super(); this.view = null; this.administration=null; this.tasks = null; this.section = 'tasks'; this.deployment = 'standalone'; this.language = 'en'; this.nameDraft = ''; this.zoneDraft = '';}
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
    const decision = view?.decision, state = decision?.state ?? 'unavailable';
    const taskWorkspace = this.section === 'tasks' && this.tasks?.phase === 'ready' && this.tasks.access !== null;
    const unresolved = view?.journal?.records.some(record => record.stage === 'prepared' || record.stage === 'uncertain') === true;
    return html`<main><header><div class="brand"><svg class="logo" viewBox="0 0 48 48" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2.5">
      <path d="M8 23 24 9l16 14v16H8Z"/><path d="M19 39V25h10v14"/></svg><div><div class="wordmark">DOMUS</div><div class="tagline">${this.text('tagline')}</div></div></div>
      <label class="language">${this.text('language')}<select aria-label=${this.text('language')} .value=${this.language}
        @change=${(event: Event) => {this.language = language((event.target as HTMLSelectElement).value, 'en'); this.intent({type: 'language', language: this.language});}}>
        <option value="en">${this.text('english')}</option><option value="es">${this.text('spanish')}</option></select></label></header>
      <section aria-labelledby="entry-title" aria-busy=${loading || view!.busy}>
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
      ${decision?.state === 'active' || this.administration !== null || this.tasks !== null ? html`<nav class="workspace-nav" aria-label=${this.text('state_active')}>
        <a href="#tasks" aria-current=${this.section === 'tasks' ? 'page' : nothing}>${this.text('navigationTasks')}</a>
        <a href="#household" aria-current=${this.section === 'household' ? 'page' : nothing}>${this.text('navigationHousehold')}</a>
      </nav>` : nothing}
      <section ?hidden=${this.section !== 'tasks' || decision?.state !== 'active'}>
        <domus-tasks .view=${this.tasks} .language=${this.language}
          .retired=${closed || view?.notice === 'context_changed' || view?.phase === 'ready' && decision?.state !== 'active'}></domus-tasks>
      </section>
      <section ?hidden=${this.section !== 'household'}><domus-administration .view=${this.administration} .language=${this.language}
        .pending=${view?.busy===true&&(decision?.state==='active'||this.administration!==null)}
        .retired=${closed||view?.notice==='context_changed'||(view?.phase==='ready'&&decision?.state!=='active')}></domus-administration></section>
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
customElements.define('domus-app', DomusApp);
declare global {interface HTMLElementTagNameMap {'domus-app': DomusApp;}}
