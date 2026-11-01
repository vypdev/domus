"""Original schema-6 evidence, causal indexes and offline restore retain original business facts."""

import hashlib
import sqlite3
from contextlib import closing
from dataclasses import replace
from pathlib import Path

import pytest
from test_task_queries import queries
from test_task_reviews import reopen, setup

from domus.application.task_requests import ReviewTaskDependency
from domus.domain.errors import DatabaseRejected, InvalidInput, StorageFailure
from domus.domain.identity import HumanIdentity
from domus.domain.storage import Installation
from domus.infrastructure.sqlite import SQLiteDatabase

INSTALLATION = Installation("047cc6fb-dfb0-4fa4-b3c3-e0fe54d116b6", "edge")


def frozen(path):
    source = Path(__file__).resolve().parents[1] / "fixtures/sqlite/v6.sql"
    assert hashlib.sha256(source.read_bytes()).hexdigest() == (
        "af84ed25f3bf5ffe7da5a8f1b9ff8163bd2aa27641283aa79c0c60edd5927f11"
    )
    with closing(sqlite3.connect(path, autocommit=True)) as connection:
        connection.executescript(source.read_text())
    return SQLiteDatabase(path, INSTALLATION)


def rows(connection):
    return {
        row[0]: [tuple(item) for item in connection.execute('SELECT * FROM "' + row[0] + '"')]
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }


def test_original_schema6_migration_adds_only_indexes_and_projects_existing_cause(tmp_path):
    store = frozen(tmp_path / "old.sqlite3")
    with store._connection() as connection:
        original = rows(connection)
    with pytest.raises(DatabaseRejected), store.read():
        pytest.fail("Old storage requires explicit migration")
    store.initialize(require_existing=True)
    with store._connection() as connection:
        assert rows(connection) == original
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 7
    service = queries(store, HumanIdentity("ha_admin", True, True, False))
    detail = service.occurrence("identity-15")
    assert detail.dependency_review_required and len(detail.dependency_reviews.items) == 1
    cause = detail.dependency_reviews.items[0].cause
    assert cause.source_operation_id == "identity-20"
    assert cause.source_cycle_id == "identity-8"
    assert not detail.dependency_reviews.items[0].source_satisfies_gate
    assert detail.cycle.rules.dependency_gate.value == "approved"
    with store.read() as unit:
        assert unit.task_materials.get("home", "identity-9").posting.quantity.value == "3"
        assert unit.tasks.cycle("home", "identity-21") is None
        assert unit.tasks.operation("home", "ha_child", "identity-24").current is False
    store.initialize(require_existing=True)


def test_schema6_failed_index_migration_rolls_back_exact_database_bytes(tmp_path, monkeypatch):
    from domus.infrastructure import sqlite as adapter

    store = frozen(tmp_path / "old.sqlite3")
    before = store.path.read_bytes()
    with monkeypatch.context() as patch:
        patch.setattr(adapter, "REVIEW_STATEMENTS", (*adapter.REVIEW_STATEMENTS, "INVALID SQL"))
        with pytest.raises(StorageFailure):
            store.initialize(require_existing=True)
    assert store.path.read_bytes() == before
    with store._connection() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 6
    store.initialize(require_existing=True)


