"""A prepared restore seals old business state plus later evidence and never starts a server."""

import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from test_sqlite_snapshots import Clock, configured

from domus.domain.errors import Conflict, DatabaseRejected, DomusError, InvalidInput, StorageFailure
from domus.domain.storage import Installation
from domus.infrastructure import sqlite_restoration
from domus.infrastructure.owned_storage import attach_storage, open_storage
from domus.infrastructure.sqlite import SQLiteDatabase
from domus.infrastructure.sqlite_restoration import SQLiteRestorations


def fixture(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir(mode=0o700)
    snapshots, commands, store, archive = configured(source)
    checkpoint = snapshots.create("checkpoint-1")
    commands.update("later", "Later state", "UTC", 1)
    target = tmp_path / "prepared"
    adapter = SQLiteRestorations(store, archive, target, store.installation, Clock(), checkpoint)
    return adapter, store, archive, target


def inspect_at(target, installation):
    return SQLiteRestorations(None, None, target, installation, Clock()).inspect()


def test_preparation_seals_checkpoint_bytes_and_complete_later_history_without_source_mutation(
    tmp_path,
):
    adapter, store, archive, target = fixture(tmp_path)
    source_before = store.path.read_bytes()
    archive_before = {p.name: p.read_bytes() for p in archive.iterdir()}
    result = adapter.prepare("restore-1")
    assert result == inspect_at(target, store.installation)
    assert result.operation_count == result.highwater == 2 and result.current_operations == 1
    assert result.checkpoint == adapter.checkpoint
    assert (target / "domus.sqlite3").read_bytes() == (archive / "domus.sqlite3").read_bytes()
    assert source_before == store.path.read_bytes()
    assert archive_before == {p.name: p.read_bytes() for p in archive.iterdir()}
    assert json.loads((target / "installation.json").read_text())["state"] == "restore_pending"
    rows = [json.loads(line) for line in (target / "operations.jsonl").read_text().splitlines()]
    assert [row["current"] for row in rows] == [True, False]
    assert rows[1]["archived_by"] == "restore-1"
    with SQLiteDatabase(target / "domus.sqlite3", store.installation).read() as unit:
        assert unit.households.current().name == "Home"
        assert len(unit.audit.entries("home")) == 1
    assert target.stat().st_mode & 0o777 == 0o700
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in target.iterdir())


@pytest.mark.parametrize("complete", [True, False])
def test_prepared_copy_is_rejected_without_mutation_by_every_managed_and_explicit_runtime(
    tmp_path, complete
):
    from domus.composition import ingress, server

    adapter, store, _, target = fixture(tmp_path)
    adapter.prepare("restore-1")
    if not complete:
        (target / "restore.json").unlink()
    before = {p.name: p.read_bytes() for p in target.iterdir()}
    attempts = [
        lambda: open_storage(target, "edge"),
        lambda: attach_storage(target, "edge"),
        lambda: ingress.create_owned_runtime("fixture-token", "edge", target, ("http://ha.local",)),
        lambda: server.create_owned_runtime(
            "http://ha.local", "https://domus.example", "edge", target
        ),
        lambda: ingress.create_business_runtime(
            "fixture-token",
            "edge",
            target / "domus.sqlite3",
            store.installation.instance_id,
            ("http://ha.local",),
        ),
        lambda: server.create_runtime(
            "http://ha.local",
            "https://domus.example",
            store.installation.instance_id,
            "edge",
            database=target / "domus.sqlite3",
        ),
    ]
    for attempt in attempts:
        with pytest.raises(DomusError):
            attempt()
        assert before == {p.name: p.read_bytes() for p in target.iterdir()}


@pytest.mark.parametrize(
    "name", ["restore.json", "operations.jsonl", "installation.json", "domus.sqlite3"]
)
def test_altered_files_cannot_verify(tmp_path, name):
    adapter, store, _, target = fixture(tmp_path)
    adapter.prepare("restore-1")
    path = target / name
    path.write_bytes(path.read_bytes() + b"altered")
    with pytest.raises(DatabaseRejected):
        inspect_at(target, store.installation)


def test_missing_or_conflicting_source_facts_leave_only_a_blocked_partial_target(tmp_path):
    adapter, store, _, target = fixture(tmp_path)
    with store._connection() as connection:
        connection.execute("UPDATE receipts SET result='{}' WHERE action='household.setup'")
    before = store.path.read_bytes()
    with pytest.raises(Conflict, match="restore_evidence_conflict"):
        adapter.prepare("restore-1")
    assert not (target / "restore.json").exists() and store.path.read_bytes() == before
    with pytest.raises(DatabaseRejected):
        inspect_at(target, store.installation)


