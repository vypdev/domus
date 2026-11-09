"""Snapshot verification includes scoped recurrence values and original slot evidence."""

import sqlite3
from typing import cast

from domus.domain.errors import StorageFailure
from domus.domain.recurrence_records import FixedSchedule, ScheduledSlot
from domus.domain.relative_lifecycle import RelativeClosure
from domus.domain.relative_recurrence import RelativeSchedule
from domus.domain.storage import Installation
from domus.infrastructure.sqlite_recurrence import SQLiteRecurrences


def verify_recurrence_records(connection: sqlite3.Connection, installation: Installation) -> None:
    repository = SQLiteRecurrences(connection, installation)
    for row in connection.execute("SELECT household_id FROM recurrence_frontiers"):
        repository.frontier(row[0])
    for row in connection.execute(
        "SELECT household_id,schedule_id,timing_kind FROM recurrence_rules"
    ):
        # These keys came from the same read cursor; record decoding still checks every header.
        if row[2] == "fixed_calendar":
            rule = cast(FixedSchedule, repository.schedule(row[0], row[1]))
            progress = repository.progress(row[0], row[1])
            valid = progress is not None and progress.matches_schedule(rule)
        elif row[2] == "completion_relative":
            relative = cast(RelativeSchedule, repository.relative_schedule(row[0], row[1]))
            continuation = repository.relative_progress(row[0], row[1])
            valid = continuation is not None and continuation.matches_schedule(relative)
        else:
            valid = False
        if not valid:
            raise StorageFailure("invalid_recurrence_record")
    for row in connection.execute("SELECT household_id,slot_key FROM recurrence_relative_slots"):
        repository.relative_slot(row[0], row[1])
    for row in connection.execute("SELECT household_id,slot_key FROM recurrence_slots"):
        value = cast(ScheduledSlot, repository.slot(row[0], row[1]))
        source = repository.schedule(value.schedule.household_id, value.schedule.schedule_id)
        if source is None or not value.consistent_with(source):
            raise StorageFailure("invalid_recurrence_record")


def verify_relative_lifecycle_records(
    connection: sqlite3.Connection, installation: Installation
) -> None:
    repository = SQLiteRecurrences(connection, installation)
    repository.verify_relative_inbox()
    for row in connection.execute(
        "SELECT household_id,closure_key FROM recurrence_relative_closures"
    ):
        repository.relative_closure(row[0], row[1])
    missing = connection.execute(
        "WITH proof AS ("
        "SELECT operation_id FROM receipts WHERE actor_id='system:recurrence' "
        "AND json_type(result,'$.relative_closure') IS NOT NULL "
        "UNION ALL SELECT operation_id FROM retained_operations "
        "WHERE current=0 AND actor_id='system:recurrence' "
        "AND json_type(document,'$.result.relative_closure') IS NOT NULL) "
        "SELECT 1 FROM proof LEFT JOIN recurrence_relative_closures USING(operation_id) "
        "WHERE closure_key IS NULL LIMIT 1"
    ).fetchone()
    if missing is not None:
        raise StorageFailure("invalid_relative_closure_record")


def restore_relative_closures(
    target: sqlite3.Connection, source: sqlite3.Connection, installation: Installation
) -> None:
    original = SQLiteRecurrences(source, installation)
    restored = SQLiteRecurrences(target, installation)
    for row in source.execute("SELECT household_id,closure_key FROM recurrence_relative_closures"):
        closure = cast(RelativeClosure, original.relative_closure(row[0], row[1]))
        previous = restored.relative_closure(row[0], row[1])
        if previous is None:
            restored.add_relative_closure(closure)
        elif previous != closure:
            raise StorageFailure("invalid_relative_closure_record")
