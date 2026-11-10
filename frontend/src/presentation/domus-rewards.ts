import {LitElement, css, html, nothing} from 'lit';
import type {PropertyValues} from 'lit';
import {live} from 'lit/directives/live.js';
import {registerCard} from '@vypdev/ha-ui/card';
import {cardState} from '@vypdev/ha-ui/card-contracts';
import {registerButton} from '@vypdev/ha-ui/button';
import {buttonState} from '@vypdev/ha-ui/button-contracts';
import {registerFeedback} from '@vypdev/ha-ui/feedback';
import {feedbackState} from '@vypdev/ha-ui/feedback-contracts';
import type {RewardsView} from '../application/rewards-controller';
import {MEMBER_ROLES} from '../domain/administration-commands';
import type {Revision} from '../domain/administration';
import type {MemberRole} from '../domain/administration-commands';
import {displayPoints, minorPoints} from '../domain/point-allocation';
import {hasTaskText} from '../domain/tasks';
import type {Redemption, RewardCommand, RewardOffer, RewardReport} from '../domain/rewards';
import {rewardMessage} from './reward-messages';
import type {RewardMessage} from './reward-messages';
import type {Language} from './messages';

export type RewardsIntent = {readonly type: 'refresh' | 'more' | 'recover'}
  | {readonly type: 'submit'; readonly command: RewardCommand};
interface OfferDraft {readonly title: string; readonly price: string; readonly enabled: boolean; readonly roles: readonly MemberRole[];}
const NEW: OfferDraft = {title: '', price: '', enabled: true, roles: MEMBER_ROLES};

export class DomusRewards extends LitElement {
  static properties = {view: {attribute: false}, language: {attribute: false}, zone: {attribute: false},
    selectedOffer: {state: true}, selectedCancellation: {state: true}, reason: {state: true},
    editing: {state: true}, offerDraft: {state: true}, code: {state: true}, delivered: {state: true}};
  static styles = css`
    :host {display:grid;gap:16px;margin-block:16px;--vyp-ha-surface:var(--surface);--vyp-ha-text:var(--text);
      --vyp-ha-text-secondary:var(--muted);--vyp-ha-border:var(--line);--vyp-ha-primary:var(--accent)}
    h3 {margin:0} form,fieldset,ol {display:grid;gap:10px}
    ol {list-style:none;padding:0;margin:0 0 12px} li+li {border-block-start:1px solid var(--line);padding-block-start:12px}
    li {overflow-wrap:anywhere} li p {margin-block:6px}
    form,fieldset {margin-block:10px} fieldset {border:1px solid var(--line);border-radius:8px}
    label {display:grid;gap:4px;font-weight:650} label:has(input[type=checkbox]) {display:flex;align-items:center;gap:8px}
    input,select,textarea {font:inherit;color:inherit;background:var(--surface);padding:8px;border:1px solid var(--line);
      border-radius:8px;max-width:100%;box-sizing:border-box} input[type=checkbox] {accent-color:var(--accent)}
    .actions {display:flex;flex-wrap:wrap;gap:8px} summary {font-weight:650}
    :focus-visible {outline:3px solid var(--accent);outline-offset:3px}
  `;
  declare view: RewardsView | null;
  declare language: Language;
  declare zone: string;
  private declare selectedOffer: string | null;
  private declare selectedCancellation: string | null;
  private declare reason: string;
  private declare editing: Readonly<{id: string; revision: Revision}> | null;
  private declare offerDraft: OfferDraft;
  private declare code: string;
  private declare delivered: boolean;

