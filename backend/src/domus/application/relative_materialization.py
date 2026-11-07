"""A bounded initial relative step commits work, mapping, original proof and continuation."""

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import cast

from domus.application.commands import AtomicCommands, Change
from domus.application.fixed_materialization import MaintenanceScope
from domus.application.ports import Clock, Identifiers, Transactions, UnitOfWork
from domus.application.recurrence_ports import RecurrenceTimes
from domus.domain.errors import Conflict, Forbidden, InvalidInput, NotFound, StorageFailure
from domus.domain.recurrence_records import ScheduleState
from domus.domain.relative_recurrence import (
    RelativeOperation,
    RelativeProgress,
    RelativeSchedule,
    RelativeSlot,
)
from domus.domain.storage import CommandKey, JsonDocument, Receipt, validate_identifier
from domus.domain.task_values import DefinitionState
from domus.domain.tasks import TaskDefinition


@dataclass(frozen=True, slots=True)
class RelativeStep:
    status: str
    schedule_id: str
    receipt: Receipt | None = None
    occurrence_id: str | None = None


@dataclass(frozen=True, slots=True)
class RelativeSource:
    schedule: RelativeSchedule
    progress: RelativeProgress
    definition: TaskDefinition


@dataclass(frozen=True, slots=True)
class _InitialAuthority:
    scope: MaintenanceScope
    source: RelativeSource
    command: CommandKey

    def require(self, command: CommandKey, unit: UnitOfWork) -> None:
        self.scope.require(unit)
        if command != self.command:
            raise Forbidden("maintenance_scope_denied")
        rule = self.source.schedule
        if (
            unit.recurrence.relative_schedule(rule.household_id, rule.schedule_id) != rule
            or unit.recurrence.relative_progress(rule.household_id, rule.schedule_id)
            != self.source.progress
            or unit.tasks.definition(rule.household_id, rule.definition_id)
            != self.source.definition
        ):
            raise Conflict("recurrence_source_changed")


def initial_source(unit: UnitOfWork, scope: MaintenanceScope, schedule_id: str) -> RelativeSource:
    scope.require(unit)
    rule = unit.recurrence.relative_schedule(scope.household_id, schedule_id)
    if rule is None:
        raise NotFound("recurrence_rule_missing")
    progress = unit.recurrence.relative_progress(rule.household_id, schedule_id)
    definition = unit.tasks.definition(rule.household_id, rule.definition_id)
    if progress is None or definition is None or not progress.matches_schedule(rule):
        raise StorageFailure("invalid_recurrence_source")
    return RelativeSource(rule, progress, definition)


def _payload(slot: RelativeSlot) -> JsonDocument:
    return JsonDocument.from_value(
        {
            "version": 1,
            "slot_key": slot.key,
            "generation": slot.schedule.binding,
            "initial": slot.schedule.initial.value(),
        }
    )


def _result(source: RelativeSource, slot: RelativeSlot) -> JsonDocument:
    continuation = replace(
        source.progress,
        current_occurrence_id=slot.occurrence_id,
        current_slot_key=slot.key,
    )
    return JsonDocument.from_value(
        {
            "version": 1,
            "slot_key": slot.key,
            "occurrence_id": slot.occurrence_id,
            "schedule_id": slot.schedule.schedule_id,
            "definition_id": slot.schedule.definition_id,
            "created_at": slot.created_at,
            "relative_slot_fingerprint": slot.evidence_fingerprint,
            "relative_progress": continuation.state_document().decode(),
        }
    )


def _add_initial_slot(
    unit: UnitOfWork, source: RelativeSource, slot: RelativeSlot, payload: JsonDocument
) -> Change:
    unit.recurrence.add_relative_slot(slot)
    result = _result(source, slot)
    return Change(
        result,
        JsonDocument.from_value({"request": payload.decode(), "result": result.decode()}),
        JsonDocument.from_value({"version": 1, "kind": slot.command.action, **result.decode()}),
    )


def _advance_initial(
    unit: UnitOfWork, progress: RelativeProgress, slot: RelativeSlot, receipt: Receipt, now: int
) -> None:
    unit.recurrence.save_relative_progress(
        replace(
            progress,
            current_occurrence_id=slot.occurrence_id,
            current_slot_key=slot.key,
            last_run_at=now,
            revision=progress.revision + 1,
            evidence=RelativeOperation(receipt.command, receipt.operation_id),
        ),
        progress.revision,
    )


