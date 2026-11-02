"""Snapshot verification includes scoped recurrence values and original slot evidence."""

import sqlite3
from typing import cast

from domus.domain.errors import StorageFailure
from domus.domain.recurrence_records import FixedSchedule, ScheduledSlot
from domus.domain.storage import Installation, JsonDocument
from domus.infrastructure.sqlite_recurrence import SQLiteRecurrences


def verify_recurrence_records(connection: sqlite3.Connection, installation: Installation) -> None:
    repository = SQLiteRecurrences(connection, installation)
    for row in connection.execute("SELECT household_id FROM recurrence_frontiers"):
        repository.frontier(row[0])
    for row in connection.execute("SELECT household_id,schedule_id FROM recurrence_rules"):
        # These keys came from the same read cursor; record decoding still checks every header.
        rule = cast(FixedSchedule, repository.schedule(row[0], row[1]))
        progress = repository.progress(row[0], row[1])
        if progress is None or not progress.matches_schedule(rule):
            raise StorageFailure("invalid_recurrence_record")
    for row in connection.execute("SELECT household_id,slot_key FROM recurrence_slots"):
        value = cast(ScheduledSlot, repository.slot(row[0], row[1]))
        source = repository.schedule(value.schedule.household_id, value.schedule.schedule_id)
        if source is None or not value.consistent_with(source):
            raise StorageFailure("invalid_recurrence_record")
        receipt = connection.execute(
            "SELECT result FROM receipts WHERE household_id=? "
            "AND actor_id=? AND action=? AND command_key=?",
            (value.command.household_id, value.command.actor_id, value.command.action, value.key),
        ).fetchone()
        if receipt is None:
            raise StorageFailure("invalid_recurrence_record")
        result = JsonDocument(receipt[0]).decode()
        if (
            result.get("slot_key") != value.key
            or result.get("occurrence_id") != value.occurrence_id
        ):
            raise StorageFailure("invalid_recurrence_record")
