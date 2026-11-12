import {LitElement, css, html, nothing} from 'lit';
import {live} from 'lit/directives/live.js';
import type {PropertyValues} from 'lit';
import {registerField} from '@vypdev/ha-ui/field';
import type {FieldValueEvent} from '@vypdev/ha-ui/field';
import {textFieldState} from '@vypdev/ha-ui/field-contracts';
import type {TaskView} from '../application/task-controller';
import type {TaskRecord} from '../application/task-ports';
import {categoryLabel, hasTaskText, taskQuantity, taskScheduleDraft, TASK_PRIORITIES, TASK_TEXT_LIMITS} from '../domain/tasks';
import type {Revision} from '../domain/administration';
import type {TaskCategory, TaskDetail, TaskMaterialUsage, TaskPriority, TaskScheduleDraft} from '../domain/tasks';
import {language} from './messages';
import type {Language} from './messages';
import {taskDeadline, taskInstant, taskMessage} from './task-messages';
import type {TaskMessageKey} from './task-messages';
import {styles} from './styles';
import type {AllocationView} from '../application/allocation-controller';
import {displayPoints, minorPoints, requiresManualAllocation} from '../domain/point-allocation';
import type {ReviewedAllocation} from '../domain/point-allocation';
import type {ParticipantName} from './allocation-details';
import './domus-allocation-preview';
import './domus-allocation-settings';
export type TaskIntent = Readonly<{type: 'refresh' | 'more' | 'claim'}>
  | Readonly<{type: 'select'; occurrenceId: string}>
  | Readonly<{type: 'create'; title: string; description: string; priority: TaskPriority;
    categoryId?: string; schedule?: TaskScheduleDraft; basePointsMinor?: number}>
  | Readonly<{type: 'createCategory'; label: string}>
  | Readonly<{type: 'renameCategory'; categoryId: string; revision: Revision; label: string}>
  | Readonly<{type: 'archiveCategory'; categoryId: string; revision: Revision}>
  | Readonly<{type: 'complete'; materialUsages: readonly TaskMaterialUsage[] | null; reviewed?: ReviewedAllocation}>
  | Readonly<{type: 'verify'; decision: 'approved' | 'rejected'; reason: string}>
  | Readonly<{type: 'reopen'; reason: string}>
  | Readonly<{type: 'recover' | 'dismiss'; key: string}>;
