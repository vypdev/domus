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
    assert prepared.source.schema_version == checkpoint.schema_version == 8
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


@pytest.mark.parametrize("action", ["create", "claim"])
def test_real_task_commands_return_historical_receipts_without_reapplying_restored_away_work(
    tmp_path: Path, action: str
) -> None:
    from test_task_commands import child_commands, resource
    from test_task_commands import fixture as task_fixture

    from domus.application.task_commands import ClaimTask, CreateTask, TaskCommands
    from domus.domain.task_values import TaskContent

    root, archive, target = tmp_path / "source", tmp_path / "checkpoint", tmp_path / "prepared"
    root.mkdir(mode=0o700)
    commands, store, actor, identifiers = task_fixture(root)
    identity_at(root, store.installation)
    create = CreateTask(TaskContent("Work"))
    work_id = None
    if action == "claim":
        work_id = resource(commands.create("create", create))[1]
    checkpoint = SQLiteSnapshots(store, archive, store.installation, Clock()).create(
        "before-command"
    )
    if action == "create":
        request = create
        original = commands.create("create", request)
        proof = actor
    else:
        service, proof = child_commands(store, identifiers=identifiers)
        request = ClaimTask(work_id, 1)
        original = service.claim("claim", request)
    count = identifiers.count
    SQLiteRestorations(store, archive, target, store.installation, Clock(), checkpoint).prepare(
        "restore-command"
    )
    assert SQLiteActivation(root, store.installation, Clock(), target).activate().state == "active"
    restored = open_storage(root, "edge")
    try:
        service = TaskCommands(restored.database, proof, Clock(), identifiers)
        result = getattr(service, action)(action, request)
        assert result.historical and result.operation_id == original.operation_id
        assert result.result == original.result and identifiers.count == count
        with restored.database.read() as unit:
            if action == "create":
                assert unit.tasks.definitions("home") == unit.tasks.occurrences("home") == ()
                assert unit.tasks.policy("home") is None
            else:
                work = unit.tasks.occurrence("home", work_id)
                assert work.assignee_ids == () and work.state is OccurrenceState.AVAILABLE
                assert work.revision == 1
    finally:
        restored.close()
