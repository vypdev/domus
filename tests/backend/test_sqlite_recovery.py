"""Durable recovery state is scoped, immutable in its binding and migrated atomically."""

import sqlite3
from contextlib import closing
from dataclasses import replace
from pathlib import Path

import pytest
from test_recovery_values import INSTALLATION, request

from domus.domain.errors import Conflict, InvalidInput, StorageFailure
from domus.domain.identity import AdministratorMapping, MappingMode
from domus.domain.storage import CommandKey, Household
from domus.infrastructure.sqlite import SCHEMA_VERSION, SQLiteDatabase


def storage(path: Path) -> SQLiteDatabase:
    database = SQLiteDatabase(path, INSTALLATION)
    database.initialize()
    with database.write() as unit:
        unit.households.save(Household("home", "Home", "UTC", 1), 0)
    return database


def test_recovery_roundtrip_preserves_binding_and_optimistic_state(tmp_path: Path) -> None:
    store = storage(tmp_path / "database")
    value = request()
    with store.write() as unit:
        assert unit.recoveries.get("home", "missing") is None
        unit.recoveries.save(value, 0)
    with store.read() as unit:
        assert unit.recoveries.get("home", value.request_id) == value
        assert unit.recoveries.get("other", value.request_id) is None
    approved = value.approve(2000)
    with store.write() as unit:
        unit.recoveries.save(approved, 1)
    reopened = SQLiteDatabase(store.path, INSTALLATION)
    reopened.initialize(require_existing=True)
    with reopened.read() as unit:
        assert unit.recoveries.get("home", value.request_id) == approved
    with store.write() as unit:
        unit.recoveries.save(approved.consume(3000), 2)
    with store.read() as unit:
        assert unit.recoveries.get("home", value.request_id).state.value == "consumed"


def test_stale_duplicate_retargeted_and_missing_recovery_updates_do_not_mutate(
    tmp_path: Path,
) -> None:
    store = storage(tmp_path / "database")
    value = request()
    with store.write() as unit:
        unit.recoveries.save(value, 0)
    changes = [
        (value, 0, "recovery_exists"),
        (value.approve(2000), 2, "revision_conflict"),
        (replace(value.approve(2000), request_id="missing"), 1, "revision_conflict"),
        (
            replace(
                value.approve(2000), mapping=AdministratorMapping(MappingMode.SELECTED, "other")
            ),
            1,
            "recovery_binding_changed",
        ),
    ]
    for changed, expected, reason in changes:
        with pytest.raises(Conflict, match=reason):
            with store.write() as unit:
                unit.recoveries.save(changed, expected)
        with store.read() as unit:
            assert unit.recoveries.get("home", value.request_id) == value
    with store.write() as unit:
        unit.recoveries.save(value.approve(2000), 1)
    with pytest.raises(Conflict, match="revision_conflict"):
        with store.write() as unit:
            unit.recoveries.save(value.approve(2000), 1)


def test_pending_recovery_inventory_is_bounded_scoped_and_excludes_expired_or_terminal(
    tmp_path: Path,
) -> None:
    store = storage(tmp_path / "database")
    a = request()
    b = replace(request(), request_id="b", target_ha_user_id="other").approve(2000)
    c = replace(request(), request_id="c").cancel(3000)
    d = replace(request(), request_id="d").approve(2000).consume(3000)
    with store.write() as unit:
        for value in (
            a,
            replace(b, state=a.state, revision=1, approved_at=None, expires_at=a.expires_at),
            replace(c, state=a.state, revision=1, closed_at=None),
            replace(
                d,
                state=a.state,
                revision=1,
                approved_at=None,
                closed_at=None,
                expires_at=a.expires_at,
            ),
        ):
            unit.recoveries.save(value, 0)
        unit.recoveries.save(b, 1)
        unit.recoveries.save(c, 1)
        unit.recoveries.save(replace(d, state=b.state, revision=2, closed_at=None), 1)
        unit.recoveries.save(d, 2)
    with store.read() as unit:
        assert unit.recoveries.pending("home", 3000) == (b, a)
        assert unit.recoveries.pending("home", 3000, limit=1) == (b,)
        assert unit.recoveries.pending("other", 3000) == ()
        assert unit.recoveries.pending("home", 601000) == (b,)
        assert unit.recoveries.pending("home", 602000) == ()
        assert unit.recoveries.pending("home", 999) == ()
        for limit in (True, 0, 258):
            with pytest.raises(InvalidInput, match="invalid_page_size"):
                unit.recoveries.pending("home", 3000, limit=limit)


