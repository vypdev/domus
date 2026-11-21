"""Actual checkpoint preparation/activation preserves admitted proof without redelivery."""

from dataclasses import replace

import pytest
from test_activation_compatibility import identity_at
from test_daily_automation_execution import due, enabled

from domus.domain.automation_scheduling import ScheduledOutcome
from domus.infrastructure.owned_storage import open_storage
from domus.infrastructure.sqlite_activation import SQLiteActivation
from domus.infrastructure.sqlite_restoration import SQLiteRestorations
from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots


@pytest.mark.parametrize(
    "checkpoint_phase, completed",
    [
        ("before_admission", True),
        ("after_admission", True),
        ("before_admission", False),
    ],
)
def test_actual_restore_preserves_outcomes_and_compatible_rollback_without_a_second_task(
    tmp_path, checkpoint_phase, completed
):
    data = tmp_path / "data"
    data.mkdir(mode=0o700)
    _, engine, store, _, clock, schedule = enabled(data)
    root = store.path.parent
    identity_at(root, store.installation)
    archive, target = tmp_path / "checkpoint", tmp_path / "prepared"
    snapshots = SQLiteSnapshots(store, archive, store.installation, clock)
    if checkpoint_phase == "before_admission":
        checkpoint = snapshots.create("before-admission")
    admitted = due(engine, clock, schedule)
    if checkpoint_phase == "after_admission":
        checkpoint = snapshots.create("after-admission")
    created = engine.execute(admitted.trigger_key) if completed else None
    with store.read() as unit:
        original = unit.scheduled_automations.run("home", admitted.trigger_key)
    assert original.outcome is (ScheduledOutcome.CREATED if completed else ScheduledOutcome.QUEUED)
    SQLiteRestorations(store, archive, target, store.installation, clock, checkpoint).prepare(
        "restore-daily"
    )
    activation = SQLiteActivation(root, store.installation, clock, target).activate()
    assert activation.state == "active"
    selected = open_storage(root, "edge")
    rollback_target = tmp_path / "rollback"
    try:
        # Keeping this process's original startup cutoff models recovery while
        # the wall clock is still in the same admitted window. Real startup
        # skipping is independently asserted by the execution tests.
        restored = replace(engine, transactions=selected.database)
        if checkpoint_phase == "after_admission":
            result = restored.execute(admitted.trigger_key)
            assert result.status == "created" and result.receipt.historical
        else:
            assert restored.admit("daily").status == "retained"
        with selected.database.read() as unit:
            recovered = unit.scheduled_automations.run("home", admitted.trigger_key)
            assert recovered.outcome is (
                ScheduledOutcome.CREATED if completed else ScheduledOutcome.CANCELLED
            )
            assert recovered.planned == original.planned
            assert recovered.grant == original.grant
            assert unit.tasks.definitions("home") == ()
            assert unit.scheduled_automations.pending("home") == ()
            assert all(event.event_type != "task.create" for event in unit.outbox.pending())
            if completed:
                assert recovered.task_operation_id == original.task_operation_id
                assert recovered.task_occurrence_id == original.task_occurrence_id
        SQLiteRestorations(
            selected.database,
            root / "activations/restore-daily/source-checkpoint",
            rollback_target,
            store.installation,
            clock,
            activation.record.rollback_snapshot,
        ).prepare("rollback-daily")
    finally:
        selected.close()
    assert (
        SQLiteActivation(root, store.installation, clock, rollback_target).activate().state
        == "active"
    )
    rolled_back = open_storage(root, "edge")
    try:
        with rolled_back.database.read() as unit:
            assert unit.scheduled_automations.run("home", admitted.trigger_key) == original
            assert len(unit.tasks.definitions("home")) == int(completed)
        if created is not None:
            assert (
                replace(engine, transactions=rolled_back.database)
                .execute(admitted.trigger_key)
                .status
                == "created"
            )
    finally:
        rolled_back.close()
