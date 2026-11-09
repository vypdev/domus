"""Read and change the current member's calendar preference and recover their original."""

from collections.abc import Callable
from dataclasses import dataclass, replace

from domus.application.commands import AtomicCommands, Change
from domus.application.identity_ports import CurrentHuman
from domus.application.member_profile_access import preference_owner
from domus.application.ports import Clock, Identifiers, Transactions, UnitOfWork
from domus.domain.calendar_values import CalendarPreference, WeekStart
from domus.domain.errors import Conflict, Forbidden, InvalidInput, NotFound
from domus.domain.identity import HumanIdentity, Member, validate_revision
from domus.domain.storage import CommandKey, JsonDocument, Receipt

CALENDAR_PREFERENCE_ACTION = "calendar.preferences.update"


@dataclass(frozen=True, slots=True)
class CalendarPreferenceUpdate:
    expected_revision: int
    week_start: WeekStart

    def __post_init__(self) -> None:
        validate_revision(self.expected_revision)
        if not isinstance(self.week_start, WeekStart):
            raise InvalidInput("invalid_calendar_week_start")

    def document(self) -> JsonDocument:
        return JsonDocument.from_value(
            {"expected_revision": self.expected_revision, "week_start": self.week_start.value}
        )


@dataclass(frozen=True, slots=True)
class _OwnerAuthority:
    human: HumanIdentity
    command: CommandKey

    def require(self, command: CommandKey, unit: UnitOfWork) -> None:
        if command != self.command:
            raise Forbidden("permission_denied")
        self.owner(unit)

    def owner(self, unit: UnitOfWork) -> Member:
        return preference_owner(unit, self.human, self.command.household_id, write=True)

    def check_result(self, unit: UnitOfWork, receipt: Receipt) -> None:
        if receipt.result.decode().get("member_id") != self.owner(unit).member_id:
            raise Forbidden("permission_denied")


@dataclass(frozen=True, slots=True)
class CalendarCommands:
    transactions: Transactions
    actor: CurrentHuman
    read_actor: Callable[[], HumanIdentity]
    clock: Clock
    identifiers: Identifiers
    household_id: str = "home"

    def preference(self) -> CalendarPreference:
        human = self.read_actor()
        with self.transactions.read() as unit:
            member = preference_owner(unit, human, self.household_id)
            return unit.calendar_preferences.get(self.household_id, member.member_id)

    def _authority(self, human: HumanIdentity, key: str) -> _OwnerAuthority:
        return _OwnerAuthority(
            human, CommandKey(self.household_id, human.ha_user_id, CALENDAR_PREFERENCE_ACTION, key)
        )

    def update(self, key: str, request: CalendarPreferenceUpdate) -> Receipt:
        authority = self._authority(self.actor.current(), key)
        commands = AtomicCommands(self.transactions, authority, self.clock, self.identifiers)

        def apply(unit: UnitOfWork) -> Change:
            owner = authority.owner(unit)
            current = unit.calendar_preferences.get(self.household_id, owner.member_id)
            if current.revision != request.expected_revision:
                raise Conflict("revision_conflict")
            updated = replace(current, week_start=request.week_start, revision=current.revision + 1)
            unit.calendar_preferences.save(updated, current.revision)
            fact = JsonDocument.from_value({"revision": updated.revision})
            return Change(
                JsonDocument.from_value(
                    {
                        "member_id": owner.member_id,
                        "revision": updated.revision,
                        "week_start": updated.week_start.value,
                    }
                ),
                fact,
                fact,
            )

        with self.transactions.write() as unit:
            receipt = commands.in_unit(unit, authority.command, request.document(), apply)
            authority.check_result(unit, receipt)
            return receipt

    def original(self, key: str) -> Receipt:
        authority = self._authority(self.read_actor(), key)
        with self.transactions.read() as unit:
            authority.require(authority.command, unit)
            receipt = unit.receipts.get(authority.command)
            if receipt is None:
                raise NotFound("operation_missing")
            authority.check_result(unit, receipt)
            return receipt
