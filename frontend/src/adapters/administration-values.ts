/** Strict projections of the actual administration wire; no source fact is an authorization rule. */
import {aliasValue, nextRevision} from '../domain/administration';
import {MEMBER_ROLES, MEMBER_STATUSES, MAPPING_MODES, ORDINARY_PERMISSIONS} from '../domain/administration-commands';
import type {AdministrationCommand, PermissionDecision, ProfileDecision} from '../domain/administration-commands';
import type {AdministrationAccess, AdministrationCapabilities, AdministrationMember, AdministrationPolicy, AdministrationReceipt,
  AdministrationResult, Directory, OwnPreferences, PublicPresentation, Roster} from '../domain/administration-views';
import type {AdministrationOriginal, AdministrationRequest} from '../application/administration-ports';
import type {JournalContext} from '../domain/journal';
import {authorization as entryAuthorization} from './http-values';
import {boolean, check, choice, fields, identifier, integer, invalid, responseRevision, text} from './json-values';

const actions = ['household.update', 'member.update', 'policy.update', 'member.presentation.update', 'member.preferences.update'] as const;
function userId(value: unknown): string {check(typeof value === 'string' && /^[a-f0-9]{32}$/u.test(value)); return value;}
function name(value: unknown): string | null {
  if (value === null) return null;
  const result = text(value, 256);
  check(result.replace(/^\p{White_Space}+|\p{White_Space}+$/gu, '').length > 0 && !/\p{Cc}/u.test(result)); return result;
}
function alias(value: unknown): string | null {
  try {const result = aliasValue(value); check(result === value); return result;} catch {return invalid();}
}
function decisions(value: unknown, profile: boolean): readonly (PermissionDecision | ProfileDecision)[] {
  check(Array.isArray(value) && value.length <= 256);
  const seen = new Set<string>();
  return Object.freeze(value.map(raw => {
    const item = fields(raw, profile ? ['role', 'permission', 'allow'] : ['permission', 'allow'], []);
    const permission = choice(item.permission, ORDINARY_PERMISSIONS), allow = boolean(item.allow);
    const role = profile ? choice(item.role, MEMBER_ROLES) : null, key = JSON.stringify([role, permission]);
    check(!seen.has(key)); seen.add(key);
    return Object.freeze(role === null ? {permission, allow} : {role, permission, allow});
  }));
}
export function member(value: unknown): AdministrationMember {
  const item = fields(value, ['member_id', 'role', 'status', 'revision'], ['ha_user_id', 'exceptions']);
  return Object.freeze({memberId: identifier(item.member_id), role: choice(item.role, MEMBER_ROLES), status: choice(item.status, MEMBER_STATUSES),
    revision: responseRevision(item.revision), haUserId: item.ha_user_id == null ? null : userId(item.ha_user_id),
    exceptions: item.exceptions == null ? null : decisions(item.exceptions, false)});
}
export function authorization(value: unknown, expected: JournalContext): AdministrationAccess {
  const basic = entryAuthorization(value, expected), item = value as Record<string, unknown>;
  return Object.freeze({...basic, member: item.member == null ? null : member(item.member),
    effectiveRole: basic.state === 'active' ? choice(item.effective_role, MEMBER_ROLES) : null,
    policyRevision: basic.state === 'active' ? responseRevision(item.policy_revision) : null});
}
export function capabilities(value: unknown): AdministrationCapabilities {
  const item = fields(value, ['state', 'contract_version', 'exact_revisions', 'actions', 'journal'], []);
  check(item.state === 'available' && integer(item.contract_version, 1) === 1 && item.exact_revisions === 'json-integer-int64');
  check(Array.isArray(item.actions) && item.actions.length === actions.length);
  const actual = item.actions.map(value => choice(value, actions)); check(new Set(actual).size === actions.length);
  const journal = fields(item.journal, ['namespace', 'version', 'maximum_records', 'maximum_bytes', 'lifetime_ms'], []);
  check(journal.namespace === 'administration' && integer(journal.version, 1) === 1
    && integer(journal.maximum_records, 1) === 8 && integer(journal.maximum_bytes, 1) === 65536 && integer(journal.lifetime_ms, 1) === 3600000);
  return Object.freeze({contractVersion: 1, actions: Object.freeze(actual)});
}
export function presentation(value: unknown): PublicPresentation {
  const item = fields(value, ['member_id', 'alias', 'revision'], []);
  return Object.freeze({memberId: identifier(item.member_id), alias: alias(item.alias), revision: responseRevision(item.revision)});
}
export function preferences(value: unknown): OwnPreferences {
  const item = fields(value, ['member_id', 'locale', 'routine_participation_summaries', 'revision', 'notification_delivery'], []);
  check(item.notification_delivery === 'unavailable');
  return Object.freeze({memberId: identifier(item.member_id), locale: item.locale === null ? null : choice(item.locale, ['en', 'es']),
    routine_participation_summaries: boolean(item.routine_participation_summaries), revision: responseRevision(item.revision), notificationDelivery: 'unavailable'});
}
export function roster(value: unknown): Roster {
  const item = fields(value, ['members', 'directory_state'], []);
  check(Array.isArray(item.members) && item.members.length <= 256);
  const members = item.members.map(raw => {
    const row = fields(raw, ['member', 'presentation', 'metadata'], []), person = member(row.member), display = presentation(row.presentation);
    check(person.memberId === display.memberId);
    const meta = fields(row.metadata, ['state', 'name', 'avatar_state'], []);
    const state = choice(meta.state, ['available', 'absent', 'denied', 'unavailable']);
    const label = name(meta.name); check((state === 'available') === (label !== null) && meta.avatar_state === 'unavailable');
    return Object.freeze({member: person, presentation: display, metadata: Object.freeze({state, name: label, avatarState: 'unavailable' as const})});
  });
  check(new Set(members.map(row => row.member.memberId)).size === members.length);
  const linked = members.map(row => row.member.haUserId).filter(id => id !== null); check(new Set(linked).size === linked.length);
  return Object.freeze({members: Object.freeze(members), directoryState: choice(item.directory_state, ['available', 'denied', 'unavailable'])});
}
export function directory(value: unknown): Directory {
  const item = fields(value, ['state', 'profiles'], []), state = choice(item.state, ['available', 'denied', 'unavailable']);
  check(Array.isArray(item.profiles) && item.profiles.length <= 256 && (state === 'available' || item.profiles.length === 0));
  const profiles = item.profiles.map(raw => {const row = fields(raw, ['ha_user_id', 'name'], []); return Object.freeze({haUserId: userId(row.ha_user_id), name: name(row.name)});});
  check(new Set(profiles.map(row => row.haUserId)).size === profiles.length);
  return Object.freeze({state, profiles: Object.freeze(profiles)});
}
export function policy(value: unknown): AdministrationPolicy {
  const item = fields(value, ['household_id', 'mapping', 'revision', 'adjustments'], []), mapping = fields(item.mapping, ['mode', 'target_ha_user_id'], []);
  const mode = choice(mapping.mode, MAPPING_MODES), target = mapping.target_ha_user_id === null ? null : userId(mapping.target_ha_user_id);
  check((mode === 'all_ha_administrators') === (target === null));
  return Object.freeze({householdId: identifier(item.household_id), revision: responseRevision(item.revision), mappingMode: mode,
    targetHAUserId: target, adjustments: decisions(item.adjustments, true) as readonly ProfileDecision[]});
}
function result(value: unknown, command: AdministrationCommand): AdministrationResult {
  let item: Record<string, unknown>;
  switch (command.action) {
    case 'household.update':
      item = fields(value, ['household_id', 'revision'], []);
      return Object.freeze({householdId: identifier(item.household_id), revision: responseRevision(item.revision)});
    case 'policy.update':
      item = fields(value, ['household_id', 'mapping_mode', 'revision'], []);
      check(item.mapping_mode === command.payload.mapping_mode);
      return Object.freeze({householdId: identifier(item.household_id), revision: responseRevision(item.revision), mappingMode: choice(item.mapping_mode, MAPPING_MODES)});
    case 'member.update':
      item = fields(value, ['member_id', 'role', 'status', 'revision'], []);
      check(item.member_id === command.memberId && item.role === command.payload.role && item.status === command.payload.status);
      return Object.freeze({memberId: identifier(item.member_id), role: choice(item.role, MEMBER_ROLES), status: choice(item.status, MEMBER_STATUSES), revision: responseRevision(item.revision)});
    case 'member.presentation.update': {
      item = fields(value, ['member_id', 'alias', 'revision'], []);
      const actual = presentation(item); check(actual.memberId === command.memberId && actual.alias === aliasValue(command.payload.alias)); return actual;
    }
    case 'member.preferences.update': {
      const actual = preferences(value);
      check(actual.locale === command.payload.locale && actual.routine_participation_summaries === command.payload.routine_participation_summaries); return actual;
    }
  }
}
export function receipt(value: unknown, input: AdministrationRequest | AdministrationOriginal, mode: 'mutation' | 'key' | 'operation'): AdministrationReceipt {
  const profile = input.command.action === 'member.presentation.update' || input.command.action === 'member.preferences.update';
  const notification = mode === 'key' || (mode === 'mutation' && profile);
  const item = fields(value, ['state', 'archived_by', 'operation_id', 'created_at', 'result', 'message', 'action_required',
    ...(notification ? ['notification_delivery'] : []), ...(mode === 'key' ? ['action', 'command_key', 'event_delivery'] : mode === 'operation' ? ['delivery'] : [])], []);
  text(item.message, 2048); text(item.action_required, 4096);
  const stage = choice(item.state, ['committed', 'historical']), archivedBy = item.archived_by === null ? null : identifier(item.archived_by);
  check(stage !== 'historical' || archivedBy !== null);
  if (notification) check(item.notification_delivery === 'unavailable');
  const operationId = identifier(item.operation_id), actual = result(item.result, input.command);
  try {check(actual.revision === nextRevision(input.command.payload.expected_revision));} catch {return invalid();}
  let delivery: 'pending' | 'delivered' | 'suppressed' | null = null;
  if (mode !== 'mutation') {
    if (mode === 'key') check(item.action === input.command.action && item.command_key === input.key);
    const known = (input as AdministrationOriginal).operationId; check(known === null || known === operationId);
    delivery = choice(mode === 'key' ? item.event_delivery : item.delivery, ['pending', 'delivered', 'suppressed'] as const);
    check(stage === 'historical' ? delivery !== 'pending' : delivery !== 'suppressed');
  }
  return Object.freeze({kind: 'receipt', stage, action: input.command.action, operationId, archivedBy, createdAt: integer(item.created_at, 0),
    result: actual, notificationDelivery: 'unavailable', eventDelivery: delivery});
}
