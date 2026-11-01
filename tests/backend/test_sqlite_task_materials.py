"""Real SQLite material durability, strict codecs and original schema-5 compatibility."""

import hashlib
import json
import sqlite3
from contextlib import closing
from dataclasses import replace
from pathlib import Path

import pytest
from test_task_materials import intent, posting
from test_tasks import definition

from domus.domain.errors import Conflict, StorageFailure
from domus.domain.storage import CommandKey, Installation
from domus.infrastructure.sqlite import SCHEMA_VERSION, SQLiteDatabase
from domus.infrastructure.sqlite_task_material_records import material_document, read_material
from domus.infrastructure.sqlite_task_records import (
    definition_document,
    occurrence_document,
    read_definition,
    read_occurrence,
)


def test_definition_materials_are_validated_and_frozen_per_occurrence():
    original = definition(materials=(intent().line,))
    work = original.new_occurrence("occurrence", 20)
    changed = original.revise(original.content, original.overrides, original.state, materials=())
    assert work.definition_snapshot == original and changed.materials == ()
    assert read_definition(definition_document(original).encoded) == original
    assert read_occurrence(occurrence_document(work).encoded) == work
    assert definition_document(original).decode()["version"] == 2


def test_material_record_roundtrip_preserves_unknown_original_and_confirmed_correction():
    original = intent(None)
    corrected = original.correct(posting(intent()).quantity, "Actual usage", 110)
    confirmed = corrected.confirm(posting(corrected, posted_at=111), 112)
    pending = confirmed.correct(posting(intent("3")).quantity, "One more", 113)
    for value in (original, corrected, confirmed, pending):
        assert read_material(material_document(value).encoded) == value
    assert pending.submitted_quantity is None and pending.posting == confirmed.posting


def test_original_schema5_migration_preserves_history_and_legacy_request_fingerprints(tmp_path):
    source = Path(__file__).resolve().parents[1] / "fixtures/sqlite/v5.sql"
    assert hashlib.sha256(source.read_bytes()).hexdigest() == (
        "d93e1cbfb0547b53308ee6ac485ca895c0269dd286c29656618da60d5c20de50"
    )
    path = tmp_path / "old.sqlite3"
    with closing(sqlite3.connect(path, autocommit=True)) as connection:
        connection.executescript(source.read_text())
        before = {
            table: connection.execute(f"SELECT * FROM {table}").fetchall()
            for table in ("receipts", "audit", "outbox", "retained_operations", "task_cycles")
        }
    store = SQLiteDatabase(path, Installation("047cc6fb-dfb0-4fa4-b3c3-e0fe54d116b6", "edge"))
    store.initialize(require_existing=True)
    with store._connection() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION == 6
        for table, rows in before.items():
            assert [tuple(row) for row in connection.execute(f"SELECT * FROM {table}")] == rows
    with store.read() as unit:
        work = unit.tasks.occurrence("home", "identity-4")
        assert work.current_cycle_id is None and work.definition_snapshot.materials == ()
        assert len(unit.tasks.cycles("home", "identity-4")) == 1
        receipt = unit.receipts.get(CommandKey("home", "ha_child", "task.complete", "second-work"))
        assert receipt.historical and receipt.operation_id == "identity-12"
        assert unit.task_materials.list("home", receipt.result.decode()["cycle"]["cycle_id"]) == ()
    from test_task_commands import child_commands

    from domus.application.task_commands import CompleteTask

    commands, _ = child_commands(store)
    replay = commands.complete("second-work", CompleteTask("identity-4", 5, ("child",), 90))
    assert replay.historical and replay.operation_id == receipt.operation_id
    assert replay.result == receipt.result
    store.initialize(require_existing=True)


def material_store(tmp_path, quantity="2"):
    from test_sqlite_task_integrity import perform, populated
    from test_task_material_values import line

    from domus.domain.task_material_values import MaterialQuantity
    from domus.domain.task_materials import MaterialIntent

    store, actor, identifiers, work = populated(tmp_path, materials=(line(),))
    completed, saved, _, _ = perform(store, actor, identifiers, work)
    value = MaterialIntent.record(
        "intent",
        "home",
        work.occurrence_id,
        saved.cycle_id,
        work.definition_snapshot.materials[0],
        None if quantity is None else MaterialQuantity(quantity),
        recorded_by=saved.recorded_by,
        performed_at=saved.performed_at,
        recorded_at=saved.recorded_at,
        recording_mode=saved.rules.material_recording,
        authorized=True,
    )
    return store, completed, saved, value


