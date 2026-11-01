import {afterEach, expect, test, vi} from 'vitest';
import {decodeIntent, mountEntry} from '../src/composition/entry-page';
import type {EntryPage} from '../src/composition/entry-page';
import type {DomusApp} from '../src/presentation/domus-app';
import {ENTRY_JOURNAL_KEY} from '../src/adapters/session-journal';
import corpus from './fixtures/entry-wire.json';

const dispose: (() => void)[] = [], nodes: Element[] = [];
afterEach(() => {
  for (const stop of dispose.splice(0)) stop();
  for (const node of nodes.splice(0)) node.remove();
  document.querySelector('#domus-entry-error')?.remove();
});
function fixture(deployment: 'native' | 'standalone' = 'standalone', locale = 'en') {
  const wire = corpus[deployment], values = new Map<string, string>(), navigation: string[] = [];
  const root = document.createElement('div'); root.id = 'domus-entry'; document.body.append(root); nodes.push(root);
  const data = document.createElement('script'); data.id = 'domus-bootstrap'; data.type = 'application/json';
  data.textContent = JSON.stringify({version: 1, deployment, application_base: wire.endpoint.applicationBase, style_nonce: 'a'.repeat(32)});
  document.head.append(data); nodes.push(data);
  let phase = 'unconfigured', postRequests = 0;
  const fetch = vi.fn(async (path: string, init: RequestInit) => {
    const route = path.slice(wire.endpoint.applicationBase.length + 'api/v1/'.length);
    let raw: string;
    if (route === 'session') raw = phase === 'eligible' || phase === 'pending' ? wire.participantSession : wire.session;
    else if (route === 'authorization') raw = phase === 'active' ? wire.active : phase === 'eligible' ? wire.eligible : phase === 'pending' ? wire.pending : wire.unconfigured;
    else if (route === 'auth/csrf') raw = JSON.stringify({csrf_token: 'c'.repeat(64)});
    else if (route === 'auth/logout') raw = JSON.stringify({state: 'logged_out', upstream_revoked: true,
      message: 'You are signed out of Domus.', action_required: 'Sign in to continue.'});
    else if (init.method === 'POST') {postRequests++; phase = route === 'household' ? 'active' : 'pending'; raw = route === 'household' ? wire.setup : wire.enrollment;}
    else raw = wire.household;
    const response = new Response(raw, {headers: {'Content-Type': 'application/json', 'Cache-Control': 'no-store'}});
    Object.defineProperty(response, 'url', {value: wire.endpoint.origin + path}); return response;
  });
  const events = new EventTarget();
  const page: EntryPage = {document, location: {href: wire.endpoint.origin + wire.endpoint.applicationBase,
    assign: url => {navigation.push(String(url));}, reload: vi.fn()}, navigator: {language: locale},
    crypto, performance, fetch, sessionStorage: {getItem: key => values.get(key) ?? null,
      setItem: (key, value) => {values.set(key, value);}, removeItem: key => {values.delete(key);}},
    addEventListener: events.addEventListener.bind(events), removeEventListener: events.removeEventListener.bind(events),
    dispatchEvent: events.dispatchEvent.bind(events), setTimeout: window.setTimeout.bind(window), clearTimeout: window.clearTimeout.bind(window)};
  const open = async () => {const mounted = mountEntry(page); dispose.push(mounted.dispose); await mounted.ready;
    const app = root.querySelector<DomusApp>('domus-app')!; await app?.updateComplete; return {mounted, app};};
  return {root, data, page, open, values, navigation, fetch, events, postRequests: () => postRequests,
    phase: (value: string) => {phase = value;}};
}
function intent(app: DomusApp, detail: unknown) {app.dispatchEvent(new CustomEvent('domus-intent', {detail, bubbles: true, composed: true}));}

