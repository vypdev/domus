import {LitElement, css, html, nothing} from 'lit';
import type {TemplateResult} from 'lit';
import {registerButton} from '@vypdev/ha-ui/button';
import {buttonState} from '@vypdev/ha-ui/button-contracts';
import {registerCard} from '@vypdev/ha-ui/card';
import {cardState} from '@vypdev/ha-ui/card-contracts';
import {registerFeedback} from '@vypdev/ha-ui/feedback';
import {feedbackState} from '@vypdev/ha-ui/feedback-contracts';
import type {AutomationDraftIntent, AutomationDraftView, DraftCondition} from '../application/automation-drafts';
import type {Language} from './messages';

const COPY = {
  en: {
    heading: 'Automation drafts', loading: 'Loading automation drafts…',
    empty: 'Enter a task title above and save your first draft.',
    first: 'First drafts', next: 'Next drafts', retry: 'Try again', open: 'Open',
    save: 'Save draft', new: 'New draft', revision: 'Revision', inactive: 'Inactive',
    denied: 'Your current household permissions do not allow access to automation drafts.',
    unavailable: 'Automation drafts are unavailable. Try again.',
    invalid_title: 'Enter a task title of 1 to 160 characters.',
    uncertain: 'The save result is uncertain. Check the original request to recover it.',
    rejected: 'The draft could not be saved. Check its title and selected product and try again.',
    conflict: 'Another save changed this draft. Review its latest revision before saving your edits.',
    saved: 'Draft saved.', historical: 'This save was processed before restoration. Review the current draft list.',
    recover: 'Check original save', review: 'Review latest revision', rebase: 'Keep edits on latest revision',
    current: 'Current draft', operation: 'Operation ID', busy: 'Checking automation drafts…',
    noCondition: 'No stock condition',
    complex: 'This draft uses grouped conditions. You can open and preview the saved rule here.',
    product: 'Stock below minimum', all: 'All conditions', any: 'Any condition', not: 'Negated condition',
    preview_saved: 'Preview saved rule', wouldCreate: 'Would create this task', noAction: 'No task would be created',
    readOnly: 'Saving drafts is unavailable in the current read-only session.',
  },
  es: {
    heading: 'Borradores de automatización', loading: 'Cargando borradores de automatización…',
    empty: 'Introduce un título de tarea arriba y guarda tu primer borrador.',
    first: 'Primeros borradores', next: 'Siguientes borradores', retry: 'Volver a intentar', open: 'Abrir',
    save: 'Guardar borrador', new: 'Nuevo borrador', revision: 'Revisión', inactive: 'Inactivo',
    denied: 'Tus permisos actuales del hogar no permiten acceder a los borradores de automatización.',
    unavailable: 'Los borradores de automatización no están disponibles. Vuelve a intentarlo.',
    invalid_title: 'Introduce un título de tarea de 1 a 160 caracteres.',
    uncertain: 'No se pudo confirmar el guardado. Consulta la solicitud original para recuperarlo.',
    rejected: 'No se pudo guardar el borrador. Revisa el título y el producto seleccionado y vuelve a intentarlo.',
    conflict: 'Otro guardado cambió este borrador. Revisa la última revisión antes de guardar tus cambios.',
    saved: 'Borrador guardado.', historical: 'El guardado se procesó antes de la restauración. Revisa la lista actual de borradores.',
    recover: 'Consultar guardado original', review: 'Revisar la última revisión', rebase: 'Mantener mis cambios sobre la última revisión',
    current: 'Borrador actual', operation: 'Identificador de operación', busy: 'Consultando borradores…',
    noCondition: 'Sin condición de existencias',
    complex: 'Este borrador usa condiciones agrupadas. Aquí puedes abrir y previsualizar la regla guardada.',
    product: 'Existencias por debajo del mínimo', all: 'Todas las condiciones', any: 'Cualquier condición', not: 'Negación de la condición',
    preview_saved: 'Previsualizar regla guardada', wouldCreate: 'Se crearía esta tarea', noAction: 'No se crearía ninguna tarea',
    readOnly: 'El guardado de borradores no está disponible en esta sesión de solo lectura.',
  },
} as const;

type CopyKey = keyof typeof COPY.en;
type Ready = Extract<AutomationDraftView, {state: 'ready'}>;

export class DomusAutomationDrafts extends LitElement {
  static properties = {view: {attribute: false}, language: {attribute: false}, canEdit: {attribute: false}};
  static styles = css`
    :host {display:block;--vyp-ha-surface:var(--surface);--vyp-ha-surface-raised:var(--surface);--vyp-ha-text:var(--text);
      --vyp-ha-text-secondary:var(--muted);--vyp-ha-border:var(--line);--vyp-ha-primary:var(--accent);
      --vyp-ha-on-accent:var(--surface);--vyp-ha-focus-ring:3px solid var(--accent)}
    vyp-ha-card {margin-block-end:16px}
    .content, .drafts {display:grid;gap:10px}
    .actions, .draft {display:flex;align-items:center;flex-wrap:wrap;gap:8px}
    .draft {justify-content:space-between;border-block-start:1px solid var(--line);padding-block-start:8px}
    .draft p {flex:1 1 17rem}
    p,ul {margin:0;overflow-wrap:anywhere}
    .drafts {list-style:none;padding:0}
  `;

