"""One bounded local maintenance step commits actual fixed work or reconciles original proof."""

from dataclasses import asdict, dataclass, replace
from typing import cast

from domus.application.commands import AtomicCommands, Change
from domus.application.fixed_recurrence import FixedRecurrencePlanner
from domus.application.ports import Clock, Identifiers, Transactions, UnitOfWork
from domus.domain.errors import Conflict, Forbidden, InvalidInput, NotFound, StorageFailure
from domus.domain.recurrence_planning import FixedBatch, FixedCursor
from domus.domain.recurrence_records import (
    MAINTENANCE_ACTOR,
    FixedProgress,
    FixedSchedule,
    ScheduledSlot,
    ScheduleState,
)
from domus.domain.recurrence_rules import NominalDate, NominalSlot
from domus.domain.storage import (
    CommandKey,
    Installation,
    JsonDocument,
    Receipt,
    validate_identifier,
)
from domus.domain.task_values import DefinitionState
from domus.domain.tasks import TaskDefinition


@dataclass(frozen=True, slots=True)
class MaintenanceScope:
    """Composition owns this local capability; it is never decoded from HTTP or a stored rule."""

    installation: Installation
    household_id: str

    def __post_init__(self) -> None:
        validate_identifier(self.household_id)
        if not isinstance(self.installation, Installation):
            raise InvalidInput("invalid_maintenance_scope")

    def require(self, unit: UnitOfWork) -> None:
        household = unit.households.current()
        if (
            unit.recurrence.installation != self.installation
            or household is None
            or household.household_id != self.household_id
        ):
            raise Forbidden("maintenance_scope_denied")


@dataclass(frozen=True, slots=True)
class FixedStep:
    status: str
    schedule_id: str
    cursor: FixedCursor
    range_complete: bool
    periods_scanned: int = 0
    receipt: Receipt | None = None
    occurrence_id: str | None = None


@dataclass(frozen=True, slots=True)
class _Source:
    schedule: FixedSchedule
    progress: FixedProgress
    definition: TaskDefinition


@dataclass(frozen=True, slots=True)
class _FixedAuthority:
    scope: MaintenanceScope
    source: _Source
    command: CommandKey

    def require(self, command: CommandKey, unit: UnitOfWork) -> None:
        self.scope.require(unit)
        rule = self.source.schedule
        if (
            command != self.command
            or command.household_id != self.scope.household_id
            or command.actor_id != MAINTENANCE_ACTOR
            or command.action not in ("recurrence.materialize", "recurrence.scan")
            or rule.state is not ScheduleState.ACTIVE
            or self.source.definition.state is not DefinitionState.ACTIVE
        ):
            raise Forbidden("maintenance_scope_denied")
        if (
            unit.recurrence.schedule(rule.household_id, rule.schedule_id) != rule
            or unit.recurrence.progress(rule.household_id, rule.schedule_id) != self.source.progress
            or unit.tasks.definition(rule.household_id, rule.definition_id)
            != self.source.definition
        ):
            raise Conflict("recurrence_source_changed")


def _nominal(value: NominalSlot) -> dict[str, str]:
    return {
        "kind": "date" if isinstance(value, NominalDate) else "time",
        "local": value.local.isoformat(),
    }


