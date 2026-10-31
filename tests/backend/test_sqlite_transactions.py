"""Real files prove schema ownership, atomic transactions and durable replay facts."""

import hashlib
import sqlite3
import subprocess
import sys
import textwrap
from contextlib import closing
from pathlib import Path

import pytest

from domus.domain.errors import (
    Conflict,
    DatabaseRejected,
    InvalidInput,
    StorageBusy,
    StorageFailure,
)
from domus.domain.storage import (
    AuditEntry,
    CommandKey,
    Household,
    Installation,
    JsonDocument,
    OutboxEvent,
    Receipt,
)
from domus.infrastructure.sqlite import SQLiteDatabase

IDENTITY = Installation("047cc6fb-dfb0-4fa4-b3c3-e0fe54d116b6", "edge")
KEY = CommandKey("home", "ha_1", "household.create", "request-1")
RESULT = JsonDocument.from_value({"household_id": "home", "revision": 1})


def database(path: Path) -> SQLiteDatabase:
    store = SQLiteDatabase(path, IDENTITY, busy_timeout=0.05)
    store.initialize()
    return store


def receipt(key: CommandKey = KEY, operation_id: str = "operation-1") -> Receipt:
    return Receipt(key, "a" * 64, operation_id, RESULT, 100)


def test_committed_household_receipt_audit_and_outbox_survive_reopen(tmp_path: Path) -> None:
    path = tmp_path / "domus.sqlite3"
    store = database(path)
    with store.write() as unit:
        unit.households.save(Household("home", "Family home", "Europe/Madrid", 1), 0)
        unit.receipts.add(receipt())
        unit.audit.append(AuditEntry("operation-1", KEY, RESULT, 100))
        unit.outbox.append(OutboxEvent("operation-1", "home", KEY.action, RESULT, 100))
    reopened = SQLiteDatabase(path, IDENTITY)
    reopened.initialize()
    with reopened.read() as unit:
        assert unit.households.get("home") == Household("home", "Family home", "Europe/Madrid", 1)
        assert unit.households.current() == unit.households.get("home")
        assert unit.receipts.get(KEY) == receipt()
        assert unit.receipts.get_operation("home", "ha_1", "operation-1") == receipt()
        assert unit.audit.entries("home") == (AuditEntry("operation-1", KEY, RESULT, 100),)
        assert unit.outbox.pending() == (
            OutboxEvent("operation-1", "home", KEY.action, RESULT, 100),
        )


@pytest.mark.parametrize("after", ["household", "receipt", "audit", "outbox"])
def test_business_exception_rolls_back_every_fact(tmp_path: Path, after: str) -> None:
    store = database(tmp_path / "domus.sqlite3")
    with pytest.raises(RuntimeError, match="effect failed"):
        with store.write() as unit:
            unit.households.save(Household("home", "Home", "UTC", 1), 0)
            if after != "household":
                unit.receipts.add(receipt())
            if after in ("audit", "outbox"):
                unit.audit.append(AuditEntry("operation-1", KEY, RESULT, 100))
            if after == "outbox":
                unit.outbox.append(OutboxEvent("operation-1", "home", KEY.action, RESULT, 100))
            raise RuntimeError("effect failed")
    with store.read() as unit:
        assert unit.households.current() is None
        assert unit.receipts.get(KEY) is None
        assert unit.audit.entries("home") == ()
        assert unit.outbox.pending() == ()


def test_cancellation_rolls_back_and_releases_the_writer(tmp_path: Path) -> None:
    store = database(tmp_path / "domus.sqlite3")
    with pytest.raises(KeyboardInterrupt):
        with store.write() as unit:
            unit.households.save(Household("home", "Home", "UTC", 1), 0)
            raise KeyboardInterrupt
    with store.write() as unit:
        assert unit.households.current() is None
        unit.households.save(Household("home", "Home", "UTC", 1), 0)


def test_expected_revision_prevents_lost_updates_and_second_household(tmp_path: Path) -> None:
    store = database(tmp_path / "domus.sqlite3")
    with store.write() as unit:
        unit.households.save(Household("home", "First", "UTC", 1), 0)
    with store.write() as unit:
        unit.households.save(Household("home", "Second", "UTC", 2), 1)
    with pytest.raises(Conflict, match="revision_conflict"):
        with store.write() as unit:
            unit.households.save(Household("home", "Lost update", "UTC", 2), 1)
    with pytest.raises(Conflict, match="household_exists"):
        with store.write() as unit:
            unit.households.save(Household("another", "Another", "UTC", 1), 0)
    with store.read() as unit:
        assert unit.households.get("home").name == "Second"
        assert unit.households.get("another") is None


def test_receipt_scope_is_not_an_operation_key_capability(tmp_path: Path) -> None:
    store = database(tmp_path / "domus.sqlite3")
    with store.write() as unit:
        unit.households.save(Household("home", "Home", "UTC", 1), 0)
        unit.receipts.add(receipt())
    with store.read() as unit:
        assert unit.receipts.get(CommandKey("other", "ha_1", KEY.action, KEY.key)) is None
        assert unit.receipts.get(CommandKey("home", "ha_2", KEY.action, KEY.key)) is None
        assert unit.receipts.get(CommandKey("home", "ha_1", "other.action", KEY.key)) is None
        assert unit.receipts.get_operation("home", "ha_2", "operation-1") is None
        assert unit.receipts.get_operation("other", "ha_1", "operation-1") is None