@pytest.mark.parametrize("stage", ["before_reopening", "before_acceptance"])
def test_restore_retains_historical_acceptance_without_clearing_restored_alert(tmp_path, stage):
    from test_activation_compatibility import identity_at
    from test_sqlite_snapshots import Clock

    from domus.infrastructure.owned_storage import open_storage
    from domus.infrastructure.sqlite_activation import SQLiteActivation
    from domus.infrastructure.sqlite_restoration import SQLiteRestorations
    from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots

    root = tmp_path / "source"
    root.mkdir(mode=0o700)
    commands, store, actor, _, source, target, _, _, done = setup(root)
    identity_at(root, store.installation)
    snapshots = SQLiteSnapshots(store, tmp_path / "archive", store.installation, Clock())
    if stage == "before_reopening":
        checkpoint = snapshots.create("before")
    opened = reopen(commands, store, source, "reopen-source")
    cid = done.result.decode()["cycle"]["cycle_id"]
    if stage == "before_acceptance":
        checkpoint = snapshots.create("before")
    request = ReviewTaskDependency(target, 1, cid, opened.operation_id, "Work remains valid")
    receipt = commands.review_dependency("accept", request)
    SQLiteRestorations(
        store, tmp_path / "archive", tmp_path / "prepared", store.installation, Clock(), checkpoint
    ).prepare("restore-review")
    assert (
        SQLiteActivation(root, store.installation, Clock(), tmp_path / "prepared").activate().state
        == "active"
    )
    selected = open_storage(root, "edge")
    try:
        commands = replace(commands, transactions=selected.database)
        recovered = commands.review_dependency("accept", request)
        assert recovered.historical and recovered.operation_id == receipt.operation_id
        assert recovered.result == receipt.result
        service = queries(selected.database, actor.current())
        assert service.operation(receipt.operation_id).receipt.historical
        detail = service.occurrence(target)
        assert detail.work.current_cycle_id == cid
        assert detail.dependency_review_required == (stage == "before_acceptance")
        assert all(row.state.value == "pending" for row in detail.dependency_reviews.items)
        assert any(
            row.operation_id == receipt.operation_id and row.historical
            for row in service.history(target).items
        )
    finally:
        selected.close()


@pytest.mark.parametrize(
    "values",
    [
        {"limit": True},
        {"limit": 0},
        {"limit": 102},
        {"after": True},
        {"after": -1},
        {"after": 2**63},
        {"state": "pending"},
        {"source_operation_id": "bad/id"},
    ],
)
def test_review_storage_rejects_invalid_bounded_query_values(tmp_path, values):
    _, store, _, _, _, target, _, _, done = setup(tmp_path)
    with store.read() as unit:
        with pytest.raises(InvalidInput):
            unit.tasks.review_evidence(
                "home", target, done.result.decode()["cycle"]["cycle_id"], **values
            )


@pytest.mark.parametrize(
    "column,value",
    [
        ("audit.household_id", "other"),
        ("audit.actor_id", "other"),
        ("audit.action", "other"),
        ("audit.command_key", "other"),
        ("audit.created_at", 101),
        ("outbox.household_id", "other"),
        ("outbox.event_type", "other"),
        ("outbox.created_at", 101),
    ],
)
def test_review_evidence_rejects_incoherent_raw_headers(tmp_path, column, value):
    commands, store, actor, _, source, target, _, _, done = setup(tmp_path)
    opened = reopen(commands, store, source, "reopen-source")
    table, field = column.split(".")
    with store._connection() as connection:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute(
            f"UPDATE {table} SET {field}=? WHERE "
            + ("operation_id" if table == "audit" else "event_id")
            + "=?",
            (value, opened.operation_id),
        )
    with pytest.raises(StorageFailure):
        queries(store, actor.current()).dependency_reviews(
            target, done.result.decode()["cycle"]["cycle_id"]
        )


@pytest.mark.parametrize("missing", ["completion", "source_reopening"])
def test_missing_original_proof_never_hides_a_required_review(tmp_path, missing):
    commands, store, actor, _, source, target, _, _, done = setup(tmp_path)
    opened = reopen(commands, store, source, "reopen-source")
    with store._connection() as connection:
        connection.execute(
            "DELETE FROM outbox WHERE event_id=?",
            (done.operation_id if missing == "completion" else opened.operation_id,),
        )
    with pytest.raises(StorageFailure):
        queries(store, actor.current()).dependency_reviews(
            target, done.result.decode()["cycle"]["cycle_id"]
        )


def test_duplicate_completion_evidence_is_rejected_before_projection(tmp_path):
    _, store, actor, _, _, target, _, _, done = setup(tmp_path)
    with store._connection() as connection:
        for table, identity in (
            ("receipts", "operation_id"),
            ("audit", "operation_id"),
            ("outbox", "event_id"),
        ):
            original = dict(
                connection.execute(
                    f"SELECT * FROM {table} WHERE {identity}=?", (done.operation_id,)
                ).fetchone()
            )
            original[identity] = "duplicate-operation"
            if table == "outbox":
                del original["position"]
            else:
                original["command_key"] = "duplicate-completion"
            connection.execute(
                f"INSERT INTO {table}("
                + ",".join(original)
                + ") VALUES("
                + ",".join("?" for _ in original)
                + ")",
                tuple(original.values()),
            )
    with pytest.raises(StorageFailure):
        queries(store, actor.current()).dependency_reviews(
            target, done.result.decode()["cycle"]["cycle_id"]
        )


