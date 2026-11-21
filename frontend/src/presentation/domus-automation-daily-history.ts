import {LitElement, css, html, nothing} from 'lit';
import {repeat} from 'lit/directives/repeat.js';
import {registerButton} from '@vypdev/ha-ui/button';
import {buttonState} from '@vypdev/ha-ui/button-contracts';
import {registerCard} from '@vypdev/ha-ui/card';
import {cardState} from '@vypdev/ha-ui/card-contracts';
import {registerFeedback} from '@vypdev/ha-ui/feedback';
import {feedbackState} from '@vypdev/ha-ui/feedback-contracts';
import type {DailyHistoryView, ScheduledAutomationRun} from '../application/automation-daily-history';
import type {AutomationRunHistoryIntent} from '../application/automation-run-history';
import type {Language} from './messages';

const COPY = {
  en: {
    heading: 'Daily run history', open: 'Show daily history', close: 'Hide daily history',
    loading: 'Loading scheduled runs…', empty: 'No scheduled run has been admitted for this rule.',
    unavailable: 'The daily history is temporarily unavailable.', retry: 'Try again',
    readDenied: 'Your current permissions do not allow this history.', expired: 'This page has expired. Load recent runs.',
    older: 'Older daily runs', latest: 'Recent daily runs', revision: 'Revision',
    queued: 'Admitted and waiting.', created: 'Task created.', no_task: 'Conditions did not match. No task was created.',
    cancelled: 'Cancelled before creating a task.', denied: 'The run could not be authorized. No task was created.',
    historical: 'Record from before restoration.', historicalQueued: 'This historical admission is not current queued work.',
    historicalAdmission: 'Admitted before restoration.',
    requested: 'Requested local time', resolved: 'Resolved local time', admitted: 'Admitted at', finished: 'Finished at',
    exact: 'Exact local time.', gap_first_valid: 'First valid time after a clock change.',
    fold_first: 'First occurrence of the repeated time.', fold_second: 'Second occurrence of the repeated time.',
    task: 'Open created task', operation: 'Operation ID',
  },
  es: {
    heading: 'Historial de ejecuciones diarias', open: 'Mostrar historial diario', close: 'Ocultar historial diario',
    loading: 'Cargando ejecuciones programadas…', empty: 'No se ha admitido ninguna ejecución programada para esta regla.',
    unavailable: 'El historial diario no está disponible en este momento.', retry: 'Volver a intentar',
    readDenied: 'Tus permisos actuales no permiten este historial.', expired: 'Esta página ha caducado. Carga las ejecuciones recientes.',
    older: 'Ejecuciones diarias anteriores', latest: 'Ejecuciones diarias recientes', revision: 'Revisión',
    queued: 'Admitida y en espera.', created: 'Tarea creada.', no_task: 'No se cumplieron las condiciones. No se creó ninguna tarea.',
    cancelled: 'Cancelada antes de crear una tarea.', denied: 'No se pudo autorizar la ejecución. No se creó ninguna tarea.',
    historical: 'Registro anterior a la restauración.', historicalQueued: 'Esta admisión histórica no es trabajo pendiente actual.',
    historicalAdmission: 'Admitida antes de la restauración.',
    requested: 'Hora local solicitada', resolved: 'Hora local resuelta', admitted: 'Admitida a las', finished: 'Finalizada a las',
    exact: 'Hora local exacta.', gap_first_valid: 'Primera hora válida tras un cambio de hora.',
    fold_first: 'Primera aparición de la hora repetida.', fold_second: 'Segunda aparición de la hora repetida.',
    task: 'Abrir tarea creada', operation: 'Identificador de operación',
  },
} as const;

