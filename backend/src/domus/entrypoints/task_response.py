"""Read DTOs flatten material value objects at the wire boundary, outside Domain."""

from dataclasses import dataclass
from typing import Annotated

from pydantic import Field

from domus.application.task_queries import TaskDetail as Detail
from domus.domain.task_material_values import MaterialBinding
from domus.domain.task_values import (
    DefinitionState,
    OccurrenceState,
    TaskContent,
    TaskOverrides,
    TaskRequirement,
    TaskRules,
)
from domus.domain.tasks import TaskCycle
from domus.domain.tasks import TaskDefinition as Definition


@dataclass(frozen=True, slots=True)
class MaterialLine:
    line_id: str
    binding: MaterialBinding
    planned_quantity: Annotated[
        str, Field(pattern=r"^(?:0|[1-9][0-9]{0,11})(?:\.[0-9]{0,5}[1-9])?$")
    ]


@dataclass(frozen=True, slots=True)
class TaskDefinition:
    definition_id: str
    household_id: str
    content: TaskContent
    created_at: int
    overrides: TaskOverrides = TaskOverrides()
    state: DefinitionState = DefinitionState.ACTIVE
    revision: int = 1
    materials: tuple[MaterialLine, ...] = ()


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


@dataclass(frozen=True, slots=True)
class TaskDetail:
    work: TaskOccurrence
    rules: TaskRules
    task_policy_revision: int
    requirements: tuple[TaskRequirement, ...]
    cycle: TaskCycle | None
    allowed_actions: tuple[str, ...]
    consumer_delivery: str = "unconfirmed"


def definition_response(value: Definition) -> TaskDefinition:
    return TaskDefinition(
        value.definition_id,
        value.household_id,
        value.content,
        value.created_at,
        value.overrides,
        value.state,
        value.revision,
        tuple(
            MaterialLine(line.line_id, line.binding, line.planned_quantity.value)
            for line in value.materials
        ),
    )


def detail_response(value: Detail) -> TaskDetail:
    work = value.work
    return TaskDetail(
        TaskOccurrence(
            work.occurrence_id,
            work.household_id,
            definition_response(work.definition_snapshot),
            work.created_at,
            work.state,
            work.revision,
            work.assignee_ids,
            work.prerequisite_ids,
            work.required_subtask_ids,
            work.due_at,
            work.current_cycle_id,
            work.current_cycle_revision,
            work.state_reason,
        ),
        value.rules,
        value.task_policy_revision,
        value.requirements,
        value.cycle,
        value.allowed_actions,
        value.consumer_delivery,
    )
