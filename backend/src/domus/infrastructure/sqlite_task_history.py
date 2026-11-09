"""Bounded task evidence reads merge current and retained positions in the caller transaction."""

import heapq
import sqlite3
from dataclasses import dataclass

from domus.domain.errors import InvalidInput, StorageFailure
from domus.domain.restoration import OperationEvidence, RetainedOperation
from domus.domain.storage import JsonDocument, validate_identifier
from domus.domain.task_events import TaskSourceRecord
from domus.infrastructure.sqlite_history import SQLiteHistory, _evidence, _record, _same
from domus.infrastructure.sqlite_task_records import read_cycle

RESTORED_AWARD_CLOSURE = (
    "current=0 AND (action='task.reopen' OR (action='task.verify' AND "
    "json_extract(document,'$.event_payload.cycle.verification')='rejected'))"
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


def task_source_record(retained: RetainedOperation) -> TaskSourceRecord:
    raw = retained.evidence.receipt.result.decode().get("cycle")
    if not isinstance(raw, dict):
        raise StorageFailure("invalid_recurrence_source")
    cycle = read_cycle(JsonDocument.from_value({"version": 1, **raw}).encoded)
    return TaskSourceRecord(retained, cycle)


@dataclass
class SQLiteTaskHistory:
    connection: sqlite3.Connection

    def lifecycle_sources(
        self, household_id: str, *, limit: int = 100, after: int = 0
    ) -> tuple[TaskSourceRecord, ...]:
        validate_identifier(household_id)
        if type(limit) is not int or not 1 <= limit <= 100:
            raise InvalidInput("invalid_page_size")
        if type(after) is not int or not 0 <= after <= 2**63 - 1:
            raise InvalidInput("invalid_task_position")
        candidates = self.connection.execute(
            "SELECT r.actor_id,r.operation_id,o.position,1 AS current FROM receipts r "
            "JOIN outbox o ON o.event_id=r.operation_id "
            "WHERE r.household_id=? AND r.action IN ('task.complete','task.verify','task.reopen') "
            "AND o.position>? UNION ALL "
            "SELECT actor_id,operation_id,position,0 AS current FROM retained_operations "
            "WHERE household_id=? AND current=0 "
            "AND action IN ('task.complete','task.verify','task.reopen') AND position>? "
            "ORDER BY position LIMIT ?",
            (household_id, after, household_id, after, limit),
        ).fetchall()
        result = []
        previous = after
        for row in candidates:
            retained = self.operation(household_id, row["actor_id"], row["operation_id"])
            if (
                retained is None
                or retained.current != bool(row["current"])
                or retained.evidence.position != row["position"]
                or row["position"] <= previous
            ):
                raise StorageFailure("invalid_recurrence_source")
            result.append(task_source_record(retained))
            previous = row["position"]
        return tuple(result)

    def lifecycle_events(
        self, household_id: str, *, limit: int = 25, after: int = 0
    ) -> tuple[OperationEvidence, ...]:
        validate_identifier(household_id)
        if type(limit) is not int or not 1 <= limit <= 101:
            raise InvalidInput("invalid_page_size")
        if type(after) is not int or not 0 <= after <= 2**63 - 1:
            raise InvalidInput("invalid_task_position")
        return tuple(
            self._live(row).evidence
            for row in self.connection.execute(
                _CURRENT + "WHERE r.household_id=? "
                "AND r.action IN ('task.complete','task.verify','task.reopen') "
                "AND o.position>? ORDER BY o.position LIMIT ?",
                (household_id, after, limit),
            )
        )

    def restored_cycle_closure(self, household_id: str, cycle_id: str) -> TaskSourceRecord | None:
        row = self.connection.execute(
            "SELECT * FROM retained_operations WHERE household_id=? "
            "AND json_extract(document,'$.event_payload.cycle.cycle_id')=? "
            f"AND {RESTORED_AWARD_CLOSURE} ORDER BY position LIMIT 1",
            (household_id, cycle_id),
        ).fetchone()
        return None if row is None else task_source_record(_record(row))

    def _live(self, row: sqlite3.Row) -> RetainedOperation:
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
        try:
            evidence = _evidence(row)
        except InvalidInput:
            raise StorageFailure("invalid_task_operation") from None
        retained = SQLiteHistory(self.connection).get(evidence.receipt.command)
        if retained is not None and (
            not retained.current or not _same(retained.evidence, evidence)
        ):
            raise StorageFailure("invalid_retained_projection")
        return RetainedOperation(evidence, True, None if retained is None else retained.archived_by)

    def history(
        self, household_id: str, occurrence_id: str, *, limit: int = 25, after: int = 0
    ) -> tuple[RetainedOperation, ...]:
        validate_identifier(household_id)
        validate_identifier(occurrence_id)
        if type(limit) is not int or not 1 <= limit <= 101:
            raise InvalidInput("invalid_page_size")
        if type(after) is not int or not 0 <= after <= 2**63 - 1:
            raise InvalidInput("invalid_task_position")
        # Each SQL source materializes at most one lookahead page. Current retained
        # projections are represented only by live rows, never delivered twice.
        live = tuple(
            self._live(row)
            for row in self.connection.execute(
                _CURRENT + "WHERE r.household_id=? AND r.action GLOB 'task.*' "
                "AND json_extract(o.payload,'$.occurrence_id')=? AND o.position>? "
                "ORDER BY o.position LIMIT ?",
                (household_id, occurrence_id, after, limit),
            )
        )
        retained = tuple(
            _record(row)
            for row in self.connection.execute(
                "SELECT * FROM retained_operations WHERE household_id=? AND current=0 "
                "AND action GLOB 'task.*' "
                "AND json_extract(document,'$.event_payload.occurrence_id')=? AND position>? "
                "ORDER BY position LIMIT ?",
                (household_id, occurrence_id, after, limit),
            )
        )
        rows = tuple(heapq.merge(live, retained, key=lambda value: value.evidence.position))
        if len({row.evidence.position for row in rows}) != len(rows):
            raise StorageFailure("invalid_retained_projection")
        return rows[:limit]

    def latest_reschedule(self, household_id: str, occurrence_id: str) -> RetainedOperation | None:
        validate_identifier(household_id)
        validate_identifier(occurrence_id)
        row = self.connection.execute(
            _CURRENT + "WHERE r.household_id=? AND r.action='task.recurrence.reschedule' "
            "AND json_extract(o.payload,'$.occurrence_id')=? ORDER BY o.position DESC LIMIT 1",
            (household_id, occurrence_id),
        ).fetchone()
        return None if row is None else self._live(row)

    def operation(
        self, household_id: str, actor_id: str, operation_id: str
    ) -> RetainedOperation | None:
        for identity in (household_id, actor_id, operation_id):
            validate_identifier(identity)
        row = self.connection.execute(
            _CURRENT + "WHERE r.household_id=? AND r.actor_id=? AND r.operation_id=? "
            "AND r.action GLOB 'task.*'",
            (household_id, actor_id, operation_id),
        ).fetchone()
        if row is not None:
            return self._live(row)
        row = self.connection.execute(
            "SELECT * FROM retained_operations WHERE household_id=? AND actor_id=? "
            "AND operation_id=? AND action GLOB 'task.*'",
            (household_id, actor_id, operation_id),
        ).fetchone()
        if row is None:
            return None
        retained = _record(row)
        if retained.current:
            raise StorageFailure("invalid_retained_projection")
        return retained
