"""Task persistence and opaque pagination contracts expose domain facts and bounded reads."""

from dataclasses import dataclass
from typing import Protocol

from domus.domain.restoration import OperationEvidence, RetainedOperation
from domus.domain.storage import JsonDocument
from domus.domain.task_reviews import DependencyReviewState
from domus.domain.task_values import DefinitionState, OccurrenceState
from domus.domain.tasks import HouseholdTaskPolicy, TaskCycle, TaskDefinition, TaskOccurrence


class TaskCursors(Protocol):
    def encode(self, binding: JsonDocument, after: str) -> str: ...
    def decode(self, binding: JsonDocument, token: str) -> str: ...


@dataclass(frozen=True, slots=True)
class TaskReviewEvidence:
    completion: OperationEvidence
    closure: OperationEvidence | None
    reopenings: tuple[OperationEvidence, ...]
    acknowledgements: tuple[OperationEvidence, ...] = ()


class TaskRepository(Protocol):
    def review_evidence(
        self,
        household_id: str,
        occurrence_id: str,
        cycle_id: str,
        *,
        limit: int = 25,
        after: int = 0,
        state: DependencyReviewState | None = None,
        source_operation_id: str | None = None,
    ) -> TaskReviewEvidence: ...

    def history(
        self, household_id: str, occurrence_id: str, *, limit: int = 25, after: int = 0
    ) -> tuple[RetainedOperation, ...]: ...
    def operation(
        self, household_id: str, actor_id: str, operation_id: str
    ) -> RetainedOperation | None: ...
    def policy(self, household_id: str) -> HouseholdTaskPolicy | None: ...
    def save_policy(self, value: HouseholdTaskPolicy, expected_revision: int) -> None: ...
    def definition(self, household_id: str, definition_id: str) -> TaskDefinition | None: ...
    def save_definition(self, value: TaskDefinition, expected_revision: int) -> None: ...
    def definitions(
        self,
        household_id: str,
        *,
        limit: int = 25,
        after: str | None = None,
        state: DefinitionState | None = None,
    ) -> tuple[TaskDefinition, ...]: ...
    def occurrence(self, household_id: str, occurrence_id: str) -> TaskOccurrence | None: ...
    def save_occurrence(self, value: TaskOccurrence, expected_revision: int) -> None: ...
    def occurrences(
        self,
        household_id: str,
        *,
        limit: int = 25,
        after: str | None = None,
        state: OccurrenceState | None = None,
        definition_id: str | None = None,
        assignee_id: str | None = None,
    ) -> tuple[TaskOccurrence, ...]: ...
    def cycle(self, household_id: str, cycle_id: str) -> TaskCycle | None: ...
    def save_cycle(self, value: TaskCycle, expected_revision: int) -> None: ...
    def cycles(
        self,
        household_id: str,
        occurrence_id: str | None = None,
        *,
        limit: int = 25,
        after: str | None = None,
    ) -> tuple[TaskCycle, ...]: ...