@dataclass
class FixedMaintenance:
    transactions: Transactions
    scope: MaintenanceScope
    planner: FixedRecurrencePlanner
    clock: Clock
    identifiers: Identifiers

    def _source(self, unit: UnitOfWork, schedule_id: str) -> _Source:
        self.scope.require(unit)
        rule = unit.recurrence.schedule(self.scope.household_id, schedule_id)
        if rule is None:
            raise NotFound("recurrence_rule_missing")
        progress = unit.recurrence.progress(rule.household_id, schedule_id)
        definition = unit.tasks.definition(rule.household_id, rule.definition_id)
        if progress is None or definition is None or not progress.matches_schedule(rule):
            raise StorageFailure("invalid_recurrence_source")
        return _Source(rule, progress, definition)

    def step(self, schedule_id: str, before: NominalSlot, *, period_limit: int = 64) -> FixedStep:
        validate_identifier(schedule_id)
        if type(period_limit) is not int or not 1 <= period_limit <= 64:
            raise InvalidInput("invalid_recurrence_limits")
        with self.transactions.read() as unit:
            source = self._source(unit, schedule_id)
        rule, progress = source.schedule, source.progress
        if rule.state is not ScheduleState.ACTIVE:
            return FixedStep(rule.state.value, schedule_id, progress.cursor, False)
        if source.definition.state is not DefinitionState.ACTIVE:
            return FixedStep("definition_inactive", schedule_id, progress.cursor, False)
        self.planner.times.require_policy(rule.policy)
        batch = self.planner.expand(
            rule.pattern,
            rule.policy,
            cursor=progress.cursor,
            before=before,
            slot_limit=1,
            period_limit=period_limit,
        )
        if (
            not batch.slots
            and batch.cursor == progress.cursor
            and batch.range_complete == progress.range_complete
            and progress.last_run_at is not None
        ):
            return FixedStep(
                "current", schedule_id, batch.cursor, batch.range_complete, batch.periods_scanned
            )
        return self._commit(source, batch, before)

    def _commit(self, source: _Source, batch: FixedBatch, before: NominalSlot) -> FixedStep:
        rule, progress = source.schedule, source.progress
        planned = batch.slots[0] if batch.slots else None
        probe = (
            None
            if planned is None
            else ScheduledSlot(self.scope.installation, rule, planned, "pending", self.clock.now())
        )
        if probe is None:
            payload = JsonDocument.from_value(
                {
                    "version": 1,
                    "schedule_id": rule.schedule_id,
                    "pattern_revision": rule.pattern_revision,
                    "from_revision": progress.revision,
                    "from_cursor": asdict(progress.cursor),
                    "to_cursor": asdict(batch.cursor),
                    "before": _nominal(before),
                }
            )
            command = CommandKey(
                rule.household_id, MAINTENANCE_ACTOR, "recurrence.scan", payload.fingerprint
            )
        else:
            resolved = probe.planned.resolved
            payload = JsonDocument.from_value(
                {
                    "version": 1,
                    "slot_key": probe.key,
                    "definition_id": rule.definition_id,
                    "pattern": rule.pattern.fingerprint,
                    "nominal": _nominal(probe.planned.nominal),
                    "resolved_at": None if resolved is None else resolved.instant_ms,
                    "zone_digest": None if resolved is None else resolved.zone_digest,
                }
            )
            command = probe.command
        authority = _FixedAuthority(self.scope, source, command)
        commands = AtomicCommands(self.transactions, authority, self.clock, self.identifiers)
        created = False

        def apply(unit: UnitOfWork) -> Change:
            nonlocal created
            created = True
            if planned is None:
                result = JsonDocument.from_value(
                    {
                        "schedule_id": rule.schedule_id,
                        "processed_slots": 0,
                        "cursor": asdict(batch.cursor),
                        "range_complete": batch.range_complete,
                    }
                )
            else:
                work = source.definition.new_occurrence(
                    self.identifiers.new(),
                    self.clock.now(),
                    due_at=None if planned.resolved is None else planned.resolved.instant_ms,
                )
                slot = ScheduledSlot(
                    self.scope.installation, rule, planned, work.occurrence_id, work.created_at
                )
                unit.tasks.save_occurrence(work, 0)
                unit.recurrence.add_slot(slot)
                result = JsonDocument.from_value(
                    {
                        "slot_key": slot.key,
                        "occurrence_id": work.occurrence_id,
                        "schedule_id": rule.schedule_id,
                        "definition_id": rule.definition_id,
                        "nominal": _nominal(planned.nominal),
                        "resolved_at": work.due_at,
                    }
                )
            return Change(
                result,
                JsonDocument.from_value({"request": payload.decode(), "result": result.decode()}),
                JsonDocument.from_value({"version": 1, "kind": command.action, **result.decode()}),
            )

        with self.transactions.write() as unit:
            receipt = commands.in_unit(unit, command, payload, apply)
            occurrence_id = None
            status = "scan"
            if probe is not None:
                data = receipt.result.decode()
                occurrence_id = data.get("occurrence_id")
                try:
                    validate_identifier(cast(str, occurrence_id))
                    if data.get("slot_key") != probe.key:
                        raise InvalidInput("invalid_recurrence_effect")
                except InvalidInput:
                    raise StorageFailure("invalid_recurrence_effect") from None
                saved = unit.recurrence.slot(rule.household_id, probe.key)
                if receipt.historical:
                    if saved is not None:
                        raise StorageFailure("invalid_recurrence_effect")
                    status = "historical_absent"
                else:
                    if (
                        saved is None
                        or saved.occurrence_id != occurrence_id
                        or not saved.consistent_with(rule)
                        or saved.planned != planned
                    ):
                        raise StorageFailure("invalid_recurrence_effect")
                    status = "created" if created else "replayed"
            unit.recurrence.save_progress(
                replace(
                    progress,
                    cursor=batch.cursor,
                    revision=progress.revision + 1,
                    last_run_at=self.clock.now(),
                    range_complete=batch.range_complete,
                ),
                progress.revision,
            )
        return FixedStep(
            status,
            rule.schedule_id,
            batch.cursor,
            batch.range_complete,
            batch.periods_scanned,
            receipt,
            cast(str | None, occurrence_id),
        )
