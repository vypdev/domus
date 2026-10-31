"""Owned initialization preserves identity and never replaces lost data with an empty home."""

import json
import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

import pytest

from domus.domain.errors import DatabaseRejected, InvalidInput, StorageBusy, StorageFailure
from domus.domain.storage import Household
from domus.infrastructure.owned_storage import open_storage
from domus.infrastructure.sqlite import SQLiteDatabase


def directory(tmp_path: Path) -> Path:
    root = tmp_path / "domus"
    root.mkdir(mode=0o700)
    return root


def marker(root: Path) -> dict:
    return json.loads((root / "installation.json").read_text())


def test_first_start_creates_private_identity_and_empty_schema_then_reuses_both(
    tmp_path: Path,
) -> None:
    root = directory(tmp_path)
    first = open_storage(root, "edge")
    identity = first.installation
    assert marker(root) == {
        "schema_version": 1,
        "instance_id": identity.instance_id,
        "channel": "edge",
        "state": "ready",
    }
    assert first.database.path == root / "domus.sqlite3"
    with first.database.write() as unit:
        unit.households.save(Household("home", "Preserved home", "UTC", 1), 0)
    for name in ("installation.json", "runtime.lock", "domus.sqlite3"):
        assert (root / name).stat().st_mode & 0o777 == 0o600
    first.close()
    first.close()
    second = open_storage(root, "edge")
    assert second.installation == identity
    with second.database.read() as unit:
        assert unit.households.current().name == "Preserved home"
    second.close()


def test_channel_mismatch_does_not_rewrite_identity_or_database(tmp_path: Path) -> None:
    root = directory(tmp_path)
    owned = open_storage(root, "edge")
    owned.close()
    before = {name: (root / name).read_bytes() for name in ("installation.json", "domus.sqlite3")}
    with pytest.raises(DatabaseRejected, match="installation_channel_mismatch"):
        open_storage(root, "stable")
    assert before == {name: (root / name).read_bytes() for name in before}
    assert open_storage(root, "edge").close() is None


@pytest.mark.parametrize("artifact", ["domus.sqlite3", "domus.sqlite3-wal", ".installation.next"])
def test_missing_identity_never_adopts_existing_artifact(tmp_path: Path, artifact: str) -> None:
    root = directory(tmp_path)
    (root / artifact).write_bytes(b"preexisting")
    (root / artifact).chmod(0o600)
    with pytest.raises(DatabaseRejected, match="missing_installation_identity"):
        open_storage(root, "edge")
    assert (root / artifact).read_bytes() == b"preexisting"
    assert not (root / "installation.json").exists()


@pytest.mark.parametrize("loss", ["missing", "empty", "invalid", "foreign"])
def test_ready_identity_cannot_recreate_or_adopt_lost_or_replaced_database(
    tmp_path: Path, loss: str
) -> None:
    root = directory(tmp_path)
    owned = open_storage(root, "edge")
    owned.close()
    original = (root / "installation.json").read_bytes()
    database = root / "domus.sqlite3"
    if loss == "missing":
        database.unlink()
    elif loss == "empty":
        database.write_bytes(b"")
    elif loss == "invalid":
        database.write_bytes(b"not sqlite")
    else:
        with closing(sqlite3.connect(database, autocommit=True)) as connection:
            connection.execute(
                "UPDATE installation SET instance_id='047cc6fb-dfb0-4fa4-b3c3-e0fe54d116b6'"
            )
    before = database.read_bytes() if database.exists() else None
    with pytest.raises((DatabaseRejected, StorageFailure)):
        open_storage(root, "edge")
    assert (root / "installation.json").read_bytes() == original
    assert (database.read_bytes() if database.exists() else None) == before


@pytest.mark.parametrize("after_commit", [False, True])
def test_interrupted_schema_initialization_resumes_only_the_persisted_uuid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, after_commit: bool
) -> None:
    root = directory(tmp_path)
    original = SQLiteDatabase.initialize

    def interrupted(self, **kwargs):
        if after_commit:
            original(self, **kwargs)
        raise StorageFailure("simulated_interruption")

    monkeypatch.setattr(SQLiteDatabase, "initialize", interrupted)
    with pytest.raises(StorageFailure, match="simulated_interruption"):
        open_storage(root, "edge")
    pending = marker(root)
    assert pending["state"] == "initializing"
    monkeypatch.setattr(SQLiteDatabase, "initialize", original)
    resumed = open_storage(root, "edge")
    assert resumed.installation.instance_id == pending["instance_id"]
    assert marker(root)["state"] == "ready"
    with resumed.database.read() as unit:
        assert unit.households.current() is None
    resumed.close()