def test_target_never_overwrites_complete_or_partial_outputs_and_aliases_are_rejected(tmp_path):
    adapter, store, archive, target = fixture(tmp_path)
    result = adapter.prepare("restore-1")
    with pytest.raises(Conflict, match="restore_destination_exists"):
        adapter.prepare("other")
    assert inspect_at(target, store.installation) == result
    adapter.location = archive / "inside"
    with pytest.raises(InvalidInput):
        adapter.prepare("other")
    assert not adapter.location.exists()
    adapter.location = tmp_path / "new"
    adapter.checkpoint = None
    with pytest.raises(InvalidInput):
        adapter.prepare("other")
    adapter.checkpoint = result.checkpoint
    adapter.database = None
    with pytest.raises(InvalidInput):
        adapter.prepare("other")


def test_scope_changes_and_snapshot_replacement_fail_before_any_output(tmp_path):
    adapter, store, _, target = fixture(tmp_path)
    adapter.installation = Installation(store.installation.instance_id, "stable")
    with pytest.raises(DatabaseRejected):
        adapter.prepare("restore-1")
    assert not target.exists()
    adapter.installation = store.installation
    from dataclasses import replace

    adapter.checkpoint = replace(adapter.checkpoint, snapshot_id="other")
    with pytest.raises(DatabaseRejected):
        adapter.prepare("restore-1")
    assert not target.exists()


def test_output_flush_failure_preserves_uncertainty_and_an_independently_inspectable_bundle(
    tmp_path, monkeypatch
):
    adapter, store, _, target = fixture(tmp_path)
    original = sqlite_restoration.os.fsync

    def fail(fd):
        if (target / "restore.json").exists():
            raise OSError("private failure")
        return original(fd)

    monkeypatch.setattr(sqlite_restoration.os, "fsync", fail)
    with pytest.raises(StorageFailure):
        adapter.prepare("restore-1")
    monkeypatch.undo()
    assert inspect_at(target, store.installation).restore_id == "restore-1"


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan"), True, 3601])
def test_deadlines_are_fixed_and_invalid_configuration_makes_no_artifact(tmp_path, timeout):
    with pytest.raises(InvalidInput):
        SQLiteRestorations(
            None,
            None,
            tmp_path / "unused",
            Installation("047cc6fb-dfb0-4fa4-b3c3-e0fe54d116b6", "edge"),
            Clock(),
            timeout=timeout,
        )


def test_expired_budget_does_not_publish_success(tmp_path):
    adapter, _, _, target = fixture(tmp_path)
    calls = iter([0, 100])
    adapter.monotonic = lambda: next(calls, 100)
    with pytest.raises(StorageFailure):
        adapter.prepare("restore-1")
    assert not (target / "restore.json").exists()


def rewrite_manifest(target, change):
    path = target / "restore.json"
    value = json.loads(path.read_text())
    change(value)
    path.write_text(json.dumps(value))


def reseal(target, name, field):
    digest = hashlib.sha256((target / name).read_bytes()).hexdigest()
    rewrite_manifest(target, lambda value: value.update({field: digest}))


@pytest.mark.parametrize(
    "data",
    [b"{}", b'"' + b"x" * 16_384 + b'"', b"\xff", b'{"format_version":true}'],
)
def test_invalid_or_oversized_manifest_is_sanitized(tmp_path, data):
    adapter, store, _, target = fixture(tmp_path)
    adapter.prepare("restore-1")
    (target / "restore.json").write_bytes(data)
    with pytest.raises(DatabaseRejected, match="invalid_restore_manifest"):
        inspect_at(target, store.installation)


@pytest.mark.parametrize(
    "data",
    [
        b"{}\n",
        b"{}",
        b"\xff\n",
        b'{"x":1,"x":2}\n',
        b"[" * 2000 + b"]" * 2000 + b"\n",
        b"x" * 262_145 + b"\n",
    ],
)
def test_rehashed_journal_must_still_contain_bounded_strict_complete_operations(tmp_path, data):
    adapter, store, _, target = fixture(tmp_path)
    adapter.prepare("restore-1")
    (target / "operations.jsonl").write_bytes(data)
    reseal(target, "operations.jsonl", "operations_sha256")
    with pytest.raises(DatabaseRejected, match="invalid_restore_operations"):
        inspect_at(target, store.installation)