  declare view: AutomationDraftView | null;
  declare language: Language;
  declare canEdit: boolean;

  constructor() {super(); this.view = null; this.language = 'en'; this.canEdit = false;}

  private text(key: CopyKey): string {return COPY[this.language][key];}

  private button(key: CopyKey, intent: AutomationDraftIntent, disabled: boolean, title?: string) {
    const label = title === undefined ? this.text(key) : this.text(key) + ' ' + title.replace(/[\u007f-\u009f]/gu, '�');
    return html`<vyp-ha-button .state=${buttonState({label, variant: key === 'save' ? 'primary' : 'outlined'})}
      ?disabled=${disabled} @ha-press-request=${() => this.dispatchEvent(new CustomEvent<AutomationDraftIntent>(
        'domus-automation-draft-intent', {detail: intent, bubbles: true, composed: true}))}></vyp-ha-button>`;
  }

  private feedback(key: CopyKey, loading = false) {
    return html`<vyp-ha-feedback .state=${loading
      ? feedbackState({kind: 'loading', message: this.text(key)})
      : feedbackState({kind: 'notice', tone: key === 'saved' ? 'success' : 'warning',
        message: this.text(key)})}></vyp-ha-feedback>`;
  }

  private describe(condition: DraftCondition): TemplateResult {
    switch (condition.kind) {
      case 'stock_below_minimum':
        return html`<li>${this.text('product')} · ${condition.product_id}</li>`;
      case 'not':
        return html`<li>${this.text('not')}<ul>${this.describe(condition.child)}</ul></li>`;
      default:
        return html`<li>${this.text(condition.kind)}<ul>${condition.children.map(value => this.describe(value))}</ul></li>`;
    }
  }

  private controls(view: Ready) {
    const busy = view.busy || view.pending;
    return html`<div class="actions">
      ${this.button('save', {type: 'save'}, busy || view.readOnly || !this.canEdit || view.locked !== null || view.notice === 'conflict')}
      ${view.selected === null ? nothing : this.button('new', {type: 'new'}, busy || !this.canEdit)}
      ${view.pending ? this.button('recover', {type: 'recover'}, view.busy) : nothing}
    </div>
    ${view.selected === null ? nothing : html`<p role="status">${this.text('current')} ·
      ${this.text('revision')} ${view.selected.revision} · ${this.text('inactive')}</p>`}
    ${view.readOnly ? html`<p>${this.text('readOnly')}</p>` : nothing}
    ${view.busy ? this.feedback('busy', true) : nothing}
    ${view.notice === null ? nothing : this.feedback(view.notice)}
    ${view.operationId === null ? nothing : html`<p>${this.text('operation')} <code>${view.operationId}</code></p>`}
    ${view.notice === 'conflict' ? this.button('review', {type: 'review'}, busy) : nothing}
    ${view.competing === null ? nothing : html`<div class="content">
      <p>${view.competing.title} · ${this.text('revision')} ${view.competing.revision}</p>
      ${view.competing.condition === null ? html`<p>${this.text('noCondition')}</p>`
        : html`<ul>${this.describe(view.competing.condition)}</ul>`}
      <div class="actions">${this.button('rebase', {type: 'rebase'}, busy || view.readOnly || !this.canEdit
        || (view.competing.condition !== null && view.competing.condition.kind !== 'stock_below_minimum'))}</div>
    </div>`}
    ${view.locked === null ? nothing : html`<p><strong>${view.locked.title}</strong></p>
      <p>${this.text('complex')}</p>
      <ul>${view.locked.condition === null ? nothing : this.describe(view.locked.condition)}</ul>
      <div class="actions">${this.button('preview_saved', {type: 'preview_saved'}, busy || !this.canEdit)}</div>
      ${view.preview === null ? nothing : html`<p role="status">${this.text(view.preview ? 'wouldCreate' : 'noAction')}</p>`}`}
    ${view.page.drafts.length === 0 ? html`<p>${this.text('empty')}</p>` : html`<ul class="drafts">
      ${view.page.drafts.map(draft => html`<li class="draft">
        <p><strong>${draft.title}</strong> · ${this.text('revision')} ${draft.revision} · ${this.text('inactive')}</p>
        ${this.button('open', {type: 'open', id: draft.id}, busy, draft.title)}
      </li>`)}
    </ul>`}
    ${view.after !== null || view.page.next !== null ? html`<div class="actions">
      ${view.after === null ? nothing : this.button('first', {type: 'first'}, view.busy)}
      ${view.page.next === null ? nothing : this.button('next', {type: 'next'}, view.busy)}
    </div>` : nothing}`;
  }

  protected render() {
    const view = this.view;
    if (view === null) return nothing;
    return html`<vyp-ha-card .state=${cardState({title: this.text('heading'), headingLevel: 2})}>
      <div class="content">${view.state === 'ready' ? this.controls(view)
        : this.feedback(view.state, view.state === 'loading')}
      ${view.state === 'unavailable' ? this.button('retry', {type: 'retry'}, false) : nothing}</div>
    </vyp-ha-card>`;
  }
}

registerButton(); registerCard(); registerFeedback();
customElements.define('domus-automation-drafts', DomusAutomationDrafts);
declare global {interface HTMLElementTagNameMap {'domus-automation-drafts': DomusAutomationDrafts;}}
