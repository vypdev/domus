"""Cancellation is an atomic scoped terminal outcome, including retained original facts."""

from dataclasses import replace

import pytest
from test_activation_compatibility import identity_at
from test_daily_automation_execution import due, enabled

from domus.application.automation_scheduled_cancellation import _CancellationAuthority
from domus.application.automation_scheduled_control import DailyControlRequest
from domus.application.automation_scheduled_documents import receipt_run
from domus.domain.automation_scheduling import ScheduledOutcome
from domus.domain.errors import DatabaseRejected, Forbidden, StorageFailure
from domus.domain.storage import CommandKey
from domus.infrastructure.owned_storage import open_storage
from domus.infrastructure.sqlite import SQLiteOutbox
from domus.infrastructure.sqlite_activation import SQLiteActivation
from domus.infrastructure.sqlite_restoration import SQLiteRestorations
from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots, _verify_database


@pytest.mark.parametrize("failure", ["cancellation", "control"])
def test_cancellation_proof_and_control_share_one_writer_and_roll_back_together(
    tmp_path, monkeypatch, failure
):
    control, engine, store, _, clock, schedule = enabled(tmp_path)
    step = due(engine, clock, schedule)
    current = control.review("daily", 1)
    request = DailyControlRequest(
        "daily", 1, current.control.control_revision, current.schedule.revision
    )
    key = CommandKey("home", schedule.grant.principal, "automation.scheduled.run", step.trigger_key)
    append = SQLiteOutbox.append

    def fail(self, event):
        target = (
            "automation.scheduled.run" if failure == "cancellation" else "automation.daily.disable"
        )
        if event.event_type == target:
            raise StorageFailure("injected_cancellation_failure")
        return append(self, event)

    with monkeypatch.context() as patch:
        patch.setattr(SQLiteOutbox, "append", fail)
        with pytest.raises(StorageFailure, match="injected_cancellation_failure"):
            control.disable("disable", request)
    with store.read() as unit:
        assert unit.automation_controls.get("home", "daily").enabled
        assert unit.scheduled_automations.schedule("home", "daily") == current.schedule
        assert (
            unit.scheduled_automations.run("home", step.trigger_key).outcome
            is ScheduledOutcome.QUEUED
        )
        assert unit.receipts.get(key) is None and unit.tasks.definitions("home") == ()
    first = control.disable("disable", request)
    assert control.disable("disable", request) == first
    with store.read() as unit:
        proof = unit.receipts.get(key)
        cancelled = unit.scheduled_automations.run("home", step.trigger_key)
        assert receipt_run(proof) == cancelled and cancelled.outcome is ScheduledOutcome.CANCELLED
        assert unit.scheduled_automations.pending("home") == ()
        assert all(event.event_id != proof.operation_id for event in unit.outbox.pending())
        assert unit.tasks.definitions("home") == ()


@pytest.mark.parametrize(
    "forgery", ["action", "installation", "household", "terminal", "admission", "scope"]
)
def test_cancellation_authority_cannot_be_used_for_a_task_or_another_pending_snapshot(
    tmp_path, forgery
):
    _, engine, store, _, clock, schedule = enabled(tmp_path)
    step = due(engine, clock, schedule)
    with store.read() as unit:
        run = unit.scheduled_automations.run("home", step.trigger_key)
    value, scope = run, engine.scope
    action = "automation.scheduled.run"
    if forgery == "action":
        action = "task.create"
    elif forgery == "installation":
        value = replace(
            run,
            grant=replace(run.grant, installation=replace(store.installation, channel="stable")),
        )
    elif forgery == "household":
        value = replace(run, grant=replace(run.grant, household_id="foreign"))
    elif forgery == "terminal":
        value = run.finish(ScheduledOutcome.CANCELLED, clock.now())
    elif forgery == "admission":
        value = replace(run, admitted_at=run.admitted_at + 1)
    else:
        scope = replace(scope, household_id="foreign")
    command = CommandKey(scope.household_id, value.grant.principal, action, value.key)
    with store.read() as unit:
        with pytest.raises(Forbidden):
            _CancellationAuthority(scope, value).require(command, unit)
        assert unit.tasks.definitions("home") == ()
        assert unit.scheduled_automations.run("home", run.key) == run
        assert (
            unit.receipts.get(
                CommandKey("home", run.grant.principal, "automation.scheduled.run", run.key)
            )
            is None
        )


def test_revoking_a_restored_queue_preserves_its_actual_historical_task_instead_of_relabelling_it(
    tmp_path,
):
    data = tmp_path / "data"
    data.mkdir(mode=0o700)
    control, engine, store, _, clock, schedule = enabled(data)
    root = store.path.parent
    identity_at(root, store.installation)
    step = due(engine, clock, schedule)
    archive, target = tmp_path / "checkpoint", tmp_path / "prepared"
    checkpoint = SQLiteSnapshots(store, archive, store.installation, clock).create("queued")
    created = engine.execute(step.trigger_key)
    with store.read() as unit:
        original = unit.scheduled_automations.run("home", step.trigger_key)
    SQLiteRestorations(store, archive, target, store.installation, clock, checkpoint).prepare(
        "restore-created"
    )
    assert SQLiteActivation(root, store.installation, clock, target).activate().state == "active"
    restored = open_storage(root, "edge")
    try:
        manager = replace(control, transactions=restored.database)
        current = manager.review("daily", 1)
        manager.disable(
            "disable",
            DailyControlRequest(
                "daily", 1, current.control.control_revision, current.schedule.revision
            ),
        )
        with restored.database.read() as unit:
            actual = unit.scheduled_automations.run("home", step.trigger_key)
            assert actual == original and actual.outcome is ScheduledOutcome.CREATED
            proof = unit.receipts.get(created.receipt.command)
            assert proof.historical and proof.operation_id == created.receipt.operation_id
            assert unit.tasks.definitions("home") == ()
            assert unit.scheduled_automations.pending("home") == ()
        assert (
            replace(engine, transactions=restored.database).execute(step.trigger_key).status
            == "created"
        )
        with restored.database._connection() as connection:
            assert _verify_database(connection, restored.database, previous=False) == 38
    finally:
        restored.close()


def test_checkpoint_requires_the_exact_terminal_cancellation_receipt(tmp_path):
    control, engine, store, _, clock, schedule = enabled(tmp_path)
    due(engine, clock, schedule)
    current = control.review("daily", 1)
    control.disable(
        "disable",
        DailyControlRequest(
            "daily", 1, current.control.control_revision, current.schedule.revision
        ),
    )
    with store._connection() as connection:
        # Removing the whole envelope isolates semantic run-proof validation from
        # the separate generic receipt/audit/outbox completeness guard.
        proof = connection.execute(
            "SELECT operation_id FROM receipts WHERE action='automation.scheduled.run'"
        ).fetchone()[0]
        connection.execute("DELETE FROM outbox WHERE event_id=?", (proof,))
        connection.execute("DELETE FROM audit WHERE operation_id=?", (proof,))
        connection.execute("DELETE FROM receipts WHERE operation_id=?", (proof,))
        with pytest.raises(DatabaseRejected, match="invalid_snapshot_records"):
            _verify_database(connection, store, previous=False)
