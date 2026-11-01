import {afterEach, expect, test} from 'vitest';
import {DomusApp} from '../src/presentation/domus-app';
import type {EntryIntent} from '../src/presentation/domus-app';
import type {EntryView, EntryNotice} from '../src/application/entry-controller';
import type {CommandResult} from '../src/application/ports';
import {entryDecision} from '../src/domain/entry';
import type {MembershipState} from '../src/domain/entry';
import type {JournalRecord, RequestStage} from '../src/domain/journal';
import {message} from '../src/presentation/messages';

const owned: DomusApp[] = [];
afterEach(() => {for (const element of owned.splice(0)) element.remove();});
const context = {installationId: '01234567-89ab-cdef-0123-456789abcdef', channel: 'edge' as const, subject: 'a'.repeat(32)};
function view(state: MembershipState = 'unconfigured', extra: Partial<EntryView> = {}): EntryView {
  const session = {context, deployment: 'standalone' as const, access: 'full' as const,
    serverTime: 1_800_000_000_000, expiresAt: 1_800_001_000_000, householdApiAvailable: true};
  const authorization = {state, setupAllowed: state === 'unconfigured', enrollmentAllowed: state === 'not_enrolled',
    permissions: state === 'active' ? ['household.read'] : []};
  return {phase: 'ready', busy: false, session, authorization,
    decision: entryDecision('standalone', session, authorization, session.serverTime), household: null,
    journal: {version: 1, context, observedAt: session.serverTime, records: []},
    outcome: null, notice: null, fields: [], cleanup: null, ...extra};
}
async function mount(value: EntryView | null = null, locale: 'en' | 'es' = 'en', deployment: 'native' | 'standalone' = 'standalone') {
  const element = document.createElement('domus-app'); element.view = value; element.language = locale; element.deployment = deployment;
  const intents: EntryIntent[] = [];
  element.addEventListener('domus-intent', event => {
    const actual = event as CustomEvent<EntryIntent>;
    expect(actual.bubbles).toBe(true); expect(actual.composed).toBe(true);
    expect(Object.isFrozen(actual.detail)).toBe(true); intents.push(actual.detail);
  });
  document.body.append(element); owned.push(element); await element.updateComplete;
  const root = element.shadowRoot!;
  const text = () => root.querySelector('main')!.textContent!;
  const button = (label: string) => [...root.querySelectorAll('button')].find(item => item.textContent?.trim() === label)!;
  return {element, root, intents, text, button};
}
const receipt: CommandResult = {kind: 'receipt', stage: 'committed', archivedBy: null,
  operationId: 'op_original', createdAt: 1_800_000_000_000, result: {private: 'Never render this result blob'}};
function record(stage: RequestStage, action: 'setup' | 'enroll' = 'setup'): JournalRecord {
  return {key: 'original-key-not-for-display', action,
    payload: action === 'setup' ? {name: 'Private original draft', time_zone: 'UTC', expected_revision: 0,
      mapping_mode: 'all_ha_administrators'} : {expected_revision: 0},
    createdAt: 1_800_000_000_000, expiresAt: 1_800_003_600_000, stage,
    operationId: stage === 'committed' || stage === 'historical' ? 'op_original' : null} as JournalRecord;
}

test('the owned component starts with truthful read-only loading and no fabricated household', async () => {
  const f = await mount(); expect(f.element).toBeInstanceOf(DomusApp);
  expect(f.root.querySelector('h1')!.textContent).toBe('Checking your access');
  expect(f.text()).toContain('No household changes are requested');
  expect(f.root.querySelector('input')).toBeNull(); expect(f.intents).toEqual([]);
});
test.each(['idle', 'loading', 'sending'] as const)('%s has distinct loading presentation and no submit control', async phase => {
  const f = await mount(view('unconfigured', {phase, busy: phase === 'sending'}));
  expect(f.root.querySelector('h1')!.textContent).toBe('Checking your access');
  expect(f.root.querySelector('input')).toBeNull();
});
test.each(['unconfigured', 'not_enrolled', 'pending', 'active', 'suspended', 'archived'] as const)(
  '%s renders its actual state and emits no automatic command', async state => {
    const f = await mount(view(state));
    expect(f.root.querySelector('h1')!.textContent).toBe(message(`state_${state}`, 'en'));
    expect(f.intents).toEqual([]);
    if (state !== 'unconfigured') expect(f.root.querySelector('form')).toBeNull();
  });