def test_same_directory_is_exclusively_owned_until_close_even_in_another_process(
    tmp_path: Path,
) -> None:
    root = directory(tmp_path)
    owned = open_storage(root, "edge")
    with pytest.raises(StorageBusy, match="installation_in_use"):
        open_storage(root, "edge")
    code = """from pathlib import Path
from domus.infrastructure.owned_storage import open_storage
from domus.domain.errors import StorageBusy
import sys
try:
    open_storage(Path(sys.argv[1]), 'edge')
except StorageBusy as error:
    assert error.code == 'installation_in_use'
else:
    raise AssertionError('A second process obtained the owned directory')
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(root)], text=True, capture_output=True, timeout=10
    )
    assert result.returncode == 0, result.stderr
    owned.close()
    open_storage(root, "edge").close()


@pytest.mark.parametrize(
    "content",
    ["{}", "[]", "not JSON", '{"schema_version":1,"schema_version":1}', "\ud800", "x" * 1025],
)
def test_invalid_identity_is_preserved_and_never_replaced(tmp_path: Path, content: str) -> None:
    root = directory(tmp_path)
    file = root / "installation.json"
    file.write_bytes(content.encode("utf-8", errors="surrogatepass"))
    file.chmod(0o600)
    original = file.read_bytes()
    with pytest.raises(DatabaseRejected, match="invalid_installation_identity"):
        open_storage(root, "edge")
    assert file.read_bytes() == original
    assert not (root / "domus.sqlite3").exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", True),
        ("schema_version", 2),
        ("instance_id", "not-uuid"),
        ("state", "unknown"),
        ("channel", "preview"),
    ],
)
def test_invalid_identity_fields_cannot_initialize_sqlite(
    tmp_path: Path, field: str, value: object
) -> None:
    root = directory(tmp_path)
    value_object = {
        "schema_version": 1,
        "instance_id": "047cc6fb-dfb0-4fa4-b3c3-e0fe54d116b6",
        "channel": "edge",
        "state": "ready",
    }
    value_object[field] = value
    file = root / "installation.json"
    file.write_text(json.dumps(value_object))
    file.chmod(0o600)
    with pytest.raises(DatabaseRejected, match="invalid_installation_identity"):
        open_storage(root, "edge")
    assert not (root / "domus.sqlite3").exists()


def test_unknown_files_and_unsafe_root_do_not_receive_a_new_identity(tmp_path: Path) -> None:
    root = directory(tmp_path)
    (root / "unexpected").touch()
    with pytest.raises(DatabaseRejected, match="unexpected_installation_artifact"):
        open_storage(root, "edge")
    assert not (root / "installation.json").exists()
    (root / "unexpected").unlink()
    root.chmod(0o755)
    with pytest.raises(DatabaseRejected, match="unsafe_installation_directory"):
        open_storage(root, "edge")


@pytest.mark.parametrize(
    "name", ["runtime.lock", "installation.json", "domus.sqlite3", ".installation.next"]
)
@pytest.mark.parametrize("kind", ["symlink", "hardlink", "fifo", "shared_mode"])
def test_special_linked_or_shared_files_are_not_opened_as_owned_state(
    tmp_path: Path, name: str, kind: str
) -> None:
    root = directory(tmp_path)
    if name != "runtime.lock":
        open_storage(root, "edge").close()
    file = root / name
    file.unlink(missing_ok=True)
    outside = tmp_path / "outside"
    outside.write_bytes(b"untouched")
    outside.chmod(0o600)
    if kind == "symlink":
        file.symlink_to(outside)
    elif kind == "hardlink":
        os.link(outside, file)
    elif kind == "fifo":
        os.mkfifo(file, 0o600)
    else:
        file.write_bytes(b"unsafe")
        file.chmod(0o644)
    with pytest.raises((DatabaseRejected, StorageFailure)):
        open_storage(root, "edge")
    assert outside.read_bytes() == b"untouched"


def test_invalid_channel_and_missing_or_symlink_root_fail_before_initialization(
    tmp_path: Path,
) -> None:
    root = tmp_path / "missing"
    with pytest.raises(InvalidInput, match="invalid_installation_channel"):
        open_storage(root, "preview")
    with pytest.raises(StorageFailure):
        open_storage(root, "edge")
    private = directory(tmp_path)
    root.symlink_to(private, target_is_directory=True)
    with pytest.raises(StorageFailure):
        open_storage(root, "edge")
    assert list(private.iterdir()) == []


def test_failed_ready_marker_replacement_resumes_committed_schema_with_same_uuid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = directory(tmp_path)
    original = os.replace

    def fail(*args, **kwargs):
        raise OSError("injected device error")

    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(StorageFailure, match="storage_failure"):
        open_storage(root, "edge")
    pending = marker(root)
    assert pending["state"] == "initializing"
    assert (root / ".installation.next").is_file()
    monkeypatch.setattr(os, "replace", original)
    owned = open_storage(root, "edge")
    assert owned.installation.instance_id == pending["instance_id"]
    assert marker(root)["state"] == "ready"
    assert not (root / ".installation.next").exists()
    owned.close()


def test_ready_storage_discards_only_owned_staging_file_without_changing_identity(
    tmp_path: Path,
) -> None:
    root = directory(tmp_path)
    owned = open_storage(root, "edge")
    identity = owned.installation
    owned.close()
    staged = root / ".installation.next"
    staged.write_text("interrupted staging")
    staged.chmod(0o600)
    restarted = open_storage(root, "edge")
    assert restarted.installation == identity and not staged.exists()
    restarted.close()


@pytest.mark.parametrize("stage", ["before_schema", "after_schema"])
def test_process_death_releases_lock_and_resumes_only_durable_installation(
    tmp_path: Path, stage: str
) -> None:
    root = directory(tmp_path)
    code = """from pathlib import Path
