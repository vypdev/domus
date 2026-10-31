"""Actual offline publication restores business state and retains later processed facts."""

import json
from dataclasses import replace

import pytest
from test_household_commands import fixture as command_fixture
from test_sqlite_snapshots import Clock

from domus.application.household_commands import SetupHousehold
from domus.domain.errors import Conflict, DomusError, StorageBusy
from domus.infrastructure.owned_storage import open_storage
from domus.infrastructure.sqlite_activation import SQLiteActivation
from domus.infrastructure.sqlite_restoration import SQLiteRestorations
from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots


def fixture(tmp_path):

    root = tmp_path / "owned"
    root.mkdir(mode=0o700)
    storage = open_storage(root, "edge")
    commands, _, actor, directory, identifiers = command_fixture(tmp_path / "unused")
    commands = replace(commands, transactions=storage.database)
    commands.setup("setup", SetupHousehold("Home", "UTC"))
    archive = tmp_path / "snapshot"
    snapshot = SQLiteSnapshots(storage.database, archive, storage.installation, Clock()).create(
        "snapshot"
    )
    commands.update("later", "Later state", "UTC", 1)
    target = tmp_path / "prepared"
    prepared = SQLiteRestorations(
        storage.database, archive, target, storage.installation, Clock(), snapshot
    ).prepare("restore-1")
    installation = storage.installation
    storage.close()
    return SQLiteActivation(root, installation, Clock(), target), root, installation, prepared


def test_real_activation_and_restart_keep_checkpoint_state_plus_later_receipts(tmp_path):
    adapter, root, installation, prepared = fixture(tmp_path)
    source = (root / "domus.sqlite3").read_bytes()
    result = adapter.activate()
    assert result.state == "active" and result.record.prepared == prepared
    assert not (root / "activation.json").exists()
    assert adapter.inspect().state == "active"
    assert adapter.activate() == result
    storage = open_storage(root, "edge")
    try:
        assert storage.generation_id == prepared.restore_id
        with storage.database.read() as unit:
            assert unit.households.current().name == "Home"
            assert len(unit.audit.entries("home")) == 1
            assert len(unit.outbox.pending()) == 1
        with storage.database._connection() as connection:
            rows = connection.execute(
                "SELECT current,document FROM retained_operations ORDER BY position"
            ).fetchall()
            assert len(rows) == 2 and not rows[1]["current"]
            assert json.loads(rows[1]["document"])["archived_by"] == prepared.restore_id
    finally:
        storage.close()
    assert (root / "domus.sqlite3").read_bytes() == source


def test_activation_requires_stopped_runtime_and_current_source_before_any_transition(tmp_path):
    adapter, root, _, _ = fixture(tmp_path)
    running = open_storage(root, "edge")
    with pytest.raises(StorageBusy):
        adapter.activate()
    assert not (root / "activation.json").exists()
    with running.database.write() as unit:
        assert unit.outbox.acknowledge(unit.outbox.pending()[0].event_id)
    running.close()
    with pytest.raises(Conflict, match="restore_source_changed"):
        adapter.activate()
    assert not (root / "activation.json").exists()