def test_constraint_failure_rolls_back_without_driver_text(tmp_path: Path) -> None:
    store = database(tmp_path / "domus.sqlite3")
    with pytest.raises(StorageFailure) as caught:
        with store.write() as unit:
            unit.households.save(Household("home", "private title", "UTC", 1), 0)
            unit.receipts.add(receipt())
            unit.receipts.add(receipt())
    assert str(caught.value) == "storage_failure"
    assert "private title" not in repr(caught.value)
    with store.read() as unit:
        assert unit.households.current() is None
        assert unit.receipts.get(KEY) is None


def test_reader_cannot_write_and_an_external_writer_returns_bounded_busy(tmp_path: Path) -> None:
    store = database(tmp_path / "domus.sqlite3")
    with pytest.raises(StorageFailure):
        with store.read() as unit:
            unit.households.save(Household("home", "Home", "UTC", 1), 0)
    with store.write():
        with pytest.raises(StorageBusy, match="storage_busy"):
            with store.write():
                pytest.fail("A second independent writer was admitted")
    with store.read() as unit:
        assert unit.households.current() is None


@pytest.mark.parametrize(
    "change", ["future", "unrelated", "missing_metadata", "wrong_channel", "wrong_instance"]
)
def test_schema_and_ownership_rejection_happens_before_file_writes(
    tmp_path: Path, change: str
) -> None:
    path = tmp_path / "domus.sqlite3"
    database(path)
    with closing(sqlite3.connect(path, autocommit=True)) as connection:
        if change == "future":
            connection.execute("PRAGMA user_version=999")
        elif change == "unrelated":
            connection.execute("PRAGMA application_id=1")
        elif change == "missing_metadata":
            connection.execute("DELETE FROM installation")
        elif change == "wrong_channel":
            connection.execute("UPDATE installation SET channel='stable'")
        else:
            connection.execute(
                "UPDATE installation SET instance_id='10000000-0000-0000-0000-000000000001'"
            )
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(DatabaseRejected):
        SQLiteDatabase(path, IDENTITY).initialize()
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_unversioned_foreign_database_and_non_database_are_not_adopted(tmp_path: Path) -> None:
    path = tmp_path / "foreign.sqlite3"
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("CREATE TABLE unrelated(value TEXT)")
    before = path.read_bytes()
    with pytest.raises(DatabaseRejected):
        SQLiteDatabase(path, IDENTITY).initialize()
    assert path.read_bytes() == before
    invalid = tmp_path / "not-sqlite"
    invalid.write_text("unrelated private file")
    with pytest.raises(DatabaseRejected):
        SQLiteDatabase(invalid, IDENTITY).initialize()
    assert invalid.read_text() == "unrelated private file"


def test_partial_initial_migration_is_rolled_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from domus.infrastructure import sqlite as adapter

    path = tmp_path / "domus.sqlite3"
    with monkeypatch.context() as patch:
        patch.setattr(adapter, "SCHEMA_STATEMENTS", (*adapter.SCHEMA_STATEMENTS, "INVALID SQL"))
        with pytest.raises(StorageFailure):
            SQLiteDatabase(path, IDENTITY).initialize()
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 0
        assert (
            connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == []
        )
    database(path)


def test_outbox_acknowledgement_is_durable_and_duplicate_safe(tmp_path: Path) -> None:
    path = tmp_path / "domus.sqlite3"
    store = database(path)
    with store.write() as unit:
        unit.households.save(Household("home", "Home", "UTC", 1), 0)
        unit.outbox.append(OutboxEvent("event-1", "home", "household.created", RESULT, 100))
    with store.write() as unit:
        assert unit.outbox.acknowledge("event-1")
        assert not unit.outbox.acknowledge("event-1")
        assert not unit.outbox.acknowledge("unknown")
    with database(path).read() as unit:
        assert unit.outbox.pending() == ()


@pytest.mark.parametrize("timeout", [0, -1, 6, float("inf"), float("nan")])
def test_writer_wait_is_a_finite_bounded_configuration(tmp_path: Path, timeout: float) -> None:
    with pytest.raises(InvalidInput, match="invalid_storage_timeout"):
        SQLiteDatabase(tmp_path / "database", IDENTITY, busy_timeout=timeout)


def test_missing_parent_or_removed_database_is_a_safe_storage_failure(tmp_path: Path) -> None:
    with pytest.raises(StorageFailure, match="storage_failure"):
        SQLiteDatabase(tmp_path / "missing" / "database", IDENTITY).initialize()
    path = tmp_path / "database"
    store = database(path)
    path.unlink()
    with pytest.raises(StorageFailure, match="storage_failure"):
        with store.read():
            pytest.fail("Read must not silently recreate a removed database")
    assert not path.exists()