test.each(['native','standalone'] as const)('%s page wires the owned view to actual controller/adapters without automatic mutation', async deployment => {
  const f = fixture(deployment, 'es-ES'), {app} = await f.open();
  expect(app.deployment).toBe(deployment); expect(app.language).toBe('es');
  expect(document.documentElement.lang).toBe('es'); expect(f.page.litNonce).toBe('a'.repeat(32));
  expect(app.view?.decision?.action).toBe('create_household'); expect(f.postRequests()).toBe(0);
  expect(f.fetch.mock.calls.every(([, init]) => init.method === 'GET')).toBe(true);
  intent(app, {type: 'setup', name: 'Maple House', timeZone: 'UTC'});
  await vi.waitFor(() => {expect(app.view?.household?.name).toBe('Home 🏠');});
  expect(f.postRequests()).toBe(1); expect(JSON.parse(f.values.get(ENTRY_JOURNAL_KEY)!).records[0].stage).toBe('committed');
});
test('deliberate enrollment, refresh, original-request recovery and dismissal route through the controller', async () => {
  const f = fixture(); f.phase('eligible'); const {app} = await f.open();
  intent(app, {type: 'request_membership'}); await vi.waitFor(() => {expect(app.view?.decision?.state).toBe('pending');});
  const key = app.view!.journal!.records[0].key;
  intent(app, {type: 'refresh'}); await vi.waitFor(() => {expect(app.view?.phase).toBe('ready');});
  intent(app, {type: 'recover', key}); await vi.waitFor(() => {expect(f.postRequests()).toBe(2);});
  await vi.waitFor(() => {expect(app.view?.busy).toBe(false);});
  intent(app, {type: 'dismiss', key}); await vi.waitFor(() => {expect(app.view?.journal?.records).toEqual([]);});
});
test('language is presentation-only, and navigation has only fixed reviewed destinations', async () => {
  const f = fixture(), {app} = await f.open(); const calls = f.fetch.mock.calls.length;
  intent(app, {type: 'language', language: 'es'}); expect(app.language).toBe('es'); expect(document.documentElement.lang).toBe('es');
  expect(f.fetch).toHaveBeenCalledTimes(calls); intent(app, {type: 'sign_in'}); intent(app, {type: 'reopen'});
  expect(f.navigation).toEqual(['/api/v1/auth/start','/']);
});
test('logout closes local access and keeps explicit deployment-specific reentry available', async () => {
  const f = fixture(), {app} = await f.open(); intent(app, {type: 'logout'});
  await vi.waitFor(() => {expect(app.view?.notice).toBe('signed_out');});
  expect(f.values.has(ENTRY_JOURNAL_KEY)).toBe(false); intent(app, {type: 'sign_in'});
  expect(f.navigation).toEqual(['/api/v1/auth/start']);
});
test('detaching the owned component retires reads, events and future commands', async () => {
  const f = fixture(), {app, mounted} = await f.open(); app.remove(); const calls = f.fetch.mock.calls.length;
  intent(app, {type: 'setup', name: 'Home', timeZone: 'UTC'}); await Promise.resolve(); mounted.dispose();
  expect(app.view?.phase).toBe('closed'); expect(f.fetch).toHaveBeenCalledTimes(calls);
});
test('only intents from the actual owned component are accepted', async () => {
  const f = fixture(), {app} = await f.open(), child = document.createElement('span'); app.append(child);
  child.dispatchEvent(new CustomEvent('domus-intent', {detail: {type: 'setup', name: 'Foreign', timeZone: 'UTC'}, bubbles: true}));
  app.dispatchEvent(new Event('domus-intent')); intent(app, {type: 'setup', name: 42, timeZone: 'UTC'});
  expect(f.postRequests()).toBe(0);
});
test.each(['missing-data','duplicate-data','wrong-type','bad-json','wrong-location','missing-root'] as const)(
  '%s yields an owned safe fallback without reading storage or sending API requests', async failure => {
    const f = fixture();
    if (failure === 'missing-data') f.data.remove();
    if (failure === 'duplicate-data') {const extra = f.data.cloneNode(true) as Element; document.head.append(extra); nodes.push(extra);}
    if (failure === 'wrong-type') f.data.type = 'text/javascript';
    if (failure === 'bad-json') f.data.textContent = 'Private raw malformed data';
    if (failure === 'wrong-location') f.page.location.href = 'https://domus.example/wrong';
    if (failure === 'missing-root') f.root.remove();
    const mounted = mountEntry(f.page); dispose.push(mounted.dispose); await mounted.ready;
    const error = document.querySelector('#domus-entry-error')!;
    expect(error.textContent).toContain('Household status unavailable'); expect(error.textContent).not.toContain('Private raw');
    expect(f.fetch).not.toHaveBeenCalled(); error.querySelector('button')!.click(); expect(f.page.location.reload).toHaveBeenCalledOnce();
  });
