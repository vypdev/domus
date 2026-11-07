"""Private display choices use their own storage and compare-and-swap revision."""

import sqlite3
from dataclasses import dataclass

from domus.domain.calendar_values import CalendarPreference, WeekStart
from domus.domain.errors import Conflict, InvalidInput, StorageFailure
from domus.domain.identity import validate_revision

CALENDAR_PREFERENCE_STATEMENT = (
    "CREATE TABLE calendar_preferences(household_id TEXT NOT NULL, member_id TEXT NOT NULL, "
    "week_start TEXT NOT NULL DEFAULT 'monday' CHECK(week_start IN ('monday','sunday')), "
    "revision INTEGER NOT NULL DEFAULT 1 CHECK(typeof(revision)='integer' AND revision>=1), "
    "PRIMARY KEY(household_id,member_id), "
    "FOREIGN KEY(household_id,member_id) REFERENCES members(household_id,member_id))"
)


@dataclass
class SQLiteCalendarPreferences:
    connection: sqlite3.Connection

    def get(self, household_id: str, member_id: str) -> CalendarPreference:
        row = self.connection.execute(
            "SELECT week_start,revision FROM calendar_preferences "
            "WHERE household_id=? AND member_id=?",
            (household_id, member_id),
        ).fetchone()
        if row is None:
            raise StorageFailure("invalid_calendar_preference")
        try:
            return CalendarPreference(household_id, member_id, WeekStart(row[0]), row[1])
        except ValueError, InvalidInput:
            raise StorageFailure("invalid_calendar_preference") from None

    def save(self, preference: CalendarPreference, expected_revision: int) -> None:
        validate_revision(expected_revision)
        if (
            preference.revision != expected_revision + 1
            or self.connection.execute(
                "UPDATE calendar_preferences SET week_start=?,revision=? "
                "WHERE household_id=? AND member_id=? AND revision=?",
                (
                    preference.week_start,
                    preference.revision,
                    preference.household_id,
                    preference.member_id,
                    expected_revision,
                ),
            ).rowcount
            != 1
        ):
            raise Conflict("revision_conflict")