def test_rehashed_identity_must_remain_blocked_and_match_the_installation(tmp_path):
    adapter, store, _, target = fixture(tmp_path)
    adapter.prepare("restore-1")
    path = target / "installation.json"
    value = json.loads(path.read_text())
    value["state"] = "ready"
    path.write_text(json.dumps(value))
    reseal(target, "installation.json", "identity_sha256")
    with pytest.raises(DatabaseRejected, match="invalid_restore_identity"):
        inspect_at(target, store.installation)


@pytest.mark.parametrize("field", ["schema_version", "last_committed_at", "database_bytes"])
def test_manifest_cannot_relabel_the_selected_checkpoint(tmp_path, field):
    adapter, store, _, target = fixture(tmp_path)
    adapter.prepare("restore-1")

    def change(value):
        value["checkpoint"][field] += 1

    rewrite_manifest(target, change)
    with pytest.raises(DatabaseRejected):
        inspect_at(target, store.installation)


def test_independent_inspection_requires_the_same_channel(tmp_path):
    adapter, store, _, target = fixture(tmp_path)
    adapter.prepare("restore-1")
    with pytest.raises(DatabaseRejected, match="installation_mismatch"):
        inspect_at(target, Installation(store.installation.instance_id, "stable"))


def test_rehashed_journal_cannot_make_later_business_changes_current(tmp_path):
    adapter, store, _, target = fixture(tmp_path)
    adapter.prepare("restore-1")
    path = target / "operations.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    rows[-1]["current"] = True
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    reseal(target, "operations.jsonl", "operations_sha256")
    with pytest.raises(DatabaseRejected, match="invalid_restore_projection"):
        inspect_at(target, store.installation)


@pytest.mark.parametrize("field", ["operation_count", "current_operations", "highwater"])
def test_manifest_counts_must_match_complete_history(tmp_path, field):
    adapter, store, _, target = fixture(tmp_path)
    adapter.prepare("restore-1")
    rewrite_manifest(target, lambda value: value.update({field: 1}))
    if field == "current_operations":
        rewrite_manifest(target, lambda value: value.update({field: 0}))
    with pytest.raises(DatabaseRejected):
        inspect_at(target, store.installation)


@pytest.mark.parametrize("state", ["ready", "initializing", "wrong_channel"])
def test_owned_source_identity_and_destination_are_checked_before_creation(tmp_path, state):
    adapter, store, _, target = fixture(tmp_path)
    path = store.path.parent / "installation.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "instance_id": store.installation.instance_id,
                "channel": "stable" if state == "wrong_channel" else "edge",
                "state": "ready" if state == "wrong_channel" else state,
            }
        )
    )
    path.chmod(0o600)
    if state == "ready":
        adapter.location = store.path.parent / "inside"
        error = InvalidInput
    else:
        error = DatabaseRejected
    with pytest.raises(error):
        adapter.prepare("restore-1")
    assert not target.exists() and not adapter.location.exists()


def test_snapshot_replacement_after_inspection_is_detected_by_copy_hash(tmp_path, monkeypatch):
    adapter, _, archive, target = fixture(tmp_path)
    original = sqlite_restoration.SQLiteSnapshots.inspect

    def inspect_then_change(instance):
        result = original(instance)
        with (archive / "domus.sqlite3").open("ab") as stream:
            stream.write(b"changed")
        return result

    monkeypatch.setattr(sqlite_restoration.SQLiteSnapshots, "inspect", inspect_then_change)
    with pytest.raises(DatabaseRejected, match="snapshot_checksum_mismatch"):
        adapter.prepare("restore-1")
    assert not (target / "restore.json").exists()


def test_missing_paths_and_partial_targets_never_provision_or_replace_data(tmp_path):
    adapter, store, _, target = fixture(tmp_path)
    adapter.location = tmp_path / "missing" / "target"
    with pytest.raises(StorageFailure):
        adapter.prepare("restore-1")
    assert not adapter.location.parent.exists()
    with pytest.raises(StorageFailure):
        inspect_at(adapter.location, store.installation)
    adapter.location = target
    target.mkdir(mode=0o700)
    marker = target / "partial"
    marker.write_bytes(b"retained")
    with pytest.raises(Conflict):
        adapter.prepare("restore-1")
    assert marker.read_bytes() == b"retained"


