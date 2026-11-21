import {afterEach, expect, test, vi} from 'vitest';
import type {DailyView} from '../src/application/automation-daily';
import type {DailyHistoryView, ScheduledAutomationRun} from '../src/application/automation-daily-history';
import {active, inactive, one, point, policy, times, two} from './automation-daily-fixtures';
import '../src/presentation/domus-automation-daily';
import '../src/presentation/domus-automation-daily-history';

afterEach(() => document.querySelectorAll('domus-automation-daily, domus-automation-daily-history').forEach(node => node.remove()));
const initial: DailyView = {review: inactive, confirmation: null, result: null, notice: null,
  busy: false, pending: false, readOnly: false, savedRevision: two};

test('daily review exposes saved conditions, pinned timing and explicit localized grant management with focus', async () => {
  const element = document.createElement('domus-automation-daily');
  document.body.append(element); await element.updateComplete;
  const root = element.shadowRoot!, intents = vi.fn();
  element.addEventListener('domus-automation-daily-intent', intents);
  let current = initial;
  const view = async (patch: Partial<DailyView>) => {current = {...current, ...patch}; element.view = current; await element.updateComplete;};
  const button = (intent: string) => root.querySelector<HTMLElementTagNameMap['vyp-ha-button']>(`[data-intent="${intent}"]`);
  const press = (intent: string) => button(intent)!.dispatchEvent(new CustomEvent('ha-press-request'));
  expect(root.querySelector('vyp-ha-card')).toBeNull();
  await view({});
  expect(button('enable')?.state?.label).toBe('Enable this daily revision');
  expect(root.textContent).toContain('Check the soap');
  expect(root.textContent).toContain('No condition.');
  expect(root.querySelectorAll('details ol li')).toHaveLength(5);
  expect(root.querySelector('time')?.dateTime).toBe('2026-11-22T06:30:00.000Z');
  press('enable'); expect(intents.mock.lastCall?.[0].detail).toBe('enable');
  const confirmation = {kind: 'enable' as const, ruleId: 'rule', ruleRevision: two, controlRevision: '0' as const,
    scheduleRevision: '0' as const, reviewed: point()};
  await view({confirmation});
  expect(root.activeElement?.id).toBe('daily-confirmation');
  expect(root.textContent).toContain('This replaces any enabled revision');
  press('cancel'); expect(intents.mock.lastCall?.[0].detail).toBe('cancel');
  await view({confirmation: null});
  await vi.waitFor(() => expect(root.activeElement).toBe(button('enable')));
  await view({review: {...active, condition: {kind: 'all', children: [{kind: 'not', child: {
    kind: 'stock_below_minimum', product_id: 'soap'}}, {kind: 'any', children: [{kind: 'stock_below_minimum', product_id: 'tea'}]}]}}});
  expect(root.textContent).toContain('All of these'); expect(root.textContent).toContain('At least one of these');
  expect(root.textContent).toContain('Not'); expect(root.textContent).toContain('soap');
  expect(button('active')).not.toBeNull();
  expect(button('adopt')).toBeNull();
  await view({review: {...active, ruleRevision: one, mayEnable: false, policyChanged: true, approvedUnavailable: true,
    approvedTimes: null, suppression: {first: point(), throughMs: 1795329000000}}});
  expect(button('saved')).not.toBeNull(); expect(button('adopt')?.disabled).toBe(false);
  expect(button('disable')?.disabled).toBe(false); expect(button('enable')).toBeNull();
  expect(root.textContent).toContain('The household timing has changed.');
  expect(root.textContent).toContain('Skipped while stopped');
  expect([...root.querySelectorAll('vyp-ha-feedback')].map(node => node.state?.message).join(' ')).toContain('cannot currently be resolved');
  await view({confirmation: {...confirmation, kind: 'adopt', ruleRevision: one}});
  expect(root.textContent).toContain('Already admitted runs keep their original timing.');
  element.language = 'es'; await element.updateComplete;
  expect(button('confirm')?.state?.label).toBe('Confirmar');
  expect(root.textContent).toContain('Horario aprobado');
  await view({confirmation: {...confirmation, kind: 'disable', reviewed: undefined}, readOnly: true});
  expect(button('confirm')?.disabled).toBe(true);
  expect(root.textContent).toContain('Se conservarán las tareas ya creadas');
  await view({review: {...inactive, mayEnable: false, activeTrigger: 'manual', activeRevision: one, activeTitle: 'Manual task'},
    confirmation: null, readOnly: false});
  expect(button('enable')?.disabled).toBe(true);
  expect(root.textContent).toContain('Hay una revisión manual habilitada.');
  await view({review: {...active, activeRevision: two, proposedTimes: [], proposedUnavailable: true, policyChanged: true}});
  expect(button('disable')?.disabled).toBe(false);
  expect(button('adopt')?.disabled).toBe(true);
  expect([...root.querySelectorAll('vyp-ha-feedback')].map(node => node.state?.message).join(' ')).toContain('Puedes deshabilitar la regla diaria');
});

