"""Original task lifecycle evidence and immutable source identities for owning consumers."""

import hashlib
import json
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import cast

from domus.domain.errors import InvalidInput
from domus.domain.identity import validate_revision
from domus.domain.restoration import OperationEvidence
from domus.domain.storage import Installation, JsonDocument, JsonObject, validate_identifier
from domus.domain.task_values import (
    TaskPerformer,
    VerificationState,
    validate_task_ids,
    validate_task_text,
    validate_task_time,
)
from domus.domain.tasks import TaskCycle, TaskOccurrence


class TaskEventKind(StrEnum):
    COMPLETED = "task.completed"
    VERIFIED = "task.verified"
    REOPENED = "task.reopened"


def _event_cycle(kind: TaskEventKind, value: TaskCycle) -> TaskCycle:
    original = TaskCycle.record(
        value.cycle_id,
        value.household_id,
        value.occurrence_id,
        recorded_by=value.recorded_by,
        performers=value.performers,
        rules=value.rules,
        definition_revision=value.definition_revision,
        task_policy_revision=value.task_policy_revision,
        identity_policy_revision=value.identity_policy_revision,
        performed_at=value.performed_at,
        recorded_at=value.recorded_at,
    )
    completed = original
    if value.verification in (VerificationState.APPROVED, VerificationState.REJECTED):
        original = original.verify(
            value.verification,
            cast(TaskPerformer, value.verified_by),
            cast(int, value.verified_at),
            value.verification_reason,
        )
    verified = original
    if value.closed_at is not None:
        original = original.close(value.closed_at)
    if original != value:
        raise InvalidInput("invalid_task_event")
    if kind is TaskEventKind.COMPLETED:
        return completed
    if kind is TaskEventKind.VERIFIED:
        if verified.verification not in (VerificationState.APPROVED, VerificationState.REJECTED):
            raise InvalidInput("invalid_task_event")
        return verified
    if value.closed_at is None:
        raise InvalidInput("invalid_task_event")
    return original


@dataclass(frozen=True, slots=True)
class TaskLifecycleEvent:
    installation: Installation
    event_id: str
    position: int
    kind: TaskEventKind
    definition_id: str
    occurrence_revision: int
    cycle: TaskCycle
    occurred_at: int
    version: int = 1

    def __post_init__(self) -> None:
        if (
            not isinstance(self.installation, Installation)
            or not isinstance(self.kind, TaskEventKind)
            or not isinstance(self.cycle, TaskCycle)
            or type(self.version) is not int
            or self.version != 1
        ):
            raise InvalidInput("invalid_task_event")
        validate_identifier(self.event_id)
        validate_identifier(self.definition_id)
        validate_revision(self.position)
        validate_revision(self.occurrence_revision)
        validate_task_time(self.occurred_at)
        latest = (
            self.cycle.closed_at
            if self.cycle.closed_at is not None
            else self.cycle.verified_at
            if self.cycle.verified_at is not None
            else self.cycle.recorded_at
        )
        if self.occurred_at < latest or self.cycle != _event_cycle(self.kind, self.cycle):
            raise InvalidInput("invalid_task_event")

    def _key(self, *, event: bool) -> str:
        value = {
            "version": 1,
            "instance": self.installation.instance_id,
            "channel": self.installation.channel,
            "household": self.cycle.household_id,
        }
        if event:
            value["event"] = self.event_id
        else:
            value["occurrence"] = self.cycle.occurrence_id
            value["cycle"] = self.cycle.cycle_id
        return hashlib.sha256(JsonDocument.from_value(value).encoded.encode()).hexdigest()

    @property
    def event_key(self) -> str:
        return self._key(event=True)

    @property
    def cycle_key(self) -> str:
        return self._key(event=False)

    @property
    def points_eligible(self) -> bool:
        return self.kind is not TaskEventKind.REOPENED and self.cycle.verification in (
            VerificationState.NONE,
            VerificationState.APPROVED,
        )

    @property
    def closes_awards(self) -> bool:
        return (
            self.kind is TaskEventKind.REOPENED
            or self.cycle.verification is VerificationState.REJECTED
        )


def recorded_dependencies(result: JsonObject) -> tuple[tuple[str, ...], tuple[str, ...]]:
    occurrence_id = cast(str, result.get("occurrence_id"))
    validate_identifier(occurrence_id)
    values = []
    for name in ("prerequisite_ids", "required_subtask_ids"):
        raw = result.get(name)
        if not isinstance(raw, list):
            raise InvalidInput("invalid_dependency_review")
        identities = tuple(cast(list[str], raw))
        validate_task_ids(identities)
        if occurrence_id in identities:
            raise InvalidInput("invalid_dependency_review")
        values.append(identities)
    return values[0], values[1]


def _cycle_snapshot(value: TaskCycle) -> JsonDocument:
    return JsonDocument(json.dumps(asdict(value)))


def operation_request(evidence: OperationEvidence) -> JsonObject:
    value = evidence.audit.detail.decode().get("request")
    if not isinstance(value, dict):
        raise InvalidInput("invalid_dependency_review")
    return value


