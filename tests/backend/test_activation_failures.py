"""Unsafe restore artifacts fail closed; interrupted owned work remains resumable."""

import json
import os
from dataclasses import replace

import pytest
from test_sqlite_activation import fixture
from test_sqlite_snapshots import Clock

from domus.domain.activation import ActivationRecord
from domus.domain.errors import Conflict, DatabaseRejected, DomusError, NotFound, StorageFailure
from domus.domain.storage import Installation
from domus.infrastructure import sqlite_activation
from domus.infrastructure.owned_storage import open_storage
from domus.infrastructure.sqlite_activation import SQLiteActivation
from domus.infrastructure.sqlite_restoration import SQLiteRestorations


def document(path, value):
    path.write_text(value.document().encoded)
    path.chmod(0o600)


def directory(path):
    if not path.parent.exists():
        directory(path.parent)
    path.mkdir(mode=0o700, exist_ok=True)
    return path


def pause(adapter, root, monkeypatch, point):
    original = sqlite_activation.os.replace
    inode = root.stat().st_ino

    def interrupt(source, target, **kwargs):
        result = original(source, target, **kwargs)
        at_root = os.fstat(kwargs["dst_dir_fd"]).st_ino == inode
        if at_root and target == "activation.json":
            if json.loads((root / target).read_text())["phase"] == point:
                raise OSError("interrupted after durable intent")
        if at_root and target == "installation.json" and point == "selected":
            raise OSError("interrupted after durable selection")
        if not at_root and target == "activation.json" and point == "receipt":
            raise OSError("interrupted after completion receipt")
        return result

    monkeypatch.setattr(sqlite_activation.os, "replace", interrupt)
    with pytest.raises(StorageFailure):
        adapter.activate()
    monkeypatch.undo()


@pytest.mark.parametrize("timeout", [0, -1, True, float("nan"), float("inf"), 3601])
def test_invalid_activation_timeout_has_no_filesystem_effect(tmp_path, timeout):
    from domus.domain.errors import InvalidInput

    with pytest.raises(InvalidInput):
        SQLiteActivation(
            tmp_path / "absent",
            Installation("047cc6fb-dfb0-4fa4-b3c3-e0fe54d116b6", "edge"),
            Clock(),
            timeout=timeout,
        )
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("damage", ["invalid", "active", "staged_materialized", "foreign"])
def test_invalid_pending_records_do_not_authorize_a_transition(tmp_path, monkeypatch, damage):
    adapter, root, identity, prepared = fixture(tmp_path)
    pause(adapter, root, monkeypatch, "pending")
    path = root / "activation.json"
    if damage == "invalid":
        path.write_text("{}")
    elif damage in ("active", "staged_materialized"):
        value = ActivationRecord(prepared, "materialized", "a" * 64, 1, None, prepared.checkpoint)
        if damage == "active":
            value = replace(value, phase="active", activated_at=2000)
        document(path, value)
        if damage == "staged_materialized":
            path.rename(root / "activation.json.next")
    else:
        other = Installation("b08026cc-6ded-4c68-9c7d-722b81a19dca", "edge")
        value = replace(
            prepared,
            checkpoint=replace(prepared.checkpoint, installation=other),
            source=replace(prepared.source, installation=other),
        )
        document(path, ActivationRecord(value, "pending"))
    with pytest.raises(DatabaseRejected):
        adapter.resume()
    assert not (root / "generations").exists()


def test_missing_selection_and_foreign_installation_cannot_gain_offline_authority(tmp_path):
    _, root, identity, _ = fixture(tmp_path)
    missing = SQLiteActivation(root, identity, Clock())
    for attempt in (missing.activate, missing.inspect):
        with pytest.raises(NotFound):
            attempt()
    foreign = SQLiteActivation(
        root,
        Installation("b08026cc-6ded-4c68-9c7d-722b81a19dca", "edge"),
        Clock(),
        restore_id="restore-1",
    )
    for attempt in (foreign.activate, foreign.inspect):
        with pytest.raises(DatabaseRejected, match="installation_mismatch"):
            attempt()
    assert not (root / "activation.json").exists()


