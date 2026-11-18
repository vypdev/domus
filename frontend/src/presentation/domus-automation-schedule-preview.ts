import {LitElement, css, html, nothing} from 'lit';
import type {PropertyValues} from 'lit';
import {registerButton} from '@vypdev/ha-ui/button';
import {buttonState} from '@vypdev/ha-ui/button-contracts';
import {registerCard} from '@vypdev/ha-ui/card';
import {cardState} from '@vypdev/ha-ui/card-contracts';
import {registerFeedback} from '@vypdev/ha-ui/feedback';
import {feedbackState} from '@vypdev/ha-ui/feedback-contracts';
import {registerField} from '@vypdev/ha-ui/field';
import type {FieldValueEvent} from '@vypdev/ha-ui/field';
import {textFieldState} from '@vypdev/ha-ui/field-contracts';
import type {DailyAutomationTime, SchedulePreviewIntent, SchedulePreviewView} from '../application/automation-schedule-preview';
import type {Language} from './messages';

const COPY = {
  en: {
    title: 'Daily schedule preview', time: 'Time each day', format: 'Use 24-hour time, for example 07:30.',
    preview: 'Preview daily times', retry: 'Try again', zone: 'Household time zone',
    loading: 'Calculating the next five times…', invalid: 'Enter a time between 00:00 and 23:59.',
    unavailable: 'The daily times are temporarily unavailable.',
    denied: 'Your current permissions do not allow scheduling previews.',
    results: 'Next five times', requested: 'Requested',
    gap_first_valid: 'Shifted to the first valid time after the clock change.',
    fold_first: 'First occurrence of the repeated time.',
    fold_second: 'Second occurrence of the repeated time.',
  },
  es: {
    title: 'Vista previa del horario diario', time: 'Hora de cada día', format: 'Usa el formato de 24 horas, por ejemplo 07:30.',
    preview: 'Previsualizar horario diario', retry: 'Volver a intentar', zone: 'Zona horaria del hogar',
    loading: 'Calculando las próximas cinco fechas…', invalid: 'Introduce una hora entre las 00:00 y las 23:59.',
    unavailable: 'El horario diario no está disponible en este momento.',
    denied: 'Tus permisos actuales no te permiten previsualizar horarios.',
    results: 'Próximas cinco fechas', requested: 'Hora solicitada',
    gap_first_valid: 'Se ajustó a la primera hora válida tras el cambio de hora.',
    fold_first: 'Primera aparición de la hora repetida.',
    fold_second: 'Segunda aparición de la hora repetida.',
  },
} as const;

export class DomusAutomationSchedulePreview extends LitElement {
  static properties = {view: {attribute: false}, language: {attribute: false}};
  static styles = css`
    :host {display:block;--vyp-ha-surface:var(--surface);--vyp-ha-surface-raised:var(--surface);--vyp-ha-text:var(--text);
      --vyp-ha-text-secondary:var(--muted);--vyp-ha-border:var(--line);--vyp-ha-primary:var(--accent);
      --vyp-ha-on-accent:var(--surface);--vyp-ha-focus-ring:3px solid var(--accent)}
    vyp-ha-card {margin-block-end:16px}
    form,section {display:grid;gap:12px}
    p,h3 {margin:0;overflow-wrap:anywhere}
    ol {display:grid;gap:8px;margin:0;padding-inline-start:24px}
    vyp-ha-button {justify-self:start}
    li p {margin-block-start:4px}
  `;

  declare view: SchedulePreviewView | null;
  declare language: Language;
  constructor() {super(); this.view = null; this.language = 'en';}

  private intent(detail: SchedulePreviewIntent): void {
    this.dispatchEvent(new CustomEvent('domus-automation-schedule-preview-intent', {
      detail, bubbles: true, composed: true,
    }));
  }

  protected updated(changed: PropertyValues<this>): void {
    if (changed.has('view') && this.view?.issue === 'invalid')
      this.renderRoot.querySelector('vyp-ha-field')!.focus();
  }

  private item(item: DailyAutomationTime, input: string, format: Intl.DateTimeFormat) {
    const text = COPY[this.language];
    // Interpret the server's civil fields on a fixed UTC display clock.
    const local = format.format(new Date(item.resolvedLocal + 'Z'));
    return html`<li>
      <time datetime=${new Date(item.instantMs).toISOString()}>${local}</time>
      ${item.resolution === 'gap_first_valid'
        ? html`<p>${text.requested} · ${format.format(new Date(item.requestedDate + 'T' + input + ':00Z'))}</p>` : nothing}
      ${item.resolution === 'exact' ? nothing : html`<p>${text[item.resolution]}</p>`}
    </li>`;
  }

  protected render() {
    const view = this.view;
    if (view === null) return nothing;
    const text = COPY[this.language];
    const format = new Intl.DateTimeFormat(this.language, {dateStyle: 'medium', timeStyle: 'short', timeZone: 'UTC', hourCycle: 'h23'});
    return html`<vyp-ha-card .state=${cardState({title: text.title, headingLevel: 2})}>
      <form novalidate aria-busy=${view.busy} @submit=${(event: SubmitEvent) => {
        event.preventDefault();
        if (!view.busy) this.intent({type: 'preview'});
      }}>
        <p>${text.zone} · ${view.timeZone}</p>
        <vyp-ha-field .value=${view.input}
          .state=${textFieldState({label: text.time, description: text.format, required: true, maxLength: 16,
            error: view.issue === 'invalid' ? text.invalid : ''})}
          @ha-value-request=${(event: FieldValueEvent) => this.intent({type: 'time', value: event.detail.value})}></vyp-ha-field>
        <vyp-ha-button type="submit" ?disabled=${view.busy}
          .state=${buttonState({label: view.issue === 'unavailable' ? text.retry : text.preview, variant: 'primary'})}></vyp-ha-button>
        ${view.busy ? html`<vyp-ha-feedback .state=${feedbackState({kind: 'loading', message: text.loading})}></vyp-ha-feedback>` : nothing}
        ${view.issue === 'unavailable' || view.issue === 'denied'
          ? html`<vyp-ha-feedback .state=${feedbackState({kind: 'notice', tone: 'warning', message: text[view.issue]})}></vyp-ha-feedback>` : nothing}
        ${view.result === null ? nothing : html`<section aria-labelledby="daily-preview-results" role="status">
          <h3 id="daily-preview-results">${text.results}</h3>
          <ol>${view.result.map(item => this.item(item, view.input, format))}</ol>
        </section>`}
      </form>
    </vyp-ha-card>`;
  }
}

registerButton(); registerCard(); registerFeedback(); registerField();
customElements.define('domus-automation-schedule-preview', DomusAutomationSchedulePreview);
declare global {interface HTMLElementTagNameMap {'domus-automation-schedule-preview': DomusAutomationSchedulePreview;}}
