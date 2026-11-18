import {LitElement, css, html, nothing} from 'lit';
import type {PropertyValues} from 'lit';
import {registerButton} from '@vypdev/ha-ui/button';
import {buttonState} from '@vypdev/ha-ui/button-contracts';
import {registerCard} from '@vypdev/ha-ui/card';
import {cardState} from '@vypdev/ha-ui/card-contracts';
import {registerFeedback} from '@vypdev/ha-ui/feedback';
import {feedbackState} from '@vypdev/ha-ui/feedback-contracts';
import type {AutomationExecutionIntent, AutomationExecutionResult, AutomationExecutionView} from '../application/automation-execution';
import type {Language} from './messages';

const COPY = {
  en: {
    heading: 'Manual automation', saved: 'Saved draft', revision: 'Revision',
    enabled: 'Enabled', inactive: 'Disabled', enable: 'Enable saved revision',
    disable: 'Disable future runs', run: 'Run manually', cancel: 'Cancel',
    confirmEnable: 'Enable this revision', confirmDisable: 'Disable future runs',
    confirmRun: 'Run this revision', review: 'Confirm automation action',
    loading: 'Checking automation status…', unauthorised: 'This session can view results and recover receipts.',
    denied: 'Your current permissions do not allow manual automation.',
    unavailable: 'The automation status is unavailable. Try again.',
    uncertain: 'The result could not be confirmed. Check the original request.',
    stale: 'The automation changed. Review the current revision and confirm again.',
    disabled: 'Manual runs are disabled for this rule.',
    rejected: 'The action was rejected. Check the rule before trying again.',
    retry: 'Try again', recover: 'Check original request',
    historical: 'Result from before restoration.', enabledResult: 'Rule enabled.',
    disabledResult: 'Future runs disabled.', matched: 'Task created.',
    unmatched: 'The stock condition did not match. No task was created.',
    task: 'Open created task', operation: 'Operation ID',
  },
  es: {
    heading: 'Automatización manual', saved: 'Borrador guardado', revision: 'Revisión',
    enabled: 'Habilitada', inactive: 'Deshabilitada', enable: 'Habilitar revisión guardada',
    disable: 'Deshabilitar futuras ejecuciones', run: 'Ejecutar manualmente', cancel: 'Cancelar',
    confirmEnable: 'Habilitar esta revisión', confirmDisable: 'Deshabilitar futuras ejecuciones',
    confirmRun: 'Ejecutar esta revisión', review: 'Confirmar acción de automatización',
    loading: 'Consultando el estado de la automatización…', unauthorised: 'En esta sesión puedes consultar resultados y recuperar recibos.',
    denied: 'Tus permisos actuales no permiten ejecutar automatizaciones manuales.',
    unavailable: 'El estado de la automatización no está disponible. Vuelve a intentarlo.',
    uncertain: 'No se pudo confirmar el resultado. Consulta la solicitud original.',
    stale: 'La automatización cambió. Revisa la revisión actual y vuelve a confirmar.',
    disabled: 'Las ejecuciones manuales están deshabilitadas para esta regla.',
    rejected: 'Se rechazó la acción. Revisa la regla antes de volver a intentarlo.',
    retry: 'Volver a intentar', recover: 'Consultar solicitud original',
    historical: 'Resultado anterior a la restauración.', enabledResult: 'Regla habilitada.',
    disabledResult: 'Futuras ejecuciones deshabilitadas.', matched: 'Tarea creada.',
    unmatched: 'No se cumplió la condición de existencias. No se creó ninguna tarea.',
    task: 'Abrir tarea creada', operation: 'Identificador de operación',
  },
} as const;

type CopyKey = keyof typeof COPY.en;

export class DomusAutomationExecution extends LitElement {
  static properties = {view: {attribute: false}, language: {attribute: false}};
  static styles = css`
    :host {display:block;--vyp-ha-surface:var(--surface);--vyp-ha-surface-raised:var(--surface);
      --vyp-ha-text:var(--text);--vyp-ha-text-secondary:var(--muted);--vyp-ha-border:var(--line);
      --vyp-ha-primary:var(--accent);--vyp-ha-on-accent:var(--surface);--vyp-ha-focus-ring:3px solid var(--accent)}
    vyp-ha-card {margin-block-end:16px}
    .content {display:grid;gap:10px}
    .actions {display:flex;align-items:center;flex-wrap:wrap;gap:8px}
    p,h3 {margin:0;overflow-wrap:anywhere}
    .confirmation,.result {display:grid;gap:8px;border-block-start:1px solid var(--line);padding-block-start:10px}
    a {color:var(--accent);width:fit-content}
    a:focus-visible, h3:focus-visible {outline:3px solid var(--accent);outline-offset:3px}
  `;

  declare view: AutomationExecutionView | null;
  declare language: Language;

