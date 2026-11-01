"""Pure identity eligibility and household authority; no provider or credential state."""

from dataclasses import dataclass
from enum import StrEnum

from domus.domain.errors import Conflict, InvalidInput
from domus.domain.storage import validate_identifier


class Role(StrEnum):
    ADMINISTRATOR = "administrator"
    ADULT = "adult"
    RESTRICTED = "restricted"
    VIEWER = "viewer"


class MemberStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    ARCHIVED = "archived"


class MappingMode(StrEnum):
    ALL = "all_ha_administrators"
    SETUP = "setup_administrator"
    SELECTED = "selected_ha_user"


class Permission(StrEnum):
    HOUSEHOLD_READ = "household.read"
    HOUSEHOLD_MANAGE = "household.manage"
    MEMBERS_READ = "members.read"
    MEMBERS_MANAGE = "members.manage"
    POLICY_MANAGE = "policy.manage"
    PREFERENCES_READ = "preferences.read"
    PREFERENCES_WRITE = "preferences.write"
    OPERATIONS_READ = "operations.read"
    TASKS_READ = "tasks.read"
    TASKS_CLAIM = "tasks.claim"
    TASKS_MANAGE = "tasks.manage"
    TASKS_RECORD_FOR_OTHERS = "tasks.record_for_others"
    TASKS_MATERIAL_USE = "tasks.material_use"
    TASKS_CREATE = "tasks.create"
    TASKS_COMPLETE = "tasks.complete"
    TASKS_APPROVE = "tasks.approve"
    TASKS_CONFIGURE = "tasks.configure"
    SHOPPING_REQUEST = "shopping.request"
    SHOPPING_MANAGE = "shopping.manage"
    INVENTORY_MANAGE = "inventory.manage"
    AUTOMATIONS_CONFIGURE = "automations.configure"
    POINTS_MANAGE = "points.manage"


ADMINISTRATOR_ONLY = frozenset(
    {
        Permission.HOUSEHOLD_MANAGE,
        Permission.MEMBERS_MANAGE,
        Permission.POLICY_MANAGE,
        Permission.TASKS_CONFIGURE,
        Permission.AUTOMATIONS_CONFIGURE,
        Permission.POINTS_MANAGE,
    }
)
OWN_SCOPED = frozenset(
    {Permission.PREFERENCES_READ, Permission.PREFERENCES_WRITE, Permission.OPERATIONS_READ}
)
COMMON = (
    frozenset({Permission.HOUSEHOLD_READ, Permission.MEMBERS_READ, Permission.TASKS_READ})
    | OWN_SCOPED
)
RESTRICTED = COMMON | {
    Permission.TASKS_CLAIM,
    Permission.TASKS_MATERIAL_USE,
    Permission.TASKS_COMPLETE,
    Permission.SHOPPING_REQUEST,
}
ADULT = RESTRICTED | {
    Permission.TASKS_CREATE,
    Permission.TASKS_MANAGE,
    Permission.TASKS_RECORD_FOR_OTHERS,
    Permission.TASKS_APPROVE,
    Permission.SHOPPING_MANAGE,
    Permission.INVENTORY_MANAGE,
}
DEFAULTS = {
    Role.ADMINISTRATOR: frozenset(Permission),
    Role.ADULT: ADULT,
    Role.RESTRICTED: RESTRICTED,
    Role.VIEWER: COMMON,
}


def validate_revision(revision: int) -> None:
    if type(revision) is not int or not 1 <= revision <= 2**63 - 1:
        raise InvalidInput("invalid_revision")


@dataclass(frozen=True, slots=True)
class HumanIdentity:
    """An adapter-proven active human; construction cannot authenticate a request."""

    ha_user_id: str
    is_administrator: bool
    is_active: bool
    system_generated: bool

    def __post_init__(self) -> None:
        validate_identifier(self.ha_user_id)
        if (
            type(self.is_administrator) is not bool
            or self.is_active is not True
            or self.system_generated is not False
        ):
            raise InvalidInput("invalid_human_identity")


@dataclass(frozen=True, slots=True)
class AdministratorMapping:
    mode: MappingMode
    target_ha_user_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.mode, MappingMode) or (self.mode is MappingMode.ALL) != (
            self.target_ha_user_id is None
        ):
            raise InvalidInput("invalid_administrator_mapping")
        if self.target_ha_user_id is not None:
            validate_identifier(self.target_ha_user_id)

    def grants(self, human: HumanIdentity) -> bool:
        if self.mode is MappingMode.ALL:
            return human.is_administrator
        if self.target_ha_user_id != human.ha_user_id:
            return False
        return self.mode is MappingMode.SELECTED or human.is_administrator