@pytest.mark.parametrize(
    "point",
    [
        "intent_stage",
        "intent",
        "input_copy",
        "target_import",
        "materialized",
        "pointer_before",
        "pointer_after",
        "receipt",
        "unlink_before",
        "unlink_after",
    ],
)
def test_faulted_transition_preserves_source_and_resumes_exact_input_without_second_effect(
    tmp_path, monkeypatch, point
):
    from domus.domain.errors import StorageFailure
    from domus.infrastructure import sqlite_activation

    adapter, root, installation, prepared = fixture(tmp_path)
    original = (root / "domus.sqlite3").read_bytes()
    root_inode = root.stat().st_ino
    fired = False
    real_replace = sqlite_activation.os.replace
    real_copy = sqlite_activation._copy
    real_verify = sqlite_activation._verify_database
    real_unlink = sqlite_activation.os.unlink

    def interrupt():
        nonlocal fired
        if not fired:
            fired = True
            raise OSError("injected durable-boundary failure")

    def replace_file(source, destination, **kwargs):
        is_root = sqlite_activation.os.fstat(kwargs["dst_dir_fd"]).st_ino == root_inode
        if (
            is_root
            and destination == "activation.json"
            and point == "intent_stage"
            and not (root / "activation.json").exists()
        ):
            interrupt()
        if is_root and destination == "installation.json" and point == "pointer_before":
            interrupt()
        result = real_replace(source, destination, **kwargs)
        if is_root and destination == "activation.json":
            phase = json.loads((root / "activation.json").read_text())["phase"]
            if point == "intent" and phase == "pending":
                interrupt()
            if point == "materialized" and phase == "materialized":
                interrupt()
        if is_root and destination == "installation.json" and point == "pointer_after":
            interrupt()
        if not is_root and destination == "activation.json" and point == "receipt":
            interrupt()
        return result

    def copy_file(source, target, name, budget):
        if point == "input_copy" and name == "domus.sqlite3":
            interrupt()
        return real_copy(source, target, name, budget)

    def verify(connection, database, *, previous):
        result = real_verify(connection, database, previous=previous)
        if point == "target_import" and "generations" in database.path.parts:
            interrupt()
        return result

    def unlink_file(name, **kwargs):
        if name == "activation.json" and point == "unlink_before":
            interrupt()
        result = real_unlink(name, **kwargs)
        if name == "activation.json" and point == "unlink_after":
            interrupt()
        return result

    monkeypatch.setattr(sqlite_activation.os, "replace", replace_file)
    monkeypatch.setattr(sqlite_activation, "_copy", copy_file)
    monkeypatch.setattr(sqlite_activation, "_verify_database", verify)
    monkeypatch.setattr(sqlite_activation.os, "unlink", unlink_file)
    with pytest.raises(StorageFailure):
        adapter.activate()
    assert fired and (root / "domus.sqlite3").read_bytes() == original
    if point != "unlink_after":
        with pytest.raises(DomusError):
            open_storage(root, "edge")
        assert adapter.inspect().state == "pending"
    monkeypatch.undo()
    resumed = SQLiteActivation(
        root, installation, Clock(), adapter.prepared_location, prepared.restore_id
    ).resume()
    assert resumed.state == "active"
    assert adapter.activate().record == resumed.record
    restarted = open_storage(root, "edge")
    try:
        with restarted.database.read() as unit:
            assert unit.households.current().name == "Home"
            assert len(unit.audit.entries("home")) == 1
    finally:
        restarted.close()


@pytest.mark.parametrize("mode", ["standalone", "native"])
def test_actual_compositions_reauthenticate_and_replay_historical_work_after_activation(
    tmp_path, monkeypatch, mode
):
    from fastapi.testclient import TestClient
    from test_household_runtime import headers as standalone_headers
    from test_household_runtime import runtime_at
    from test_native_http import HEADERS, ORIGIN, Lookup
    from test_native_http import headers as native_headers

    from domus.composition import ingress

    root = tmp_path / "root"
    root.mkdir(mode=0o700)

    def start():
        if mode == "standalone":
            runtime, client = runtime_at(root, monkeypatch, owned=True)
            return runtime, client, standalone_headers
        monkeypatch.setattr(ingress, "HomeAssistantWebSocket", lambda _: Lookup())
        runtime = ingress.create_owned_runtime("private-supervisor-token", "edge", root, (ORIGIN,))
        return (
            runtime,
            TestClient(
                runtime.app, base_url=ORIGIN, client=("172.30.32.2", 12000), headers=dict(HEADERS)
            ),
            native_headers,
        )

    runtime, client, headers = start()
    try:
        created = client.post(
            "/api/v1/household",
            json={"name": "Home", "time_zone": "UTC", "expected_revision": 0},
            headers=headers(client, "setup"),
        )
        assert created.status_code == 200, created.text
        installation = runtime.storage.installation
        snapshot = SQLiteSnapshots(
            runtime.storage.database, tmp_path / "snapshot", installation, Clock()
        ).create("snapshot")
        payload = {"name": "Later", "time_zone": "UTC", "expected_revision": 1}
        later = client.put("/api/v1/household", json=payload, headers=headers(client, "later"))
        assert later.status_code == 200, later.text
        prepared_path = tmp_path / "prepared"
        SQLiteRestorations(
            runtime.storage.database,
            tmp_path / "snapshot",
            prepared_path,
            installation,
            Clock(),
            snapshot,
        ).prepare("restore-1")
    finally:
        runtime.close()
    activation = SQLiteActivation(root, installation, Clock(), prepared_path)
    assert activation.activate().state == "active"
    runtime, client, headers = start()
    try:
        assert client.get("/api/v1/household").json()["name"] == "Home"
        replay = client.put("/api/v1/household", json=payload, headers=headers(client, "later"))
        assert replay.status_code == 200 and replay.json()["state"] == "historical"
        assert replay.json()["operation_id"] == later.json()["operation_id"]
        assert (
            client.get("/api/v1/operations/" + later.json()["operation_id"]).json()["delivery"]
            == "suppressed"
        )
        assert activation.inspect().state == "active"
    finally:
        runtime.close()