def save_material(store, value, expected):
    with store.write() as unit:
        unit.task_materials.save(value, expected)


def test_real_file_material_cas_preserves_source_pending_and_confirmed_totals(tmp_path):
    from test_sqlite_snapshots import Clock
    from test_sqlite_task_integrity import validate

    from domus.domain.task_material_values import MaterialPendingReason, MaterialQuantity
    from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots

    store, _, saved, value = material_store(tmp_path)
    with store.read() as unit:
        assert unit.task_materials.get("home", "intent") is None
        assert unit.task_materials.list("other", saved.cycle_id) == ()
    save_material(store, value, 0)
    pending = value.defer(MaterialPendingReason.STOCK_SHORTAGE, 150)
    save_material(store, pending, 1)
    # The confirmation is an explicit semantic fake, not proof of a real Inventory ledger.
    posted = pending.confirm(posting(pending, posted_at=151), 152)
    save_material(store, posted, 2)
    correction = posted.correct(MaterialQuantity("3"), "Extra cleaner", 160)
    save_material(store, correction, 3)
    final = correction.confirm(posting(correction, posted_at=161), 162)
    save_material(store, final, 4)
    validate(store)
    checkpoint = SQLiteSnapshots(store, tmp_path / "snapshot", store.installation, Clock()).create(
        "materials"
    )
    assert checkpoint.schema_version == 6
    copy = SQLiteDatabase(tmp_path / "snapshot/domus.sqlite3", store.installation)
    with copy.read() as unit:
        assert unit.task_materials.get("home", "intent") == final
        assert unit.task_materials.get("other", "intent") is None
        assert unit.task_materials.list("home", saved.cycle_id) == (final,)
        assert final.submitted_quantity.value == "2" and final.quantity.value == "3"
    with pytest.raises(Conflict):
        save_material(store, pending, 1)
    with pytest.raises(Conflict):
        save_material(store, value, 0)


def test_material_source_and_stock_confirmation_are_not_erased_by_reopening_work(tmp_path):
    from test_sqlite_task_integrity import validate

    store, completed, saved, value = material_store(tmp_path)
    save_material(store, value, 0)
    posted = value.confirm(posting(value, posted_at=151), 152)
    save_material(store, posted, 1)
    reopened, closed = completed.reopen(saved, 160, "Repeat work")
    with store.write() as unit:
        unit.tasks.save_cycle(closed, saved.revision)
        unit.tasks.save_occurrence(reopened, completed.revision)
    validate(store)
    with store.read() as unit:
        assert unit.task_materials.list("home", saved.cycle_id) == (posted,)
        assert unit.tasks.occurrence("home", completed.occurrence_id).current_cycle_id is None


def test_material_rollback_uses_enclosing_transaction_and_no_independent_commit(tmp_path):
    store, _, _, value = material_store(tmp_path)
    with pytest.raises(RuntimeError, match="injected"):
        with store.write() as unit:
            unit.task_materials.save(value, 0)
            raise RuntimeError("injected after write")
    with store.read() as unit:
        assert unit.task_materials.get("home", "intent") is None


@pytest.mark.parametrize(
    "field,new",
    [
        ("recorded_by", "child"),
        ("performed_at", 129),
        ("created_at", 141),
        ("authorized_at_recording", False),
        ("submitted_quantity", None),
        ("cycle_id", "other-cycle"),
        ("occurrence_id", "other-occurrence"),
    ],
)
def test_material_immutable_submission_and_scope_cannot_be_rewritten(tmp_path, field, new):
    store, _, _, value = material_store(tmp_path, None if field == "submitted_quantity" else "2")
    save_material(store, value, 0)
    if field == "submitted_quantity":
        from domus.domain.task_material_values import MaterialQuantity

        candidate = replace(
            value.correct(MaterialQuantity("1"), "Attempt replacement", 150),
            submitted_quantity=MaterialQuantity("1"),
        )
    else:
        candidate = replace(value, **{field: new}, revision=2, updated_at=150)
    with pytest.raises(Conflict, match="task_identity_conflict"):
        save_material(store, candidate, 1)