test('a labeled setup form preserves exact draft values and emits only an explicit semantic intent', async () => {
  const f = await mount(view()); const name = f.root.querySelector<HTMLInputElement>('#name')!;
  const zone = f.root.querySelector<HTMLInputElement>('#time_zone')!;
  expect(f.root.querySelector('label[for="name"]')!.textContent).toBe('Household name');
  expect(name.getAttribute('aria-describedby')).toBe('name-help');
  name.value = '  Family 🏠  '; name.dispatchEvent(new InputEvent('input', {bubbles: true}));
  zone.value = 'Europe/Madrid'; zone.dispatchEvent(new InputEvent('input', {bubbles: true}));
  f.root.querySelector('form')!.requestSubmit();
  expect(f.intents).toEqual([{type: 'setup', name: '  Family 🏠  ', timeZone: 'Europe/Madrid'}]);
  f.element.view = view('unconfigured', {phase: 'loading'}); await f.element.updateComplete;
  f.element.view = view(); await f.element.updateComplete;
  expect(f.root.querySelector<HTMLInputElement>('#name')!.value).toBe('  Family 🏠  ');
  expect(f.root.querySelector<HTMLInputElement>('#time_zone')!.value).toBe('Europe/Madrid');
});
test('validation focuses the associated first error, without focusing a hidden form in another state', async () => {
  const f = await mount(view()); f.element.view = view('unconfigured', {fields: ['name', 'time_zone']});
  await f.element.updateComplete;
  expect(f.root.activeElement?.id).toBe('name');
  expect(f.root.querySelector('#name')!.getAttribute('aria-invalid')).toBe('true');
  expect(f.root.querySelector('#name')!.getAttribute('aria-describedby')).toBe('name-help name-error');
  expect(f.root.querySelector('#name-error')!.getAttribute('role')).toBe('alert');
  f.element.view = view('unconfigured', {fields: ['time_zone']}); await f.element.updateComplete;
  expect(f.root.activeElement?.id).toBe('time_zone');
  f.element.view = view('pending', {fields: ['name']}); await f.element.updateComplete;
  expect(f.root.querySelector('input')).toBeNull();
});
test('in-flight controls suppress clicks; unavailable journal blocks setup while retaining input', async () => {
  const f = await mount(view('unconfigured', {busy: true}));
  expect(f.root.querySelector<HTMLInputElement>('#name')!.disabled).toBe(true);
  f.button('Create household').click(); f.button('Refresh status').click(); expect(f.intents).toEqual([]);
  f.element.view = view('unconfigured', {journal: null, notice: 'journal_unavailable'}); await f.element.updateComplete;
  expect(f.root.querySelector<HTMLInputElement>('#name')!.disabled).toBe(false);
  expect(f.button('Create household').disabled).toBe(true);
  expect(f.text()).toContain('new changes are blocked');
});
test('joining, refresh, standalone sign-in and native reopen emit their closed intents', async () => {
  const join = await mount(view('not_enrolled')); join.button('Request membership').click(); join.button('Refresh status').click();
  expect(join.intents).toEqual([{type: 'request_membership'}, {type: 'refresh'}]);
  for (const deployment of ['native', 'standalone'] as const) {
    const decision = entryDecision(deployment, null, null, 0);
    const f = await mount(view('pending', {session: null, authorization: null, decision, journal: null}), 'en', deployment);
    f.button(deployment === 'native' ? 'Reopen Domus' : 'Sign in with Home Assistant').click();
    expect(f.intents).toEqual([{type: deployment === 'native' ? 'reopen' : 'sign_in'}]);
  }
});
test('closed views expose deployment-specific reentry even while a retired command remains busy', async () => {
  for (const deployment of ['native', 'standalone'] as const) {
    const f = await mount(view('active', {phase: 'closed', busy: true, session: null, decision: null,
      authorization: null, journal: null, notice: 'logout_unconfirmed', cleanup: 'unconfirmed'}), 'es', deployment);
    expect(f.root.querySelector('h1')!.textContent).toBe('Esta vista está cerrada');
    expect(f.text()).toContain('no tiene acceso activo');
    const button = f.button(deployment === 'native' ? 'Volver a abrir Domus' : 'Iniciar sesión con Home Assistant');
    expect(button.disabled).toBe(false); button.click();
    expect(f.intents.at(-1)?.type).toBe(deployment === 'native' ? 'reopen' : 'sign_in');
    expect(f.root.querySelector('.busy')).toBeNull();
  }
});
test('actual permitted household text is inert and technical details omit private context and journal', async () => {
  const f = await mount(view('active', {household: {householdId: 'private-id', name: '<img src=x onerror=alert(1)>',
    timeZone: 'UTC<script>bad()</script>', revision: 3}}));
  expect(f.root.querySelector('img,script')).toBeNull(); expect(f.text()).toContain('<img src=x onerror=alert(1)>');
  expect(f.text()).toContain('household.read'); expect(f.text()).not.toContain(context.installationId);
  expect(f.text()).not.toContain(context.subject); expect(f.text()).not.toContain('private-id');
});
test('grace shows the original UTC deadline, permits current facts and exposes no setup form', async () => {
  const actual = view('active'), session = {...actual.session!, access: 'read_only' as const};
  const decision = entryDecision('standalone', session, actual.authorization, session.serverTime);
  const f = await mount({...actual, session, decision, journal: null}, 'es');
  expect(f.text()).toContain('Acceso de solo lectura'); expect(f.text()).toContain('UTC');
  expect(f.text()).toContain('los cambios están bloqueados'); expect(f.root.querySelector('form')).toBeNull();
});
test('a denied setup mapping asks an administrator and invents no effective grant', async () => {
  const actual = view(), authorization = {...actual.authorization!, setupAllowed: false};
  const f = await mount({...actual, authorization, decision: entryDecision('standalone', actual.session, authorization, actual.session!.serverTime)});
  expect(f.root.querySelector('form')).toBeNull(); expect(f.text()).toContain('Ask a household administrator');
  expect(f.text()).toContain('No household administration permissions');
});
test('the stable channel uses an explicit badge while unavailable facts remain unavailable', async () => {
  const actual = view('active'); const session = {...actual.session!, context: {...context, channel: 'stable' as const}, householdApiAvailable: false};
  const f = await mount({...actual, session, authorization: null, journal: null,
    decision: entryDecision('standalone', session, null, session.serverTime)});
  expect(f.text()).toContain('Stable'); expect(f.root.querySelector('h1')!.textContent).toBe('Household status unavailable');
  expect(f.root.querySelector('form')).toBeNull();
});
test('joining is visibly blocked when owned recovery storage is unavailable, while refresh still works', async () => {
  const f = await mount(view('not_enrolled', {journal: null, notice: 'journal_unavailable'}));
  expect(f.button('Request membership').disabled).toBe(true); f.button('Request membership').click();
  f.button('Refresh status').click(); expect(f.intents).toEqual([{type: 'refresh'}]);
});
test('locale choice updates accessible language and labels without changing the business view', async () => {
  const actual = view(); const f = await mount(actual); const select = f.root.querySelector('select')!;
  select.value = 'es'; select.dispatchEvent(new Event('change', {bubbles: true})); await f.element.updateComplete;
  expect(f.element.lang).toBe('es'); expect(f.root.querySelector('h1')!.textContent).toBe('Configura tu hogar');
  expect(f.root.querySelector('#name')!.getAttribute('aria-describedby')).toBe('name-help');
  expect(f.intents).toEqual([{type: 'language', language: 'es'}]); expect(f.element.view).toBe(actual);
});
test.each((['en', 'es'] as const).flatMap(locale =>
  (['unconfigured', 'not_enrolled', 'pending', 'active', 'suspended', 'archived'] as const)
    .map(state => [locale, state] as const)))('%s technical status localizes %s without changing permissions', async (locale, state) => {
  const actual = view(state), f = await mount(actual, locale);
  expect(f.root.querySelector('details dt')!.textContent).toBe(message('status', locale));
  expect(f.root.querySelector('details dd')!.textContent).toBe(message(`state_${state}`, locale));
  expect(f.element.view).toBe(actual); expect(f.intents).toEqual([]);
});
test.each(['subject', 'installationId', 'channel'] as const)('a verified %s change clears both private drafts before rendering the next context', async field => {
  const f = await mount(view());
  const name = f.root.querySelector<HTMLInputElement>('#name')!, zone = f.root.querySelector<HTMLInputElement>('#time_zone')!;
  name.value = 'Private prior household'; name.dispatchEvent(new InputEvent('input', {bubbles: true}));
  zone.value = 'Europe/Madrid'; zone.dispatchEvent(new InputEvent('input', {bubbles: true}));
  const actual = view(); const next = {...context, [field]: field === 'channel' ? 'stable' : field === 'subject' ? 'b'.repeat(32) : '11234567-89ab-cdef-0123-456789abcdef'} as typeof context;
  f.element.view = {...actual, session: {...actual.session!, context: next}}; await f.element.updateComplete;
  expect(f.root.querySelector<HTMLInputElement>('#name')!.value).toBe('');
  expect(f.root.querySelector<HTMLInputElement>('#time_zone')!.value).toBe('');
  expect(f.text()).not.toContain('Private prior household');
});
test('closed presentation retires private drafts even if the same account later reopens this component', async () => {
  const f = await mount(view()); const input = f.root.querySelector<HTMLInputElement>('#name')!;
  input.value = 'Private draft'; input.dispatchEvent(new InputEvent('input', {bubbles: true}));
  f.element.view = view('unconfigured', {phase: 'closed', session: null, decision: null, journal: null});
  await f.element.updateComplete;
  expect(f.root.querySelector('h1')!.textContent).toBe('This view is closed');
  expect(f.root.querySelector('input')).toBeNull();
  f.element.view = view();
  await f.element.updateComplete;
  expect(f.root.querySelector<HTMLInputElement>('#name')!.value).toBe('');
});
test.each(['committed', 'historical', 'uncertain'] as const)('%s outcome explains retained effects without claiming current access', async stage => {
  const outcome: CommandResult = stage === 'uncertain' ? {kind: 'uncertain'} : {...receipt, stage, archivedBy: stage === 'historical' ? 'restore-1' : null};
  const f = await mount(view('pending', {outcome}));
  expect(f.text()).toContain(message(`outcome_${stage}`, 'en'));
  expect(f.text()).not.toContain('Never render this result blob');
  if (stage !== 'uncertain') expect(f.text()).toContain('op_original');
});
test.each(['authentication_required', 'forbidden', 'conflict', 'invalid_input', 'invalid_response', 'unavailable'] as const)(
  'rejected %s uses owned guidance and an optional safe support reference', async reason => {
    const f = await mount(view('pending', {outcome: {kind: 'rejected', reason, correlationId: reason === 'conflict' ? 'cor_safe' : null}}));
    expect(f.text()).toContain(message(`error_${reason}`, 'en'));
    expect(f.text().includes('cor_safe')).toBe(reason === 'conflict');
  });
