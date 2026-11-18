import {afterEach, expect, test, vi} from 'vitest';
import {HttpAutomationSchedulePreview} from '../src/adapters/automation-schedule-preview-http';
import {AutomationSchedulePreviewController} from '../src/application/automation-schedule-preview';
import type {AutomationScheduleServer, DailyAutomationTime, SchedulePreviewScope, SchedulePreviewView}
  from '../src/application/automation-schedule-preview';
import {EntryReadError} from '../src/application/ports';
import '../src/presentation/domus-automation-schedule-preview';

const scope: SchedulePreviewScope = {key: 'owner', timeZone: 'Europe/Madrid',
  context: {installationId: '01234567-89ab-cdef-0123-456789abcdef', channel: 'edge', subject: 'a'.repeat(32)}};

function row(date: string, time = '02:30', offset = 7200, resolution: DailyAutomationTime['resolution'] = 'exact') {
  const resolved = date + 'T' + time + ':00.000';
  return {requested_date: date, resolved_local: resolved, instant_ms: Date.parse(resolved + 'Z') - offset * 1000,
    offset_seconds: offset, resolution};
}

const spring = row('2026-03-29', '03:00', 7200, 'gap_first_valid');
const regular = row('2026-03-30');
const rows = [spring, regular, row('2026-03-31'), row('2026-04-01'), row('2026-04-02')];
const result: DailyAutomationTime[] = rows.map(item => ({
  requestedDate: item.requested_date, resolvedLocal: item.resolved_local, instantMs: item.instant_ms,
  resolution: item.resolution,
}));
const preview = {type: 'preview'} as const;
const time = (value: string) => ({type: 'time', value} as const);

test('daily preview validates, serializes reads and retries with the same typed value', async () => {
  const daily = vi.fn<AutomationScheduleServer['daily']>(() => ({result: Promise.resolve(result), cancel: vi.fn()}));
  const publish = vi.fn<(next: SchedulePreviewView | null) => void>();
  const controller = new AutomationSchedulePreviewController({daily}, publish);
  const view = () => publish.mock.lastCall?.[0];
  await controller.handle(preview);
  controller.bind(null);
  expect(publish).not.toHaveBeenCalled();
  controller.bind(scope);
  expect(view()).toMatchObject({input: '', issue: null, result: null});
  for (const invalid of ['', '7:30', '24:00', '02:60', '02:30\n']) {
    await controller.handle(time(invalid));
    await controller.handle(preview);
    expect(view()).toMatchObject({input: invalid, issue: 'invalid'});
  }
  expect(daily).not.toHaveBeenCalled();
  await controller.handle(time('02:30'));
  controller.bind({...scope});
  const pending = Promise.withResolvers<readonly DailyAutomationTime[]>();
  daily.mockReturnValueOnce({result: pending.promise, cancel: vi.fn()});
  const first = controller.handle(preview);
  expect(view()).toMatchObject({input: '02:30', busy: true});
  await controller.handle(preview);
  expect(daily).toHaveBeenCalledOnce();
  pending.reject(new Error('connection lost'));
  await first;
  expect(view()).toMatchObject({input: '02:30', issue: 'unavailable', busy: false, result: null});
  await controller.handle(preview);
  expect(daily.mock.calls).toEqual([[scope, '02:30'], [scope, '02:30']]);
  expect(view()).toMatchObject({input: '02:30', issue: null, busy: false, result});
  for (const code of ['forbidden', 'authentication_required', 'unavailable'] as const) {
    daily.mockReturnValueOnce({result: Promise.reject(new EntryReadError(code)), cancel: vi.fn()});
    await controller.handle(preview);
    expect(view()).toMatchObject({input: '02:30', issue: code === 'unavailable' ? 'unavailable' : 'denied', result: null});
  }
});

test('edits, time policies and authorization changes discard late results', async () => {
  const daily = vi.fn<AutomationScheduleServer['daily']>();
  const publish = vi.fn<(next: SchedulePreviewView | null) => void>();
  const controller = new AutomationSchedulePreviewController({daily}, publish);
  controller.bind(scope);
  await controller.handle(time('02:30'));
  const obsolete = Promise.withResolvers<readonly DailyAutomationTime[]>(), cancel = vi.fn();
  daily.mockReturnValueOnce({result: obsolete.promise, cancel});
  const initial = controller.handle(preview);
  await controller.handle(time('04:00'));
  obsolete.resolve(result);
  await initial;
  expect(cancel).toHaveBeenCalledOnce();
  expect(publish.mock.lastCall?.[0]).toMatchObject({input: '04:00', busy: false, result: null});
  const revoked = Promise.withResolvers<readonly DailyAutomationTime[]>(), cancelRevoked = vi.fn();
  daily.mockReturnValueOnce({result: revoked.promise, cancel: cancelRevoked});
  const previous = controller.handle(preview);
  controller.bind({...scope, timeZone: 'UTC'});
  revoked.reject(new EntryReadError('forbidden'));
  await previous;
  expect(cancelRevoked).toHaveBeenCalledOnce();
  expect(publish.mock.lastCall?.[0]).toMatchObject({timeZone: 'UTC', input: '', issue: null});
  controller.bind({...scope, timeZone: 'UTC', key: 'viewer'});
  controller.bind(null);
  expect(publish.mock.lastCall?.[0]).toBeNull();
});