def test_owned_source_outside_target_preserves_later_acknowledgements_without_inventing_them(
    tmp_path,
):
    adapter, store, _, target = fixture(tmp_path)
    identity = store.path.parent / "installation.json"
    identity.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "instance_id": store.installation.instance_id,
                "channel": "edge",
                "state": "ready",
            }
        )
    )
    identity.chmod(0o600)
    with store._connection() as connection:
        connection.execute("UPDATE outbox SET delivered=1 WHERE event_type='household.setup'")
    adapter.prepare("restore-1")
    rows = [json.loads(line) for line in (target / "operations.jsonl").read_text().splitlines()]
    assert rows[0]["current"] and rows[0]["delivered"]
    assert not rows[1]["current"] and not rows[1]["delivered"]
    assert inspect_at(target, store.installation).operation_count == 2


def test_empty_checkpoint_keeps_later_setup_as_history_without_creating_a_household(tmp_path):
    from test_household_commands import fixture as commands_fixture

    from domus.application.household_commands import SetupHousehold
    from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots

    commands, store, _, _, _ = commands_fixture(tmp_path / "current.sqlite3")
    archive = tmp_path / "empty"
    checkpoint = SQLiteSnapshots(store, archive, store.installation, Clock()).create("empty")
    commands.setup("first", SetupHousehold("Later household", "UTC"))
    target = tmp_path / "prepared"
    adapter = SQLiteRestorations(store, archive, target, store.installation, Clock(), checkpoint)
    result = adapter.prepare("restore-empty")
    assert result.operation_count == 1 and result.current_operations == 0
    with SQLiteDatabase(target / "domus.sqlite3", store.installation).read() as unit:
        assert unit.households.current() is None
    assert inspect_at(target, store.installation) == result


@pytest.mark.parametrize("version", [1, 2, 3])
def test_compatible_legacy_checkpoint_is_copied_without_migration(tmp_path, version):
    from test_snapshot_values import INSTALLATION

    from domus.domain.snapshots import Snapshot

    archive = tmp_path / "archive"
    archive.mkdir(mode=0o700)
    database = archive / "domus.sqlite3"
    frozen = Path(__file__).resolve().parents[1] / f"fixtures/sqlite/v{version}.sql"
    with closing(sqlite3.connect(database, autocommit=True)) as connection:
        connection.executescript(frozen.read_text())
        # Supply a real canonical command digest; the frozen fixture intentionally uses a dummy.
        connection.execute("UPDATE receipts SET payload_fingerprint=?", ("a" * 64,))
    database.chmod(0o600)
    identity = archive / "installation.json"
    identity.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "instance_id": INSTALLATION.instance_id,
                "channel": "edge",
                "state": "ready",
            }
        )
    )
    identity.chmod(0o600)
    checkpoint = Snapshot(
        "old",
        INSTALLATION,
        version,
        2000,
        100,
        hashlib.sha256(database.read_bytes()).hexdigest(),
        database.stat().st_size,
        hashlib.sha256(identity.read_bytes()).hexdigest(),
    )
    manifest = archive / "manifest.json"
    manifest.write_text(checkpoint.document().encoded)
    manifest.chmod(0o600)
    source = tmp_path / "source.sqlite3"
    source.write_bytes(database.read_bytes())
    source.chmod(0o600)
    target = tmp_path / "prepared"
    adapter = SQLiteRestorations(
        SQLiteDatabase(source, INSTALLATION), archive, target, INSTALLATION, Clock(), checkpoint
    )
    result = adapter.prepare("restore-old")
    assert inspect_at(target, INSTALLATION) == result
    assert (target / "domus.sqlite3").read_bytes() == database.read_bytes()
    with closing(sqlite3.connect(target / "domus.sqlite3")) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == version


def test_current_history_is_one_coherent_read_view_during_a_concurrent_wal_commit(
    tmp_path, monkeypatch
):
    from test_household_commands import fixture as commands_fixture

    from domus.application.household_commands import SetupHousehold
    from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots

    commands, store, _, _, _ = commands_fixture(tmp_path / "source.sqlite3")
    commands.setup("first", SetupHousehold("Home", "UTC"))
    archive = tmp_path / "archive"
    checkpoint = SQLiteSnapshots(store, archive, store.installation, Clock()).create("checkpoint")
    commands.update("second", "Included", "UTC", 1)
    with closing(sqlite3.connect(store.path, autocommit=True)) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
    original = sqlite_restoration._verify_database
    changed = False

    def verify_then_commit(connection, database, *, previous):
        nonlocal changed
        result = original(connection, database, previous=previous)
        if database.path == store.path and not changed:
            changed = True
            commands.update("third", "Committed after source view", "UTC", 2)
        return result

    monkeypatch.setattr(sqlite_restoration, "_verify_database", verify_then_commit)
    target = tmp_path / "prepared"
    adapter = SQLiteRestorations(store, archive, target, store.installation, Clock(), checkpoint)
    result = adapter.prepare("restore-1")
    assert result.operation_count == 2
    assert inspect_at(target, store.installation) == result
    with store.read() as unit:
        assert unit.households.current().revision == 3 and len(unit.audit.entries("home")) == 3


