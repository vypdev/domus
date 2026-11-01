"""Scoped task repositories with compare-and-swap writes and strict stored-header checks."""

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

from domus.application.task_ports import TaskRepository
from domus.domain.errors import Conflict, InvalidInput, StorageFailure
from domus.domain.storage import validate_identifier
from domus.domain.task_values import DefinitionState, OccurrenceState, VerificationState
from domus.domain.tasks import HouseholdTaskPolicy, TaskCycle, TaskDefinition, TaskOccurrence
from domus.infrastructure.sqlite_task_records import (
    cycle_document,
    definition_document,
    occurrence_document,
    policy_document,
    read_cycle,
    read_definition,
    read_occurrence,
    read_policy,
)


def _policy_headers(value: HouseholdTaskPolicy) -> dict[str, object]:
    return {"household_id": value.household_id, "revision": value.revision}


def _definition_headers(value: TaskDefinition) -> dict[str, object]:
    return {
        "definition_id": value.definition_id,
        "household_id": value.household_id,
        "revision": value.revision,
        "state": value.state.value,
    }


def _occurrence_headers(value: TaskOccurrence) -> dict[str, object]:
    return {
        "occurrence_id": value.occurrence_id,
        "household_id": value.household_id,
        "definition_id": value.definition_snapshot.definition_id,
        "revision": value.revision,
        "state": value.state.value,
        "current_cycle_id": value.current_cycle_id,
        "current_cycle_revision": value.current_cycle_revision,
    }


def _cycle_headers(value: TaskCycle) -> dict[str, object]:
    return {
        "cycle_id": value.cycle_id,
        "household_id": value.household_id,
        "occurrence_id": value.occurrence_id,
        "active_occurrence_id": value.occurrence_id if value.closed_at is None else None,
        "revision": value.revision,
        "closed_at": value.closed_at,
        "recorded_by": value.recorded_by,
        "verified_by": None if value.verified_by is None else value.verified_by.member_id,
    }


def _model[T](
    row: sqlite3.Row | None, read: Callable[[str], T], headers: Callable[[T], dict[str, object]]
) -> T | None:
    if row is None:
        return None
    value = read(row["document"])
    if any(
        type(row[key]) is not type(expected) or row[key] != expected
        for key, expected in headers(value).items()
    ):
        raise StorageFailure("invalid_task_record")
    return value


def _page(
    household_id: str, limit: int, after: str | None, key: str
) -> tuple[list[str], list[object]]:
    validate_identifier(household_id)
    if type(limit) is not int or not 1 <= limit <= 101:
        raise InvalidInput("invalid_page_size")
    where, parameters = ["household_id=?"], [cast(object, household_id)]
    if after is not None:
        validate_identifier(after)
        where.append(key + ">?")
        parameters.append(after)
    return where, parameters


def _immutable(previous: object | None, value: object, fields: tuple[str, ...]) -> None:
    if previous is not None and any(
        getattr(previous, field) != getattr(value, field) for field in fields
    ):
        raise Conflict("task_identity_conflict")


