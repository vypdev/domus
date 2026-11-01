"""Task state and source events survive offline activation without replaying later work."""

from pathlib import Path

import pytest
from test_activation_compatibility import identity_at
from test_sqlite_snapshots import Clock
from test_sqlite_task_integrity import FixedClock, perform, populated

from domus.application.authorization import HouseholdAccess, MembershipAuthorization
from domus.application.commands import AtomicCommands
from domus.domain.identity import Permission
from domus.domain.storage import CommandKey
from domus.domain.task_values import OccurrenceState
from domus.infrastructure.owned_storage import open_storage
from domus.infrastructure.sqlite_activation import SQLiteActivation
from domus.infrastructure.sqlite_restoration import SQLiteRestorations
from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots


def test_restore_keeps_original_task_state_and_retains_later_completion_as_processed(
    tmp_path: Path,
) -> None:
    root, archive, target = tmp_path / "source", tmp_path / "checkpoint", tmp_path / "prepared"
    store, actor, identifiers, original = populated(root)
    identity_at(root, store.installation)
    checkpoint = SQLiteSnapshots(store, archive, store.installation, Clock()).create("before-work")
    _, saved, receipt, payload = perform(store, actor, identifiers, original)
    source_bytes, checkpoint_bytes = (
        store.path.read_bytes(),
        (archive / "domus.sqlite3").read_bytes(),
    )
    adapter = SQLiteRestorations(store, archive, target, store.installation, Clock(), checkpoint)
    prepared = adapter.prepare("restore-tasks")
    assert prepared.source.schema_version == checkpoint.schema_version == 5
    assert prepared.operation_count == 3 and prepared.current_operations == 2
    assert adapter.inspect() == prepared and store.path.read_bytes() == source_bytes
    assert (archive / "domus.sqlite3").read_bytes() == checkpoint_bytes
    activation = SQLiteActivation(root, store.installation, Clock(), target)
    result = activation.activate()
    assert result.state == "active"
    storage = open_storage(root, "edge")
    try:
        with storage.database.read() as unit:
            assert unit.tasks.occurrence("home", "occurrence") == original
            assert unit.tasks.cycle("home", saved.cycle_id) is None
            old = unit.receipts.get_operation("home", actor.human.ha_user_id, receipt.operation_id)
            assert old.historical and old.archived_by == "restore-tasks"
            assert old.result == receipt.result
            assert all(event.event_id != receipt.operation_id for event in unit.outbox.pending())
        authority = MembershipAuthorization(
            HouseholdAccess(actor.human), "task.complete", Permission.TASKS_COMPLETE
        )
        commands = AtomicCommands(storage.database, authority, FixedClock(180), identifiers)
        replayed = commands.execute(
            CommandKey("home", actor.human.ha_user_id, "task.complete", "complete"),
            payload,
            lambda unit: pytest.fail("A historical completion must never execute again"),
        )
        assert replayed.historical and replayed.operation_id == receipt.operation_id
        with storage.database.read() as unit:
            current = unit.tasks.occurrence("home", "occurrence")
            assert current.state is OccurrenceState.AVAILABLE and current.current_cycle_id is None
            assert unit.tasks.cycle("home", saved.cycle_id) is None
    finally:
        storage.close()
    # Rollback uses the supported restore pipeline and its sealed source checkpoint.
    rollback_checkpoint = result.record.rollback_snapshot
    rollback_archive = root / "activations/restore-tasks/source-checkpoint"
    rollback_target = tmp_path / "rollback-prepared"
    previous = open_storage(root, "edge")
    try:
        SQLiteRestorations(
            previous.database,
            rollback_archive,
            rollback_target,
            store.installation,
            Clock(),
            rollback_checkpoint,
        ).prepare("rollback-tasks")
    finally:
        previous.close()
    rollback = SQLiteActivation(root, store.installation, Clock(), rollback_target).activate()
    assert rollback.state == "active" and rollback.selected_generation == "rollback-tasks"
    again = open_storage(root, "edge")
    try:
        with again.database.read() as unit:
            assert unit.tasks.cycle("home", saved.cycle_id) == saved
            assert unit.tasks.occurrence("home", "occurrence").state is OccurrenceState.COMPLETED
    finally:
        again.close()
