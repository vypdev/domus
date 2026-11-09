"""Reconcile one admitted original task event and its relative cycle in one writer."""

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import cast

from domus.application.commands import AtomicCommands, Change
from domus.application.fixed_materialization import MaintenanceScope
from domus.application.ports import Clock, Identifiers, Transactions, UnitOfWork
from domus.application.relative_materialization import RelativeStep
from domus.application.relative_recurrence import RelativeRecurrencePlanner
from domus.application.task_authorization import recorded_request
from domus.domain.errors import Conflict, Forbidden, NotFound, StorageFailure
from domus.domain.recurrence_records import MAINTENANCE_ACTOR, ScheduleState
from domus.domain.relative_lifecycle import (
    RelativeClosure,
    RelativeClosureKind,
    RelativeEventOutcome,
    SuccessorDisposition,
    WorkHistory,
    successor_disposition,
)
from domus.domain.relative_recurrence import (
    RelativeOperation,
    RelativeProgress,
    RelativeSchedule,
    RelativeSlot,
    SuccessorVisibility,
)
from domus.domain.storage import CommandKey, JsonDocument, JsonObject, Receipt
from domus.domain.task_events import TaskLifecycleEvent
from domus.domain.task_values import DefinitionState, OccurrenceState, VerificationState
from domus.domain.tasks import TaskCycle, TaskDefinition, TaskOccurrence


def occurrence_work_history(unit: UnitOfWork, work: TaskOccurrence) -> WorkHistory:
    rows = unit.tasks.history(work.household_id, work.occurrence_id, limit=100)
    revisions = set()
    for row in rows:
        result = row.evidence.receipt.result.decode()
        if (
            result.get("state") in ("in_progress", "completed")
            or row.evidence.receipt.command.action == "task.complete"
        ):
            return WorkHistory.STARTED
        revision = result.get("revision")
        if row.current and type(revision) is int and 2 <= revision <= work.revision:
            revisions.add(revision)
    if len(rows) < 100 and len(revisions) == work.revision - 1:
        return WorkHistory.UNSTARTED
    return WorkHistory.UNKNOWN


def relative_invalidation_command(household_id: str, closure_key: str) -> CommandKey:
    return CommandKey(
        household_id, MAINTENANCE_ACTOR, "recurrence.relative.invalidate", closure_key
    )


def recorded_invalidation(receipt: Receipt, closure_key: str, occurrence_id: str) -> str:
    result = receipt.result.decode()
    if (
        result.get("closure_key") != closure_key
        or result.get("occurrence_id") != occurrence_id
        or result.get("disposition") not in ("cancel", "retained", "review", "absent")
    ):
        raise StorageFailure("invalid_relative_closure_record")
    return cast(str, result["disposition"])


@dataclass(frozen=True, slots=True)
class _CycleAuthority:
    scope: MaintenanceScope
    expected: CommandKey

    def require(self, command: CommandKey, unit: UnitOfWork) -> None:
        self.scope.require(unit)
        if command != self.expected:
            raise Forbidden("maintenance_scope_denied")


