import type {EntryOperation, EntryReceipt, HouseholdFacts, VerifiedEntrySession} from '../application/ports';
import {isMaterializationHorizonDays} from '../domain/administration';
import {setupPayload} from '../domain/entry';
import type {Authorization, Deployment} from '../domain/entry';
import type {JournalCommand, JournalContext} from '../domain/journal';
import {check, invalid, fields, identifier, text, integer, boolean, choice, responseRevision} from './json-values';
import type {Fields} from './json-values';
export {check, invalid, fields, identifier, wireJSON} from './json-values';

export interface EntryEndpoint {readonly origin: string; readonly deployment: Deployment; readonly applicationBase: string;}
export function endpoint(value: EntryEndpoint): EntryEndpoint {
  const item = fields(value, ['origin', 'deployment', 'applicationBase'], []);
  const origin = text(item.origin, 2048); let url: URL;
  try {url = new URL(origin);} catch {return invalid();}
  check(['http:', 'https:'].includes(url.protocol) && url.origin === origin);
  const deployment = choice(item.deployment, ['native', 'standalone']);
  const applicationBase = text(item.applicationBase, 300);
  check(deployment === 'standalone' ? applicationBase === '/'
    : /^\/api\/hassio_ingress\/[A-Za-z0-9_-]{16,256}\/$/u.test(applicationBase));
  return Object.freeze({origin, deployment, applicationBase});
}
export function assertion(value: JournalContext): string {
  const item = fields(value, ['installationId', 'channel', 'subject'], []);
  check(typeof item.installationId === 'string' && /^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$/u.test(item.installationId));
  choice(item.channel, ['stable', 'edge']);
  check(typeof item.subject === 'string' && /^[a-f0-9]{32}$/u.test(item.subject));
  return `v1:${item.installationId}:${item.channel}:${item.subject}`;
}

function guidance(item: Fields): void {text(item.message, 2048); text(item.action_required, 4096);}
export function session(value: unknown, target: EntryEndpoint): VerifiedEntrySession {
  const item = fields(value, ['state', 'ha_user_id', 'ha_administrator', 'access', 'expires_in',
    'message', 'action_required', 'context'], target.deployment === 'native' ? ['source'] : []);
  check(item.state === 'authenticated'); boolean(item.ha_administrator); guidance(item);
  if (target.deployment === 'native') check(item.source === 'home_assistant_ingress');
  const meta = fields(item.context, ['installation_id', 'channel', 'deployment', 'application_base',
    'household_api_available', 'server_time', 'expires_at'], []);
  check(meta.deployment === target.deployment && meta.application_base === target.applicationBase);
  const context: JournalContext = {installationId: meta.installation_id as string,
    channel: meta.channel as JournalContext['channel'], subject: item.ha_user_id as string}; assertion(context);
  const serverTime = integer(meta.server_time, 0), expiresAt = integer(meta.expires_at, 0);
  check(expiresAt - serverTime <= 28_800_000
    && integer(item.expires_in, 0) === Math.max(0, Math.floor((expiresAt - serverTime) / 1000)));
  return Object.freeze({context: Object.freeze(context), deployment: target.deployment,
    access: choice(item.access, ['full', 'read_only']), serverTime, expiresAt,
    householdApiAvailable: boolean(meta.household_api_available)});
}
const roles = ['administrator', 'adult', 'restricted', 'viewer'] as const;
const administration = ['household.read', 'household.manage', 'members.read', 'members.manage',
  'policy.manage', 'preferences.read', 'preferences.write', 'operations.read'] as const;