def _root(evidence: OperationEvidence, cycle: TaskCycle, action: str) -> JsonObject:
    result, request = evidence.receipt.result.decode(), operation_request(evidence)
    expected = cast(int, request.get("expected_revision"))
    validate_revision(expected)
    validate_revision(cast(int, result.get("revision")))
    validate_identifier(cast(str, result.get("definition_id")))
    actual = {
        name: result.get(name) for name in ("occurrence_id", "definition_revision", "revision")
    }
    wanted = {
        "occurrence_id": cycle.occurrence_id,
        "definition_revision": cycle.definition_revision,
        "revision": expected + 1,
    }
    if (
        evidence.receipt.command.action != action
        or evidence.receipt.command.household_id != cycle.household_id
        or request.get("occurrence_id") != cycle.occurrence_id
        or JsonDocument.from_value(actual) != JsonDocument.from_value(wanted)
    ):
        raise InvalidInput("invalid_dependency_review")
    return result


def validate_completion(evidence: OperationEvidence, cycle: TaskCycle) -> JsonObject:
    result = _root(evidence, cycle, "task.complete")
    request = operation_request(evidence)
    original = TaskCycle.record(
        cycle.cycle_id,
        cycle.household_id,
        cycle.occurrence_id,
        recorded_by=cycle.recorded_by,
        performers=cycle.performers,
        rules=cycle.rules,
        definition_revision=cycle.definition_revision,
        task_policy_revision=cycle.task_policy_revision,
        identity_policy_revision=cycle.identity_policy_revision,
        performed_at=cycle.performed_at,
        recorded_at=cycle.recorded_at,
    )
    if (
        result.get("state") != "completed"
        or JsonDocument.from_value({"cycle": result.get("cycle")})
        != JsonDocument.from_value({"cycle": _cycle_snapshot(original).decode()})
        or JsonDocument.from_value(
            {name: request.get(name) for name in ("performer_ids", "performed_at")}
        )
        != JsonDocument.from_value(
            {
                "performer_ids": [v.member_id for v in cycle.performers],
                "performed_at": cycle.performed_at,
            }
        )
    ):
        raise InvalidInput("invalid_dependency_review")
    recorded_dependencies(result)
    return result


def validate_reopening(evidence: OperationEvidence, cycle: TaskCycle) -> JsonObject:
    result = _root(evidence, cycle, "task.reopen")
    request = operation_request(evidence)
    reason = cast(str, request.get("reason"))
    validate_task_text(reason, 1000, required=True, multiline=True)
    assignees = result.get("assignee_ids")
    if not isinstance(assignees, list):
        raise InvalidInput("invalid_dependency_review")
    validate_task_ids(tuple(cast(list[str], assignees)))
    if (
        cycle.closed_at is None
        or request.get("cycle_id") != cycle.cycle_id
        or result.get("compensates_cycle_id") != cycle.cycle_id
        or result.get("dependency_review_required") is not True
        or result.get("state") != ("assigned" if assignees else "available")
        or result.get("state_reason") != reason
        or JsonDocument.from_value({"cycle": result.get("cycle")})
        != JsonDocument.from_value({"cycle": _cycle_snapshot(cycle).decode()})
    ):
        raise InvalidInput("invalid_dependency_review")
    return result


def lifecycle_event(
    evidence: OperationEvidence, work: TaskOccurrence, cycle: TaskCycle, installation: Installation
) -> TaskLifecycleEvent:
    action = evidence.receipt.command.action
    try:
        kind = {
            "task.complete": TaskEventKind.COMPLETED,
            "task.verify": TaskEventKind.VERIFIED,
            "task.reopen": TaskEventKind.REOPENED,
        }[action]
    except KeyError:
        raise InvalidInput("invalid_task_event") from None
    snapshot = _event_cycle(kind, cycle)
    if kind is TaskEventKind.COMPLETED:
        result = validate_completion(evidence, cycle)
    elif kind is TaskEventKind.REOPENED:
        result = validate_reopening(evidence, cycle)
    else:
        result, request = _root(evidence, cycle, "task.verify"), operation_request(evidence)
        if (
            request.get("cycle_id") != cycle.cycle_id
            or request.get("decision") != snapshot.verification.value
            or request.get("reason") != snapshot.verification_reason
            or result.get("state") != "completed"
            or JsonDocument.from_value({"cycle": result.get("cycle")})
            != JsonDocument.from_value({"cycle": _cycle_snapshot(snapshot).decode()})
        ):
            raise InvalidInput("invalid_task_event")
    if (
        cycle.household_id != work.household_id
        or cycle.occurrence_id != work.occurrence_id
        or result.get("definition_id") != work.definition_snapshot.definition_id
    ):
        raise InvalidInput("invalid_task_event")
    return TaskLifecycleEvent(
        installation,
        evidence.receipt.operation_id,
        evidence.position,
        kind,
        work.definition_snapshot.definition_id,
        cast(int, result["revision"]),
        snapshot,
        evidence.receipt.created_at,
    )