@pytest.mark.parametrize(
    "change",
    [
        "old_time",
        "skip_effect",
        "same_effect_quantity",
        "lost_posting",
        "old_confirmation",
        "same_movement",
        "same_operation",
    ],
)
def test_material_cas_rejects_effect_rewrites_and_revision_gaps(tmp_path, change):
    from domus.domain.task_material_values import MaterialPendingReason, MaterialQuantity

    store, _, _, value = material_store(tmp_path)
    save_material(store, value, 0)
    if change in ("lost_posting", "old_confirmation", "same_movement", "same_operation"):
        confirmed = value.confirm(posting(value, posted_at=151), 152)
        save_material(store, confirmed, 1)
        desired = confirmed.correct(MaterialQuantity("3"), "More", 160)
        if change == "lost_posting":
            candidate = replace(desired, posting=None)
            expected = 2
        else:
            save_material(store, desired, 2)
            proof = posting(desired, posted_at=161)
            if change == "old_confirmation":
                proof = replace(proof, posted_at=150)
            elif change == "same_movement":
                proof = replace(proof, movement_id=confirmed.posting.movement_id)
            else:
                proof = replace(
                    proof, inventory_operation_id=confirmed.posting.inventory_operation_id
                )
            candidate = replace(
                desired,
                posting=proof,
                state=confirmed.state.__class__.CORRECTED,
                pending_reason=None,
                revision=4,
                updated_at=162,
            )
            expected = 3
    elif change == "old_time":
        pending = value.defer(MaterialPendingReason.STOCK_SHORTAGE, 160)
        save_material(store, pending, 1)
        candidate, expected = replace(pending, updated_at=150, revision=3), 2
    elif change == "skip_effect":
        candidate = replace(
            value,
            quantity=MaterialQuantity("3"),
            effect_revision=3,
            revision=3,
            reason="Skipped generation",
        )
        # Save revision 2 first to isolate effect generation from resource CAS.
        save_material(store, value.defer(MaterialPendingReason.STOCK_SHORTAGE, 150), 1)
        expected = 2
    else:
        original = value.correct(MaterialQuantity("3"), "First correction", 150)
        save_material(store, original, 1)
        candidate = replace(original, quantity=MaterialQuantity("4"), revision=3)
        expected = 2
    with pytest.raises(Conflict, match="material_effect_conflict"):
        save_material(store, candidate, expected)


def test_material_queries_are_bounded_scoped_and_validate_exact_headers(tmp_path):
    from domus.domain.errors import InvalidInput

    store, _, saved, value = material_store(tmp_path)
    save_material(store, value, 0)
    with store.read() as unit:
        repository = unit.task_materials
        assert repository.list("home", saved.cycle_id, after="intent") == ()
        assert repository.list("home", saved.cycle_id, limit=1) == (value,)
        for limit in (0, True, 102):
            with pytest.raises(InvalidInput):
                repository.list("home", saved.cycle_id, limit=limit)
        for attempt in (
            lambda: repository.get("bad/id", "intent"),
            lambda: repository.list("home", "bad/id"),
            lambda: repository.list("home", saved.cycle_id, after="bad/id"),
        ):
            with pytest.raises(InvalidInput):
                attempt()
    with store._connection() as connection:
        connection.execute("UPDATE task_material_intents SET state='pending_regularization'")
    with store.read() as unit:
        with pytest.raises(StorageFailure):
            unit.task_materials.get("home", "intent")
        with pytest.raises(StorageFailure):
            unit.task_materials.list("home", saved.cycle_id)


@pytest.mark.parametrize(
    "path,value",
    [
        (("version",), 2),
        (("version",), True),
        (("unknown",), None),
        (("line",), []),
        (("line", "binding"), {}),
        (("line", "planned_quantity"), {"value": "1"}),
        (("quantity",), 2.0),
        (("submitted_quantity",), "2.0"),
        (("state",), "future"),
        (("pending_reason",), "future"),
        (("recording_mode",), "automatic"),
        (("authorized_at_recording",), 1),
        (("posting",), {}),
    ],
)
def test_material_decode_rejects_malformed_or_future_records(path, value):
    body = material_document(intent()).decode()
    current = body
    for part in path[:-1]:
        current = current[part]
    current[path[-1]] = value
    with pytest.raises(StorageFailure, match="invalid_material_record"):
        read_material(json.dumps(body))


@pytest.mark.parametrize(
    "encoded", ["{}", "[]", "{", "null", '{"version":1,"version":1}', "\ud800"]
)
def test_material_decode_rejects_invalid_json_and_duplicate_members(encoded):
    with pytest.raises(StorageFailure):
        read_material(encoded)


