"""Current administrator edits preserve eligible human linkage and a remaining administrator."""

from dataclasses import dataclass, replace
from typing import cast

from domus.application.administrator_proof import exact_human, remaining_humans
from domus.application.authorization import HouseholdAccess, MembershipAuthorization
from domus.application.commands import AtomicCommands, Change
from domus.application.identity_ports import CurrentHuman, HumanDirectory
from domus.application.ports import Clock, Identifiers, Transactions, UnitOfWork
from domus.domain.errors import Conflict, StorageFailure
from domus.domain.identity import (
    HouseholdPolicy,
    HumanIdentity,
    Member,
    MemberStatus,
    Permission,
    PermissionRule,
    Role,
    ensure_administrator,
)
from domus.domain.storage import CommandKey, JsonDocument, Receipt, validate_identifier


@dataclass(frozen=True, slots=True)
class UpdateMember:
    member_id: str
    expected_revision: int
    role: Role
    status: MemberStatus
    exceptions: tuple[PermissionRule, ...] = ()

    def __post_init__(self) -> None:
        Member(
            self.member_id,
            "home",
            "subject",
            self.role,
            self.status,
            self.expected_revision,
            self.exceptions,
        )
        object.__setattr__(
            self,
            "exceptions",
            tuple(sorted(self.exceptions, key=lambda rule: rule.permission.value)),
        )

    def document(self) -> JsonDocument:
        return JsonDocument.from_value(
            {
                "member_id": self.member_id,
                "expected_revision": self.expected_revision,
                "role": self.role.value,
                "status": self.status.value,
                "exceptions": [
                    {"permission": rule.permission.value, "allow": rule.allow}
                    for rule in self.exceptions
                ],
            }
        )


@dataclass(frozen=True, slots=True)
class _Snapshot:
    policy: HouseholdPolicy
    members: tuple[Member, ...]


@dataclass
class MemberCommands:
    transactions: Transactions
    actor: CurrentHuman
    directory: HumanDirectory
    clock: Clock
    identifiers: Identifiers
    household_id: str = "home"

    def __post_init__(self) -> None:
        validate_identifier(self.household_id)

    def _commands(self, human: HumanIdentity) -> AtomicCommands:
        return AtomicCommands(
            self.transactions,
            MembershipAuthorization(
                HouseholdAccess(human), "member.update", Permission.MEMBERS_MANAGE
            ),
            self.clock,
            self.identifiers,
        )

    def _snapshot(self, human: HumanIdentity) -> _Snapshot:
        with self.transactions.read() as unit:
            HouseholdAccess(human).require(unit, self.household_id, Permission.MEMBERS_MANAGE)
            members = unit.members.list(self.household_id)
            if len(members) > 256:
                raise StorageFailure("invalid_identity_record")
            return _Snapshot(cast(HouseholdPolicy, unit.policies.get(self.household_id)), members)

    def _proofs(
        self, human: HumanIdentity, snapshot: _Snapshot, proposed: Member
    ) -> tuple[HumanIdentity, ...]:
        humans = {human.ha_user_id: human}
        external = False
        if proposed.status is MemberStatus.ACTIVE and proposed.ha_user_id != human.ha_user_id:
            humans[proposed.ha_user_id] = exact_human(
                self.directory.get(proposed.ha_user_id), proposed.ha_user_id
            )
            external = True
        members = tuple(
            proposed if member.member_id == proposed.member_id else member
            for member in snapshot.members
        )
        resolved, batch = remaining_humans(
            snapshot.policy, members, tuple(humans.values()), self.directory
        )
        humans = {person.ha_user_id: person for person in resolved}
        external = external or batch
        if external:
            humans[human.ha_user_id] = exact_human(self.actor.current(), human.ha_user_id)
        return tuple(humans.values())

    def update(self, key: str, request: UpdateMember) -> Receipt:
        human = self.actor.current()
        command = CommandKey(self.household_id, human.ha_user_id, "member.update", key)
        payload = request.document()
        previous = self._commands(human).replay(command, payload)
        if previous is not None:
            return previous
        snapshot = self._snapshot(human)
        current = next(
            (member for member in snapshot.members if member.member_id == request.member_id), None
        )
        if current is None:
            raise Conflict("member_missing")
        if current.revision != request.expected_revision:
            raise Conflict("revision_conflict")
        proposed = replace(
            current,
            role=request.role,
            status=request.status,
            exceptions=request.exceptions,
            revision=current.revision + 1,
        )
        humans = self._proofs(human, snapshot, proposed)
        actor = next(person for person in humans if person.ha_user_id == human.ha_user_id)

        def apply(unit: UnitOfWork) -> Change:
            if (
                unit.policies.get(self.household_id) != snapshot.policy
                or unit.members.list(self.household_id) != snapshot.members
            ):
                raise Conflict("identity_state_changed")
            members = tuple(
                proposed if member.member_id == proposed.member_id else member
                for member in snapshot.members
            )
            ensure_administrator(snapshot.policy, members, humans)
            unit.members.save(proposed, request.expected_revision)
            result = JsonDocument.from_value(
                {
                    "member_id": proposed.member_id,
                    "revision": proposed.revision,
                    "status": proposed.status.value,
                    "role": proposed.role.value,
                }
            )
            detail = JsonDocument.from_value(
                {
                    "transition": "member.updated",
                    "previous_revision": current.revision,
                    "previous_role": current.role.value,
                    "previous_status": current.status.value,
                    "member": result.decode(),
                    "exceptions": request.document().decode()["exceptions"],
                }
            )
            return Change(result, detail, result)

        return self._commands(actor).execute(command, payload, apply)
