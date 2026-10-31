"""Explicit policy changes preserve administrator provenance and current human authority."""

from dataclasses import dataclass
from typing import cast

from domus.application.administrator_proof import exact_human, remaining_humans
from domus.application.authorization import HouseholdAccess, MembershipAuthorization
from domus.application.commands import AtomicCommands, Change
from domus.application.identity_ports import CurrentHuman, HumanDirectory
from domus.application.ports import Clock, Identifiers, Transactions, UnitOfWork
from domus.domain.errors import Conflict, Forbidden, InvalidInput, StorageFailure
from domus.domain.identity import (
    AdministratorMapping,
    HouseholdPolicy,
    HumanIdentity,
    MappingMode,
    MemberStatus,
    Permission,
    ProfileRule,
    ensure_administrator,
)
from domus.domain.storage import CommandKey, JsonDocument, Receipt, validate_identifier


@dataclass(frozen=True, slots=True)
class UpdatePolicy:
    expected_revision: int
    mapping: AdministratorMapping
    adjustments: tuple[ProfileRule, ...] = ()

    def __post_init__(self) -> None:
        HouseholdPolicy("home", self.mapping, self.expected_revision, self.adjustments)
        object.__setattr__(
            self,
            "adjustments",
            tuple(
                sorted(self.adjustments, key=lambda rule: (rule.role.value, rule.permission.value))
            ),
        )

    def document(self) -> JsonDocument:
        return JsonDocument.from_value(
            {
                "expected_revision": self.expected_revision,
                "mapping_mode": self.mapping.mode.value,
                "target_ha_user_id": self.mapping.target_ha_user_id,
                "adjustments": [
                    {
                        "role": rule.role.value,
                        "permission": rule.permission.value,
                        "allow": rule.allow,
                    }
                    for rule in self.adjustments
                ],
            }
        )


@dataclass
class PolicyCommands:
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
                HouseholdAccess(human), "policy.update", Permission.POLICY_MANAGE
            ),
            self.clock,
            self.identifiers,
        )

    def update(self, key: str, request: UpdatePolicy) -> Receipt:
        human = self.actor.current()
        command = CommandKey(self.household_id, human.ha_user_id, "policy.update", key)
        payload = request.document()
        previous = self._commands(human).replay(command, payload)
        if previous is not None:
            return previous
        with self.transactions.read() as unit:
            HouseholdAccess(human).require(unit, self.household_id, Permission.POLICY_MANAGE)
            current = cast(HouseholdPolicy, unit.policies.get(self.household_id))
            if current.revision != request.expected_revision:
                raise Conflict("revision_conflict")
            members = unit.members.list(self.household_id)
            if len(members) > 256:
                raise StorageFailure("invalid_identity_record")
            if request.mapping.mode is MappingMode.SETUP:
                founder = unit.audit.setup_actor(self.household_id)
                if founder is None:
                    raise Conflict("setup_provenance_required")
                if founder != request.mapping.target_ha_user_id:
                    raise InvalidInput("setup_administrator_mismatch")
        proposed = HouseholdPolicy(
            self.household_id, request.mapping, current.revision + 1, request.adjustments
        )
        humans = {human.ha_user_id: human}
        external = False
        target = request.mapping.target_ha_user_id
        if target is not None:
            member = next((person for person in members if person.ha_user_id == target), None)
            if member is None or member.status is not MemberStatus.ACTIVE:
                raise Conflict("mapping_target_inactive")
            target_human = human
            if target != human.ha_user_id:
                target_human = exact_human(self.directory.get(target), target)
                external = True
            if request.mapping.mode is MappingMode.SETUP and not target_human.is_administrator:
                raise Forbidden("ha_administrator_required")
            humans[target] = target_human
        resolved, batch = remaining_humans(
            proposed, members, tuple(humans.values()), self.directory
        )
        humans = {person.ha_user_id: person for person in resolved}
        if external or batch:
            humans[human.ha_user_id] = exact_human(self.actor.current(), human.ha_user_id)
        actor = humans[human.ha_user_id]

        def apply(unit: UnitOfWork) -> Change:
            if (
                unit.policies.get(self.household_id) != current
                or unit.members.list(self.household_id) != members
            ):
                raise Conflict("identity_state_changed")
            ensure_administrator(proposed, members, tuple(humans.values()))
            unit.policies.save(proposed, request.expected_revision)
            result = JsonDocument.from_value(
                {
                    "household_id": self.household_id,
                    "revision": proposed.revision,
                    "mapping_mode": proposed.mapping.mode.value,
                }
            )
            detail = JsonDocument.from_value(
                {
                    "transition": "policy.updated",
                    "previous_revision": current.revision,
                    "previous_mapping_mode": current.mapping.mode.value,
                    "policy": request.document().decode(),
                }
            )
            return Change(result, detail, result)

        return self._commands(actor).execute(command, payload, apply)
