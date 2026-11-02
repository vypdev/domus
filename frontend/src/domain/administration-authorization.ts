/** Presentation availability uses current decoded grants; every backend operation still reauthorizes. */
import type {AdministrationAccess} from './administration-views';
import type {AdministrationCommand} from './administration-commands';

export function administrationAllowed(access: AdministrationAccess, command: AdministrationCommand): boolean {
  if (access.state !== 'active' || access.member === null) return false;
  const has = (permission: string) => access.permissions.includes(permission);
  switch (command.action) {
    case 'household.update': return has('household.manage');
    case 'member.update': return has('members.manage');
    case 'policy.update': return has('policy.manage');
    case 'member.presentation.update': return has('members.manage')
      || (command.memberId === access.member.memberId && has('preferences.write'));
    case 'member.preferences.update': return has('preferences.write');
  }
}