def test_initialization_also_obeys_the_existing_writer_budget(tmp_path: Path) -> None:
    path = tmp_path / "database"
    store = database(path)
    with store.write():
        with pytest.raises(StorageBusy, match="storage_busy"):
            SQLiteDatabase(path, IDENTITY, busy_timeout=0.01).initialize()


def test_invalid_revision_step_and_outbox_limits_have_no_effect(tmp_path: Path) -> None:
    store = database(tmp_path / "database")
    with pytest.raises(Conflict, match="revision_conflict"):
        with store.write() as unit:
            unit.households.save(Household("home", "Home", "UTC", 3), 0)
    with store.read() as unit:
        for limit in (0, -1, 201, True):
            with pytest.raises(InvalidInput, match="invalid_page_size"):
                unit.outbox.pending(limit)
        assert unit.households.current() is None


def test_initialization_rechecks_ownership_after_obtaining_the_writer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "database"
    store = database(path)
    inspect = store._inspect
    first = True

    def change_after_preflight(
        connection: sqlite3.Connection, *, allow_empty: bool = False, allow_previous: bool = False
    ) -> int:
        nonlocal first
        result = inspect(connection, allow_empty=allow_empty, allow_previous=allow_previous)
        if first:
            first = False
            with closing(sqlite3.connect(path, autocommit=True)) as external:
                external.execute("UPDATE installation SET channel='stable'")
        return result

    monkeypatch.setattr(store, "_inspect", change_after_preflight)
    with pytest.raises(DatabaseRejected, match="installation_mismatch"):
        store.initialize()


def test_display_text_is_bound_as_data_instead_of_executed_as_sql(tmp_path: Path) -> None:
    store = database(tmp_path / "database")
    name = "Home'); DROP TABLE outbox; --"
    with store.write() as unit:
        unit.households.save(Household("home", name, "UTC", 1), 0)
    with store.read() as unit:
        assert unit.households.get("home").name == name
        assert unit.outbox.pending() == ()


def test_separate_process_observes_bounded_busy_then_committed_revision(tmp_path: Path) -> None:
    path = tmp_path / "database"
    store = database(path)
    with store.write() as unit:
        unit.households.save(Household("home", "Initial", "UTC", 1), 0)
    script = textwrap.dedent("""
        import sys
        from pathlib import Path
        from domus.domain.errors import DomusError
        from domus.domain.storage import Household, Installation
        from domus.infrastructure.sqlite import SQLiteDatabase
        store = SQLiteDatabase(Path(sys.argv[1]),
            Installation('047cc6fb-dfb0-4fa4-b3c3-e0fe54d116b6','edge'), busy_timeout=0.01)
        try:
            with store.write() as unit:
                unit.households.save(Household('home','Child','UTC',2),1)
        except DomusError as error:
            print(error.code)
        else:
            print('committed')
    """)
    with store.write() as unit:
        unit.households.save(Household("home", "Parent", "UTC", 2), 1)
        busy = subprocess.run(
            [sys.executable, "-c", script, str(path)],
            text=True,
            capture_output=True,
            check=True,
            timeout=5,
        )
        assert busy.stdout.strip() == "storage_busy"
    conflict = subprocess.run(
        [sys.executable, "-c", script, str(path)],
        text=True,
        capture_output=True,
        check=True,
        timeout=5,
    )
    assert conflict.stdout.strip() == "revision_conflict"
    with store.read() as unit:
        assert unit.households.get("home").name == "Parent"


def test_process_death_cannot_commit_partial_business_or_replay_facts(tmp_path: Path) -> None:
    path = tmp_path / "database"
    store = database(path)
    with store.write() as unit:
        unit.households.save(Household("home", "Before crash", "UTC", 1), 0)
    script = textwrap.dedent("""
        import os, sys
        from pathlib import Path
        from domus.domain.storage import (
            AuditEntry, CommandKey, Household, Installation, JsonDocument, OutboxEvent, Receipt)
        from domus.infrastructure.sqlite import SQLiteDatabase
        store = SQLiteDatabase(Path(sys.argv[1]),
            Installation('047cc6fb-dfb0-4fa4-b3c3-e0fe54d116b6','edge'))
        key = CommandKey('home','ha_1','household.rename','crash')
        document = JsonDocument.from_value({'revision':2})
        with store.write() as unit:
            unit.households.save(Household('home','Uncommitted','UTC',2),1)
            unit.receipts.add(Receipt(key,'a'*64,'crash-operation',document,100))
            unit.audit.append(AuditEntry('crash-operation',key,document,100))
            unit.outbox.append(OutboxEvent('crash-operation','home',key.action,document,100))
            os._exit(23)
    """)
    crashed = subprocess.run(
        [sys.executable, "-c", script, str(path)],
        text=True,
        capture_output=True,
        check=False,
        timeout=5,
    )
    assert crashed.returncode == 23, crashed.stderr
    with database(path).read() as unit:
        assert unit.households.get("home").name == "Before crash"
        assert unit.households.get("home").revision == 1
        assert unit.receipts.get(CommandKey("home", "ha_1", "household.rename", "crash")) is None
        assert unit.audit.entries("home") == ()
        assert unit.outbox.pending() == ()