  constructor() {super(); this.view = null; this.language = 'en';}

  private text(key: CopyKey): string {return COPY[this.language][key];}

  private button(key: CopyKey, intent: AutomationExecutionIntent, disabled: boolean, primary = false) {
    return html`<vyp-ha-button .state=${buttonState({label: this.text(key), variant: primary ? 'primary' : 'outlined'})}
      ?disabled=${disabled} @ha-press-request=${() => this.dispatchEvent(new CustomEvent('domus-automation-execution-intent',
        {detail: intent, bubbles: true, composed: true}))}></vyp-ha-button>`;
  }

  protected updated(changed: PropertyValues<this>): void {
    if (changed.has('view') && this.view?.confirmation && !changed.get('view')?.confirmation)
      this.renderRoot.querySelector<HTMLElement>('#automation-confirmation-title')!.focus();
  }

  private outcome(result: AutomationExecutionResult) {
    const current = result.kind === 'committed';
    const message = result.action === 'configure'
      ? result.enabled ? 'enabledResult' : 'disabledResult'
      : result.taskOccurrenceId === null ? 'unmatched' : 'matched';
    const id = result.action === 'run' && current ? result.taskOccurrenceId : null;
    return html`<section class="result" role="status">
      ${current ? nothing : html`<p>${this.text('historical')}</p>`}
      <p><strong>${this.text(message)}</strong> · ${this.text('revision')} ${result.ruleRevision}</p>
      ${id === null ? nothing : html`<a href="#tasks" @click=${(event: MouseEvent) => {
        event.preventDefault();
        this.dispatchEvent(new CustomEvent('domus-automation-task-intent',
          {detail: {type: 'select', occurrenceId: id}, bubbles: true, composed: true}));
      }}>${this.text('task')}</a>`}
      <p>${this.text('operation')} <code>${result.operationId}</code></p>
    </section>`;
  }

  private configuration(view: AutomationExecutionView) {
    const configuration = view.configuration;
    if (configuration === null) return nothing;
    const {latestRevision, latestTitle, control} = configuration;
    const blocked = view.busy || view.pending || view.readOnly;
    const confirmation = view.confirmation;
    const enabled = control?.enabled === true;
    return html`<p>${this.text('saved')} · ${this.text('revision')} ${latestRevision} · ${latestTitle}</p>
      <p role="status">${enabled ? html`${this.text('enabled')} · ${this.text('revision')} ${control.ruleRevision} · ${control.title}`
        : this.text('inactive')}</p>
      ${confirmation === null ? html`<div class="actions">
        ${enabled ? this.button('run', 'run', blocked, true) : nothing}
        ${enabled && control.ruleRevision === latestRevision ? nothing : this.button('enable', 'enable', blocked, !enabled)}
        ${enabled ? this.button('disable', 'disable', blocked) : nothing}
      </div>` : html`<section class="confirmation" aria-labelledby="automation-confirmation-title">
        <h3 id="automation-confirmation-title" tabindex="-1">${this.text('review')}</h3>
        <p>${this.text('revision')} ${confirmation.command.ruleRevision} · ${confirmation.title}</p>
        <div class="actions">
          ${this.button(confirmation.command.kind === 'run' ? 'confirmRun'
            : confirmation.command.enabled ? 'confirmEnable' : 'confirmDisable', 'confirm', blocked, true)}
          ${this.button('cancel', 'cancel', view.busy)}
        </div>
      </section>`}`;
  }

  protected render() {
    const view = this.view;
    if (view === null) return nothing;
    return html`<vyp-ha-card .state=${cardState({title: this.text('heading'), headingLevel: 2})}>
      <div class="content" aria-busy=${view.busy}>
        ${this.configuration(view)}
        ${view.readOnly ? html`<p>${this.text('unauthorised')}</p>` : nothing}
        ${view.busy ? html`<vyp-ha-feedback .state=${feedbackState({kind: 'loading', message: this.text('loading')})}></vyp-ha-feedback>` : nothing}
        ${view.notice === null ? nothing : html`<vyp-ha-feedback .state=${feedbackState({kind: 'notice', tone: 'warning', message: this.text(view.notice)})}></vyp-ha-feedback>`}
        ${view.notice === 'unavailable' && view.configuration === null && !view.pending
          ? this.button('retry', 'reload', view.busy) : nothing}
        ${view.pending && !view.busy ? this.button('recover', 'recover', false) : nothing}
        ${view.result === null ? nothing : this.outcome(view.result)}
      </div>
    </vyp-ha-card>`;
  }
}

registerButton(); registerCard(); registerFeedback();
customElements.define('domus-automation-execution', DomusAutomationExecution);
declare global {interface HTMLElementTagNameMap {'domus-automation-execution': DomusAutomationExecution;}}
