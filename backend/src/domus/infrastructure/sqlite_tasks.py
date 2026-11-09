"""Scoped task repositories with compare-and-swap writes and strict stored-header checks."""

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

from domus.application.task_ports import TaskRepository, TaskReviewEvidence
from domus.domain.errors import Conflict, InvalidInput, StorageFailure
from domus.domain.restoration import OperationEvidence, RetainedOperation
from domus.domain.storage import validate_identifier
from domus.domain.task_events import TaskSourceRecord
from domus.domain.task_reviews import DependencyReviewState
from domus.domain.task_values import (
    DefinitionState,
    MissedOccurrencePolicy,
    MissedOccurrenceSettings,
    OccurrenceState,
    VerificationState,
)
from domus.domain.tasks import HouseholdTaskPolicy, TaskCycle, TaskDefinition, TaskOccurrence
from domus.infrastructure.sqlite_task_history import SQLiteTaskHistory
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
from domus.infrastructure.sqlite_task_reviews import SQLiteTaskReviews
from domus.infrastructure.sqlite_task_schema import MISSED_OCCURRENCE_TABLE


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
    record_version: int = 2

    def lifecycle_sources(
        self, household_id: str, *, limit: int = 100, after: int = 0
    ) -> tuple[TaskSourceRecord, ...]:
        return SQLiteTaskHistory(self.connection).lifecycle_sources(
            household_id, limit=limit, after=after
        )

    def lifecycle_events(
        self, household_id: str, *, limit: int = 25, after: int = 0
    ) -> tuple[OperationEvidence, ...]:
        return SQLiteTaskHistory(self.connection).lifecycle_events(
            household_id, limit=limit, after=after
        )

    def restored_cycle_closure(self, household_id: str, cycle_id: str) -> TaskSourceRecord | None:
        return SQLiteTaskHistory(self.connection).restored_cycle_closure(household_id, cycle_id)

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
    ) -> TaskReviewEvidence:
        return SQLiteTaskReviews(self.connection).read(
            household_id,
            occurrence_id,
            cycle_id,
            limit=limit,
            after=after,
            state=state,
            source_operation_id=source_operation_id,
        )

    def history(
        self, household_id: str, occurrence_id: str, *, limit: int = 25, after: int = 0
    ) -> tuple[RetainedOperation, ...]:
        return SQLiteTaskHistory(self.connection).history(
            household_id, occurrence_id, limit=limit, after=after
        )

    def latest_reschedule(self, household_id: str, occurrence_id: str) -> RetainedOperation | None:
        return SQLiteTaskHistory(self.connection).latest_reschedule(household_id, occurrence_id)

    def operation(
        self, household_id: str, actor_id: str, operation_id: str
    ) -> RetainedOperation | None:
        return SQLiteTaskHistory(self.connection).operation(household_id, actor_id, operation_id)

    def _write(
        self,
        table: str,
        identity: dict[str, str],
        headers: dict[str, object],
        document: str | None,
        revision: int,
        expected_revision: int,
    ) -> None:
        if type(expected_revision) is not int or not 0 <= expected_revision <= 2**63 - 1:
            raise InvalidInput("invalid_revision")
        if revision != expected_revision + 1:
            raise Conflict("revision_conflict")
        values = headers if document is None else {**headers, "document": document}
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
            lambda encoded: read_definition(encoded, version=self.record_version),
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

    def missed_occurrence_settings(
        self, household_id: str, definition_id: str
    ) -> MissedOccurrenceSettings:
        validate_identifier(household_id)
        validate_identifier(definition_id)
        row = self.connection.execute(
            "SELECT policy,revision FROM task_missed_occurrence_settings "
            "WHERE household_id=? AND definition_id=?",
            (household_id, definition_id),
        ).fetchone()
        if row is None:
            return MissedOccurrenceSettings(household_id, definition_id)
        try:
            return MissedOccurrenceSettings(
                household_id, definition_id, MissedOccurrencePolicy(row["policy"]), row["revision"]
            )
        except InvalidInput, ValueError:
            raise StorageFailure("invalid_task_record") from None

    def save_missed_occurrence_settings(
        self, value: MissedOccurrenceSettings, expected_revision: int
    ) -> None:
        identity = {"household_id": value.household_id, "definition_id": value.definition_id}
        self._write(
            MISSED_OCCURRENCE_TABLE,
            identity,
            {**identity, "policy": value.policy.value, "revision": value.revision},
            None,
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
            cast(
                TaskDefinition,
                _model(
                    row,
                    lambda encoded: read_definition(encoded, version=self.record_version),
                    _definition_headers,
                ),
            )
            for row in rows
        )

    def occurrence(self, household_id: str, occurrence_id: str) -> TaskOccurrence | None:
        validate_identifier(household_id)
        validate_identifier(occurrence_id)
        return _model(
            self.connection.execute(
                "SELECT * FROM task_occurrences WHERE household_id=? AND occurrence_id=?",
                (household_id, occurrence_id),
            ).fetchone(),
            lambda encoded: read_occurrence(encoded, version=self.record_version),
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

    def has_current_dependents(self, household_id: str, occurrence_id: str) -> bool:
        validate_identifier(household_id)
        validate_identifier(occurrence_id)
        return (
            self.connection.execute(
                "SELECT 1 FROM task_occurrences AS work WHERE household_id=? "
                "AND state NOT IN ('completed','cancelled','skipped') AND ("
                "EXISTS (SELECT 1 FROM json_each(work.document,'$.prerequisite_ids') "
                "WHERE value=?) OR EXISTS (SELECT 1 "
                "FROM json_each(work.document,'$.required_subtask_ids') WHERE value=?)) "
                "LIMIT 1",
                (household_id, occurrence_id, occurrence_id),
            ).fetchone()
            is not None
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
        open_only: bool = False,
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
        if open_only:
            where.append("state NOT IN ('completed','cancelled','skipped')")
        rows = self.connection.execute(
            "SELECT * FROM task_occurrences WHERE "
            + " AND ".join(where)
            + " ORDER BY occurrence_id LIMIT ?",
            (*parameters, limit),
        )
        return tuple(
            cast(
                TaskOccurrence,
                _model(
                    row,
                    lambda encoded: read_occurrence(encoded, version=self.record_version),
                    _occurrence_headers,
                ),
            )
            for row in rows
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
