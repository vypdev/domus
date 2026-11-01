"""Real SQLite snapshots preserve a committed view and reject incomplete or altered bundles."""

import hashlib
import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from test_household_commands import fixture

from domus.application.household_commands import SetupHousehold
from domus.domain.errors import Conflict, DatabaseRejected, InvalidInput, StorageFailure
from domus.domain.storage import Installation
from domus.infrastructure import sqlite_snapshots
from domus.infrastructure.sqlite import SQLiteDatabase
from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots


class Clock:
    def now(self) -> int:
        return 2000


def configured(tmp_path: Path) -> tuple:
    commands, store, _, _, _ = fixture(tmp_path / "database")
    commands.setup("setup", SetupHousehold("Home", "UTC"))
    location = tmp_path / "snapshot"
    return SQLiteSnapshots(store, location, store.installation, Clock()), commands, store, location


def test_snapshot_contains_verified_private_identity_checkpoint_and_all_atomic_records(
    tmp_path: Path,
) -> None:
    snapshots, _, store, location = configured(tmp_path)
    before = store.path.read_bytes()
    result = snapshots.create("snapshot-1")
    assert (
        result.schema_version == 7
        and result.captured_at == 2000
        and result.last_committed_at == 100
    )
    assert (
        result.database_sha256
        == hashlib.sha256((location / "domus.sqlite3").read_bytes()).hexdigest()
    )
    assert result.database_bytes == (location / "domus.sqlite3").stat().st_size
    assert (
        result.identity_sha256
        == hashlib.sha256((location / "installation.json").read_bytes()).hexdigest()
    )
    assert set(p.name for p in location.iterdir()) == {
        "domus.sqlite3",
        "installation.json",
        "manifest.json",
    }
    assert location.stat().st_mode & 0o777 == 0o700
    for path in location.iterdir():
        assert path.stat().st_mode & 0o777 == 0o600
    assert snapshots.inspect() == result
    assert store.path.read_bytes() == before
    copy = SQLiteDatabase(location / "domus.sqlite3", store.installation)
    with copy.read() as unit:
        assert unit.households.current().name == "Home"
        assert len(unit.members.list("home")) == 1
        assert unit.policies.get("home").revision == 1
        assert len(unit.audit.entries("home")) == len(unit.outbox.pending()) == 1
    with closing(sqlite3.connect(copy.path)) as connection:
        assert connection.execute("SELECT count(*) FROM receipts").fetchone()[0] == 1


def test_snapshot_never_overwrites_existing_destination_or_creates_one_for_wrong_scope(
    tmp_path: Path,
) -> None:
    snapshots, _, store, location = configured(tmp_path)
    result = snapshots.create("snapshot-1")
    with pytest.raises(Conflict, match="snapshot_destination_exists"):
        snapshots.create("another")
    assert snapshots.inspect() == result
    wrong = SQLiteSnapshots(
        store, tmp_path / "wrong", Installation(store.installation.instance_id, "stable"), Clock()
    )
    with pytest.raises(DatabaseRejected):
        wrong.create("snapshot-2")
    assert not (tmp_path / "wrong").exists()
    with pytest.raises(DatabaseRejected):
        SQLiteSnapshots(None, location, wrong.installation, Clock()).inspect()


@pytest.mark.parametrize("name", ["domus.sqlite3", "installation.json", "manifest.json"])
def test_changed_files_never_verify_and_do_not_change_the_source(tmp_path: Path, name: str) -> None:
    snapshots, _, store, location = configured(tmp_path)
    snapshots.create("snapshot-1")
    before = store.path.read_bytes()
    path = location / name
    content = path.read_bytes()
    path.write_bytes(content + b"corruption")
    with pytest.raises(DatabaseRejected):
        snapshots.inspect()
    assert store.path.read_bytes() == before


