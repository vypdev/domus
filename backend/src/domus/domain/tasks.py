"""Revisioned task records and cycle-bound transitions without clocks, storage or grants."""

from dataclasses import dataclass, replace
from typing import Self

from domus.domain.errors import Conflict, Forbidden, InvalidInput
from domus.domain.identity import validate_revision
from domus.domain.storage import validate_identifier
from domus.domain.task_policy import (
    can_approve,
    next_definition_state,
    next_occurrence_state,
    reopened_state,
    require_completion_state,
    requirements_satisfied,
    verification_required,
)
from domus.domain.task_values import (
    DefinitionState,
    OccurrenceState,
    TaskContent,
    TaskOverrides,
    TaskPerformer,
    TaskRequirement,
    TaskRules,
    VerificationState,
    next_task_revision,
    validate_performers,
    validate_task_ids,
    validate_task_text,
    validate_task_time,
)


@dataclass(frozen=True, slots=True)
class HouseholdTaskPolicy:
    household_id: str
    rules: TaskRules
    revision: int = 1

    def __post_init__(self) -> None:
        validate_identifier(self.household_id)
        validate_revision(self.revision)
        if not isinstance(self.rules, TaskRules):
            raise InvalidInput("invalid_task_rules")

    def revise(self, rules: TaskRules) -> Self:
        if rules == self.rules:
            raise Conflict("task_unchanged")
        return replace(self, rules=rules, revision=next_task_revision(self.revision))


@dataclass(frozen=True, slots=True)
class TaskDefinition:
    definition_id: str
    household_id: str
    content: TaskContent
    created_at: int
    overrides: TaskOverrides = TaskOverrides()
    state: DefinitionState = DefinitionState.ACTIVE
    revision: int = 1

    def __post_init__(self) -> None:
        validate_identifier(self.definition_id)
        validate_identifier(self.household_id)
        validate_revision(self.revision)
        validate_task_time(self.created_at)
        if (
            not isinstance(self.content, TaskContent)
            or not isinstance(self.overrides, TaskOverrides)
            or not isinstance(self.state, DefinitionState)
        ):
            raise InvalidInput("invalid_task_definition")

    def revise(
        self, content: TaskContent, overrides: TaskOverrides, state: DefinitionState
    ) -> Self:
        candidate = replace(
            self,
            content=content,
            overrides=overrides,
            state=state,
            revision=next_task_revision(self.revision),
        )
        if self.state is DefinitionState.ARCHIVED:
            raise Conflict("task_transition_conflict")
        if (content, overrides, state) == (self.content, self.overrides, self.state):
            raise Conflict("task_unchanged")
        if state is not self.state:
            next_definition_state(self.state, state)
        return candidate

    def new_occurrence(
        self,
        occurrence_id: str,
        created_at: int,
        *,
        assignees: tuple[str, ...] = (),
        prerequisites: tuple[str, ...] = (),
        required_subtasks: tuple[str, ...] = (),
        due_at: int | None = None,
    ) -> TaskOccurrence:
        if self.state not in (DefinitionState.DRAFT, DefinitionState.ACTIVE):
            raise Conflict("task_definition_unavailable")
        if self.state is DefinitionState.DRAFT:
            if assignees:
                raise InvalidInput("invalid_task_assignment")
            state = OccurrenceState.DRAFT
        else:
            state = OccurrenceState.ASSIGNED if assignees else OccurrenceState.AVAILABLE
        return TaskOccurrence(
            occurrence_id,
            self.household_id,
            self,
            created_at,
            state=state,
            assignee_ids=assignees,
            prerequisite_ids=prerequisites,
            required_subtask_ids=required_subtasks,
            due_at=due_at,
        )