def test_deadline_expiring_after_manifest_flush_reports_uncertainty(tmp_path, monkeypatch):
    adapter, store, _, target = fixture(tmp_path)
    now = 0
    adapter.monotonic = lambda: now
    original = sqlite_restoration.os.fsync

    def flush_then_expire(fd):
        nonlocal now
        original(fd)
        if (target / "restore.json").exists():
            now = 100

    monkeypatch.setattr(sqlite_restoration.os, "fsync", flush_then_expire)
    with pytest.raises(StorageFailure):
        adapter.prepare("restore-1")
    assert inspect_at(target, store.installation).restore_id == "restore-1"


def test_inspection_cannot_report_success_after_its_last_validation_exceeds_the_deadline(
    tmp_path, monkeypatch
):
    adapter, store, _, target = fixture(tmp_path)
    adapter.prepare("restore-1")
    now = 0
    original = sqlite_restoration._read_operations

    def read_then_expire(directory, budget):
        nonlocal now
        yield from original(directory, budget)
        now = 100

    monkeypatch.setattr(sqlite_restoration, "_read_operations", read_then_expire)
    inspector = SQLiteRestorations(
        None, None, target, store.installation, Clock(), monotonic=lambda: now
    )
    with pytest.raises(StorageFailure):
        inspector.inspect()


def test_blocked_identity_precedes_database_creation_and_prevents_partial_direct_start(
    tmp_path, monkeypatch
):
    from domus.composition import ingress, server

    adapter, store, _, target = fixture(tmp_path)
    original = sqlite_restoration._file
    observed = False

    def inspect_before_database(directory, name, flags=sqlite_restoration.os.O_RDONLY):
        nonlocal observed
        if name == "domus.sqlite3" and flags & sqlite_restoration.os.O_CREAT:
            observed = True
            assert (
                json.loads((target / "installation.json").read_text())["state"] == "restore_pending"
            )
            before = {p.name: p.read_bytes() for p in target.iterdir()}
            for attempt in (
                lambda: open_storage(target, "edge"),
                lambda: attach_storage(target, "edge"),
                lambda: ingress.create_business_runtime(
                    "fixture-token",
                    "edge",
                    target / "domus.sqlite3",
                    store.installation.instance_id,
                    ("http://ha.local",),
                ),
                lambda: server.create_runtime(
                    "http://ha.local",
                    "https://domus.example",
                    store.installation.instance_id,
                    "edge",
                    database=target / "domus.sqlite3",
                ),
            ):
                with pytest.raises(DomusError):
                    attempt()
                assert before == {p.name: p.read_bytes() for p in target.iterdir()}
            raise OSError("interrupted before checkpoint bytes")
        return original(directory, name, flags)

    monkeypatch.setattr(sqlite_restoration, "_file", inspect_before_database)
    with pytest.raises(StorageFailure):
        adapter.prepare("restore-1")
    assert observed and not (target / "domus.sqlite3").exists()


@pytest.mark.parametrize("signal", ["restore.json", "operations.jsonl"])
def test_a_partial_restore_signal_blocks_direct_paths_even_if_identity_is_missing(tmp_path, signal):
    from domus.infrastructure.owned_storage import attach_database, reject_owned_database

    adapter, store, _, target = fixture(tmp_path)
    adapter.prepare("restore-1")
    for name in ("installation.json", "restore.json", "operations.jsonl"):
        if name != signal:
            (target / name).unlink()
    before = {p.name: p.read_bytes() for p in target.iterdir()}
    for attempt in (
        lambda: reject_owned_database(target / "domus.sqlite3"),
        lambda: attach_database(target / "domus.sqlite3", store.installation),
    ):
        with pytest.raises(DomusError):
            attempt()
        assert before == {p.name: p.read_bytes() for p in target.iterdir()}
