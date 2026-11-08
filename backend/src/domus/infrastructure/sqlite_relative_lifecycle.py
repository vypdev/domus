"""Canonical closure snapshots and a durable, scoped task-event inbox."""

import sqlite3
from dataclasses import dataclass
from typing import cast

from domus.domain.errors import Conflict, InvalidInput, StorageFailure
from domus.domain.recurrence_records import MAINTENANCE_ACTOR
from domus.domain.relative_lifecycle import (
    RelativeClosure,
    RelativeClosureKind,
    RelativeEventOutcome,
)
from domus.domain.storage import (
    Installation,
    JsonDocument,
    JsonObject,
    JsonValue,
    validate_identifier,
)
from domus.domain.task_events import TaskEventKind, TaskSourceRecord
from domus.domain.task_values import VerificationState
from domus.infrastructure.sqlite_receipts import SQLiteReceipts
from domus.infrastructure.sqlite_recurrence_records import _object, _read, _record
from domus.infrastructure.sqlite_relative_recurrence_records import (
    _operation,
    read_relative_schedule,
    read_relative_slot,
    relative_schedule_document,
    relative_slot_document,
)
from domus.infrastructure.sqlite_task_history import SQLiteTaskHistory, task_source_record
from domus.infrastructure.sqlite_task_records import cycle_document, read_cycle


def relative_closure_document(value: RelativeClosure) -> JsonDocument:
    document: JsonObject = {
        "version": 1,
        "installation": {
            "instance_id": value.installation.instance_id,
            "channel": value.installation.channel,
        },
        "schedule": relative_schedule_document(value.schedule).decode(),
        "cycle": cycle_document(value.cycle).decode(),
        "kind": value.kind.value,
        "recorded_at": value.recorded_at,
        "operation": {
            "command": {
                "household_id": value.operation.command.household_id,
                "actor_id": value.operation.command.actor_id,
                "action": value.operation.command.action,
                "key": value.operation.command.key,
            },
            "operation_id": value.operation.operation_id,
        },
        "successor": None
        if value.successor is None
        else relative_slot_document(value.successor).decode(),
    }
    return JsonDocument.from_value(document)


def _closure(value: JsonValue) -> RelativeClosure:
    row = _record(
        value,
        ("installation", "schedule", "cycle", "kind", "recorded_at", "operation", "successor"),
    )
    installation = _object(row["installation"], ("instance_id", "channel"))
    return RelativeClosure(
        Installation(cast(str, installation["instance_id"]), cast(str, installation["channel"])),
        read_relative_schedule(JsonDocument.from_value(row["schedule"]).encoded),
        read_cycle(JsonDocument.from_value(row["cycle"]).encoded),
        RelativeClosureKind(cast(str, row["kind"])),
        cast(int, row["recorded_at"]),
        _operation(row["operation"]),
        None
        if row["successor"] is None
        else read_relative_slot(JsonDocument.from_value(row["successor"]).encoded),
    )


def read_relative_closure(document: str) -> RelativeClosure:
    return _read(document, _closure)