@dataclass(frozen=True, slots=True)
class RelativeLifecycle:
    transactions: Transactions
    scope: MaintenanceScope
    planner: RelativeRecurrencePlanner
    clock: Clock
    identifiers: Identifiers

    def consume(
        self,
        schedule_id: str,
        event_key: str,
        *,
        should_continue: Callable[[], bool] = lambda: True,
    ) -> RelativeStep:
        """Recheck persisted source, current work and rule in the transaction that effects them."""
        household = self.scope.household_id
        with self.transactions.write() as unit:
            self.scope.require(unit)
            if not should_continue():
                return RelativeStep("stopped", schedule_id)
            record = unit.recurrence.relative_source(household, event_key)
            if record is None:
                raise NotFound("recurrence_source_missing")
            recorded_request(record.original.evidence)
            event = record.event(self.scope.installation)
            rule = unit.recurrence.relative_schedule(household, schedule_id)
            if rule is None or event.definition_id != rule.definition_id:
                raise NotFound("recurrence_rule_missing")
            previous = unit.recurrence.relative_source_outcome(household, event_key)
            if previous is not None:
                if previous.schedule_id != schedule_id:
                    raise Conflict("recurrence_source_changed")
                return RelativeStep(
                    previous.status, schedule_id, previous.receipt, previous.occurrence_id
                )
            progress = unit.recurrence.relative_progress(household, schedule_id)
            definition = unit.tasks.definition(household, rule.definition_id)
            if progress is None or definition is None or not progress.matches_schedule(rule):
                raise StorageFailure("invalid_recurrence_source")
            key = RelativeClosure.cycle_key(rule, event.cycle, self.scope.installation)
            closure = unit.recurrence.relative_closure(household, key)
            cycle = unit.tasks.cycle(household, event.cycle.cycle_id)
            if (
                cycle is not None
                and cycle.completion_snapshot() != event.cycle.completion_snapshot()
            ):
                raise StorageFailure("invalid_recurrence_source")
            if closure is not None:
                step = self._reconcile(unit, closure, cycle, progress, event)
            else:
                step = self._consume_new(
                    unit, rule, progress, definition, cycle, event, record.original.current
                )
            if step.status != "paused":
                unit.recurrence.finish_relative_source(
                    household,
                    event_key,
                    RelativeEventOutcome(
                        step.status, step.schedule_id, step.receipt, step.occurrence_id
                    ),
                )
            return step

    def _consume_new(
        self,
        unit: UnitOfWork,
        rule: RelativeSchedule,
        progress: RelativeProgress,
        definition: TaskDefinition,
        cycle: TaskCycle | None,
        event: TaskLifecycleEvent,
        current: bool,
    ) -> RelativeStep:
        household, schedule = rule.household_id, rule.schedule_id
        if progress.current_occurrence_id != event.cycle.occurrence_id:
            return RelativeStep("unrelated", schedule)
        if not current:
            return self._close(
                unit, rule, event.cycle, event, RelativeClosureKind.HISTORICAL_ABSENT
            )
        if cycle is None:
            raise StorageFailure("invalid_recurrence_source")
        if cycle.closed_at is not None:
            return self._close(unit, rule, cycle, event, RelativeClosureKind.REOPENED)
        if cycle.verification is VerificationState.REJECTED:
            return self._close(unit, rule, cycle, event, RelativeClosureKind.REJECTED)
        work = unit.tasks.occurrence(household, cycle.occurrence_id)
        if (
            work is None
            or work.current_cycle_id != cycle.cycle_id
            or work.current_cycle_revision != cycle.revision
            or work.revision < event.occurrence_revision
            or work.definition_snapshot.definition_id != rule.definition_id
        ):
            raise Conflict("recurrence_source_changed")
        if definition.state is not DefinitionState.ACTIVE:
            return RelativeStep("definition_inactive", schedule)
        if (
            rule.state is ScheduleState.ACTIVE
            and rule.visibility is SuccessorVisibility.AT_VERIFICATION
            and event.cycle.verification is VerificationState.PENDING
        ):
            return RelativeStep("waiting_verification", schedule)
        plan = self.planner.plan(rule, cycle)
        if plan.planned is None or plan.source is None:
            return RelativeStep(plan.status, schedule)
        now = self.clock.now()
        due = plan.planned.resolved
        successor = definition.new_occurrence(
            self.identifiers.new(), now, due_at=None if due is None else due.instant_ms
        )
        slot = RelativeSlot(
            self.scope.installation, rule, plan.planned, successor.occurrence_id, now, plan.source
        )
        result = {
            "slot_key": slot.key,
            "occurrence_id": slot.occurrence_id,
            "schedule_id": schedule,
            "definition_id": rule.definition_id,
            "relative_slot_fingerprint": slot.evidence_fingerprint,
        }
        updated = replace(
            progress,
            current_occurrence_id=slot.occurrence_id,
            current_slot_key=slot.key,
            source_after=event.position,
            last_run_at=now,
            revision=progress.revision + 1,
        )
        unit.tasks.save_occurrence(successor, 0)
        unit.recurrence.add_relative_slot(slot)
        return self._close(
            unit,
            rule,
            cycle,
            event,
            RelativeClosureKind.GENERATED,
            slot=slot,
            progress=updated,
            result=cast(JsonObject, result),
        )

    @staticmethod
    def _payload(closure_key: str, event: TaskLifecycleEvent) -> JsonDocument:
        return JsonDocument.from_value(
            {"version": 1, "closure_key": closure_key, "source_event": event.event_key}
        )

    def _commit(
        self, unit: UnitOfWork, command: CommandKey, payload: JsonDocument, result: JsonObject
    ) -> Receipt:
        def change(_: UnitOfWork) -> Change:
            return Change(
                JsonDocument.from_value(result),
                JsonDocument.from_value({"request": payload.decode(), "result": result}),
                JsonDocument.from_value({"version": 1, "kind": command.action, **result}),
            )

        return AtomicCommands(
            self.transactions, _CycleAuthority(self.scope, command), self.clock, self.identifiers
        ).in_unit(unit, command, payload, change)

    def _close(
        self,
        unit: UnitOfWork,
        rule: RelativeSchedule,
        cycle: TaskCycle,
        event: TaskLifecycleEvent,
        kind: RelativeClosureKind,
        *,
        slot: RelativeSlot | None = None,
        progress: RelativeProgress | None = None,
        result: JsonObject | None = None,
    ) -> RelativeStep:
        key = RelativeClosure.cycle_key(rule, cycle, self.scope.installation)
        command = (
            slot.command
            if slot is not None
            else CommandKey(rule.household_id, MAINTENANCE_ACTOR, "recurrence.relative.close", key)
        )
        recorded_at = slot.created_at if slot is not None else self.clock.now()
        closure = RelativeClosure(
            self.scope.installation,
            rule,
            cycle,
            kind,
            recorded_at,
            RelativeOperation(command, "pending"),
            slot,
        )
        output: JsonObject = {
            "version": 1,
            **(result or {}),
            "relative_closure": closure.document().decode(),
        }
        if progress is not None:
            output["relative_progress"] = progress.state_document().decode()
        payload = self._payload(key, event)
        receipt = self._commit(unit, command, payload, output)
        operation = RelativeOperation(receipt.command, receipt.operation_id)
        unit.recurrence.add_relative_closure(replace(closure, operation=operation))
        if progress is not None:
            unit.recurrence.save_relative_progress(
                replace(progress, evidence=operation), progress.revision - 1
            )
        return RelativeStep(
            kind.value, rule.schedule_id, receipt, None if slot is None else slot.occurrence_id
        )

    def _reconcile(
        self,
        unit: UnitOfWork,
        closure: RelativeClosure,
        cycle: TaskCycle | None,
        progress: RelativeProgress,
        event: TaskLifecycleEvent,
    ) -> RelativeStep:
        rule = closure.schedule
        receipt = unit.receipts.get(closure.operation.command)
        if not closure.matches_receipt(receipt):
            raise StorageFailure("invalid_relative_closure_record")
        original = cast(Receipt, receipt)
        slot = closure.successor
        if slot is None:
            return RelativeStep(closure.kind.value, rule.schedule_id, original)
        if original.historical:
            return RelativeStep("historical_absent", rule.schedule_id, original, slot.occurrence_id)
        payload = self._payload(closure.key, event)
        command = relative_invalidation_command(rule.household_id, closure.key)
        invalidation = unit.receipts.get(command)
        if invalidation is not None:
            return self._invalidation_step(closure, invalidation)
        successor = unit.tasks.occurrence(rule.household_id, slot.occurrence_id)
        history = (
            WorkHistory.UNKNOWN if successor is None else occurrence_work_history(unit, successor)
        )
        decision = successor_disposition(closure, cycle, successor, history)
        if decision is SuccessorDisposition.CURRENT:
            return RelativeStep("generated", rule.schedule_id, original, slot.occurrence_id)
        reason = (
            "relative_source_unavailable"
            if cycle is None
            else "relative_source_reopened"
            if cycle.closed_at is not None
            else "relative_source_rejected"
        )
        result: JsonObject = {
            "version": 1,
            "closure_key": closure.key,
            "disposition": decision.value,
            "occurrence_id": slot.occurrence_id,
            "reason": reason,
        }
        updated = None
        if decision is SuccessorDisposition.CANCEL:
            work = cast(TaskOccurrence, successor)
            unit.tasks.save_occurrence(
                work.transition(OccurrenceState.CANCELLED, reason), work.revision
            )
            if progress.current_occurrence_id == work.occurrence_id:
                parent = unit.recurrence.relative_slot_for_occurrence(
                    rule.household_id, closure.cycle.occurrence_id
                )
                if parent is None:
                    raise StorageFailure("invalid_relative_closure_record")
                updated = replace(
                    progress,
                    current_occurrence_id=parent.occurrence_id,
                    current_slot_key=parent.key,
                    last_run_at=self.clock.now(),
                    source_after=max(progress.source_after, event.position),
                    revision=progress.revision + 1,
                )
                result["relative_progress"] = updated.state_document().decode()
        invalidation = self._commit(unit, command, payload, result)
        if updated is not None:
            unit.recurrence.save_relative_progress(
                replace(updated, evidence=RelativeOperation(command, invalidation.operation_id)),
                progress.revision,
            )
        return self._invalidation_step(closure, invalidation)

    @staticmethod
    def _invalidation_step(closure: RelativeClosure, receipt: Receipt) -> RelativeStep:
        slot = cast(RelativeSlot, closure.successor)
        disposition = recorded_invalidation(receipt, closure.key, slot.occurrence_id)
        status = "historical_absent" if receipt.historical else disposition
        return RelativeStep(status, closure.schedule.schedule_id, receipt, slot.occurrence_id)
