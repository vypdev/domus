import {afterEach, expect, test, vi} from 'vitest';
import {EntryRuntime} from '../src/composition/entry-runtime';
import type {EntryBrowser} from '../src/composition/entry-runtime';
import type {EntryView} from '../src/application/entry-controller';
import {ENTRY_JOURNAL_KEY} from '../src/adapters/session-journal';
import corpus from './fixtures/entry-wire.json';

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(yes => {resolve = yes;}); return {promise, resolve};
}
const owned: EntryRuntime[] = [];
afterEach(() => {for (const runtime of owned.splice(0)) runtime.dispose();});
function fixture(deployment: 'native' | 'standalone' = 'standalone') {
  const wire = corpus[deployment], target = {...wire.endpoint, deployment};
  const values = new Map<string, string>(), views: EntryView[] = [], paths: string[] = [];
  const storage = {getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => {values.set(key, value);},
    removeItem: (key: string) => {values.delete(key);}};
  let elapsed = 0, phase = 'unconfigured', lost = false, effects = 0;
  const keys = new Set<string>();
  const pending: {tick: () => void; delay: number; cancel: ReturnType<typeof vi.fn>}[] = [];
  const transport = vi.fn(async (path: string, init: RequestInit) => {
    const route = path.slice(target.applicationBase.length + 'api/v1/'.length);
    let raw: string;
    if (route === 'session') raw = phase === 'eligible' || phase === 'pending' ? wire.participantSession : wire.session;
    else if (route === 'authorization') raw = phase === 'eligible' ? wire.eligible
      : phase === 'pending' ? wire.pending : phase === 'active' ? wire.active : wire.unconfigured;
    else if (route === 'auth/csrf') raw = JSON.stringify({csrf_token: 'c'.repeat(64)});
    else if (route === 'auth/logout') raw = JSON.stringify({state: 'logged_out', upstream_revoked: true,
      message: 'You are signed out of Domus.', action_required: 'Sign in to continue.'});
    else if (init.method === 'POST') {
      const key = new Headers(init.headers).get('Idempotency-Key')!;
      if (!keys.has(key)) {keys.add(key); effects++;}
      phase = route === 'household' ? 'active' : 'pending';
      raw = route === 'household' ? wire.setup : wire.enrollment;
      if (lost) {lost = false; throw new TypeError('simulated response loss after one effect');}
    } else raw = wire.household;
    return response(raw, path);
  });
  function response(raw: string, path: string) {
    const result = new Response(raw, {headers: {'Content-Type': 'application/json', 'Cache-Control': 'no-store'}});
    Object.defineProperty(result, 'url', {value: target.origin + path}); return result;
  }
  const browser: EntryBrowser = {transport, storage: () => storage, elapsed: () => elapsed,
    random: bytes => {bytes.fill(1); return bytes;}, navigate: path => {paths.push(path);},
    events: new EventTarget(), visibility: new EventTarget(),
    schedule: (tick, delay) => {const cancel = vi.fn(); pending.push({tick, delay, cancel}); return cancel;}};
  const runtime = new EntryRuntime(target, browser, view => {views.push(view);}); owned.push(runtime);
  return {runtime, browser, target, values, views, paths, transport, pending, response, wire,
    phase: (value: string) => {phase = value;}, elapsed: (value: number) => {elapsed = value;},
    lose: () => {lost = true;}, effects: () => effects};
}
async function settle() {for (let i = 0; i < 60; i++) await Promise.resolve();}

