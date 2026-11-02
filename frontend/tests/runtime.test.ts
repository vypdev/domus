import {afterEach, expect, test, vi} from 'vitest';
import {EntryRuntime} from '../src/composition/entry-runtime';
import type {EntryBrowser} from '../src/composition/entry-runtime';
import type {EntryView} from '../src/application/entry-controller';
import type {AdministrationView} from '../src/application/administration-controller';
import {ENTRY_JOURNAL_KEY} from '../src/adapters/session-journal';
import {ADMINISTRATION_JOURNAL_KEY} from '../src/adapters/administration-journal';
import corpus from './fixtures/entry-wire.json';

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(yes => {resolve = yes;}); return {promise, resolve};
}
const owned: EntryRuntime[] = [];
afterEach(() => {for (const runtime of owned.splice(0)) runtime.dispose();});
function fixture(deployment: 'native' | 'standalone' = 'standalone') {
  const wire = corpus[deployment], target = {...wire.endpoint, deployment};
  const values = new Map<string, string>(), views: EntryView[] = [], paths: string[] = [], administrationViews: (AdministrationView | null)[] = [];
  const storage = {getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => {values.set(key, value);},
    removeItem: (key: string) => {values.delete(key);}};
  let elapsed = 0, phase = 'unconfigured', lost = false, effects = 0, random = 0;
  const keys = new Set<string>();
  const member = JSON.parse(wire.active).member;
  let preferences = {member_id: member.member_id, revision: 1, locale: 'es', routine_participation_summaries: true, notification_delivery: 'unavailable'};
  const records = new Map<string, {state: string; archived_by: null; operation_id: string; created_at: number;
    result: typeof preferences; message: string; action_required: string; notification_delivery: string}>();
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
    else if (init.method === 'PUT') {
      if (route !== 'administration/preferences') throw new Error('Unexpected administration fixture mutation.');
      const key = new Headers(init.headers).get('Idempotency-Key')!;
      if (!keys.has(key)) {
        const body = JSON.parse(init.body as string); keys.add(key); effects++;
        preferences = {...preferences, revision: preferences.revision + 1, locale: body.locale,
          routine_participation_summaries: body.routine_participation_summaries};
        records.set(key, {state: 'committed', archived_by: null, operation_id: 'profile-' + effects,
          created_at: JSON.parse(wire.session).context.server_time + elapsed, result: {...preferences},
          message: 'Saved.', action_required: 'Review current state.', notification_delivery: 'unavailable'});
      }
      raw = JSON.stringify(records.get(key));
      if (lost) {lost = false; throw new TypeError('simulated response loss after one effect');}
    } else if (route === 'administration/capabilities') raw = JSON.stringify({state: 'available', contract_version: 2,
      household_id: 'home', exact_revisions: 'json-integer-int64', actions: ['household.update', 'member.update', 'policy.update',
        'member.presentation.update', 'member.preferences.update'], journal: {namespace: 'administration', version: 1,
        maximum_records: 8, maximum_bytes: 65536, lifetime_ms: 3600000}});
    else if (route === 'administration/roster') raw = JSON.stringify({directory_state: 'available', members: [{member,
      presentation: {member_id: member.member_id, alias: null, revision: 1},
      metadata: {state: 'available', name: 'Verified member', avatar_state: 'unavailable'}}]});
    else if (route === 'administration/directory') raw = JSON.stringify({state: 'denied', profiles: []});
    else if (route === 'policy') raw = JSON.stringify({household_id: 'home', revision: 1,
      mapping: {mode: 'all_ha_administrators', target_ha_user_id: null}, adjustments: []});
    else if (route === 'administration/preferences') raw = JSON.stringify(preferences);
    else if (route.startsWith('administration/requests/member.preferences.update/')) {
      const key = route.split('/').at(-1)!, record = records.get(key);
      if (record === undefined) throw new Error('Unknown original administration fixture request.');
      raw = JSON.stringify({...record, action: 'member.preferences.update', command_key: key, event_delivery: 'pending'});
    } else if (route.startsWith('operations/profile-')) {
      const record = [...records.values()].find(row => row.operation_id === route.slice('operations/'.length));
      if (record === undefined) throw new Error('Unknown administration fixture operation.');
      const {notification_delivery: _notification, ...result} = record;
      raw = JSON.stringify({...result, delivery: 'pending'});
    } else if (init.method === 'POST') {
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
    random: bytes => {bytes.fill(++random); return bytes;}, navigate: path => {paths.push(path);},
    events: new EventTarget(), visibility: new EventTarget(),
    schedule: (tick, delay) => {const cancel = vi.fn(); pending.push({tick, delay, cancel}); return cancel;}};
  const runtime = new EntryRuntime(target, browser, (view, administration) => {views.push(view); administrationViews.push(administration);}); owned.push(runtime);
  return {runtime, browser, target, values, views, paths, transport, pending, response, wire, administrationViews,
    phase: (value: string) => {phase = value;}, elapsed: (value: number) => {elapsed = value;},
    lose: () => {lost = true;}, effects: () => effects};
}
async function settle() {for (let i = 0; i < 200; i++) await Promise.resolve();}

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

