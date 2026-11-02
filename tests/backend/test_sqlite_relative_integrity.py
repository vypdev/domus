"""Relative state binds its exact generation and original evidence across corruption and restore."""

from dataclasses import replace
from datetime import timedelta

import pytest
from test_sqlite_relative_recurrence import prepared, proof
from test_sqlite_snapshots import Clock

from domus.domain.errors import DatabaseRejected, StorageFailure
from domus.domain.recurrence_planning import PlannedSlot
from domus.domain.recurrence_rules import NominalDate
from domus.domain.relative_recurrence import RelativeSlot, SuccessorVisibility
from domus.infrastructure.sqlite_relative_recurrence_records import relative_schedule_document
from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots


def successor(tmp_path, *, restricted=False, before_successor=None):
    from test_household_commands import Actor
    from test_household_commands import Clock as CommandClock

    from domus.application.relative_recurrence import RelativeRecurrencePlanner
    from domus.application.task_commands import CompleteTask, TaskCommands
    from domus.infrastructure.application_runtime import SecureIdentifiers
    from domus.infrastructure.recurrence_time import PinnedRecurrenceTime

    store, rule, progress, initial, _ = committed(tmp_path)
    commands = TaskCommands(store, Actor(), CommandClock(), SecureIdentifiers())
    with store.read() as unit:
        member = unit.members.by_user("home", "ha_admin").member_id
    done = commands.complete(
        "complete-source",
        CompleteTask(initial.occurrence_id, 1, ("child" if restricted else member,), 90),
    )
    with store.read() as unit:
        cycle = unit.tasks.cycle("home", done.result.decode()["cycle"]["cycle_id"])
        definition = unit.tasks.definition("home", rule.definition_id)
        event = unit.tasks.lifecycle_events("home")[0]
    if before_successor is not None:
        before_successor(store)
    plan = RelativeRecurrencePlanner(PinnedRecurrenceTime()).plan(rule, cycle)
    work = definition.new_occurrence("generated-next", 101)
    slot = RelativeSlot(
        store.installation, rule, plan.planned, work.occurrence_id, work.created_at, plan.source
    )
    with store.write() as unit:
        unit.tasks.save_occurrence(work, 0)
        unit.recurrence.add_relative_slot(slot)
        next_progress, receipt = proof(
            unit, slot, replace(progress, source_after=event.position), "successor-operation"
        )
        unit.recurrence.save_relative_progress(next_progress, 2)
    return commands, store, rule, next_progress, slot, receipt


def committed(tmp_path):
    store, rule, progress, work_id = prepared(tmp_path)
    slot = RelativeSlot(store.installation, rule, rule.initial, work_id, 100)
    with store.write() as unit:
        unit.recurrence.add_relative_slot(slot)
        progress, receipt = proof(unit, slot, progress)
        unit.recurrence.save_relative_progress(progress, 1)
    return store, rule, progress, slot, receipt


@pytest.mark.parametrize("field", ["interval", "initial", "policy", "visibility"])
@pytest.mark.parametrize("surface", ["value", "read", "snapshot"])
def test_valid_fields_cannot_rebind_unconsumed_relative_progress(tmp_path, field, surface):
    store, rule, progress, _ = prepared(tmp_path)
    changes = {
        "interval": {"interval": replace(rule.interval, days=31)},
        "initial": {
            "initial": PlannedSlot(
                NominalDate(rule.initial.nominal.local + timedelta(days=1)), None
            )
        },
        "policy": {"policy": replace(rule.policy, revision=2)},
        "visibility": {"visibility": SuccessorVisibility.AT_VERIFICATION},
    }
    altered = replace(rule, **changes[field])
    if surface == "value":
        assert not progress.matches_schedule(altered)
        return
    with store._connection() as connection:
        connection.execute(
            "UPDATE recurrence_rules SET document=?", (relative_schedule_document(altered).encoded,)
        )
    original = store.path.read_bytes()
    if surface == "read":
        with store.read() as unit:
            with pytest.raises(StorageFailure, match="invalid_recurrence_record"):
                unit.recurrence.relative_progress("home", rule.schedule_id)
    else:
        with pytest.raises(DatabaseRejected, match="invalid_snapshot_records"):
            SQLiteSnapshots(store, tmp_path / "bad", store.installation, Clock()).create("bad")
    assert store.path.read_bytes() == original


