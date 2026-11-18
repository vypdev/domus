import {LitElement, css, html, nothing} from 'lit';
import {repeat} from 'lit/directives/repeat.js';
import {registerButton} from '@vypdev/ha-ui/button';
import {buttonState} from '@vypdev/ha-ui/button-contracts';
import {registerCard} from '@vypdev/ha-ui/card';
import {cardState} from '@vypdev/ha-ui/card-contracts';
import {registerFeedback} from '@vypdev/ha-ui/feedback';
import {feedbackState} from '@vypdev/ha-ui/feedback-contracts';
import type {AutomationRun, AutomationRunHistoryIntent, AutomationRunHistoryView} from '../application/automation-run-history';
import type {Language} from './messages';

const COPY = {
  en: {
    heading: 'Manual run history', open: 'Show run history', close: 'Hide run history',
    loading: 'Loading manual runs…', empty: 'You have no manual runs for this rule.',
    unavailable: 'The run history is temporarily unavailable.', retry: 'Try again',
    denied: 'Your current permissions do not allow you to view this history.',
    expired: 'This page has expired. Go back to recent runs.',
    older: 'Older runs', latest: 'Recent runs', revision: 'Revision',
    created: 'Task created.', skipped: 'The stock condition did not match. No task was created.',
    historical: 'Result from before restoration.', task: 'Open created task', operation: 'Operation ID',
  },
  es: {
    heading: 'Historial de ejecuciones manuales', open: 'Mostrar historial', close: 'Ocultar historial',
    loading: 'Cargando ejecuciones manuales…', empty: 'No tienes ejecuciones manuales para esta regla.',
    unavailable: 'El historial no está disponible en este momento.', retry: 'Volver a intentar',
    denied: 'Tus permisos actuales no te permiten consultar el historial.',
    expired: 'Esta página ha caducado. Vuelve a las ejecuciones recientes.',
    older: 'Ejecuciones anteriores', latest: 'Ejecuciones recientes', revision: 'Revisión',
    created: 'Tarea creada.', skipped: 'No se cumplió la condición de existencias. No se creó ninguna tarea.',
    historical: 'Resultado anterior a la restauración.', task: 'Abrir tarea creada', operation: 'Identificador de operación',
  },
} as const;

export class DomusAutomationRunHistory extends LitElement {
  static properties = {view: {attribute: false}, language: {attribute: false}};
  static styles = css`
    :host {display:block;--vyp-ha-surface:var(--surface);--vyp-ha-text:var(--text);--vyp-ha-text-secondary:var(--muted);
      --vyp-ha-border:var(--line);--vyp-ha-primary:var(--accent);--vyp-ha-on-accent:var(--surface);
      --vyp-ha-focus-ring:3px solid var(--accent)}
    vyp-ha-card {margin-block-end:16px}
    section {display:grid;gap:10px;margin-block-start:12px}
    .actions {display:flex;flex-wrap:wrap;gap:8px}
    ol {display:grid;gap:10px;margin:0;padding-inline-start:24px}
    li {padding-block:8px;border-block-start:1px solid var(--line);overflow-wrap:anywhere}
    p {margin:0 0 5px}
    a {color:var(--accent);display:inline-flex;min-block-size:44px;align-items:center}
    a:focus-visible, section:focus-visible {outline:3px solid var(--accent);outline-offset:3px}
    small {display:block}
  `;

  declare view: AutomationRunHistoryView | null;
  declare language: Language;

  constructor() {super(); this.view = null; this.language = 'en';}

  private button(intent: AutomationRunHistoryIntent) {
    return html`<vyp-ha-button .state=${buttonState({label: COPY[this.language][intent], variant: 'outlined'})}
      @ha-press-request=${() => {
        if (intent === 'older' || intent === 'latest' || intent === 'retry')
          this.renderRoot.querySelector<HTMLElement>('section')?.focus();
        this.dispatchEvent(new CustomEvent('domus-automation-run-history-intent',
          {detail: intent, bubbles: true, composed: true}));
      }}></vyp-ha-button>`;
  }

  private run(item: AutomationRun, format: Intl.DateTimeFormat) {
    const text = COPY[this.language], date = new Date(item.time), occurrenceId = item.taskOccurrenceId;
    return html`<li>
      <p><time datetime=${date.toISOString()}>${format.format(date)}</time> · ${text.revision} ${item.revision}</p>
      <p><strong>${item.taskCreated ? text.created : text.skipped}</strong></p>
      ${item.historical ? html`<p>${text.historical}</p>` : nothing}
      ${occurrenceId === null ? nothing : html`<a href="#tasks" @click=${(event: MouseEvent) => {
        event.preventDefault();
        this.dispatchEvent(new CustomEvent('domus-automation-task-intent',
          {detail: {type: 'select', occurrenceId}, bubbles: true, composed: true}));
      }}>${text.task}</a>`}
      <small>${text.operation} <code>${item.operationId}</code></small>
    </li>`;
  }

  protected render() {
    const view = this.view;
    if (view === null) return nothing;
    const text = COPY[this.language], {phase, items, hasOlder, timeZone} = view;
    const format = new Intl.DateTimeFormat(this.language, {dateStyle: 'medium', timeStyle: 'short', timeZone});
    return html`<vyp-ha-card .state=${cardState({title: text.heading, headingLevel: 2})}>
      ${this.button(phase === 'closed' ? 'open' : 'close')}
      ${phase === 'closed' ? nothing : html`<section tabindex="-1" aria-label=${text.heading} aria-busy=${phase === 'loading'}>
        ${items.length === 0 ? nothing : html`<ol>${repeat(items, item => item.operationId,
          item => this.run(item, format))}</ol>`}
        ${phase === 'loading' ? html`<vyp-ha-feedback .state=${feedbackState({kind: 'loading', message: text.loading})}></vyp-ha-feedback>` : nothing}
        ${phase === 'ready' && items.length === 0 ? html`<p role="status">${text.empty}</p>` : nothing}
        ${phase === 'unavailable' || phase === 'expired' || phase === 'denied'
          ? html`<vyp-ha-feedback .state=${feedbackState({kind: 'notice', tone: 'warning', message: text[phase]})}></vyp-ha-feedback>` : nothing}
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
customElements.define('domus-automation-run-history', DomusAutomationRunHistory);
declare global {interface HTMLElementTagNameMap {'domus-automation-run-history': DomusAutomationRunHistory;}}