export class DomusAutomationDailyHistory extends LitElement {
  static properties = {view: {attribute: false}, language: {attribute: false}};
  static styles = css`
    :host {display:block;--vyp-ha-surface:var(--surface);--vyp-ha-surface-raised:var(--surface);--vyp-ha-text:var(--text);--vyp-ha-text-secondary:var(--muted);
      --vyp-ha-border:var(--line);--vyp-ha-primary:var(--accent);--vyp-ha-on-accent:var(--surface);
      --vyp-ha-focus-ring:3px solid var(--accent)}
    vyp-ha-card {margin-block-end:16px}
    section,ol {display:grid;gap:12px} section {margin-block-start:12px}
    ol {margin:0;padding-inline-start:24px}
    li {border-block-start:1px solid var(--line);padding-block:12px;overflow-wrap:anywhere}
    p {margin:0 0 6px}.actions {display:flex;flex-wrap:wrap;gap:8px}
    a {color:var(--accent);display:inline-flex;min-block-size:44px;align-items:center}
    a:focus-visible,section:focus-visible {outline:3px solid var(--accent);outline-offset:3px}
  `;
  declare view: DailyHistoryView | null;
  declare language: Language;
  constructor() {super(); this.view = null; this.language = 'en';}
  private button(intent: AutomationRunHistoryIntent) {
    return html`<vyp-ha-button .state=${buttonState({label: COPY[this.language][intent], variant: 'outlined'})}
      @ha-press-request=${() => {
        if (intent === 'older' || intent === 'latest' || intent === 'retry')
          this.renderRoot.querySelector<HTMLElement>('section')?.focus();
        this.dispatchEvent(new CustomEvent('domus-automation-daily-history-intent', {detail: intent, bubbles: true, composed: true}));
      }}></vyp-ha-button>`;
  }
  private local(value: string): string {
    return new Intl.DateTimeFormat(this.language, {dateStyle: 'medium', timeStyle: 'short', timeZone: 'UTC', hourCycle: 'h23'})
      .format(new Date(value + 'Z'));
  }
  private run(item: ScheduledAutomationRun) {
    const text = COPY[this.language], id = item.taskOccurrenceId;
    return html`<li>
      <p>${text.revision} ${item.ruleRevision} · ${item.timeZone}</p>
      <p>${text.requested} · ${this.local(item.requestedLocal)}</p>
      <p>${text.resolved} · <time datetime=${new Date(item.scheduledAt).toISOString()}>${this.local(item.resolvedLocal)}</time></p>
      <p>${text[item.resolution]}</p><p><strong>${item.historical && item.outcome === 'queued' ? text.historicalAdmission : text[item.outcome]}</strong></p>
      ${item.historical ? html`<p>${text.historical}</p>` : nothing}
      ${item.historical && item.outcome === 'queued' ? html`<p>${text.historicalQueued}</p>` : nothing}
      <p><small>${text.admitted} · ${new Date(item.admittedAt).toISOString()}</small></p>
      ${item.finishedAt === null ? nothing : html`<p><small>${text.finished} · ${new Date(item.finishedAt).toISOString()}</small></p>`}
      ${id === null ? nothing : html`<a href="#tasks" @click=${(event: MouseEvent) => {
        event.preventDefault(); this.dispatchEvent(new CustomEvent('domus-automation-task-intent', {
          detail: {type: 'select', occurrenceId: id}, bubbles: true, composed: true,
        }));
      }}>${text.task}</a>`}
      ${item.operationId === null ? nothing : html`<p><small>${text.operation} <code>${item.operationId}</code></small></p>`}
    </li>`;
  }
  protected render() {
    const view = this.view;
    if (view === null) return nothing;
    const text = COPY[this.language], {phase, items, hasOlder} = view;
    return html`<vyp-ha-card .state=${cardState({title: text.heading, headingLevel: 2})}>
      ${this.button(phase === 'closed' ? 'open' : 'close')}
      ${phase === 'closed' ? nothing : html`<section tabindex="-1" aria-label=${text.heading} aria-busy=${phase === 'loading'}>
        ${items.length === 0 ? nothing : html`<ol>${repeat(items, item => item.key, item => this.run(item))}</ol>`}
        ${phase === 'loading' ? html`<vyp-ha-feedback .state=${feedbackState({kind: 'loading', message: text.loading})}></vyp-ha-feedback>` : nothing}
        ${phase === 'ready' && items.length === 0 ? html`<p role="status">${text.empty}</p>` : nothing}
        ${phase === 'unavailable' || phase === 'expired' || phase === 'denied'
          ? html`<vyp-ha-feedback .state=${feedbackState({kind: 'notice', tone: 'warning', message: phase === 'denied' ? text.readDenied : text[phase]})}></vyp-ha-feedback>` : nothing}
        <div class="actions">
          ${phase === 'ready' && hasOlder ? this.button('older') : nothing}
          ${phase === 'ready' || phase === 'expired' ? this.button('latest') : nothing}
          ${phase === 'unavailable' ? this.button('retry') : nothing}
        </div>
      </section>`}
    </vyp-ha-card>`;
  }
}
registerButton(); registerCard(); registerFeedback();
customElements.define('domus-automation-daily-history', DomusAutomationDailyHistory);
declare global {interface HTMLElementTagNameMap {'domus-automation-daily-history': DomusAutomationDailyHistory;}}
