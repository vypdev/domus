import {LitElement, css, html, nothing} from 'lit';
import type {PropertyValues, TemplateResult} from 'lit';
import {registerButton} from '@vypdev/ha-ui/button';
import {buttonState} from '@vypdev/ha-ui/button-contracts';
import {registerCard} from '@vypdev/ha-ui/card';
import {cardState} from '@vypdev/ha-ui/card-contracts';
import {registerFeedback} from '@vypdev/ha-ui/feedback';
import {feedbackState} from '@vypdev/ha-ui/feedback-contracts';
import {dailyInstant} from '../application/automation-daily';
import type {DailyAction, DailyIntent, DailyPolicy, DailyReview, DailyView, ReviewedDailyTime} from '../application/automation-daily';
import type {DraftCondition} from '../application/automation-drafts';
import type {Language} from './messages';

const COPY = {
  en: {
    heading: 'Daily automation', rule: 'Rule ID', revision: 'Revision', task: 'Create task', daily: 'Every day at',
    disabledStatus: 'Daily automation is disabled.', enabledStatus: 'Daily automation is enabled.',
    manualStatus: 'A manual revision is enabled.',
    enable: 'Enable this daily revision', disable: 'Disable daily automation', adopt: 'Review new household timing',
    active: 'Review enabled daily revision', saved: 'Review selected saved revision',
    confirmation: 'Confirm daily automation', confirm: 'Confirm', cancel: 'Cancel',
    enableHelp: 'This replaces any enabled revision of this rule. Only this saved revision is granted permission.',
    disableHelp: 'New effects and waiting runs will stop. Tasks already created and their history will remain.',
    adoptHelp: 'Use the reviewed household timing for future admissions. Already admitted runs keep their original timing.',
    grant: 'The permission belongs to this household rule and allows it to create only the task shown here. It remains until disabled, even if the person who enabled it leaves.',
    startup: 'Times missed while Domus is stopped are skipped. Already admitted work is preserved.',
    permission: 'Creating or renewing this permission also requires permission to create tasks. You can still disable an enabled rule or review its timing.',
    readOnly: 'Changes are unavailable in this session. You can still check an original request.',
    approved: 'Approved timing', proposed: 'Current household timing', upcoming: 'Next five times',
    next: 'Next scheduled time', zone: 'Time zone', data: 'Time-zone data',
    first_instant: 'Use the first occurrence of a repeated time.', second_instant: 'Use the second occurrence of a repeated time.',
    changed: 'The household timing has changed. The approved timing stays in use until you explicitly adopt the new timing.',
    approvedUnavailable: 'The approved timing cannot currently be resolved. New admissions will wait until it is available or you explicitly adopt the reviewed household timing.',
    proposedUnavailable: 'The household timing cannot currently be resolved. You can still disable the daily rule. Refresh the review before enabling it or adopting new timing.',
    condition: 'Conditions', noCondition: 'No condition. This task is created each scheduled day.',
    stock: 'Stock below minimum for product', all: 'All of these', any: 'At least one of these', not: 'Not',
    requested: 'Requested local time', resolved: 'Resolved local time',
    exact: 'Exact local time.', gap_first_valid: 'Moved to the first valid time after a clock change.',
    fold_first: 'First occurrence of the repeated time.', fold_second: 'Second occurrence of the repeated time.',
    suppression: 'Skipped while stopped', through: 'Through', loading: 'Checking the daily automation…',
    reload: 'Refresh daily review', recover: 'Check original daily request', operation: 'Operation ID',
    historical: 'Result from before restoration. This receipt does not activate the current rule.',
    enableResult: 'Daily permission granted.', disableResult: 'Daily permission revoked.', adoptResult: 'New timing adopted.',
    unavailable: 'The daily review is unavailable. Refresh it to review the current state.',
    denied: 'Your current permissions do not allow this daily automation.',
    uncertain: 'The request result is unknown. Check the original request before making another change.',
    journal_unavailable: 'The request record could not be updated. Keep this page open and check the original request before making another change.',
    record_failed: 'The request could not be saved locally. No change was sent. Keep the reviewed values and try confirming again when storage is available.',
    stale: 'The rule or schedule changed. Review the refreshed state and confirm again.',
    timing_changed: 'The reviewed first time changed. Review the refreshed times and confirm again.',
    disabled: 'This daily rule is no longer enabled. Review its current state.',
    rejected: 'The change was rejected. Review the saved rule before trying again.',
  },
  es: {
    heading: 'Automatización diaria', rule: 'Identificador de regla', revision: 'Revisión', task: 'Crear tarea', daily: 'Cada día a las',
    disabledStatus: 'La automatización diaria está deshabilitada.', enabledStatus: 'La automatización diaria está habilitada.',
    manualStatus: 'Hay una revisión manual habilitada.',
    enable: 'Habilitar esta revisión diaria', disable: 'Deshabilitar automatización diaria', adopt: 'Revisar nuevo horario del hogar',
    active: 'Revisar revisión diaria habilitada', saved: 'Revisar revisión guardada seleccionada',
    confirmation: 'Confirmar automatización diaria', confirm: 'Confirmar', cancel: 'Cancelar',
    enableHelp: 'Sustituye cualquier revisión habilitada de esta regla. El permiso se concede solo a esta revisión guardada.',
    disableHelp: 'Se detendrán los nuevos efectos y las ejecuciones en espera. Se conservarán las tareas ya creadas y su historial.',
    adoptHelp: 'Usa el horario revisado del hogar para las futuras admisiones. Las ejecuciones ya admitidas conservan su horario original.',
    grant: 'El permiso pertenece a esta regla del hogar y solo le permite crear la tarea que se muestra aquí. Se mantiene hasta deshabilitarla, aunque se marche quien la habilitó.',
    startup: 'Se omiten las horas perdidas mientras Domus está detenido. Se conserva el trabajo ya admitido.',
    permission: 'Crear o renovar este permiso también requiere poder crear tareas. Puedes deshabilitar una regla habilitada o revisar su horario.',
    readOnly: 'En esta sesión no puedes hacer cambios. Puedes consultar una solicitud original.',
    approved: 'Horario aprobado', proposed: 'Horario actual del hogar', upcoming: 'Próximas cinco fechas',
    next: 'Próxima hora programada', zone: 'Zona horaria', data: 'Datos de zona horaria',
    first_instant: 'Usar la primera aparición de una hora repetida.', second_instant: 'Usar la segunda aparición de una hora repetida.',
    changed: 'El horario del hogar ha cambiado. El horario aprobado se mantiene hasta que adoptes el nuevo explícitamente.',
    approvedUnavailable: 'No se puede resolver el horario aprobado. Las nuevas admisiones esperarán hasta que vuelva a estar disponible o adoptes explícitamente el horario revisado del hogar.',
    proposedUnavailable: 'No se puede resolver el horario del hogar. Puedes deshabilitar la regla diaria. Actualiza la revisión antes de habilitarla o adoptar otro horario.',
    condition: 'Condiciones', noCondition: 'Sin condición. Esta tarea se crea cada día programado.',
    stock: 'Existencias por debajo del mínimo para el producto', all: 'Todas estas', any: 'Al menos una de estas', not: 'No',
    requested: 'Hora local solicitada', resolved: 'Hora local resuelta',
    exact: 'Hora local exacta.', gap_first_valid: 'Se ajustó a la primera hora válida tras el cambio de hora.',
    fold_first: 'Primera aparición de la hora repetida.', fold_second: 'Segunda aparición de la hora repetida.',
    suppression: 'Omitidas durante la parada', through: 'Hasta', loading: 'Consultando la automatización diaria…',
    reload: 'Actualizar revisión diaria', recover: 'Consultar solicitud diaria original', operation: 'Identificador de operación',
    historical: 'Resultado anterior a la restauración. Este recibo no activa la regla actual.',
    enableResult: 'Permiso diario concedido.', disableResult: 'Permiso diario revocado.', adoptResult: 'Nuevo horario adoptado.',
    unavailable: 'La revisión diaria no está disponible. Actualízala para revisar el estado actual.',
    denied: 'Tus permisos actuales no permiten esta automatización diaria.',
    uncertain: 'Se desconoce el resultado. Consulta la solicitud original antes de hacer otro cambio.',
    journal_unavailable: 'No se pudo actualizar el registro de la solicitud. Mantén abierta esta página y consulta la solicitud original antes de hacer otro cambio.',
    record_failed: 'No se pudo guardar la solicitud localmente. No se envió ningún cambio. Conserva los valores revisados y vuelve a confirmar cuando el almacenamiento esté disponible.',
    stale: 'La regla o el horario ha cambiado. Revisa el estado actualizado y vuelve a confirmar.',
    timing_changed: 'La primera hora revisada ha cambiado. Revisa las fechas actualizadas y vuelve a confirmar.',
    disabled: 'Esta regla diaria ya no está habilitada. Revisa su estado actual.',
    rejected: 'Se rechazó el cambio. Revisa la regla guardada antes de volver a intentarlo.',
  },
} as const;
type CopyKey = keyof typeof COPY.en;

