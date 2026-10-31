"""Local reads use a server-proven human and reread current policy before every disclosure."""

from dataclasses import dataclass
from typing import Literal, cast

from domus.application.authorization import HouseholdAccess
from domus.application.ports import Transactions, UnitOfWork
from domus.domain.errors import Conflict, Forbidden, NotFound, StorageFailure
from domus.domain.identity import (
    HouseholdPolicy,
    HumanIdentity,
    Member,
    MemberStatus,
    Permission,
    PermissionRule,
    Role,
    allows,
    effective_role,
)
from domus.domain.storage import Household, Receipt, validate_identifier

_ADMINISTRATION_SCOPE = (
    Permission.HOUSEHOLD_READ,
    Permission.HOUSEHOLD_MANAGE,
    Permission.MEMBERS_READ,
    Permission.MEMBERS_MANAGE,
    Permission.POLICY_MANAGE,
    Permission.PREFERENCES_READ,
    Permission.PREFERENCES_WRITE,
    Permission.OPERATIONS_READ,
)
_ORIGINAL_PERMISSION = {
    "household.setup": Permission.HOUSEHOLD_MANAGE,
    "household.update": Permission.HOUSEHOLD_MANAGE,
    "member.update": Permission.MEMBERS_MANAGE,
    "policy.update": Permission.POLICY_MANAGE,
}


@dataclass(frozen=True, slots=True)
class MemberView:
    member_id: str
    role: Role
    status: MemberStatus
    revision: int
    ha_user_id: str | None
    exceptions: tuple[PermissionRule, ...] | None


type AccessState = Literal[
    "unconfigured", "not_enrolled", "pending", "active", "suspended", "archived"
]


@dataclass(frozen=True, slots=True)
class AccessView:
    state: AccessState
    setup_allowed: bool = False
    enrollment_allowed: bool = False
    member: MemberView | None = None
    policy_revision: int | None = None
    effective_role: Role | None = None
    permission_scope: Literal["household_administration"] = "household_administration"
    permissions: tuple[Permission, ...] = ()


@dataclass(frozen=True, slots=True)
class OperationView:
    receipt: Receipt
    delivered: bool


@dataclass(frozen=True, slots=True)
class HouseholdQueries:
    """The composition supplies human proof or a valid outage lease, never an HTTP actor ID."""

    transactions: Transactions
    human: HumanIdentity
    household_id: str = "home"

    def __post_init__(self) -> None:
        validate_identifier(self.household_id)

    def _view(self, member: Member, *, privileged: bool = False) -> MemberView:
        private = privileged or member.ha_user_id == self.human.ha_user_id
        return MemberView(
            member.member_id,
            member.role,
            member.status,
            member.revision,
            member.ha_user_id if private else None,
            member.exceptions if private else None,
        )

    def _require(self, unit: UnitOfWork, permission: Permission) -> Member:
        return HouseholdAccess(self.human).require(unit, self.household_id, permission)

    def access(self) -> AccessView:
        with self.transactions.read() as unit:
            home = unit.households.current()
            if home is None:
                return AccessView("unconfigured", setup_allowed=self.human.is_administrator)
            if home.household_id != self.household_id:
                raise Forbidden("permission_denied")
            policy = unit.policies.get(self.household_id)
            if policy is None:
                raise Conflict("household_configuration_required")
            member = unit.members.by_user(self.household_id, self.human.ha_user_id)
            if member is None:
                return AccessView("not_enrolled", enrollment_allowed=True)
            view = self._view(member)
            if member.status is not MemberStatus.ACTIVE:
                return AccessView(cast(AccessState, member.status.value), member=view)
            permissions = tuple(
                permission
                for permission in _ADMINISTRATION_SCOPE
                if allows(
                    self.human,
                    member,
                    policy,
                    permission,
                    self.household_id,
                    subject_member_id=member.member_id,
                )
            )
            return AccessView(
                "active",
                member=view,
                policy_revision=policy.revision,
                effective_role=effective_role(self.human, member, policy),
                permissions=permissions,
            )

    def household(self) -> Household:
        with self.transactions.read() as unit:
            self._require(unit, Permission.HOUSEHOLD_READ)
            home = unit.households.get(self.household_id)
            if home is None:
                raise StorageFailure("invalid_identity_record")
            return home

    def members(self) -> tuple[MemberView, ...]:
        with self.transactions.read() as unit:
            actor = self._require(unit, Permission.MEMBERS_READ)
            policy = cast(HouseholdPolicy, unit.policies.get(self.household_id))
            privileged = allows(
                self.human, actor, policy, Permission.MEMBERS_MANAGE, self.household_id
            )
            members = unit.members.list(self.household_id)
            if len(members) > 256:
                raise StorageFailure("invalid_identity_record")
            return tuple(self._view(member, privileged=privileged) for member in members)

    def policy(self) -> HouseholdPolicy:
        with self.transactions.read() as unit:
            self._require(unit, Permission.POLICY_MANAGE)
            return cast(HouseholdPolicy, unit.policies.get(self.household_id))

    def operation(self, operation_id: str) -> OperationView:
        validate_identifier(operation_id)
        with self.transactions.read() as unit:
            member = unit.members.by_user(self.household_id, self.human.ha_user_id)
            HouseholdAccess(self.human).require(
                unit,
                self.household_id,
                Permission.OPERATIONS_READ,
                subject_member_id=member.member_id if member is not None else None,
            )
            receipt = unit.receipts.get_operation(
                self.household_id, self.human.ha_user_id, operation_id
            )
            if receipt is None:
                raise NotFound("operation_missing")
            if receipt.command.action != "member.enroll":
                original = _ORIGINAL_PERMISSION.get(receipt.command.action)
                if original is None:
                    raise Forbidden("permission_denied")
                self._require(unit, original)
            delivered = unit.outbox.delivered(receipt.operation_id)
            if delivered is None:
                raise StorageFailure("invalid_operation_record")
            return OperationView(receipt, delivered)