@pytest.mark.parametrize("binding", ["legacy", "changed"])
def test_unbound_or_stale_preparation_is_inspectable_but_not_activatable(tmp_path, binding):
    adapter, root, _, prepared = fixture(tmp_path)
    value = (
        replace(prepared, source=None)
        if binding == "legacy"
        else replace(prepared, source=replace(prepared.source, schema_version=3))
    )
    document(adapter.prepared_location / "restore.json", value)
    assert adapter._inspect_input(adapter.prepared_location) == value
    with pytest.raises(DomusError, match="managed_restore_binding_required|restore_source_changed"):
        adapter.activate()
    assert not (root / "activation.json").exists()


def test_conflicting_selectors_and_pending_external_input_do_not_replace_an_intent(
    tmp_path, monkeypatch
):
    adapter, root, identity, prepared = fixture(tmp_path)
    with pytest.raises(Conflict, match="activation_record_conflict"):
        replace(adapter, restore_id="other").activate()
    pause(adapter, root, monkeypatch, "pending")
    original = (root / "activation.json").read_bytes()
    with pytest.raises(Conflict, match="activation_in_progress"):
        SQLiteActivation(root, identity, Clock(), restore_id="other").resume()
    document(
        adapter.prepared_location / "restore.json",
        replace(prepared, prepared_at=prepared.prepared_at + 1),
    )
    with pytest.raises(Conflict, match="activation_in_progress"):
        adapter.resume()
    assert (root / "activation.json").read_bytes() == original


def test_missing_and_invalid_completion_evidence_never_creates_a_new_activation(tmp_path):
    adapter, root, identity, prepared = fixture(tmp_path)
    adapter.activate()
    unknown = SQLiteActivation(root, identity, Clock(), restore_id="unknown")
    for attempt in (unknown.activate, unknown.inspect):
        with pytest.raises(NotFound):
            attempt()
    receipt = root / "activations" / prepared.restore_id / "activation.json"
    document(receipt, ActivationRecord(prepared, "pending"))
    with pytest.raises(DatabaseRejected, match="invalid_activation_record"):
        adapter.activate()


def test_completed_id_cannot_be_reused_with_a_different_preparation(tmp_path):
    adapter, root, _, prepared = fixture(tmp_path)
    adapter.activate()
    document(
        adapter.prepared_location / "restore.json",
        replace(prepared, prepared_at=prepared.prepared_at + 1),
    )
    with pytest.raises(Conflict, match="activation_record_conflict"):
        adapter.activate()
    assert not (root / "activation.json").exists()


@pytest.mark.parametrize("damage", ["invalid", "changed"])
def test_sealed_input_recovers_corruption_but_requires_exact_original_for_partial_copy(
    tmp_path, monkeypatch, damage
):
    adapter, root, identity, prepared = fixture(tmp_path)
    pause(adapter, root, monkeypatch, "materialized")
    sealed = root / "activations" / prepared.restore_id / "input"
    if damage == "invalid":
        (sealed / "operations.jsonl").write_text("corrupted")
    else:
        document(sealed / "restore.json", replace(prepared, prepared_at=prepared.prepared_at + 1))
    with pytest.raises(DatabaseRejected, match="activation_input_required"):
        SQLiteActivation(root, identity, Clock(), restore_id=prepared.restore_id).resume()
    assert adapter.resume().state == "active"


@pytest.mark.parametrize("area", ["input", "slot", "checkpoint"])
def test_unknown_artifacts_are_retained_and_block_resume(tmp_path, monkeypatch, area):
    adapter, root, _, prepared = fixture(tmp_path)
    pause(adapter, root, monkeypatch, "pending")
    evidence = directory(root / "activations" / prepared.restore_id)
    target = (
        directory(root / "generations" / prepared.restore_id)
        if area == "slot"
        else directory(evidence / ("input" if area == "input" else "source-checkpoint"))
    )
    foreign = target / "unrecognized"
    foreign.write_text("retain this evidence")
    foreign.chmod(0o600)
    with pytest.raises(DatabaseRejected, match="invalid_activation_artifacts"):
        adapter.resume()
    assert foreign.read_text() == "retain this evidence"


def test_partial_source_checkpoint_is_safely_recopied_before_publication(tmp_path, monkeypatch):
    adapter, root, identity, prepared = fixture(tmp_path)
    pause(adapter, root, monkeypatch, "pending")
    target = directory(root / "activations" / prepared.restore_id / "source-checkpoint")
    (target / "domus.sqlite3").write_bytes(b"partial copy")
    (target / "domus.sqlite3").chmod(0o600)
    assert adapter.resume().state == "active"


