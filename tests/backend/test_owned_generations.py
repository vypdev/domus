"""Only the selected private generation can run under the installation-wide lease."""

import json
from dataclasses import replace

import pytest

from domus.domain.errors import DomusError, StorageBusy
from domus.domain.generations import GenerationSelection
from domus.infrastructure.owned_storage import (
    attach_database,
    attach_storage,
    open_storage,
    reject_owned_database,
)
from domus.infrastructure.sqlite import SQLiteDatabase


def fixture(tmp_path):
    root = tmp_path / "owned"
    root.mkdir(mode=0o700)
    initial = open_storage(root, "edge")
    installation = initial.installation
    initial.close()
    generations = root / "generations"
    generations.mkdir(mode=0o700)
    selection = GenerationSelection(installation, "generation-1")
    slot = generations / selection.generation_id
    slot.mkdir(mode=0o700)
    database = slot / "domus.sqlite3"
    database.write_bytes((root / "domus.sqlite3").read_bytes())
    database.chmod(0o600)
    marker = {
        "schema_version": 1,
        "instance_id": installation.instance_id,
        "channel": "edge",
        "state": "ready",
    }
    (slot / "installation.json").write_text(json.dumps(marker))
    (slot / "installation.json").chmod(0o600)
    (slot / "generation.json").write_text(selection.document().encoded)
    (slot / "generation.json").chmod(0o600)
    (root / "installation.json").write_text(selection.document().encoded)
    return root, slot, selection


def test_runtime_and_console_share_only_the_selected_generation_and_keep_root_leases(tmp_path):
    root, slot, selection = fixture(tmp_path)
    legacy = (root / "domus.sqlite3").read_bytes()
    storage = open_storage(root, "edge")
    assert (
        storage.installation == selection.installation
        and storage.generation_id == selection.generation_id
    )
    assert storage.database.path == slot / "domus.sqlite3"
    with storage.database.read() as unit:
        assert unit.households.current() is None
    attached = attach_storage(root, "edge")
    assert (
        attached.database.path == storage.database.path
        and attached.generation_id == storage.generation_id
    )
    attached.close()
    with pytest.raises(StorageBusy):
        open_storage(root, "edge")
    storage.close()
    restarted = open_storage(root, "edge")
    assert restarted.database.path == slot / "domus.sqlite3"
    restarted.close()
    assert (root / "domus.sqlite3").read_bytes() == legacy


@pytest.mark.parametrize("missing_identity", [False, True])
def test_slot_cannot_bypass_root_selection_by_any_direct_storage_path(tmp_path, missing_identity):
    root, slot, selection = fixture(tmp_path)
    if missing_identity:
        (slot / "installation.json").unlink()
    before = {p.name: p.read_bytes() for p in slot.iterdir()}
    for attempt in (
        lambda: open_storage(slot, "edge"),
        lambda: attach_storage(slot, "edge"),
        lambda: reject_owned_database(slot / "domus.sqlite3"),
        lambda: attach_database(slot / "domus.sqlite3", selection.installation),
    ):
        with pytest.raises(DomusError):
            attempt()
        assert before == {p.name: p.read_bytes() for p in slot.iterdir()}


@pytest.mark.parametrize(
    "damage",
    [
        "missing_database",
        "empty_database",
        "foreign_database",
        "missing_slot",
        "wrong_marker",
        "missing_marker",
        "pending_identity",
        "extra",
        "unsafe_slot",
        "unsafe_parent",
        "foreign_identity",
        "nested_identity",
        "corrupt_marker",
    ],
)
def test_invalid_selection_never_falls_back_to_legacy_or_initializes_empty_data(tmp_path, damage):
    root, slot, selection = fixture(tmp_path)
    database = slot / "domus.sqlite3"
    if damage == "missing_database":
        database.unlink()
    elif damage == "empty_database":
        database.write_bytes(b"")
    elif damage == "foreign_database":
        other = tmp_path / "other.sqlite3"
        SQLiteDatabase(other, replace(selection.installation, channel="stable")).initialize()
        database.write_bytes(other.read_bytes())
    elif damage == "missing_slot":
        slot.rename(slot.with_name("other"))
    elif damage == "wrong_marker":
        (slot / "generation.json").write_text(
            replace(selection, generation_id="other").document().encoded
        )
    elif damage == "missing_marker":
        (slot / "generation.json").unlink()
    elif damage == "pending_identity":
        value = json.loads((slot / "installation.json").read_text())
        value["state"] = "restore_pending"
        (slot / "installation.json").write_text(json.dumps(value))
    elif damage == "extra":
        (slot / "unknown").write_text("retained")
    elif damage == "unsafe_slot":
        slot.chmod(0o755)
    elif damage == "unsafe_parent":
        slot.parent.chmod(0o755)
    elif damage == "foreign_identity":
        value = json.loads((slot / "installation.json").read_text())
        value["instance_id"] = "047cc6fb-dfb0-4fa4-b3c3-e0fe54d116b7"
        (slot / "installation.json").write_text(json.dumps(value))
    elif damage == "nested_identity":
        (slot / "installation.json").write_text(selection.document().encoded)
    else:
        (slot / "generation.json").write_text("not JSON")
    marker = (root / "installation.json").read_bytes()
    legacy = (root / "domus.sqlite3").read_bytes()
    before = database.read_bytes() if database.exists() else None
    with pytest.raises(DomusError):
        open_storage(root, "edge")
    assert (
        marker == (root / "installation.json").read_bytes()
        and legacy == (root / "domus.sqlite3").read_bytes()
    )
    assert (database.read_bytes() if database.exists() else None) == before