@dataclass
class SQLiteTasks(TaskRepository):
    """The enclosing unit owns begin/commit/rollback; these methods never commit independently."""

    connection: sqlite3.Connection

    def _write(
        self,
        table: str,
        identity: dict[str, str],
        headers: dict[str, object],
        document: str,
        revision: int,
        expected_revision: int,
    ) -> None:
        if type(expected_revision) is not int or not 0 <= expected_revision <= 2**63 - 1:
            raise InvalidInput("invalid_revision")
        if revision != expected_revision + 1:
            raise Conflict("revision_conflict")
        values = {**headers, "document": document}
        if expected_revision == 0:
            try:
                self.connection.execute(
                    f"INSERT INTO {table}({','.join(values)}) "
                    f"VALUES ({','.join('?' for _ in values)})",
                    tuple(values.values()),
                )
            except sqlite3.IntegrityError:
                raise Conflict("task_record_conflict") from None
        elif (
            self.connection.execute(
                f"UPDATE {table} SET {','.join(key + '=?' for key in values)} "
                f"WHERE {' AND '.join(key + '=?' for key in identity)} AND revision=?",
                (*values.values(), *identity.values(), expected_revision),
            ).rowcount
            != 1
        ):
            raise Conflict("revision_conflict")

    def policy(self, household_id: str) -> HouseholdTaskPolicy | None:
        validate_identifier(household_id)
        return _model(
            self.connection.execute(
                "SELECT * FROM task_policy WHERE household_id=?", (household_id,)
            ).fetchone(),
            read_policy,
            _policy_headers,
        )

    def save_policy(self, value: HouseholdTaskPolicy, expected_revision: int) -> None:
        self._write(
            "task_policy",
            {"household_id": value.household_id},
            _policy_headers(value),
            policy_document(value).encoded,
            value.revision,
            expected_revision,
        )

    def definition(self, household_id: str, definition_id: str) -> TaskDefinition | None:
        validate_identifier(household_id)
        validate_identifier(definition_id)
        return _model(
            self.connection.execute(
                "SELECT * FROM task_definitions WHERE household_id=? AND definition_id=?",
                (household_id, definition_id),
            ).fetchone(),
            read_definition,
            _definition_headers,
        )

    def save_definition(self, value: TaskDefinition, expected_revision: int) -> None:
        _immutable(self.definition(value.household_id, value.definition_id), value, ("created_at",))
        self._write(
            "task_definitions",
            {"household_id": value.household_id, "definition_id": value.definition_id},
            _definition_headers(value),
            definition_document(value).encoded,
            value.revision,
            expected_revision,
        )

    def definitions(
        self,
        household_id: str,
        *,
        limit: int = 25,
        after: str | None = None,
        state: DefinitionState | None = None,
    ) -> tuple[TaskDefinition, ...]:
        where, parameters = _page(household_id, limit, after, "definition_id")
        if state is not None:
            if not isinstance(state, DefinitionState):
                raise InvalidInput("invalid_task_query")
            where.append("state=?")
            parameters.append(state.value)
        rows = self.connection.execute(
            "SELECT * FROM task_definitions WHERE "
            + " AND ".join(where)
            + " ORDER BY definition_id LIMIT ?",
            (*parameters, limit),
        )
        return tuple(
            cast(TaskDefinition, _model(row, read_definition, _definition_headers)) for row in rows
        )

    def occurrence(self, household_id: str, occurrence_id: str) -> TaskOccurrence | None:
        validate_identifier(household_id)
        validate_identifier(occurrence_id)
        return _model(
            self.connection.execute(
                "SELECT * FROM task_occurrences WHERE household_id=? AND occurrence_id=?",
                (household_id, occurrence_id),
            ).fetchone(),
            read_occurrence,
            _occurrence_headers,
        )

    def save_occurrence(self, value: TaskOccurrence, expected_revision: int) -> None:
        _immutable(
            self.occurrence(value.household_id, value.occurrence_id),
            value,
            ("created_at", "definition_snapshot"),
        )
        self._write(
            "task_occurrences",
            {"household_id": value.household_id, "occurrence_id": value.occurrence_id},
            _occurrence_headers(value),
            occurrence_document(value).encoded,
            value.revision,
            expected_revision,
        )

    def occurrences(
        self,
        household_id: str,
        *,
        limit: int = 25,
        after: str | None = None,
        state: OccurrenceState | None = None,
        definition_id: str | None = None,
        assignee_id: str | None = None,
    ) -> tuple[TaskOccurrence, ...]:
        where, parameters = _page(household_id, limit, after, "occurrence_id")
        if state is not None:
            if not isinstance(state, OccurrenceState):
                raise InvalidInput("invalid_task_query")
            where.append("state=?")
            parameters.append(state.value)
        if definition_id is not None:
            validate_identifier(definition_id)
            where.append("definition_id=?")
            parameters.append(definition_id)
        if assignee_id is not None:
            validate_identifier(assignee_id)
            where.append(
                "EXISTS (SELECT 1 FROM json_each(task_occurrences.document,'$.assignee_ids') "
                "AS assigned WHERE assigned.value=?)"
            )
            parameters.append(assignee_id)
        rows = self.connection.execute(
            "SELECT * FROM task_occurrences WHERE "
            + " AND ".join(where)
            + " ORDER BY occurrence_id LIMIT ?",
            (*parameters, limit),
        )
        return tuple(
            cast(TaskOccurrence, _model(row, read_occurrence, _occurrence_headers)) for row in rows
        )

    def cycle(self, household_id: str, cycle_id: str) -> TaskCycle | None:
        validate_identifier(household_id)
        validate_identifier(cycle_id)
        return _model(
            self.connection.execute(
                "SELECT * FROM task_cycles WHERE household_id=? AND cycle_id=?",
                (household_id, cycle_id),
            ).fetchone(),
            read_cycle,
            _cycle_headers,
        )

    def save_cycle(self, value: TaskCycle, expected_revision: int) -> None:
        previous = self.cycle(value.household_id, value.cycle_id)
        _immutable(
            previous,
            value,
            (
                "occurrence_id",
                "recorded_by",
                "performers",
                "rules",
                "definition_revision",
                "task_policy_revision",
                "identity_policy_revision",
                "performed_at",
                "recorded_at",
            ),
        )
        if previous is not None:
            if previous.closed_at is not None:
                _immutable(previous, value, ("closed_at",))
            if previous.verification in (VerificationState.APPROVED, VerificationState.REJECTED):
                _immutable(
                    previous,
                    value,
                    ("verification", "verified_by", "verified_at", "verification_reason"),
                )
        self._write(
            "task_cycles",
            {"household_id": value.household_id, "cycle_id": value.cycle_id},
            _cycle_headers(value),
            cycle_document(value).encoded,
            value.revision,
            expected_revision,
        )

    def cycles(
        self,
        household_id: str,
        occurrence_id: str | None = None,
        *,
        limit: int = 25,
        after: str | None = None,
    ) -> tuple[TaskCycle, ...]:
        where, parameters = _page(household_id, limit, after, "cycle_id")
        if occurrence_id is not None:
            validate_identifier(occurrence_id)
            where.append("occurrence_id=?")
            parameters.append(occurrence_id)
        rows = self.connection.execute(
            "SELECT * FROM task_cycles WHERE " + " AND ".join(where) + " ORDER BY cycle_id LIMIT ?",
            (*parameters, limit),
        )
        return tuple(cast(TaskCycle, _model(row, read_cycle, _cycle_headers)) for row in rows)
