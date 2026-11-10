"""Genuine supported schema-9 input, captured before lifecycle DDL or migration code."""

import hashlib
from types import SimpleNamespace

import pytest
from test_sqlite_member_profiles import FIXTURES, facts, frozen

from domus.domain.errors import DatabaseRejected, StorageFailure
from domus.domain.member_profiles import MemberLocale
from domus.infrastructure.sqlite import SQLiteDatabase
from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots


def test_schema9_fixture_preserves_the_exact_captured_pre_ddl_sql():
    assert hashlib.sha256((FIXTURES / "v9.sql").read_bytes()).hexdigest() == (
        "e3c81ef1fa42e1ea302de60662c10e7231466ab32da1931ecde1e6d7a49213b7"
    )


def test_supported_schema9_keeps_fixed_work_pristine_relative_progress_and_private_choices(
    tmp_path,
):
    store = frozen(tmp_path, 9)
    with store._connection() as connection:
        tables = tuple(
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        )
    original = facts(store.path, tables)
    with pytest.raises(DatabaseRejected, match="unsupported_schema"), store.read():
        pass
    store.initialize(require_existing=True)
    restarted = SQLiteDatabase(store.path, store.installation)
    with restarted.read() as unit:
        fixed, relative = (
            unit.recurrence.schedules("home"),
            unit.recurrence.relative_schedules("home"),
        )
        assert len(fixed) == len(relative) == 1
        slots = unit.recurrence.slots("home", fixed[0].schedule_id)
        assert len(slots) == 2
        assert {slot.occurrence_id for slot in slots} == {
            item.occurrence_id for item in unit.tasks.occurrences("home")
        }
        progress = unit.recurrence.relative_progress("home", relative[0].schedule_id)
        assert progress.revision == 1 and progress.source_after == 0
        assert progress.current_occurrence_id is progress.current_slot_key is None
        assert progress.evidence is progress.last_run_at is None
        assert unit.recurrence.relative_slots("home", relative[0].schedule_id) == ()
        members = unit.members.list("home")
        assert len(members) == 1
        public = unit.presentations.get("home", members[0].member_id)
        private = unit.preferences.get("home", members[0].member_id)
        assert public.alias == "Fixture 🧹" and public.revision == 2
        assert private.locale is MemberLocale.SPANISH
        assert private.routine_participation_summaries is False and private.revision == 2
    assert facts(store.path, tables) == original
    with restarted._connection() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 23
    with restarted.read() as unit:
        assert unit.recurrence.relative_inbox_after("home") == 0


def test_independent_snapshot_inspection_after_migration_preserves_every_original_row(tmp_path):
    store = frozen(tmp_path, 9)
    # Raw SQL import is test setup; the snapshot boundary requires an owned private file.
    store.path.chmod(0o600)
    assert store.path.stat().st_mode & 0o777 == 0o600
    with store._connection() as connection:
        tables = tuple(
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        )
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 9
    original = facts(store.path, tables)
    store.initialize(require_existing=True)
    before = store.path.read_bytes()
    archive = tmp_path / "snapshot"
    snapshots = SQLiteSnapshots(
        store, archive, store.installation, SimpleNamespace(now=lambda: 1800000000000)
    )
    checkpoint = snapshots.create("source-nine")
    assert checkpoint.schema_version == 23 and snapshots.inspect() == checkpoint
    assert facts(archive / "domus.sqlite3", tables) == original
    assert store.path.read_bytes() == before


def test_late_lifecycle_ddl_failure_leaves_genuine_schema9_bytes_untouched(tmp_path, monkeypatch):
    from domus.infrastructure import sqlite as adapter

    store = frozen(tmp_path, 9)
    before = store.path.read_bytes()
    monkeypatch.setattr(
        adapter,
        "RELATIVE_LIFECYCLE_STATEMENTS",
        (*adapter.RELATIVE_LIFECYCLE_STATEMENTS, "INVALID SQL"),
    )
    with pytest.raises(StorageFailure, match="storage_failure"):
        store.initialize(require_existing=True)
    assert store.path.read_bytes() == before


def test_relabelled_schema9_with_an_unrecognized_layout_is_refused(tmp_path):
    store = frozen(tmp_path, 9)
    with store._connection() as connection:
        connection.execute("CREATE INDEX bogus_profile_index ON member_preferences(locale)")
    before = store.path.read_bytes()
    with pytest.raises(DatabaseRejected, match="unrelated_database"):
        store.initialize(require_existing=True)
    assert store.path.read_bytes() == before


