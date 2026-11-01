"""Shared transaction-scoped task facts for commands and read-only planning."""

import json
from dataclasses import asdict
from typing import cast

from domus.application.ports import UnitOfWork
from domus.domain.errors import Conflict, StorageFailure
from domus.domain.storage import JsonDocument
from domus.domain.task_values import OccurrenceState, TaskRequirement, TaskRules
from domus.domain.tasks import TaskCycle, TaskDefinition, TaskOccurrence


def current_cycle(unit: UnitOfWork, work: TaskOccurrence, cycle_id: str) -> TaskCycle:
    if work.current_cycle_id != cycle_id:
        raise Conflict("task_cycle_conflict")
    cycle = unit.tasks.cycle(work.household_id, cycle_id)
    if (
        cycle is None
        or cycle.household_id != work.household_id
        or cycle.occurrence_id != work.occurrence_id
        or cycle.revision != work.current_cycle_revision
        or cycle.closed_at is not None
    ):
        raise StorageFailure("invalid_task_references")
    return cycle


def required_work(unit: UnitOfWork, work: TaskOccurrence) -> tuple[TaskRequirement, ...]:
    result = []
    for identity in sorted(set(work.prerequisite_ids) | set(work.required_subtask_ids)):
        required = unit.tasks.occurrence(work.household_id, identity)
        if required is None:
            raise StorageFailure("invalid_task_references")
        verification = None
        if required.state is OccurrenceState.COMPLETED:
            verification = current_cycle(
                unit, required, cast(str, required.current_cycle_id)
            ).verification
        result.append(TaskRequirement(identity, required.state, verification))
    return tuple(result)


def resolved_rules(unit: UnitOfWork, work: TaskOccurrence) -> tuple[TaskRules, int]:
    policy = unit.tasks.policy(work.household_id)
    if policy is None:
        raise StorageFailure("invalid_task_references")
    return work.definition_snapshot.overrides.resolve(policy.rules), policy.revision


def definition_result(value: TaskDefinition) -> JsonDocument:
    """Bounded command evidence uses reference facts; queries retain full binding snapshots."""
    result = asdict(value)
    del result["materials"]
    if value.materials:
        result["materials"] = [
            {
                "line_id": line.line_id,
                "reference_id": line.binding.reference_id,
                "binding_revision": line.binding.revision,
                "planned_quantity": line.planned_quantity.value,
            }
            for line in value.materials
        ]
    return JsonDocument(json.dumps(result, ensure_ascii=False))
