"""Current local authority is checked inside each read or command transaction."""

from dataclasses import dataclass

from domus.application.ports import UnitOfWork
from domus.domain.errors import Forbidden
from domus.domain.identity import HumanIdentity, Member, Permission, allows
from domus.domain.storage import CommandKey


@dataclass(frozen=True, slots=True)
class HouseholdAccess:
    """The identity must come from the server proof boundary, never a request DTO.

    Mutating use cases must obtain fresh HA proof before entering SQLite. Reads
    may use an unexpired session's outage lease. Both reread current local facts;
    an HA proof and a local commit cannot be atomic across the two systems.
    """

    human: HumanIdentity

    def require(
        self,
        unit: UnitOfWork,
        household_id: str,
        permission: Permission,
        *,
        subject_member_id: str | None = None,
        assigned_to: tuple[str, ...] = (),
    ) -> Member:
        member = unit.members.by_user(household_id, self.human.ha_user_id)
        policy = unit.policies.get(household_id)
        if (
            member is None
            or policy is None
            or not allows(
                self.human,
                member,
                policy,
                permission,
                household_id,
                subject_member_id=subject_member_id,
                assigned_to=assigned_to,
            )
        ):
            raise Forbidden("permission_denied")
        return member


@dataclass(frozen=True, slots=True)
class MembershipAuthorization:
    """Bind a server-selected command action/permission to its proven actor."""

    access: HouseholdAccess
    action: str
    permission: Permission
    subject_member_id: str | None = None
    assigned_to: tuple[str, ...] = ()

    def require(self, command: CommandKey, unit: UnitOfWork) -> None:
        if command.actor_id != self.access.human.ha_user_id or command.action != self.action:
            raise Forbidden("permission_denied")
        self.access.require(
            unit,
            command.household_id,
            self.permission,
            subject_member_id=self.subject_member_id,
            assigned_to=self.assigned_to,
        )
