"""Offline restoration requires both root leases and never initializes or migrates source data."""

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from test_owned_generations import fixture as generation_fixture

from domus.domain.errors import DomusError, InvalidInput, StorageBusy
from domus.domain.storage import Installation
from domus.infrastructure.offline_storage import offline_storage
from domus.infrastructure.owned_storage import attach_storage, open_storage


def flat(tmp_path):
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    storage = open_storage(root, "edge")
    identity = storage.installation
    storage.close()
    return root, identity


def test_both_leases_exclude_server_and_console_until_offline_capability_exits(tmp_path):
    root, identity = flat(tmp_path)
    original = (root / "domus.sqlite3").read_bytes()
    with offline_storage(root, "edge") as storage:
        assert storage.installation == identity and storage.source.generation_id is None
        assert storage.source.identity_sha256 == storage.root_identity.fingerprint
        for attempt in (
            lambda: open_storage(root, "edge"),
            lambda: attach_storage(root, "edge"),
            lambda: offline_storage(root, "edge").__enter__(),
        ):
            with pytest.raises(StorageBusy):
                attempt()
    assert (root / "domus.sqlite3").read_bytes() == original
    open_storage(root, "edge").close()


@pytest.mark.parametrize("serving", [True, False])
def test_live_runtime_or_shared_console_refuses_offline_work_and_releases_partial_leases(
    tmp_path, serving
):
    root, _ = flat(tmp_path)
    active = open_storage(root, "edge") if serving else attach_storage(root, "edge")
    with pytest.raises(StorageBusy):
        with offline_storage(root, "edge"):
            pytest.fail("unexpected offline capability")
    active.close()
    with offline_storage(root, "edge"):
        pass


def test_selected_generation_is_bound_under_exclusive_root_leases(tmp_path):
    root, slot, selection = generation_fixture(tmp_path)
    with offline_storage(root, "edge") as storage:
        assert storage.database.path == slot / "domus.sqlite3"
        assert storage.source.generation_id == selection.generation_id
        assert storage.root_identity == selection.document()
        assert storage.source.identity_sha256 == selection.document().fingerprint


def test_frozen_schema_three_is_inspected_without_migration_or_source_rewrite(tmp_path):
    import json

    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    identity = Installation("047cc6fb-dfb0-4fa4-b3c3-e0fe54d116b6", "edge")
    database = root / "domus.sqlite3"
    frozen = Path(__file__).resolve().parents[1] / "fixtures/sqlite/v3.sql"
    with closing(sqlite3.connect(database, autocommit=True)) as connection:
        connection.executescript(frozen.read_text())
    database.chmod(0o600)
    marker = root / "installation.json"
    marker.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "instance_id": identity.instance_id,
                "channel": "edge",
                "state": "ready",
            }
        )
    )
    marker.chmod(0o600)
    before = database.read_bytes()
    with offline_storage(root, "edge") as storage:
        assert storage.source.schema_version == 3 and storage.installation == identity
    assert before == database.read_bytes()


@pytest.mark.parametrize(
    "damage",
    [
        "missing_identity",
        "empty_database",
        "missing_database",
        "initializing",
        "partial",
        "slot_bypass",
        "unknown",
    ],
)
def test_existing_source_is_required_and_partial_or_unrelated_state_is_not_adopted(
    tmp_path, damage
):
    import json

    if damage == "slot_bypass":
        _, root, _ = generation_fixture(tmp_path)
    else:
        root, _ = flat(tmp_path)
    if damage == "missing_identity":
        (root / "installation.json").unlink()
    elif damage == "empty_database":
        (root / "domus.sqlite3").write_bytes(b"")
    elif damage == "missing_database":
        (root / "domus.sqlite3").unlink()
    elif damage == "initializing":
        value = json.loads((root / "installation.json").read_text())
        value["state"] = "initializing"
        (root / "installation.json").write_text(json.dumps(value))
    elif damage == "partial":
        (root / "operations.jsonl").write_text("retained")
    elif damage == "unknown":
        (root / "foreign").write_text("retained")
    before = {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}
    with pytest.raises(DomusError):
        with offline_storage(root, "edge"):
            pytest.fail("adopted unsafe source")
    for name, value in before.items():
        assert (root / name).read_bytes() == value


@pytest.mark.parametrize("timeout", [0, -1, True, float("nan"), float("inf"), 3601])
def test_invalid_maintenance_budget_never_opens_a_directory(tmp_path, timeout):
    with pytest.raises(InvalidInput):
        with offline_storage(tmp_path / "absent", "edge", timeout=timeout):
            pass


def test_unsafe_owner_channel_and_missing_root_do_not_acquire_offline_authority(tmp_path):
    from domus.domain.errors import StorageFailure

    root, _ = flat(tmp_path)
    with pytest.raises(InvalidInput):
        with offline_storage(root, "wrong"):
            pass
    with pytest.raises(DomusError):
        with offline_storage(root, "stable"):
            pass
    root.chmod(0o755)
    with pytest.raises(DomusError):
        with offline_storage(root, "edge"):
            pass
    with pytest.raises(StorageFailure):
        with offline_storage(tmp_path / "absent", "edge"):
            pass