test('daily review shows real gap and fold explanations, committed results and recoverable failures separately', async () => {
  const element = document.createElement('domus-automation-daily'); document.body.append(element);
  element.view = {...initial, review: null, notice: 'unavailable'}; await element.updateComplete;
  const root = element.shadowRoot!;
  expect(root.querySelector('[data-intent="reload"]')).not.toBeNull();
  for (const resolution of ['gap_first_valid', 'fold_first', 'fold_second'] as const) {
    const first = {...point(), resolution, nominal: '2026-03-29T02:30:00', resolvedLocal: '2026-03-29T03:00:00',
      policy: {...policy, repeatedTime: 'second_instant' as const}};
    element.view = {...initial, review: {...active, proposedTimes: [first, ...times.slice(1)]}};
    await element.updateComplete;
    expect(root.querySelectorAll('time')).toHaveLength(11);
    if (resolution === 'gap_first_valid') expect(root.textContent).toContain('Requested local time');
  }
  for (const action of ['enable', 'disable', 'adopt'] as const) {
    element.view = {...initial, review: null, notice: 'unavailable',
      result: {kind: 'committed', action, ruleId: 'rule', ruleRevision: two, operationId: 'real-operation', next: point()}};
    await element.updateComplete;
    expect(root.activeElement?.id).toBe('daily-result');
    expect(root.querySelector('#daily-result')?.textContent).toContain(action === 'enable' ? 'granted' : action === 'disable' ? 'revoked' : 'adopted');
    expect(root.textContent).toContain('real-operation');
  }
  element.view = {...element.view, result: {...element.view.result!, kind: 'historical'}, pending: true, notice: 'uncertain', busy: true};
  await element.updateComplete;
  expect(root.textContent).toContain('This receipt does not activate the current rule');
  expect(root.querySelector<HTMLElementTagNameMap['vyp-ha-button']>('[data-intent="recover"]')?.disabled).toBe(true);
  expect([...root.querySelectorAll('vyp-ha-feedback')].some(node => node.state?.kind === 'loading')).toBe(true);
  element.view = {...element.view, busy: false}; await element.updateComplete;
  expect(root.querySelector<HTMLElementTagNameMap['vyp-ha-button']>('[data-intent="recover"]')?.disabled).toBe(false);
});

