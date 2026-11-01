"""Causal dependency facts use durable positions; they never change completed work."""

import hashlib
import json
from dataclasses import asdict, dataclass, fields
from enum import StrEnum
from typing import cast

from domus.domain.errors import InvalidInput
from domus.domain.identity import validate_revision
from domus.domain.restoration import OperationEvidence
from domus.domain.storage import JsonDocument, JsonObject, validate_identifier
from domus.domain.task_events import (
    operation_request,
    recorded_dependencies,
    validate_completion,
    validate_reopening,
)
from domus.domain.task_values import validate_task_text, validate_task_time
from domus.domain.tasks import TaskCycle


class DependencyRelationship(StrEnum):
    PREREQUISITE = "prerequisite"
    REQUIRED_SUBTASK = "required_subtask"


class DependencyReviewState(StrEnum):
    PENDING = "pending"
    REVIEWED = "reviewed"


@dataclass(frozen=True, slots=True)
class DependencyReviewCause:
    household_id: str
    dependent_occurrence_id: str
    dependent_cycle_id: str
    source_occurrence_id: str
    source_cycle_id: str
    source_cycle_revision: int
    source_occurrence_revision: int
    source_operation_id: str
    source_position: int
    completion_position: int
    created_at: int
    relationships: tuple[DependencyRelationship, ...]
    reason: str

    def __post_init__(self) -> None:
        for value in (
            self.household_id,
            self.dependent_occurrence_id,
            self.dependent_cycle_id,
            self.source_occurrence_id,
            self.source_cycle_id,
            self.source_operation_id,
        ):
            validate_identifier(value)
        for revision in (
            self.source_cycle_revision,
            self.source_occurrence_revision,
            self.source_position,
            self.completion_position,
        ):
            validate_revision(revision)
        validate_task_time(self.created_at)
        validate_task_text(self.reason, 1000, required=True, multiline=True)
        if (
            self.source_occurrence_id == self.dependent_occurrence_id
            or self.source_cycle_id == self.dependent_cycle_id
            or self.source_position <= self.completion_position
            or self.relationships
            not in (
                (DependencyRelationship.PREREQUISITE,),
                (DependencyRelationship.REQUIRED_SUBTASK,),
                (DependencyRelationship.PREREQUISITE, DependencyRelationship.REQUIRED_SUBTASK),
            )
            or any(not isinstance(value, DependencyRelationship) for value in self.relationships)
        ):
            raise InvalidInput("invalid_dependency_review")

    @property
    def cause_id(self) -> str:
        key = JsonDocument.from_value(
            {
                "version": 1,
                "household_id": self.household_id,
                "cycle_id": self.dependent_cycle_id,
                "source_operation_id": self.source_operation_id,
            }
        )
        return "review_" + hashlib.sha256(key.encoded.encode()).hexdigest()


def dependency_review_cause(
    completion: OperationEvidence,
    reopening: OperationEvidence,
    dependent: TaskCycle,
    source: TaskCycle,
    closure: OperationEvidence | None,
) -> DependencyReviewCause:
    completed = validate_review_interval(completion, closure, dependent)
    reopened = validate_reopening(reopening, source)
    prerequisites, subtasks = recorded_dependencies(completed)
    relationships = tuple(
        kind
        for kind, identities in (
            (DependencyRelationship.PREREQUISITE, prerequisites),
            (DependencyRelationship.REQUIRED_SUBTASK, subtasks),
        )
        if source.occurrence_id in identities
    )
    if dependent.household_id != source.household_id or (
        closure is not None and reopening.position >= closure.position
    ):
        raise InvalidInput("invalid_dependency_review")
    return DependencyReviewCause(
        dependent.household_id,
        dependent.occurrence_id,
        dependent.cycle_id,
        source.occurrence_id,
        source.cycle_id,
        source.revision,
        cast(int, reopened["revision"]),
        reopening.receipt.operation_id,
        reopening.position,
        completion.position,
        cast(int, source.closed_at),
        relationships,
        cast(str, reopened["state_reason"]),
    )