test('unavailable storage and navigation failures never get another endpoint or implicit command', async () => {
  const f = fixture(); Object.defineProperty(f.page, 'sessionStorage', {get: () => {throw new Error('Private provider');}});
  const {app} = await f.open(); expect(app.view?.notice).toBe('journal_unavailable');
  f.page.location.assign = () => {throw new Error('Private navigation error');}; intent(app, {type: 'sign_in'});
  await vi.waitFor(() => {expect(document.querySelector('#domus-entry-error')).not.toBeNull();}); expect(f.postRequests()).toBe(0);
});
test('initial scheduling refusal has an owned fallback and a refused reload stays explicitly disabled', async () => {
  const f = fixture(); f.page.setTimeout = () => {throw new Error('Private timer failure');};
  f.page.location.reload = () => {throw new Error('Private reload failure');};
  const mounted = mountEntry(f.page); dispose.push(mounted.dispose); await mounted.ready;
  const error = document.querySelector('#domus-entry-error')!, button = error.querySelector('button')!;
  button.click(); expect(button.disabled).toBe(true); expect(error.textContent).not.toContain('Private');
});
test('later scheduling refusal replaces closed controls with an actual reload fallback', async () => {
  const f = fixture(); let tick!: () => void;
  f.page.setTimeout = callback => {tick = callback; return 1;}; f.page.clearTimeout = () => {};
  const {app} = await f.open(); f.page.setTimeout = () => {throw new Error('Private later timer failure');};
  expect(() => tick()).not.toThrow(); expect(app.isConnected).toBe(false);
  document.querySelector<HTMLButtonElement>('#domus-entry-error button')!.click();
  expect(f.page.location.reload).toHaveBeenCalledOnce(); expect(f.postRequests()).toBe(0);
});
test('replacing a page mount retires the previous generation and does not let its disposer remove the new one', async () => {
  const f = fixture(), first = await f.open(), second = await f.open(); first.mounted.dispose();
  expect(first.app.view?.phase).toBe('closed'); intent(second.app, {type: 'language', language: 'es'});
  expect(second.app.language).toBe('es');
});
test('ordinary pagehide disposes the page; a persisted hide remains owned for fresh runtime restoration', async () => {
  const f = fixture(), {app} = await f.open(); f.events.dispatchEvent(new PageTransitionEvent('pagehide', {persisted: true}));
  f.events.dispatchEvent(new PageTransitionEvent('pageshow', {persisted: true}));
  await vi.waitFor(() => {expect(app.view?.decision?.action).toBe('create_household');});
  f.events.dispatchEvent(new Event('pagehide')); const calls = f.fetch.mock.calls.length;
  intent(app, {type: 'refresh'}); expect(f.fetch).toHaveBeenCalledTimes(calls);
});
test.each([null, [], {}, {type: 'other'}, {type: 'refresh', url: 'https://foreign.invalid'},
  {type: 'setup', name: 'Home', timeZone: 'UTC', ha_user_id: 'forged'},
  {type: 'setup', name: {}, timeZone: 'UTC'}, {type: 'setup', name: 'Home', timeZone: false},
  {type: 'recover', key: '../new'}, {type: 'dismiss', key: ''}, {type: 'language', language: 'fr'},
])('untrusted DOM intent %s is discarded as a closed value', value => {expect(decodeIntent(value)).toBeNull();});
test('the actual module entrypoint starts safely and refuses the test runner location as a product root', async () => {
  const f = fixture(); await import('../src/composition/main');
  expect(document.querySelector('#domus-entry-error')).not.toBeNull(); expect(f.fetch).not.toHaveBeenCalled();
  const mounted = mountEntry(f.page); dispose.push(mounted.dispose); await mounted.ready;
});