def test_input_replaced_during_sealing_is_not_selected(tmp_path, monkeypatch):
    adapter, root, _, prepared = fixture(tmp_path)
    original = sqlite_activation._copy

    def changed(source, target, name, budget):
        original(source, target, name, budget)
        if name == "restore.json":
            fd = os.open(name, os.O_WRONLY | os.O_TRUNC, dir_fd=target)
            with os.fdopen(fd, "w") as stream:
                stream.write(
                    replace(prepared, prepared_at=prepared.prepared_at + 1).document().encoded
                )

    monkeypatch.setattr(sqlite_activation, "_copy", changed)
    with pytest.raises(DatabaseRejected, match="activation_input_changed"):
        adapter.activate()
    assert "generation_id" not in json.loads((root / "installation.json").read_text())


def test_history_import_failure_rolls_back_target_and_resume_reimports_once(tmp_path, monkeypatch):
    adapter, root, _, prepared = fixture(tmp_path)
    original = sqlite_activation.SQLiteHistory.install

    def fail(history, records):
        original(history, records)
        raise OSError("write failed before commit")

    monkeypatch.setattr(sqlite_activation.SQLiteHistory, "install", fail)
    with pytest.raises(StorageFailure):
        adapter.activate()
    import sqlite3
    from contextlib import closing

    with closing(
        sqlite3.connect(root / "generations" / prepared.restore_id / "domus.sqlite3")
    ) as connection:
        assert connection.execute("SELECT COUNT(*) FROM retained_operations").fetchone()[0] == 0
    monkeypatch.undo()
    assert adapter.resume().state == "active"


def test_materialized_target_modified_before_selection_is_rejected(tmp_path, monkeypatch):
    adapter, root, _, prepared = fixture(tmp_path)
    pause(adapter, root, monkeypatch, "materialized")
    path = root / "generations" / prepared.restore_id / "domus.sqlite3"
    with path.open("ab") as stream:
        stream.write(b"unexpected bytes")
    with pytest.raises(DatabaseRejected, match="activation_target_changed"):
        adapter.resume()


@pytest.mark.parametrize("area", ["generations", "activations"])
def test_new_activation_does_not_adopt_a_preexisting_destination(tmp_path, area):
    adapter, root, identity, prepared = fixture(tmp_path)
    adapter.activate()
    storage = open_storage(root, "edge")
    target = tmp_path / "second-prepared"
    try:
        SQLiteRestorations(
            storage.database, tmp_path / "snapshot", target, identity, Clock(), prepared.checkpoint
        ).prepare("restore-2")
    finally:
        storage.close()
    collision = directory(root / area / "restore-2")
    with pytest.raises(Conflict, match="activation_destination_exists"):
        SQLiteActivation(root, identity, Clock(), target).activate()
    assert list(collision.iterdir()) == []


def test_selected_generation_cannot_claim_a_merely_pending_record(tmp_path, monkeypatch):
    adapter, root, _, prepared = fixture(tmp_path)
    pause(adapter, root, monkeypatch, "selected")
    document(root / "activation.json", ActivationRecord(prepared, "pending"))
    with pytest.raises(DatabaseRejected, match="invalid_activation_record"):
        adapter.resume()


def test_pending_status_requires_same_installation_and_can_report_a_prior_activation(
    tmp_path, monkeypatch
):
    adapter, root, identity, prepared = fixture(tmp_path)
    adapter.activate()
    storage = open_storage(root, "edge")
    target = tmp_path / "second-prepared"
    try:
        second = SQLiteRestorations(
            storage.database, tmp_path / "snapshot", target, identity, Clock(), prepared.checkpoint
        ).prepare("restore-2")
    finally:
        storage.close()
    other = SQLiteActivation(root, identity, Clock(), target)
    pause(other, root, monkeypatch, "pending")
    assert adapter.inspect().state == "active"
    assert SQLiteActivation(root, identity, Clock()).inspect().record.prepared == second
    with pytest.raises(NotFound):
        SQLiteActivation(root, identity, Clock(), restore_id="unknown").inspect()
    foreign = replace(
        adapter, installation=Installation("b08026cc-6ded-4c68-9c7d-722b81a19dca", "edge")
    )
    with pytest.raises(DatabaseRejected, match="installation_mismatch"):
        foreign.inspect()
    assert other.resume().state == "active"


