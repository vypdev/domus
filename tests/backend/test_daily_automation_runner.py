"""The owned worker has bounded fair turns and never grants authority from a session."""

from dataclasses import replace
from unittest.mock import Mock

import pytest
from test_daily_automation_control import reviewed, setup
from test_daily_automation_execution import due, enabled
from test_household_commands import fixture as empty_household

from domus.application.automation_scheduled_control import ReviewedDailyRequest
from domus.application.automation_scheduled_runner import DailyAutomationRunner
from domus.application.fixed_materialization import MaintenanceScope
from domus.composition.automation import automation_worker
from domus.domain.errors import Forbidden, IntegrationUnavailable, InvalidInput


def test_newly_admitted_work_is_processed_on_the_next_bounded_turn(tmp_path):
    _, engine, store, _, clock, schedule = enabled(tmp_path)
    clock.now.return_value = schedule.next_time.instant_ms
    runner = DailyAutomationRunner(engine, limit=1)
    first = runner.tick(lambda: True)
    assert [step.status for step in first.steps] == ["admitted"]
    second = runner.tick(lambda: True)
    assert [step.status for step in second.steps] == ["created", "future"]
    with store.read() as unit:
        assert len(unit.tasks.definitions("home")) == 1


def test_one_rule_with_unavailable_policy_does_not_starve_the_other_rule(tmp_path):
    service, engine, store, _, _, _ = enabled(tmp_path)
    with store.write() as unit:
        draft = unit.automation_drafts.latest("home", "daily")
        unit.automation_drafts.append("home", replace(draft, rule_id="second"))
    review = service.review("second", 1)
    service.enable(
        "second-enable", ReviewedDailyRequest("second", 1, 0, 0, review.proposed_times[0])
    )
    wrapped = Mock(wraps=engine)
    wrapped.scope = engine.scope

    def admit(rule_id, **kwargs):
        if rule_id == "daily":
            raise IntegrationUnavailable("private-source-error")
        return engine.admit(rule_id, **kwargs)

    wrapped.admit.side_effect = admit
    runner = DailyAutomationRunner(wrapped, limit=1)
    first = runner.tick(lambda: True)
    second = runner.tick(lambda: True)
    third = runner.tick(lambda: True)
    assert [(step.rule_id, step.status) for step in first.steps] == [("daily", "unavailable")]
    assert [(step.rule_id, step.status) for step in second.steps] == [("second", "future")]
    assert [(step.rule_id, step.status) for step in third.steps] == [("daily", "unavailable")]
    assert "private-source-error" not in repr(first)


def test_lost_rule_grant_is_cancelled_without_a_global_scope_failure(tmp_path):
    _, engine, store, _, clock, schedule = enabled(tmp_path)
    step = due(engine, clock, schedule)
    with store.write() as unit:
        control = unit.automation_controls.get("home", "daily")
        unit.automation_controls.save(
            "home", replace(control, control_revision=2, enabled=False), 1
        )
    turn = DailyAutomationRunner(engine).tick(lambda: True)
    assert [(item.trigger_key, item.status) for item in turn.steps] == [
        (step.trigger_key, "cancelled")
    ]


def test_stop_before_read_and_between_pending_work_preserves_the_unstarted_queue(tmp_path):
    _, engine, _, _, clock, schedule = enabled(tmp_path)
    due(engine, clock, schedule)
    runner = DailyAutomationRunner(engine)
    assert runner.tick(lambda: False).status == "stopped"
    assert runner.tick(Mock(side_effect=[True, False])).status == "stopped"
    assert runner.tick(Mock(side_effect=[True, True, True, True, False])).status == "stopped"


def test_global_scope_denial_is_not_hidden_as_a_single_rules_unavailability(tmp_path):
    _, engine, store, _, _, _ = enabled(tmp_path)
    foreign = replace(
        engine, scope=MaintenanceScope(replace(store.installation, channel="stable"), "home")
    )
    with pytest.raises(Forbidden, match="maintenance_scope_denied"):
        DailyAutomationRunner(foreign).tick(lambda: True)
    wrapped = Mock(wraps=engine)
    wrapped.scope = engine.scope
    wrapped.admit.side_effect = Forbidden("maintenance_scope_denied")
    with pytest.raises(Forbidden, match="maintenance_scope_denied"):
        DailyAutomationRunner(wrapped).tick(lambda: True)


@pytest.mark.parametrize("limit", [True, 0, 26])
def test_invalid_turn_limits_never_start_unbounded_work(tmp_path, limit):
    _, engine, _, _, _, _ = enabled(tmp_path)
    with pytest.raises(InvalidInput, match="invalid_daily_automation_limits"):
        DailyAutomationRunner(engine, limit)


def test_factory_is_inert_until_start_and_distinguishes_an_unconfigured_household(tmp_path):
    _, store, _, _, _ = empty_household(tmp_path / "empty.sqlite3")
    worker = automation_worker(store, store.installation)
    assert not worker.is_running and worker.last_run is None
    assert worker._tick(lambda: False).status == "stopped"
    assert worker._tick(lambda: True).status == "unconfigured"
    worker.close()


def test_factory_retains_one_runner_after_setup_and_stops_on_installation_mismatch(tmp_path):
    service, store, _, _ = setup(tmp_path)
    service.enable("enable", reviewed(service))
    worker = automation_worker(store, store.installation)
    try:
        assert worker._tick(lambda: True).status == "processed"
        assert worker._tick(lambda: True).status == "processed"
    finally:
        worker.close()
    foreign = automation_worker(store, replace(store.installation, channel="stable"))
    try:
        with pytest.raises(Forbidden, match="maintenance_scope_denied"):
            foreign._tick(lambda: True)
    finally:
        foreign.close()


def test_a_transiently_unavailable_old_run_does_not_starve_later_admitted_work(tmp_path):
    _, engine, store, _, clock, schedule = enabled(tmp_path)
    clock.now.return_value = schedule.next_time.instant_ms + 86_400_001
    assert engine.admit("daily").status == "admitted"
    assert engine.admit("daily").status == "admitted"
    with store.read() as unit:
        ordered = unit.scheduled_automations.pending("home")
        blocked_key, later_key = ordered[0].key, ordered[1].key
    wrapped = Mock(wraps=engine)
    wrapped.scope = engine.scope

    def execute(key, **kwargs):
        if key == blocked_key:
            raise IntegrationUnavailable("temporary-condition-outage")
        return engine.execute(key, **kwargs)

    wrapped.execute.side_effect = execute
    runner = DailyAutomationRunner(wrapped, limit=1)
    assert runner.tick(lambda: True).steps[0].status == "unavailable"
    assert runner.tick(lambda: True).steps[0].trigger_key == later_key
    assert runner.tick(lambda: True).steps[0].status == "unavailable"
    with store.read() as unit:
        assert len(unit.tasks.definitions("home")) == 1
        assert [run.key for run in unit.scheduled_automations.pending("home")] == [blocked_key]
