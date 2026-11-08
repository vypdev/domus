"""Immutable consumer closure and pure successor policy do not grant authority or change work."""

import json
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import cast

from domus.domain.errors import InvalidInput
from domus.domain.recurrence_records import MAINTENANCE_ACTOR
from domus.domain.relative_recurrence import RelativeOperation, RelativeSchedule, RelativeSlot
from domus.domain.storage import (
    Installation,
    JsonDocument,
    JsonObject,
    Receipt,
    validate_identifier,
)
from domus.domain.task_events import TaskLifecycleEvent
from domus.domain.task_values import OccurrenceState, VerificationState, validate_task_time
from domus.domain.tasks import TaskCycle, TaskOccurrence


def _cycle_key(
    installation: Installation,
    household_id: str,
    schedule_id: str,
    definition_id: str,
    occurrence_id: str,
    cycle_id: str,
) -> str:
    return JsonDocument.from_value(
        {
            "version": 1,
            "installation": asdict(installation),
            "household_id": household_id,
            "schedule_id": schedule_id,
            "definition_id": definition_id,
            "occurrence_id": occurrence_id,
            "cycle_id": cycle_id,
        }
    ).fingerprint


class RelativeClosureKind(StrEnum):
    GENERATED = "generated"
    REJECTED = "rejected"
    REOPENED = "reopened"
    HISTORICAL_ABSENT = "historical_absent"


class WorkHistory(StrEnum):
    UNSTARTED = "unstarted"
    STARTED = "started"
    UNKNOWN = "unknown"


class SuccessorDisposition(StrEnum):
    CURRENT = "current"
    CLOSED = "closed"
    ABSENT = "absent"
    RETAINED = "retained"
    REVIEW = "review"
    CANCEL = "cancel"


@dataclass(frozen=True, slots=True)
class RelativeClosure:
    """One original cycle is fenced across rule generations and compatible restoration.

    This is consumer proof, distinct from closing or approving the human TaskCycle.
    A generated closure keeps its original slot even if later work needs invalidation.
    Persistence must enforce uniqueness by key and validate the original receipt.
    """

    installation: Installation
    schedule: RelativeSchedule
    cycle: TaskCycle
    kind: RelativeClosureKind
    recorded_at: int
    operation: RelativeOperation
    successor: RelativeSlot | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.installation, Installation)
            or not isinstance(self.schedule, RelativeSchedule)
            or not isinstance(self.cycle, TaskCycle)
            or not isinstance(self.kind, RelativeClosureKind)
            or not isinstance(self.operation, RelativeOperation)
        ):
            raise InvalidInput("invalid_relative_closure")
        validate_task_time(self.recorded_at)
        latest = max(
            self.schedule.created_at,
            self.cycle.recorded_at,
            self.cycle.verified_at if self.cycle.verified_at is not None else 0,
            self.cycle.closed_at if self.cycle.closed_at is not None else 0,
        )
        if self.cycle.household_id != self.schedule.household_id or self.recorded_at < latest:
            raise InvalidInput("invalid_relative_closure")
        slot = self.successor
        command = self.operation.command
        if self.kind is RelativeClosureKind.GENERATED:
            if (
                not isinstance(slot, RelativeSlot)
                or not self.schedule.allows_successor(self.cycle)
                or slot.installation != self.installation
                or slot.schedule != self.schedule
                or slot.source is None
                or slot.source.cycle != self.cycle.completion_snapshot()
                or slot.created_at != self.recorded_at
                or command != slot.command
            ):
                raise InvalidInput("invalid_relative_closure")
        elif (
            slot is not None
            or command.household_id != self.schedule.household_id
            or command.actor_id != MAINTENANCE_ACTOR
            or command.action != "recurrence.relative.close"
            or command.key != self.key
            or (
                self.kind is RelativeClosureKind.REJECTED
                and self.cycle.verification is not VerificationState.REJECTED
            )
            or (self.kind is RelativeClosureKind.REOPENED and self.cycle.closed_at is None)
        ):
            raise InvalidInput("invalid_relative_closure")

    @staticmethod
    def cycle_key(schedule: RelativeSchedule, cycle: TaskCycle, installation: Installation) -> str:
        if (
            not isinstance(schedule, RelativeSchedule)
            or not isinstance(cycle, TaskCycle)
            or not isinstance(installation, Installation)
            or cycle.household_id != schedule.household_id
        ):
            raise InvalidInput("invalid_relative_closure")
        return _cycle_key(
            installation,
            schedule.household_id,
            schedule.schedule_id,
            schedule.definition_id,
            cycle.occurrence_id,
            cycle.cycle_id,
        )

    @property
    def key(self) -> str:
        return self.cycle_key(self.schedule, self.cycle, self.installation)

    def document(self) -> JsonDocument:
        return JsonDocument.from_value(
            {
                "version": 1,
                "key": self.key,
                "kind": self.kind.value,
                "installation": asdict(self.installation),
                "schedule": self.schedule.generation_document().decode(),
                "cycle": JsonDocument(json.dumps(asdict(self.cycle))).decode(),
                "recorded_at": self.recorded_at,
                "successor": None
                if self.successor is None
                else {
                    "slot_key": self.successor.key,
                    "occurrence_id": self.successor.occurrence_id,
                    "fingerprint": self.successor.evidence_fingerprint,
                },
            }
        )

    def matches_receipt(self, receipt: Receipt | None) -> bool:
        if (
            receipt is None
            or receipt.command != self.operation.command
            or receipt.operation_id != self.operation.operation_id
        ):
            return False
        return JsonDocument.from_value(
            {"relative_closure": self.document().decode()}
        ) == JsonDocument.from_value(
            {"relative_closure": receipt.result.decode().get("relative_closure")}
        )

    def matches_source(self, schedule: RelativeSchedule, cycle: TaskCycle) -> bool:
        return (
            isinstance(schedule, RelativeSchedule)
            and isinstance(cycle, TaskCycle)
            and self.schedule.schedule_id == schedule.schedule_id
            and self.schedule.household_id == schedule.household_id
            and self.schedule.definition_id == schedule.definition_id
            and self.schedule.created_at == schedule.created_at
            and self.cycle.completion_snapshot() == cycle.completion_snapshot()
        )