export class DomusAutomationDaily extends LitElement {
  static properties = {view: {attribute: false}, language: {attribute: false}};
  static styles = css`
    :host {display:block;--vyp-ha-surface:var(--surface);--vyp-ha-surface-raised:var(--surface);--vyp-ha-text:var(--text);--vyp-ha-text-secondary:var(--muted);
      --vyp-ha-border:var(--line);--vyp-ha-primary:var(--accent);--vyp-ha-on-accent:var(--surface);
      --vyp-ha-focus-ring:3px solid var(--accent)}
    vyp-ha-card {margin-block-end:16px}
    .content,section,li {display:grid;gap:8px}
    .actions {display:flex;flex-wrap:wrap;gap:8px}
    p,h3,h4 {margin:0;overflow-wrap:anywhere}
    section {border-block-start:1px solid var(--line);padding-block-start:12px}
    ol,ul {display:grid;gap:12px;margin:0;padding-inline-start:24px}
    li {display:list-item;overflow-wrap:anywhere}
    details {padding-block:6px} summary {cursor:pointer;padding-block:8px}
    h3:focus-visible,summary:focus-visible {outline:3px solid var(--accent);outline-offset:3px}
  `;
  declare view: DailyView | null;
  declare language: Language;
  private restore: DailyAction | null = null;
  constructor() {super(); this.view = null; this.language = 'en';}
  private text(key: CopyKey): string {return COPY[this.language][key];}
  private button(intent: DailyIntent, disabled: boolean, primary = false) {
    return html`<vyp-ha-button data-intent=${intent} ?disabled=${disabled}
      .state=${buttonState({label: this.text(intent), variant: primary ? 'primary' : 'outlined'})}
      @ha-press-request=${() => this.dispatchEvent(new CustomEvent('domus-automation-daily-intent',
        {detail: intent, bubbles: true, composed: true}))}></vyp-ha-button>`;
  }
  protected updated(changed: PropertyValues<this>): void {
    if (!changed.has('view')) return;
    const prior = changed.get('view'), view = this.view;
    if (view === null) {this.restore = null; return;}
    if (view.confirmation && !prior?.confirmation) {
      this.restore = view.confirmation.kind;
      this.renderRoot.querySelector<HTMLElement>('#daily-confirmation')!.focus();
    } else if (view.result && view.result !== prior?.result) {
      this.restore = null;
      this.renderRoot.querySelector<HTMLElement>('#daily-result')!.focus();
    } else if (!view.busy && !view.confirmation && this.restore !== null) {
      void this.focusAction(this.restore, view);
      this.restore = null;
    }
  }
  private async focusAction(intent: DailyAction, view: DailyView): Promise<void> {
    const button = this.renderRoot.querySelector<HTMLElementTagNameMap['vyp-ha-button']>(`[data-intent="${intent}"]`)
      ?? this.renderRoot.querySelector<HTMLElementTagNameMap['vyp-ha-button']>(`[data-intent="${view.pending ? 'recover' : 'reload'}"]`)!;
    await button.updateComplete;
    if (this.view === view && button.isConnected) button.focus();
  }
  private local(value: string): string {
    return new Intl.DateTimeFormat(this.language, {dateStyle: 'medium', timeStyle: 'short', timeZone: 'UTC', hourCycle: 'h23'})
      .format(new Date(value + 'Z'));
  }
  private time(value: ReviewedDailyTime) {
    return html`<time datetime=${new Date(dailyInstant(value)).toISOString()}>${this.local(value.resolvedLocal)}</time>
      <p>${this.text(value.resolution)}</p>
      ${value.resolution === 'gap_first_valid' ? html`<p>${this.text('requested')} · ${this.local(value.nominal)}</p>` : nothing}`;
  }
  private policy(policy: DailyPolicy, times: readonly ReviewedDailyTime[] | null, label: 'approved' | 'proposed') {
    return html`<section><h3>${this.text(label)}</h3>
      <p>${this.text('zone')} · ${policy.zone}</p><p>${this.text(policy.repeatedTime)}</p>
      <p><small>${this.text('data')} · ${policy.dataIdentity}</small></p>
      ${times === null ? nothing : html`<details><summary>${this.text('upcoming')}</summary>
        <ol>${times.map(value => html`<li>${this.time(value)}</li>`)}</ol></details>`}
    </section>`;
  }
  private condition(value: DraftCondition): TemplateResult {
    if (value.kind === 'stock_below_minimum') return html`<li>${this.text('stock')} · ${value.product_id}</li>`;
    if (value.kind === 'not') return html`<li>${this.text('not')}<ul>${this.condition(value.child)}</ul></li>`;
    return html`<li>${this.text(value.kind)}<ul>${value.children.map(child => this.condition(child))}</ul></li>`;
  }
  private detail(view: DailyView, review: DailyReview) {
    const blocked = view.busy || view.pending || view.readOnly, active = review.enabled && review.activeTrigger === 'daily';
    return html`<p><strong>${this.text('task')} · ${review.title}</strong></p>
      <p>${this.text('revision')} ${review.ruleRevision} · ${this.text('daily')} ${review.requestedTime}</p>
      <p role="status">${this.text(active ? 'enabledStatus' : review.activeTrigger === 'manual' ? 'manualStatus' : 'disabledStatus')}
        ${review.activeRevision === null ? nothing : html` · ${this.text('revision')} ${review.activeRevision} · ${review.activeTitle}`}</p>
      <p>${this.text('grant')}</p><p>${this.text('startup')}</p>
      <section><h3>${this.text('condition')}</h3>
        ${review.condition === null ? html`<p>${this.text('noCondition')}</p>` : html`<ul>${this.condition(review.condition)}</ul>`}
      </section>
      ${review.approvedPolicy === null ? nothing : this.policy(review.approvedPolicy, review.approvedTimes, 'approved')}
      ${active && review.next !== null ? html`<section><h3>${this.text('next')}</h3>${this.time(review.next)}</section>` : nothing}
      ${review.policyChanged ? html`<p role="status">${this.text('changed')}</p>` : nothing}
      ${review.approvedUnavailable ? html`<vyp-ha-feedback .state=${feedbackState({kind: 'notice', tone: 'warning',
        message: this.text('approvedUnavailable')})}></vyp-ha-feedback>` : nothing}
      ${review.proposedUnavailable ? html`<vyp-ha-feedback .state=${feedbackState({kind: 'notice', tone: 'warning',
        message: this.text('proposedUnavailable')})}></vyp-ha-feedback>` : nothing}
      ${this.policy(review.proposedPolicy, review.proposedUnavailable ? null : review.proposedTimes, 'proposed')}
      ${review.suppression === null ? nothing : html`<section><h3>${this.text('suppression')}</h3>
        ${this.time(review.suppression.first)}<p>${this.text('through')} · ${new Date(review.suppression.throughMs).toISOString()}</p>
      </section>`}
      ${!review.mayEnable ? html`<p>${this.text('permission')}</p>` : nothing}
      ${view.confirmation !== null ? nothing : html`<div class="actions">
        ${active && review.activeRevision === review.ruleRevision ? nothing : this.button('enable', blocked || !review.mayEnable || review.proposedUnavailable, true)}
        ${active ? this.button('disable', blocked) : nothing}
        ${active && review.activeRevision === review.ruleRevision && review.policyChanged ? this.button('adopt', blocked || review.proposedUnavailable) : nothing}
        ${active && review.activeRevision !== review.ruleRevision ? this.button('active', view.busy || view.pending) : nothing}
        ${view.savedRevision !== null && view.savedRevision !== review.ruleRevision ? this.button('saved', view.busy || view.pending) : nothing}
        ${this.button('reload', view.busy)}
      </div>`}`;
  }
  protected render() {
    const view = this.view;
    if (view === null) return nothing;
    const confirmation = view.confirmation, result = view.result;
    return html`<vyp-ha-card .state=${cardState({title: this.text('heading'), headingLevel: 2})}>
      <div class="content" aria-busy=${view.busy}>
        ${view.review === null ? nothing : this.detail(view, view.review)}
        ${view.readOnly ? html`<p>${this.text('readOnly')}</p>` : nothing}
        ${confirmation === null ? nothing : html`<section aria-labelledby="daily-confirmation">
          <h3 id="daily-confirmation" tabindex="-1">${this.text('confirmation')}</h3>
          <p><strong>${this.text(confirmation.kind)}</strong> · ${this.text('revision')} ${confirmation.ruleRevision}</p>
          <p>${this.text(confirmation.kind === 'enable' ? 'enableHelp' : confirmation.kind === 'disable' ? 'disableHelp' : 'adoptHelp')}</p>
          ${confirmation.reviewed === undefined ? nothing : html`<p>${this.text('zone')} · ${confirmation.reviewed.policy.zone}</p>
            ${this.time(confirmation.reviewed)}`}
          <div class="actions">${this.button('confirm', view.busy || view.pending || view.readOnly, true)}
            ${this.button('cancel', view.busy)}</div>
        </section>`}
        ${view.busy ? html`<vyp-ha-feedback .state=${feedbackState({kind: 'loading', message: this.text('loading')})}></vyp-ha-feedback>` : nothing}
        ${view.notice === null ? nothing : html`<vyp-ha-feedback .state=${feedbackState({kind: 'notice', tone: 'warning',
          message: this.text(view.notice)})}></vyp-ha-feedback>`}
        ${view.review === null && !view.pending && !view.busy ? this.button('reload', false) : nothing}
        ${view.pending ? this.button('recover', view.busy) : nothing}
        ${result === null ? nothing : html`<section role="status" aria-labelledby="daily-result">
          <h3 id="daily-result" tabindex="-1">${this.text(result.action === 'enable' ? 'enableResult'
            : result.action === 'disable' ? 'disableResult' : 'adoptResult')}</h3>
          ${result.kind === 'historical' ? html`<p>${this.text('historical')}</p>` : nothing}
          <p>${this.text('rule')} <code>${result.ruleId}</code> · ${this.text('revision')} ${result.ruleRevision}</p>
          <p>${this.text('operation')} <code>${result.operationId}</code></p>
        </section>`}
      </div>
    </vyp-ha-card>`;
  }
}
registerButton(); registerCard(); registerFeedback();
customElements.define('domus-automation-daily', DomusAutomationDaily);
declare global {interface HTMLElementTagNameMap {'domus-automation-daily': DomusAutomationDaily;}}
