/** Closed original intents; validation never supplies a principal or a permission grant. */
import {AdministrationError, aliasValue, preferenceValues, revisionValue} from './administration';
import type {OwnPreferenceValues, Revision} from './administration';

const roles = ['administrator', 'adult', 'restricted', 'viewer'] as const;
export type MemberRole = typeof roles[number];
export type MemberStatus = 'pending' | 'active' | 'suspended' | 'archived';
export interface PermissionDecision {readonly permission: string; readonly allow: boolean;}
export interface ProfileDecision extends PermissionDecision {readonly role: MemberRole;}
export type AdministrationCommand =
  Readonly<{action: 'household.update'; payload: Readonly<{expected_revision: Revision; name: string; time_zone: string}>}>
  | Readonly<{action: 'member.update'; memberId: string; payload: Readonly<{expected_revision: Revision;
    role: MemberRole; status: MemberStatus; exceptions: readonly PermissionDecision[]}>}>
  | Readonly<{action: 'policy.update'; payload: Readonly<{expected_revision: Revision;
    mapping_mode: 'all_ha_administrators' | 'setup_administrator' | 'selected_ha_user';
    target_ha_user_id: string | null; adjustments: readonly ProfileDecision[]}>}>
  | Readonly<{action: 'member.presentation.update'; memberId: string; payload: Readonly<{expected_revision: Revision; alias: string | null}>}>
  | Readonly<{action: 'member.preferences.update'; payload: Readonly<{expected_revision: Revision} & OwnPreferenceValues>}>;

const ordinary = ['household.read', 'members.read', 'preferences.read', 'preferences.write',
  'operations.read', 'tasks.read', 'tasks.claim', 'tasks.manage', 'tasks.record_for_others',
  'tasks.material_use', 'tasks.create', 'tasks.complete', 'tasks.approve', 'shopping.request',
  'shopping.manage', 'inventory.manage'];
type Fields = Record<string, unknown>;
function requireValue(condition: unknown): asserts condition {
  if (!condition) throw new AdministrationError('invalid_command');
}
function fields(value: unknown, keys: readonly string[]): Fields {
  requireValue(typeof value === 'object' && value !== null && !Array.isArray(value));
  requireValue(Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key)));
  return value as Fields;
}
function choice<T extends string>(value: unknown, choices: readonly T[]): T {
  requireValue(typeof value === 'string' && choices.includes(value as T)); return value as T;
}
function identifier(value: unknown): string {
  requireValue(typeof value === 'string' && /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/u.test(value)); return value;
}
function text(value: unknown, maximum: number): string {
  requireValue(typeof value === 'string' && value.replace(/^\p{White_Space}+|\p{White_Space}+$/gu, '').length > 0
    && Array.from(value).length <= maximum && !/[\u0000-\u001F\uD800-\uDFFF]/u.test(value)); return value;
}
function decisions(value: unknown, profile: boolean): readonly (PermissionDecision | ProfileDecision)[] {
  requireValue(Array.isArray(value) && value.length <= 256);
  const seen = new Set<string>();
  return Object.freeze(value.map(raw => {
    const item = fields(raw, profile ? ['role', 'permission', 'allow'] : ['permission', 'allow']);
    const permission = choice(item.permission, ordinary);
    requireValue(typeof item.allow === 'boolean');
    const role = profile ? choice(item.role, roles) : null;
    const key = JSON.stringify([role, permission]);
    requireValue(!seen.has(key)); seen.add(key);
    return Object.freeze(role === null ? {permission, allow: item.allow} : {role, permission, allow: item.allow});
  }));
}
export function administrationCommand(value: unknown): AdministrationCommand {
  try {
    requireValue(typeof value === 'object' && value !== null && !Array.isArray(value));
    const action = (value as Fields).action;
    const targeted = action === 'member.update' || action === 'member.presentation.update';
    const item = fields(value, targeted ? ['action', 'memberId', 'payload'] : ['action', 'payload']);
    const memberId = targeted ? identifier(item.memberId) : null;
    let body: Fields;
    switch (action) {
      case 'household.update':
        body = fields(item.payload, ['expected_revision', 'name', 'time_zone']);
        return Object.freeze({action, payload: Object.freeze({expected_revision: revisionValue(body.expected_revision),
          name: text(body.name, 160), time_zone: text(body.time_zone, 128)})});
      case 'member.update':
        body = fields(item.payload, ['expected_revision', 'role', 'status', 'exceptions']);
        return Object.freeze({action, memberId: memberId as string, payload: Object.freeze({
          expected_revision: revisionValue(body.expected_revision), role: choice(body.role, roles),
          status: choice(body.status, ['pending', 'active', 'suspended', 'archived']),
          exceptions: decisions(body.exceptions, false)})});
      case 'policy.update': {
        body = fields(item.payload, ['expected_revision', 'mapping_mode', 'target_ha_user_id', 'adjustments']);
        const mapping_mode = choice(body.mapping_mode, ['all_ha_administrators', 'setup_administrator', 'selected_ha_user']);
        requireValue(mapping_mode === 'all_ha_administrators' ? body.target_ha_user_id === null
          : typeof body.target_ha_user_id === 'string' && /^[a-f0-9]{32}$/u.test(body.target_ha_user_id));
        return Object.freeze({action, payload: Object.freeze({expected_revision: revisionValue(body.expected_revision),
          mapping_mode, target_ha_user_id: body.target_ha_user_id as string | null,
          adjustments: decisions(body.adjustments, true) as readonly ProfileDecision[]})});
      }
      case 'member.presentation.update':
        body = fields(item.payload, ['expected_revision', 'alias']);
        aliasValue(body.alias); // Validate without substituting normalized text for the original request.
        return Object.freeze({action, memberId: memberId as string, payload: Object.freeze({
          expected_revision: revisionValue(body.expected_revision), alias: body.alias as string | null})});
      case 'member.preferences.update':
        body = fields(item.payload, ['expected_revision', 'locale', 'routine_participation_summaries']);
        return Object.freeze({action, payload: Object.freeze({expected_revision: revisionValue(body.expected_revision),
          ...preferenceValues(body.locale, body.routine_participation_summaries)})});
      default: throw new AdministrationError('invalid_command');
    }
  } catch {throw new AdministrationError('invalid_command');}
}
