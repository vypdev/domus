"""Validate task graph, scope and historical snapshots before accepting a checkpoint."""

import sqlite3
from collections.abc import Callable

from domus.domain.errors import StorageFailure
from domus.domain.identity import HouseholdPolicy, Member
from domus.domain.task_policy import validate_dependency_graph
from domus.infrastructure.sqlite_tasks import SQLiteTasks


def _collect[T](
    page: Callable[[str | None], tuple[T, ...]], identity: Callable[[T], str]
) -> dict[str, T]:
    result: dict[str, T] = {}
    after: str | None = None
    while values := page(after):
        result.update((identity(value), value) for value in values)
        after = identity(values[-1])
    return result


def verify_task_records(
    connection: sqlite3.Connection,
    household_id: str,
    members: tuple[Member, ...],
    identity_policy: HouseholdPolicy | None,
) -> None:
    repository = SQLiteTasks(connection)
    policy = repository.policy(household_id)
    definitions = _collect(
        lambda after: repository.definitions(household_id, limit=101, after=after),
        lambda value: value.definition_id,
    )
    occurrences = _collect(
        lambda after: repository.occurrences(household_id, limit=101, after=after),
        lambda value: value.occurrence_id,
    )
    cycles = _collect(
        lambda after: repository.cycles(household_id, limit=101, after=after),
        lambda value: value.cycle_id,
    )
    if policy is None:
        if definitions or occurrences or cycles:
            raise StorageFailure("invalid_task_references")
        return
    if identity_policy is None or not members:
        raise StorageFailure("invalid_task_references")
    member_ids = {member.member_id for member in members}
    graph: dict[str, tuple[str, ...]] = {}
    for work in occurrences.values():
        original = work.definition_snapshot
        current = definitions.get(original.definition_id)
        if (
            current is None
            or original.created_at != current.created_at
            or original.revision > current.revision
            or (original.revision == current.revision and original != current)
            or any(member_id not in member_ids for member_id in work.assignee_ids)
        ):
            raise StorageFailure("invalid_task_references")
        graph[work.occurrence_id] = tuple(
            set(work.prerequisite_ids) | set(work.required_subtask_ids)
        )
        if work.current_cycle_id is not None:
            cycle = cycles.get(work.current_cycle_id)
            if (
                cycle is None
                or cycle.closed_at is not None
                or cycle.occurrence_id != work.occurrence_id
                or cycle.revision != work.current_cycle_revision
            ):
                raise StorageFailure("invalid_task_references")
    validate_dependency_graph(graph)
    for cycle in cycles.values():
        cycle_work = occurrences.get(cycle.occurrence_id)
        if (
            cycle_work is None
            or cycle.definition_revision != cycle_work.definition_snapshot.revision
            or cycle.recorded_at < cycle_work.created_at
            or cycle.task_policy_revision > policy.revision
            or cycle.identity_policy_revision > identity_policy.revision
            or cycle.recorded_by not in member_ids
            or any(performer.member_id not in member_ids for performer in cycle.performers)
            or (cycle.verified_by is not None and cycle.verified_by.member_id not in member_ids)
            or (cycle.closed_at is None and cycle_work.current_cycle_id != cycle.cycle_id)
        ):
            raise StorageFailure("invalid_task_references")
