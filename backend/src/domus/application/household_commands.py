"""Explicit household setup and own enrollment commit through the durable command boundary."""

from dataclasses import dataclass
from typing import cast

from domus.application.authorization import HouseholdAccess, MembershipAuthorization
from domus.application.commands import AtomicCommands, Change
from domus.application.identity_ports import CurrentHuman, HumanDirectory
from domus.application.ports import Clock, Identifiers, TimeZones, Transactions, UnitOfWork
from domus.domain.errors import Conflict, Forbidden, InvalidInput
from domus.domain.identity import (
    AdministratorMapping,
    HouseholdPolicy,
    HumanIdentity,
    MappingMode,
    Member,
    MemberStatus,
    Permission,
    Role,
    validate_revision,
)
from domus.domain.storage import CommandKey, Household, JsonDocument, Receipt, validate_identifier


def _initial_revision(value: int) -> None:
    if type(value) is not int or value != 0:
        raise InvalidInput("invalid_revision")


@dataclass(frozen=True, slots=True)
class SetupHousehold:
    name: str
    time_zone: str
    mapping_mode: MappingMode = MappingMode.ALL
    selected_ha_user_id: str | None = None
    expected_revision: int = 0

    def __post_init__(self) -> None:
        _initial_revision(self.expected_revision)
        home = Household("home", self.name, self.time_zone, 1)
        object.__setattr__(self, "name", home.name)
        if not isinstance(self.mapping_mode, MappingMode) or (
            self.mapping_mode is MappingMode.SELECTED
        ) != (self.selected_ha_user_id is not None):
            raise InvalidInput("invalid_administrator_mapping")
        if self.selected_ha_user_id is not None:
            validate_identifier(self.selected_ha_user_id)

    def document(self) -> JsonDocument:
        return JsonDocument.from_value(
            {
                "name": self.name,
                "time_zone": self.time_zone,
                "mapping_mode": self.mapping_mode.value,
                "selected_ha_user_id": self.selected_ha_user_id,
                "expected_revision": self.expected_revision,
            }
        )


@dataclass(frozen=True, slots=True)
class _InitialAuthority:
    human: HumanIdentity
    action: str

    def require(self, command: CommandKey, unit: UnitOfWork) -> None:
        if (
            self.action not in ("household.setup", "member.enroll")
            or command.actor_id != self.human.ha_user_id
            or command.action != self.action
        ):
            raise Forbidden("permission_denied")
        home = unit.households.current()
        if self.action == "household.setup" and home is None:
            if not self.human.is_administrator:
                raise Forbidden("permission_denied")
            return
        if home is None or home.household_id != command.household_id:
            raise Forbidden("permission_denied")
        if self.action == "household.setup":
            HouseholdAccess(self.human).require(
                unit, home.household_id, Permission.HOUSEHOLD_MANAGE
            )
            return
        member = unit.members.by_user(home.household_id, self.human.ha_user_id)
        if unit.policies.get(home.household_id) is None or (
            member is not None and member.status not in (MemberStatus.PENDING, MemberStatus.ACTIVE)
        ):
            raise Forbidden("permission_denied")