@dataclass(frozen=True, slots=True)
class TaskCycle:
    cycle_id: str
    household_id: str
    occurrence_id: str
    recorded_by: str
    performers: tuple[TaskPerformer, ...]
    rules: TaskRules
    definition_revision: int
    task_policy_revision: int
    identity_policy_revision: int
    performed_at: int
    recorded_at: int
    verification: VerificationState
    verified_by: TaskPerformer | None = None
    verified_at: int | None = None
    verification_reason: str = ""
    closed_at: int | None = None
    revision: int = 1

    def __post_init__(self) -> None:
        for value in (self.cycle_id, self.household_id, self.occurrence_id, self.recorded_by):
            validate_identifier(value)
        for revision in (
            self.revision,
            self.definition_revision,
            self.task_policy_revision,
            self.identity_policy_revision,
        ):
            validate_revision(revision)
        validate_performers(self.performers)
        validate_task_time(self.performed_at)
        validate_task_time(self.recorded_at)
        if (
            not isinstance(self.rules, TaskRules)
            or not isinstance(self.verification, VerificationState)
            or self.performed_at > self.recorded_at
        ):
            raise InvalidInput("invalid_task_cycle")
        required = verification_required(self.performers, self.rules)
        if (self.verification is VerificationState.NONE) == required:
            raise InvalidInput("invalid_task_cycle")
        validate_task_text(
            self.verification_reason,
            1000,
            required=self.verification is VerificationState.REJECTED,
            multiline=True,
        )
        latest = self.recorded_at
        if self.verification in (VerificationState.APPROVED, VerificationState.REJECTED):
            if not isinstance(self.verified_by, TaskPerformer) or self.verified_at is None:
                raise InvalidInput("invalid_task_cycle")
            validate_task_time(self.verified_at)
            if self.verified_at < self.recorded_at or not can_approve(
                self.verified_by,
                self.performers,
                independent=not self.rules.adult_performer_may_approve,
            ):
                raise InvalidInput("invalid_task_cycle")
            latest = self.verified_at
        elif (
            self.verified_by is not None
            or self.verified_at is not None
            or self.verification_reason != ""
        ):
            raise InvalidInput("invalid_task_cycle")
        if self.closed_at is not None:
            validate_task_time(self.closed_at)
            if self.closed_at < latest:
                raise InvalidInput("invalid_task_cycle")

    @classmethod
    def record(
        cls,
        cycle_id: str,
        household_id: str,
        occurrence_id: str,
        *,
        recorded_by: str,
        performers: tuple[TaskPerformer, ...],
        rules: TaskRules,
        definition_revision: int,
        task_policy_revision: int,
        identity_policy_revision: int,
        performed_at: int,
        recorded_at: int,
    ) -> Self:
        return cls(
            cycle_id,
            household_id,
            occurrence_id,
            recorded_by,
            performers,
            rules,
            definition_revision,
            task_policy_revision,
            identity_policy_revision,
            performed_at,
            recorded_at,
            VerificationState.PENDING
            if verification_required(performers, rules)
            else VerificationState.NONE,
        )

    def verify(
        self, decision: VerificationState, verifier: TaskPerformer, now: int, reason: str = ""
    ) -> Self:
        if self.closed_at is not None or self.verification is not VerificationState.PENDING:
            raise Conflict("task_cycle_not_pending")
        if (
            not isinstance(decision, VerificationState)
            or decision not in (VerificationState.APPROVED, VerificationState.REJECTED)
            or not isinstance(verifier, TaskPerformer)
        ):
            raise InvalidInput("invalid_task_verification")
        if not can_approve(
            verifier, self.performers, independent=not self.rules.adult_performer_may_approve
        ):
            raise Forbidden("task_approval_denied")
        return replace(
            self,
            verification=decision,
            verified_by=verifier,
            verified_at=now,
            verification_reason=reason,
            revision=next_task_revision(self.revision),
        )

    def close(self, now: int) -> Self:
        if self.closed_at is not None:
            raise Conflict("task_cycle_closed")
        return replace(self, closed_at=now, revision=next_task_revision(self.revision))