@pytest.mark.parametrize(
    "corruption", ["missing", "line", "recorder", "performed", "created", "mode"]
)
def test_snapshot_semantic_validation_rejects_materials_detached_from_original_cycle(
    tmp_path, corruption
):
    from test_sqlite_snapshots import Clock
    from test_sqlite_task_integrity import validate

    from domus.domain.errors import DatabaseRejected, DomusError
    from domus.domain.task_values import MaterialRecording
    from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots

    store, _, _, value = material_store(tmp_path)
    save_material(store, value, 0)
    validate(store)
    if corruption == "missing":
        with store._connection() as connection:
            connection.execute("DELETE FROM task_material_intents")
    else:
        change = {
            "line": {"line": replace(value.line, planned_quantity=value.quantity)},
            "recorder": {"recorded_by": "child"},
            "performed": {"performed_at": 129},
            "created": {"created_at": 139},
            "mode": {"recording_mode": MaterialRecording.SEPARATE},
        }[corruption]
        changed = replace(value, **change)
        with store._connection() as connection:
            connection.execute(
                "UPDATE task_material_intents SET recorded_by=?,document=?",
                (changed.recorded_by, material_document(changed).encoded),
            )
    with pytest.raises(DomusError):
        validate(store)
    with pytest.raises(DatabaseRejected):
        SQLiteSnapshots(store, tmp_path / "snapshot", store.installation, Clock()).create(
            "bad-materials"
        )


def test_schema5_real_offline_activation_upgrades_only_target_and_keeps_original_history(tmp_path):
    from test_activation_compatibility import identity_at
    from test_sqlite_snapshots import Clock

    from domus.domain.snapshots import Snapshot
    from domus.infrastructure.owned_storage import open_storage
    from domus.infrastructure.sqlite_activation import SQLiteActivation
    from domus.infrastructure.sqlite_history import last_committed_at
    from domus.infrastructure.sqlite_restoration import SQLiteRestorations
    from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots

    installation = Installation("047cc6fb-dfb0-4fa4-b3c3-e0fe54d116b6", "edge")
    archive, root, target = tmp_path / "snapshot", tmp_path / "source", tmp_path / "prepared"
    archive.mkdir(mode=0o700)
    root.mkdir(mode=0o700)
    database = archive / "domus.sqlite3"
    frozen = Path(__file__).resolve().parents[1] / "fixtures/sqlite/v5.sql"
    with closing(sqlite3.connect(database, autocommit=True)) as connection:
        connection.executescript(frozen.read_text())
        connection.row_factory = sqlite3.Row
        committed = last_committed_at(connection)
    database.chmod(0o600)
    identity = identity_at(archive, installation)
    checkpoint = Snapshot(
        "old-material-free",
        installation,
        5,
        2000,
        committed,
        hashlib.sha256(database.read_bytes()).hexdigest(),
        database.stat().st_size,
        hashlib.sha256(identity.read_bytes()).hexdigest(),
    )
    manifest = archive / "manifest.json"
    manifest.write_text(checkpoint.document().encoded)
    manifest.chmod(0o600)
    assert SQLiteSnapshots(None, archive, installation, Clock()).inspect() == checkpoint
    source = root / "domus.sqlite3"
    source.write_bytes(database.read_bytes())
    source.chmod(0o600)
    identity_at(root, installation)
    before = source.read_bytes()
    prepared = SQLiteRestorations(
        SQLiteDatabase(source, installation), archive, target, installation, Clock(), checkpoint
    ).prepare("upgrade-materials")
    assert prepared.source.schema_version == 5 and prepared.operation_count == 7
    result = SQLiteActivation(root, installation, Clock(), target).activate()
    assert result.state == "active" and result.record.rollback_snapshot.schema_version == 5
    assert source.read_bytes() == before == database.read_bytes()
    selected = open_storage(root, "edge")
    try:
        with selected.database.read() as unit:
            current = unit.tasks.occurrence("home", "identity-4")
            assert current.definition_snapshot.materials == () and current.current_cycle_id is None
            retained = unit.receipts.get(
                CommandKey("home", "ha_child", "task.complete", "second-work")
            )
            assert retained.historical and retained.operation_id == "identity-12"
            assert (
                unit.task_materials.list("home", retained.result.decode()["cycle"]["cycle_id"])
                == ()
            )
        assert (
            SQLiteSnapshots(selected.database, tmp_path / "new-snapshot", installation, Clock())
            .create("new")
            .schema_version
            == 6
        )
    finally:
        selected.close()


