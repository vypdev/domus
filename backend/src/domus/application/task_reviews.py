"""Project immutable causes and manager decisions alongside the current source condition."""

from dataclasses import dataclass
from typing import cast

from domus.application.ports import UnitOfWork
from domus.application.task_authorization import recorded_request
from domus.application.task_facts import current_cycle
from domus.application.task_ports import TaskReviewEvidence
from domus.domain.errors import InvalidInput, NotFound, StorageFailure
from domus.domain.task_policy import requirements_satisfied
from domus.domain.task_reviews import (
    DependencyReviewCause,
    DependencyReviewState,
    dependency_review_cause,
    recorded_review,
    validate_review_interval,
)
from domus.domain.task_values import OccurrenceState, TaskRequirement, VerificationState
from domus.domain.tasks import TaskCycle, TaskOccurrence


@dataclass(frozen=True, slots=True)
class DependencyReviewAcknowledgement:
    operation_id: str
    recorded_by: str
    recorded_at: int
    reason: str


@dataclass(frozen=True, slots=True)
class DependencyReviewView:
    cause: DependencyReviewCause
    revision: int
    state: DependencyReviewState
    source_state: OccurrenceState
    source_verification: VerificationState | None
    source_satisfies_gate: bool
    acknowledgement: DependencyReviewAcknowledgement | None


def review_cycle(unit: UnitOfWork, work: TaskOccurrence, cycle_id: str) -> TaskCycle:
    cycle = unit.tasks.cycle(work.household_id, cycle_id)
    if cycle is None or cycle.occurrence_id != work.occurrence_id:
        raise NotFound("task_cycle_missing")
    return cycle


def review_items(
    unit: UnitOfWork, work: TaskOccurrence, cycle: TaskCycle, evidence: TaskReviewEvidence
) -> tuple[DependencyReviewView, ...]:
    """One snapshot per bounded page; outbox delivery never changes business review state."""
    try:
        recorded_request(evidence.completion)
        if evidence.closure is not None:
            recorded_request(evidence.closure)
        validate_review_interval(evidence.completion, evidence.closure, cycle)
        causes = {}
        for row in evidence.reopenings:
            recorded_request(row)
            raw = row.receipt.result.decode().get("cycle")
            if not isinstance(raw, dict):
                raise InvalidInput("invalid_dependency_review")
            source = unit.tasks.cycle(work.household_id, cast(str, raw.get("cycle_id")))
            if source is None:
                raise InvalidInput("invalid_dependency_review")
            cause = dependency_review_cause(
                evidence.completion, row, cycle, source, evidence.closure
            )
            if cause.source_operation_id in causes:
                raise InvalidInput("invalid_dependency_review")
            causes[cause.source_operation_id] = cause
        decisions = {}
        for row in evidence.acknowledgements:
            recorded_request(row)
            decision = recorded_review(row)
            key = decision.cause.source_operation_id
            if key in decisions or causes.get(key) != decision.cause:
                raise InvalidInput("invalid_dependency_review")
            decisions[key] = DependencyReviewAcknowledgement(
                row.receipt.operation_id,
                decision.recorded_by,
                decision.recorded_at,
                decision.reason,
            )
        result = []
        for key, cause in causes.items():
            source_work = unit.tasks.occurrence(work.household_id, cause.source_occurrence_id)
            if source_work is None:
                raise InvalidInput("invalid_dependency_review")
            verification = (
                current_cycle(
                    unit, source_work, cast(str, source_work.current_cycle_id)
                ).verification
                if source_work.state is OccurrenceState.COMPLETED
                else None
            )
            satisfied = requirements_satisfied(
                (TaskRequirement(source_work.occurrence_id, source_work.state, verification),),
                cycle.rules.dependency_gate,
            )
            acknowledgement = decisions.get(key)
            result.append(
                DependencyReviewView(
                    cause,
                    1 if acknowledgement is None else 2,
                    DependencyReviewState.PENDING
                    if acknowledgement is None
                    else DependencyReviewState.REVIEWED,
                    source_work.state,
                    verification,
                    satisfied,
                    acknowledgement,
                )
            )
        return tuple(result)
    except InvalidInput, TypeError, ValueError:
        raise StorageFailure("invalid_dependency_review") from None
