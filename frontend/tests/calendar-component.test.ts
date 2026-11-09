import {afterEach, expect, test, vi} from 'vitest';
import '../src/presentation/domus-calendar';
import {DATE_MAX} from '../src/domain/calendar';
import type {CalendarEntry} from '../src/domain/calendar';

const planned: CalendarEntry = {id: 'planned:work', kind: 'planned', title: '<b>Set clocks</b>', day: '2026-11-01',
  time: null, zone: null, nominal: null, resolved: null, verification: null};
const approval: CalendarEntry = {...planned, id: 'approval:cycle', kind: 'approval', title: 'Clock review',
  time: '09:30:00', zone: 'Europe/Madrid', nominal: '2026-11-01T08:30', resolved: '2026-11-01T09:30', verification: 'pending'};
const empty = {entries: [], count: 0, occurrenceCount: 0, cursor: null, pending: false};
const nodes: HTMLElement[] = [];
afterEach(() => {for (const node of nodes.splice(0)) node.remove();});

test('calendar owns its range, filters and scope and distinguishes literal date-only and timed facts in both languages', async () => {
  const element = document.createElement('domus-calendar'), listener = vi.fn();
  element.addEventListener('domus-calendar-intent', listener);
  document.body.append(element); nodes.push(element); await element.updateComplete;
  const root = element.shadowRoot!;
  const form = root.querySelector('form')!;
  const submit = () => form.dispatchEvent(new Event('submit', {cancelable: true}));
  submit();
  expect(listener).not.toHaveBeenCalled();
  element.today = '2026-11-03'; element.scopeKey = 'first'; await element.updateComplete;
  expect(listener).toHaveBeenLastCalledWith(expect.objectContaining({detail: {type: 'load', query: {
    start: '2026-11-01', end: '2026-12-01', kind: '', timing: '', state: '', priority: '', category: '', own: false}}}));
  element.view = {status: 'loading', page: null}; await element.updateComplete;
  expect(root.textContent).toContain('Loading calendar.');
  expect(form.querySelector('button')!.disabled).toBe(true);
  element.view = {status: 'ready', page: empty}; await element.updateComplete;
  expect(root.textContent).toContain('There are no matching entries');
  expect(root.querySelectorAll('.calendar-grid > li')).toHaveLength(36);
  const selects = [...form.querySelectorAll('select')];
  const select = (index: number, value: string) => {
    selects[index].value = value; selects[index].dispatchEvent(new Event('change'));
  };
  const date = form.querySelector<HTMLInputElement>('input[type=date]')!;
  const dateValue = (value: string) => {date.value = value; date.dispatchEvent(new Event('change'));};
  select(0, ''); dateValue(''); submit();
  dateValue('9998-12-02'); submit();
  expect(listener).toHaveBeenCalledOnce();
  select(0, 'month'); dateValue(DATE_MAX); submit();
  expect(listener).toHaveBeenCalledTimes(2);
  expect(listener).toHaveBeenLastCalledWith(expect.objectContaining({detail: {type: 'load', query: {
    start: '9998-12-01', end: '9999-01-01', kind: '', timing: '', state: '', priority: '', category: '', own: false}}}));
  select(0, 'week'); select(1, 'approval'); select(2, 'manual'); select(3, 'completed'); select(4, 'high');
  const tag = form.querySelector<HTMLInputElement>('input[name=category]')!;
  tag.value = 'Hogar & más'; tag.dispatchEvent(new Event('input'));
  const own = form.querySelector<HTMLInputElement>('input[type=checkbox]')!;
  own.checked = true; own.dispatchEvent(new Event('change'));
  dateValue('2026-11-01'); submit();
  expect(listener).toHaveBeenLastCalledWith(expect.objectContaining({detail: {type: 'load', query: {
    start: '2026-10-26', end: '2026-11-02', kind: 'approval', timing: 'manual', state: 'completed',
    priority: 'high', category: 'Hogar & más', own: true}}}));
  element.view = {status: 'ready', page: {entries: [approval, planned, {...planned, id: 'planned:other', title: 'Wash clocks'}, {...approval, id: 'approval:other',
    title: 'Verified', verification: 'approved', nominal: approval.resolved}], count: 4, occurrenceCount: 2, cursor: 'more', pending: true}};
  await element.updateComplete;
  expect(root.querySelectorAll('.calendar-grid > li')).toHaveLength(7);
  expect(root.textContent).toContain('Recurrence processing is pending.');
  expect(root.textContent).toContain('Matching entries 4. Matching tasks 2');
  const entries = [...root.querySelectorAll('.calendar-entries li')];
  expect(entries.map(item => item.querySelector('strong')!.textContent)).toEqual(['<b>Set clocks</b>', 'Wash clocks', 'Clock review', 'Verified']);
  expect(entries[0].querySelector('time, b')).toBeNull();
  expect(entries[2].textContent).toContain('Pending approval');
  expect(entries[2].textContent).toContain('Original local time');
  expect(entries[3].textContent).toContain('Approved');
  root.querySelector<HTMLButtonElement>('button[type=button]')!.click();
  expect(listener).toHaveBeenLastCalledWith(expect.objectContaining({detail: {type: 'more'}}));
  element.language = 'es'; select(0, 'agenda'); submit(); await element.updateComplete;
  expect(root.textContent).toContain('Vista del calendario');
  expect(root.textContent).toContain('Entradas que coinciden 4. Tareas que coinciden 2');
  expect(root.querySelector('h3')!.textContent).toContain('2026');
  expect(root.querySelector('.calendar-grid')).toBeNull();
  element.view = {status: 'unavailable', page: null}; await element.updateComplete;
  expect(root.querySelector('[role=alert]')!.textContent).toContain('No se pudo cargar');
  expect(date.value).toBe('2026-11-01');
  expect(selects.map(input => input.value)).toEqual(['agenda', 'approval', 'manual', 'completed', 'high']);
  expect(tag.value).toBe('Hogar & más'); expect(own.checked).toBe(true);
  element.scopeKey = null; await element.updateComplete;
  expect(date.value).toBe('2026-11-03');
  expect(own.checked).toBe(false); expect(tag.value).toBe('');
});