@dataclass
class HouseholdCommands:
    transactions: Transactions
    actor: CurrentHuman
    directory: HumanDirectory
    time_zones: TimeZones
    clock: Clock
    identifiers: Identifiers
    household_id: str = "home"

    def __post_init__(self) -> None:
        validate_identifier(self.household_id)

    def _initial(self, human: HumanIdentity, action: str) -> AtomicCommands:
        return AtomicCommands(
            self.transactions, _InitialAuthority(human, action), self.clock, self.identifiers
        )

    def setup(self, key: str, request: SetupHousehold) -> Receipt:
        human = self.actor.current()
        command = CommandKey(self.household_id, human.ha_user_id, "household.setup", key)
        payload = request.document()
        commands = self._initial(human, command.action)
        previous = commands.replay(command, payload)
        if previous is not None:
            return previous
        self.time_zones.require(request.time_zone)
        target = human
        if request.mapping_mode is MappingMode.SELECTED:
            user_id = cast(str, request.selected_ha_user_id)
            target = human if user_id == human.ha_user_id else self.directory.get(user_id)
            if target.ha_user_id != user_id:
                raise Forbidden("identity_mismatch")
        mapping = AdministratorMapping(
            request.mapping_mode,
            None if request.mapping_mode is MappingMode.ALL else target.ha_user_id,
        )

        def apply(unit: UnitOfWork) -> Change:
            if unit.households.current() is not None:
                raise Conflict("household_exists")
            unit.households.save(
                Household(self.household_id, request.name, request.time_zone, 1), 0
            )
            unit.policies.save(HouseholdPolicy(self.household_id, mapping, 1), 0)
            member_id = self.identifiers.new()
            unit.members.save(
                Member(
                    member_id,
                    self.household_id,
                    human.ha_user_id,
                    Role.VIEWER,
                    MemberStatus.ACTIVE,
                    1,
                ),
                0,
            )
            administrator_id = member_id
            if target.ha_user_id != human.ha_user_id:
                administrator_id = self.identifiers.new()
                unit.members.save(
                    Member(
                        administrator_id,
                        self.household_id,
                        target.ha_user_id,
                        Role.VIEWER,
                        MemberStatus.ACTIVE,
                        1,
                    ),
                    0,
                )
            result = JsonDocument.from_value(
                {
                    "state": "configured",
                    "household_id": self.household_id,
                    "revision": 1,
                    "policy_revision": 1,
                    "member_id": member_id,
                    "administrator_member_id": administrator_id,
                    "mapping_mode": mapping.mode.value,
                }
            )
            detail = JsonDocument.from_value(
                {
                    "transition": "household.configured",
                    "mapping_mode": mapping.mode.value,
                    "administrator_member_id": administrator_id,
                }
            )
            event = JsonDocument.from_value({"household_id": self.household_id, "revision": 1})
            return Change(result, detail, event)

        return commands.execute(command, payload, apply)

    def enroll(self, key: str, expected_revision: int = 0) -> Receipt:
        _initial_revision(expected_revision)
        human = self.actor.current()
        command = CommandKey(self.household_id, human.ha_user_id, "member.enroll", key)
        payload = JsonDocument.from_value({"expected_revision": expected_revision})

        def apply(unit: UnitOfWork) -> Change:
            if unit.members.by_user(self.household_id, human.ha_user_id) is not None:
                raise Conflict("member_exists")
            if len(unit.members.list(self.household_id)) >= 256:
                raise Conflict("member_capacity")
            policy = cast(HouseholdPolicy, unit.policies.get(self.household_id))
            status = (
                MemberStatus.ACTIVE
                if policy.mapping.mode is MappingMode.ALL and human.is_administrator
                else MemberStatus.PENDING
            )
            member_id = self.identifiers.new()
            member = Member(member_id, self.household_id, human.ha_user_id, Role.VIEWER, status, 1)
            unit.members.save(member, 0)
            result = JsonDocument.from_value(
                {
                    "member_id": member_id,
                    "status": status.value,
                    "role": member.role.value,
                    "revision": 1,
                    "policy_revision": policy.revision,
                }
            )
            detail = JsonDocument.from_value(
                {"transition": "member.enrolled", "member_id": member_id, "status": status.value}
            )
            return Change(result, detail, detail)

        return self._initial(human, command.action).execute(command, payload, apply)

    def update(self, key: str, name: str, time_zone: str, expected_revision: int) -> Receipt:
        validate_revision(expected_revision)
        proposed = Household(self.household_id, name, time_zone, expected_revision + 1)
        human = self.actor.current()
        command = CommandKey(self.household_id, human.ha_user_id, "household.update", key)
        payload = JsonDocument.from_value(
            {
                "name": proposed.name,
                "time_zone": proposed.time_zone,
                "expected_revision": expected_revision,
            }
        )
        authority = MembershipAuthorization(
            HouseholdAccess(human), command.action, Permission.HOUSEHOLD_MANAGE
        )
        commands = AtomicCommands(self.transactions, authority, self.clock, self.identifiers)
        previous = commands.replay(command, payload)
        if previous is not None:
            return previous
        self.time_zones.require(proposed.time_zone)

        def apply(unit: UnitOfWork) -> Change:
            unit.households.save(proposed, expected_revision)
            result = JsonDocument.from_value(
                {"household_id": proposed.household_id, "revision": proposed.revision}
            )
            detail = JsonDocument.from_value(
                {"transition": "household.updated", "revision": proposed.revision}
            )
            return Change(result, detail, result)

        return commands.execute(command, payload, apply)