def test_genuine_schema11_horizon_migration_preserves_private_preferences_and_history(tmp_path):
    from domus.domain.calendar_values import WeekStart
    from domus.infrastructure.sqlite_snapshots import _verify_database

    assert hashlib.sha256((FIXTURES / "v11.sql").read_bytes()).hexdigest() == (
        "52ab8c4a91322eaf9f56b547f20a4ca51f7a93426e6969dbc9f037d71d6fbe02"
    )
    store = frozen(tmp_path, 11)
    with store._connection() as connection:
        assert _verify_database(connection, store, previous=True) == 11
        tables = tuple(
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        )
    before = facts(store.path, tables)
    with pytest.raises(DatabaseRejected, match="unsupported_schema"), store.read():
        pass
    store.initialize(require_existing=True)
    restarted = SQLiteDatabase(store.path, store.installation)
    with restarted.read() as unit:
        assert unit.households.current().materialization_horizon_days == 60
        (member,) = unit.members.list("home")
        preference = unit.calendar_preferences.get("home", member.member_id)
        assert preference.week_start is WeekStart.SUNDAY and preference.revision == 2
    with restarted._connection() as connection:
        assert _verify_database(connection, restarted, previous=False) == 23
    assert facts(store.path, tables) == before


def test_failed_schema11_horizon_ddl_preserves_original_bytes(tmp_path, monkeypatch):
    from domus.infrastructure import sqlite as adapter

    store = frozen(tmp_path, 11)
    before = store.path.read_bytes()
    monkeypatch.setattr(
        adapter, "HOUSEHOLD_HORIZON_STATEMENT", "ALTER TABLE missing ADD COLUMN days"
    )
    with pytest.raises(StorageFailure, match="storage_failure"):
        store.initialize(require_existing=True)
    assert store.path.read_bytes() == before


def test_corrupt_persisted_horizon_blocks_reads_and_snapshot_inspection(tmp_path):
    from domus.infrastructure.sqlite_snapshots import _verify_database

    store = frozen(tmp_path, 11)
    store.initialize(require_existing=True)
    with store._connection() as connection:
        connection.execute("PRAGMA ignore_check_constraints=ON")
        connection.execute("UPDATE households SET materialization_horizon_days=6")
    before = store.path.read_bytes()
    with store.read() as unit, pytest.raises(StorageFailure, match="invalid_identity_record"):
        unit.households.current()
    with store._connection() as connection, pytest.raises(DatabaseRejected):
        _verify_database(connection, store, previous=False)
    assert store.path.read_bytes() == before


def test_schema12_fold_migration_preserves_horizon_and_rolls_back_failed_ddl(tmp_path, monkeypatch):
    from domus.domain.fold_policy import FoldPolicy
    from domus.infrastructure import sqlite as adapter
    from domus.infrastructure.sqlite_snapshots import _verify_database

    assert hashlib.sha256((FIXTURES / "v12.sql").read_bytes()).hexdigest() == (
        "b2dffe33b6d0ef7a84ab3120f5868e14d8196fafefacb0b37dc036bfcdc07073"
    )
    store = frozen(tmp_path, 12)
    with store._connection() as connection:
        connection.execute("UPDATE households SET materialization_horizon_days=31")
        assert _verify_database(connection, store, previous=True) == 12
    before = store.path.read_bytes()
    with monkeypatch.context() as patch:
        patch.setattr(adapter, "HOUSEHOLD_FOLD_STATEMENT", "ALTER TABLE missing ADD COLUMN fold")
        with pytest.raises(StorageFailure, match="storage_failure"):
            store.initialize(require_existing=True)
    assert store.path.read_bytes() == before
    store.initialize(require_existing=True)
    with store.read() as unit:
        home = unit.households.current()
        assert home.repeated_time is FoldPolicy.FIRST
        assert home.materialization_horizon_days == 31
    with store._connection() as connection:
        connection.execute("PRAGMA ignore_check_constraints=ON")
        connection.execute("UPDATE households SET repeated_time='unknown'")
    with store.read() as unit, pytest.raises(StorageFailure, match="invalid_identity_record"):
        unit.households.current()
