"""Actual checkpoint preparation/activation preserves admitted proof without redelivery."""

from dataclasses import replace

import pytest
from test_activation_compatibility import identity_at
from test_daily_automation_execution import due, enabled

from domus.application.automation_execution import AutomationExecution, ConfigureAutomation
from domus.application.automation_scheduled_control import DailyControlRequest, ReviewedDailyRequest
from domus.application.automation_scheduled_documents import receipt_run
from domus.application.task_commands import TaskCommands
from domus.domain.automation import AutomationDraft, AutomationRule
from domus.domain.automation_scheduling import ScheduledOutcome
from domus.domain.storage import CommandKey
from domus.domain.task_values import TaskContent
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


@pytest.mark.parametrize(
    "retirement", ["disable", "daily_regrant", "manual_switch", "worker_rejection"]
)
def test_restore_after_admission_cannot_resume_a_run_cancelled_after_the_checkpoint(
    tmp_path, retirement
):
    data = tmp_path / "data"
    data.mkdir(mode=0o700)
    control, engine, store, actor, clock, schedule = enabled(data)
    root = store.path.parent
    identity_at(root, store.installation)
    step = due(engine, clock, schedule)
    archive, target = tmp_path / "checkpoint", tmp_path / "prepared"
    checkpoint = SQLiteSnapshots(store, archive, store.installation, clock).create("queued")
    current = control.review("daily", 1)
    if retirement == "disable":
        control.disable(
            "disable",
            DailyControlRequest(
                "daily", 1, current.control.control_revision, current.schedule.revision
            ),
        )
    elif retirement == "daily_regrant":
        control.enable(
            "renew",
            ReviewedDailyRequest(
                "daily",
                1,
                current.control.control_revision,
                current.schedule.revision,
                current.proposed_times[0],
            ),
        )
    elif retirement == "manual_switch":
        with store.write() as unit:
            unit.automation_drafts.append(
                "home",
                AutomationDraft(
                    "daily", 2, AutomationRule(1, "manual", None, TaskContent("Later manual task"))
                ),
            )
        manual = AutomationExecution(
            store,
            control.scope,
            actor,
            actor.current,
            clock,
            control.identifiers,
            TaskCommands(store, actor, clock, control.identifiers),
        )
        manual.configure("switch", ConfigureAutomation("daily", 2, 1, True))
    else:
        with store.write() as unit:
            prior = unit.automation_controls.get("home", "daily")
            unit.automation_controls.save(
                "home", replace(prior, control_revision=2, enabled=False), 1
            )
        assert engine.execute(step.trigger_key).status == "cancelled"
    with store.read() as unit:
        cancelled = unit.scheduled_automations.run("home", step.trigger_key)
        assert cancelled.outcome is ScheduledOutcome.CANCELLED
        assert unit.tasks.definitions("home") == ()
    SQLiteRestorations(store, archive, target, store.installation, clock, checkpoint).prepare(
        "restore-cancelled"
    )
    activation = SQLiteActivation(root, store.installation, clock, target).activate()
    assert activation.state == "active"
    restored = open_storage(root, "edge")
    rollback_target = tmp_path / "rollback-cancellation"
    try:
        recovered = replace(engine, transactions=restored.database)
        assert recovered.execute(step.trigger_key).status == "cancelled"
        assert recovered.execute(step.trigger_key).status == "cancelled"
        with restored.database.read() as unit:
            assert unit.tasks.definitions("home") == ()
            assert unit.scheduled_automations.pending("home") == ()
            assert unit.scheduled_automations.run("home", step.trigger_key) == cancelled
            original = unit.receipts.get(
                CommandKey(
                    "home", cancelled.grant.principal, "automation.scheduled.run", cancelled.key
                )
            )
            assert original is not None and original.historical
            assert receipt_run(original) == cancelled
        SQLiteRestorations(
            restored.database,
            root / "activations/restore-cancelled/source-checkpoint",
            rollback_target,
            store.installation,
            clock,
            activation.record.rollback_snapshot,
        ).prepare("rollback-cancellation")
    finally:
        restored.close()
    assert (
        SQLiteActivation(root, store.installation, clock, rollback_target).activate().state
        == "active"
    )
    rollback = open_storage(root, "edge")
    try:
        assert (
            replace(engine, transactions=rollback.database).execute(step.trigger_key).status
            == "cancelled"
        )
        with rollback.database.read() as unit:
            assert unit.tasks.definitions("home") == ()
            assert unit.scheduled_automations.pending("home") == ()
            assert unit.scheduled_automations.run("home", step.trigger_key) == cancelled
            assert unit.receipts.get(original.command).operation_id == original.operation_id
    finally:
        rollback.close()
