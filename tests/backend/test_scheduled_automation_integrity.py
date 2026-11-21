"""Fault injection rejects wrong scoped projections and incomplete durable proof."""

import json
import sqlite3
from contextlib import closing
from dataclasses import replace
from datetime import timedelta
from unittest.mock import Mock

import pytest
from test_daily_automation_control import setup
from test_daily_automation_execution import due, enabled
from test_scheduled_automation_storage import source

from domus.application.automation_scheduled_authority import RUN_SCHEDULED_AUTOMATION
from domus.application.automation_scheduled_cancellation import ScheduledCancellations
from domus.application.automation_scheduled_control import ReviewedDailyRequest
from domus.application.automation_scheduled_documents import read_run, run_document
from domus.application.automation_scheduled_execution import ScheduledAutomationExecution
from domus.application.fixed_materialization import MaintenanceScope
from domus.application.inventory import InventoryCommands
from domus.domain.automation import StockCondition
from domus.domain.automation_scheduling import ScheduledOutcome
from domus.domain.errors import DatabaseRejected, StorageFailure
from domus.domain.inventory import BaseUnit
from domus.domain.recurrence_time import NominalTime
from domus.domain.storage import CommandKey, JsonDocument, Receipt
from domus.domain.task_values import TaskContent
from domus.infrastructure.recurrence_time import PinnedRecurrenceTime
from domus.infrastructure.sqlite_automation_drafts import SQLiteAutomationDrafts
from domus.infrastructure.sqlite_inventory import SQLiteInventory
from domus.infrastructure.sqlite_receipts import SQLiteReceipts
from domus.infrastructure.sqlite_snapshots import _verify_database


@pytest.mark.parametrize("fault", ["missing_run", "changed_rule", "wrong_action", "queued_result"])
def test_an_invalid_original_outcome_never_becomes_a_new_effect_or_success(
    tmp_path, monkeypatch, fault
):
    _, engine, store, _, clock, schedule = enabled(tmp_path)
    step = due(engine, clock, schedule)
    with store.read() as unit:
        run = unit.scheduled_automations.run("home", step.trigger_key)
    command = CommandKey("home", run.grant.principal, RUN_SCHEDULED_AUTOMATION, run.key)
    finished = run.finish(ScheduledOutcome.NO_TASK, clock.now())
    if fault == "changed_rule":
        draft = replace(
            run.grant.draft,
            rule=replace(run.grant.draft.rule, task=TaskContent("Unapproved title")),
        )
        finished = replace(finished, grant=replace(finished.grant, draft=draft))
    if fault == "queued_result":
        finished = run
    result = (
        {}
        if fault == "missing_run"
        else {"trigger_key": run.key, "run": run_document(finished).decode()}
    )
    original = Receipt(
        command,
        step.receipt.payload_fingerprint,
        "injected-original",
        JsonDocument.from_value(result),
        clock.now(),
    )
    if fault == "wrong_action":
        original = replace(original, command=replace(command, action="task.create"))
    read = SQLiteReceipts.get

    def injected(self, requested):
        return original if requested == command else read(self, requested)

    with monkeypatch.context() as patch:
        patch.setattr(SQLiteReceipts, "get", injected)
        with pytest.raises(StorageFailure, match="invalid_daily_automation_outcome"):
            engine.execute(run.key)
    with store.read() as unit:
        assert unit.scheduled_automations.run("home", run.key) == run
        assert unit.tasks.definitions("home") == ()
        assert unit.receipts.get(command) is None


def test_missing_scoped_condition_data_records_denial_without_creating_a_task(
    tmp_path, monkeypatch
):
    service, store, actor, clock = setup(tmp_path)
    inventory = InventoryCommands(store, actor, clock, service.identifiers)
    product = inventory.register("soap", "Soap", BaseUnit.PIECE).result.decode()["product_id"]
    with store.write() as unit:
        draft = unit.automation_drafts.latest("home", "daily")
        unit.automation_drafts.append(
            "home",
            replace(draft, revision=2, rule=replace(draft.rule, condition=StockCondition(product))),
        )
    view = service.review("daily", 2)
    service.enable("enable", ReviewedDailyRequest("daily", 2, 0, 0, view.proposed_times[0]))
    engine = ScheduledAutomationExecution(
        store, service.scope, clock, service.identifiers, service.planner, clock.now()
    )
    with store.read() as unit:
        schedule = unit.scheduled_automations.schedule("home", "daily")
    step = due(engine, clock, schedule)
    read = SQLiteInventory.product

    def absent(self, home, product_id):
        return None if home == "home" and product_id == product else read(self, home, product_id)

    with monkeypatch.context() as patch:
        patch.setattr(SQLiteInventory, "product", absent)
        assert engine.execute(step.trigger_key).status == "denied"
    with store.read() as unit:
        assert unit.tasks.definitions("home") == ()
        assert (
            unit.scheduled_automations.run("home", step.trigger_key).outcome
            is ScheduledOutcome.DENIED
        )