import os, sys
from domus.infrastructure.owned_storage import open_storage
from domus.infrastructure.sqlite import SQLiteDatabase
original = SQLiteDatabase.initialize
def die(self, **kwargs):
    if sys.argv[2] == 'after_schema':
        original(self, **kwargs)
    os._exit(61)
SQLiteDatabase.initialize = die
open_storage(Path(sys.argv[1]), 'edge')
"""
    stopped = subprocess.run(
        [sys.executable, "-c", code, str(root), stage], capture_output=True, timeout=10
    )
    assert stopped.returncode == 61
    before = marker(root)
    assert before["state"] == "initializing"
    resumed = open_storage(root, "edge")
    assert resumed.installation.instance_id == before["instance_id"]
    assert marker(root)["state"] == "ready"
    resumed.close()


def test_wrong_directory_or_file_owner_is_rejected_without_changing_os_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = directory(tmp_path)
    uid = os.getuid()
    monkeypatch.setattr(os, "getuid", lambda: uid + 1)
    with pytest.raises(DatabaseRejected, match="unsafe_installation_directory"):
        open_storage(root, "edge")
    calls = iter((uid, uid + 1))
    monkeypatch.setattr(os, "getuid", lambda: next(calls))
    with pytest.raises(DatabaseRejected, match="unsafe_installation_file"):
        open_storage(root, "edge")
    assert not (root / "installation.json").exists()


def test_ready_owned_directory_permits_explicit_v1_migration_without_recreating_state(
    tmp_path: Path,
) -> None:
    from test_sqlite_identity import V1

    root = directory(tmp_path)
    open_storage(root, "edge").close()
    value = marker(root)
    value["instance_id"] = "047cc6fb-dfb0-4fa4-b3c3-e0fe54d116b6"
    (root / "installation.json").write_text(json.dumps(value))
    database = root / "domus.sqlite3"
    database.unlink()
    with closing(sqlite3.connect(database, autocommit=True)) as connection:
        connection.executescript(V1.read_text())
    database.chmod(0o600)
    owned = open_storage(root, "edge")
    with owned.database.read() as unit:
        home = unit.households.current()
        assert home.name == "Existing household" and home.revision == 3
        assert unit.audit.entries("home")[0].operation_id == "old-operation"
        assert unit.outbox.pending()[0].event_id == "old-operation"
    owned.close()