const EMPTY_SCHEDULE_FIELDS = Object.freeze({date: '', time: '', rule: '', interval: '30', visibility: 'at_completion'});
type ScheduleFields = {[Field in keyof typeof EMPTY_SCHEDULE_FIELDS]: string};
function validCategoryLabel(value: string): boolean {
  try {categoryLabel(value); return true;} catch {return false;}
}
function quantityInput(value: string, precision: number): string | null {
  const trimmed = value.trim();
  if (trimmed.length > 64 || !/^[0-9]+(?:[.,][0-9]+)?$/u.test(trimmed)) return null;
  const [whole, fraction = ''] = trimmed.replace(',', '.').split('.');
  const integer = whole.replace(/^0+(?=[0-9])/u, ''), decimal = fraction.replace(/0+$/u, '');
  if (decimal.length > precision) return null;
  try {return taskQuantity(integer + (decimal ? '.' + decimal : ''));} catch {return null;}
}
/** Render only verified task facts; emitted intents never select an actor or grant a permission. */
export class DomusTasks extends LitElement {
  static properties = {allocation: {attribute: false}, participantNames: {attribute: false}, view: {attribute: false}, retired: {attribute: false}, language: {attribute: false}, titleDraft: {state: true}, descriptionDraft: {state: true},
    categoryDraft: {state: true}, categoryName: {state: true}, categoryEdit: {state: true}, manageOpen: {state: true},
    basePointsDraft: {state: true}, basePointsError: {state: true},
    titleRequired: {state: true}, priorityDraft: {state: true}, reasonDraft: {state: true}, quantities: {state: true}, quantityError: {state: true}, createOpen: {state: true},
    scheduleKind: {state: true}, scheduleError: {state: true}, scheduleInput: {state: true}};
  static styles = [styles, css`:host {min-height:0;background:transparent;overflow-wrap:anywhere}.task-header {display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap}
    .task-header h2 {font-size:1.6rem;margin:0} .task-layout {display:grid;gap:20px}.task-layout .card {margin:0}
    .task-layout>div {display:grid;gap:20px;align-content:start} .new-task summary h3 {display:inline} .new-task form {margin-top:20px}
    h3 {font-size:1.1rem;margin:0 0 16px} textarea {font:inherit;resize:vertical;width:100%;min-height:90px;border:1px solid var(--line);border-radius:10px;
    padding:10px 12px;background:var(--surface);color:var(--text)} .task-list {list-style:none;padding:0;margin:0}.task-list li {padding:14px 0;border-bottom:1px solid var(--line)}
    .task-link {border:0;border-radius:8px;padding:4px 0;text-align:start;font-weight:700}.task-meta {display:flex;flex-wrap:wrap;gap:8px;color:var(--muted);font-size:.875rem}
    .description {white-space:pre-wrap}.task-fields {margin-top:24px}.material {display:grid;gap:6px;margin-bottom:12px}.request {margin-top:16px}
    #task-base-points {--vyp-ha-surface:var(--canvas);--vyp-ha-border:var(--line);
      --vyp-ha-text:var(--text);--vyp-ha-text-secondary:var(--muted);
      --vyp-ha-primary:var(--accent);--vyp-ha-danger:var(--warning)}
    @media(min-width:800px) {.task-layout {grid-template-columns:minmax(0,1fr) minmax(0,1fr)}.task-layout.single {grid-template-columns:1fr}}`];
  declare allocation: AllocationView | null;
  declare participantNames: readonly ParticipantName[];
  declare view: TaskView | null;
  declare retired: boolean;
  declare language: Language;
  private declare titleDraft: string;
  private declare categoryDraft: string;
  private declare categoryName: string;
  private declare categoryEdit: TaskCategory | null;
  private declare manageOpen: boolean;
  private declare scheduleInput: ScheduleFields;
  private submittedCategory: Readonly<{action: 'task.category.create' | 'task.category.rename' | 'task.category.archive'; label: string}> | null = null;
  private declare titleRequired: boolean;
  private declare createOpen: boolean;
  private declare descriptionDraft: string;
  private declare basePointsDraft: string;
  private declare basePointsError: boolean;
  private declare priorityDraft: TaskPriority;
  private declare scheduleKind: 'manual' | TaskScheduleDraft['kind'];
  private declare scheduleError: boolean;
  private declare reasonDraft: string;
  private declare quantities: Readonly<Record<string, string>>;
  private declare quantityError: string | null;
  private draftScope: string | null = null;
  private detailKey: string | null = null;
  private submittedDraft: string | null = null;
  private lastForm: 'create' | 'review' | 'category' = 'create';
  private focusDetail = false;
  constructor() {super(); this.allocation = null; this.participantNames = []; this.view = null; this.retired = false; this.language = 'en'; this.titleDraft = ''; this.titleRequired = false; this.descriptionDraft = '';
    this.priorityDraft = 'normal'; this.scheduleKind = 'manual'; this.scheduleError = false; this.scheduleInput = EMPTY_SCHEDULE_FIELDS;
    this.createOpen = false; this.reasonDraft = ''; this.quantities = {}; this.quantityError = null;
    this.basePointsDraft = ''; this.basePointsError = false;
    this.categoryDraft = ''; this.categoryName = ''; this.categoryEdit = null; this.manageOpen = false;}
  private text(key: TaskMessageKey): string {return taskMessage(key, this.language);}
  private get blocked(): boolean {return this.view?.busy !== false || this.view.readOnly || this.view.records === null
    || this.view.records.some(record => record.stage === 'prepared' || record.stage === 'uncertain');}
  private get staleCategory(): boolean {
    return this.categoryDraft !== '' && !this.view?.access?.categoryCatalog?.categories.some(item => item.id === this.categoryDraft);
  }
  private creationDraftKey(): string {
    return JSON.stringify([this.titleDraft, this.descriptionDraft, this.priorityDraft, this.categoryDraft,
      this.basePointsDraft, this.scheduleKind, this.scheduleInput]);
  }
  private reset(): void {
    this.categoryDraft = ''; this.categoryName = ''; this.categoryEdit = null; this.submittedCategory = null; this.manageOpen = false;
    this.createOpen = false; this.titleDraft = ''; this.titleRequired = false; this.descriptionDraft = ''; this.priorityDraft = 'normal'; this.reasonDraft = '';
    this.basePointsDraft = ''; this.basePointsError = false;
    this.scheduleKind = 'manual'; this.scheduleError = false; this.scheduleInput = EMPTY_SCHEDULE_FIELDS; this.quantities = {}; this.quantityError = null; this.detailKey = null; this.focusDetail = false; this.submittedDraft = null; this.draftScope = null;}
  protected willUpdate(changed: PropertyValues<this>): void {
    if (changed.has('retired') && this.retired) this.reset();
    if (!changed.has('view')) return;
    if (this.view?.notice === 'category_unavailable' || this.view?.notice === 'invalid_input' && this.lastForm === 'create')
      this.createOpen = true;
    const next = this.view?.scopeKey;
    if (this.view?.phase === 'closed' || this.view?.notice === 'authentication_required' || this.view?.notice === 'forbidden'
      || next != null && this.draftScope !== null && next !== this.draftScope) this.reset();
    if (next != null) this.draftScope = next;
    const detail = this.view?.detail, key = detail ? JSON.stringify([next, detail.occurrenceId, detail.revision]) : null;
    if (key !== null && key !== this.detailKey) {this.focusDetail = this.view?.phase === 'ready'; this.detailKey = key; this.reasonDraft = ''; this.quantityError = null;
      this.quantities = Object.fromEntries(detail!.materials.map(item => [item.lineId, item.plannedQuantity]));}
    const outcome = this.view?.outcome;
    if (outcome?.kind === 'receipt' && outcome.stage === 'committed' && outcome.action === this.submittedCategory?.action
        && this.categoryName === this.submittedCategory.label) {
      this.categoryName = ''; this.categoryEdit = null; this.submittedCategory = null;
    }
    if (outcome?.kind === 'receipt' && outcome.stage === 'committed' && outcome.action === 'task.create'
        && this.submittedDraft === this.creationDraftKey()) {
      this.categoryDraft = ''; this.createOpen = false; this.titleDraft = ''; this.titleRequired = false; this.descriptionDraft = ''; this.priorityDraft = 'normal'; this.submittedDraft = null;
      this.basePointsDraft = ''; this.basePointsError = false;
      this.scheduleKind = 'manual'; this.scheduleError = false; this.scheduleInput = EMPTY_SCHEDULE_FIELDS;
    }
  }
  protected updated(changed: PropertyValues): void {
    this.lang = language(this.language, 'en');
    if (this.focusDetail) {this.focusDetail = false; this.shadowRoot?.querySelector<HTMLElement>('#selected-task-title')?.focus();}
    if (changed.has('view') && this.view?.notice === 'invalid_input')
      this.shadowRoot?.querySelector<HTMLElement>(this.lastForm === 'create' ? '#task-title' : this.lastForm === 'category' ? '#task-category-label' : '#task-reason')?.focus();
    if (changed.has('view') && this.view?.notice === 'category_unavailable')
      this.renderRoot.querySelector<HTMLSelectElement>('#task-category')?.focus();
    if (changed.has('quantityError') && this.quantityError) this.shadowRoot?.querySelector<HTMLInputElement>('[aria-invalid="true"]')?.focus();
  }
  disconnectedCallback(): void {super.disconnectedCallback(); this.reset();}
  private intent(detail: TaskIntent): void {
    if (this.retired || this.view?.phase !== 'ready' || this.view.busy) return;
    if (['create', 'createCategory', 'renameCategory', 'archiveCategory', 'claim', 'complete', 'verify', 'reopen'].includes(detail.type) && this.blocked) return;
    this.dispatchEvent(new CustomEvent<TaskIntent>('domus-task-intent', {detail: Object.freeze(detail), bubbles: true, composed: true}));
  }
  private scheduleDraft(form: HTMLFormElement): TaskScheduleDraft | undefined {
    if (this.scheduleKind === 'manual') return undefined;
    const data = new FormData(form), date = String(data.get('schedule-date')), time = String(data.get('schedule-time'));
    const start = time ? {kind: 'time', local: date + 'T' + time} : {kind: 'date', local: date};
    return taskScheduleDraft(this.scheduleKind === 'fixed'
      ? {kind: 'fixed', start, rrule: data.get('schedule-rule')}
      : {kind: 'relative', start, interval_days: Number(data.get('schedule-interval')), visibility: data.get('schedule-visibility')});
  }
  private rememberSchedule(field: keyof ScheduleFields, event: Event): void {
    this.scheduleInput = {...this.scheduleInput, [field]: (event.target as HTMLInputElement | HTMLSelectElement).value};
  }
  private scheduleFields() {
    const policy = this.view!.access!.schedulePolicy;
    if (policy === undefined) return nothing;
    return html`<div class="field"><label for="task-schedule">${this.text('schedule')}</label>
      <select id="task-schedule" .value=${this.scheduleKind} ?disabled=${this.view!.busy}
        @change=${(event: Event) => {this.scheduleKind = (event.target as HTMLSelectElement).value as typeof this.scheduleKind; this.scheduleError = false;}}>
        ${(['manual','fixed','relative'] as const).map(kind => html`<option value=${kind} .selected=${kind === this.scheduleKind}>${this.text(`schedule_${kind}`)}</option>`)}
      </select></div>
      ${this.scheduleKind === 'manual' ? nothing : html`<fieldset ?disabled=${this.view!.busy}>
        <legend>${this.text('scheduleDetails')}</legend>
        <p>${this.text('scheduleZone')} ${policy.zone}</p>
        <label>${this.text('scheduleDate')} <input type="date" min="1970-01-01" max="9999-12-31" name="schedule-date" .value=${live(this.scheduleInput.date)}
          @input=${(event: Event) => this.rememberSchedule('date', event)} required></label>
        <label>${this.text('scheduleTime')} <input type="time" name="schedule-time" .value=${live(this.scheduleInput.time)}
          @input=${(event: Event) => this.rememberSchedule('time', event)}></label>
        ${this.scheduleKind === 'fixed' ? html`
          <label>${this.text('scheduleRule')} <input type="text" name="schedule-rule" .value=${live(this.scheduleInput.rule)}
          @input=${(event: Event) => this.rememberSchedule('rule', event)} placeholder="FREQ=WEEKLY" maxlength="2048" required></label>` : html`
          <label>${this.text('scheduleInterval')} <input type="number" name="schedule-interval" .value=${live(this.scheduleInput.interval)}
          @input=${(event: Event) => this.rememberSchedule('interval', event)} min="1" max="36600" required></label>
          <label for="task-schedule-visibility">${this.text('scheduleVisibility')}</label>
          <select id="task-schedule-visibility" name="schedule-visibility"
            @change=${(event: Event) => this.rememberSchedule('visibility', event)}>
            <option value="at_completion" .selected=${this.scheduleInput.visibility === 'at_completion'}>${this.text('scheduleCompletion')}</option>
            <option value="at_verification" .selected=${this.scheduleInput.visibility === 'at_verification'}>${this.text('scheduleApproval')}</option>
          </select>`}
        ${this.scheduleError ? html`<p role="alert">${this.text('scheduleInvalid')}</p>` : nothing}
      </fieldset>`}`;
  }
  private createForm() {
    // Native maxlength counts UTF-16 units; the form enforces the shared code-point limits.
    const titleTooLong = Array.from(this.titleDraft).length > TASK_TEXT_LIMITS.title;
    const titleMissing = this.titleRequired && !hasTaskText(this.titleDraft);
    const descriptionInvalid = Array.from(this.descriptionDraft).length > TASK_TEXT_LIMITS.description;
    const canSetPoints = this.view!.access!.canConfigure === true;
    const stalePoints = !canSetPoints && this.basePointsDraft.trim() !== '';
    return html`<details class="card new-task" ?open=${this.createOpen || this.view!.page?.items.length === 0}
      @toggle=${(event: Event) => {const target = event.target as HTMLDetailsElement; if (target.isConnected) this.createOpen = target.open;}}><summary><h3 id="new-task-title">${this.text('newTask')}</h3></summary>
      <form novalidate @submit=${(event: SubmitEvent) => {event.preventDefault(); this.lastForm = 'create';
        if (stalePoints) return;
        this.titleRequired = !hasTaskText(this.titleDraft);
        if (this.titleRequired || titleTooLong || descriptionInvalid || this.staleCategory) {
          this.shadowRoot?.querySelector<HTMLElement>(this.titleRequired || titleTooLong ? '#task-title' : descriptionInvalid ? '#task-description' : '#task-category')?.focus(); return;
        }
        const basePointsMinor = this.basePointsDraft.trim() === '' ? undefined : minorPoints(this.basePointsDraft);
        if (basePointsMinor === null) {
          this.basePointsError = true;
          this.renderRoot.querySelector<HTMLElement>('#task-base-points')?.focus();
          return;
        }
        let schedule: TaskScheduleDraft | undefined;
        try {schedule = this.scheduleDraft(event.currentTarget as HTMLFormElement);}
        catch {this.scheduleError = true; return;}
        this.scheduleError = false;
        this.submittedDraft = this.creationDraftKey();
        this.intent({type: 'create', title: this.titleDraft, description: this.descriptionDraft, priority: this.priorityDraft,
          ...this.categoryDraft ? {categoryId: this.categoryDraft} : {}, ...schedule === undefined ? {} : {schedule},
          ...basePointsMinor === undefined ? {} : {basePointsMinor}});}}>
        <div class="field"><label for="task-title">${this.text('taskTitle')}</label><input id="task-title" type="text" required maxlength=${TASK_TEXT_LIMITS.title * 2} aria-invalid=${titleMissing || titleTooLong ? 'true' : 'false'} autocomplete="off"
          .value=${live(this.titleDraft)} ?disabled=${this.view!.busy} aria-describedby="task-title-help"
          @input=${(event: InputEvent) => {this.titleDraft = (event.target as HTMLInputElement).value;}}><small id="task-title-help" aria-live="polite">${titleMissing ? this.text('titleRequired') : titleTooLong ? this.text('textTooLong') + ': ' + TASK_TEXT_LIMITS.title : this.text('titleHelp')}</small></div>
        <div class="field"><label for="task-description">${this.text('description')}</label><textarea id="task-description" maxlength=${TASK_TEXT_LIMITS.description * 2} aria-invalid=${descriptionInvalid ? 'true' : 'false'}
          .value=${live(this.descriptionDraft)} ?disabled=${this.view!.busy} aria-describedby="task-description-help"
          @input=${(event: InputEvent) => {this.descriptionDraft = (event.target as HTMLTextAreaElement).value;}}></textarea><small id="task-description-help">${descriptionInvalid ? this.text('textTooLong') + ': ' + TASK_TEXT_LIMITS.description : this.text('descriptionHelp')}</small></div>
        <div class="field"><label for="task-priority">${this.text('priority')}</label><select id="task-priority" ?disabled=${this.view!.busy}
          @change=${(event: Event) => {this.priorityDraft = (event.target as HTMLSelectElement).value as TaskPriority;}}>
          ${TASK_PRIORITIES.map(priority => html`<option value=${priority} .selected=${this.priorityDraft === priority}>${this.text(`priority_${priority}`)}</option>`)}</select></div>
        ${this.scheduleFields()}
        ${this.view?.access?.categoryCatalog ? this.categorySelector() : nothing}
        ${canSetPoints ? this.basePointsField() : nothing}
        ${stalePoints ? html`<p role="alert">${this.text('basePointsUnavailable')}</p>
          <button type="button" @click=${() => {this.basePointsDraft = ''; this.basePointsError = false;}}>
            ${this.text('clearBasePoints')}</button>` : nothing}
        <button type="submit" class="primary" ?disabled=${this.blocked || titleTooLong || descriptionInvalid || this.staleCategory || stalePoints}>${this.text('create')}</button>
      </form></details>`;
  }
  private basePointsField() {
    return html`<vyp-ha-field id="task-base-points" .value=${this.basePointsDraft} ?disabled=${this.view!.busy}
      .state=${textFieldState({label: this.text('basePointsOptional'), description: this.text('basePointsHelp'), inputMode: 'decimal',
        error: this.basePointsError ? this.text('basePointsInvalid') : ''})}
      @ha-value-request=${(event: FieldValueEvent) => {
        this.basePointsDraft = event.detail.value;
        this.basePointsError = false;
      }}></vyp-ha-field>`;
  }
  private categorySelector() {
    const categories = this.view!.access!.categoryCatalog!.categories;
    return html`<div class="field"><label for="task-category">${this.text('category')}</label>
      <select id="task-category" ?disabled=${this.view!.busy} aria-invalid=${this.staleCategory} aria-describedby="task-category-help"
        @change=${(event: Event) => {this.categoryDraft = (event.target as HTMLSelectElement).value;}}>
        <option value="" .selected=${this.categoryDraft === ''}>${this.text('unclassified')}</option>
        ${this.staleCategory ? html`<option value=${this.categoryDraft} selected disabled>${this.text('notice_category_unavailable')}</option>` : nothing}
        ${categories.map(item => html`<option value=${item.id} .selected=${item.id === this.categoryDraft}>${item.label}</option>`)}
      </select><small id="task-category-help" aria-live="polite">${this.text(this.staleCategory ? 'notice_category_unavailable' : 'categoryHelp')}</small></div>`;
  }
  private manageCategories() {
    const categories = this.view!.access!.categoryCatalog!.categories, selected = this.categoryEdit;
    const current = categories.find(item => item.id === selected?.id);
    const stale = selected !== null && selected.revision !== current?.revision;
    const valid = validCategoryLabel(this.categoryName);
    return html`<details class="card new-task" ?open=${this.manageOpen}
      @toggle=${(event: Event) => {const target = event.target as HTMLDetailsElement; if (target.isConnected) this.manageOpen = target.open;}}>
      <summary><h3>${this.text('categories')}</h3></summary>
      <form @submit=${(event: SubmitEvent) => {
        event.preventDefault();
        if (!valid || stale) return;
        this.lastForm = 'category';
        this.submittedCategory = {action: selected ? 'task.category.rename' : 'task.category.create', label: this.categoryName};
        this.intent(selected ? {type: 'renameCategory', categoryId: selected.id, revision: selected.revision, label: this.categoryName}
          : {type: 'createCategory', label: this.categoryName});
      }}>
        <div class="field"><label for="manage-task-category">${this.text('manageCategory')}</label>
          <select id="manage-task-category" ?disabled=${this.view!.busy}
            @change=${(event: Event) => {
              const id = (event.target as HTMLSelectElement).value;
              this.categoryEdit = categories.find(item => item.id === id) ?? null;
              this.categoryName = this.categoryEdit?.label ?? '';
            }}>
            <option value="" .selected=${selected === null}>${this.text('newCategory')}</option>
            ${selected !== null && current === undefined ? html`<option value=${selected.id} selected disabled>${selected.label}</option>` : nothing}
            ${categories.map(item => html`<option value=${item.id} .selected=${item.id === selected?.id}>${item.label}</option>`)}
          </select>
        </div>
        <div class="field"><label for="task-category-label">${this.text('categoryName')}</label>
          <input id="task-category-label" type="text" required maxlength="512" autocomplete="off"
            .value=${live(this.categoryName)} ?disabled=${this.view!.busy} aria-invalid=${this.categoryName.length > 0 && !valid}
            aria-describedby="category-name-help" @input=${(event: InputEvent) => {this.categoryName = (event.target as HTMLInputElement).value;}}>
          <small id="category-name-help">${this.text('categoryNameHelp')}</small>
        </div>
        ${stale ? html`<p role="alert">${this.text('categoryChanged')}</p>
          ${current ? html`<button type="button" @click=${() => {this.categoryEdit = current;}}>${this.text('reloadCategory')}</button>` : nothing}` : nothing}
        <div class="actions">
          <button type="submit" ?disabled=${this.blocked || stale || !valid}>${this.text(selected ? 'renameCategory' : 'newCategory')}</button>
          ${selected ? html`<button type="button" ?disabled=${this.blocked || stale} @click=${() => {
            this.submittedCategory = {action: 'task.category.archive', label: this.categoryName};
            this.intent({type: 'archiveCategory', categoryId: selected.id, revision: selected.revision});
          }}>${this.text('archiveCategory')}</button>` : nothing}
        </div>
      </form>
    </details>`;
  }
  private allocationFor(work: TaskDetail): AllocationView | null {
    const allocation = this.allocation, selected = allocation?.scope.work;
    return selected?.occurrenceId === work.occurrenceId && selected.revision === work.revision ? allocation : null;
  }
  private completionReview(work: TaskDetail, allocation: AllocationView | null) {
    const preview = allocation === null ? null : this.renderRoot.querySelector('domus-allocation-preview');
    const reviewed = preview?.reviewed;
    const manual = requiresManualAllocation(allocation?.settings, work.completionPoints === 'manual');
    const blocked = allocation?.busy === true || (manual || preview?.needsReview === true) && reviewed === undefined;
    return {reviewed, blocked};
  }
  private complete(): void {
    const work = this.view!.detail!;
    const {reviewed, blocked} = this.completionReview(work, this.allocationFor(work));
    if (blocked) return;
    let materialUsages: readonly TaskMaterialUsage[] | null = null;
    if (work.materialRecording === 'review_on_completion' && work.materials.length > 0) {
      const usages: TaskMaterialUsage[] = [];
      for (const material of work.materials) {
        const quantity = quantityInput(this.quantities[material.lineId] ?? '', material.precision);
        if (quantity === null) {this.quantityError = material.lineId; return;}
        usages.push(Object.freeze({line_id: material.lineId, quantity}));
      }
      materialUsages = Object.freeze(usages);
    }
    this.quantityError = null; this.intent({type: 'complete', materialUsages, ...reviewed === undefined ? {} : {reviewed}});
  }
  private workDetail() {
    const work = this.view!.detail!;
    const allocation = this.allocationFor(work);
    const allocationBlocked = this.completionReview(work, allocation).blocked;
    return html`<section class="card" aria-labelledby="selected-task-title"><h3 id="selected-task-title" tabindex="-1">${work.title}</h3>
      <p><span class="badge">${this.text(`state_${work.state}`)}</span><span class="badge">${this.text(`priority_${work.priority}`)}</span></p>
      ${work.categoryLabel ? html`<p>${this.text('category')} ${work.categoryLabel}</p>` : nothing}
      ${work.description ? html`<p class="description">${work.description}</p>` : nothing}
      <p class="help">${this.text('due')}: ${taskDeadline(work, this.language)}</p>
      ${work.cycle ? html`<p class="note" role="status"><strong>${this.text(`verification_${work.cycle.verification}`)}</strong><br>
        <small>${this.text('performed')}: ${taskInstant(work.cycle.performedAt, this.language)}</small></p>` : nothing}
      ${work.dependencyReviewRequired ? html`<p class="note warning" role="status">${this.text('dependencyReview')}</p>` : nothing}
      ${work.pendingMaterials ? html`<p class="note warning" role="status">${this.text('pendingMaterials')}</p>` : nothing}
      ${work.allowedActions.includes('claim') ? html`<div class="actions"><button ?disabled=${this.blocked} @click=${() => this.intent({type: 'claim'})}>${this.text('claim')}</button></div>` : nothing}
      ${work.completionPoints === 'manager_required' ? html`<p class="note" role="status">${this.text('manualPointsManager')}</p>` : nothing}
      ${work.allowedActions.includes('complete') ? html`<form id="complete-form" class="task-fields" novalidate @submit=${(event: SubmitEvent) => {event.preventDefault(); this.complete();}}>
        <p>${this.text('completionHelp')}</p>${work.materials.length ? work.materialRecording === 'review_on_completion' ? html`<fieldset><legend>${this.text('materials')}</legend>
          <p class="help">${this.text('quantityHelp')}</p>${work.materials.map((material, index) => html`<div class="material"><label for=${'material-' + index}>${material.label || this.text('quantity')}</label>
            <input id=${'material-' + index} inputmode="decimal" type="text" maxlength="64" .value=${live(this.quantities[material.lineId] ?? '')}
              ?disabled=${this.view!.busy} aria-invalid=${this.quantityError === material.lineId ? 'true' : 'false'} aria-describedby=${this.quantityError === material.lineId ? 'quantity-error' : 'quantity-help'}
              @input=${(event: InputEvent) => {this.quantities = {...this.quantities, [material.lineId]: (event.target as HTMLInputElement).value}; this.quantityError = null;}}>
            <small>${material.precision === 0 ? this.text('wholeQuantity') : this.text('decimalPlaces') + ': ' + material.precision}</small></div>`)}
          <small id="quantity-help">${this.text('quantityHelp')}</small>${this.quantityError ? html`<p id="quantity-error" class="error" role="alert">${this.text('quantityInvalid')}</p>` : nothing}</fieldset>`
          : html`<p class="help">${this.text('separateMaterials')}</p>` : nothing}
        ${allocation === null ? nothing : html`<domus-allocation-preview .view=${allocation} .language=${this.language}
          .ownId=${this.view!.access!.memberId} .names=${this.participantNames} .disabled=${this.blocked}
          @domus-allocation-draft=${() => this.requestUpdate()}></domus-allocation-preview>`}
        <button class="primary" type="submit" ?disabled=${this.blocked || allocationBlocked}>${this.text('complete')}</button></form>` : nothing}
      <domus-allocation-settings .view=${allocation} .language=${this.language}></domus-allocation-settings>
      ${work.allowedActions.some(action => ['approve', 'reject', 'reopen'].includes(action)) ? html`<section class="task-fields" aria-labelledby="review-title"><h3 id="review-title">${this.text('review')}</h3>
        <div class="field"><label for="task-reason">${this.text('reason')}</label><textarea id="task-reason" maxlength=${TASK_TEXT_LIMITS.reason * 2} aria-invalid=${Array.from(this.reasonDraft).length > TASK_TEXT_LIMITS.reason ? 'true' : 'false'} .value=${live(this.reasonDraft)}
          ?disabled=${this.view!.busy} aria-describedby="task-reason-help" @input=${(event: InputEvent) => {this.reasonDraft = (event.target as HTMLTextAreaElement).value;}}></textarea>
          <small id="task-reason-help">${Array.from(this.reasonDraft).length > TASK_TEXT_LIMITS.reason ? this.text('textTooLong') + ': ' + TASK_TEXT_LIMITS.reason : this.text('reasonHelp')}</small></div><div class="actions">
          ${(['approve', 'reject', 'reopen'] as const).filter(action => work.allowedActions.includes(action)).map(action => html`<button type="button" ?disabled=${this.blocked || Array.from(this.reasonDraft).length > TASK_TEXT_LIMITS.reason || action !== 'approve' && !hasTaskText(this.reasonDraft)}
            @click=${() => {this.lastForm = 'review'; this.intent(action === 'reopen' ? {type: 'reopen', reason: this.reasonDraft}
              : {type: 'verify', decision: action === 'approve' ? 'approved' : 'rejected', reason: this.reasonDraft});}}>${this.text(action)}</button>`)}
        </div></section>` : nothing}
      <details><summary>${this.text('technical')}</summary><dl><dt>${this.text('taskId')}</dt><dd><code>${work.occurrenceId}</code></dd>
        <dt>${this.text('revision')}</dt><dd>${work.revision}</dd></dl></details></section>`;
  }
  private request(record: TaskRecord) {
    return html`<div class="request"><strong>${this.text(`action_${record.command.action.slice(5)}` as TaskMessageKey)}</strong>
      <div class="actions">${record.stage !== 'rejected' ? html`<button type="button" ?disabled=${this.view!.busy} @click=${() => this.intent({type: 'recover', key: record.key})}>${this.text('check')}</button>` : nothing}
        ${record.stage !== 'prepared' && record.stage !== 'uncertain' ? html`<button type="button" ?disabled=${this.view!.busy} @click=${() => this.intent({type: 'dismiss', key: record.key})}>${this.text('dismiss')}</button>` : nothing}</div></div>`;
  }
  private outcome() {
    const result = this.view!.outcome; if (result === null) return nothing;
    const kind = result.kind === 'receipt' ? result.stage === 'committed' ? 'saved' : 'historical' : result.kind;
    const body = kind === 'saved' && result.kind === 'receipt' && result.state === 'active' ? 'scheduleSaved' : `${kind}Body` as const;
    return html`<section class="note" role="status"><h3>${this.text(kind)}</h3><p>${this.text(body)}</p>
      ${result.kind === 'rejected' ? html`<p>${this.text(`notice_${result.reason}`)}</p>` : nothing}
      ${result.kind === 'receipt' && result.basePointsMinor !== undefined ? html`<dl><dt>${this.text('basePoints')}</dt>
        <dd>${displayPoints(result.basePointsMinor, this.language)}</dd></dl>` : nothing}
      ${result.kind === 'receipt' ? html`<details><summary>${this.text('technical')}</summary><p>${this.text('operation')}: <code>${result.operationId}</code></p></details>` : nothing}</section>`;
  }
  protected render() {
    const view = this.retired ? null : this.view, ready = view?.phase === 'ready' && view.access !== null;
    const unresolved = view?.records?.filter(item => item.stage === 'prepared' || item.stage === 'uncertain') ?? [];
    const resolved = view?.records?.filter(item => item.stage !== 'prepared' && item.stage !== 'uncertain') ?? [];
    return html`<section aria-labelledby="tasks-title" aria-busy=${view?.busy === true}><div class="task-header"><h2 id="tasks-title">${this.text('title')}</h2>
      <button type="button" ?disabled=${view?.busy === true || view?.phase === 'closed'} @click=${() => this.intent({type: 'refresh'})}>${this.text('refresh')}</button></div>
      <p class="intro">${this.text('intro')}</p>
      ${view === null || view.phase === 'idle' || view.phase === 'loading' ? html`<p role="status">${this.text('loading')}</p>` : view.phase === 'closed' ? html`<p role="status">${this.text('closed')}</p>` : nothing}
      ${view?.notice ? html`<p class="note warning" role="alert">${this.text(`notice_${view.notice}`)}</p>` : nothing}
      ${ready ? html`${view.readOnly ? html`<p class="note" role="status">${this.text('readOnly')}</p>` : nothing}${this.outcome()}
        ${unresolved.length ? html`<section class="note warning" aria-label=${this.text('requests')}><p>${this.text('uncertainBody')}</p>${unresolved.map(record => this.request(record))}</section>` : nothing}
        <div class=${view.detail ? 'task-layout' : 'task-layout single'}>
          <div>${view.access!.canCreate ? this.createForm() : nothing}
            ${view.access!.categoryCatalog?.canManage ? this.manageCategories() : nothing}
            <section class="card" aria-labelledby="task-list-title"><h3 id="task-list-title">${this.text('list')}</h3>
              ${view.page?.items.length ? html`<ul class="task-list">${view.page.items.map(item => html`<li><button type="button" class="task-link" ?disabled=${view.busy}
                aria-pressed=${item.occurrenceId === view.detail?.occurrenceId ? 'true' : 'false'} @click=${() => this.intent({type: 'select', occurrenceId: item.occurrenceId})}>${item.title}</button>
                <div class="task-meta"><span>${this.text(`state_${item.state}`)}</span><span>${taskDeadline(item, this.language)}</span></div></li>`)}</ul>`
                : view.page !== null ? html`<p>${this.text('empty')}</p>` : nothing}
              ${view.page?.nextCursor ? html`<div class="actions"><button type="button" ?disabled=${view.busy} @click=${() => this.intent({type: 'more'})}>${this.text('more')}</button></div>` : nothing}</section></div>
          <div>${view.detail ? this.workDetail() : nothing}</div>
        </div>
        ${resolved.length ? html`<details><summary>${this.text('requests')}</summary>${resolved.map(record => this.request(record))}</details>` : nothing}` : nothing}
    </section>`;
  }
}
registerField();
customElements.define('domus-tasks', DomusTasks);
declare global {interface HTMLElementTagNameMap {'domus-tasks': DomusTasks;}}