@pytest.mark.parametrize(
    "artifact",
    [
        "missing_manifest",
        "extra_file",
        "symlink",
        "hardlink",
        "fifo",
        "shared_file",
        "shared_directory",
    ],
)
def test_incomplete_or_unsafe_archive_is_not_accepted(tmp_path: Path, artifact: str) -> None:
    snapshots, _, _, location = configured(tmp_path)
    snapshots.create("snapshot-1")
    path = location / "manifest.json"
    if artifact == "missing_manifest":
        path.unlink()
    elif artifact == "extra_file":
        (location / "extra").touch()
    elif artifact == "shared_directory":
        location.chmod(0o755)
    elif artifact == "shared_file":
        path.chmod(0o644)
    else:
        content = path.read_bytes()
        path.unlink()
        outside = tmp_path / "outside"
        outside.write_bytes(content)
        outside.chmod(0o600)
        if artifact == "symlink":
            path.symlink_to(outside)
        elif artifact == "hardlink":
            os.link(outside, path)
        else:
            os.mkfifo(path, 0o600)
    with pytest.raises((DatabaseRejected, StorageFailure)):
        snapshots.inspect()


def test_failed_copy_has_no_valid_manifest_and_a_retry_cannot_replace_partial_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshots, _, store, location = configured(tmp_path)

    def fail(*args, **kwargs):
        raise StorageFailure("injected_copy_failure")

    monkeypatch.setattr(sqlite_snapshots, "_copy", fail)
    with pytest.raises(StorageFailure):
        snapshots.create("snapshot-1")
    assert location.is_dir() and not (location / "manifest.json").exists()
    with pytest.raises(DatabaseRejected):
        snapshots.inspect()
    with pytest.raises(Conflict):
        snapshots.create("another")
    with store.read() as unit:
        assert unit.households.current().name == "Home"


def test_read_transaction_pins_snapshot_while_wal_writer_commits_a_newer_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshots, commands, store, location = configured(tmp_path)
    with closing(sqlite3.connect(store.path)) as connection:
        assert connection.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    original = sqlite_snapshots._copy

    def interleave(*args, **kwargs):
        commands.update("later", "Later home", "UTC", 1)
        original(*args, **kwargs)

    monkeypatch.setattr(sqlite_snapshots, "_copy", interleave)
    result = snapshots.create("snapshot-1")
    assert result.last_committed_at == 100
    with store.read() as unit:
        assert unit.households.current().name == "Later home"
    with SQLiteDatabase(location / "domus.sqlite3", store.installation).read() as unit:
        assert unit.households.current().name == "Home"
        assert len(unit.audit.entries("home")) == 1
    assert snapshots.inspect() == result


@pytest.mark.parametrize("value", [float("nan"), float("inf"), 0, 3601, True])
def test_invalid_deadline_fails_before_any_destination(tmp_path: Path, value: float) -> None:
    _, _, store, location = configured(tmp_path)
    with pytest.raises(InvalidInput):
        SQLiteSnapshots(store, location, store.installation, Clock(), timeout=value)
    assert not location.exists()


def test_source_is_required_for_capture_and_unknown_schema_is_not_copied(tmp_path: Path) -> None:
    snapshots, _, store, location = configured(tmp_path)
    with pytest.raises(InvalidInput):
        SQLiteSnapshots(None, location, store.installation, Clock()).create("snapshot-1")
    with closing(sqlite3.connect(store.path, autocommit=True)) as connection:
        connection.execute("PRAGMA user_version=999")
    with pytest.raises(DatabaseRejected):
        snapshots.create("snapshot-1")
    assert not location.exists()


@pytest.mark.parametrize(
    "change",
    [
        "PRAGMA ignore_check_constraints=ON; UPDATE members SET role='unknown'",
        "DELETE FROM households",
        "DELETE FROM audit",
        "DELETE FROM outbox",
        "DELETE FROM receipts",
        "DELETE FROM receipts; DELETE FROM audit",
        "UPDATE audit SET actor_id='other'",
        "UPDATE receipts SET result='broken JSON'",
        "UPDATE members SET exceptions='broken JSON'",
        "ALTER TABLE members ADD COLUMN unauthorized TEXT",
        "UPDATE receipts SET created_at='bad'; UPDATE audit SET created_at='bad'; "
        "UPDATE outbox SET created_at='bad'",
    ],
)
def test_logical_or_physical_corruption_is_rejected_before_creating_archive(
    tmp_path: Path, change: str
) -> None:
    snapshots, _, store, location = configured(tmp_path)
    with closing(sqlite3.connect(store.path, autocommit=True)) as connection:
        connection.executescript(change)
    with pytest.raises(DatabaseRejected):
        snapshots.create("snapshot-1")
    assert not location.exists()


