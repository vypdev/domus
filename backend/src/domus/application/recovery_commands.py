"""Two-authority recovery keeps terminal approval separate from human HTTP commands."""

from dataclasses import dataclass, replace
from typing import Protocol, cast

from domus.application.authorization import HouseholdAccess
from domus.application.commands import AtomicCommands, Change
from domus.application.identity_ports import CurrentHuman
from domus.application.ports import Clock, Identifiers, Transactions, UnitOfWork
from domus.domain.errors import Conflict, Forbidden, InvalidInput, NotFound
from domus.domain.identity import (
    HouseholdPolicy,
    HumanIdentity,
    Member,
    MemberStatus,
    Permission,
    Role,
    recovery_allowed,
    validate_revision,
)
from domus.domain.recovery import RECOVERY_LIFETIME, RecoveryRequest, RecoveryState
from domus.domain.storage import (
    CommandKey,
    Installation,
    JsonDocument,
    Receipt,
    validate_identifier,
)


class RecoveryConfirmation(Protocol):
    """Only the installation-console composition supplies this port, never an HTTP DTO."""

    def confirm(self, request: RecoveryRequest, member: Member | None) -> bool: ...


def _policy(unit: UnitOfWork, household_id: str) -> HouseholdPolicy:
    home = unit.households.current()
    policy = unit.policies.get(household_id)
    if home is None or home.household_id != household_id or policy is None:
        raise Forbidden("recovery_unavailable")
    return policy


def _request(unit: UnitOfWork, household_id: str, request_id: str) -> RecoveryRequest:
    validate_identifier(request_id)
    value = unit.recoveries.get(household_id, request_id)
    if value is None:
        raise NotFound("recovery_missing")
    return value


def _own(
    unit: UnitOfWork,
    household_id: str,
    request_id: str,
    human: HumanIdentity,
    installation: Installation,
) -> RecoveryRequest:
    value = _request(unit, household_id, request_id)
    if value.target_ha_user_id != human.ha_user_id:
        raise NotFound("recovery_missing")
    if value.installation != installation:
        raise Conflict("recovery_binding_changed")
    return value


def _require_open(unit: UnitOfWork, household_id: str, request_id: str) -> None:
    if unit.recoveries.closed_before_restoration(household_id, request_id):
        raise Conflict("recovery_closed")


def _view(value: RecoveryRequest, now: int) -> JsonDocument:
    state = value.visible_state(now)
    return JsonDocument.from_value(
        {
            "request_id": value.request_id,
            "state": state,
            "revision": value.revision,
            "target_ha_user_id": value.target_ha_user_id,
            "mapping_mode": value.mapping.mode.value,
            "policy_revision": value.policy_revision,
            "member_id": value.member_id,
            "member_revision": value.member_revision,
            "created_at": value.created_at,
            "expires_at": value.expires_at,
            "approved_at": value.approved_at,
            "closed_at": value.closed_at,
        }
    )


@dataclass(frozen=True, slots=True)
class RecoveryQueries:
    transactions: Transactions
    human: HumanIdentity
    installation: Installation
    clock: Clock
    household_id: str = "home"

    def get(self, request_id: str) -> JsonDocument:
        with self.transactions.read() as unit:
            value = _own(unit, self.household_id, request_id, self.human, self.installation)
            _require_open(unit, self.household_id, request_id)
            return _view(value, self.clock.now())


@dataclass(frozen=True, slots=True)
class _HumanAuthority:
    human: HumanIdentity
    installation: Installation
    action: str
    request_id: str | None = None

    def require(self, command: CommandKey, unit: UnitOfWork) -> None:
        if command.actor_id != self.human.ha_user_id or command.action != self.action:
            raise Forbidden("permission_denied")
        policy = _policy(unit, command.household_id)
        if self.action in ("recovery.complete", "recovery.cancel"):
            value = _own(
                unit,
                command.household_id,
                cast(str, self.request_id),
                self.human,
                self.installation,
            )
            if self.action == "recovery.cancel":
                return
            if value.state is RecoveryState.CONSUMED:
                HouseholdAccess(self.human).require(
                    unit, command.household_id, Permission.POLICY_MANAGE
                )
                return
        elif self.action != "recovery.request":
            raise Forbidden("permission_denied")
        if not recovery_allowed(self.human, policy):
            raise Forbidden("recovery_unavailable")


