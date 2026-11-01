"""Indexed live evidence projects reviews without duplicating a task or stock ledger."""

import sqlite3
from dataclasses import dataclass
from typing import cast

from domus.application.task_ports import TaskReviewEvidence
from domus.domain.errors import InvalidInput, StorageFailure
from domus.domain.restoration import OperationEvidence
from domus.domain.storage import validate_identifier
from domus.domain.task_reviews import DependencyReviewState, recorded_dependencies
from domus.infrastructure.sqlite_task_history import SQLiteTaskHistory

REVIEW_STATEMENTS = (
    "CREATE INDEX task_cycle_event_page ON outbox("
    "json_extract(payload,'$.cycle.cycle_id'),position)",
    "CREATE INDEX task_occurrence_event_page ON outbox("
    "json_extract(payload,'$.occurrence_id'),position)",
    "CREATE INDEX task_dependency_ack_page ON outbox("
    "json_extract(payload,'$.review.cause.dependent_cycle_id'),"
    "json_extract(payload,'$.review.cause.source_operation_id'),position)",
)

_CURRENT = (
    "SELECT r.*,a.detail AS audit_detail,o.payload AS event_payload,o.position,o.delivered,"
    "a.household_id AS review_audit_household,a.actor_id AS review_audit_actor,"
    "a.action AS review_audit_action,a.command_key AS review_audit_key,"
    "a.created_at AS review_audit_time,o.household_id AS review_event_household,"
    "o.event_type AS review_event_action,o.created_at AS review_event_time "
    "FROM receipts r JOIN audit a ON a.operation_id=r.operation_id "
    "JOIN outbox o ON o.event_id=r.operation_id "
)


@dataclass
class SQLiteTaskReviews:
    connection: sqlite3.Connection

    def _evidence(self, row: sqlite3.Row) -> OperationEvidence:
        if tuple(
            row[name]
            for name in (
                "review_audit_household",
                "review_audit_actor",
                "review_audit_action",
                "review_audit_key",
                "review_audit_time",
                "review_event_household",
                "review_event_action",
                "review_event_time",
            )
        ) != (
            row["household_id"],
            row["actor_id"],
            row["action"],
            row["command_key"],
            row["created_at"],
            row["household_id"],
            row["action"],
            row["created_at"],
        ):
            raise StorageFailure("invalid_dependency_review")
        return SQLiteTaskHistory(self.connection)._live(row).evidence

    def _one(
        self, household_id: str, occurrence_id: str, cycle_id: str, action: str, *, required: bool
    ) -> OperationEvidence | None:
        rows = self.connection.execute(
            _CURRENT + "WHERE r.household_id=? AND r.action=? "
            "AND json_extract(o.payload,'$.occurrence_id')=? "
            "AND json_extract(o.payload,'$.cycle.cycle_id')=? LIMIT 2",
            (household_id, action, occurrence_id, cycle_id),
        ).fetchall()
        if len(rows) > 1 or (required and not rows):
            raise StorageFailure("invalid_dependency_review")
        return None if not rows else self._evidence(rows[0])

    def read(
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
        for identity in (household_id, occurrence_id, cycle_id):
            validate_identifier(identity)
        if type(limit) is not int or not 1 <= limit <= 101:
            raise InvalidInput("invalid_page_size")
        if type(after) is not int or not 0 <= after <= 2**63 - 1:
            raise InvalidInput("invalid_task_position")
        if state is not None and not isinstance(state, DependencyReviewState):
            raise InvalidInput("invalid_task_query")
        if source_operation_id is not None:
            validate_identifier(source_operation_id)
        completion = cast(
            OperationEvidence,
            self._one(household_id, occurrence_id, cycle_id, "task.complete", required=True),
        )
        closure = self._one(household_id, occurrence_id, cycle_id, "task.reopen", required=False)
        try:
            prerequisites, subtasks = recorded_dependencies(completion.receipt.result.decode())
        except InvalidInput:
            raise StorageFailure("invalid_dependency_review") from None
        identities = sorted(set(prerequisites) | set(subtasks))
        if not identities:
            return TaskReviewEvidence(completion, closure, ())
        placeholders = ",".join("?" for _ in identities)
        missing = self.connection.execute(
            "SELECT 1 FROM task_cycles c WHERE c.household_id=? AND c.closed_at IS NOT NULL "
            "AND c.occurrence_id IN (" + placeholders + ") AND NOT EXISTS ("
            "SELECT 1 FROM receipts r JOIN audit a ON a.operation_id=r.operation_id "
            "JOIN outbox o ON o.event_id=r.operation_id WHERE r.household_id=c.household_id "
            "AND r.action='task.reopen' AND json_extract(o.payload,'$.cycle.cycle_id')=c.cycle_id) "
            "LIMIT 1",
            (household_id, *identities),
        ).fetchone()
        if missing is not None:
            raise StorageFailure("invalid_dependency_review")
        sql = (
            _CURRENT + "WHERE r.household_id=? AND r.action='task.reopen' "
            "AND json_extract(o.payload,'$.occurrence_id') IN (" + placeholders + ") "
            "AND o.position>? "
        )
        parameters: list[str | int] = [household_id, *identities, max(after, completion.position)]
        if closure is not None:
            sql += "AND o.position<? "
            parameters.append(closure.position)
        if source_operation_id is not None:
            sql += "AND r.operation_id=? "
            parameters.append(source_operation_id)
        if state is not None:
            sql += (
                "AND "
                + ("NOT " if state is DependencyReviewState.PENDING else "")
                + "EXISTS (SELECT 1 FROM receipts ar "
                "JOIN audit aa ON aa.operation_id=ar.operation_id "
                "JOIN outbox ao ON ao.event_id=ar.operation_id "
                "WHERE ar.household_id=r.household_id "
                "AND ar.action='task.dependency.review' "
                "AND json_extract(ao.payload,'$.review.cause.dependent_cycle_id')=? "
                "AND json_extract(ao.payload,'$.review.cause.source_operation_id')=r.operation_id) "
            )
            parameters.append(cycle_id)
        rows = self.connection.execute(sql + "ORDER BY o.position LIMIT ?", (*parameters, limit))
        reopenings = tuple(self._evidence(row) for row in rows)
        if not reopenings:
            return TaskReviewEvidence(completion, closure, ())
        operation_ids = tuple(row.receipt.operation_id for row in reopenings)
        ack_rows = self.connection.execute(
            _CURRENT + "WHERE r.household_id=? AND r.action='task.dependency.review' "
            "AND json_extract(o.payload,'$.review.cause.dependent_cycle_id')=? "
            "AND json_extract(o.payload,'$.review.cause.source_operation_id') IN ("
            + ",".join("?" for _ in operation_ids)
            + ") ORDER BY o.position LIMIT ?",
            (household_id, cycle_id, *operation_ids, len(operation_ids) + 1),
        )
        return TaskReviewEvidence(
            completion, closure, reopenings, tuple(self._evidence(row) for row in ack_rows)
        )