def test_empty_initialized_database_is_a_valid_checkpoint_without_command_time(
    tmp_path: Path,
) -> None:
    from test_snapshot_values import INSTALLATION

    database = SQLiteDatabase(tmp_path / "database", INSTALLATION)
    database.initialize()
    snapshots = SQLiteSnapshots(database, tmp_path / "empty", INSTALLATION, Clock())
    result = snapshots.create("empty-1")
    assert result.last_committed_at is None and snapshots.inspect() == result


@pytest.mark.parametrize("changed_identity", [False, True])
def test_recovery_consumption_is_preserved_and_mismatched_installation_recovery_is_rejected(
    tmp_path: Path, changed_identity: bool
) -> None:
    import json

    from test_recovery_commands import configured as recovery_fixture
    from test_recovery_commands import start

    commands, approval, store, _, _, _ = recovery_fixture(tmp_path)
    request_id = start(commands)
    approval.approve(request_id)
    commands.complete("complete", request_id, 2)
    if changed_identity:
        with closing(sqlite3.connect(store.path, autocommit=True)) as connection:
            document = json.loads(
                connection.execute("SELECT detail FROM recovery_requests").fetchone()[0]
            )
            document["channel"] = "stable"
            connection.execute("UPDATE recovery_requests SET detail=?", (json.dumps(document),))
    snapshots = SQLiteSnapshots(store, tmp_path / "copy", store.installation, Clock())
    if changed_identity:
        with pytest.raises(DatabaseRejected):
            snapshots.create("snapshot-1")
    else:
        result = snapshots.create("snapshot-1")
        with SQLiteDatabase(
            snapshots.location / "domus.sqlite3", store.installation
        ).read() as unit:
            assert unit.recoveries.get("home", request_id).state.value == "consumed"
        assert snapshots.inspect() == result


@pytest.mark.parametrize(
    "change", ["unknown", "large", "unicode", "version", "checkpoint", "schema", "identity"]
)
def test_manifest_and_identity_are_strict_and_cross_checked_against_database(
    tmp_path: Path, change: str
) -> None:
    import json

    snapshots, _, _, location = configured(tmp_path)
    snapshots.create("snapshot-1")
    path = location / "manifest.json"
    document = json.loads(path.read_text())
    if change == "unknown":
        document["extra"] = True
    elif change == "large":
        path.write_bytes(b"x" * 16385)
    elif change == "unicode":
        path.write_bytes(b"\xff")
    elif change == "version":
        document["format_version"] = 2
    elif change == "checkpoint":
        document["last_committed_at"] = 101
    elif change == "schema":
        document["schema_version"] = 2
    else:
        identity = location / "installation.json"
        value = json.loads(identity.read_text())
        value["state"] = "initializing"
        identity.write_text(json.dumps(value))
        document["identity_sha256"] = hashlib.sha256(identity.read_bytes()).hexdigest()
    if change not in ("large", "unicode"):
        path.write_text(json.dumps(document))
    with pytest.raises(DatabaseRejected):
        snapshots.inspect()


def test_owned_source_metadata_and_nested_destination_are_checked_before_copy(
    tmp_path: Path,
) -> None:
    import json

    snapshots, _, store, location = configured(tmp_path)
    marker = store.path.parent / "installation.json"
    value = {
        "schema_version": 1,
        "instance_id": store.installation.instance_id,
        "channel": "edge",
        "state": "initializing",
    }
    marker.write_text(json.dumps(value))
    marker.chmod(0o600)
    with pytest.raises(DatabaseRejected):
        snapshots.create("snapshot-1")
    value["state"] = "ready"
    marker.write_text(json.dumps(value))
    with pytest.raises(InvalidInput, match="snapshot_destination_inside_source"):
        snapshots.create("snapshot-1")
    assert not location.exists()
    outside = tmp_path.parent / (tmp_path.name + "-separate-snapshot")
    snapshots.location = outside
    try:
        assert snapshots.create("snapshot-1") == snapshots.inspect()
    finally:
        if outside.exists():
            for child in outside.iterdir():
                child.unlink()
            outside.rmdir()


