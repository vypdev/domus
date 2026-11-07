"""Schema 11 adds a separate owner-private preference to genuine supported databases."""

import hashlib
from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_sqlite_member_profiles import FIXTURES, facts, frozen
from test_task_commands import fixture

from domus.application.calendar_commands import (
    CalendarCommands,
    CalendarPreferenceUpdate,
)
from domus.domain.calendar_values import CalendarPreference, WeekStart
from domus.domain.errors import Conflict, DatabaseRejected, Forbidden, InvalidInput, StorageFailure
from domus.domain.storage import JsonDocument
from domus.infrastructure.sqlite import SQLiteDatabase
from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots, _verify_database


def test_genuine_v10_fixture_is_migrated_without_reinterpreting_original_rows(tmp_path):
    assert hashlib.sha256((FIXTURES / "v10.sql").read_bytes()).hexdigest() == (
        "dc23b125821550920eda487685c353aed6485bf36d0d0a7f60902967397a8e83"
    )
    store = frozen(tmp_path, 10)
    with store._connection() as connection:
        assert _verify_database(connection, store, previous=True) == 10
        tables = tuple(
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        )
    before = facts(store.path, tables)
    with pytest.raises(DatabaseRejected, match="unsupported_schema"), store.read():
        pass
    store.initialize(require_existing=True)
    with store.read() as unit:
        (owner,) = unit.members.list("home")
        assert unit.calendar_preferences.get("home", owner.member_id) == CalendarPreference(
            "home", owner.member_id
        )
    assert facts(store.path, tables) == before


def test_late_v10_preference_migration_failure_preserves_exact_source(tmp_path, monkeypatch):
    from domus.infrastructure import sqlite as adapter

    store = frozen(tmp_path, 10)
    before = store.path.read_bytes()
    monkeypatch.setattr(adapter, "CALENDAR_PREFERENCE_STATEMENT", "SELECT 1")
    with pytest.raises(StorageFailure, match="storage_failure"):
        store.initialize(require_existing=True)
    assert store.path.read_bytes() == before


@pytest.mark.parametrize("corruption", ["missing", "unknown"])
def test_current_preference_and_snapshot_fail_closed_without_repair(tmp_path, corruption):
    tasks, store, actor, identifiers = fixture(tmp_path)
    commands = CalendarCommands(store, actor, actor.current, tasks.clock, identifiers)
    current = commands.preference()
    with store._connection() as connection:
        if corruption == "missing":
            connection.execute(
                "DELETE FROM calendar_preferences WHERE member_id=?", (current.member_id,)
            )
        else:
            connection.execute("PRAGMA ignore_check_constraints=ON")
            connection.execute(
                "UPDATE calendar_preferences SET week_start='tuesday' WHERE member_id=?",
                (current.member_id,),
            )
    before = store.path.read_bytes()
    with pytest.raises(StorageFailure, match="invalid_calendar_preference"):
        commands.preference()
    with pytest.raises(DatabaseRejected):
        SQLiteSnapshots(
            store, tmp_path / "archive", store.installation, SimpleNamespace(now=lambda: 100)
        ).create("invalid")
    assert store.path.read_bytes() == before


def test_preference_uses_original_owner_and_compare_and_swap(tmp_path):
    from domus.application.calendar_commands import _OwnerAuthority
    from domus.domain.storage import CommandKey

    tasks, store, actor, identifiers = fixture(tmp_path)
    commands = CalendarCommands(store, actor, actor.current, tasks.clock, identifiers)
    with pytest.raises(InvalidInput):
        CalendarPreferenceUpdate(1, "sunday")
    with pytest.raises(InvalidInput):
        CalendarPreference("home", "member", "sunday")
    current = commands.preference()
    opened = replace(commands, transactions=SQLiteDatabase(store.path, store.installation))
    committed = opened.update("original", CalendarPreferenceUpdate(1, WeekStart.SUNDAY))
    with pytest.raises(Conflict, match="revision_conflict"):
        commands.update("stale", CalendarPreferenceUpdate(1, WeekStart.MONDAY))
    with store.write() as unit:
        with pytest.raises(Conflict, match="revision_conflict"):
            unit.calendar_preferences.save(replace(current, revision=3), 1)
        with pytest.raises(Conflict, match="revision_conflict"):
            unit.calendar_preferences.save(replace(current, revision=2), 1)
        proof = _OwnerAuthority(actor.current(), committed.command)
        with pytest.raises(Forbidden):
            proof.require(
                CommandKey("home", actor.current().ha_user_id, committed.command.action, "other"),
                unit,
            )
        with pytest.raises(Forbidden):
            proof.check_result(
                unit, replace(committed, result=JsonDocument.from_value({"member_id": "foreign"}))
            )
