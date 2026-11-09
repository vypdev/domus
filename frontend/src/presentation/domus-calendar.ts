import {LitElement, css, html, nothing} from 'lit';
import type {PropertyValues} from 'lit';
import type {CalendarPreferenceView} from '../application/calendar-preferences';
import type {CalendarView} from '../application/calendar-controller';
import {CALENDAR_KINDS, CALENDAR_MODES, CALENDAR_TIMINGS, DATE_MAX, DATE_MIN, calendarDays, calendarPeriod, calendarQuery, calendarWeekOffset, civilDate, WEEK_STARTS} from '../domain/calendar';
import type {CalendarEntry, CalendarMode, CalendarPeriod, CalendarQuery, WeekStart} from '../domain/calendar';
import {TASK_PRIORITIES, TASK_STATES} from '../domain/tasks';
import {calendarMessage} from './calendar-messages';
import type {CalendarMessage} from './calendar-messages';
import type {Language} from './messages';
import {styles} from './styles';
import {taskMessage} from './task-messages';

export type CalendarIntent = {readonly type: 'load'; readonly query: CalendarQuery} | {readonly type: 'more' | 'recoverPreference' | 'refreshPreference'}
  | {readonly type: 'setWeekStart'; readonly weekStart: WeekStart};

export class DomusCalendar extends LitElement {
  static properties = {preference: {attribute:false}, view: {attribute: false}, language: {attribute: false}, scopeKey: {attribute: false},
    today: {attribute: false}, anchor: {state: true}, mode: {state: true}, filters: {state: true},
    shownMode: {state: true}, shownRange: {state: true}};
  static styles = [styles, css`
    .filters{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(min(100%,150px),1fr))}
    .filters .field{margin:0}.calendar-grid{display:grid;grid-template-columns:repeat(7,minmax(100px,1fr));
      gap:4px;margin:0;padding:0;list-style:none;min-width:700px}
    .grid-scroll{overflow:auto}.calendar-grid li{border:1px solid var(--line);padding:8px;overflow-wrap:anywhere}
    .calendar-entries{padding-inline-start:20px;overflow-wrap:anywhere}
  `];
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

  constructor() {
    super(); this.preference = null; this.view = null; this.language = 'en'; this.scopeKey = null; this.today = DATE_MIN;
    this.anchor = DATE_MIN; this.mode = 'month'; this.shownMode = 'month'; this.shownRange = null;
    this.filters = {kind: '', timing: '', state: '', priority: '', category: '', own: false};
  }

  protected willUpdate(changed: PropertyValues<this>): void {
    if (changed.has('scopeKey')) {
      this.anchor = this.today; this.mode = 'month'; this.shownRange = null;
      this.filters = {kind: '', timing: '', state: '', priority: '', category: '', own: false};
    }
  }
  protected updated(changed: PropertyValues<this>): void {
    this.categoryValidity(this.renderRoot.querySelector<HTMLInputElement>('input[name=category]')!);
    const before = changed.get('preference')?.value?.weekStart ?? 'monday';
    if (this.scopeKey !== null && (changed.has('scopeKey') ||
        changed.has('preference') && this.shownMode === 'week' && before !== this.weekStart)) this.submit();
  }

  private get weekStart(): WeekStart {return this.preference?.value?.weekStart ?? 'monday';}
  private categoryValidity(input: HTMLInputElement): void {
    input.setCustomValidity(Array.from(input.value).length > 64 ? this.text('categoryLimit') : '');
  }
  private text(key: CalendarMessage): string {return calendarMessage(key, this.language);}
  private dayLabel(value: string): string {
    return new Intl.DateTimeFormat(this.language, {dateStyle: 'medium', timeZone: 'UTC'}).format(new Date(value));
  }
  private intent(detail: CalendarIntent): void {
    this.dispatchEvent(new CustomEvent<CalendarIntent>('domus-calendar-intent',
      {detail: Object.freeze(detail), bubbles: true, composed: true}));
  }
  private submit(): void {
    if (this.scopeKey === null || !civilDate(this.anchor) || this.anchor > DATE_MAX) return;
    const range = calendarPeriod(this.mode, this.anchor, this.weekStart);
    const query = {...range,...this.filters};
    if (!calendarQuery(query)) return;
    this.shownMode = this.mode; this.shownRange = range;
    this.intent({type: 'load', query});
  }

  private renderEntry(item: CalendarEntry) {
    return html`<li><strong>${item.title}</strong> · ${this.text(item.kind)}
      ${item.time === null ? nothing : html`<time>${item.time}</time> ${item.zone}`}
      ${item.verification === null ? nothing : this.text(item.verification === 'pending' ? 'verificationPending' : item.verification as CalendarMessage)}
      ${item.nominal !== null && item.nominal !== item.resolved ? html`<small>${this.text('adjusted')} ${item.nominal}</small>` : nothing}
      ${item.relativeReviewRequired ? html`<small>${this.text('relativeReviewRequired')}</small>` : nothing}
    </li>`;
  }

  private select<T extends string>(label: CalendarMessage, value: T | '', options: readonly T[],
    caption: (option: T) => string, change: (value: T | '') => void, all = true) {
    return html`<label>${this.text(label)}<select .value=${value}
      @change=${(event: Event) => change((event.target as HTMLSelectElement).value as T | '')}>
      ${all ? html`<option value="">${this.text('any')}</option>` : nothing}
      ${options.map(option => html`<option value=${option} .selected=${value === option}>${caption(option)}</option>`)}
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
    const view = this.view, page = this.shownRange === null ? null : view?.page;
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
          <label>${this.text('category')}<input name="category" .value=${this.filters.category}
            @input=${(event: Event) => {
              const input = event.target as HTMLInputElement, category = input.value;
              this.categoryValidity(input);
              this.filters = {...this.filters, category};
            }}></label>
          <label><input type="checkbox" .checked=${this.filters.own}
            @change=${(event: Event) => {this.filters = {...this.filters, own: (event.target as HTMLInputElement).checked};}}>${this.text('mine')}</label>
        </div>
        <button type="submit" ?disabled=${this.scopeKey === null || view?.status === 'loading'}>${this.text('apply')}</button>
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
