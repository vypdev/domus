import {LitElement, css, html, nothing} from 'lit';
import type {PropertyValues} from 'lit';
import type {CalendarPreferenceView} from '../application/calendar-preferences';
import type {CalendarView} from '../application/calendar-controller';
import {CALENDAR_KINDS, CALENDAR_MODES, CALENDAR_TIMINGS, DATE_MAX, DATE_MIN, calendarDays, calendarPeriod, calendarQuery, calendarWeekOffset, civilDate, WEEK_STARTS} from '../domain/calendar';
import type {CalendarEntry, CalendarMode, CalendarPeriod, CalendarQuery, WeekStart} from '../domain/calendar';
import {TASK_PRIORITIES, TASK_STATES} from '../domain/tasks';
import type {TaskCategory} from '../domain/tasks';
import {calendarMessage} from './calendar-messages';
import type {CalendarMessage} from './calendar-messages';
import type {Language} from './messages';
import {styles} from './styles';
import {taskMessage} from './task-messages';

export type CalendarIntent = {readonly type: 'load'; readonly query: CalendarQuery} | {readonly type: 'more' | 'recoverPreference' | 'refreshPreference'}
  | {readonly type: 'setWeekStart'; readonly weekStart: WeekStart};

export class DomusCalendar extends LitElement {
  static properties = {preference: {attribute:false}, categories: {attribute:false}, view: {attribute: false}, language: {attribute: false}, scopeKey: {attribute: false},
    today: {attribute: false}, anchor: {state: true}, mode: {state: true}, filters: {state: true},
    shownMode: {state: true}, shownRange: {state: true}, shownCategory: {state: true}};
  static styles = [styles, css`
    .filters{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(min(100%,150px),1fr))}
    .filters .field{margin:0}.calendar-grid{display:grid;grid-template-columns:repeat(7,minmax(100px,1fr));
      gap:4px;margin:0;padding:0;list-style:none;min-width:700px}
    .grid-scroll{overflow:auto}.calendar-grid li{border:1px solid var(--line);padding:8px;overflow-wrap:anywhere}
    .calendar-entries{padding-inline-start:20px;overflow-wrap:anywhere}
  `];
  declare categories: readonly TaskCategory[] | undefined;
  declare preference: CalendarPreferenceView | null;
  declare view: CalendarView | null;
  declare language: Language;
  declare scopeKey: string | null;
  declare today: string;
  private declare anchor: string;
  private declare mode: CalendarMode;
  private declare filters: Omit<CalendarQuery, 'start' | 'end'>;
  private declare shownMode: CalendarMode;
  private declare shownRange: CalendarPeriod | null;
  private declare shownCategory: string;
  private readonly unavailableCategories = new Set<string>();

  constructor() {
    super(); this.preference = null; this.view = null; this.language = 'en'; this.scopeKey = null; this.today = DATE_MIN;
    this.anchor = DATE_MIN; this.mode = 'month'; this.shownMode = 'month'; this.shownRange = null; this.shownCategory = '';
    this.filters = {kind: '', timing: '', state: '', priority: '', category: '', own: false};
  }

  protected willUpdate(changed: PropertyValues<this>): void {
    if (changed.has('scopeKey')) {
      this.anchor = this.today; this.mode = 'month'; this.shownRange = null; this.shownCategory = '';
      this.filters = {kind: '', timing: '', state: '', priority: '', category: '', own: false};
      this.unavailableCategories.clear();
    }
    if (changed.has('view') && this.view?.status === 'category_unavailable') {
      this.unavailableCategories.add(this.shownCategory);
    }
  }
  protected updated(changed: PropertyValues<this>): void {
    const before = changed.get('preference')?.value?.weekStart ?? 'monday';
    if (this.scopeKey !== null && (changed.has('scopeKey') ||
        changed.has('preference') && this.shownMode === 'week' && before !== this.weekStart)) this.submit();
  }

