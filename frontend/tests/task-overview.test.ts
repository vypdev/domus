import {afterEach, expect, test, vi} from 'vitest';
import {EntryReadError} from '../src/application/ports';
import {TaskOverviewController} from '../src/application/task-overview';
import type {TaskOverview} from '../src/application/task-overview';
import '../src/presentation/domus-task-overview';

const context = {installationId: '01234567-89ab-cdef-0123-456789abcdef', channel: 'edge' as const, subject: 'a'.repeat(32)};
const scope = {key: 'first', context};
const overview: TaskOverview = {assigned: {total: 2, items: [{id: 'work-1', title: 'Fold <b>laundry</b>', state: 'assigned'}]},
  unclaimed: {total: 0, items: []},
  overdue: {total: 1, items: [{id: 'late', title: 'Change filter', state: 'blocked',
    deadline: {day: '2026-04-02', instant: null, zone: 'Europe/Madrid'}}]},
  dueToday: {total: 1, items: [{id: 'due', title: 'Check meter', state: 'available',
    deadline: {day: null, instant: Date.parse('2026-04-02T07:00:00Z'), zone: 'Europe/Madrid'}}]},
  upcomingMaintenance: {total: 1, items: [{id: 'maintenance', title: 'Drain the tank', state: 'assigned',
    deadline: {day: '2026-04-05', instant: null, zone: 'Europe/Madrid'}}]}};

function deferred() {
  let resolve!: (value: TaskOverview) => void;
  let reject!: (error: unknown) => void;
  const result = new Promise<TaskOverview>((done, failed) => {resolve = done; reject = failed;});
  return {result, resolve, reject, cancel: vi.fn()};
}

test('Overview retires obsolete responses on refresh and account change', async () => {
  const first = deferred(), refresh = deferred(), next = deferred(), closed = deferred();
  const read = vi.fn().mockReturnValueOnce(first).mockReturnValueOnce(refresh)
    .mockReturnValueOnce(next).mockReturnValueOnce(closed);
  const publish = vi.fn();
  const controller = new TaskOverviewController({overview: read}, publish);
  await controller.refresh();
  controller.bind(null);
  expect(read).not.toHaveBeenCalled();
  controller.bind(scope);
  controller.bind(scope);
  expect(read).toHaveBeenCalledTimes(1);
  expect(publish).toHaveBeenLastCalledWith({state: 'loading'});
  const retry = controller.refresh();
  expect(first.cancel).toHaveBeenCalledOnce();
  first.resolve(overview);
  await first.result;
  expect(publish).toHaveBeenLastCalledWith({state: 'loading'});

  const nextContext = {...context, subject: 'b'.repeat(32)};
  controller.bind({key: 'second', context: nextContext});
  expect(refresh.cancel).toHaveBeenCalledOnce();
  refresh.reject(new Error('stale read'));
  await retry;
  expect(read).toHaveBeenLastCalledWith(nextContext);
  expect(publish).toHaveBeenLastCalledWith({state: 'loading'});
  next.resolve(overview);
  await next.result;
  expect(publish).toHaveBeenLastCalledWith({state: 'ready', overview});

  const retired = controller.refresh();
  controller.bind(null);
  expect(closed.cancel).toHaveBeenCalledOnce();
  closed.resolve(overview);
  await retired;
  expect(publish).toHaveBeenLastCalledWith(null);
});

test.each([
  [new EntryReadError('forbidden'), 'denied'],
  [new EntryReadError('authentication_required'), 'denied'],
  [new EntryReadError('invalid_response'), 'unavailable'],
  [new Error('local service unavailable'), 'unavailable'],
] as const)('Overview maps %s without exposing an empty count', async (error, state) => {
  const request = deferred(), publish = vi.fn();
  const controller = new TaskOverviewController({overview: () => request}, publish);
  controller.bind(scope);
  request.reject(error);
  await request.result.catch(() => {});
  expect(publish).toHaveBeenLastCalledWith({state});
});

afterEach(() => document.querySelectorAll('domus-task-overview').forEach(item => item.remove()));

test('Overview shows localized states and emits only task selection or retry', async () => {
  const element = document.createElement('domus-task-overview');
  document.body.append(element);
  const intent = vi.fn();
  element.addEventListener('domus-task-overview-intent', intent);
  await element.updateComplete;
  expect(element.shadowRoot!.querySelector('section')).toBeNull();
  element.view = {state: 'loading'};
  await element.updateComplete;
  const feedback = () => element.shadowRoot!.querySelector('vyp-ha-feedback')!;
  expect(feedback().state).toMatchObject({message: 'Loading task summary…'});
  element.view = {state: 'denied'};
  element.language = 'es';
  await element.updateComplete;
  expect(feedback().state).toMatchObject({message: expect.stringContaining('Tu acceso actual')});
  expect(element.shadowRoot!.querySelector('vyp-ha-card')).toBeNull();
  element.view = {state: 'unavailable'};
  await element.updateComplete;
  expect(feedback().state).toMatchObject({message: expect.stringContaining('No se ha podido cargar')});
  const press = async (title?: string) => {
    const buttons = [...element.shadowRoot!.querySelectorAll('vyp-ha-button')];
    const button = title === undefined ? buttons[0] : buttons.find(item => item.state.label.startsWith(title))!;
    await button.updateComplete;
    button.shadowRoot!.querySelector('button')!.click();
    return button;
  };
  expect((await press()).state.label).toBe('Volver a cargar el resumen de tareas');
  expect(intent.mock.calls.at(-1)![0].detail).toEqual({type: 'refresh'});

  element.language = 'en';
  element.view = {state: 'ready', overview};
  await element.updateComplete;
  expect(Array.from(element.shadowRoot!.querySelectorAll('vyp-ha-card'), card => card.state.title))
    .toEqual(['Overdue · 1', 'Due today · 1', 'Upcoming maintenance · 1', 'Assigned to me · 2', 'Unclaimed tasks · 0']);
  expect(element.shadowRoot!.textContent).toContain('No tasks in this group.');
  expect(element.shadowRoot!.textContent).toContain('Open Tasks for the full list.');
  expect((await press('Fold')).state.label).toBe('Fold <b>laundry</b> · Assigned');
  expect(intent.mock.calls.at(-1)![0].detail).toEqual({type: 'select', occurrenceId: 'work-1'});
  expect((await press('Change filter')).state.label).toBe('Change filter · Apr 2, 2026 · Blocked');
  expect(intent.mock.calls.at(-1)![0].detail).toEqual({type: 'select', occurrenceId: 'late'});
  expect((await press('Check meter')).state.label).toMatch(/Apr 2, 2026.*9:00 AM/u);
  expect((await press('Drain the tank')).state.label).toBe('Drain the tank · Apr 5, 2026 · Assigned');
  expect(intent.mock.calls.at(-1)![0].detail).toEqual({type: 'select', occurrenceId: 'maintenance'});
  element.language = 'es';
  await element.updateComplete;
  expect(Array.from(element.shadowRoot!.querySelectorAll('vyp-ha-card'), card => card.state.title))
    .toEqual(['Vencidas · 1', 'Para hoy · 1', 'Próximos mantenimientos · 1', 'Asignadas a mí · 2', 'Tareas sin asignar · 0']);
  expect((await press('Check meter')).state.label).toMatch(/2 abr 2026.*9:00/u);
});
