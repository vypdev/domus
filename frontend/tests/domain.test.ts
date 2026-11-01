import {describe, expect, test} from 'vitest';
import {entryDecision, setupPayload} from '../src/domain/entry';
import type {Authorization, EntrySession} from '../src/domain/entry';

const session: EntrySession = {access: 'full', serverTime: 1000, expiresAt: 2000,
  householdApiAvailable: true};
const access: Authorization = {state: 'unconfigured', setupAllowed: true,
  enrollmentAllowed: false, permissions: []};

describe('household-entry-interface-C01/C08: decisions use actual server facts', () => {
  test.each([
    ['unconfigured', 'create_household'], ['not_enrolled', 'contact_administrator'],
    ['pending', 'refresh'], ['active', 'none'], ['suspended', 'contact_administrator'],
    ['archived', 'contact_administrator'],
  ] as const)('%s selects %s without a role-derived grant', (state, action) => {
    const result = entryDecision('native', session, {...access, state}, 1000);
    expect(result).toEqual({state, action, readOnly: false, householdReadable: false});
    expect(Object.isFrozen(result)).toBe(true);
  });

  test('setup and enrollment require their actual server flags', () => {
    expect(entryDecision('native', session, {...access, setupAllowed: false}, 1000).action)
      .toBe('contact_administrator');
    expect(entryDecision('native', session, {...access, state: 'not_enrolled',
      enrollmentAllowed: true}, 1000).action).toBe('request_membership');
  });

  test('a household is readable only with an active membership and actual grant', () => {
    const permitted = {...access, permissions: ['household.read']};
    expect(entryDecision('native', session, {...permitted, state: 'active'}, 1000)
      .householdReadable).toBe(true);
    expect(entryDecision('native', session, permitted, 1000).householdReadable).toBe(false);
    expect(entryDecision('native', session, {...permitted, state: 'pending'}, 1000)
      .householdReadable).toBe(false);
  });

  test.each(['native', 'standalone'] as const)('%s unavailable data stays unavailable', deployment => {
    expect(entryDecision(deployment, session, null, 1000)).toEqual({
      state: 'unavailable', action: 'refresh', readOnly: false, householdReadable: false,
    });
    expect(entryDecision(deployment, {...session, householdApiAvailable: false}, access, 1000)
      .state).toBe('unavailable');
  });

  test.each(['native', 'standalone'] as const)('%s missing identity follows its existing auth', deployment => {
    const action = deployment === 'native' ? 'reopen_home_assistant' : 'sign_in';
    expect(entryDecision(deployment, null, access, 1000)).toEqual({
      state: 'authentication_required', action, readOnly: false, householdReadable: false,
    });
  });

  test.each([2000, 2001, 999, NaN, Infinity, -1, 1000.5])(
    'an expired or inconsistent clock (%s) grants no local access', now => {
      expect(entryDecision('standalone', session, access, now).state)
        .toBe('authentication_required');
    },
  );

  test('read-only grace retains actual membership meaning and disables both mutations', () => {
    const grace = {...session, access: 'read_only' as const};
    for (const state of ['unconfigured', 'not_enrolled'] as const) {
      expect(entryDecision('native', grace, {...access, state, enrollmentAllowed: true}, 1000))
        .toEqual({state, action: 'refresh', readOnly: true, householdReadable: false});
    }
    expect(entryDecision('native', grace, {...access, state: 'pending'}, 1000).state).toBe('pending');
    expect(entryDecision('native', grace, {...access, state: 'active',
      permissions: ['household.read']}, 1999)).toEqual({state: 'active', action: 'none',
      readOnly: true, householdReadable: true});
    expect(entryDecision('native', grace, null, 1000).readOnly).toBe(true);
  });
});

describe('household-entry-interface-C03/C04: default setup payload and validation', () => {
  test('title/timezone-only input selects the explicit default mapping without an actor', () => {
    const result = setupPayload('  Example household  ', 'Europe/Madrid');
    expect(result).toEqual({ok: true, payload: {name: 'Example household',
      time_zone: 'Europe/Madrid', expected_revision: 0, mapping_mode: 'all_ha_administrators'}});
    expect(Object.isFrozen(result)).toBe(true);
    if (result.ok) expect(Object.isFrozen(result.payload)).toBe(true);
  });

  test.each([undefined, null, 12, '', '   ', 'x'.repeat(161), '\u0000bad', '\uD800', '\uDC00'])(
    'invalid name %j is associated with its field', name => {
      expect(setupPayload(name, 'UTC')).toEqual({ok: false, fields: ['name']});
    },
  );

  test.each([undefined, null, 12, '', '   ', 'x'.repeat(129), 'Bad\nZone', '\uD800'])(
    'invalid timezone %j is associated with its field', zone => {
      expect(setupPayload('Home', zone)).toEqual({ok: false, fields: ['time_zone']});
    },
  );

  test('both invalid fields are reported without replacing the original draft', () => {
    const draft = {name: '\n', time_zone: ''};
    const result = setupPayload(draft.name, draft.time_zone);
    expect(result).toEqual({ok: false, fields: ['name', 'time_zone']});
    expect(draft).toEqual({name: '\n', time_zone: ''});
    expect(Object.isFrozen(result)).toBe(true);
    if (!result.ok) expect(Object.isFrozen(result.fields)).toBe(true);
  });

  test('Unicode limits count code points, while timezone catalog validation remains server-owned', () => {
    expect(setupPayload('🏠'.repeat(160), 'x'.repeat(128)).ok).toBe(true);
    expect(setupPayload('🏠'.repeat(161), 'UTC').ok).toBe(false);
    expect(setupPayload('Home', 'Catalog/Unknown').ok).toBe(true);
  });
});