test.each(['native', 'standalone'] as const)('logout during a command preserves the %s runtime and original recovery record', async deployment => {
  const f = fixture(deployment); await f.runtime.start();
  const original = f.transport.getMockImplementation()!, waiting = deferred<Response>();
  let intercepted = false;
  f.transport.mockImplementation(async (path, init) => {
    if (!intercepted && path.endsWith('/household') && init.method === 'POST') {
      intercepted = true; await original(path, init); return waiting.promise;
    }
    return original(path, init);
  });
  const command = f.runtime.submitSetup('Home', 'UTC'); await settle();
  expect(f.effects()).toBe(1); expect(f.runtime.view.phase).toBe('sending');
  const record = f.values.get(ENTRY_JOURNAL_KEY), timer = f.pending.at(-1)!;
  const cancellations = timer.cancel.mock.calls.length;
  await f.runtime.logout();
  expect(f.runtime.view.phase).toBe('sending'); expect(timer.cancel).toHaveBeenCalledTimes(cancellations);
  expect(f.values.get(ENTRY_JOURNAL_KEY)).toBe(record);
  waiting.resolve(new Response('Lost fictional reply', {status: 502})); await command;
  expect(f.runtime.view.outcome?.kind).toBe('uncertain');
  const key = f.runtime.view.journal!.records[0].key;
  await f.runtime.recover(key);
  expect(f.runtime.view.outcome?.kind).toBe('receipt'); expect(f.effects()).toBe(1);
  await f.runtime.logout(); expect(f.runtime.view.phase).toBe('closed');
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
test('a scheduler failure after opening is contained inside the owned timer callback', async () => {
  const f = fixture(); await f.runtime.start(); const timer = f.pending.at(-1)!;
  f.browser.schedule = () => {throw new Error('later scheduler unavailable');};
  expect(() => timer.tick()).not.toThrow(); expect(f.runtime.view.phase).toBe('closed');
});
test('a failing outer failure observer cannot restore access or expose provider details', async () => {
  const f = fixture(); const runtime = new EntryRuntime(f.target, f.browser, () => {}, () => {throw new Error('private observer error');});
  owned.push(runtime); f.browser.schedule = () => {throw new Error('private scheduler error');};
  await expect(runtime.start()).rejects.toThrow('unavailable'); expect(runtime.view.phase).toBe('closed');
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

const preferenceCommand = {action: 'member.preferences.update', payload: {expected_revision: '1', locale: 'en', routine_participation_summaries: false}};
test.each(['native', 'standalone'] as const)('household-browser-C01: %s document runtime composes real protected administration HTTP and its separate journal', async mode => {
  const f = fixture(mode); f.phase('active'); expect(f.runtime.administration).toBeNull();
  await f.runtime.start();
  expect(f.runtime.administration?.preferences).toMatchObject({memberId: 'identity-1', locale: 'es', revision: '1'});
  expect(f.runtime.administration?.roster?.members[0].metadata.name).toBe('Verified member');
  expect(f.administrationViews.at(-1)).toEqual(f.runtime.administration);
  expect(f.runtime.view.decision?.state).toBe('active'); expect(f.effects()).toBe(0);
  expect(f.values.has(ENTRY_JOURNAL_KEY)).toBe(true); expect(f.values.has(ADMINISTRATION_JOURNAL_KEY)).toBe(true);
  expect(f.transport.mock.calls.every(([path, init]) => path.startsWith(f.target.applicationBase + 'api/v1/') && init.method === 'GET')).toBe(true);
});
test('household-browser-C11/C12: runtime persists the immutable separate original before one guarded PUT and explicitly dismisses its result', async () => {
  const f = fixture(); await f.runtime.start(); await f.runtime.submitSetup('Home', 'UTC');
  const entry = f.values.get(ENTRY_JOURNAL_KEY), original = f.transport.getMockImplementation()!;
  f.transport.mockImplementation(async (path, init) => {
    if (init.method === 'PUT') expect(JSON.parse(f.values.get(ADMINISTRATION_JOURNAL_KEY)!).records[0]).toMatchObject({stage: 'prepared', payload: preferenceCommand.payload});
    return original(path, init);
  });
  await f.runtime.submitAdministration(preferenceCommand);
  const puts = f.transport.mock.calls.filter(([, init]) => init.method === 'PUT');
  expect(puts).toHaveLength(1); expect(new Headers(puts[0][1].headers).get('Idempotency-Key')).toBe('req_' + '02'.repeat(16));
  expect(new Headers(puts[0][1].headers).get('X-CSRF-Token')).toBe('c'.repeat(64));
  expect(f.runtime.administration?.outcome?.kind).toBe('receipt');
  expect(f.runtime.administration?.preferences).toMatchObject({locale: 'en', revision: '2'});
  const key = f.runtime.administration!.journal!.records[0].key;
  await f.runtime.dismissAdministration(key); expect(f.runtime.administration?.journal?.records).toEqual([]);
  expect(f.runtime.administration?.outcome).toBeNull(); expect(f.values.get(ENTRY_JOURNAL_KEY)).toBe(entry);
  expect(f.effects()).toBe(2);
});
test('household-browser-C09/C10: reload does not look up an uncertain original; explicit recovery uses protected GET without another mutation', async () => {
  const f = fixture(); f.phase('active'); await f.runtime.start(); f.lose(); await f.runtime.submitAdministration(preferenceCommand);
  expect(f.runtime.administration?.outcome?.kind).toBe('uncertain'); const key = f.runtime.administration!.journal!.records[0].key;
  await f.runtime.refresh(); expect(f.transport.mock.calls.some(([path]) => path.includes('/administration/requests/'))).toBe(false);
  await f.runtime.recoverAdministration(key); expect(f.runtime.administration?.outcome?.kind).toBe('receipt');
  expect(f.transport.mock.calls.filter(([path, init]) => path.endsWith('/administration/requests/member.preferences.update/' + key) && init.method === 'GET')).toHaveLength(1);
  await f.runtime.recoverAdministration(key);
  expect(f.transport.mock.calls.filter(([path, init]) => path.includes('/operations/profile-') && init.method === 'GET')).toHaveLength(1);
  expect(f.effects()).toBe(1); expect(f.transport.mock.calls.filter(([, init]) => init.method === 'PUT')).toHaveLength(1);
});
test('household-browser-C05: stale logout and duplicate intents preserve the in-flight runtime, timer and original', async () => {
  const f = fixture(); f.phase('active'); await f.runtime.start(); const original = f.transport.getMockImplementation()!, waiting = deferred<Response>();
  f.transport.mockImplementation(async (path, init) => path.endsWith('/auth/csrf') ? waiting.promise : original(path, init));
  const work = f.runtime.submitAdministration(preferenceCommand); await settle();
  expect(f.runtime.view.busy).toBe(true); expect(f.runtime.administration).toBeNull();
  const timer = f.pending.at(-1)!, cancellations = timer.cancel.mock.calls.length, raw = f.values.get(ADMINISTRATION_JOURNAL_KEY);
  await f.runtime.logout(); await f.runtime.submitAdministration(preferenceCommand); await f.runtime.recoverAdministration('missing');
  expect(timer.cancel).toHaveBeenCalledTimes(cancellations); expect(f.values.get(ADMINISTRATION_JOURNAL_KEY)).toBe(raw);
  expect(f.transport.mock.calls.some(([path]) => path.endsWith('/auth/logout'))).toBe(false);
  waiting.resolve(f.response(JSON.stringify({csrf_token: 'c'.repeat(64)}), '/api/v1/auth/csrf')); await work;
  expect(f.effects()).toBe(1); expect(f.runtime.administration?.outcome?.kind).toBe('receipt');
});
test.each(['native', 'standalone'] as const)('household-browser-C04: %s timer uses the earlier administration lease and never renews either proof', async mode => {
  const f = fixture(mode); f.phase('active'); const original = f.transport.getMockImplementation()!; let sessions = 0;
  f.transport.mockImplementation(async (path, init) => {
    if (path.endsWith('/session') && ++sessions === 2) {
      const raw = JSON.parse(f.wire.session); raw.context.expires_at = raw.context.server_time + 25; raw.expires_in = 0;
      return f.response(JSON.stringify(raw), path);
    }
    return original(path, init);
  });
  await f.runtime.start(); expect(f.runtime.administration?.preferences).not.toBeNull(); expect(f.pending.at(-1)?.delay).toBe(25);
  const reads = f.transport.mock.calls.length; f.elapsed(25); f.pending.at(-1)!.tick();
  expect(f.runtime.view.session).toBeNull(); expect(f.runtime.administration).toBeNull();
  expect(f.administrationViews.at(-1)).toBeNull(); expect(f.transport).toHaveBeenCalledTimes(reads);
});
test('household-browser-C06/C07: BFcache restores fresh administration proof and keeps a prepared original without automatic GET or PUT', async () => {
  const f = fixture(); f.phase('active'); await f.runtime.start(); const original = f.transport.getMockImplementation()!, waiting = deferred<Response>();
  let saved!: Response;
  f.transport.mockImplementation(async (path, init) => {const response = await original(path, init); if (init.method === 'PUT') {saved = response; return waiting.promise;} return response;});
  const work = f.runtime.submitAdministration(preferenceCommand); await settle(); expect(f.effects()).toBe(1);
  const raw = f.values.get(ADMINISTRATION_JOURNAL_KEY); f.browser.events.dispatchEvent(new PageTransitionEvent('pagehide', {persisted: true}));
  expect(f.runtime.administration).toBeNull(); expect(f.values.get(ADMINISTRATION_JOURNAL_KEY)).toBe(raw);
  f.browser.events.dispatchEvent(new PageTransitionEvent('pageshow', {persisted: true})); await settle();
  expect(f.runtime.administration?.preferences).toMatchObject({revision: '2', locale: 'en'});
  expect(f.runtime.administration?.journal?.records[0].stage).toBe('prepared');
  expect(f.transport.mock.calls.some(([path]) => path.includes('/administration/requests/'))).toBe(false);
  waiting.resolve(saved); await work; expect(f.runtime.administration?.outcome).toBeNull(); expect(f.effects()).toBe(1);
  await f.runtime.recoverAdministration(f.runtime.administration!.journal!.records[0].key);
  expect(f.runtime.administration?.outcome?.kind).toBe('receipt'); expect(f.effects()).toBe(1);
});
test('household-browser-C04/C10: read-only grace retains explicit original GET while blocking a new mutation', async () => {
  const f = fixture(); f.phase('active'); await f.runtime.start(); f.lose(); await f.runtime.submitAdministration(preferenceCommand);
  const key = f.runtime.administration!.journal!.records[0].key, original = f.transport.getMockImplementation()!;
  f.transport.mockImplementation(async (path, init) => path.endsWith('/session') ? f.response(JSON.stringify({...JSON.parse(f.wire.session), access: 'read_only'}), path) : original(path, init));
  await f.runtime.refresh(); expect(f.runtime.administration?.notice).toBe('read_only');
  await f.runtime.recoverAdministration(key); expect(f.runtime.administration?.outcome?.kind).toBe('receipt');
  await f.runtime.submitAdministration({...preferenceCommand, payload: {...preferenceCommand.payload, expected_revision: '2'}});
  expect(f.effects()).toBe(1); expect(f.transport.mock.calls.filter(([, init]) => init.method === 'PUT')).toHaveLength(1);
});
test('household-browser-C04: the administration journal expires at its original deadline while a longer lease remains valid', async () => {
  const f = fixture(); f.phase('active'); const original = f.transport.getMockImplementation()!;
  f.transport.mockImplementation(async (path, init) => {
    if (path.endsWith('/session')) {const raw = JSON.parse(f.wire.session); raw.context.expires_at += 3_600_000; raw.expires_in = 7200; return f.response(JSON.stringify(raw), path);}
    return original(path, init);
  });
  await f.runtime.start(); await f.runtime.submitAdministration(preferenceCommand);
  f.elapsed(3_599_990); f.pending.at(-1)!.tick(); expect(f.pending.at(-1)?.delay).toBe(10);
  const reads = f.transport.mock.calls.length; f.elapsed(3_600_000); f.pending.at(-1)!.tick();
  expect(f.runtime.view.session).not.toBeNull(); expect(f.runtime.administration?.journal?.records).toEqual([]);
  expect(f.runtime.administration?.outcome).toBeNull(); expect(f.transport).toHaveBeenCalledTimes(reads);
});
test('household-browser-C03: current permission loss removes private facts and prevents any new guarded PUT', async () => {
  const f = fixture(); f.phase('active'); await f.runtime.start(); const original = f.transport.getMockImplementation()!;
  f.transport.mockImplementation(async (path, init) => path.endsWith('/authorization')
    ? f.response(JSON.stringify({...JSON.parse(f.wire.active), permissions: ['household.read']}), path) : original(path, init));
  await f.runtime.refresh(); expect(f.runtime.administration?.preferences).toBeNull(); expect(f.runtime.administration?.roster).toBeNull();
  const reads = f.transport.mock.calls.length; await f.runtime.submitAdministration(preferenceCommand);
  expect(f.effects()).toBe(0); expect(f.runtime.administration?.notice).toBe('action_not_allowed');
  expect(f.transport.mock.calls.slice(reads).every(([, init]) => init.method === 'GET')).toBe(true);
});
test('household-browser-C12: failure of only the administration storage key preserves current reads and the separate entry record', async () => {
  const f = fixture(); await f.runtime.start(); await f.runtime.submitSetup('Home', 'UTC'); const entry = f.values.get(ENTRY_JOURNAL_KEY);
  const storage = f.browser.storage(); f.browser.storage = () => ({...storage,
    getItem: key => {if (key === ADMINISTRATION_JOURNAL_KEY) throw new Error('private-provider-detail'); return storage.getItem(key);}});
  await f.runtime.refresh(); expect(f.runtime.administration?.preferences?.locale).toBe('es');
  expect(f.runtime.administration?.notice).toBe('journal_unavailable'); await f.runtime.submitAdministration(preferenceCommand);
  expect(f.effects()).toBe(1); expect(f.values.get(ENTRY_JOURNAL_KEY)).toBe(entry);
  expect(JSON.stringify(f.runtime.administration)).not.toContain('private-provider-detail');
});
test('household-browser-C07: document exit cancels the actual owned administration GET and fences its late private payload', async () => {
  const f = fixture(); f.phase('active'); const original = f.transport.getMockImplementation()!; let canceled = false;
  f.transport.mockImplementation(async (path, init) => path.endsWith('/administration/preferences') ? new Promise<Response>((_resolve, reject) => {
    init.signal!.addEventListener('abort', () => {canceled = true; reject(new TypeError('retired private read'));}, {once: true});
  }) : original(path, init));
  const work = f.runtime.start(); await settle(); f.browser.events.dispatchEvent(new Event('pagehide')); await work;
  expect(canceled).toBe(true); expect(f.runtime.view.phase).toBe('closed'); expect(f.runtime.administration).toBeNull();
  expect(f.administrationViews.at(-1)).toBeNull(); expect(f.effects()).toBe(0);
});
test('household-browser-C07: a scheduling failure after administration opens closes both views and releases the old timer', async () => {
  const f = fixture(); f.phase('active'); await f.runtime.start(); const timer = f.pending.at(-1)!;
  f.browser.schedule = () => {throw new Error('private-scheduler-detail');};
  expect(() => timer.tick()).not.toThrow(); expect(f.runtime.view.phase).toBe('closed');
  expect(f.runtime.administration).toBeNull(); expect(f.administrationViews.at(-1)).toBeNull();
});
test('household-browser-C04: a late atomic PUT cannot renew an expired document lease or publish its private result', async () => {
  const f = fixture(); f.phase('active'); await f.runtime.start(); const original = f.transport.getMockImplementation()!, waiting = deferred<Response>();
  let response!: Response;
  f.transport.mockImplementation(async (path, init) => {const reply = await original(path, init); if (init.method === 'PUT') {response = reply; return waiting.promise;} return reply;});
  const work = f.runtime.submitAdministration(preferenceCommand); await settle(); expect(f.effects()).toBe(1);
  const raw = f.values.get(ADMINISTRATION_JOURNAL_KEY), reads = f.transport.mock.calls.length;
  f.elapsed(3_600_000); f.pending.at(-1)!.tick(); waiting.resolve(response); await work;
  expect(f.runtime.view.decision?.state).toBe('authentication_required'); expect(f.runtime.administration).toBeNull();
  expect(f.values.get(ADMINISTRATION_JOURNAL_KEY)).toBe(raw); expect(f.transport).toHaveBeenCalledTimes(reads);
});