@pytest.mark.parametrize("fragment", ["not JSON", "{}", "[]", '{"unexpected":true}'])
def test_invalid_stored_document_is_not_silently_skipped(tmp_path: Path, fragment: str) -> None:
    store = storage(tmp_path / "database")
    with store.write() as unit:
        unit.recoveries.save(request(), 0)
    with closing(sqlite3.connect(store.path, autocommit=True)) as connection:
        connection.execute("UPDATE recovery_requests SET detail=?", (fragment,))
    with pytest.raises(StorageFailure, match="invalid_recovery_record"):
        with store.read() as unit:
            unit.recoveries.get("home", "request")


def test_stored_index_and_complete_document_must_agree(tmp_path: Path) -> None:
    store = storage(tmp_path / "database")
    with store.write() as unit:
        unit.recoveries.save(request(), 0)
    with closing(sqlite3.connect(store.path, autocommit=True)) as connection:
        connection.execute("UPDATE recovery_requests SET target_ha_user_id='wrong'")
    with pytest.raises(StorageFailure, match="invalid_recovery_record"):
        with store.read() as unit:
            unit.recoveries.pending("home", 3000)


@pytest.mark.parametrize("version", [1, 2])
def test_compatible_migration_preserves_identity_history_and_adds_empty_recovery(
    tmp_path: Path, version: int
) -> None:
    path = tmp_path / "database"
    fixture = Path(__file__).resolve().parents[1] / f"fixtures/sqlite/v{version}.sql"
    with closing(sqlite3.connect(path, autocommit=True)) as connection:
        connection.executescript(fixture.read_text())
    store = SQLiteDatabase(path, INSTALLATION)
    store.initialize(require_existing=True)
    with store.read() as unit:
        assert unit.households.current().name == "Existing household"
        assert (
            unit.receipts.get(
                CommandKey("home", "ha_1", "household.rename", "old-key")
            ).operation_id
            == "old-operation"
        )
        assert unit.audit.entries("home")[0].operation_id == "old-operation"
        assert unit.outbox.pending()[0].event_id == "old-operation"
        assert unit.recoveries.pending("home", 3000) == ()
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION == 6


def test_failed_v2_upgrade_rolls_back_all_new_schema_and_replay_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from domus.infrastructure import sqlite

    path = tmp_path / "database"
    fixture = Path(__file__).resolve().parents[1] / "fixtures/sqlite/v2.sql"
    with closing(sqlite3.connect(path, autocommit=True)) as connection:
        connection.executescript(fixture.read_text())
    monkeypatch.setattr(sqlite, "RECOVERY_STATEMENTS", (*sqlite.RECOVERY_STATEMENTS, "INVALID SQL"))
    with pytest.raises(StorageFailure):
        SQLiteDatabase(path, INSTALLATION).initialize(require_existing=True)
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        assert (
            connection.execute(
                "SELECT count(*) FROM sqlite_master WHERE name='recovery_requests'"
            ).fetchone()[0]
            == 0
        )
        assert (
            connection.execute("SELECT operation_id FROM receipts").fetchone()[0] == "old-operation"
        )


def test_persisted_approval_time_and_deadline_cannot_be_extended_when_consuming(
    tmp_path: Path,
) -> None:
    store = storage(tmp_path / "database")
    value = request()
    approved = value.approve(2000)
    with store.write() as unit:
        unit.recoveries.save(value, 0)
        unit.recoveries.save(approved, 1)
    forged = replace(approved.consume(4000), approved_at=3000, expires_at=603000)
    with pytest.raises(Conflict, match="recovery_binding_changed"):
        with store.write() as unit:
            unit.recoveries.save(forged, 2)
    with store.read() as unit:
        assert unit.recoveries.get("home", value.request_id) == approved