def validate_review_interval(
    completion: OperationEvidence, closure: OperationEvidence | None, dependent: TaskCycle
) -> JsonObject:
    result = validate_completion(completion, dependent)
    if (closure is None) != (dependent.closed_at is None):
        raise InvalidInput("invalid_dependency_review")
    if closure is not None:
        validate_reopening(closure, dependent)
        if closure.position <= completion.position:
            raise InvalidInput("invalid_dependency_review")
    return result


@dataclass(frozen=True, slots=True)
class DependencyReviewDecision:
    cause: DependencyReviewCause
    recorded_by: str
    recorded_at: int
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.cause, DependencyReviewCause):
            raise InvalidInput("invalid_dependency_review")
        validate_identifier(self.recorded_by)
        validate_task_time(self.recorded_at)
        validate_task_text(self.reason, 1000, required=True, multiline=True)
        if self.recorded_at < self.cause.created_at:
            raise InvalidInput("invalid_dependency_review")

    def document(self) -> JsonDocument:
        return JsonDocument(json.dumps(asdict(self)))


def recorded_review(evidence: OperationEvidence) -> DependencyReviewDecision:
    """Decode original scope and reason; stored reviewer facts never grant current authority."""
    result, request = evidence.receipt.result.decode(), operation_request(evidence)
    raw = result.get("review")
    if not isinstance(raw, dict) or set(raw) != {
        item.name for item in fields(DependencyReviewDecision)
    }:
        raise InvalidInput("invalid_dependency_review")
    cause = raw["cause"]
    if not isinstance(cause, dict) or set(cause) != {
        item.name for item in fields(DependencyReviewCause)
    }:
        raise InvalidInput("invalid_dependency_review")
    relationships = cause["relationships"]
    if not isinstance(relationships, list):
        raise InvalidInput("invalid_dependency_review")
    decoded = DependencyReviewCause(
        cast(str, cause["household_id"]),
        cast(str, cause["dependent_occurrence_id"]),
        cast(str, cause["dependent_cycle_id"]),
        cast(str, cause["source_occurrence_id"]),
        cast(str, cause["source_cycle_id"]),
        cast(int, cause["source_cycle_revision"]),
        cast(int, cause["source_occurrence_revision"]),
        cast(str, cause["source_operation_id"]),
        cast(int, cause["source_position"]),
        cast(int, cause["completion_position"]),
        cast(int, cause["created_at"]),
        tuple(DependencyRelationship(cast(str, value)) for value in relationships),
        cast(str, cause["reason"]),
    )
    decision = DependencyReviewDecision(
        decoded,
        cast(str, raw["recorded_by"]),
        cast(int, raw["recorded_at"]),
        cast(str, raw["reason"]),
    )
    expected = {
        "occurrence_id": decision.cause.dependent_occurrence_id,
        "expected_revision": 1,
        "cycle_id": decision.cause.dependent_cycle_id,
        "source_operation_id": decision.cause.source_operation_id,
        "reason": decision.reason,
    }
    cycle = result.get("cycle")
    if (
        evidence.receipt.command.action != "task.dependency.review"
        or evidence.receipt.command.household_id != decision.cause.household_id
        or result.get("occurrence_id") != decision.cause.dependent_occurrence_id
        or not isinstance(cycle, dict)
        or cycle.get("cycle_id") != decision.cause.dependent_cycle_id
        or cycle.get("household_id") != decision.cause.household_id
        or cycle.get("occurrence_id") != decision.cause.dependent_occurrence_id
        or JsonDocument.from_value(request) != JsonDocument.from_value(expected)
        or evidence.position <= decision.cause.source_position
        or evidence.receipt.created_at < decision.recorded_at
    ):
        raise InvalidInput("invalid_dependency_review")
    return decision