def successor_disposition(
    closure: RelativeClosure,
    current_cycle: TaskCycle | None,
    successor: TaskOccurrence | None,
    history: WorkHistory,
) -> SuccessorDisposition:
    """Plan only; the writer must recheck exact revisions and original consumer proof."""
    if (
        not isinstance(closure, RelativeClosure)
        or not isinstance(history, WorkHistory)
        or (
            current_cycle is not None
            and (
                not isinstance(current_cycle, TaskCycle)
                or not closure.matches_source(closure.schedule, current_cycle)
            )
        )
    ):
        raise InvalidInput("invalid_relative_invalidation")
    slot = closure.successor
    if successor is not None and (
        not isinstance(successor, TaskOccurrence)
        or slot is None
        or successor.occurrence_id != slot.occurrence_id
        or successor.household_id != closure.schedule.household_id
        or successor.definition_snapshot.definition_id != closure.schedule.definition_id
    ):
        raise InvalidInput("invalid_relative_invalidation")
    if closure.kind is not RelativeClosureKind.GENERATED:
        return SuccessorDisposition.CLOSED
    if current_cycle is None:
        return SuccessorDisposition.REVIEW
    if (
        current_cycle.closed_at is None
        and current_cycle.verification is not VerificationState.REJECTED
    ):
        return SuccessorDisposition.CURRENT
    if successor is None:
        return SuccessorDisposition.ABSENT
    if successor.state in (OccurrenceState.CANCELLED, OccurrenceState.SKIPPED):
        return SuccessorDisposition.RETAINED
    if (
        successor.state in (OccurrenceState.IN_PROGRESS, OccurrenceState.COMPLETED)
        or history is not WorkHistory.UNSTARTED
    ):
        return SuccessorDisposition.REVIEW
    return SuccessorDisposition.CANCEL


@dataclass(frozen=True, slots=True)
class RelativeEventOutcome:
    """Durable result for one admitted event, including non-effect decisions."""

    status: str
    schedule_id: str
    receipt: Receipt | None = None
    occurrence_id: str | None = None

    def __post_init__(self) -> None:
        validate_identifier(self.schedule_id)
        if self.occurrence_id is not None:
            validate_identifier(self.occurrence_id)
        if self.status in ("unrelated", "retired", "definition_inactive", "waiting_verification"):
            if self.receipt is not None or self.occurrence_id is not None:
                raise InvalidInput("invalid_relative_outcome")
            return
        if (
            self.status
            not in (
                "generated",
                "rejected",
                "reopened",
                "historical_absent",
                "cancel",
                "retained",
                "review",
                "absent",
            )
            or self.receipt is None
            or self.receipt.command.actor_id != MAINTENANCE_ACTOR
            or self.receipt.command.action
            not in (
                "recurrence.materialize",
                "recurrence.relative.close",
                "recurrence.relative.invalidate",
            )
            or not self._matches_receipt()
        ):
            raise InvalidInput("invalid_relative_outcome")

    def _matches_receipt(self) -> bool:
        receipt = cast(Receipt, self.receipt)
        result = receipt.result.decode()
        if not isinstance(result, dict) or result.get("occurrence_id") != self.occurrence_id:
            return False
        historical_absence = self.status == "historical_absent" and receipt.historical
        if receipt.command.action == "recurrence.relative.invalidate":
            disposition = result.get("disposition")
            return (
                self.occurrence_id is not None
                and disposition in ("cancel", "retained", "review", "absent")
                and (self.status == disposition or historical_absence)
                and result.get("closure_key") == receipt.command.key
            )
        proof = result.get("relative_closure")
        if not isinstance(proof, dict):
            return False
        schedule = proof.get("schedule")
        if not isinstance(schedule, dict) or schedule.get("schedule_id") != self.schedule_id:
            return False
        if receipt.command.action == "recurrence.materialize":
            successor = proof.get("successor")
            return (
                self.occurrence_id is not None
                and proof.get("kind") == "generated"
                and (self.status == "generated" or historical_absence)
                and result.get("schedule_id") == self.schedule_id
                and result.get("slot_key") == receipt.command.key
                and isinstance(successor, dict)
                and successor.get("slot_key") == receipt.command.key
                and successor.get("occurrence_id") == self.occurrence_id
            )
        return (
            self.occurrence_id is None
            and proof.get("kind") in ("rejected", "reopened", "historical_absent")
            and self.status == proof["kind"]
            and proof.get("key") == receipt.command.key
        )

    def matches_source(self, event: TaskLifecycleEvent, installation: Installation) -> bool:
        """Bind an effect receipt to its original cycle, including restored absent mappings."""
        if self.receipt is None:
            return True
        result = self.receipt.result.decode()
        proof = result.get("relative_closure")
        key = (
            result.get("closure_key")
            if self.receipt.command.action == "recurrence.relative.invalidate"
            else cast(JsonObject, proof).get("key")
        )
        return key == _cycle_key(
            installation,
            event.cycle.household_id,
            self.schedule_id,
            event.definition_id,
            event.cycle.occurrence_id,
            event.cycle.cycle_id,
        )