def test_restore_of_a_missing_mapping_retains_its_original_and_existing_manual_work(tmp_path):
    from test_activation_compatibility import identity_at

    from domus.infrastructure.owned_storage import open_storage
    from domus.infrastructure.sqlite_activation import SQLiteActivation
    from domus.infrastructure.sqlite_restoration import SQLiteRestorations

    root = tmp_path / "source"
    root.mkdir(mode=0o700)
    store, rule, progress, work_id = prepared(root)
    identity_at(root, store.installation)
    archive, target = tmp_path / "checkpoint", tmp_path / "prepared"
    checkpoint = SQLiteSnapshots(store, archive, store.installation, Clock()).create(
        "before-mapping"
    )
    slot = RelativeSlot(store.installation, rule, rule.initial, work_id, 100)
    with store.write() as unit:
        unit.recurrence.add_relative_slot(slot)
        advanced, receipt = proof(unit, slot, progress)
        unit.recurrence.save_relative_progress(advanced, 1)
    SQLiteRestorations(store, archive, target, store.installation, Clock(), checkpoint).prepare(
        "relative-restore"
    )
    assert SQLiteActivation(root, store.installation, Clock(), target).activate().state == "active"
    storage = open_storage(root, "edge")
    try:
        with storage.database.write() as unit:
            historical = unit.receipts.get(slot.command)
            assert historical.historical and historical.operation_id == receipt.operation_id
            assert unit.tasks.occurrence("home", work_id) is not None
            assert unit.recurrence.relative_slot("home", slot.key) is None
            unit.recurrence.save_relative_progress(advanced, 1)
        with storage.database.read() as unit:
            assert unit.recurrence.relative_progress("home", rule.schedule_id) == advanced
            assert unit.recurrence.relative_slots("home", rule.schedule_id) == ()
            assert unit.receipts.get(slot.command).historical
            assert all(item.event_id != receipt.operation_id for item in unit.outbox.pending())
        assert SQLiteSnapshots(
            storage.database, tmp_path / "after", store.installation, Clock()
        ).create("after")
    finally:
        storage.close()


def test_actual_source_cycle_survives_approval_and_closure_without_rewriting_slot_facts(tmp_path):
    from domus.application.task_commands import ReopenTask, VerifyTask
    from domus.domain.task_values import VerificationState

    commands, store, rule, progress, slot, _ = successor(tmp_path, restricted=True)
    original_source = slot.source
    assert original_source.cycle.verification is VerificationState.PENDING
    assert SQLiteSnapshots(store, tmp_path / "before", store.installation, Clock()).create("before")
    commands.verify(
        "approve",
        VerifyTask(
            slot.source.cycle.occurrence_id,
            2,
            slot.source.cycle.cycle_id,
            VerificationState.APPROVED,
        ),
    )
    commands.reopen(
        "reopen",
        ReopenTask(slot.source.cycle.occurrence_id, 3, slot.source.cycle.cycle_id, "Repeat"),
    )
    with store.read() as unit:
        assert unit.recurrence.relative_slot("home", slot.key) == slot
        assert unit.recurrence.relative_progress("home", rule.schedule_id) == progress
        assert unit.tasks.cycle("home", slot.source.cycle.cycle_id).closed_at is not None
    assert slot.source == original_source
    # This verifies retained storage facts; a recurrence lifecycle consumer must still
    # invalidate/review the successor rather than treating this read as execution.
    assert SQLiteSnapshots(store, tmp_path / "after", store.installation, Clock()).create("after")


def test_self_consistent_saved_source_proof_cannot_replace_the_actual_live_completion(tmp_path):
    from domus.domain.storage import JsonDocument
    from domus.infrastructure.recurrence_time import PinnedRecurrenceTime
    from domus.infrastructure.sqlite_relative_recurrence_records import relative_slot_document

    _, store, _, _, slot, receipt = successor(tmp_path)
    cycle = replace(slot.source.cycle, performed_at=89)
    source = replace(
        slot.source,
        cycle=cycle,
        performed_local=PinnedRecurrenceTime().local_at(89, slot.schedule.policy),
    )
    altered = replace(slot, source=source)
    assert altered.key == slot.key
    body = receipt.result.decode()
    body["relative_slot_fingerprint"] = altered.evidence_fingerprint
    changed_receipt = replace(receipt, result=JsonDocument.from_value(body))
    assert altered.matches_receipt(changed_receipt)
    with store._connection() as connection:
        connection.execute(
            "UPDATE recurrence_relative_slots SET document=? WHERE slot_key=?",
            (relative_slot_document(altered).encoded, slot.key),
        )
        connection.execute(
            "UPDATE receipts SET result=? WHERE operation_id=?",
            (changed_receipt.result.encoded, receipt.operation_id),
        )
    before = store.path.read_bytes()
    with store.read() as unit:
        with pytest.raises(StorageFailure, match="invalid_recurrence_record"):
            unit.recurrence.relative_slot("home", slot.key)
    with pytest.raises(DatabaseRejected, match="invalid_snapshot_records"):
        SQLiteSnapshots(store, tmp_path / "bad", store.installation, Clock()).create("bad")
    assert store.path.read_bytes() == before


