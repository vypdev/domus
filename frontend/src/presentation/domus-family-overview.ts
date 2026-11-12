import {LitElement, css, html, nothing} from 'lit';
import {registerButton} from '@vypdev/ha-ui/button';
import {buttonState} from '@vypdev/ha-ui/button-contracts';
import {registerCard} from '@vypdev/ha-ui/card';
import {cardState} from '@vypdev/ha-ui/card-contracts';
import {registerFeedback} from '@vypdev/ha-ui/feedback';
import {feedbackState} from '@vypdev/ha-ui/feedback-contracts';
import type {FamilyOverviewView} from '../application/family-controller';
import {displayPoints} from '../domain/point-allocation';
import type {Language} from './messages';

const COPY = {
  en: {
    title: 'Your participation this week',
    earned: 'Earned points',
    completed: 'Completed tasks',
    loading: 'Loading weekly participation…',
    denied: 'Your current household access does not allow viewing participation.',
    unavailable: 'Weekly participation could not be loaded.',
    retry: 'Retry participation summary',
    open: 'Open Family',
  },
  es: {
    title: 'Tu participación esta semana',
    earned: 'Puntos ganados',
    completed: 'Tareas completadas',
    loading: 'Cargando la participación semanal…',
    denied: 'Tu acceso actual al hogar no permite ver la participación.',
    unavailable: 'No se pudo cargar la participación semanal.',
    retry: 'Volver a cargar la participación',
    open: 'Abrir Familia',
  },
} as const;

export class DomusFamilyOverview extends LitElement {
  static properties = {view: {attribute: false}, language: {attribute: false}};
  static styles = css`
    :host {display:block;--vyp-ha-surface:var(--surface);--vyp-ha-surface-raised:var(--surface);
      --vyp-ha-text:var(--text);--vyp-ha-text-secondary:var(--muted);--vyp-ha-border:var(--line);
      --vyp-ha-primary:var(--accent);--vyp-ha-focus-ring:3px solid var(--accent)}
    vyp-ha-card {margin-block-start:16px}
    vyp-ha-card::part(heading) {text-wrap:balance}
    p {margin:0 0 12px;color:var(--muted)}
    dl {display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px 16px;margin:0}
    dd {margin:0;font-weight:650;font-variant-numeric:tabular-nums}
    a {display:inline-flex;align-items:center;min-height:44px;margin-block-start:8px;color:var(--accent)}
    a:focus-visible {outline:3px solid var(--accent);outline-offset:3px}
    vyp-ha-feedback + vyp-ha-button {margin-block-start:8px}
  `;

  declare view: FamilyOverviewView | null;
  declare language: Language;

  constructor() {super(); this.view = null; this.language = 'en';}

  protected render() {
    const view = this.view;
    if (view === null) return nothing;
    const copy = COPY[this.language];
    return html`<vyp-ha-card .state=${cardState({title:copy.title, headingLevel:2})}>
      ${view.state === 'ready' ? html`
        <p>${new Intl.DateTimeFormat(this.language, {timeZone:'UTC', dateStyle:'medium'}).formatRange(
          Date.parse(view.data.period.start), Date.parse(view.data.period.end) - 86_400_000)}</p>
        <dl>
          <dt>${copy.completed}</dt><dd>${new Intl.NumberFormat(this.language).format(view.data.completed)}</dd>
          <dt>${copy.earned}</dt><dd>${displayPoints(view.data.earned, this.language, 2)}</dd>
        </dl>
        <a href="#family">${copy.open}</a>` : html`
        <vyp-ha-feedback .state=${view.state === 'loading'
          ? feedbackState({kind:'loading', message:copy.loading})
          : feedbackState({kind:'notice', tone:'warning', message:copy[view.state]})}></vyp-ha-feedback>
        ${view.state === 'unavailable' ? html`<vyp-ha-button
          .state=${buttonState({label:copy.retry, variant:'outlined'})}
          @ha-press-request=${() => this.dispatchEvent(new Event('domus-family-overview-retry', {
            bubbles:true, composed:true,
          }))}></vyp-ha-button>` : nothing}`}
    </vyp-ha-card>`;
  }
}

registerButton(); registerCard(); registerFeedback();
customElements.define('domus-family-overview', DomusFamilyOverview);
declare global {interface HTMLElementTagNameMap {'domus-family-overview': DomusFamilyOverview;}}