  constructor() {
    super(); this.view = null; this.language = 'en'; this.zone = 'UTC';
    this.selectedOffer = null; this.selectedCancellation = null; this.reason = '';
    this.editing = null; this.offerDraft = NEW; this.code = ''; this.delivered = false;
  }
  protected willUpdate(changed: PropertyValues<this>): void {
    if (changed.has('view') && changed.get('view')?.scope.key !== this.view?.scope.key) {
      this.selectedOffer = null; this.selectedCancellation = null; this.reason = '';
      this.editing = null; this.offerDraft = NEW; this.code = ''; this.delivered = false;
    }
  }
  private text(key: RewardMessage): string {return rewardMessage(key, this.language);}
  private points(value: number): string {return displayPoints(value, this.language);}
  private date(value: number): string {
    return new Intl.DateTimeFormat(this.language, {timeZone: this.zone, dateStyle: 'medium', timeStyle: 'short'}).format(value);
  }
  private intent(detail: RewardsIntent): void {
    this.dispatchEvent(new CustomEvent('domus-rewards-intent', {detail, bubbles: true, composed: true}));
  }
  private submit(command: RewardCommand): void {this.intent({type: 'submit', command});}
  private button(key: RewardMessage, action: () => void, disabled: boolean, primary = false) {
    return html`<vyp-ha-button .state=${buttonState({label: this.text(key), variant: primary ? 'primary' : 'outlined'})}
      ?disabled=${disabled} @ha-press-request=${action}></vyp-ha-button>`;
  }
  private submitButton(key: RewardMessage, disabled: boolean) {
    return html`<vyp-ha-button type="submit" .state=${buttonState({label: this.text(key), variant: 'primary'})}
      ?disabled=${disabled}></vyp-ha-button>`;
  }
  private card(key: RewardMessage) {return cardState({title: this.text(key), headingLevel: 3});}

  private catalogEntry(offer: RewardOffer, report: RewardReport, blocked: boolean) {
    const unavailable = !report.enabled ? 'disabled' : !offer.enabled ? 'inactive'
      : !offer.eligible ? 'ineligible' : offer.cost > report.available ? 'unaffordable' : null;
    return html`<li><strong>${offer.title}</strong><p>${this.text('cost')} ${this.points(offer.cost)}</p>
      ${unavailable === null ? this.selectedOffer === offer.id ? html`<form @submit=${(event: SubmitEvent) => {
        event.preventDefault();
        if (!blocked) {
          this.selectedOffer = null;
          this.submit({action: 'reward.request', offer_id: offer.id, expected_revision: offer.revision});
        }
      }}><p>${this.text('remaining')} ${this.points(report.available - offer.cost)}</p>
        <div class="actions">${this.submitButton('confirmRequest', blocked)}
          ${this.button('cancelDraft', () => {this.selectedOffer = null;}, blocked)}</div></form>`
        : this.button('request', () => {this.selectedOffer = offer.id;}, blocked, true)
        : html`<p>${this.text(unavailable)}</p>`}</li>`;
  }

  private requestEntry(request: Redemption, report: RewardReport, blocked: boolean) {
    const open = request.stage !== 'delivered' && request.stage !== 'cancelled';
    const status = request.stage;
    return html`<li><strong>${request.title}</strong> · ${this.text(status)}
      <p>${this.text('cost')} ${this.points(request.cost)} · ${this.text('requestedAt')} ${this.date(request.requestedAt)}</p>
      ${request.approvedAt === null ? nothing : html`<p>${this.text('approvedAt')} ${this.date(request.approvedAt)}</p>`}
      ${request.closedAt === null ? nothing : html`<p>${this.text('closedAt')} ${this.date(request.closedAt)}</p>`}
      ${status === 'funding_hold' ? html`<p>${this.text('hold')}</p>
        <p>${this.text('shortfall')} ${this.points(Math.max(0, -report.available))}</p>` : nothing}
      ${status === 'requested' ? html`<p>${this.text('pendingReview')}</p>` : nothing}
      ${status === 'approved' ? html`<p>${this.text('fundedNext')}</p>` : nothing}
      ${status === 'delivered' ? html`<p>${this.text('spent')} ${this.points(-request.cost)} · ${this.text('released')}</p>` : nothing}
      ${request.cancellationReason === null ? nothing : html`<p>${this.text('released')} · ${request.cancellationReason}</p>`}
      ${open ? html`<p>${this.text('shareCode')} <code>${request.id}</code></p>${
        this.selectedCancellation === request.id ? html`<form @submit=${(event: SubmitEvent) => {
          event.preventDefault();
          if (!blocked && hasTaskText(this.reason)) {
            const reason = this.reason; this.selectedCancellation = null; this.reason = '';
            this.submit({action: 'reward.cancel', redemption_id: request.id, expected_revision: request.revision, reason});
          }
        }}><label>${this.text('cancelReason')}<input .value=${live(this.reason)} maxlength="1000" ?disabled=${blocked}
          @input=${(event: InputEvent) => {this.reason = (event.target as HTMLInputElement).value;}}></label>
          <div class="actions">${this.submitButton('confirmCancel', blocked || !hasTaskText(this.reason))}
          ${this.button('cancelDraft', () => {this.selectedCancellation = null; this.reason = '';}, blocked)}</div></form>`
          : this.button('cancel', () => {this.selectedCancellation = request.id; this.reason = '';}, blocked)}` : nothing}</li>`;
  }