test.each(['journal_unavailable','context_changed','action_not_allowed','previous_request_unresolved','request_unavailable',
  'request_changed','invalid_response','authentication_required','forbidden','unavailable','check_unconfirmed',
  'home_assistant_sign_out','signed_out','logout_unconfirmed'] satisfies EntryNotice[])(
  'notice %s is translated owned guidance', async notice => {
    const f = await mount(view('pending', {notice}), 'es'); expect(f.text()).toContain(message(`notice_${notice}`, 'es'));
  });
test.each(['prepared', 'uncertain', 'committed', 'historical', 'rejected'] as const)(
  '%s recovery shows only permitted local actions and never renders original payload/key', async stage => {
    const original = record(stage, stage === 'rejected' ? 'enroll' : 'setup');
    const actual = view('pending'); const f = await mount({...actual, journal: {...actual.journal!, records: [original]}});
    expect(f.text()).toContain(message(`stage_${stage}`, 'en'));
    expect(f.text()).not.toContain(original.key); expect(f.text()).not.toContain('Private original draft');
    if (stage !== 'rejected') {f.button('Check previous request').click(); expect(f.intents.at(-1)).toEqual({type: 'recover', key: original.key});}
    else expect(f.button('Check previous request')).toBeUndefined();
    if (stage !== 'prepared' && stage !== 'uncertain') {f.button('Remove resolved entry').click(); expect(f.intents.at(-1)).toEqual({type: 'dismiss', key: original.key});}
    else expect(f.button('Remove resolved entry')).toBeUndefined();
  });
test('native closing and standalone sign-out produce only the semantic logout intent', async () => {
  for (const deployment of ['native', 'standalone'] as const) {
    const f = await mount(view('active'), 'en', deployment); f.button(deployment === 'native' ? 'Close this view' : 'Sign out of Domus').click();
    expect(f.intents).toEqual([{type: 'logout'}]);
  }
});
test('a narrow real layout wraps long inert facts without horizontal main overflow in either locale', async () => {
  for (const locale of ['en', 'es'] as const) {
    const f = await mount(view('active', {household: {householdId: 'home', name: 'X'.repeat(160), timeZone: 'Europe/Madrid', revision: 1}}), locale);
    f.element.style.width = '360px'; await f.element.updateComplete;
    const main = f.root.querySelector('main')!;
    expect(main.getBoundingClientRect().width).toBe(360); expect(main.scrollWidth).toBeLessThanOrEqual(360);
  }
});