def test_storage_rejects_malformed_original_dependencies_and_empty_ones_need_no_scan(tmp_path):
    _, store, actor, _, source, target, _, source_done, done = setup(tmp_path)
    service = queries(store, actor.current())
    assert (
        service.dependency_reviews(source, source_done.result.decode()["cycle"]["cycle_id"]).items
        == ()
    )
    with store._connection() as connection:
        result = done.result.decode()
        result["prerequisite_ids"] = None
        from domus.domain.storage import JsonDocument

        connection.execute(
            "UPDATE receipts SET result=? WHERE operation_id=?",
            (JsonDocument.from_value(result).encoded, done.operation_id),
        )
    with pytest.raises(StorageFailure):
        service.dependency_reviews(target, done.result.decode()["cycle"]["cycle_id"])


def test_acknowledged_transport_events_still_project_live_review_causes(tmp_path):
    commands, store, actor, _, source, target, _, _, done = setup(tmp_path)
    opened = reopen(commands, store, source, "reopen-source")
    service = queries(store, actor.current())
    cid = done.result.decode()["cycle"]["cycle_id"]
    before = service.dependency_reviews(target, cid)
    with store.write() as unit:
        assert unit.outbox.acknowledge(opened.operation_id)
    assert service.dependency_reviews(target, cid) == before


def test_original_schema6_checkpoint_activation_migrates_only_the_prepared_target(tmp_path):
    from test_activation_compatibility import identity_at
    from test_sqlite_snapshots import Clock

    from domus.domain.snapshots import Snapshot
    from domus.infrastructure.owned_storage import open_storage
    from domus.infrastructure.sqlite_activation import SQLiteActivation
    from domus.infrastructure.sqlite_history import last_committed_at
    from domus.infrastructure.sqlite_restoration import SQLiteRestorations
    from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots

    archive, root, target = tmp_path / "archive", tmp_path / "source", tmp_path / "prepared"
    archive.mkdir(mode=0o700)
    root.mkdir(mode=0o700)
    old = frozen(archive / "domus.sqlite3")
    old.path.chmod(0o600)
    identity = identity_at(archive, INSTALLATION)
    with old._connection() as connection:
        committed = last_committed_at(connection)
    checkpoint = Snapshot(
        "original-six",
        INSTALLATION,
        6,
        2000,
        committed,
        hashlib.sha256(old.path.read_bytes()).hexdigest(),
        old.path.stat().st_size,
        hashlib.sha256(identity.read_bytes()).hexdigest(),
    )
    manifest = archive / "manifest.json"
    manifest.write_text(checkpoint.document().encoded)
    manifest.chmod(0o600)
    assert SQLiteSnapshots(None, archive, INSTALLATION, Clock()).inspect() == checkpoint
    source = root / "domus.sqlite3"
    source.write_bytes(old.path.read_bytes())
    source.chmod(0o600)
    identity_at(root, INSTALLATION)
    before = source.read_bytes()
    prepared = SQLiteRestorations(
        SQLiteDatabase(source, INSTALLATION), archive, target, INSTALLATION, Clock(), checkpoint
    ).prepare("upgrade-reviews")
    assert prepared.source.schema_version == 6
    result = SQLiteActivation(root, INSTALLATION, Clock(), target).activate()
    assert result.state == "active" and result.record.rollback_snapshot.schema_version == 6
    assert source.read_bytes() == before == old.path.read_bytes()
    selected = open_storage(root, "edge")
    try:
        detail = queries(
            selected.database, HumanIdentity("ha_admin", True, True, False)
        ).occurrence("identity-15")
        assert (
            detail.dependency_review_required
            and detail.dependency_reviews.items[0].cause.source_operation_id == "identity-20"
        )
        assert (
            SQLiteSnapshots(selected.database, tmp_path / "new-checkpoint", INSTALLATION, Clock())
            .create("new")
            .schema_version
            == 7
        )
    finally:
        selected.close()