def adopt_initial(
    unit: UnitOfWork,
    commands: AtomicCommands,
    scope: MaintenanceScope,
    source: RelativeSource,
    slot: RelativeSlot,
) -> Receipt:
    """Record the ordinary initial effect for a manual task selected by the reviewed writer."""
    payload = _payload(slot)
    technical = replace(commands, authorization=_InitialAuthority(scope, source, slot.command))
    receipt = technical.in_unit(
        unit, slot.command, payload, lambda active: _add_initial_slot(active, source, slot, payload)
    )
    _advance_initial(unit, source.progress, slot, receipt, technical.clock.now())
    return receipt


@dataclass
class RelativeMaintenance:
    transactions: Transactions
    scope: MaintenanceScope
    times: RecurrenceTimes
    clock: Clock
    identifiers: Identifiers

    @staticmethod
    def _has_work(unit: UnitOfWork, rule: RelativeSchedule) -> bool:
        return bool(
            unit.tasks.occurrences(rule.household_id, definition_id=rule.definition_id, limit=1)
        )

    def _original_slot(self, source: RelativeSource, receipt: Receipt) -> RelativeSlot:
        data = receipt.result.decode()
        try:
            slot = RelativeSlot(
                self.scope.installation,
                source.schedule,
                source.schedule.initial,
                cast(str, data.get("occurrence_id")),
                cast(int, data.get("created_at")),
            )
        except InvalidInput:
            raise StorageFailure("invalid_recurrence_effect") from None
        if (
            receipt.command != slot.command
            or receipt.created_at < slot.created_at
            or receipt.result != _result(source, slot)
        ):
            raise StorageFailure("invalid_recurrence_effect")
        return slot

    def initial(
        self,
        schedule_id: str,
        *,
        expected_schedule: RelativeSchedule | None = None,
        should_continue: Callable[[], bool] = lambda: True,
    ) -> RelativeStep:
        """Create one initial obligation; existing manual work needs its explicit review flow."""
        validate_identifier(schedule_id)
        with self.transactions.read() as unit:
            source = initial_source(unit, self.scope, schedule_id)
            existing_work = (
                self._has_work(unit, source.schedule) if source.progress.pristine else False
            )
        rule, progress = source.schedule, source.progress
        if expected_schedule is not None and expected_schedule != rule:
            raise Conflict("recurrence_source_changed")
        if rule.state is not ScheduleState.ACTIVE:
            return RelativeStep(rule.state.value, schedule_id)
        if source.definition.state is not DefinitionState.ACTIVE:
            return RelativeStep("definition_inactive", schedule_id)
        if not progress.pristine:
            return RelativeStep(
                "current", schedule_id, occurrence_id=progress.current_occurrence_id
            )
        if not should_continue():
            return RelativeStep("stopped", schedule_id)
        probe = RelativeSlot(
            self.scope.installation, rule, rule.initial, "pending", self.clock.now()
        )
        payload = _payload(probe)
        commands = AtomicCommands(
            self.transactions,
            _InitialAuthority(self.scope, source, probe.command),
            self.clock,
            self.identifiers,
        )
        previous = commands.replay(probe.command, payload)
        if previous is None:
            if existing_work:
                return RelativeStep("initial_review_required", schedule_id)
            self.times.require_policy(rule.policy)
        if not should_continue():
            return RelativeStep("stopped", schedule_id)
        created = False

        def apply(unit: UnitOfWork) -> Change:
            nonlocal created
            # Recheck after provider I/O and immediately before any new write.
            if self._has_work(unit, rule):
                raise Conflict("relative_initial_review_required")
            work = source.definition.new_occurrence(
                self.identifiers.new(),
                self.clock.now(),
                due_at=None if rule.initial.resolved is None else rule.initial.resolved.instant_ms,
            )
            slot = RelativeSlot(
                self.scope.installation, rule, rule.initial, work.occurrence_id, work.created_at
            )
            unit.tasks.save_occurrence(work, 0)
            created = True
            return _add_initial_slot(unit, source, slot, payload)

        with self.transactions.write() as unit:
            if not should_continue():
                return RelativeStep("stopped", schedule_id)
            receipt = commands.in_unit(unit, probe.command, payload, apply)
            original = self._original_slot(source, receipt)
            saved = unit.recurrence.relative_slot(rule.household_id, original.key)
            if receipt.historical:
                if saved is not None:
                    raise StorageFailure("invalid_recurrence_effect")
                status = "historical_absent"
            else:
                if saved is None or saved.evidence_fingerprint != original.evidence_fingerprint:
                    raise StorageFailure("invalid_recurrence_effect")
                status = "created" if created else "replayed"
            _advance_initial(unit, progress, original, receipt, self.clock.now())
        return RelativeStep(status, schedule_id, receipt, original.occurrence_id)