def test_live_status_missing_receipt_is_explicit_and_inspection_io_is_sanitized(
    tmp_path, monkeypatch
):
    adapter, root, identity, _ = fixture(tmp_path)
    with pytest.raises(NotFound):
        SQLiteActivation(root, identity, Clock(), restore_id="unknown").inspect()
    adapter.activate()
    original = sqlite_activation.os.listdir

    def fail(directory):
        if (
            type(directory) is int
            and os.fstat(directory).st_ino == (root / "activations").stat().st_ino
        ):
            raise OSError("private inspection failure")
        return original(directory)

    monkeypatch.setattr(sqlite_activation.os, "listdir", fail)
    with pytest.raises(StorageFailure, match="activation_inspection_failed"):
        adapter.inspect()


def test_valid_but_changed_rollback_history_is_not_reused(tmp_path, monkeypatch):
    import hashlib
    import sqlite3
    from contextlib import closing

    adapter, root, _, prepared = fixture(tmp_path)
    original = sqlite_activation._copy
    slot = root / "generations" / prepared.restore_id

    def fail_before_target_copy(source, target, name, budget):
        if slot.exists() and os.fstat(target).st_ino == slot.stat().st_ino:
            raise OSError("interrupted before copying the target")
        original(source, target, name, budget)

    monkeypatch.setattr(sqlite_activation, "_copy", fail_before_target_copy)
    with pytest.raises(StorageFailure):
        adapter.activate()
    monkeypatch.undo()
    checkpoint = root / "activations" / prepared.restore_id / "source-checkpoint"
    path = checkpoint / "domus.sqlite3"
    with closing(sqlite3.connect(path, autocommit=True)) as connection:
        connection.execute("UPDATE outbox SET delivered=1")
    manifest = checkpoint / "manifest.json"
    value = json.loads(manifest.read_text())
    value["database_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    value["database_bytes"] = path.stat().st_size
    manifest.write_text(json.dumps(value))
    with pytest.raises(DatabaseRejected, match="activation_rollback_changed"):
        adapter.resume()


def test_rollback_checkpoint_identity_must_match_the_materialization_receipt(tmp_path, monkeypatch):
    adapter, root, _, prepared = fixture(tmp_path)
    pause(adapter, root, monkeypatch, "materialized")
    manifest = root / "activations" / prepared.restore_id / "source-checkpoint" / "manifest.json"
    value = json.loads(manifest.read_text())
    value["captured_at"] += 1
    manifest.write_text(json.dumps(value))
    with pytest.raises(DatabaseRejected, match="activation_rollback_changed"):
        adapter.resume()


@pytest.mark.parametrize("point", ["materialized", "selected"])
def test_out_of_band_root_identity_change_is_never_silently_overwritten(
    tmp_path, monkeypatch, point
):
    adapter, root, _, _ = fixture(tmp_path)
    original = sqlite_activation._atomic
    inode = root.stat().st_ino

    def external_change(directory, name, value, stage=None):
        original(directory, name, value, stage)
        if os.fstat(directory).st_ino != inode:
            return
        if (
            point == "materialized"
            and name == "activation.json"
            and value.decode()["phase"] == "materialized"
        ) or (point == "selected" and name == "installation.json"):
            path = root / "installation.json"
            identity = json.loads(path.read_text())
            if point == "materialized":
                identity["state"] = "initializing"
            else:
                identity["generation_id"] = "another-selection"
            path.write_text(json.dumps(identity))

    monkeypatch.setattr(sqlite_activation, "_atomic", external_change)
    with pytest.raises(DomusError, match="restore_source_changed|activation_selection_changed"):
        adapter.activate()
    assert (root / "activation.json").exists()


def test_conflicting_durable_completion_receipt_cannot_be_overwritten(tmp_path, monkeypatch):
    adapter, root, _, prepared = fixture(tmp_path)
    pause(adapter, root, monkeypatch, "receipt")
    path = root / "activations" / prepared.restore_id / "activation.json"
    value = json.loads(path.read_text())
    value["database_sha256"] = "a" * 64
    path.write_text(json.dumps(value))
    before = path.read_bytes()
    with pytest.raises(Conflict, match="activation_record_conflict"):
        adapter.resume()
    assert path.read_bytes() == before and (root / "activation.json").exists()
