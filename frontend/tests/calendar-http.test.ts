import {expect, test, vi} from 'vitest';
import {HttpCalendarServer} from '../src/adapters/calendar-http';
import type {CalendarQuery} from '../src/domain/calendar';
import type {JournalContext} from '../src/domain/journal';

const context: JournalContext = {installationId: '01234567-89ab-cdef-0123-456789abcdef', channel: 'edge', subject: 'a'.repeat(32)};
const period = {start: '2026-11-01', end: '2026-12-01'};
const query: CalendarQuery = {...period, kind: '', timing: '', state: '', priority: '', category: '', own: false};
const planned = {entry_id: 'planned:work', kind: 'planned', timing: 'completion_relative', occurrence_id: 'work',
  title: '<b>Set clocks</b>', state: 'available', priority: 'normal', categories: ['Home'], category_id: 'house:1', member_ids: [],
  schedule_id: 'rule', slot_key: 'slot', local_date: '2026-11-01', local_time: null, instant_ms: null, time_zone: null,
  nominal_local: null, resolved_local: null, verification: null, relative_review_required: true};
const approval = {...planned, entry_id: 'approval:cycle', kind: 'approval', timing: 'manual', member_ids: ['member'],
  schedule_id: null, slot_key: null, local_time: '09:00:00', instant_ms: 1793523600000, time_zone: 'Europe/Madrid',
  nominal_local: '2026-11-01T08:00', resolved_local: '2026-11-01T09:00', verification: 'approved', relative_review_required: false};
const result = {period, categories: [{category_id:'house:1', label:'Home'}], time_zone: 'Europe/Madrid', entries: [planned, approval], count: 2, occurrence_count: 1, next_cursor: null, pending: false};

function fixture(deployment: 'native' | 'standalone', body: unknown) {
  const target = {deployment, applicationBase: deployment === 'native' ? '/api/hassio_ingress/' + 'b'.repeat(43) + '/' : '/',
    origin: 'https://domus.example'};
  const fetch = vi.fn(async (path: string, _init: RequestInit) => {
    const response = new Response(JSON.stringify(body), {headers: {'Content-Type': 'application/json', 'Cache-Control': 'no-store'}});
    Object.defineProperty(response, 'url', {value: target.origin + path}); return response;
  });
  return {target, fetch, server: new HttpCalendarServer(target, fetch)};
}

test.each(['native','standalone'] as const)('%s calendar uses the protected same-origin GET and retains date-only and approval distinctions', async mode => {
  const f = fixture(mode, result);
  const page = await f.server.read(context, 'member', query, null).result;
  expect(page).toEqual({categories: [{id:'house:1', label:'Home'}], entries: [
    {id: 'planned:work', kind: 'planned', title: '<b>Set clocks</b>', day: '2026-11-01', categoryLabel: 'Home', time: null, zone: null, nominal: null, resolved: null, verification: null, relativeReviewRequired: true},
    {id: 'approval:cycle', kind: 'approval', title: '<b>Set clocks</b>', day: '2026-11-01', categoryLabel: 'Home', time: '09:00:00', zone: 'Europe/Madrid',
      nominal: '2026-11-01T08:00', resolved: '2026-11-01T09:00', verification: 'approved', relativeReviewRequired: false}], count: 2, occurrenceCount: 1, cursor: null, pending: false});
  expect(Object.isFrozen(page.entries)).toBe(true);
  const [path, init] = f.fetch.mock.calls[0];
  expect(path).toBe(f.target.applicationBase + 'api/v1/tasks/calendar?start=2026-11-01&end=2026-12-01&limit=25');
  expect(init.method).toBe('GET'); expect(new Headers(init.headers).has('X-Domus-Context')).toBe(true);
});

test('every filter and opaque cursor is URL-encoded and additional reads require the original range', async () => {
  const f = fixture('standalone', {...result, pending: true, next_cursor: 'opaque/+?'});
  const filtered: CalendarQuery = {...query, kind: 'approval', timing: 'manual', state: 'completed', priority: 'high', category: 'house:1', own: true};
  expect(await f.server.read(context, 'member-1', filtered, 'source/+?').result).toMatchObject({cursor: 'opaque/+?', pending: true});
  const [path] = f.fetch.mock.calls[0];
  expect(Object.fromEntries(new URL(path, f.target.origin).searchParams)).toEqual({...period, limit: '25', kind: 'approval', timing: 'manual',
    state: 'completed', priority: 'high', category: 'house:1', member_id: 'member-1', cursor: 'source/+?'});
  await expect(f.server.read(context, 'member', {...query, end: query.start}, null).result).rejects.toThrow();
  expect(f.fetch).toHaveBeenCalledOnce();
});

test('malformed calendar pages cannot enter the component', async () => {
  for (const body of [{...result, period: {...period, start: period.end}}, {...result, period: {...period, end: period.start}},
    {...result, categories: {}}, {...result, categories: [{category_id:'house:1'}]},
    {...result, categories: [{category_id:'house:1', label:'Home'}, {category_id:'house:1', label:'Duplicate'}]},
    {...result, entries: null}, {...result, entries: Array(26).fill(planned)}, {...result, count: 1},
    {...result, occurrence_count: 0}, {...result, occurrence_count: 3},
    {...result, entries: [planned, planned]}, ...[
      {entry_id: 'approval:work'}, {category_id: null}, {categories: null}, {categories: Array(17).fill('x')}, {member_ids: null},
      {member_ids: Array(101).fill('member')}, {local_date: '2026-11-31'}, {verification: 'other'}, {relative_review_required: 'true'},
    ].map(delta => ({...result, entries: [{...planned, ...delta}]}))]) {
    await expect(fixture('standalone', body).server.read(context, 'member', query, null).result).rejects.toThrow();
  }
});

test('an empty range has zero entries and zero distinct tasks', async () => {
  const empty = {...result, categories: [], entries: [], count: 0, occurrence_count: 0};
  const resultPage = await fixture('standalone', empty).server.read(context, 'member', query, null).result;
  expect(resultPage).toEqual({categories: [], entries: [], count: 0, occurrenceCount: 0, cursor: null, pending: false});
  await expect(fixture('standalone', {...empty, occurrence_count: 1}).server.read(context, 'member', query, null).result).rejects.toThrow();
});

test('an unclassified entry has no captured category label', async () => {
  const uncategorized = {...planned, category_id:null, categories:[]};
  const f = fixture('standalone', {...result, entries:[uncategorized], categories:[]});
  expect((await f.server.read(context, 'member', query, null).result).entries[0].categoryLabel).toBeNull();
});
