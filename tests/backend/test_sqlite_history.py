"""Retained operation facts prevent replay while checkpoint business state remains current."""

import sqlite3
from contextlib import closing
from dataclasses import replace
from pathlib import Path

import pytest
from test_household_commands import fixture
from test_restoration_values import record

from domus.domain.errors import Conflict, InvalidInput, StorageFailure
from domus.domain.storage import Installation, RestorationProvenance
from domus.infrastructure.sqlite import SCHEMA_VERSION, SQLiteDatabase
from domus.infrastructure.sqlite_history import SQLiteHistory, iter_operations


def install(store, values):
    with store._connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            SQLiteHistory(connection).install(values)
            connection.execute("COMMIT")
        except BaseException:
            connection.execute("ROLLBACK")
            raise


def test_historical_lookup_retains_original_result_and_never_enters_pending_delivery(tmp_path):
    _, store, _, _, _ = fixture(tmp_path / "database")
    original = record(current=False, archived_by="restore-1", position=8)
    install(store, [original])
    with store.read() as unit:
        receipt = unit.receipts.get(original.evidence.receipt.command)
        assert receipt.result == original.evidence.receipt.result
        assert receipt.historical and receipt.archived_by == "restore-1"
        assert unit.receipts.get_operation("home", "human", receipt.operation_id) == receipt
        assert unit.receipts.get_operation("home", "other", receipt.operation_id) is None
        assert unit.outbox.delivered(receipt.operation_id) is False
        assert unit.outbox.pending() == () and unit.audit.entries("home") == ()
        assert unit.audit.setup_actor("home") is None
        assert unit.households.current() is None
    with store.write() as unit:
        assert not unit.outbox.acknowledge(receipt.operation_id)
    with store._connection() as connection:
        assert tuple(iter_operations(connection)) == (original,)
        assert (
            connection.execute("SELECT seq FROM sqlite_sequence WHERE name='outbox'").fetchone()[0]
            == 8
        )


def test_import_requires_a_transaction_and_preserves_earlier_history_on_failure(tmp_path):
    _, store, _, _, _ = fixture(tmp_path / "database")
    a = record(current=False, archived_by="restore-1")
    b = record("b", current=False, archived_by="restore-2", position=2)
    with store._connection() as connection:
        with pytest.raises(StorageFailure):
            SQLiteHistory(connection).install([a])
    install(store, [a])
    with pytest.raises(Conflict):
        install(store, [b])
    with store._connection() as connection:
        assert tuple(iter_operations(connection)) == (a,)


@pytest.mark.parametrize("version", [1, 2, 3, 4])
def test_frozen_old_schema_migrates_without_losing_existing_evidence(tmp_path, version):
    path = tmp_path / "old.sqlite3"
    source = Path(__file__).resolve().parents[1] / f"fixtures/sqlite/v{version}.sql"
    with closing(sqlite3.connect(path, autocommit=True)) as connection:
        connection.executescript(source.read_text())
        before = {
            table: connection.execute(f"SELECT * FROM {table}").fetchall()
            for table in ("receipts", "audit", "outbox")
        }
        if version == 4:
            before["retained_operations"] = connection.execute(
                "SELECT * FROM retained_operations"
            ).fetchall()
    store = SQLiteDatabase(path, Installation("047cc6fb-dfb0-4fa4-b3c3-e0fe54d116b6", "edge"))
    store.initialize()
    with store._connection() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION == 6
        assert connection.execute("SELECT count(*) FROM retained_operations").fetchone()[0] == len(
            before.get("retained_operations", [])
        )
        for table, expected in before.items():
            assert [tuple(row) for row in connection.execute(f"SELECT * FROM {table}")] == expected