test('category filters preserve up to 64 Unicode code points and reject oversized drafts', async () => {
  const element = document.createElement('domus-calendar'), sent = vi.fn();
  element.addEventListener('domus-calendar-intent',sent);
  document.body.append(element); nodes.push(element);
  element.today='2026-11-01'; element.scopeKey='unicode-member'; await element.updateComplete;
  const root=element.shadowRoot!, input=root.querySelector<HTMLInputElement>('input[name=category]')!;
  const form=root.querySelector('form')!;
  expect(input.hasAttribute('maxlength')).toBe(false);
  for (const language of ['en','es'] as const) {
    element.language=language; await element.updateComplete;
    input.value='🌿'.repeat(64); input.dispatchEvent(new Event('input'));
    expect(input.validity.valid).toBe(true);
    form.dispatchEvent(new Event('submit',{cancelable:true}));
    expect(sent.mock.calls.at(-1)?.[0].detail.query.category).toBe('🌿'.repeat(64));
    const count=sent.mock.calls.length;
    input.value='🌿'.repeat(65); input.dispatchEvent(new Event('input'));
    expect(input.validity.customError).toBe(true);
    expect(input.validationMessage).toContain('64');
    form.dispatchEvent(new Event('submit',{cancelable:true}));
    expect(sent).toHaveBeenCalledTimes(count);
    expect(input.value).toBe('🌿'.repeat(65));
  }
  element.language='en'; await element.updateComplete;
  expect(input.validationMessage).toBe('Use at most 64 characters for the category.');
  element.scopeKey='other-member'; await element.updateComplete;
  expect(input.value).toBe('');
  expect(input.validity.valid).toBe(true);
});