@dataclass(frozen=True, slots=True)
class TaskOccurrence:
    occurrence_id: str
    household_id: str
    definition_snapshot: TaskDefinition
    created_at: int
    state: OccurrenceState = OccurrenceState.AVAILABLE
    revision: int = 1
    assignee_ids: tuple[str, ...] = ()
    prerequisite_ids: tuple[str, ...] = ()
    required_subtask_ids: tuple[str, ...] = ()
    due_at: int | None = None
    current_cycle_id: str | None = None
    current_cycle_revision: int | None = None
    state_reason: str = ""

    def __post_init__(self) -> None:
        validate_identifier(self.occurrence_id)
        validate_identifier(self.household_id)
        validate_revision(self.revision)
        validate_task_time(self.created_at)
        if (
            not isinstance(self.definition_snapshot, TaskDefinition)
            or self.definition_snapshot.household_id != self.household_id
            or self.definition_snapshot.state not in (DefinitionState.DRAFT, DefinitionState.ACTIVE)
            or self.created_at < self.definition_snapshot.created_at
            or not isinstance(self.state, OccurrenceState)
        ):
            raise InvalidInput("invalid_task_occurrence")
        for values in (self.assignee_ids, self.prerequisite_ids, self.required_subtask_ids):
            validate_task_ids(values)
        if self.occurrence_id in (*self.prerequisite_ids, *self.required_subtask_ids):
            raise InvalidInput("invalid_task_dependency")
        if self.due_at is not None:
            validate_task_time(self.due_at)
        if self.current_cycle_id is not None:
            validate_identifier(self.current_cycle_id)
        if self.current_cycle_revision is not None:
            validate_revision(self.current_cycle_revision)
        completed = self.state is OccurrenceState.COMPLETED
        if (
            completed != (self.current_cycle_id is not None)
            or completed != (self.current_cycle_revision is not None)
            or (self.state is OccurrenceState.AVAILABLE and self.assignee_ids)
            or (
                self.state in (OccurrenceState.ASSIGNED, OccurrenceState.IN_PROGRESS)
                and not self.assignee_ids
            )
            or (self.state is OccurrenceState.DRAFT and self.assignee_ids)
        ):
            raise InvalidInput("invalid_task_occurrence")
        validate_task_text(
            self.state_reason,
            1000,
            required=self.state
            in (OccurrenceState.BLOCKED, OccurrenceState.CANCELLED, OccurrenceState.SKIPPED),
            multiline=True,
        )

    def assign(self, assignees: tuple[str, ...]) -> Self:
        validate_task_ids(assignees)
        if self.state not in (
            OccurrenceState.AVAILABLE,
            OccurrenceState.ASSIGNED,
            OccurrenceState.IN_PROGRESS,
            OccurrenceState.BLOCKED,
        ):
            raise Conflict("task_transition_conflict")
        if assignees == self.assignee_ids:
            raise Conflict("task_unchanged")
        if self.state is OccurrenceState.IN_PROGRESS and not assignees:
            raise InvalidInput("invalid_task_assignment")
        state = self.state
        if state in (OccurrenceState.AVAILABLE, OccurrenceState.ASSIGNED):
            state = OccurrenceState.ASSIGNED if assignees else OccurrenceState.AVAILABLE
        return replace(
            self,
            assignee_ids=assignees,
            state=state,
            revision=next_task_revision(self.revision),
            state_reason=self.state_reason if state is OccurrenceState.BLOCKED else "",
        )

    def transition(self, target: OccurrenceState, reason: str = "") -> Self:
        state = next_occurrence_state(self.state, target, self.assignee_ids, reason)
        return replace(
            self, state=state, state_reason=reason, revision=next_task_revision(self.revision)
        )

    def complete(self, cycle: TaskCycle, *, requirements: tuple[TaskRequirement, ...]) -> Self:
        require_completion_state(self.state)
        if not isinstance(cycle, TaskCycle):
            raise InvalidInput("invalid_task_cycle")
        satisfied = requirements_satisfied(requirements, cycle.rules.dependency_gate)
        expected = set(self.prerequisite_ids) | set(self.required_subtask_ids)
        if {item.occurrence_id for item in requirements} != expected:
            raise InvalidInput("invalid_task_requirement")
        if not satisfied:
            raise Conflict("task_dependencies_incomplete")
        self._cycle_scope(cycle)
        return replace(
            self,
            state=OccurrenceState.COMPLETED,
            state_reason="",
            current_cycle_id=cycle.cycle_id,
            current_cycle_revision=cycle.revision,
            revision=next_task_revision(self.revision),
        )

    def _cycle_scope(self, cycle: TaskCycle) -> None:
        if (
            cycle.household_id != self.household_id
            or cycle.occurrence_id != self.occurrence_id
            or cycle.definition_revision != self.definition_snapshot.revision
            or cycle.closed_at is not None
            or cycle.recorded_at < self.created_at
        ):
            raise InvalidInput("invalid_task_cycle")

    def _current_cycle(self, cycle: TaskCycle) -> None:
        if (
            not isinstance(cycle, TaskCycle)
            or self.state is not OccurrenceState.COMPLETED
            or self.current_cycle_id != cycle.cycle_id
            or self.current_cycle_revision != cycle.revision
        ):
            raise InvalidInput("invalid_task_cycle")
        self._cycle_scope(cycle)

    def verify(
        self,
        cycle: TaskCycle,
        decision: VerificationState,
        verifier: TaskPerformer,
        now: int,
        reason: str = "",
    ) -> tuple[Self, TaskCycle]:
        self._current_cycle(cycle)
        updated = cycle.verify(decision, verifier, now, reason)
        return replace(
            self,
            current_cycle_revision=updated.revision,
            revision=next_task_revision(self.revision),
        ), updated

    def reopen(self, cycle: TaskCycle, now: int, reason: str) -> tuple[Self, TaskCycle]:
        state = reopened_state(self.state, self.assignee_ids)
        self._current_cycle(cycle)
        validate_task_text(reason, 1000, required=True, multiline=True)
        closed = cycle.close(now)
        return replace(
            self,
            state=state,
            state_reason=reason,
            current_cycle_id=None,
            current_cycle_revision=None,
            revision=next_task_revision(self.revision),
        ), closed