test('scheduled history distinguishes terminal outcomes, historical admissions and permission-safe task navigation in both languages', async () => {
  const element = document.createElement('domus-automation-daily-history'); document.body.append(element); await element.updateComplete;
  const root = element.shadowRoot!, intents = vi.fn(), navigate = vi.fn();
  element.addEventListener('domus-automation-daily-history-intent', intents);
  element.addEventListener('domus-automation-task-intent', navigate);
  const base: ScheduledAutomationRun = {key: 'f'.repeat(64), ruleRevision: one, controlRevision: two,
    requestedLocal: point().nominal, resolvedLocal: point().resolvedLocal, scheduledAt: 1795329000000,
    timeZone: 'Europe/Madrid', resolution: 'exact', admittedAt: 1795329000001, outcome: 'queued',
    finishedAt: null, historical: false, taskOccurrenceId: null, operationId: null};
  const view = async (value: DailyHistoryView) => {element.view = value; await element.updateComplete;};
  const press = (label: string) => [...root.querySelectorAll('vyp-ha-button')]
    .find(node => node.state?.label === label)!.dispatchEvent(new CustomEvent('ha-press-request'));
  expect(root.querySelector('vyp-ha-card')).toBeNull();
  await view({phase: 'closed', items: [], hasOlder: false, timeZone: 'UTC'});
  press('Show daily history'); expect(intents.mock.lastCall?.[0].detail).toBe('open');
  await view({phase: 'ready', items: [], hasOlder: false, timeZone: 'UTC'});
  expect(root.textContent).toContain('No scheduled run has been admitted');
  const rows = [base, {...base, key: 'e'.repeat(64), historical: true}, ...(['created', 'no_task', 'cancelled', 'denied'] as const)
    .map((outcome, index) => ({...base, key: String(index).repeat(64), outcome, finishedAt: 1795329000002,
      operationId: 'operation-' + index, taskOccurrenceId: outcome === 'created' ? 'created-task' : null,
      resolution: (['exact', 'gap_first_valid', 'fold_first', 'fold_second'] as const)[index]}))];
  await view({phase: 'ready', items: rows, hasOlder: true, timeZone: 'UTC'});
  expect(root.textContent).toContain('Admitted and waiting.');
  expect(root.textContent).toContain('This historical admission is not current queued work.');
  expect(root.textContent).toContain('No task was created.');
  expect(root.querySelectorAll('a')).toHaveLength(1);
  root.querySelector('a')!.click(); expect(navigate.mock.lastCall?.[0].detail).toEqual({type: 'select', occurrenceId: 'created-task'});
  press('Older daily runs'); expect(root.activeElement?.tagName).toBe('SECTION');
  expect(intents.mock.lastCall?.[0].detail).toBe('older');
  press('Recent daily runs'); expect(intents.mock.lastCall?.[0].detail).toBe('latest');
  element.language = 'es'; await element.updateComplete;
  expect(root.textContent).toContain('Esta admisión histórica no es trabajo pendiente actual.');
  for (const phase of ['loading', 'unavailable', 'expired', 'denied'] as const) {
    await view({phase, items: phase === 'loading' || phase === 'unavailable' ? rows : [], hasOlder: false, timeZone: 'UTC'});
    if (phase === 'unavailable') {press('Volver a intentar'); expect(intents.mock.lastCall?.[0].detail).toBe('retry');}
  }
  press('Ocultar historial diario'); expect(intents.mock.lastCall?.[0].detail).toBe('close');
});

test.each(['scope', 'detach'])('pending button focus cannot survive a rapid %s retirement', async reason => {
  const element = document.createElement('domus-automation-daily'); document.body.append(element);
  element.view = {...initial, confirmation: {kind: 'enable', ruleId: 'rule', ruleRevision: two,
    controlRevision: '0', scheduleRevision: '0', reviewed: point()}};
  await element.updateComplete;
  element.view = initial;
  await element.updateComplete;
  const button = element.shadowRoot!.querySelector<HTMLElementTagNameMap['vyp-ha-button']>('[data-intent="enable"]')!;
  const focus = vi.spyOn(button, 'focus');
  if (reason === 'scope') {element.view = null; await element.updateComplete;}
  else element.remove();
  await Promise.resolve();
  expect(focus).not.toHaveBeenCalled();
});

test('an unknown write focuses original recovery and never calls the former disabled state current', async () => {
  const element = document.createElement('domus-automation-daily'); document.body.append(element);
  element.view = {...initial, confirmation: {kind: 'enable', ruleId: 'rule', ruleRevision: two,
    controlRevision: '0', scheduleRevision: '0', reviewed: point()}};
  await element.updateComplete;
  element.view = {...initial, review: null, busy: true, pending: true}; await element.updateComplete;
  element.view = {...element.view, busy: false, notice: 'uncertain'}; await element.updateComplete;
  const root = element.shadowRoot!, recover = root.querySelector('[data-intent="recover"]');
  await vi.waitFor(() => expect(root.activeElement).toBe(recover));
  expect(root.textContent).not.toContain('Daily automation is disabled');
  expect(root.textContent).not.toContain('Daily automation is enabled');
  element.view = {...initial, notice: 'record_failed'}; await element.updateComplete;
  expect(root.querySelector('vyp-ha-feedback')?.state?.message).toContain('No change was sent.');
});