@pytest.mark.parametrize("failure", ["ddl", "definition", "occurrence"])
def test_schema5_failed_migration_rolls_back_schema_documents_and_retained_facts(
    tmp_path, monkeypatch, failure
):
    from domus.domain.errors import StorageFailure
    from domus.infrastructure import sqlite as adapter

    source = Path(__file__).resolve().parents[1] / "fixtures/sqlite/v5.sql"
    path = tmp_path / "old.sqlite3"
    with closing(sqlite3.connect(path, autocommit=True)) as connection:
        connection.executescript(source.read_text())
        if failure != "ddl":
            table = "task_definitions" if failure == "definition" else "task_occurrences"
            connection.execute(f"UPDATE {table} SET document='{{}}'")
    before = path.read_bytes()
    store = SQLiteDatabase(path, Installation("047cc6fb-dfb0-4fa4-b3c3-e0fe54d116b6", "edge"))
    with monkeypatch.context() as patch:
        if failure == "ddl":
            patch.setattr(
                adapter, "MATERIAL_STATEMENTS", (*adapter.MATERIAL_STATEMENTS, "INVALID SQL")
            )
        with pytest.raises(StorageFailure):
            store.initialize(require_existing=True)
    assert path.read_bytes() == before
    with closing(sqlite3.connect(path, autocommit=True)) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 5
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master WHERE name='task_material_intents'"
            ).fetchone()
            is None
        )


@pytest.mark.parametrize(
    "change", ["missing_cycle", "foreign_occurrence", "missing_recorder", "duplicate_line"]
)
def test_material_database_constraints_reject_orphaned_or_duplicate_sources(tmp_path, change):
    store, _, _, value = material_store(tmp_path)
    save_material(store, value, 0)
    candidate = replace(value, intent_id="other-intent")
    if change == "missing_cycle":
        candidate = replace(candidate, cycle_id="missing")
    elif change == "foreign_occurrence":
        candidate = replace(candidate, occurrence_id="other")
    elif change == "missing_recorder":
        candidate = replace(candidate, recorded_by="missing")
    with pytest.raises(Conflict):
        save_material(store, candidate, 0)


def test_repeated_material_definition_update_preserves_or_explicitly_clears_snapshot():
    original = definition(materials=(intent().line,))
    renamed = original.revise(
        replace(original.content, title="Rename"), original.overrides, original.state
    )
    assert renamed.materials == original.materials
    with pytest.raises(Conflict, match="task_unchanged"):
        original.revise(
            original.content, original.overrides, original.state, materials=original.materials
        )
    with pytest.raises(StorageFailure):
        read_definition(json.dumps({**definition_document(original).decode(), "materials": None}))


def test_material_snapshot_definition_rejects_unscoped_or_duplicate_lines():
    from domus.domain.errors import InvalidInput

    value = intent().line
    for materials in (
        [value],
        (value, value),
        (replace(value, binding=replace(value.binding, household_id="other")),),
    ):
        with pytest.raises(InvalidInput):
            definition(materials=materials)


def test_maximum_material_binding_snapshots_and_compact_command_evidence_fit_document_budget():
    from domus.application.task_commands import UpdateTaskDefinition, _change
    from domus.application.task_facts import definition_result
    from domus.domain.task_material_values import MaterialBinding, MaterialLine, MaterialQuantity
    from domus.domain.task_values import TaskContent

    lines = tuple(
        MaterialLine(
            f"line{index:03}" + "x" * 121,
            MaterialBinding(
                "home",
                f"ref{index:03}" + "x" * 122,
                "p" * 128,
                "u" * 128,
                "l" * 128,
                2**63 - 1,
                6,
                "y" * 160,
            ),
            MaterialQuantity("999999999999.999999"),
        )
        for index in range(32)
    )
    content = TaskContent(
        "t" * 160, "d" * 4000, tags=tuple(f"tag{index:02}" + "x" * 59 for index in range(16))
    )
    value = definition(content=content, materials=lines)
    assert read_definition(definition_document(value).encoded) == value
    work = value.new_occurrence("occurrence", 20)
    assert read_occurrence(occurrence_document(work).encoded) == work
    result = definition_result(value)
    change = _change(
        "task.definition.updated",
        UpdateTaskDefinition(value.definition_id, value.revision, content, value.state),
        result,
    )
    assert len(change.audit_detail.encoded.encode()) <= 65536
    assert len(change.event_payload.encoded.encode()) <= 65536
    assert all(
        row["planned_quantity"] == "999999999999.999999" for row in result.decode()["materials"]
    )
