"""Real daily admissions and effects survive writer races, crashes and process restarts."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, contextmanager
from dataclasses import replace
from threading import Event
from unittest.mock import Mock

import pytest
from test_daily_automation_control import reviewed, setup

from domus.application.automation_preview import evaluate_scheduled_rule
from domus.application.automation_scheduled_authority import (
    ADMIT_SCHEDULED_AUTOMATION,
    RUN_SCHEDULED_AUTOMATION,
)
from domus.application.automation_scheduled_control import DailyControlRequest, ReviewedDailyRequest
from domus.application.automation_scheduled_execution import ScheduledAutomationExecution
from domus.application.inventory import InventoryCommands
from domus.domain.automation import (
    AutomationRule,
    ConditionGroup,
    DailyTrigger,
    NegatedCondition,
    StockCondition,
)
from domus.domain.automation_scheduling import ScheduledOutcome
from domus.domain.errors import Conflict, Forbidden, InvalidInput, NotFound, StorageFailure
from domus.domain.identity import MemberStatus
from domus.domain.inventory import BaseUnit
from domus.domain.storage import CommandKey
from domus.domain.task_material_values import MaterialQuantity
from domus.domain.task_values import TaskContent
from domus.infrastructure.sqlite import SQLiteDatabase, SQLiteOutbox
from domus.infrastructure.sqlite_snapshots import _verify_database


def enabled(tmp_path):
    service, store, actor, clock = setup(tmp_path)
    service.enable("enable", reviewed(service))
    engine = ScheduledAutomationExecution(
        store, service.scope, clock, service.identifiers, service.planner, clock.now()
    )
    with store.read() as unit:
        schedule = unit.scheduled_automations.schedule("home", "daily")
    return service, engine, store, actor, clock, schedule


def due(engine, clock, schedule):
    clock.now.return_value = schedule.next_time.instant_ms + 1000
    step = engine.admit("daily")
    assert step.status == "admitted"
    return step


def test_manual_rules_cannot_enter_the_scheduled_condition_path_or_probe_inventory(tmp_path):
    _, _, store, _, _, _ = enabled(tmp_path)
    manual = AutomationRule(
        1, "manual", StockCondition("unavailable-product"), TaskContent("Manual task")
    )
    with store.read() as unit:
        with pytest.raises(InvalidInput, match="automation_requires_daily_trigger"):
            evaluate_scheduled_rule(unit, "home", manual)
        assert unit.tasks.definitions("home") == ()


def test_due_trigger_admits_durable_work_before_one_ordinary_task_command(tmp_path):
    _, engine, store, _, clock, schedule = enabled(tmp_path)
    assert engine.admit("daily").status == "future"
    step = due(engine, clock, schedule)
    with store.read() as unit:
        queued = unit.scheduled_automations.run("home", step.trigger_key)
        current = unit.scheduled_automations.schedule("home", "daily")
        assert queued.outcome is ScheduledOutcome.QUEUED
        assert queued.planned == schedule.next_time
        assert current.next_time.instant_ms > schedule.next_time.instant_ms
        assert current.last_nominal == schedule.next_time.nominal.local.date()
        assert unit.tasks.definitions("home") == ()
    result = engine.execute(step.trigger_key)
    assert result.status == "created"
    assert engine.execute(step.trigger_key).status == "created"
    assert engine.admit("daily").status == "future"
    with store.read() as unit:
        finished = unit.scheduled_automations.run("home", step.trigger_key)
        task = unit.tasks.occurrence("home", finished.task_occurrence_id)
        task_key = CommandKey("home", finished.grant.principal, "task.create", finished.key)
        assert task.definition_snapshot.content == schedule.grant.draft.rule.task
        assert unit.receipts.get(task_key).operation_id == finished.task_operation_id
        assert len(unit.tasks.definitions("home")) == 1
        assert all(
            event.event_type not in (ADMIT_SCHEDULED_AUTOMATION, RUN_SCHEDULED_AUTOMATION)
            for event in unit.outbox.pending()
        )
    with closing(sqlite3.connect(store.path)) as db:
        db.row_factory = sqlite3.Row
        assert _verify_database(db, store, previous=False) == 38


def test_only_offline_unadmitted_times_are_skipped_and_suppression_survives_restart(tmp_path):
    _, engine, store, _, clock, schedule = enabled(tmp_path)
    clock.now.return_value = schedule.next_time.instant_ms + 2 * 86_400_000 + 1000
    restarted = replace(engine, startup_ms=clock.now())
    assert restarted.admit("daily").status == "future"
    with store.read() as unit:
        advanced = unit.scheduled_automations.schedule("home", "daily")
        assert advanced.next_time.instant_ms > clock.now()
        assert advanced.suppression.first == schedule.next_time
        assert advanced.suppression.through_ms == clock.now()
        assert unit.scheduled_automations.pending("home") == ()
        assert unit.tasks.definitions("home") == ()
    # An older worker cannot lower the persisted startup fence or revive the gap.
    assert engine.admit("daily").status == "future"
    with store.read() as unit:
        assert unit.scheduled_automations.schedule("home", "daily") == advanced


def test_an_ordinary_live_worker_delay_keeps_the_eligible_time(tmp_path):
    _, engine, store, _, clock, schedule = enabled(tmp_path)
    clock.now.return_value = schedule.next_time.instant_ms + 2 * 86_400_000
    admitted = engine.admit("daily")
    assert admitted.status == "admitted"
    with store.read() as unit:
        queued = unit.scheduled_automations.run("home", admitted.trigger_key)
        assert queued.planned == schedule.next_time
        assert unit.scheduled_automations.schedule("home", "daily").suppression is None


def test_queued_work_survives_a_real_database_reopen_without_becoming_startup_suppression(tmp_path):
    _, engine, store, _, clock, schedule = enabled(tmp_path)
    step = due(engine, clock, schedule)
    reopened = SQLiteDatabase(store.path, store.installation)
    restarted = replace(engine, transactions=reopened, startup_ms=clock.now())
    assert restarted.execute(step.trigger_key).status == "created"
    assert restarted.admit("daily").status == "future"
    with reopened.read() as unit:
        assert len(unit.tasks.definitions("home")) == 1
        assert (
            unit.scheduled_automations.run("home", step.trigger_key).planned == schedule.next_time
        )


def test_concurrent_workers_admit_and_execute_one_trigger_once(tmp_path):
    _, engine, store, _, clock, schedule = enabled(tmp_path)
    clock.now.return_value = schedule.next_time.instant_ms
    other = replace(engine, transactions=SQLiteDatabase(store.path, store.installation))
    with ThreadPoolExecutor(max_workers=2) as pool:
        steps = list(pool.map(lambda worker: worker.admit("daily"), (engine, other)))
    assert sorted(step.status for step in steps) == ["admitted", "future"]
    key = next(step.trigger_key for step in steps if step.status == "admitted")
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda worker: worker.execute(key).status, (engine, other)))
    assert outcomes == ["created", "created"]
    with store.read() as unit:
        assert len(unit.tasks.definitions("home")) == 1
        assert len(unit.scheduled_automations.history("home", "daily")) == 1


def competing_writers(monkeypatch, leader, follower, first, second):
    """Force each real SQLite serialization order while both contenders are active."""
    entered, contending = Event(), Event()
    original = SQLiteDatabase.write

    @contextmanager
    def gated(store):
        if store is follower:
            contending.set()
        with original(store) as unit:
            if store is leader:
                entered.set()
                assert contending.wait(3)
            yield unit

    with monkeypatch.context() as patch, ThreadPoolExecutor(max_workers=2) as pool:
        patch.setattr(SQLiteDatabase, "write", gated)
        leading = pool.submit(first)
        assert entered.wait(3)
        following = pool.submit(second)
        return leading.result(), following.result()


@pytest.mark.parametrize("startup_first", [False, True])
def test_startup_suppression_racing_live_admission_has_one_durable_disposition(
    tmp_path, monkeypatch, startup_first
):
    _, engine, store, _, clock, schedule = enabled(tmp_path)
    clock.now.return_value = schedule.next_time.instant_ms + 1000
    restarted = replace(
        engine, transactions=SQLiteDatabase(store.path, store.installation), startup_ms=clock.now()
    )
    first, second = (restarted, engine) if startup_first else (engine, restarted)
    outcomes = competing_writers(
        monkeypatch,
        first.transactions,
        second.transactions,
        lambda: first.admit("daily"),
        lambda: second.admit("daily"),
    )
    assert [item.status for item in outcomes] == (
        ["future", "future"] if startup_first else ["admitted", "future"]
    )
    with store.read() as unit:
        current = unit.scheduled_automations.schedule("home", "daily")
        queued = unit.scheduled_automations.pending("home")
        assert len(queued) == int(not startup_first)
        assert current.startup_cutoff_ms == clock.now()
        assert current.next_time.instant_ms > clock.now()
        assert (current.suppression is not None) is startup_first
    if queued:
        assert engine.execute(queued[0].key).status == "created"
    assert engine.admit("daily").status == restarted.admit("daily").status == "future"
    with store.read() as unit:
        assert len(unit.tasks.definitions("home")) == int(not startup_first)


@pytest.mark.parametrize("disable_first", [False, True])
def test_disable_racing_admission_fences_new_work_or_requires_a_current_revision_review(
    tmp_path, monkeypatch, disable_first
):
    service, engine, store, _, clock, schedule = enabled(tmp_path)
    service = replace(service, transactions=SQLiteDatabase(store.path, store.installation))
    clock.now.return_value = schedule.next_time.instant_ms + 1000
    request = DailyControlRequest("daily", 1, 1, schedule.revision)

    def admit():
        try:
            return engine.admit("daily").status
        except Forbidden:
            return "disabled"

    def disable():
        try:
            service.disable("disable", request)
            return "disabled"
        except Conflict:
            return "review_required"

    first, second = (disable, admit) if disable_first else (admit, disable)
    leader, follower = (
        (service.transactions, store) if disable_first else (store, service.transactions)
    )
    outcomes = competing_writers(monkeypatch, leader, follower, first, second)
    assert outcomes == (
        ("disabled", "disabled") if disable_first else ("admitted", "review_required")
    )
    if not disable_first:
        current = service.review("daily", 1)
        service.disable(
            "disable",
            DailyControlRequest(
                "daily", 1, current.control.control_revision, current.schedule.revision
            ),
        )
    with pytest.raises(Forbidden):
        engine.admit("daily")
    with store.read() as unit:
        assert not unit.automation_controls.get("home", "daily").enabled
        assert unit.scheduled_automations.pending("home") == ()
        assert unit.tasks.definitions("home") == ()
        history = unit.scheduled_automations.history("home", "daily")
        assert len(history) == int(not disable_first)
        assert all(run.outcome is ScheduledOutcome.CANCELLED for run in history)


def test_failure_after_task_facts_rolls_back_both_outcomes_and_identical_retry_creates_once(
    tmp_path, monkeypatch
):
    _, engine, store, _, clock, schedule = enabled(tmp_path)
    step = due(engine, clock, schedule)
    append = SQLiteOutbox.append

    def fail_outer(self, event):
        if event.event_type == RUN_SCHEDULED_AUTOMATION:
            raise StorageFailure("outer_receipt_failure")
        return append(self, event)

    with monkeypatch.context() as patch:
        patch.setattr(SQLiteOutbox, "append", fail_outer)
        with pytest.raises(StorageFailure, match="outer_receipt_failure"):
            engine.execute(step.trigger_key)
    with store.read() as unit:
        assert unit.tasks.definitions("home") == ()
        assert (
            unit.scheduled_automations.run("home", step.trigger_key).outcome
            is ScheduledOutcome.QUEUED
        )
    assert engine.execute(step.trigger_key).status == "created"
    with store.read() as unit:
        assert len(unit.tasks.definitions("home")) == 1


def test_admission_receipt_failure_rolls_back_the_queue_and_cursor_together(tmp_path, monkeypatch):
    _, engine, store, _, clock, schedule = enabled(tmp_path)
    clock.now.return_value = schedule.next_time.instant_ms
    with monkeypatch.context() as patch:
        patch.setattr(
            SQLiteOutbox, "append", Mock(side_effect=StorageFailure("admit_receipt_failure"))
        )
        with pytest.raises(StorageFailure, match="admit_receipt_failure"):
            engine.admit("daily")
    with store.read() as unit:
        assert unit.scheduled_automations.schedule("home", "daily") == schedule
        assert unit.scheduled_automations.pending("home") == ()
    assert engine.admit("daily").status == "admitted"


def test_disable_serializes_with_the_atomic_task_effect_and_retains_actual_outcome(tmp_path):
    service, engine, store, _, clock, schedule = enabled(tmp_path)
    step = due(engine, clock, schedule)
    with store.read() as unit:
        current = unit.scheduled_automations.schedule("home", "daily")
    request = DailyControlRequest("daily", 1, 1, current.revision)
    with ThreadPoolExecutor(max_workers=2) as pool:
        effect = pool.submit(engine.execute, step.trigger_key)
        disable = pool.submit(service.disable, "disable", request)
        outcome, disabled = effect.result(), disable.result()
    assert not disabled.result.decode()["enabled"]
    with store.read() as unit:
        actual = unit.scheduled_automations.run("home", step.trigger_key)
        assert actual.outcome.value == outcome.status
        assert len(unit.tasks.definitions("home")) == int(
            actual.outcome is ScheduledOutcome.CREATED
        )
        assert unit.scheduled_automations.pending("home") == ()
    with pytest.raises(Forbidden):
        engine.admit("daily")


def test_lost_current_grant_cancels_a_queue_item_before_an_effect(tmp_path):
    _, engine, store, _, clock, schedule = enabled(tmp_path)
    step = due(engine, clock, schedule)
    with store.write() as unit:
        current = unit.automation_controls.get("home", "daily")
        unit.automation_controls.save(
            "home", replace(current, control_revision=2, enabled=False), 1
        )
    assert engine.execute(step.trigger_key).status == "cancelled"
    with store.read() as unit:
        assert unit.tasks.definitions("home") == ()


@pytest.mark.parametrize("matched", [False, True])
def test_daily_grouped_conditions_use_real_stock_semantics_without_a_manual_trigger(
    tmp_path, matched
):
    service, store, actor, clock = setup(tmp_path)
    inventory = InventoryCommands(store, actor, clock, service.identifiers)
    product = inventory.register("soap", "Soap", BaseUnit.PIECE).result.decode()["product_id"]
    inventory.configure_replenishment(
        "minimum", product, MaterialQuantity("1"), MaterialQuantity("2"), 0
    )
    condition = StockCondition(product)
    if not matched:
        condition = NegatedCondition(condition)
    tree = ConditionGroup("all", (condition, ConditionGroup("any", (condition,))))
    with store.write() as unit:
        original = unit.automation_drafts.latest("home", "daily")
        unit.automation_drafts.append(
            "home", replace(original, revision=2, rule=replace(original.rule, condition=tree))
        )
    review = service.review("daily", 2)
    service.enable("enable", ReviewedDailyRequest("daily", 2, 0, 0, review.proposed_times[0]))
    saved = service.review("daily", 2).schedule
    engine = ScheduledAutomationExecution(
        store, service.scope, clock, service.identifiers, service.planner, clock.now()
    )
    step = due(engine, clock, saved)
    assert engine.execute(step.trigger_key).status == ("created" if matched else "no_task")
    with store.read() as unit:
        assert len(unit.tasks.definitions("home")) == int(matched)


def test_stopping_before_the_writer_or_inside_it_has_no_new_effect(tmp_path):
    _, engine, store, _, clock, schedule = enabled(tmp_path)
    assert engine.admit("daily", should_continue=lambda: False).status == "stopped"
    assert (
        engine.admit("daily", should_continue=Mock(side_effect=[True, False])).status == "stopped"
    )
    step = due(engine, clock, schedule)
    assert engine.execute(step.trigger_key, should_continue=lambda: False).status == "stopped"
    assert (
        engine.execute(step.trigger_key, should_continue=Mock(side_effect=[True, False])).status
        == "stopped"
    )
    with store.read() as unit:
        assert unit.tasks.definitions("home") == ()


def test_unknown_scoped_sources_and_invalid_startup_do_not_create_work(tmp_path):
    _, engine, _, _, _, _ = enabled(tmp_path)
    with pytest.raises(NotFound, match="daily_automation_schedule_missing"):
        engine.admit("missing")
    with pytest.raises(NotFound, match="daily_automation_run_missing"):
        engine.execute("missing")
    for value in (True, -1, 253_402_300_800_000):
        with pytest.raises(InvalidInput):
            replace(engine, startup_ms=value)


@pytest.mark.parametrize("scope", ["rule", "household"])
def test_real_durable_backlog_stops_at_rule_and_household_capacity(tmp_path, scope):
    service, engine, store, _, clock, schedule = enabled(tmp_path)
    rules = ["daily"]
    if scope == "household":
        rules = ["other-" + str(index) for index in range(10)]
        for rule_id in rules:
            with store.write() as unit:
                unit.automation_drafts.append(
                    "home", replace(schedule.grant.draft, rule_id=rule_id)
                )
            review = service.review(rule_id, 1)
            service.enable(
                "enable-" + rule_id,
                ReviewedDailyRequest(rule_id, 1, 0, 0, review.proposed_times[0]),
            )
    # This is ordinary delay in a still-running process, not a restart. Every
    # queued item below is produced by the actual authorized admission command.
    clock.now.return_value = schedule.next_time.instant_ms + 101 * 86_400_000
    for _ in range(100):
        for rule_id in rules:
            assert engine.admit(rule_id).status == "admitted"
    assert engine.admit("daily").status == "queue_full"
    with store.read() as unit:
        records = unit.scheduled_automations
        assert records.pending_count("home") == 100 * len(rules)
        assert records.pending_count("home", rule_id=rules[0], limit=100) == 100
        assert records.pending_count("other") == 0
        assert unit.tasks.definitions("home") == ()
    with closing(sqlite3.connect(store.path)) as db:
        db.row_factory = sqlite3.Row
        assert _verify_database(db, store, previous=False) == 38


def test_a_stale_persisted_cursor_does_not_reemit_an_already_known_trigger(tmp_path):
    _, engine, store, _, clock, schedule = enabled(tmp_path)
    step = due(engine, clock, schedule)
    engine.execute(step.trigger_key)
    with store.write() as unit:
        latest = unit.scheduled_automations.schedule("home", "daily")
        unit.scheduled_automations.save_schedule(
            replace(
                latest,
                next_time=schedule.next_time,
                last_nominal=None,
                revision=latest.revision + 1,
            ),
            latest.revision,
        )
    assert engine.admit("daily").status == "retained"
    with store.read() as unit:
        assert len(unit.tasks.definitions("home")) == 1
        assert len(unit.scheduled_automations.history("home", "daily")) == 1


@pytest.mark.parametrize("boundary", ["depth", "nodes"])
def test_maximum_supported_rule_still_enables_admits_executes_and_survives_checkpoint(
    tmp_path, boundary
):
    service, store, actor, clock = setup(tmp_path)
    inventory = InventoryCommands(store, actor, clock, service.identifiers)
    product = inventory.register("tea", "Tea", BaseUnit.PIECE).result.decode()["product_id"]
    inventory.configure_replenishment(
        "minimum", product, MaterialQuantity("1"), MaterialQuantity("2"), 0
    )
    condition = StockCondition(product)
    if boundary == "depth":
        for _ in range(7):
            condition = ConditionGroup("all", (condition,))
    else:
        condition = ConditionGroup("all", (condition,) * 61)
    with store.write() as unit:
        draft = unit.automation_drafts.latest("home", "daily")
        unit.automation_drafts.append(
            "home", replace(draft, revision=2, rule=replace(draft.rule, condition=condition))
        )
    view = service.review("daily", 2)
    service.enable("enable", ReviewedDailyRequest("daily", 2, 0, 0, view.proposed_times[0]))
    saved = service.review("daily", 2).schedule
    engine = ScheduledAutomationExecution(
        store, service.scope, clock, service.identifiers, service.planner, clock.now()
    )
    step = due(engine, clock, saved)
    assert engine.execute(step.trigger_key).status == "created"
    with closing(sqlite3.connect(store.path)) as db:
        db.row_factory = sqlite3.Row
        assert _verify_database(db, store, previous=False) == 38


def test_rule_owned_execution_continues_after_the_activator_leaves_without_human_proof(tmp_path):
    _, engine, store, actor, clock, schedule = enabled(tmp_path)
    with store.write() as unit:
        member = unit.members.by_user("home", actor.human.ha_user_id)
        unit.members.save(
            replace(member, revision=member.revision + 1, status=MemberStatus.SUSPENDED),
            member.revision,
        )
    calls = actor.calls
    actor.error = AssertionError("A rule worker must not request a human session")
    step = due(engine, clock, schedule)
    assert engine.execute(step.trigger_key).status == "created"
    assert actor.calls == calls
    with store.read() as unit:
        assert unit.scheduled_automations.run("home", step.trigger_key).grant == schedule.grant
        assert len(unit.tasks.definitions("home")) == 1


def test_policy_adoption_keeps_an_admitted_runs_original_timing_and_effect(tmp_path):
    service, engine, store, _, clock, schedule = enabled(tmp_path)
    step = due(engine, clock, schedule)
    with store.write() as unit:
        home = unit.households.current()
        unit.households.save(
            replace(home, time_zone="Europe/Madrid", revision=home.revision + 1), home.revision
        )
    view = service.review("daily", 1)
    assert view.policy_changed
    service.adopt(
        "adopt",
        ReviewedDailyRequest(
            "daily",
            1,
            view.control.control_revision,
            view.schedule.revision,
            view.proposed_times[0],
        ),
    )
    assert engine.execute(step.trigger_key).status == "created"
    with store.read() as unit:
        actual = unit.scheduled_automations.run("home", step.trigger_key)
        current = unit.scheduled_automations.schedule("home", "daily")
        assert actual.planned == schedule.next_time
        assert actual.control_revision == 1 and current.control_revision == 2
        assert actual.planned.policy.zone == "UTC" and current.policy.zone == "Europe/Madrid"
        assert actual.grant == current.grant


def test_zone_adoption_does_not_revive_a_nominal_date_suppressed_at_startup(tmp_path):
    service, store, _, clock = setup(tmp_path)
    with store.write() as unit:
        home = unit.households.current()
        unit.households.save(
            replace(home, time_zone="Europe/Madrid", revision=home.revision + 1), home.revision
        )
    service.enable("enable", reviewed(service))
    saved = service.review("daily", 1).schedule
    clock.now.return_value = saved.next_time.instant_ms + 3_600_000
    engine = ScheduledAutomationExecution(
        store, service.scope, clock, service.identifiers, service.planner, clock.now()
    )
    assert engine.admit("daily").status == "future"
    with store.read() as unit:
        skipped = unit.scheduled_automations.schedule("home", "daily")
        assert skipped.last_nominal == saved.next_time.nominal.local.date()
    with store.write() as unit:
        home = unit.households.current()
        unit.households.save(
            replace(home, time_zone="America/New_York", revision=home.revision + 1), home.revision
        )
    view = service.review("daily", 1)
    assert view.proposed_times[0].nominal.local.date() > skipped.last_nominal
    service.adopt(
        "adopt",
        ReviewedDailyRequest(
            "daily",
            1,
            view.control.control_revision,
            view.schedule.revision,
            view.proposed_times[0],
        ),
    )
    current = service.review("daily", 1).schedule
    assert current.next_time.nominal.local.date() > saved.next_time.nominal.local.date()
    with store.read() as unit:
        assert unit.tasks.definitions("home") == ()


def test_date_line_duplicate_keeps_its_nominal_frontier_after_policy_adoption(tmp_path):
    from test_daily_automation_planning import instant

    service, store, _, clock = setup(tmp_path)
    clock.now.return_value = instant("2011-12-29T13:00:00Z")
    with store.write() as unit:
        home = unit.households.current()
        unit.households.save(
            replace(home, time_zone="Pacific/Apia", revision=home.revision + 1), home.revision
        )
        draft = unit.automation_drafts.latest("home", "daily")
        unit.automation_drafts.append(
            "home",
            replace(draft, revision=2, rule=replace(draft.rule, trigger=DailyTrigger("00:00"))),
        )
    view = service.review("daily", 2)
    service.enable("enable", ReviewedDailyRequest("daily", 2, 0, 0, view.proposed_times[0]))
    saved = service.review("daily", 2).schedule
    engine = ScheduledAutomationExecution(
        store, service.scope, clock, service.identifiers, service.planner, clock.now()
    )
    step = due(engine, clock, saved)
    with store.read() as unit:
        progressed = unit.scheduled_automations.schedule("home", "daily")
        assert progressed.last_nominal.isoformat() == "2011-12-31"
    with store.write() as unit:
        home = unit.households.current()
        unit.households.save(
            replace(home, time_zone="UTC", revision=home.revision + 1), home.revision
        )
    proposed = service.review("daily", 2)
    assert proposed.proposed_times[0].nominal.local.date().isoformat() == "2012-01-01"
    service.adopt(
        "adopt",
        ReviewedDailyRequest(
            "daily",
            2,
            proposed.control.control_revision,
            proposed.schedule.revision,
            proposed.proposed_times[0],
        ),
    )
    assert engine.execute(step.trigger_key).status == "created"
