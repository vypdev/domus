/** Presentation decisions over decoded server facts; no client decision grants authority. */
export type Deployment = 'native' | 'standalone';
export type MembershipState = 'unconfigured' | 'not_enrolled' | 'pending' | 'active'
  | 'suspended' | 'archived';

export interface EntrySession {
  readonly access: 'full' | 'read_only';
  readonly serverTime: number;
  readonly expiresAt: number;
  readonly householdApiAvailable: boolean;
}

export interface Authorization {
  readonly state: MembershipState;
  readonly setupAllowed: boolean;
  readonly enrollmentAllowed: boolean;
  readonly permissions: readonly string[];
}

export type EntryAction = 'create_household' | 'request_membership' | 'refresh'
  | 'contact_administrator' | 'none' | 'sign_in' | 'reopen_home_assistant';

export interface EntryDecision {
  readonly state: MembershipState | 'authentication_required' | 'unavailable';
  readonly action: EntryAction;
  readonly readOnly: boolean;
  readonly householdReadable: boolean;
}

/** now is server-anchored time supplied by a semantic clock, never a new session lease. */
export function entryDecision(deployment: Deployment, session: EntrySession | null,
  authorization: Authorization | null, now: number): EntryDecision {
  if (session === null
      || ![now, session.serverTime, session.expiresAt]
        .every(value => Number.isSafeInteger(value) && value >= 0)
      || now < session.serverTime || now >= session.expiresAt) {
    return Object.freeze({state: 'authentication_required',
      action: deployment === 'native' ? 'reopen_home_assistant' : 'sign_in',
      readOnly: false, householdReadable: false});
  }
  const readOnly = session.access === 'read_only';
  if (!session.householdApiAvailable || authorization === null) {
    return Object.freeze({state: 'unavailable', action: 'refresh', readOnly,
      householdReadable: false});
  }
  const state = authorization.state;
  let action: EntryAction;
  switch (state) {
    case 'unconfigured':
      action = readOnly ? 'refresh'
        : authorization.setupAllowed ? 'create_household' : 'contact_administrator';
      break;
    case 'not_enrolled':
      action = readOnly ? 'refresh'
        : authorization.enrollmentAllowed ? 'request_membership' : 'contact_administrator';
      break;
    case 'pending': action = 'refresh'; break;
    case 'active': action = 'none'; break;
    case 'suspended':
    case 'archived': action = 'contact_administrator'; break;
  }
  return Object.freeze({state, action, readOnly,
    householdReadable: state === 'active' && authorization.permissions.includes('household.read')});
}

export interface SetupPayload {
  readonly name: string;
  readonly time_zone: string;
  readonly expected_revision: 0;
  readonly mapping_mode: 'all_ha_administrators';
}

export type SetupField = 'name' | 'time_zone';
export type SetupValidation = Readonly<{ok: true; payload: SetupPayload}>
  | Readonly<{ok: false; fields: readonly SetupField[]}>;

function validText(value: unknown, maximum: number): value is string {
  return typeof value === 'string' && value.trim().length > 0
    && Array.from(value).length <= maximum && !/[\p{Cc}\uD800-\uDFFF]/u.test(value);
}

/** Validate bounded input only; the server owns the timezone catalog and final authorization. */
export function setupPayload(name: unknown, timeZone: unknown): SetupValidation {
  const nameValid = validText(name, 160);
  const zoneValid = validText(timeZone, 128);
  if (!nameValid || !zoneValid) {
    const fields: SetupField[] = [];
    if (!nameValid) fields.push('name');
    if (!zoneValid) fields.push('time_zone');
    return Object.freeze({ok: false, fields: Object.freeze(fields)});
  }
  return Object.freeze({ok: true, payload: Object.freeze({name: name.trim(),
    time_zone: timeZone, expected_revision: 0, mapping_mode: 'all_ha_administrators'})});
}