test('composition opens once, publishes loading/verified views and performs no business write', async () => {
  const f = fixture(); expect(f.runtime.view.phase).toBe('idle');
  const opening = f.runtime.start(); expect(f.views[0].phase).toBe('loading');
  await opening; await f.runtime.start();
  expect(f.transport.mock.calls.map(([path]) => path)).toEqual(['/api/v1/session', '/api/v1/authorization']);
  expect(f.runtime.view.decision?.action).toBe('create_household');
  expect(f.effects()).toBe(0); expect(f.pending.at(-1)?.delay).toBe(1000);
});
test('explicit setup composes actual HTTP guards, original journal, entropy and current-state refresh', async () => {
  const f = fixture(); await f.runtime.start(); await f.runtime.submitSetup('  Home  ', 'UTC');
  expect(f.effects()).toBe(1); expect(f.runtime.view.household?.name).toBe('Home 🏠');
  expect(f.runtime.view.outcome?.kind).toBe('receipt');
  const post = f.transport.mock.calls.find(([, init]) => init.method === 'POST')!;
  expect(new Headers(post[1].headers).get('Idempotency-Key')).toBe('req_' + '01'.repeat(16));
  expect(JSON.parse(post[1].body as string).name).toBe('Home');
  expect(JSON.parse(f.values.get(ENTRY_JOURNAL_KEY)!).records[0].stage).toBe('committed');
});
test('invalid drafts and an unrelated command never bypass current controller decisions', async () => {
  const f = fixture(); await f.runtime.start(); await f.runtime.submitSetup('', '');
  expect(f.runtime.view.fields).toEqual(['name', 'time_zone']);
  await f.runtime.requestMembership(); expect(f.effects()).toBe(0);
});
test('enrollment and explicit recovery retain one original command; resolved dismissal releases it', async () => {
  const f = fixture(); f.phase('eligible'); await f.runtime.start(); await f.runtime.requestMembership();
  expect(f.runtime.view.decision?.state).toBe('pending');
  const key = f.runtime.view.journal!.records[0].key;
  await f.runtime.recover(key); expect(f.effects()).toBe(1);
  await f.runtime.dismiss(key); expect(f.runtime.view.journal?.records).toEqual([]);
});
test('a lost POST reply remains uncertain until deliberate same-key recovery, without a duplicate effect', async () => {
  const f = fixture(); await f.runtime.start(); f.lose(); await f.runtime.submitSetup('Home', 'UTC');
  expect(f.runtime.view.outcome?.kind).toBe('uncertain'); expect(f.effects()).toBe(1);
  await f.runtime.refresh(); expect(f.effects()).toBe(1);
  await f.runtime.recover(f.runtime.view.journal!.records[0].key);
  expect(f.effects()).toBe(1); expect(f.runtime.view.outcome?.kind).toBe('receipt');
});
test('accepted navigation is deployment-specific and independent of mutable caller metadata', async () => {
  const f = fixture('native'); await f.runtime.start();
  expect(() => f.runtime.signIn()).toThrow('forbidden');
  const base = f.target.applicationBase; f.target.applicationBase = '/'; f.runtime.reopen();
  expect(f.paths).toEqual([base]);
  const standalone = fixture(); standalone.runtime.signIn(); standalone.runtime.reopen();
  expect(standalone.paths).toEqual(['/api/v1/auth/start', '/']);
});
test('session expiry is scheduled at its remaining millisecond deadline, with no renewal by a timer', async () => {
  const f = fixture(); await f.runtime.start();
  const time = JSON.parse(f.wire.session).context;
  f.elapsed(time.expires_at - time.server_time - 10);
  f.pending.at(-1)!.tick(); expect(f.pending.at(-1)?.delay).toBe(10);
  const calls = f.transport.mock.calls.length;
  f.elapsed(time.expires_at - time.server_time); f.pending.at(-1)!.tick();
  expect(f.runtime.view.decision?.state).toBe('authentication_required');
  expect(f.runtime.view.session).toBeNull(); expect(f.transport).toHaveBeenCalledTimes(calls);
});
test('visibility changes expire protected presentation immediately without an automatic API refresh', async () => {
  const f = fixture(); await f.runtime.start();
  f.elapsed(30_000_000); const count = f.transport.mock.calls.length;
  f.browser.visibility.dispatchEvent(new Event('visibilitychange'));
  expect(f.runtime.view.session).toBeNull(); expect(f.transport).toHaveBeenCalledTimes(count);
});
test('disposing is idempotent, hides personal data and fences even a canceled timer delivered late', async () => {
  const f = fixture(); await f.runtime.start(); const old = f.pending.at(-1)!;
  f.runtime.dispose(); const count = f.views.length; f.runtime.dispose(); old.tick();
  f.browser.visibility.dispatchEvent(new Event('visibilitychange'));
  f.browser.events.dispatchEvent(new PageTransitionEvent('pageshow', {persisted: true}));
  await f.runtime.start(); await f.runtime.refresh(); await f.runtime.submitSetup('Home', 'UTC');
  await f.runtime.requestMembership(); await f.runtime.recover('key'); await f.runtime.dismiss('key');
  await f.runtime.logout(); f.runtime.signIn(); f.runtime.reopen();
  expect(f.views).toHaveLength(count); expect(old.cancel).toHaveBeenCalledOnce();
  expect(f.runtime.view.phase).toBe('closed'); expect(f.paths).toEqual([]); expect(f.effects()).toBe(0);
});
test('ordinary page exit aborts the owned HTTP read and never leaves an active view', async () => {
  const f = fixture(); let aborted = false;
  f.transport.mockImplementation((_path, init) => new Promise((_resolve, reject) => {
    init.signal!.addEventListener('abort', () => {aborted = true; reject(new TypeError('aborted'));}, {once: true});
  }));
  const opening = f.runtime.start(); f.browser.events.dispatchEvent(new Event('pagehide')); await opening;
  expect(aborted).toBe(true); expect(f.runtime.view.phase).toBe('closed');
  const count = f.views.length; f.browser.events.dispatchEvent(new PageTransitionEvent('pageshow', {persisted: true}));
  expect(f.views).toHaveLength(count);
});
test('bfcache restoration obtains fresh proof and retains the original recovery record without sending it', async () => {
  const f = fixture(); await f.runtime.start(); f.lose(); await f.runtime.submitSetup('Home', 'UTC');
  const raw = f.values.get(ENTRY_JOURNAL_KEY);
  f.browser.events.dispatchEvent(new PageTransitionEvent('pagehide', {persisted: true}));
  expect(f.runtime.view.session).toBeNull(); expect(f.values.get(ENTRY_JOURNAL_KEY)).toBe(raw);
  f.runtime.signIn(); f.runtime.reopen(); expect(f.paths).toEqual([]);
  const count = f.transport.mock.calls.length;
  f.browser.events.dispatchEvent(new PageTransitionEvent('pageshow', {persisted: false})); await settle();
  expect(f.transport).toHaveBeenCalledTimes(count);
  f.browser.events.dispatchEvent(new PageTransitionEvent('pageshow', {persisted: true})); await settle();
  expect(f.runtime.view.decision?.state).toBe('active');
  expect(f.runtime.view.journal?.records[0].stage).toBe('uncertain'); expect(f.effects()).toBe(1);
  f.browser.events.dispatchEvent(new PageTransitionEvent('pageshow', {persisted: true})); await settle();
  expect(f.effects()).toBe(1); await f.runtime.recover(f.runtime.view.journal!.records[0].key); expect(f.effects()).toBe(1);
});
test('a late command result from before bfcache cannot replace the restored view', async () => {
  const f = fixture(); await f.runtime.start(); const waiting = deferred<Response>();
  const original = f.browser.transport;
  f.browser.transport = async (path, init) => init.method === 'POST' ? waiting.promise : original(path, init);
  // Recreate against the changed transport through the same supported lifecycle.
  f.browser.events.dispatchEvent(new PageTransitionEvent('pagehide', {persisted: true}));
  f.browser.events.dispatchEvent(new PageTransitionEvent('pageshow', {persisted: true})); await settle();
  const sending = f.runtime.submitSetup('Home', 'UTC'); await settle();
  expect(f.runtime.view.phase).toBe('sending');
  f.browser.events.dispatchEvent(new PageTransitionEvent('pagehide', {persisted: true}));
  f.browser.events.dispatchEvent(new PageTransitionEvent('pageshow', {persisted: true})); await settle();
  const before = f.runtime.view; waiting.resolve(f.response(f.wire.setup, '/api/v1/household')); await sending;
  expect(f.runtime.view).toEqual(before); expect(f.runtime.view.journal?.records[0].stage).toBe('prepared');
});
test('standalone logout hides access before revocation settles and cannot auto-resume', async () => {
  const f = fixture(); await f.runtime.start(); const waiting = deferred<Response>();
  const original = f.transport.getMockImplementation()!;
  f.transport.mockImplementation((path, init) => path.endsWith('/auth/logout') ? waiting.promise : original(path, init));
  const signingOut = f.runtime.logout(); await settle(); expect(f.runtime.view.phase).toBe('closed');
  f.browser.events.dispatchEvent(new PageTransitionEvent('pageshow', {persisted: true}));
  f.browser.visibility.dispatchEvent(new Event('visibilitychange'));
  waiting.resolve(f.response(JSON.stringify({state: 'logged_out', upstream_revoked: true,
    message: 'You are signed out of Domus.', action_required: 'Sign in to continue.'}), '/api/v1/auth/logout'));
  await signingOut; expect(f.runtime.view.notice).toBe('signed_out');
  f.runtime.signIn(); expect(f.paths).toEqual(['/api/v1/auth/start']);
});
test('a denied browser storage getter leaves reads usable and blocks all business mutations', async () => {
  const f = fixture(); f.browser.storage = () => {throw new Error('private provider failure');};
  await f.runtime.start(); expect(f.runtime.view.notice).toBe('journal_unavailable');
  await f.runtime.submitSetup('Home', 'UTC'); expect(f.effects()).toBe(0);
});
test('runtime composition can use actual isolated browser storage, crypto, performance and events', async () => {
  const f = fixture(); const unrelated = 'domus-runtime-unrelated';
  sessionStorage.setItem(unrelated, 'keep'); sessionStorage.removeItem(ENTRY_JOURNAL_KEY);
  f.browser.storage = () => sessionStorage; f.browser.random = bytes => crypto.getRandomValues(bytes);
  f.browser.elapsed = () => performance.now();
  try {
    await f.runtime.start(); await f.runtime.submitSetup('Home', 'UTC');
    expect(JSON.parse(sessionStorage.getItem(ENTRY_JOURNAL_KEY)!).records[0].key).toMatch(/^req_[a-f0-9]{32}$/u);
    await f.runtime.logout(); expect(sessionStorage.getItem(ENTRY_JOURNAL_KEY)).toBeNull();
    expect(sessionStorage.getItem(unrelated)).toBe('keep');
  } finally {sessionStorage.removeItem(ENTRY_JOURNAL_KEY); sessionStorage.removeItem(unrelated);}
});
test('loss of the elapsed capability between rendering and scheduling clears protected presentation', async () => {
  const f = fixture();
  f.browser.elapsed = () => {if (f.views.at(-1)?.phase === 'ready') throw new Error('private clock fault'); return 0;};
  await f.runtime.start(); expect(f.runtime.view.decision?.state).toBe('authentication_required');
  expect(f.runtime.view.session).toBeNull(); expect(f.effects()).toBe(0);
});
test('initial scheduler refusal closes the runtime with a bounded failure and releases listeners', async () => {
  const f = fixture(); f.browser.schedule = () => {throw new Error('private scheduling fault');};
  await expect(f.runtime.start()).rejects.toThrow('unavailable');
  expect(f.runtime.view.phase).toBe('closed'); const count = f.views.length;
  f.browser.visibility.dispatchEvent(new Event('visibilitychange'));
  f.browser.events.dispatchEvent(new PageTransitionEvent('pageshow', {persisted: true}));
  expect(f.views).toHaveLength(count);
});
test('scheduler refusal during bfcache restoration is handled without an unobserved rejected promise', async () => {
  const f = fixture(); await f.runtime.start();
  f.browser.events.dispatchEvent(new PageTransitionEvent('pagehide', {persisted: true}));
  f.browser.schedule = () => {throw new Error('restored scheduler unavailable');};
  f.browser.events.dispatchEvent(new PageTransitionEvent('pageshow', {persisted: true})); await settle();
  expect(f.runtime.view.phase).toBe('closed'); expect(f.effects()).toBe(0);
});
test('renderer and timer-cancellation failure cannot interrupt disposal or revive a retired callback', async () => {
  const f = fixture();
  const runtime = new EntryRuntime(f.target, f.browser, () => {throw new Error('private renderer failure');});
  owned.push(runtime); await runtime.start(); const prior = f.pending.at(-1)!;
  prior.cancel.mockImplementation(() => {throw new Error('private cancellation failure');});
  expect(() => runtime.dispose()).not.toThrow(); prior.tick();
  expect(runtime.view.phase).toBe('closed'); expect(f.effects()).toBe(0);
});
test('disposal during logout fences its late revocation result', async () => {
  const f = fixture(); await f.runtime.start(); const waiting = deferred<Response>();
  const original = f.transport.getMockImplementation()!;
  f.transport.mockImplementation((path, init) => path.endsWith('/auth/logout') ? waiting.promise : original(path, init));
  const signingOut = f.runtime.logout(); await settle(); f.runtime.dispose(); const count = f.views.length;
  waiting.resolve(f.response(JSON.stringify({state: 'logged_out', upstream_revoked: true,
    message: 'You are signed out of Domus.', action_required: 'Sign in to continue.'}), '/api/v1/auth/logout'));
  await signingOut; expect(f.views).toHaveLength(count); expect(f.runtime.view.notice).toBeNull();
});