@pytest.mark.parametrize(
    "change",
    [
        "missing-header",
        "header-revision",
        "header-operation",
        "header-fingerprint",
        "missing-original",
        "original-json",
        "original-state",
        "slot-header",
        "slot-source",
        "slot-original",
    ],
)
def test_current_relative_records_refuse_altered_headers_and_originals(tmp_path, change):
    from domus.domain.storage import JsonDocument

    _, store, rule, _, slot, receipt = successor(tmp_path)
    with store._connection() as connection:
        if change == "missing-header":
            connection.execute("DELETE FROM recurrence_progress_evidence")
        elif change.startswith("header-"):
            column, value = {
                "header-revision": ("progress_revision", 99),
                "header-operation": ("operation_id", "wrong"),
                "header-fingerprint": ("evidence_fingerprint", "b" * 64),
            }[change]
            connection.execute(f"UPDATE recurrence_progress_evidence SET {column}=?", (value,))
        elif change == "missing-original":
            connection.execute("DELETE FROM receipts WHERE operation_id=?", (receipt.operation_id,))
        elif change == "slot-header":
            connection.execute(
                "UPDATE recurrence_relative_slots SET created_at=102 WHERE slot_key=?", (slot.key,)
            )
        elif change == "slot-source":
            connection.execute(
                "UPDATE recurrence_relative_slots SET source_cycle_id='missing' WHERE slot_key=?",
                (slot.key,),
            )
        else:
            body = receipt.result.decode()
            if change == "original-state":
                body["relative_progress"]["source_after"] += 1
            if change == "slot-original":
                body["relative_slot_fingerprint"] = "b" * 64
            result = (
                "invalid JSON"
                if change == "original-json"
                else JsonDocument.from_value(body).encoded
            )
            connection.execute(
                "UPDATE receipts SET result=? WHERE operation_id=?", (result, receipt.operation_id)
            )
    original = store.path.read_bytes()
    with store.read() as unit:
        with pytest.raises(StorageFailure, match="invalid_recurrence_record"):
            unit.recurrence.relative_progress("home", rule.schedule_id)
    assert store.path.read_bytes() == original


@pytest.mark.parametrize(
    "change", ["missing-progress", "unknown-kind", "missing-rule", "slot-json"]
)
def test_semantic_snapshot_checks_cover_missing_and_unrecognized_relative_records(tmp_path, change):
    from domus.infrastructure.sqlite_recurrence_integrity import verify_recurrence_records

    store, _, _, slot, receipt = committed(tmp_path)
    with store._connection() as connection:
        if change == "missing-progress":
            connection.execute("DELETE FROM recurrence_progress")
        elif change == "unknown-kind":
            connection.execute("PRAGMA ignore_check_constraints=ON")
            connection.execute("UPDATE recurrence_rules SET timing_kind='unknown'")
        elif change == "missing-rule":
            connection.execute("DELETE FROM recurrence_rules")
        else:
            connection.execute(
                "UPDATE receipts SET result='invalid JSON' WHERE operation_id=?",
                (receipt.operation_id,),
            )
        with pytest.raises(StorageFailure):
            verify_recurrence_records(connection, store.installation)
    if change == "slot-json":
        with store.read() as unit:
            with pytest.raises(StorageFailure, match="invalid_recurrence_record"):
                unit.recurrence.relative_slot("home", slot.key)


def test_real_restore_retains_a_generated_successor_proof_without_recreating_its_task(tmp_path):
    from test_activation_compatibility import identity_at

    from domus.infrastructure.owned_storage import open_storage
    from domus.infrastructure.sqlite_activation import SQLiteActivation
    from domus.infrastructure.sqlite_restoration import SQLiteRestorations

    root, archive, target = tmp_path / "source", tmp_path / "before", tmp_path / "prepared"
    root.mkdir(mode=0o700)
    checkpoints = []

    def freeze(store):
        identity_at(root, store.installation)
        checkpoints.append(
            SQLiteSnapshots(store, archive, store.installation, Clock()).create("before-child")
        )

    _, store, rule, progress, slot, receipt = successor(root, before_successor=freeze)
    SQLiteRestorations(store, archive, target, store.installation, Clock(), checkpoints[0]).prepare(
        "relative-generated-restore"
    )
    assert SQLiteActivation(root, store.installation, Clock(), target).activate().state == "active"
    storage = open_storage(root, "edge")
    try:
        with storage.database.write() as unit:
            assert unit.tasks.occurrence("home", slot.occurrence_id) is None
            assert unit.receipts.get(slot.command).historical
            unit.recurrence.save_relative_progress(progress, 2)
        with storage.database.read() as unit:
            assert unit.recurrence.relative_progress("home", rule.schedule_id) == progress
            assert unit.recurrence.relative_slot("home", slot.key) is None
            assert len(unit.tasks.occurrences("home")) == 1
            assert unit.receipts.get(slot.command).operation_id == receipt.operation_id
            assert all(item.event_id != receipt.operation_id for item in unit.outbox.pending())
        assert SQLiteSnapshots(
            storage.database, tmp_path / "after", store.installation, Clock()
        ).create("after")
    finally:
        storage.close()


def test_corrupt_original_on_a_write_is_storage_failure_without_partial_state(tmp_path):
    store, rule, progress, _, receipt = committed(tmp_path)
    with store._connection() as connection:
        connection.execute(
            "UPDATE receipts SET result='invalid JSON' WHERE operation_id=?",
            (receipt.operation_id,),
        )
    original = store.path.read_bytes()
    with pytest.raises(StorageFailure, match="invalid_recurrence_record"):
        with store.write() as unit:
            unit.recurrence.save_relative_progress(replace(progress, revision=3), 2)
    assert store.path.read_bytes() == original