def test_supported_rollback_checkpoint_reconciles_newer_work_and_never_reactivates_an_old_key(
    tmp_path,
):
    adapter, root, installation, prepared = fixture(tmp_path)
    first = adapter.activate()
    rollback = root / "activations" / prepared.restore_id / "source-checkpoint"
    snapshot = SQLiteSnapshots(None, rollback, installation, Clock()).inspect()
    assert snapshot == first.record.rollback_snapshot
    current = open_storage(root, "edge")
    try:
        from test_atomic_commands import Authorization, Identifiers
        from test_atomic_commands import Clock as CommandClock

        from domus.application.commands import AtomicCommands, Change
        from domus.domain.storage import CommandKey, Household, JsonDocument

        # Existing commands remain current; a later operation must be retained during rollback.
        authority = Authorization()
        command = AtomicCommands(current.database, authority, CommandClock(), Identifiers())
        document = JsonDocument.from_value({"later": True})

        def apply(unit):
            unit.households.save(Household("home", "After activation", "UTC", 2), 1)
            return Change(document, document, document)

        command.execute(
            CommandKey("home", "human", "household.update", "after-activation"), document, apply
        )
        second_path = tmp_path / "rollback-prepared"
        SQLiteRestorations(
            current.database, rollback, second_path, installation, Clock(), snapshot
        ).prepare("restore-2")
    finally:
        current.close()
    second = SQLiteActivation(root, installation, Clock(), second_path).activate()
    assert second.state == "active"
    assert adapter.activate().state == adapter.inspect().state == "historical"
    selected = open_storage(root, "edge")
    try:
        assert selected.generation_id == "restore-2"
        with selected.database.read() as unit:
            assert unit.households.current().name == "Later state"
        with selected.database._connection() as connection:
            rows = connection.execute(
                "SELECT position,current,archived_by FROM retained_operations ORDER BY position"
            ).fetchall()
            assert len(rows) == 3 and rows[-1]["current"] == 0
            assert (
                connection.execute(
                    "SELECT seq FROM sqlite_sequence WHERE name='outbox'"
                ).fetchone()[0]
                == 3
            )
    finally:
        selected.close()


def test_process_death_after_pointer_rename_releases_leases_and_resumes_without_external_input(
    tmp_path,
):
    import subprocess
    import sys

    adapter, root, installation, prepared = fixture(tmp_path)
    script = tmp_path / "interrupt.py"
    script.write_text("""from pathlib import Path
import os,sys
from domus.domain.storage import Installation
from domus.infrastructure import sqlite_activation
class Clock:
    def now(self):return 2000
root=Path(sys.argv[1]);identity=Installation(sys.argv[2],'edge')
real=os.replace;inode=root.stat().st_ino
def stop(source,target,**kwargs):
    result=real(source,target,**kwargs)
    if target=='installation.json' and os.fstat(kwargs['dst_dir_fd']).st_ino==inode:os._exit(37)
    return result
os.replace=stop
sqlite_activation.SQLiteActivation(root,identity,Clock(),Path(sys.argv[3])).activate()
""")
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            str(root),
            installation.instance_id,
            str(adapter.prepared_location),
        ],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 37, result.stderr
    with pytest.raises(DomusError):
        open_storage(root, "edge")
    # Sealed local input is sufficient after the original external path is no longer available.
    resumed = SQLiteActivation(root, installation, Clock(), restore_id=prepared.restore_id).resume()
    assert resumed.state == "active"
    selected = open_storage(root, "edge")
    selected.close()