  private editOffer(report: RewardReport, blocked: boolean) {
    const draft = this.offerDraft, cost = minorPoints(draft.price);
    const editing = this.editing;
    const original = report.catalog.find(offer => offer.id === editing?.id);
    const stale = editing !== null && original?.revision !== editing.revision;
    const valid = hasTaskText(draft.title) && cost !== null && cost > 0 && draft.roles.length > 0;
    return html`<form @submit=${(event: SubmitEvent) => {
      event.preventDefault();
      if (!blocked && !stale && valid) this.submit({action: 'reward.offer', offer_id: editing?.id ?? null, title: draft.title,
        cost_minor: cost, enabled: draft.enabled, eligible_roles: draft.roles, expected_revision: editing?.revision ?? '0'});
    }}>
      <label>${this.text('edit')}<select .value=${live(editing?.id ?? '')} ?disabled=${blocked} @change=${(event: Event) => {
        const offer = report.catalog.find(item => item.id === (event.target as HTMLSelectElement).value);
        this.editing = offer === undefined ? null : {id: offer.id, revision: offer.revision};
        this.offerDraft = offer === undefined ? NEW : {title: offer.title, price: (offer.cost / 100).toFixed(2), enabled: offer.enabled, roles: offer.roles};
      }}><option value="">${this.text('newOffer')}</option>
        ${report.catalog.map(offer => html`<option .value=${offer.id}>${offer.title}</option>`)}</select></label>
      <label>${this.text('offerTitle')}<input maxlength="160" .value=${live(draft.title)} ?disabled=${blocked}
        @input=${(event: InputEvent) => {this.offerDraft = {...this.offerDraft, title: (event.target as HTMLInputElement).value};}}></label>
      <label>${this.text('price')}<input inputmode="decimal" maxlength="8" .value=${live(draft.price)} ?disabled=${blocked}
        @input=${(event: InputEvent) => {this.offerDraft = {...this.offerDraft, price: (event.target as HTMLInputElement).value};}}></label>
      <label><input type="checkbox" .checked=${draft.enabled} ?disabled=${blocked} @change=${(event: Event) => {
        this.offerDraft = {...this.offerDraft, enabled: (event.target as HTMLInputElement).checked};
      }}>${this.text('offerEnabled')}</label>
      <fieldset ?disabled=${blocked}><legend>${this.text('eligibility')}</legend>
        ${MEMBER_ROLES.map(role => html`<label><input type="checkbox" .checked=${draft.roles.includes(role)} @change=${(event: Event) => {
          const checked = (event.target as HTMLInputElement).checked;
          this.offerDraft = {...this.offerDraft, roles: MEMBER_ROLES.filter(item => item === role ? checked : this.offerDraft.roles.includes(item))};
        }}>${this.text(role)}</label>`)}
      </fieldset>
      ${stale ? html`<p role="status">${this.text('revision_conflict')}</p>
        ${this.button('cancelDraft', () => {this.editing = null; this.offerDraft = NEW;}, blocked)}` : nothing}
      ${this.submitButton('saveOffer', blocked || stale || !valid)}
    </form>`;
  }