  private get weekStart(): WeekStart {return this.preference?.value?.weekStart ?? 'monday';}
  private text(key: CalendarMessage): string {return calendarMessage(key, this.language);}
  private dayLabel(value: string): string {
    return new Intl.DateTimeFormat(this.language, {dateStyle: 'medium', timeZone: 'UTC'}).format(new Date(value));
  }
  private intent(detail: CalendarIntent): void {
    this.dispatchEvent(new CustomEvent<CalendarIntent>('domus-calendar-intent',
      {detail: Object.freeze(detail), bubbles: true, composed: true}));
  }
  private categoryIsUnavailable(category: string): boolean {
    return category !== '' && (this.unavailableCategories.has(category)
      || !this.categories?.some(item => item.id === category));
  }
  private submit(): void {
    if (this.scopeKey === null || !civilDate(this.anchor) || this.anchor > DATE_MAX) return;
    const range = calendarPeriod(this.mode, this.anchor, this.weekStart);
    const query = {...range,...this.filters};
    if (!calendarQuery(query) || this.categoryIsUnavailable(query.category)) return;
    this.shownMode = this.mode; this.shownRange = range; this.shownCategory = query.category;
    this.intent({type: 'load', query});
  }

  private renderEntry(item: CalendarEntry) {
    return html`<li><strong>${item.title}</strong> · ${this.text(item.kind)}
      ${item.categoryLabel ? html`<small>${this.text('category')} ${item.categoryLabel}</small>` : nothing}
      ${item.time === null ? nothing : html`<time>${item.time}</time> ${item.zone}`}
      ${item.verification === null ? nothing : this.text(item.verification === 'pending' ? 'verificationPending' : item.verification as CalendarMessage)}
      ${item.nominal !== null && item.nominal !== item.resolved ? html`<small>${this.text('adjusted')} ${item.nominal}</small>` : nothing}
      ${item.relativeReviewRequired ? html`<small>${this.text('relativeReviewRequired')}</small>` : nothing}
    </li>`;
  }

  private select<T extends string>(label: CalendarMessage, value: T | '', options: readonly T[],
    caption: (option: T) => string, change: (value: T | '') => void, all = true, unavailable?: T) {
    return html`<label>${this.text(label)}<select .value=${value}
      aria-invalid=${unavailable === undefined ? nothing : 'true'}
      aria-describedby=${unavailable === undefined ? nothing : 'calendar-category-error'}
      @change=${(event: Event) => change((event.target as HTMLSelectElement).value as T | '')}>
      ${all ? html`<option value="">${this.text('any')}</option>` : nothing}
      ${options.map(option => html`<option value=${option} .selected=${value === option} ?disabled=${option === unavailable}>${caption(option)}</option>`)}
    </select></label>`;
  }

  private dates(entries: readonly CalendarEntry[]) {
    const range = this.shownRange!;
    const byDay = Map.groupBy(entries, entry => entry.day);
    const chronological = (day: string) => (byDay.get(day) ?? []).toSorted((a, b) => (a.time ?? '').localeCompare(b.time ?? ''));
    if (this.shownMode === 'month' || this.shownMode === 'week') {
      const padding = this.shownMode === 'month' ? calendarWeekOffset(new Date(range.start), this.weekStart) : 0;
      return html`<div class="grid-scroll"><ul class="calendar-grid">
        ${Array.from({length: padding}, () => html`<li aria-hidden="true"></li>`)}
        ${calendarDays(range).map(day => html`<li><time datetime=${day}>${this.dayLabel(day)}</time>
          <ul class="calendar-entries">${chronological(day).map(item => this.renderEntry(item))}</ul></li>`)}
      </ul></div>`;
    }
    return html`${[...byDay.keys()].sort().map(day => html`<section>
      <h3><time datetime=${day}>${this.dayLabel(day)}</time></h3>
      <ul class="calendar-entries">${chronological(day).map(item => this.renderEntry(item))}</ul></section>`)}`;
  }