@dataclass
class RecoveryCommands:
    transactions: Transactions
    actor: CurrentHuman
    installation: Installation
    clock: Clock
    identifiers: Identifiers
    household_id: str = "home"

    def _commands(
        self, human: HumanIdentity, action: str, request_id: str | None = None
    ) -> AtomicCommands:
        return AtomicCommands(
            self.transactions,
            _HumanAuthority(human, self.installation, action, request_id),
            self.clock,
            self.identifiers,
        )

    def start(self, key: str, expected_revision: int = 0) -> Receipt:
        if type(expected_revision) is not int or expected_revision != 0:
            raise InvalidInput("invalid_revision")
        human = self.actor.current()
        command = CommandKey(self.household_id, human.ha_user_id, "recovery.request", key)
        payload = JsonDocument.from_value({"expected_revision": expected_revision})

        def apply(unit: UnitOfWork) -> Change:
            now, policy = self.clock.now(), _policy(unit, self.household_id)
            pending = unit.recoveries.pending(self.household_id, now)
            if len(pending) >= 256:
                raise Conflict("recovery_capacity")
            if any(value.target_ha_user_id == human.ha_user_id for value in pending):
                raise Conflict("recovery_pending")
            member = unit.members.by_user(self.household_id, human.ha_user_id)
            value = RecoveryRequest(
                self.identifiers.new(),
                self.household_id,
                human.ha_user_id,
                self.installation,
                policy.mapping,
                policy.revision,
                member.member_id if member is not None else None,
                member.revision if member is not None else 0,
                now,
                now + RECOVERY_LIFETIME,
            )
            unit.recoveries.save(value, 0)
            result = _view(value, now)
            detail = JsonDocument.from_value(
                {"transition": "recovery.requested", "request_id": value.request_id}
            )
            return Change(result, detail, detail)

        return self._commands(human, command.action).execute(command, payload, apply)

    def status(self, request_id: str) -> JsonDocument:
        return RecoveryQueries(
            self.transactions,
            self.actor.current(),
            self.installation,
            self.clock,
            self.household_id,
        ).get(request_id)

    def complete(self, key: str, request_id: str, expected_revision: int) -> Receipt:
        validate_revision(expected_revision)
        validate_identifier(request_id)
        human = self.actor.current()
        command = CommandKey(self.household_id, human.ha_user_id, "recovery.complete", key)
        payload = JsonDocument.from_value(
            {"request_id": request_id, "expected_revision": expected_revision}
        )

        def apply(unit: UnitOfWork) -> Change:
            value = _own(unit, self.household_id, request_id, human, self.installation)
            _require_open(unit, self.household_id, request_id)
            if value.revision != expected_revision:
                raise Conflict("revision_conflict")
            current = unit.members.by_user(self.household_id, human.ha_user_id)
            value.require_current(self.installation, _policy(unit, self.household_id), current)
            consumed = value.consume(self.clock.now())
            if current is None:
                if len(unit.members.list(self.household_id)) >= 256:
                    raise Conflict("member_capacity")
                member = Member(
                    self.identifiers.new(),
                    self.household_id,
                    human.ha_user_id,
                    Role.ADMINISTRATOR,
                    MemberStatus.ACTIVE,
                    1,
                )
            else:
                member = replace(
                    current,
                    role=Role.ADMINISTRATOR,
                    status=MemberStatus.ACTIVE,
                    revision=current.revision + 1,
                )
            unit.members.save(member, 0 if current is None else current.revision)
            unit.recoveries.save(consumed, expected_revision)
            result = JsonDocument.from_value(
                {
                    "state": "recovered",
                    "request_id": request_id,
                    "request_revision": consumed.revision,
                    "member_id": member.member_id,
                    "member_revision": member.revision,
                    "role": member.role.value,
                    "policy_revision": value.policy_revision,
                }
            )
            detail = JsonDocument.from_value(
                {
                    "transition": "administrator.recovered",
                    "grant": result.decode(),
                    "previous_role": current.role.value if current is not None else None,
                    "previous_status": current.status.value if current is not None else None,
                }
            )
            return Change(result, detail, result)

        return self._commands(human, command.action, request_id).execute(command, payload, apply)

    def cancel(self, key: str, request_id: str, expected_revision: int) -> Receipt:
        validate_revision(expected_revision)
        validate_identifier(request_id)
        human = self.actor.current()
        command = CommandKey(self.household_id, human.ha_user_id, "recovery.cancel", key)
        payload = JsonDocument.from_value(
            {"request_id": request_id, "expected_revision": expected_revision}
        )

        def apply(unit: UnitOfWork) -> Change:
            current = _own(unit, self.household_id, request_id, human, self.installation)
            _require_open(unit, self.household_id, request_id)
            if current.revision != expected_revision:
                raise Conflict("revision_conflict")
            value = current.cancel(self.clock.now())
            unit.recoveries.save(value, expected_revision)
            result = _view(value, self.clock.now())
            return Change(
                result,
                result,
                JsonDocument.from_value({"request_id": request_id, "state": "canceled"}),
            )

        return self._commands(human, command.action, request_id).execute(command, payload, apply)