@pytest.mark.parametrize("failure", ["deadline", "driver", "filesystem", "sql_deadline"])
def test_copy_failure_is_bounded_sanitized_and_never_publishes_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    snapshots, _, store, location = configured(tmp_path)

    class Timer:
        value = 0

        def __call__(self):
            return self.value

    timer = Timer()
    snapshots.monotonic = timer
    original = sqlite_snapshots._copy

    def fail(source, target, budget):
        if failure in ("deadline", "sql_deadline"):
            timer.value = 31
        if failure == "deadline":
            original(source, target, budget)
        elif failure == "driver":
            raise sqlite3.OperationalError("private fixture driver detail")
        elif failure == "filesystem":
            raise OSError("private fixture path")
        else:
            source.execute(
                "WITH RECURSIVE n(x) AS (VALUES(0) UNION ALL SELECT x+1 FROM n WHERE x<10000) "
                "SELECT sum(x) FROM n"
            ).fetchone()

    monkeypatch.setattr(sqlite_snapshots, "_copy", fail)
    with pytest.raises(StorageFailure) as rejected:
        snapshots.create("snapshot-1")
    assert "private" not in str(rejected.value)
    assert not (location / "manifest.json").exists()
    with store.read() as unit:
        assert unit.households.current().name == "Home"


def test_inspection_missing_directory_and_publication_error_do_not_touch_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshots, _, store, location = configured(tmp_path)
    with pytest.raises(StorageFailure):
        snapshots.inspect()
    original = sqlite_snapshots._file

    def fail(directory, name, *args):
        if name == "manifest.json":
            raise OSError("injected disk full")
        return original(directory, name, *args)

    monkeypatch.setattr(sqlite_snapshots, "_file", fail)
    with pytest.raises(StorageFailure):
        snapshots.create("snapshot-1")
    assert (location / "domus.sqlite3").exists() and not (location / "manifest.json").exists()
    with store.read() as unit:
        assert len(unit.audit.entries("home")) == 1


@pytest.mark.parametrize("version", [1, 2, 3])
def test_compatible_historical_schema_is_inspected_without_migrating_archive(
    tmp_path: Path, version: int
) -> None:
    from test_snapshot_values import INSTALLATION

    from domus.domain.snapshots import Snapshot

    location = tmp_path / "historical"
    location.mkdir(mode=0o700)
    database = location / "domus.sqlite3"
    fixture = Path(__file__).resolve().parents[1] / f"fixtures/sqlite/v{version}.sql"
    with closing(sqlite3.connect(database, autocommit=True)) as connection:
        connection.executescript(fixture.read_text())
    database.chmod(0o600)
    identity = location / "installation.json"
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
    manifest = Snapshot(
        "historical-1",
        INSTALLATION,
        version,
        2000,
        100,
        hashlib.sha256(database.read_bytes()).hexdigest(),
        database.stat().st_size,
        hashlib.sha256(identity.read_bytes()).hexdigest(),
    )
    (location / "manifest.json").write_text(manifest.document().encoded)
    (location / "manifest.json").chmod(0o600)
    before = database.read_bytes()
    assert SQLiteSnapshots(None, location, INSTALLATION, Clock()).inspect() == manifest
    assert database.read_bytes() == before


def test_physical_index_corruption_is_rejected_before_archive_publication(tmp_path: Path) -> None:
    snapshots, _, store, location = configured(tmp_path)
    with closing(sqlite3.connect(store.path, autocommit=True)) as connection:
        connection.executescript(
            "PRAGMA writable_schema=ON; UPDATE sqlite_master SET rootpage="
            "(SELECT rootpage FROM sqlite_master WHERE name='households') "
            "WHERE name='outbox_pending'; PRAGMA writable_schema=OFF"
        )
    with pytest.raises(DatabaseRejected, match="invalid_snapshot_database"):
        snapshots.create("snapshot-1")
    assert not location.exists()


@pytest.mark.parametrize(
    "table,field,value",
    [("installation", "singleton", 2), ("households", "singleton", 2), ("outbox", "delivered", 2)],
)
def test_readonly_inspection_also_checks_singleton_and_delivery_invariants(
    tmp_path: Path, table: str, field: str, value: int
) -> None:
    snapshots, _, _, location = configured(tmp_path)
    snapshots.create("snapshot-1")
    database = location / "domus.sqlite3"
    with closing(sqlite3.connect(database, autocommit=True)) as connection:
        connection.execute("PRAGMA ignore_check_constraints=ON")
        connection.execute(f"UPDATE {table} SET {field}=?", (value,))
    manifest = json.loads((location / "manifest.json").read_text())
    manifest["database_sha256"] = hashlib.sha256(database.read_bytes()).hexdigest()
    (location / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(DatabaseRejected):
        snapshots.inspect()