test('the HTTP adapter verifies five ordered rows, their civil values and their exact UTC instants', async () => {
  const target = {origin: 'https://domus.local', applicationBase: '/', deployment: 'standalone'} as const;
  const envelope = {time_zone: scope.timeZone, requested_time: '02:30', items: rows};
  let payload: unknown = envelope, status = 200;
  const fetch = vi.fn(async (route: string, _init: RequestInit) => {
    const response = new Response(JSON.stringify(payload), {status,
      headers: {'Content-Type': 'application/json', 'Cache-Control': 'no-store'}});
    Object.defineProperty(response, 'url', {value: target.origin + route});
    return response;
  });
  const adapter = new HttpAutomationSchedulePreview(target, fetch);
  await expect(adapter.daily(scope, '02:30').result).resolves.toEqual(result);
  expect(fetch.mock.lastCall?.[0]).toBe('/api/v1/automation/schedule-preview?time=02%3A30');
  expect(fetch.mock.lastCall?.[1].method).toBe('GET');
  for (const invalid of [
    {...envelope, time_zone:'UTC'}, {...envelope, requested_time:'03:30'}, {...envelope, items:{}},
    {...envelope, items:[spring]}, {...envelope, items:[...rows, regular]},
    ...[
      {...spring, requested_date:'2026-02-29'}, {...spring, resolved_local:'2026-02-29T02:30:00.000'},
      {...spring, resolved_local:'2026-03-29T24:00:00.000'}, {...spring, offset_seconds:86400},
      {...spring, instant_ms:spring.instant_ms + 1}, {...spring, resolution:'exact'},
      row('2026-03-29', '02:30', 3600, 'gap_first_valid'),
      row('2026-03-29', '02:00', 3600, 'gap_first_valid'),
      {...spring, resolution:'other'}, regular,
    ].map(item => ({...envelope, items:[item, ...rows.slice(1)]})),
    {...envelope, items:[spring, regular, {...regular, requested_date:'2026-03-31',
      resolution:'exact'}, ...rows.slice(3)]},
    {...envelope, items:[{...spring, requested_date:'2026-03-29', resolved_local:'2026-03-30T02:30:00.000',
      instant_ms:regular.instant_ms}, ...rows.slice(1)]},
    {...envelope, items:[spring, {...regular, requested_date:'2026-03-29', resolution:'gap_first_valid'}, ...rows.slice(2)]},
  ]) {
    payload = invalid;
    await expect(adapter.daily(scope, '02:30').result).rejects.toMatchObject({code:'invalid_response'});
  }
  status = 403;
  payload = {state:'blocked', code:'permission_denied', message:'Unable to read.',
    action_required:'Try again.', correlation_id:'cor_schedule'};
  await expect(adapter.daily(scope, '02:30').result).rejects.toMatchObject({code:'forbidden'});
});

afterEach(() => document.querySelectorAll('domus-automation-schedule-preview').forEach(node => node.remove()));

test('the panel announces validation, retry and precise local daylight-saving results in both languages', async () => {
  const element = document.createElement('domus-automation-schedule-preview');
  document.body.append(element);
  await element.updateComplete;
  const root = element.shadowRoot!;
  expect(root.querySelector('form')).toBeNull();
  const intents: unknown[] = [];
  element.addEventListener('domus-automation-schedule-preview-intent', event => intents.push((event as CustomEvent).detail));
  const display = async (patch: Partial<SchedulePreviewView>) => {
    element.view = {timeZone:scope.timeZone, input:'02:30', busy:false, issue:null, result:null, ...patch};
    await element.updateComplete;
  };
  await display({});
  await root.querySelector('vyp-ha-field')!.updateComplete;
  await display({issue:'invalid'});
  const field = root.querySelector('vyp-ha-field')!;
  expect(field.state?.error).toContain('00:00');
  await vi.waitFor(() => expect(root.activeElement).toBe(field));
  field.dispatchEvent(new CustomEvent('ha-value-request', {detail:{value:'02:30'}}));
  root.querySelector('form')!.dispatchEvent(new SubmitEvent('submit', {cancelable:true}));
  expect(intents).toEqual([time('02:30'), preview]);
  await display({busy:true});
  root.querySelector('form')!.dispatchEvent(new SubmitEvent('submit', {cancelable:true}));
  expect(intents).toHaveLength(2);
  expect(root.querySelector('vyp-ha-feedback')?.state?.kind).toBe('loading');
  await display({issue:'unavailable'});
  expect(root.querySelector('vyp-ha-button')?.state?.label).toBe('Try again');
  expect(field.value).toBe('02:30');
  await display({issue:'denied'});
  expect(root.querySelector('vyp-ha-feedback')?.state?.message).toContain('current permissions');
  await display({result});
  expect(root.querySelector('h3')?.textContent).toBe('Next five times');
  expect(root.querySelectorAll('li')).toHaveLength(5);
  expect(root.querySelector('time')?.dateTime).toBe('2026-03-29T01:00:00.000Z');
  expect(root.querySelector('li')?.textContent).toContain('Requested');
  expect(root.querySelector('li')?.textContent).toContain('03:00');
  element.language = 'es';
  const fall = [{...result[1], resolution:'fold_first'}, {...result[1], resolution:'fold_second'}] as const;
  await display({result:fall});
  expect(root.querySelector('h3')?.textContent).toBe('Próximas cinco fechas');
  expect(root.textContent).toContain('Primera aparición de la hora repetida.');
  expect(root.textContent).toContain('Segunda aparición de la hora repetida.');
});
