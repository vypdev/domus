"""Bounded task evidence reads merge current and retained positions in the caller transaction."""

import heapq
import sqlite3
from dataclasses import dataclass

from domus.domain.errors import InvalidInput, StorageFailure
from domus.domain.restoration import RetainedOperation
from domus.domain.storage import validate_identifier
from domus.infrastructure.sqlite_history import _CURRENT, SQLiteHistory, _evidence, _record, _same


@dataclass
class SQLiteTaskHistory:
    connection: sqlite3.Connection

    def _live(self, row: sqlite3.Row) -> RetainedOperation:
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
