import {LitElement, css, html, nothing} from 'lit';
import {live} from 'lit/directives/live.js';
import type {PropertyValues} from 'lit';
import {registerField} from '@vypdev/ha-ui/field';
import type {FieldValueEvent} from '@vypdev/ha-ui/field';
import {textFieldState} from '@vypdev/ha-ui/field-contracts';
import {registerCheckbox} from '@vypdev/ha-ui/checkbox';
import type {CheckboxChangeEvent} from '@vypdev/ha-ui/checkbox';
import {checkboxChangeDetail, checkboxState} from '@vypdev/ha-ui/checkbox-contracts';
import {registerButton} from '@vypdev/ha-ui/button';
import {buttonState} from '@vypdev/ha-ui/button-contracts';
import {registerCard} from '@vypdev/ha-ui/card';
import {cardState} from '@vypdev/ha-ui/card-contracts';
import {registerFeedback} from '@vypdev/ha-ui/feedback';
import {feedbackState} from '@vypdev/ha-ui/feedback-contracts';
import type {AdministrationView} from '../application/administration-controller';
import type {TaskView} from '../application/task-controller';
import type {TaskRecord} from '../application/task-ports';
import {categoryLabel, hasTaskText, taskAssignees, taskQuantityInput as quantityInput, taskScheduleDraft, taskText, TASK_PRIORITIES, TASK_TEXT_LIMITS} from '../domain/tasks';
import type {Revision} from '../domain/administration';
import type {TaskCategory, TaskDetail, TaskMaterialUsage, TaskPriority, TaskProgressTarget, TaskScheduleDraft} from '../domain/tasks';
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
import './domus-task-material-plan';
import './domus-task-material-outcomes';
import type {MaterialPlanIntent} from './domus-task-material-plan';
import type {MaterialRecordingDrafts, MaterialSettlementIntent} from './domus-task-material-outcomes';
import {materialMessage, materialSource, materialUnit} from './task-material-messages';
export type TaskIntent = Readonly<{type: 'refresh' | 'more' | 'claim'}>
  | Readonly<{type:'materialHistory'; more:boolean}>
  | Readonly<{type:'materialPlan'} & MaterialPlanIntent>
  | Readonly<{type:'settleMaterial'} & MaterialSettlementIntent>
  | Readonly<{type: 'select'; occurrenceId: string}>
  | Readonly<{type: 'assign'; occurrenceId: string; revision: Revision; assigneeIds: readonly string[]}>
  | Readonly<{type: 'transition'; occurrenceId: string; revision: Revision; target: TaskProgressTarget; reason: string}>
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
type AssignmentDraft = Readonly<{occurrenceId: string; revision: Revision; assigneeIds: readonly string[]}>;
type ProgressDraft = Readonly<{occurrenceId: string; revision: Revision; target: TaskProgressTarget; reason: string}>;
function validCategoryLabel(value: string): boolean {
  try {categoryLabel(value); return true;} catch {return false;}
}
function validBlockingReason(value: string): boolean {
  try {taskText(value, TASK_TEXT_LIMITS.reason, true, true); return true;} catch {return false;}
}
/** Render only verified task facts; emitted intents never select an actor or grant a permission. */
export class DomusTasks extends LitElement {
  static properties = {administration: {attribute: false}, assignmentDraft: {state: true}, assignmentError: {state: true},
    progressDraft: {state: true}, progressError: {state: true}, materialDrafts: {state: true},
    allocation: {attribute: false}, participantNames: {attribute: false}, view: {attribute: false}, retired: {attribute: false}, language: {attribute: false}, titleDraft: {state: true}, descriptionDraft: {state: true},
    categoryDraft: {state: true}, categoryName: {state: true}, categoryEdit: {state: true}, manageOpen: {state: true},
    basePointsDraft: {state: true}, basePointsError: {state: true},
    titleRequired: {state: true}, priorityDraft: {state: true}, reasonDraft: {state: true}, quantities: {state: true}, quantityError: {state: true}, createOpen: {state: true},
    scheduleKind: {state: true}, scheduleError: {state: true}, scheduleInput: {state: true}};
  static styles = [styles, css`:host {min-height:0;background:transparent;overflow-wrap:anywhere}.task-header {display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap}
    .task-header h2 {font-size:1.6rem;margin:0} .task-layout {display:grid;grid-template-columns:minmax(0,1fr);gap:20px}.task-layout .card {margin:0}
    .task-layout>div {display:grid;grid-template-columns:minmax(0,1fr);gap:20px;align-content:start} .new-task summary h3 {display:inline} .new-task form {margin-top:20px}
    h3 {font-size:1.1rem;margin:0 0 16px} textarea {font:inherit;resize:vertical;width:100%;min-height:90px;border:1px solid var(--line);border-radius:10px;
    padding:10px 12px;background:var(--surface);color:var(--text)} .task-list {list-style:none;padding:0;margin:0}.task-list li {padding:14px 0;border-bottom:1px solid var(--line)}
    .task-link {border:0;border-radius:8px;padding:4px 0;text-align:start;font-weight:700}.task-meta {display:flex;flex-wrap:wrap;gap:8px;color:var(--muted);font-size:.875rem}
    .description {white-space:pre-wrap}.task-fields {margin-top:24px}.material {display:grid;gap:6px;margin-bottom:12px}.request {margin-top:16px}
    #task-base-points {--vyp-ha-surface:var(--canvas);--vyp-ha-border:var(--line);
      --vyp-ha-text:var(--text);--vyp-ha-text-secondary:var(--muted);
      --vyp-ha-primary:var(--accent);--vyp-ha-danger:var(--warning)}
    .assignment {margin:24px 0}.assignment h4 {margin:0 0 8px}.assignment fieldset {margin-top:16px}
    .assignment-choices {display:grid;gap:4px;max-height:320px;overflow:auto;padding:12px}
    .assignment-choices vyp-ha-checkbox {min-height:44px;display:grid;align-content:center;
      --vyp-ha-text:var(--text);--vyp-ha-font-family:inherit;--ha-checkbox-border-color:var(--muted);
      --ha-checkbox-background-color-hover:var(--canvas);--ha-checkbox-checked-background-color:var(--accent);
      --ha-checkbox-checked-background-color-hover:var(--accent);--wa-focus-ring:solid 2px var(--accent)}
    :host {--vyp-ha-surface:var(--surface);--vyp-ha-surface-raised:var(--surface);
      --vyp-ha-text:var(--text);--vyp-ha-text-secondary:var(--muted);--vyp-ha-border:var(--line);
      --vyp-ha-primary:var(--accent);--vyp-ha-on-accent:var(--surface);--vyp-ha-focus-ring:3px solid var(--accent)}
    vyp-ha-button {--vyp-ha-button-height:44px}
    .progress {margin-block:24px}.progress h4 {margin-block:0 8px}.progress .field {margin-block:16px}
    .progress vyp-ha-feedback {margin-block:12px}.task-work-actions[hidden] {display:none}
    @media(min-width:800px) {.task-layout {grid-template-columns:minmax(0,1fr) minmax(0,1fr)}.task-layout.single {grid-template-columns:minmax(0,1fr)}}`];
  declare allocation: AllocationView | null;
  declare administration: Pick<AdministrationView, 'phase' | 'access' | 'roster' | 'errors'> | null;
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
  private declare basePointsError: 'basePointsInvalid' | 'notice_points_precision_two_required' | null;
  private declare priorityDraft: TaskPriority;
  private declare scheduleKind: 'manual' | TaskScheduleDraft['kind'];
  private declare scheduleError: boolean;
  private declare reasonDraft: string;
  private declare quantities: Readonly<Record<string, string>>;
  private declare quantityError: string | null;
  private draftScope: string | null = null;
  private detailKey: string | null = null;
  private submittedDraft: string | null = null;
  private declare assignmentDraft: AssignmentDraft | null;
  private declare assignmentError: boolean;
  private submittedAssignment: AssignmentDraft | null = null;
  private assignmentFocus: string | null = null;
  private declare progressDraft: ProgressDraft | null;
  private declare materialDrafts: MaterialRecordingDrafts;
  private declare progressError: boolean;
  private submittedProgress: ProgressDraft | null = null;
  private progressFocus: string | null = null;
  private materialFocus: 'choices' | 'last-row' | 'outcomes' | 'history' | null = null;
  private lastForm: 'create' | 'review' | 'category' | 'assignment' | 'progress' | 'material' = 'create';
  private focusDetail = false;
  constructor() {super(); this.allocation = null; this.participantNames = []; this.view = null; this.retired = false; this.language = 'en'; this.titleDraft = ''; this.titleRequired = false; this.descriptionDraft = '';
    this.priorityDraft = 'normal'; this.scheduleKind = 'manual'; this.scheduleError = false; this.scheduleInput = EMPTY_SCHEDULE_FIELDS;
    this.createOpen = false; this.reasonDraft = ''; this.quantities = {}; this.quantityError = null;
    this.basePointsDraft = ''; this.basePointsError = null;
    this.administration = null; this.assignmentDraft = null; this.assignmentError = false;
    this.progressDraft = null; this.progressError = false; this.materialDrafts = {};
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
    this.resetProgress();
    this.materialDrafts = {};
    this.materialFocus = null;
    this.assignmentDraft = null; this.submittedAssignment = null; this.assignmentFocus = null; this.assignmentError = false;
    this.categoryDraft = ''; this.categoryName = ''; this.categoryEdit = null; this.submittedCategory = null; this.manageOpen = false;
    this.createOpen = false; this.titleDraft = ''; this.titleRequired = false; this.descriptionDraft = ''; this.priorityDraft = 'normal'; this.reasonDraft = '';
    this.basePointsDraft = ''; this.basePointsError = null;
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
    const previousDetail = changed.get('view')?.detail;
    if (detail && previousDetail && detail.occurrenceId !== previousDetail.occurrenceId) this.materialDrafts = {};
    const outcome = this.view?.outcome;
    if (detail && this.assignmentDraft && (detail.occurrenceId !== this.assignmentDraft.occurrenceId || !detail.allowedActions.includes('assign'))) {
      this.assignmentDraft = null; this.submittedAssignment = null; this.assignmentFocus = null;
    }
    if (detail && this.assignmentDraft && key !== this.detailKey && this.assignmentNeedsReview(detail))
      this.assignmentFocus = '#assignment-review';
    if (detail && this.progressDraft && detail.occurrenceId !== this.progressDraft.occurrenceId) this.resetProgress();
    if (detail && this.progressDraft) {
      const newConflict = outcome?.kind === 'rejected' && outcome.reason === 'conflict'
        && outcome !== changed.get('view')?.outcome;
      if (this.progressNeedsReview(detail, this.progressDraft) && (key !== this.detailKey || newConflict))
        this.progressFocus = this.progressTargets(detail).includes(this.progressDraft.target)
          ? '#task-progress-review' : '#task-progress-editor';
      else if (changed.get('view')?.detail === null)
        this.progressFocus = this.progressDraft.target === 'blocked' ? '#task-progress-reason' : '#task-progress-save';
    }
    if (key !== null && key !== this.detailKey) {this.focusDetail = this.view?.phase === 'ready'; this.detailKey = key; this.reasonDraft = ''; this.quantityError = null;
      this.quantities = Object.fromEntries(detail!.materials.map(item => [item.lineId, item.plannedQuantity]));}
    if (outcome?.kind === 'receipt' && outcome.stage === 'committed' && outcome.action === 'task.transition'
        && this.progressDraft !== null && this.progressDraft === this.submittedProgress
        && outcome.occurrenceId === this.progressDraft.occurrenceId && outcome.state === this.progressDraft.target
        && outcome.stateReason === this.progressDraft.reason
        && BigInt(outcome.revision) === BigInt(this.progressDraft.revision) + 1n
        && outcome !== changed.get('view')?.outcome) this.resetProgress('#task-progress-actions vyp-ha-button');
    if (outcome?.kind === 'receipt' && outcome.stage === 'committed' && outcome.action === 'task.assign'
        && outcome.occurrenceId === this.assignmentDraft?.occurrenceId && this.assignmentDraft === this.submittedAssignment
        && outcome.assigneeIds !== undefined
        && JSON.stringify([...outcome.assigneeIds].sort()) === JSON.stringify([...this.assignmentDraft.assigneeIds].sort())
        && BigInt(outcome.revision) === BigInt(this.assignmentDraft.revision) + 1n && outcome !== changed.get('view')?.outcome) {
      this.assignmentDraft = null; this.submittedAssignment = null; this.assignmentError = false; this.assignmentFocus = '#assignment-edit';
    }
    if (outcome?.kind === 'rejected' && outcome.reason === 'points_precision_two_required'
        && outcome !== changed.get('view')?.outcome) this.basePointsError = 'notice_points_precision_two_required';
    if (outcome?.kind === 'receipt' && outcome.stage === 'committed' && outcome.action === this.submittedCategory?.action
        && this.categoryName === this.submittedCategory.label) {
      this.categoryName = ''; this.categoryEdit = null; this.submittedCategory = null;
    }
    if (outcome?.kind === 'receipt' && outcome.stage === 'committed' && outcome.action === 'task.create'
        && this.submittedDraft === this.creationDraftKey()) {
      this.categoryDraft = ''; this.createOpen = false; this.titleDraft = ''; this.titleRequired = false; this.descriptionDraft = ''; this.priorityDraft = 'normal'; this.submittedDraft = null;
      this.basePointsDraft = ''; this.basePointsError = null;
      this.scheduleKind = 'manual'; this.scheduleError = false; this.scheduleInput = EMPTY_SCHEDULE_FIELDS;
    }
  }
  protected updated(changed: PropertyValues): void {
    this.lang = language(this.language, 'en');
    const current = this.retired ? null : this.view;
    if (changed.has('view') && current?.phase === 'ready' && current.notice === 'unavailable'
        && current.detail === null && changed.get('view')?.notice !== 'unavailable') {
      this.focusDetail = false; this.assignmentFocus = null; this.progressFocus = null; this.materialFocus = null;
      const recovery = this.renderRoot.querySelector<HTMLButtonElement>('.task-header button')!;
      recovery.focus();
      recovery.scrollIntoView({block: 'center', inline: 'nearest', behavior: 'instant'});
      return;
    }
    if (this.focusDetail) {this.focusDetail = false; this.shadowRoot?.querySelector<HTMLElement>('#selected-task-title')?.focus();}
    if (changed.has('view') && this.view?.notice === 'invalid_input') {
      const field = {create: '#task-title', category: '#task-category-label', assignment: '#assignment-editor',
        review: '#task-reason', progress: '#task-progress-editor', material: 'domus-task-material-outcomes'}[this.lastForm];
      this.shadowRoot?.querySelector<HTMLElement>(field)?.focus();
    }
    if (this.assignmentFocus !== null) {
      const target = this.renderRoot.querySelector<HTMLElement>(this.assignmentFocus)
        ?? this.renderRoot.querySelector<HTMLElement>('#assignment-editor');
      if (target) {this.assignmentFocus = null; queueMicrotask(() => target.focus());}
    }
    if (this.progressFocus !== null && this.view?.phase === 'ready') {
      const target = this.renderRoot.querySelector<HTMLElement>(this.progressFocus)
        ?? this.renderRoot.querySelector<HTMLElement>('#task-progress-actions vyp-ha-button')
        ?? this.renderRoot.querySelector<HTMLElement>('#selected-task-title');
      if (target) {
        this.progressFocus = null;
        requestAnimationFrame(() => {if (target.isConnected) target.focus();});
      }
    }
    if (changed.has('view') && this.view?.notice === 'category_unavailable')
      this.renderRoot.querySelector<HTMLSelectElement>('#task-category')?.focus();
    const outcome = this.view?.outcome;
    if (changed.has('view') && outcome?.kind === 'rejected' && outcome.reason === 'points_precision_two_required')
      this.renderRoot.querySelector<HTMLElement>('#task-base-points')?.focus();
    if (changed.has('quantityError') && this.quantityError) this.shadowRoot?.querySelector<HTMLInputElement>('[aria-invalid="true"]')?.focus();
    if (this.materialFocus !== null && this.view?.phase === 'ready') {
      const focus = this.materialFocus;
      this.materialFocus = null;
      if (focus === 'history') this.renderRoot.querySelector<HTMLElement>('#material-history-heading')?.focus();
      const component = this.renderRoot.querySelector<LitElement>(focus === 'outcomes' ? 'domus-task-material-outcomes' : 'domus-task-material-plan');
      if (focus !== 'history' && component) {
        void component.updateComplete.then(() => {
          const fields = component.renderRoot.querySelectorAll<HTMLElement>('vyp-ha-field');
          const target = focus === 'last-row' ? fields.item(fields.length - 1) : focus === 'outcomes'
            ? component.renderRoot.querySelector<HTMLElement>('vyp-ha-field, h4')
            : component.renderRoot.querySelector<HTMLElement>('vyp-ha-select') ?? component.renderRoot.querySelector<HTMLElement>('vyp-ha-button');
          const root = this.renderRoot as ShadowRoot, focused = root.activeElement;
          requestAnimationFrame(() => {
            if (target?.isConnected && root.activeElement === focused) {
              target.focus(); target.scrollIntoView({block: 'center', inline: 'nearest'});
            }
          });
        });
      }
    }
  }
  disconnectedCallback(): void {super.disconnectedCallback(); this.reset();}
  private intent(detail: TaskIntent): void {
    if (this.retired || this.view?.phase !== 'ready' || this.view.busy) return;
    if (['create', 'createCategory', 'renameCategory', 'archiveCategory', 'claim', 'assign', 'transition', 'complete', 'verify', 'reopen', 'settleMaterial'].includes(detail.type) && this.blocked) return;
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
    const plan = this.view!.materialPlan;
    const invalidPlan = plan !== null && plan !== undefined && plan.rows.length > 0
      && (!plan.canLink || plan.rows.some(row => row.choice === null || quantityInput(row.input, row.choice.unit === 'piece' ? 0 : 6) === null));
    return html`<details class="card new-task" ?open=${this.createOpen || this.view!.page?.items.length === 0}
      @toggle=${(event: Event) => {const target = event.target as HTMLDetailsElement; if (target.isConnected) this.createOpen = target.open;}}><summary><h3 id="new-task-title">${this.text('newTask')}</h3></summary>
      <form novalidate @submit=${(event: SubmitEvent) => {event.preventDefault(); this.lastForm = 'create';
        if (stalePoints || invalidPlan) return;
        this.titleRequired = !hasTaskText(this.titleDraft);
        if (this.titleRequired || titleTooLong || descriptionInvalid || this.staleCategory) {
          this.shadowRoot?.querySelector<HTMLElement>(this.titleRequired || titleTooLong ? '#task-title' : descriptionInvalid ? '#task-description' : '#task-category')?.focus(); return;
        }
        const basePointsMinor = this.basePointsDraft.trim() === '' ? undefined : minorPoints(this.basePointsDraft);
        if (basePointsMinor === null) {
          this.basePointsError = 'basePointsInvalid';
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
        <domus-task-material-plan .view=${this.view?.materialPlan ?? null} .language=${this.language} .disabled=${this.blocked}
          @domus-material-plan-intent=${(event: CustomEvent<MaterialPlanIntent>) => {
            this.createOpen = true;
            if (event.detail.action !== 'edit') this.materialFocus = event.detail.action === 'add' ? 'last-row' : 'choices';
            event.stopPropagation(); this.intent({type:'materialPlan', ...event.detail});
          }}></domus-task-material-plan>
        ${this.view?.access?.categoryCatalog ? this.categorySelector() : nothing}
        ${canSetPoints ? this.basePointsField() : nothing}
        ${stalePoints ? html`<p role="alert">${this.text('basePointsUnavailable')}</p>
          <button type="button" @click=${() => {this.basePointsDraft = ''; this.basePointsError = null;}}>
            ${this.text('clearBasePoints')}</button>` : nothing}
        <button type="submit" class="primary" ?disabled=${this.blocked || titleTooLong || descriptionInvalid || this.staleCategory || stalePoints || invalidPlan}>${this.text('create')}</button>
      </form></details>`;
  }
  private basePointsField() {
    return html`<vyp-ha-field id="task-base-points" .value=${this.basePointsDraft} ?disabled=${this.view!.busy}
      .state=${textFieldState({label: this.text('basePointsOptional'), description: this.text('basePointsHelp'), inputMode: 'decimal',
        error: this.basePointsError === null ? '' : this.text(this.basePointsError)})}
      @ha-value-request=${(event: FieldValueEvent) => {
        this.basePointsDraft = event.detail.value;
        this.basePointsError = null;
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
  private resetProgress(focus: string | null = null): void {
    this.progressDraft = null;
    this.submittedProgress = null;
    this.progressError = false;
    this.progressFocus = focus;
  }
  private progressLabel(target: TaskProgressTarget): TaskMessageKey {
    if (target === 'in_progress') return 'progressStart';
    if (target === 'blocked') return 'progressBlock';
    return 'progressUnblock';
  }
  private progressTargets(work: TaskDetail): readonly TaskProgressTarget[] {
    const targets: TaskProgressTarget[] = [];
    if (work.state === 'assigned') targets.push('in_progress');
    if (['available', 'assigned', 'in_progress'].includes(work.state)) targets.push('blocked');
    if (work.state === 'blocked') targets.push(work.assigneeIds.length ? 'assigned' : 'available');
    return targets.filter(target => work.allowedActions.includes('transition:' + target));
  }
  private progressNeedsReview(work: TaskDetail, draft: ProgressDraft): boolean {
    const outcome = this.view!.outcome;
    return draft.occurrenceId !== work.occurrenceId || draft.revision !== work.revision
      || this.submittedProgress !== null && outcome?.kind === 'rejected' && outcome.reason === 'conflict';
  }
  private openProgress(target: TaskProgressTarget): void {
    const work = this.view?.detail;
    if (!work || this.blocked || !this.progressTargets(work).includes(target)) return;
    this.progressDraft = Object.freeze({occurrenceId: work.occurrenceId, revision: work.revision, target, reason: ''});
    this.submittedProgress = null;
    this.progressError = false;
    this.progressFocus = target === 'blocked' ? '#task-progress-reason' : '#task-progress-save';
  }
  private changeProgressReason(event: InputEvent): void {
    if (this.blocked || this.progressDraft === null) return;
    this.progressDraft = Object.freeze({...this.progressDraft, reason: (event.target as HTMLTextAreaElement).value});
    this.progressError = false;
  }
  private reviewProgress(): void {
    const draft = this.progressDraft, work = this.view?.detail;
    if (draft === null || !work || this.blocked || work.occurrenceId !== draft.occurrenceId
        || !this.progressTargets(work).includes(draft.target)) return;
    this.progressDraft = Object.freeze({...draft, revision: work.revision});
    this.submittedProgress = null;
    this.progressError = false;
    this.progressFocus = draft.target === 'blocked' && !validBlockingReason(draft.reason)
      ? '#task-progress-reason' : '#task-progress-save';
  }
  private saveProgress(event: SubmitEvent): void {
    event.preventDefault();
    const draft = this.progressDraft, work = this.view?.detail;
    if (draft === null || !work || this.blocked) return;
    if (this.progressNeedsReview(work, draft) || !this.progressTargets(work).includes(draft.target)) {
      this.progressFocus = '#task-progress-editor';
      this.requestUpdate();
      return;
    }
    if (draft.target === 'blocked' && !validBlockingReason(draft.reason)) {
      this.progressError = true;
      this.progressFocus = '#task-progress-reason';
      return;
    }
    this.submittedProgress = draft;
    this.lastForm = 'progress';
    this.intent({type: 'transition', occurrenceId: draft.occurrenceId, revision: draft.revision,
      target: draft.target, reason: draft.reason});
  }
  private progress(work: TaskDetail) {
    const draft = this.progressDraft, targets = this.progressTargets(work);
    if (draft === null && targets.length === 0 && work.state !== 'blocked') return nothing;
    const review = draft !== null && this.progressNeedsReview(work, draft);
    const available = draft !== null && targets.includes(draft.target);
    const invalid = draft?.target === 'blocked' && !validBlockingReason(draft.reason);
    const showError = invalid && (this.progressError || draft.reason.length > 0);
    return html`<section class="progress">
      ${work.state === 'blocked' ? html`<h4>${this.text('progressCurrentReason')}</h4>
        <p id="task-blocked-reason" class="description">${work.stateReason ?? this.text('progressReasonUnavailable')}</p>` : nothing}
      ${draft === null ? html`<div id="task-progress-actions" class="actions">${targets.map(target => html`
        <vyp-ha-button id=${'task-progress-' + target} .state=${buttonState({label: this.text(this.progressLabel(target)), variant: 'outlined'})}
          ?disabled=${this.blocked} @ha-press-request=${() => this.openProgress(target)}></vyp-ha-button>`)}</div>`
      : html`<vyp-ha-card .state=${cardState({title: this.text(this.progressLabel(draft.target)), headingLevel: 4})}>
        <form id="task-progress-editor" tabindex="-1" novalidate aria-label=${this.text(this.progressLabel(draft.target)) + ' ' + work.title}
          @submit=${(event: SubmitEvent) => this.saveProgress(event)}>
          <dl>${review ? html`<dt>${this.text('progressCurrent')}</dt><dd>${this.text(`state_${work.state}`)}</dd>` : nothing}
            <dt>${this.text('progressProposed')}</dt><dd>${this.text(`state_${draft.target}`)}</dd>
            <dt>${this.text('assignmentTitle')}</dt><dd>${work.assigneeIds.length
              ? work.assigneeIds.map(id => this.assignmentName(id)).join(', ') : this.text('assignmentEmpty')}</dd>
            <dt>${this.text('progressVersion')}</dt><dd id="task-progress-version">${draft.revision}</dd></dl>
          ${!available ? html`<vyp-ha-feedback id="task-progress-unavailable" .state=${feedbackState({kind: 'notice', tone: 'warning',
              title: this.text('progressUnavailableTitle'), message: this.text('progressUnavailable')})}></vyp-ha-feedback>`
            : review ? html`<vyp-ha-feedback .state=${feedbackState({kind: 'notice', tone: 'warning',
              title: this.text('progressChangedTitle'), message: this.text('progressChanged')})}></vyp-ha-feedback>` : nothing}
          ${draft.target === 'blocked' ? html`<div class="field"><label for="task-progress-reason">${this.text('progressReason')}</label>
            <textarea id="task-progress-reason" required maxlength=${TASK_TEXT_LIMITS.reason * 2} .value=${live(draft.reason)}
              ?disabled=${this.blocked} aria-invalid=${showError ? 'true' : 'false'}
              aria-describedby=${showError ? 'task-progress-reason-help task-progress-error' : 'task-progress-reason-help'}
              @input=${(event: InputEvent) => this.changeProgressReason(event)}></textarea>
            <small id="task-progress-reason-help">${this.text('progressReasonHelp')}</small>
            ${showError ? html`<p id="task-progress-error" class="error" role="alert">${this.text('progressInvalid')}</p>` : nothing}</div>`
            : draft.target === 'assigned' || draft.target === 'available'
              ? html`<p class="help">${this.text('progressReasonHistory')}</p>` : nothing}
          <div class="actions">
            ${!available ? html`<vyp-ha-button .state=${buttonState({label: this.text('progressRefresh'), variant: 'outlined'})}
                ?disabled=${this.view!.busy} @ha-press-request=${() => this.intent({type: 'refresh'})}></vyp-ha-button>`
              : review ? html`<vyp-ha-button id="task-progress-review"
                .state=${buttonState({label: this.text('progressReview'), variant: 'outlined'})}
                ?disabled=${this.blocked} @ha-press-request=${() => this.reviewProgress()}></vyp-ha-button>` : nothing}
            <vyp-ha-button id="task-progress-save" type="submit" .state=${buttonState({label: this.text('progressSave'), variant: 'primary'})}
              ?disabled=${this.blocked || review || !available || invalid}></vyp-ha-button>
            <vyp-ha-button .state=${buttonState({label: this.text('progressCancel'), variant: 'outlined'})}
              ?disabled=${this.view!.busy} @ha-press-request=${() => this.resetProgress('#task-progress-' + draft.target)}></vyp-ha-button>
          </div>
        </form>
      </vyp-ha-card>`}
    </section>`;
  }
  private get assignmentDiscovery(): 'ready' | 'assignmentLoading' | 'assignmentDenied' | 'assignmentUnavailable' {
    const current = this.administration;
    if (current === null || current.phase === 'idle' || current.phase === 'loading' || current.phase === 'sending') return 'assignmentLoading';
    if (!current.access?.permissions.includes('members.read') || current.errors.roster === 'forbidden') return 'assignmentDenied';
    if (current.errors.roster !== undefined || current.roster === null) return 'assignmentUnavailable';
    return 'ready';
  }
  private assignmentName(id: string): string {
    const row = this.administration?.roster?.members.find(row => row.member.memberId === id);
    return row?.presentation.alias ?? row?.metadata.name ?? this.text('assignmentUnnamed') + ' ' + id;
  }
  private assignmentNeedsReview(work: TaskDetail): boolean {
    if (this.assignmentDraft === null) return false;
    const outcome = this.view!.outcome;
    return this.assignmentDraft.revision !== work.revision
      || this.submittedAssignment !== null && outcome?.kind === 'rejected' && outcome.reason === 'conflict';
  }
  private chooseAssignee(id: string, event: CheckboxChangeEvent): void {
    if (this.blocked || this.assignmentDraft === null || this.assignmentDiscovery !== 'ready') return;
    try {
      const {checked} = checkboxChangeDetail(event.detail);
      const ids = this.assignmentDraft.assigneeIds.filter(selected => selected !== id);
      this.assignmentDraft = Object.freeze({...this.assignmentDraft, assigneeIds: taskAssignees(checked ? [...ids, id] : ids)});
      this.assignmentError = false;
    } catch {event.preventDefault(); this.assignmentError = true;}
  }
  private assignment(work: TaskDetail) {
    if (!work.allowedActions.includes('assign')) return nothing;
    const discovery = this.assignmentDiscovery, draft = this.assignmentDraft;
    const choices = discovery === 'ready' ? this.administration!.roster!.members.filter(row => row.member.status === 'active') : [];
    const stale = draft?.assigneeIds.filter(id => !choices.some(row => row.member.memberId === id)) ?? [];
    const needsReview = this.assignmentNeedsReview(work);
    const unchanged = draft !== null
      && JSON.stringify([...draft.assigneeIds].sort()) === JSON.stringify([...work.assigneeIds].sort());
    const requiresAssignee = work.state === 'in_progress' && draft?.assigneeIds.length === 0;
    const currentUnavailable = this.view!.notice === 'unavailable' || this.view!.notice === 'invalid_response';
    const invalid = discovery !== 'ready' || stale.length > 0 || requiresAssignee || currentUnavailable || unchanged;
    return html`<section class="assignment" aria-labelledby="assignment-title"><h4 id="assignment-title">${this.text('assignmentTitle')}</h4>
      ${discovery === 'ready' ? html`<p>${work.assigneeIds.length ? work.assigneeIds.map(id => this.assignmentName(id)).join(', ') : this.text('assignmentEmpty')}</p>`
        : html`<p role="status">${this.text(discovery)}</p>`}
      ${draft === null ? html`<button id="assignment-edit" type="button" ?disabled=${this.blocked} @click=${() => {
        this.assignmentDraft = Object.freeze({occurrenceId: work.occurrenceId, revision: work.revision, assigneeIds: taskAssignees(work.assigneeIds)});
        this.assignmentError = false; this.assignmentFocus = 'vyp-ha-checkbox';
      }}>${this.text('assignmentEdit')}</button>` : html`<form id="assignment-editor" aria-labelledby="assignment-title" tabindex="-1" novalidate @submit=${(event: SubmitEvent) => {
        event.preventDefault();
        if (this.blocked || invalid || needsReview) return;
        this.lastForm = 'assignment'; this.submittedAssignment = draft;
        this.intent({type: 'assign', occurrenceId: draft.occurrenceId, revision: draft.revision, assigneeIds: draft.assigneeIds});
      }}><fieldset ?disabled=${this.blocked}><legend>${this.text('assignmentChoose')}</legend>
        <p class="help">${this.text('assignmentHelp')} (${draft.assigneeIds.length}/32)</p>
        ${discovery !== 'ready' ? nothing : choices.length === 0 ? html`<p role="status">${this.text('assignmentNoMembers')}</p>`
          : html`<div class="assignment-choices">${choices.map(({member}) => html`<vyp-ha-checkbox
            .state=${checkboxState({label: this.assignmentName(member.memberId)})} .checked=${draft.assigneeIds.includes(member.memberId)}
            .disabled=${this.blocked || draft.assigneeIds.length >= 32 && !draft.assigneeIds.includes(member.memberId)}
            @ha-check-request=${(event: CheckboxChangeEvent) => this.chooseAssignee(member.memberId, event)}></vyp-ha-checkbox>`)}</div>`}
        ${discovery === 'ready' && stale.length ? html`<p class="error" role="alert">${this.text('assignmentStale')}</p>
          <ul>${stale.map(id => html`<li data-stale-assignee>${this.assignmentName(id)} <button type="button"
            @click=${() => {this.assignmentDraft = Object.freeze({...draft, assigneeIds: Object.freeze(draft.assigneeIds.filter(selected => selected !== id))});}}
            aria-label=${this.text('assignmentRemove')}>${this.text('assignmentRemove')}</button></li>`)}</ul>` : nothing}
        ${requiresAssignee ? html`<p class="error" role="alert">${this.text('assignmentRequired')}</p>` : nothing}
        ${this.assignmentError ? html`<p class="error" role="alert">${this.text('assignmentInvalid')}</p>` : nothing}
        ${unchanged && discovery === 'ready' && !needsReview ? html`<p class="help" role="status">${this.text('assignmentUnchanged')}</p>` : nothing}
        ${needsReview ? html`<p role="alert">${this.text('assignmentChanged')}</p><button id="assignment-review" type="button" ?disabled=${currentUnavailable} @click=${() => {
          this.assignmentDraft = Object.freeze({...draft, revision: work.revision}); this.submittedAssignment = null;
          this.assignmentFocus = invalid ? '#assignment-editor' : '#assignment-save';
        }}>${this.text('assignmentReview')}</button>` : nothing}
        <div class="actions"><button id="assignment-save" class="primary" type="submit" ?disabled=${this.blocked || invalid || needsReview}>${this.text('assignmentSave')}</button>
          <button type="button" ?disabled=${draft.assigneeIds.length === 0} @click=${() => {
            this.assignmentDraft = Object.freeze({...draft, assigneeIds: Object.freeze([])}); this.assignmentError = false;
          }}>${this.text('assignmentClear')}</button></div></fieldset>
        <div class="actions"><button type="button" ?disabled=${this.view!.busy} @click=${() => this.intent({type: 'refresh'})}>${this.text('assignmentRefresh')}</button>
          <button type="button" @click=${() => {
            this.assignmentDraft = null; this.submittedAssignment = null; this.assignmentError = false; this.assignmentFocus = '#assignment-edit';
          }}>${this.text('assignmentCancel')}</button></div></form>`}</section>`;
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
      <domus-task-material-outcomes .work=${work} .drafts=${this.materialDrafts} .disabled=${this.blocked} .language=${this.language}
        @domus-material-recording-draft=${(event: CustomEvent<{intentId:string; draft:MaterialRecordingDrafts[string]}>) => {
          event.stopPropagation(); this.materialDrafts = {...this.materialDrafts, [event.detail.intentId]:event.detail.draft};
        }} @domus-material-settlement-intent=${(event: CustomEvent<MaterialSettlementIntent>) => {
          event.stopPropagation(); this.lastForm = 'material'; this.materialFocus = 'outcomes'; this.intent({type:'settleMaterial', ...event.detail});
        }}></domus-task-material-outcomes>
      ${work.materials.length ? html`<section aria-labelledby="material-history-heading"><h4 id="material-history-heading" tabindex="-1">${materialMessage('history',this.language)}</h4>
        <p>${materialMessage('historyHelp',this.language)}</p>
        <vyp-ha-button .state=${buttonState({label:materialMessage('historyLoad',this.language)})} ?disabled=${this.view!.busy}
          @click=${() => {this.materialFocus='history'; this.intent({type:'materialHistory',more:false});}}></vyp-ha-button>
        ${this.view!.materialHistory?.items.map(value => html`<section><h5>${materialMessage('completion',this.language)}: ${taskInstant(value.cycle.performedAt,this.language)}</h5>
          <p>${materialMessage('closed',this.language)}: ${taskInstant(value.closedAt!,this.language)}</p>
          <domus-task-material-outcomes .work=${{...work,cycle:value.cycle,materialOutcomes:value.materialOutcomes,allowedActions:value.allowedActions}}
            .drafts=${this.materialDrafts} .disabled=${this.blocked} .language=${this.language}
            @domus-material-recording-draft=${(event: CustomEvent<{intentId:string;draft:MaterialRecordingDrafts[string]}>) => {
              event.stopPropagation(); this.materialDrafts = {...this.materialDrafts,[event.detail.intentId]:event.detail.draft};
            }} @domus-material-settlement-intent=${(event: CustomEvent<MaterialSettlementIntent>) => {
              event.stopPropagation(); this.lastForm='material'; this.materialFocus='history'; this.intent({type:'settleMaterial',...event.detail});
            }}></domus-task-material-outcomes>
        </section>`)}
        ${this.view!.materialHistory?.items.length === 0 ? html`<p role="status">${materialMessage('historyEmpty',this.language)}</p>` : nothing}
        ${this.view!.materialHistory?.nextCursor ? html`<vyp-ha-button
          .state=${buttonState({label:materialMessage('historyMore',this.language)})} ?disabled=${this.view!.busy}
          @click=${() => {this.materialFocus='history'; this.intent({type:'materialHistory',more:true});}}></vyp-ha-button>` : nothing}
      </section>` : nothing}
      ${this.progress(work)}
      <div class="task-work-actions" ?hidden=${this.progressDraft !== null}>
      ${this.assignment(work)}
      ${work.allowedActions.includes('claim') ? html`<div class="actions"><button ?disabled=${this.blocked} @click=${() => this.intent({type: 'claim'})}>${this.text('claim')}</button></div>` : nothing}
      ${work.completionPoints === 'manager_required' ? html`<p class="note" role="status">${this.text('manualPointsManager')}</p>` : nothing}
      ${work.allowedActions.includes('complete') ? html`<form id="complete-form" class="task-fields" novalidate @submit=${(event: SubmitEvent) => {event.preventDefault(); this.complete();}}>
        <p>${this.text('completionHelp')}</p>${work.materials.length ? work.materialRecording === 'review_on_completion' ? html`<fieldset><legend>${this.text('materials')}</legend>
          <p class="help">${this.text('quantityHelp')}</p>${work.materials.map((material, index) => html`<div class="material"><label for=${'material-' + index}>${material.label || this.text('quantity')}</label>
            <p>${materialUnit(material.unitId, this.language, material.plannedQuantity)} · ${materialSource(material.locationId, this.language)}
              · ${materialMessage('planned', this.language)}: ${this.language === 'es' ? material.plannedQuantity.replace('.', ',') : material.plannedQuantity}</p>
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
      </div>
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
    if (kind === 'saved' && result.kind === 'receipt' && result.action === 'task.transition') return html`
      <section role="status"><vyp-ha-feedback id="task-progress-result" .state=${feedbackState({kind: 'notice', tone: 'success',
        title: this.text('progressSaved'), message: this.text('progressSavedBody')})}></vyp-ha-feedback>
        <details><summary>${this.text('technical')}</summary><p>${this.text('operation')}: <code>${result.operationId}</code></p></details></section>`;
    const assignmentSaved = kind === 'saved' && result.kind === 'receipt' && result.action === 'task.assign';
    const body = assignmentSaved ? 'assignmentSavedBody' : kind === 'saved' && result.kind === 'receipt' && result.action !== 'task.material.settle' && result.state === 'active' ? 'scheduleSaved' : `${kind}Body` as const;
    const precisionRequired = result.kind === 'rejected' && result.reason === 'points_precision_two_required';
    return html`<section class="note" role="status"><h3>${this.text(assignmentSaved ? 'assignmentSaved' : kind)}</h3>
      ${precisionRequired ? nothing : html`<p>${kind === 'saved' && result.kind === 'receipt' && result.action === 'task.material.settle'
        ? materialMessage('saved', this.language) : this.text(body)}</p>`}
      ${result.kind === 'rejected' && !precisionRequired ? html`<p>${this.text(`notice_${result.reason}`)}</p>` : nothing}
      ${result.kind === 'receipt' && result.action !== 'task.material.settle' && result.basePointsMinor !== undefined ? html`<dl><dt>${this.text('basePoints')}</dt>
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
registerCheckbox();
registerButton();
registerCard();
registerFeedback();
customElements.define('domus-tasks', DomusTasks);
declare global {interface HTMLElementTagNameMap {'domus-tasks': DomusTasks;}}