  private preferences() {
    const value = this.preference;
    if (value === null) return nothing;
    return html`<div>
      <label>${this.text('weekStart')} <select .value=${this.weekStart}
        ?disabled=${value.value === null || value.readOnly || value.busy || value.pending}
        @change=${(event: Event) => {
          const input = event.target as HTMLSelectElement;
          const weekStart = input.value as WeekStart;
          input.value = this.weekStart;
          this.intent({type:'setWeekStart', weekStart});
        }}>
        ${WEEK_STARTS.map(day => html`<option value=${day} .selected=${this.weekStart === day}>${this.text(day)}</option>`)}
      </select></label>
      ${value.pending ? html`<button type="button" ?disabled=${value.busy}
        @click=${() => this.intent({type:'recoverPreference'})}>${this.text('recoverPreference')}</button>` : nothing}
      ${value.notice ? html`<p role="alert">${this.text(value.notice)}</p>` : nothing}
      ${value.value === null && !value.busy ? html`<button type="button"
        @click=${() => this.intent({type:'refreshPreference'})}>${this.text('refreshPreference')}</button>` : nothing}
    </div>`;
  }

  protected render() {
    const view = this.view, staleResult = this.categoryIsUnavailable(this.shownCategory);
    const page = this.shownRange === null || staleResult ? null : view?.page;
    const labels = new Map(this.categories?.filter(category => !this.unavailableCategories.has(category.id))
      .map(category => [category.id, category.label]));
    const staleCategory = this.categoryIsUnavailable(this.filters.category) ? this.filters.category : undefined;
    if (staleCategory !== undefined) labels.set(staleCategory, this.text('categoryUnavailable'));
    return html`<section class="card" aria-labelledby="calendar-title" aria-busy=${view?.status === 'loading'}>
      <h2 id="calendar-title">${this.text('title')}</h2>
      ${this.preferences()}
      <form @submit=${(event: SubmitEvent) => {event.preventDefault(); this.submit();}}>
        <div class="filters">
          ${this.select('view', this.mode, CALENDAR_MODES, mode => this.text(mode), mode => {if (mode !== '') this.mode = mode;}, false)}
          <label>${this.text('date')}<input type="date" min=${DATE_MIN} max=${DATE_MAX} required .value=${this.anchor}
            @change=${(event: Event) => {this.anchor = (event.target as HTMLInputElement).value;}}></label>
          ${this.select('kind', this.filters.kind, CALENDAR_KINDS, kind => this.text(kind), kind => {this.filters = {...this.filters, kind};})}
          ${this.select('timing', this.filters.timing, CALENDAR_TIMINGS, timing => this.text(timing), timing => {this.filters = {...this.filters, timing};})}
          ${this.select('status', this.filters.state, TASK_STATES, state => taskMessage(`state_${state}`, this.language), state => {this.filters = {...this.filters, state};})}
          ${this.select('priority', this.filters.priority, TASK_PRIORITIES, priority => taskMessage(`priority_${priority}`, this.language), priority => {this.filters = {...this.filters, priority};})}
          ${this.select('category', this.filters.category, [...labels.keys()], category => labels.get(category)!,
            category => {this.filters = {...this.filters, category};}, true, staleCategory)}
          <label><input type="checkbox" .checked=${this.filters.own}
            @change=${(event: Event) => {this.filters = {...this.filters, own: (event.target as HTMLInputElement).checked};}}>${this.text('mine')}</label>
        </div>
        ${staleCategory !== undefined || staleResult ? html`<p id="calendar-category-error" role="alert">${this.text('chooseAvailableCategory')}</p>` : nothing}
        <button type="submit" ?disabled=${this.scopeKey === null || view?.status === 'loading' || staleCategory !== undefined}>${this.text('apply')}</button>
      </form>
      ${view?.status === 'loading' ? html`<p role="status">${this.text('loading')}</p>` : nothing}
      ${view?.status === 'unavailable' ? html`<p role="alert">${this.text('unavailable')}</p>` : nothing}
      ${page ? html`<p role="status">${this.text('total')} ${page.count}. ${this.text('occurrences')} ${page.occurrenceCount}</p>
        ${page.pending ? html`<p role="status">${this.text('pending')}</p>` : nothing}
        ${page.entries.length === 0 && !page.pending ? html`<p>${this.text('empty')}</p>` : nothing}
        ${this.dates(page.entries)}
        ${page.cursor === null ? nothing : html`<button type="button" ?disabled=${view?.status === 'loading'}
          @click=${() => this.intent({type: 'more'})}>${this.text('more')}</button>`}` : nothing}
    </section>`;
  }
}

customElements.define('domus-calendar', DomusCalendar);
declare global {interface HTMLElementTagNameMap {'domus-calendar': DomusCalendar;}}