  private management(report: RewardReport, blocked: boolean) {
    const code = this.code.trim(), valid = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/u.test(code);
    return html`<vyp-ha-card .state=${this.card('admin')}>
      ${this.button(report.enabled ? 'disable' : 'enable', () => this.submit({
        action: 'reward.configure', enabled: !report.enabled, expected_revision: report.revision,
      }), blocked)}
      ${this.editOffer(report, blocked)}
      <fieldset ?disabled=${blocked}><legend>${this.text('review')}</legend>
        <p>${this.text('codeHelp')}</p><label>${this.text('code')}<input maxlength="128" .value=${live(this.code)}
          @input=${(event: InputEvent) => {this.code = (event.target as HTMLInputElement).value; this.delivered = false;}}></label>
        ${this.button('approve', () => this.submit({action: 'reward.approve', redemption_id: code}), blocked || !valid)}
        <label><input type="checkbox" .checked=${this.delivered} ?disabled=${!valid} @change=${(event: Event) => {
          this.delivered = (event.target as HTMLInputElement).checked;
        }}>${this.text('deliveredCheck')}</label>
        ${this.button('deliver', () => {
          this.delivered = false; this.submit({action: 'reward.deliver', redemption_id: code});
        }, blocked || !valid || !this.delivered)}
      </fieldset>
    </vyp-ha-card>`;
  }

  protected render() {
    const view = this.view;
    if (view === null) return nothing;
    const report = view.report, result = view.result, blocked = view.scope.readOnly || view.busy || view.pending;
    const feedback = result === null ? view.notice : result.kind === 'rejected' ? result.reason
      : result.kind === 'historical' ? 'historical' : result.stage ?? 'saved';
    return html`<h3>${this.text('rewards')}</h3>
      ${feedback === null ? nothing : html`<vyp-ha-feedback .state=${feedbackState({kind: 'notice',
        tone: view.notice || result?.kind === 'rejected' ? 'warning' : 'info', message: this.text(feedback)})}></vyp-ha-feedback>`}
      ${view.busy && report === null ? html`<vyp-ha-feedback .state=${feedbackState({kind: 'loading', message: this.text('loading')})}></vyp-ha-feedback>` : nothing}
      <div class="actions">${this.button('refresh', () => this.intent({type: 'refresh'}), view.busy)}
        ${view.pending ? this.button('recover', () => this.intent({type: 'recover'}), view.busy) : nothing}</div>
      ${report === null ? nothing : html`
        <vyp-ha-card .state=${this.card('catalog')}>
          ${report.enabled ? nothing : html`<p>${this.text('disabled')}</p>`}
          ${report.catalog.length === 0 ? html`<p>${this.text('noOffers')}</p>`
            : html`<ol>${report.catalog.map(offer => this.catalogEntry(offer, report, blocked))}</ol>`}
        </vyp-ha-card>
        <vyp-ha-card .state=${this.card('ownRequests')}>
          ${report.requests.length === 0 ? html`<p>${this.text('empty')}</p>`
            : html`<ol>${report.requests.map(request => this.requestEntry(request, report, blocked))}</ol>`}
          ${report.cursor === null ? nothing : this.button('requestsMore', () => this.intent({type: 'more'}), view.busy)}
        </vyp-ha-card>
        ${report.mayManage ? this.management(report, blocked) : nothing}`}
    `;
  }
}
registerCard(); registerButton(); registerFeedback();
customElements.define('domus-rewards', DomusRewards);
declare global {interface HTMLElementTagNameMap {'domus-rewards': DomusRewards;}}
