"""Current public-profile authority and owner-only original preference disclosure."""

from dataclasses import dataclass

from domus.application.authorization import HouseholdAccess
from domus.application.ports import UnitOfWork
from domus.domain.errors import Forbidden, InvalidInput, StorageFailure
from domus.domain.identity import HumanIdentity, Member, Permission, allows
from domus.domain.storage import CommandKey, Receipt, validate_identifier

ALIAS_ACTION = "member.presentation.update"
PREFERENCES_ACTION = "member.preferences.update"


def preference_owner(
    unit: UnitOfWork, human: HumanIdentity, household_id: str, *, write: bool = False
) -> Member:
    member = unit.members.by_user(household_id, human.ha_user_id)
    return HouseholdAccess(human).require(
        unit,
        household_id,
        Permission.PREFERENCES_WRITE if write else Permission.PREFERENCES_READ,
        subject_member_id=member.member_id if member is not None else None,
    )


def require_alias(
    unit: UnitOfWork, human: HumanIdentity, household_id: str, subject_member_id: str
) -> None:
    member = unit.members.by_user(household_id, human.ha_user_id)
    policy = unit.policies.get(household_id)
    if member is None or policy is None:
        raise Forbidden("permission_denied")
    if not (
        allows(human, member, policy, Permission.MEMBERS_MANAGE, household_id)
        or allows(
            human,
            member,
            policy,
            Permission.PREFERENCES_WRITE,
            household_id,
            subject_member_id=subject_member_id,
        )
    ):
        raise Forbidden("permission_denied")


@dataclass(frozen=True, slots=True)
class ProfileAuthorization:
    human: HumanIdentity
    action: str
    subject_member_id: str | None = None

    def require(self, command: CommandKey, unit: UnitOfWork) -> None:
        if command.actor_id != self.human.ha_user_id or command.action != self.action:
            raise Forbidden("permission_denied")
        if self.action == ALIAS_ACTION and self.subject_member_id is not None:
            require_alias(unit, self.human, command.household_id, self.subject_member_id)
        elif self.action == PREFERENCES_ACTION and self.subject_member_id is None:
            preference_owner(unit, self.human, command.household_id, write=True)
        else:
            raise Forbidden("permission_denied")


def _original_subject(receipt: Receipt) -> str:
    try:
        value = receipt.result.decode().get("member_id")
        if not isinstance(value, str):
            raise InvalidInput("invalid_member_id")
        validate_identifier(value)
        return value
    except InvalidInput:
        raise StorageFailure("invalid_operation_record") from None


def require_profile_original(
    unit: UnitOfWork, human: HumanIdentity, household_id: str, receipt: Receipt
) -> bool:
    """True requires current profile authority; False grants nothing to another action."""
    if receipt.command.action not in (ALIAS_ACTION, PREFERENCES_ACTION):
        return False
    if receipt.command.household_id != household_id or receipt.command.actor_id != human.ha_user_id:
        raise Forbidden("permission_denied")
    if receipt.command.action == PREFERENCES_ACTION:
        member = preference_owner(unit, human, household_id, write=True)
        if _original_subject(receipt) != member.member_id:
            raise Forbidden("permission_denied")
    else:
        require_alias(unit, human, household_id, _original_subject(receipt))
    return True
