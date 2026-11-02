"""Snapshot verification includes scoped recurrence values and original slot evidence."""

import sqlite3
from typing import cast

from domus.domain.errors import StorageFailure
from domus.domain.recurrence_records import FixedSchedule, ScheduledSlot
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