@pytest.mark.parametrize("current", [True, False])
def test_receipt_provenance_distinguishes_history_without_modifying_original_facts(current):
    original = record().evidence.receipt
    result = replace(original, restoration=RestorationProvenance("restore-1", current))
    assert result.historical is (not current) and result.archived_by == "restore-1"
    assert result.result == original.result and result.operation_id == original.operation_id
    assert original.restoration is None and not original.historical and original.archived_by is None
    with pytest.raises(InvalidInput):
        replace(record().evidence, receipt=result)


@pytest.mark.parametrize("restore_id,current", [("bad id", True), ("restore-1", 1)])
def test_invalid_provenance_is_not_an_operation_placement(restore_id, current):
    with pytest.raises(InvalidInput):
        RestorationProvenance(restore_id, current)


def test_nonmatching_placement_type_is_not_receipt_metadata():
    with pytest.raises(InvalidInput):
        replace(record().evidence.receipt, restoration={})


def test_new_snapshot_and_repeated_preparation_keep_historical_facts_and_last_receipt_time(
    tmp_path,
):
    from test_sqlite_snapshots import Clock

    from domus.infrastructure.sqlite_restoration import SQLiteRestorations
    from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots

    _, store, _, _, _ = fixture(tmp_path / "database")
    original = record(current=False, archived_by="restore-before", position=8, delivered=True)
    install(store, [original])
    archive = tmp_path / "snapshot"
    snapshots = SQLiteSnapshots(store, archive, store.installation, Clock())
    checkpoint = snapshots.create("with-history")
    assert checkpoint.last_committed_at == original.evidence.receipt.created_at
    assert snapshots.inspect() == checkpoint
    target = tmp_path / "prepared"
    adapter = SQLiteRestorations(store, archive, target, store.installation, Clock(), checkpoint)
    result = adapter.prepare("restore-again")
    assert result.operation_count == 1 and result.current_operations == 0 and result.highwater == 8
    assert adapter.inspect() == result


def current_fixture(tmp_path):
    from domus.application.household_commands import SetupHousehold

    commands, store, _, _, _ = fixture(tmp_path / "current.sqlite3")
    created = commands.setup("setup", SetupHousehold("Home", "UTC"))
    with store._connection() as connection:
        current = tuple(iter_operations(connection))
    return commands, store, created, current[0]


def test_current_import_keeps_provenance_and_acknowledgement_and_advances_next_position(tmp_path):
    commands, store, created, original = current_fixture(tmp_path)
    retained = replace(
        original, archived_by="first-archive", evidence=replace(original.evidence, delivered=True)
    )
    extra = record("z", current=False, archived_by="restore-2", position=8)
    values = sorted([retained, extra], key=lambda v: v.evidence.command_scope)
    install(store, values)
    with store.read() as unit:
        result = unit.receipts.get(created.command)
        assert not result.historical and result.archived_by == "first-archive"
        assert (
            unit.receipts.get_operation("home", created.command.actor_id, created.operation_id)
            == result
        )
        assert unit.outbox.delivered(created.operation_id) is True
        assert unit.outbox.pending() == ()
    install(store, values)
    commands.update("new", "New state", "UTC", 1)
    with store._connection() as connection:
        rows = tuple(iter_operations(connection))
        assert max(row.evidence.position for row in rows) == 9
    with store.read() as unit:
        assert len(unit.outbox.pending()) == 1 and len(unit.audit.entries("home")) == 2


def test_large_independent_result_audit_and_event_documents_survive_real_sqlite_history(tmp_path):
    from domus.domain.storage import JsonDocument

    _, store, _, _, _ = fixture(tmp_path / "database")
    original = record(current=False, archived_by="restore-1")
    fact = original.evidence
    document = JsonDocument.from_value({"value": "x" * 60_000})
    value = replace(
        original,
        evidence=replace(
            fact,
            receipt=replace(fact.receipt, result=document),
            audit=replace(fact.audit, detail=document),
            event=replace(fact.event, payload=document),
        ),
    )
    install(store, [value])
    with store._connection() as connection:
        assert tuple(iter_operations(connection)) == (value,)