@dataclass(frozen=True, slots=True)
class PermissionRule:
    permission: Permission
    allow: bool

    def __post_init__(self) -> None:
        if not isinstance(self.permission, Permission) or type(self.allow) is not bool:
            raise InvalidInput("invalid_permission_rule")
        if self.permission in ADMINISTRATOR_ONLY:
            raise InvalidInput("protected_permission")


@dataclass(frozen=True, slots=True)
class ProfileRule:
    role: Role
    permission: Permission
    allow: bool

    def __post_init__(self) -> None:
        if not isinstance(self.role, Role):
            raise InvalidInput("invalid_profile_rule")
        PermissionRule(self.permission, self.allow)


@dataclass(frozen=True, slots=True)
class Member:
    member_id: str
    household_id: str
    ha_user_id: str
    role: Role
    status: MemberStatus
    revision: int
    exceptions: tuple[PermissionRule, ...] = ()

    def __post_init__(self) -> None:
        for value in (self.member_id, self.household_id, self.ha_user_id):
            validate_identifier(value)
        validate_revision(self.revision)
        if not isinstance(self.role, Role) or not isinstance(self.status, MemberStatus):
            raise InvalidInput("invalid_member")
        if (
            type(self.exceptions) is not tuple
            or len(self.exceptions) > 256
            or any(not isinstance(rule, PermissionRule) for rule in self.exceptions)
            or len({rule.permission for rule in self.exceptions}) != len(self.exceptions)
        ):
            raise InvalidInput("invalid_permission_rules")


@dataclass(frozen=True, slots=True)
class HouseholdPolicy:
    household_id: str
    mapping: AdministratorMapping
    revision: int
    adjustments: tuple[ProfileRule, ...] = ()

    def __post_init__(self) -> None:
        validate_identifier(self.household_id)
        validate_revision(self.revision)
        if not isinstance(self.mapping, AdministratorMapping):
            raise InvalidInput("invalid_policy")
        if (
            type(self.adjustments) is not tuple
            or len(self.adjustments) > 256
            or any(not isinstance(rule, ProfileRule) for rule in self.adjustments)
            or len({(rule.role, rule.permission) for rule in self.adjustments})
            != len(self.adjustments)
        ):
            raise InvalidInput("invalid_profile_rules")


def effective_role(human: HumanIdentity, member: Member, policy: HouseholdPolicy) -> Role | None:
    if (
        member.ha_user_id != human.ha_user_id
        or member.household_id != policy.household_id
        or member.status is not MemberStatus.ACTIVE
    ):
        return None
    if policy.mapping.grants(human):
        return Role.ADMINISTRATOR
    return member.role


def allows(
    human: HumanIdentity,
    member: Member,
    policy: HouseholdPolicy,
    permission: Permission | str,
    household_id: str,
    *,
    subject_member_id: str | None = None,
    assigned_to: tuple[str, ...] = (),
) -> bool:
    role = effective_role(human, member, policy)
    if (
        role is None
        or household_id != policy.household_id
        or not isinstance(permission, Permission)
    ):
        return False
    if permission in ADMINISTRATOR_ONLY:
        return role is Role.ADMINISTRATOR
    if permission in OWN_SCOPED and subject_member_id != member.member_id:
        return False
    if permission is Permission.TASKS_APPROVE and role not in (Role.ADMINISTRATOR, Role.ADULT):
        return False
    if (
        permission is Permission.TASKS_COMPLETE
        and role is Role.RESTRICTED
        and member.member_id not in assigned_to
    ):
        return False
    for exception in member.exceptions:
        if exception.permission is permission:
            return exception.allow
    for adjustment in policy.adjustments:
        if adjustment.role is role and adjustment.permission is permission:
            return adjustment.allow
    return permission in DEFAULTS[role]


def ensure_administrator(
    policy: HouseholdPolicy, members: tuple[Member, ...], humans: tuple[HumanIdentity, ...]
) -> None:
    """Check a proposed local transition against supplied current identity facts.

    HA proof and a SQLite commit are separate systems. This pure check does not
    promise an atomic HA directory snapshot or prevent independent HA revocation.
    """
    by_user = {human.ha_user_id: human for human in humans}
    for member in members:
        human = by_user.get(member.ha_user_id)
        if human is not None and effective_role(human, member, policy) is Role.ADMINISTRATOR:
            return
    raise Conflict("last_administrator")


def recovery_allowed(human: HumanIdentity, policy: HouseholdPolicy) -> bool:
    return human.is_administrator and policy.mapping.mode in (
        MappingMode.SETUP,
        MappingMode.SELECTED,
    )