def test_changed_immutable_source_is_not_admitted_and_missing_active_source_is_not_an_empty_review(
    tmp_path, monkeypatch
):
    service, engine, store, _, clock, schedule = enabled(tmp_path)
    clock.now.return_value = schedule.next_time.instant_ms
    read = SQLiteAutomationDrafts.revision

    def changed(self, home, rule, revision):
        value = read(self, home, rule, revision)
        return replace(value, rule=replace(value.rule, task=TaskContent("Changed source")))

    with monkeypatch.context() as patch:
        patch.setattr(SQLiteAutomationDrafts, "revision", changed)
        with pytest.raises(StorageFailure, match="invalid_daily_automation_source"):
            engine.admit("daily")
    with store.write() as unit:
        unit.automation_drafts.append("home", replace(schedule.grant.draft, revision=2))

    def missing_active(self, home, rule, revision):
        return None if revision == 1 else read(self, home, rule, revision)

    with monkeypatch.context() as patch:
        patch.setattr(SQLiteAutomationDrafts, "revision", missing_active)
        with pytest.raises(StorageFailure, match="invalid_daily_automation_source"):
            service.review("daily", 2)


@pytest.mark.parametrize("kind", ["schedule", "run"])
def test_a_canonical_record_cannot_move_to_another_installation(tmp_path, kind):
    store, _, run = source(tmp_path)
    with store.write() as unit:
        unit.scheduled_automations.admit(run)
    table = "automation_daily_schedules" if kind == "schedule" else "automation_scheduled_runs"
    with closing(sqlite3.connect(store.path, autocommit=True)) as db:
        data = json.loads(db.execute(f"SELECT document FROM {table}").fetchone()[0])
        data["grant"]["channel"] = "stable"
        db.execute(f"UPDATE {table} SET document=?", (JsonDocument.from_value(data).encoded,))
        if kind == "run":
            foreign = read_run(JsonDocument.from_value(data).encoded)
            db.execute("UPDATE automation_scheduled_runs SET trigger_key=?", (foreign.key,))
    with store.read() as unit:
        with pytest.raises(StorageFailure, match="invalid_daily_automation_record"):
            if kind == "schedule":
                unit.scheduled_automations.schedule("home", "daily")
            else:
                unit.scheduled_automations.pending("home")


def test_an_over_capacity_corrupt_queue_is_not_partly_cancelled(tmp_path):
    store, _, first = source(tmp_path)
    times = PinnedRecurrenceTime()
    with store.write() as unit:
        for offset in range(101):
            planned = times.resolve(
                NominalTime(first.planned.nominal.local + timedelta(days=offset)),
                first.planned.policy,
            )
            unit.scheduled_automations.admit(
                replace(first, planned=planned, admitted_at=planned.instant_ms)
            )
        with pytest.raises(StorageFailure, match="invalid_daily_automation_queue"):
            ScheduledCancellations(
                store, MaintenanceScope(store.installation, "home"), Mock(), Mock()
            ).pending(unit, "daily")
        assert unit.scheduled_automations.pending_count("home") == 101


@pytest.mark.parametrize("proof", ["admission", "outcome", "task"])
def test_checkpoint_rejects_an_orphaned_scheduled_proof_envelope(tmp_path, proof):
    _, engine, store, _, clock, schedule = enabled(tmp_path)
    step = due(engine, clock, schedule)
    done = engine.execute(step.trigger_key)
    with store.read() as unit:
        run = unit.scheduled_automations.run("home", step.trigger_key)
    operation = (
        step.receipt.operation_id
        if proof == "admission"
        else (done.receipt.operation_id if proof == "outcome" else run.task_operation_id)
    )
    with closing(sqlite3.connect(store.path, autocommit=True)) as db:
        db.execute("DELETE FROM receipts WHERE operation_id=?", (operation,))
        db.execute("DELETE FROM audit WHERE operation_id=?", (operation,))
        db.execute("DELETE FROM outbox WHERE event_id=?", (operation,))
        db.row_factory = sqlite3.Row
        with pytest.raises(DatabaseRejected, match="invalid_snapshot_records"):
            _verify_database(db, store, previous=False)


def test_checkpoint_rejects_a_rewritten_immutable_grant_definition(tmp_path):
    _, _, store, _, _, _ = enabled(tmp_path)
    with closing(sqlite3.connect(store.path, autocommit=True)) as db:
        data = json.loads(
            db.execute("SELECT document FROM automation_daily_schedules").fetchone()[0]
        )
        definition = json.loads(data["grant"]["rule"])
        definition["action"]["title"] = "Unapproved replacement"
        data["grant"]["rule"] = JsonDocument.from_value(definition).encoded
        db.execute(
            "UPDATE automation_daily_schedules SET document=?",
            (JsonDocument.from_value(data).encoded,),
        )
        db.row_factory = sqlite3.Row
        with pytest.raises(DatabaseRejected, match="invalid_snapshot_records"):
            _verify_database(db, store, previous=False)


def test_checkpoint_rejects_a_current_outcome_rewound_to_pending(tmp_path):
    _, engine, store, _, clock, schedule = enabled(tmp_path)
    step = due(engine, clock, schedule)
    engine.execute(step.trigger_key)
    with store.read() as unit:
        run = unit.scheduled_automations.run("home", step.trigger_key)
    rewound = replace(
        run,
        outcome=ScheduledOutcome.QUEUED,
        finished_at=None,
        task_operation_id=None,
        task_occurrence_id=None,
    )
    with closing(sqlite3.connect(store.path, autocommit=True)) as db:
        db.execute(
            "UPDATE automation_scheduled_runs SET outcome='queued',document=?",
            (run_document(rewound).encoded,),
        )
        db.row_factory = sqlite3.Row
        with pytest.raises(DatabaseRejected, match="invalid_snapshot_records"):
            _verify_database(db, store, previous=False)