function member(value: unknown, state: string, expected: JournalContext): void {
  const item = fields(value, ['member_id', 'role', 'status', 'revision'], ['ha_user_id', 'exceptions']);
  identifier(item.member_id); choice(item.role, roles); responseRevision(item.revision); check(item.status === state);
  if (item.ha_user_id != null) check(item.ha_user_id === expected.subject);
  if (item.exceptions != null) {
    check(Array.isArray(item.exceptions) && item.exceptions.length <= 256);
    const seen = new Set<string>();
    for (const raw of item.exceptions) {
      const rule = fields(raw, ['permission', 'allow'], []), permission = text(rule.permission, 128);
      check(/^[a-z][a-z_]{0,31}\.[a-z][a-z_]{0,63}$/u.test(permission) && !seen.has(permission));
      boolean(rule.allow); seen.add(permission);
    }
  }
}
export function authorization(value: unknown, expected: JournalContext): Authorization {
  const item = fields(value, ['state', 'setup_allowed', 'enrollment_allowed', 'permission_scope',
    'permissions', 'message', 'action_required'], ['member', 'policy_revision', 'effective_role']);
  guidance(item); check(item.permission_scope === 'household_administration');
  const state = choice(item.state, ['unconfigured', 'not_enrolled', 'pending', 'active', 'suspended', 'archived']);
  const setupAllowed = boolean(item.setup_allowed), enrollmentAllowed = boolean(item.enrollment_allowed);
  check((!setupAllowed || state === 'unconfigured') && (!enrollmentAllowed || state === 'not_enrolled'));
  check(Array.isArray(item.permissions) && item.permissions.length <= administration.length);
  const permissions = item.permissions.map(value => choice(value, administration));
  check(new Set(permissions).size === permissions.length);
  if (state === 'unconfigured' || state === 'not_enrolled') check(item.member == null);
  else member(item.member, state, expected);
  if (state === 'active') {responseRevision(item.policy_revision); choice(item.effective_role, roles);}
  else check(permissions.length === 0 && item.policy_revision == null && item.effective_role == null);
  return Object.freeze({state, setupAllowed, enrollmentAllowed, permissions: Object.freeze(permissions)});
}
export function household(value: unknown): HouseholdFacts {
  const item = fields(value, ['household_id', 'name', 'time_zone', 'revision'], ['materialization_horizon_days']);
  const name = text(item.name, 160), timeZone = text(item.time_zone, 128);
  // Read compatibility preserves existing DEL/C1 values; new setup uses its stronger input policy.
  check(name.replace(/^\p{White_Space}+|\p{White_Space}+$/gu, '').length > 0 && !/[\u0000-\u001F]/u.test(name + timeZone));
  const home = {householdId: identifier(item.household_id), name, timeZone, revision: responseRevision(item.revision)};
  if (!Object.hasOwn(item, 'materialization_horizon_days')) return Object.freeze(home);
  const horizon = integer(item.materialization_horizon_days, 0);
  check(isMaterializationHorizonDays(horizon));
  return Object.freeze({...home, materializationHorizonDays: horizon});
}
export function command(value: JournalCommand & Readonly<{key: string}>): JournalCommand & Readonly<{key: string}> {
  const item = fields(value, ['action', 'payload', 'key'], []), key = identifier(item.key);
  if (item.action === 'setup') {
    const payload = fields(item.payload, ['name', 'time_zone', 'expected_revision', 'mapping_mode'], []);
    check(setupPayload(payload.name, payload.time_zone).ok && payload.expected_revision === 0
      && payload.mapping_mode === 'all_ha_administrators');
    return Object.freeze({action: 'setup', key, payload: Object.freeze({name: payload.name as string,
      time_zone: payload.time_zone as string, expected_revision: 0, mapping_mode: 'all_ha_administrators'})});
  }
  check(item.action === 'enroll'); const payload = fields(item.payload, ['expected_revision'], []);
  check(payload.expected_revision === 0); return Object.freeze({action: 'enroll', key,
    payload: Object.freeze({expected_revision: 0})});
}
export function receipt(value: unknown, action: JournalCommand['action'], operation: boolean): EntryReceipt | EntryOperation {
  const item = fields(value, ['state', 'archived_by', 'operation_id', 'created_at', 'result', 'message', 'action_required'], operation ? ['delivery'] : []);
  guidance(item); const stage = choice(item.state, ['committed', 'historical']);
  const archivedBy = item.archived_by === null ? null : identifier(item.archived_by);
  check(stage !== 'historical' || archivedBy !== null);
  let result: Fields;
  if (action === 'setup') {
    result = fields(item.result, ['state', 'household_id', 'revision', 'policy_revision', 'member_id',
      'administrator_member_id', 'mapping_mode'], []);
    check(result.state === 'configured' && result.mapping_mode === 'all_ha_administrators');
    identifier(result.household_id); identifier(result.administrator_member_id);
  } else {
    check(action === 'enroll'); result = fields(item.result, ['member_id', 'status', 'role', 'revision', 'policy_revision'], []);
    choice(result.status, ['pending', 'active']); check(result.role === 'viewer');
  }
  identifier(result.member_id); check(responseRevision(result.revision) === '1');
  const policyRevision = responseRevision(result.policy_revision);
  const decoded: EntryReceipt = Object.freeze({kind: 'receipt', stage, archivedBy,
    operationId: identifier(item.operation_id), createdAt: integer(item.created_at, 0),
    result: Object.freeze({...result, revision: '1', policy_revision: policyRevision}) as EntryReceipt['result']});
  if (!operation) return decoded;
  const delivery = choice(item.delivery, ['pending', 'delivered', 'suppressed']);
  check(stage === 'historical' ? delivery !== 'pending' : delivery !== 'suppressed');
  return Object.freeze({...decoded, delivery});
}
export function csrf(value: unknown): string {
  const item = fields(value, ['csrf_token'], []);
  check(typeof item.csrf_token === 'string' && /^[a-f0-9]{64}$/u.test(item.csrf_token)); return item.csrf_token;
}
export function failure(value: unknown): string {
  const item = fields(value, ['state', 'code', 'message', 'action_required', 'correlation_id'], []);
  check(item.state === 'blocked' && typeof item.code === 'string' && /^[a-z][a-z0-9_]{0,63}$/u.test(item.code));
  guidance(item); const correlation = identifier(item.correlation_id); check(correlation.startsWith('cor_')); return correlation;
}
export function logout(value: unknown): Readonly<{upstreamRevoked: boolean | null}> {
  const item = fields(value, ['state', 'upstream_revoked', 'message', 'action_required'], []);
  guidance(item); check(item.state === 'logged_out' && item.message === 'You are signed out of Domus.');
  return Object.freeze({upstreamRevoked: item.upstream_revoked === null ? null : boolean(item.upstream_revoked)});
}