def _console_request(
    command: CommandKey, unit: UnitOfWork, installation: Installation, request_id: str
) -> RecoveryRequest:
    if (
        command.actor_id != "installation-console"
        or command.action != "recovery.approve"
        or command.key != request_id
    ):
        raise Forbidden("permission_denied")
    value = _request(unit, command.household_id, request_id)
    _require_open(unit, command.household_id, request_id)
    if value.installation != installation:
        raise Conflict("recovery_binding_changed")
    return value


@dataclass(frozen=True, slots=True)
class _ConsoleReceiptAuthority:
    installation: Installation
    request_id: str

    def require(self, command: CommandKey, unit: UnitOfWork) -> None:
        # Only read-only receipt lookup uses this authority; no effect executor receives it.
        _console_request(command, unit, self.installation, self.request_id)


@dataclass(frozen=True, slots=True)
class _ConsoleAuthority:
    installation: Installation
    clock: Clock
    request_id: str

    def require(self, command: CommandKey, unit: UnitOfWork) -> None:
        value = _console_request(command, unit, self.installation, self.request_id)
        value.require_current(
            self.installation,
            _policy(unit, command.household_id),
            unit.members.by_user(command.household_id, value.target_ha_user_id),
        )
        if value.visible_state(self.clock.now()) == "expired":
            raise Conflict("recovery_expired")
        if value.state not in (RecoveryState.PENDING, RecoveryState.APPROVED):
            raise Conflict("recovery_closed")


@dataclass
class RecoveryConsole:
    transactions: Transactions
    installation: Installation
    clock: Clock
    identifiers: Identifiers
    confirmation: RecoveryConfirmation
    household_id: str = "home"

    def approve(self, request_id: str) -> Receipt:
        command = CommandKey(
            self.household_id, "installation-console", "recovery.approve", request_id
        )
        authority = _ConsoleAuthority(self.installation, self.clock, request_id)
        commands = AtomicCommands(self.transactions, authority, self.clock, self.identifiers)
        payload = JsonDocument.from_value({"request_id": request_id, "expected_revision": 1})
        previous = AtomicCommands(
            self.transactions,
            _ConsoleReceiptAuthority(self.installation, request_id),
            self.clock,
            self.identifiers,
        ).replay(command, payload)
        if previous is not None:
            return previous
        with self.transactions.read() as unit:
            authority.require(command, unit)
            snapshot = _request(unit, self.household_id, request_id)
            member = unit.members.by_user(self.household_id, snapshot.target_ha_user_id)
        if self.confirmation.confirm(snapshot, member) is not True:
            raise Forbidden("console_confirmation_required")

        def apply(unit: UnitOfWork) -> Change:
            value = snapshot.approve(self.clock.now())
            unit.recoveries.save(value, snapshot.revision)
            result = _view(value, self.clock.now())
            detail = JsonDocument.from_value(
                {
                    "transition": "recovery.console_approved",
                    "authority": "installation_console",
                    "binding": value.document().decode(),
                }
            )
            return Change(
                result,
                detail,
                JsonDocument.from_value({"request_id": request_id, "state": "approved"}),
            )

        return commands.execute(command, payload, apply)
