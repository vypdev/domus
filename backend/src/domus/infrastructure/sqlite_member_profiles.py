"""Independent scoped profile revisions, strict decoding and atomic member initialization."""

import sqlite3
from dataclasses import dataclass
from typing import Literal, cast

from domus.domain.errors import Conflict, DomusError, StorageFailure
from domus.domain.identity import Member, validate_revision
from domus.domain.member_profiles import MemberLocale, MemberPreferences, MemberPresentation


def initialize_member_profiles(connection: sqlite3.Connection, member: Member) -> None:
    presentation = MemberPresentation(member.member_id, member.household_id)
    preferences = MemberPreferences(member.member_id, member.household_id)
    connection.execute(
        "INSERT INTO member_presentations(member_id,household_id,alias,revision) VALUES (?,?,?,?)",
        (
            presentation.member_id,
            presentation.household_id,
            presentation.alias,
            presentation.revision,
        ),
    )
    connection.execute(
        "INSERT INTO member_preferences(member_id,household_id,locale,"
        "routine_participation_summaries,revision) VALUES (?,?,?,?,?)",
        (
            preferences.member_id,
            preferences.household_id,
            preferences.locale,
            int(preferences.routine_participation_summaries),
            preferences.revision,
        ),
    )

    connection.execute(
        "INSERT INTO calendar_preferences(household_id,member_id) VALUES (?,?)",
        (member.household_id, member.member_id),
    )


def _row(
    connection: sqlite3.Connection,
    table: Literal["member_presentations", "member_preferences"],
    household_id: str,
    member_id: str,
) -> sqlite3.Row | None:
    # A missing member is absence; a missing profile for an existing member is corruption.
    return cast(
        sqlite3.Row | None,
        connection.execute(
            f"SELECT p.* FROM members m LEFT JOIN {table} p "
            "ON p.household_id=m.household_id AND p.member_id=m.member_id "
            "WHERE m.household_id=? AND m.member_id=?",
            (household_id, member_id),
        ).fetchone(),
    )


def _revision(revision: int, expected: int) -> None:
    validate_revision(expected)
    if revision != expected + 1:
        raise Conflict("revision_conflict")


@dataclass
class SQLitePresentations:
    connection: sqlite3.Connection

    def get(self, household_id: str, member_id: str) -> MemberPresentation | None:
        row = _row(self.connection, "member_presentations", household_id, member_id)
        if row is None:
            return None
        try:
            value = MemberPresentation(
                row["member_id"], row["household_id"], row["alias"], row["revision"]
            )
            if value.alias != row["alias"]:
                raise ValueError("Noncanonical stored alias")
            return value
        except DomusError, ValueError:
            raise StorageFailure("invalid_member_profile_record") from None

    def save(self, presentation: MemberPresentation, expected_revision: int) -> None:
        _revision(presentation.revision, expected_revision)
        if (
            self.connection.execute(
                "UPDATE member_presentations SET alias=?,revision=? "
                "WHERE household_id=? AND member_id=? AND revision=?",
                (
                    presentation.alias,
                    presentation.revision,
                    presentation.household_id,
                    presentation.member_id,
                    expected_revision,
                ),
            ).rowcount
            != 1
        ):
            raise Conflict("revision_conflict")


@dataclass
class SQLitePreferences:
    connection: sqlite3.Connection

    def get(self, household_id: str, member_id: str) -> MemberPreferences | None:
        row = _row(self.connection, "member_preferences", household_id, member_id)
        if row is None:
            return None
        try:
            flag = row["routine_participation_summaries"]
            if type(flag) is not int or flag not in (0, 1):
                raise ValueError("Invalid stored preference flag")
            return MemberPreferences(
                row["member_id"],
                row["household_id"],
                None if row["locale"] is None else MemberLocale(row["locale"]),
                flag == 1,
                row["revision"],
            )
        except DomusError, ValueError:
            raise StorageFailure("invalid_member_profile_record") from None

    def save(self, preferences: MemberPreferences, expected_revision: int) -> None:
        _revision(preferences.revision, expected_revision)
        if (
            self.connection.execute(
                "UPDATE member_preferences SET locale=?,routine_participation_summaries=?,"
                "revision=? "
                "WHERE household_id=? AND member_id=? AND revision=?",
                (
                    preferences.locale,
                    int(preferences.routine_participation_summaries),
                    preferences.revision,
                    preferences.household_id,
                    preferences.member_id,
                    expected_revision,
                ),
            ).rowcount
            != 1
        ):
            raise Conflict("revision_conflict")