def test_selection_is_reread_after_the_installation_lease_not_cached_before_it(
    tmp_path, monkeypatch
):
    from domus.infrastructure import owned_storage

    root, slot, selection = fixture(tmp_path)
    later = replace(selection, generation_id="generation-2")
    second = slot.with_name(later.generation_id)
    second.mkdir(mode=0o700)
    for name in ("domus.sqlite3", "installation.json"):
        (second / name).write_bytes((slot / name).read_bytes())
        (second / name).chmod(0o600)
    (second / "generation.json").write_text(later.document().encoded)
    (second / "generation.json").chmod(0o600)
    original = owned_storage._acquire
    changed = False

    def publish_before_acquire(directory, name, mode):
        nonlocal changed
        if not changed:
            (root / "installation.json").write_text(later.document().encoded)
            changed = True
        return original(directory, name, mode)

    monkeypatch.setattr(owned_storage, "_acquire", publish_before_acquire)
    storage = open_storage(root, "edge")
    try:
        assert storage.generation_id == later.generation_id
        assert storage.database.path == second / "domus.sqlite3"
    finally:
        storage.close()


@pytest.mark.parametrize("mode", ["standalone", "native"])
def test_both_composed_apis_use_the_selected_slot_across_restart(tmp_path, monkeypatch, mode):
    from fastapi.testclient import TestClient
    from test_household_runtime import headers as standalone_headers
    from test_household_runtime import runtime_at
    from test_native_http import HEADERS, ORIGIN, Lookup
    from test_native_http import headers as native_headers

    from domus.composition import ingress

    root, slot, selection = fixture(tmp_path)
    old = (root / "domus.sqlite3").read_bytes()

    def start():
        if mode == "standalone":
            runtime, client = runtime_at(root, monkeypatch, owned=True)
            return runtime, client, standalone_headers
        monkeypatch.setattr(ingress, "HomeAssistantWebSocket", lambda _: Lookup())
        runtime = ingress.create_owned_runtime("private-supervisor-token", "edge", root, (ORIGIN,))
        client = TestClient(
            runtime.app, base_url=ORIGIN, client=("172.30.32.2", 12000), headers=dict(HEADERS)
        )
        return runtime, client, native_headers

    payload = {"name": "Selected household", "time_zone": "UTC", "expected_revision": 0}
    runtime, client, headers = start()
    try:
        result = client.post("/api/v1/household", json=payload, headers=headers(client, "setup"))
        assert result.status_code == 200, result.text
        original = result.json()
        assert runtime.storage.database.path == slot / "domus.sqlite3"
    finally:
        runtime.close()
    runtime, client, headers = start()
    try:
        assert client.get("/api/v1/household").json()["name"] == "Selected household"
        assert (
            client.post("/api/v1/household", json=payload, headers=headers(client, "setup")).json()
            == original
        )
        assert runtime.storage.generation_id == selection.generation_id
    finally:
        runtime.close()
    assert (root / "domus.sqlite3").read_bytes() == old


def test_snapshot_and_blocked_preparation_work_in_private_root_archives(tmp_path):
    from test_sqlite_snapshots import Clock

    from domus.infrastructure.sqlite_restoration import SQLiteRestorations
    from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots

    root, _, selection = fixture(tmp_path)
    archives = root / "archives"
    archives.mkdir(mode=0o700)
    runtime = open_storage(root, "edge")
    attached = attach_storage(root, "edge")
    try:
        archive = archives / "manual-1"
        snapshots = SQLiteSnapshots(attached.database, archive, selection.installation, Clock())
        checkpoint = snapshots.create("snapshot-1")
        assert snapshots.inspect() == checkpoint
        candidate = archives / "prepared-1"
        restorations = SQLiteRestorations(
            attached.database, archive, candidate, selection.installation, Clock(), checkpoint
        )
        prepared = restorations.prepare("restore-1")
        assert restorations.inspect() == prepared
    finally:
        attached.close()
        runtime.close()
    restarted = open_storage(root, "edge")
    assert restarted.generation_id == selection.generation_id
    restarted.close()


def test_selected_generation_does_not_require_or_recreate_retained_flat_database(tmp_path):
    root, slot, _ = fixture(tmp_path)
    (root / "domus.sqlite3").unlink()
    storage = open_storage(root, "edge")
    try:
        assert storage.database.path == slot / "domus.sqlite3"
    finally:
        storage.close()
    assert not (root / "domus.sqlite3").exists()


@pytest.mark.parametrize("name", ["generations", "slot", "archives"])
def test_symlinked_generation_or_archive_directories_are_not_followed(tmp_path, name):
    root, slot, _ = fixture(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir(mode=0o700)
    if name == "generations":
        original = root / "generations"
        original.rename(outside / "data")
        original.symlink_to(outside / "data", target_is_directory=True)
    elif name == "slot":
        slot.rename(outside / "data")
        slot.symlink_to(outside / "data", target_is_directory=True)
    else:
        (root / "archives").symlink_to(outside, target_is_directory=True)
    before = (root / "installation.json").read_bytes()
    with pytest.raises(DomusError):
        open_storage(root, "edge")
    assert before == (root / "installation.json").read_bytes()