@dataclass
class SQLiteRelativeInbox:
    connection: sqlite3.Connection
    installation: Installation

    def _identity(
        self, record: TaskSourceRecord
    ) -> tuple[str, int, str, str, str, str, str | None, int]:
        try:
            event = record.event(self.installation)
        except InvalidInput:
            raise StorageFailure("invalid_recurrence_source") from None
        mapped = self.connection.execute(
            "SELECT schedule_id FROM recurrence_relative_slots "
            "WHERE household_id=? AND occurrence_id=?",
            (event.cycle.household_id, event.cycle.occurrence_id),
        ).fetchone()
        terminal = (
            event.kind is TaskEventKind.REOPENED
            or event.cycle.verification is VerificationState.REJECTED
        )
        return (
            event.cycle.household_id,
            event.position,
            event.event_key,
            event.event_id,
            record.original.evidence.receipt.command.actor_id,
            event.cycle_key,
            None if mapped is None else mapped["schedule_id"],
            int(terminal),
        )

    def _source(self, row: sqlite3.Row) -> TaskSourceRecord:
        identity = tuple(
            row[key]
            for key in (
                "household_id",
                "position",
                "event_key",
                "operation_id",
                "actor_id",
                "cycle_key",
                "source_schedule_id",
                "source_terminal",
            )
        )
        retained = SQLiteTaskHistory(self.connection).operation(
            row["household_id"], row["actor_id"], row["operation_id"]
        )
        if retained is None:
            raise StorageFailure("invalid_recurrence_source")
        record = task_source_record(retained)
        if identity != self._identity(record):
            raise StorageFailure("invalid_recurrence_source")
        return record

    def relative_inbox_after(self, household_id: str) -> int:
        validate_identifier(household_id)
        row = self.connection.execute(
            "SELECT * FROM recurrence_relative_inbox WHERE household_id=? "
            "ORDER BY position DESC LIMIT 1",
            (household_id,),
        ).fetchone()
        return 0 if row is None else self._source(row).original.evidence.position

    def pending_relative_sources(
        self, household_id: str, *, limit: int = 100, after: int = 0
    ) -> tuple[TaskSourceRecord, ...]:
        validate_identifier(household_id)
        if type(limit) is not int or not 1 <= limit <= 100:
            raise InvalidInput("invalid_page_size")
        if type(after) is not int or not 0 <= after <= 2**63 - 1:
            raise InvalidInput("invalid_task_position")
        return tuple(
            self._source(row)
            for row in self.connection.execute(
                "SELECT * FROM recurrence_relative_inbox WHERE household_id=? "
                "AND outcome_status IS NULL AND position>? ORDER BY position LIMIT ?",
                (household_id, after, limit),
            )
        )

    def relative_sources_pending(self, household_id: str) -> bool:
        validate_identifier(household_id)
        return (
            self.connection.execute(
                "SELECT 1 FROM recurrence_relative_inbox WHERE household_id=? "
                "AND source_schedule_id IS NOT NULL AND outcome_status IS NULL LIMIT 1",
                (household_id,),
            ).fetchone()
            is not None
        )

    def next_relative_source(self, household_id: str, schedule_id: str) -> str | None:
        validate_identifier(household_id)
        validate_identifier(schedule_id)
        row = self.connection.execute(
            "SELECT * FROM recurrence_relative_inbox WHERE household_id=? "
            "AND source_schedule_id=? AND outcome_status IS NULL "
            "ORDER BY source_terminal DESC,position LIMIT 1",
            (household_id, schedule_id),
        ).fetchone()
        if row is None:
            return None
        return self._source(row).event(self.installation).event_key

    def relative_source(self, household_id: str, event_key: str) -> TaskSourceRecord | None:
        validate_identifier(household_id)
        validate_identifier(event_key)
        row = self.connection.execute(
            "SELECT * FROM recurrence_relative_inbox WHERE household_id=? AND event_key=?",
            (household_id, event_key),
        ).fetchone()
        return None if row is None else self._source(row)

    def add_relative_source(self, record: TaskSourceRecord) -> None:
        identity = self._identity(record)
        household, _, key, operation, actor, _, _, _ = identity
        prior = self.connection.execute(
            "SELECT * FROM recurrence_relative_inbox WHERE household_id=? AND event_key=?",
            (household, key),
        ).fetchone()
        if prior is not None:
            if self._identity(self._source(prior)) != identity:
                raise Conflict("relative_source_conflict")
            return
        original = SQLiteTaskHistory(self.connection).operation(household, actor, operation)
        if original != record.original:
            raise Conflict("relative_source_conflict")
        try:
            self.connection.execute(
                "INSERT INTO recurrence_relative_inbox "
                "(household_id,position,event_key,operation_id,actor_id,cycle_key,"
                "source_schedule_id,source_terminal) VALUES (?,?,?,?,?,?,?,?)",
                identity,
            )
        except sqlite3.IntegrityError:
            raise Conflict("relative_source_conflict") from None

    def _outcome(
        self, row: sqlite3.Row, source: TaskSourceRecord | None = None
    ) -> RelativeEventOutcome | None:
        if row["outcome_status"] is None:
            return None
        operation = row["outcome_operation_id"]
        receipt = (
            None
            if operation is None
            else SQLiteReceipts(self.connection).get_operation(
                row["household_id"],
                MAINTENANCE_ACTOR,
                operation,
            )
        )
        if operation is not None and receipt is None:
            raise StorageFailure("invalid_relative_outcome")
        try:
            outcome = RelativeEventOutcome(
                row["outcome_status"],
                row["outcome_schedule_id"],
                receipt,
                row["outcome_occurrence_id"],
            )
            original = self._source(row) if source is None else source
            if not outcome.matches_source(original.event(self.installation), self.installation):
                raise InvalidInput("invalid_relative_outcome")
            return outcome
        except InvalidInput:
            raise StorageFailure("invalid_relative_outcome") from None

    def relative_source_outcome(
        self, household_id: str, event_key: str
    ) -> RelativeEventOutcome | None:
        validate_identifier(household_id)
        validate_identifier(event_key)
        row = self.connection.execute(
            "SELECT * FROM recurrence_relative_inbox WHERE household_id=? AND event_key=?",
            (household_id, event_key),
        ).fetchone()
        return None if row is None else self._outcome(row)

    def finish_relative_source(
        self, household_id: str, event_key: str, outcome: RelativeEventOutcome
    ) -> None:
        validate_identifier(household_id)
        validate_identifier(event_key)
        receipt = outcome.receipt
        operation = None if receipt is None else receipt.operation_id
        if receipt is not None and receipt != SQLiteReceipts(self.connection).get_operation(
            household_id, MAINTENANCE_ACTOR, receipt.operation_id
        ):
            raise Conflict("relative_source_conflict")
        row = self.connection.execute(
            "SELECT * FROM recurrence_relative_inbox WHERE household_id=? AND event_key=?",
            (household_id, event_key),
        ).fetchone()
        if row is None:
            raise Conflict("relative_source_missing")
        source = self._source(row)
        if not outcome.matches_source(source.event(self.installation), self.installation):
            raise Conflict("relative_source_conflict")
        if (
            self.connection.execute(
                "UPDATE recurrence_relative_inbox SET outcome_status=?,outcome_schedule_id=?,"
                "outcome_operation_id=?,outcome_occurrence_id=? "
                "WHERE household_id=? AND event_key=? AND outcome_status IS NULL",
                (
                    outcome.status,
                    outcome.schedule_id,
                    operation,
                    outcome.occurrence_id,
                    household_id,
                    event_key,
                ),
            ).rowcount
            != 1
        ):
            raise Conflict("relative_source_missing")

    def verify_relative_inbox(self) -> None:
        for row in self.connection.execute("SELECT * FROM recurrence_relative_inbox"):
            source = self._source(row)
            self._outcome(row, source)
