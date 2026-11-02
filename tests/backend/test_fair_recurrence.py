"""Actual fixed rules receive bounded fair turns across restart, errors and atomic stopping."""

from dataclasses import replace
from datetime import UTC, date, datetime
from threading import Event

import pytest
from test_recurrence_creation import request, setup

from domus.application.fair_recurrence import FairFixedRunner, RunLimits
from domus.application.fixed_materialization import FixedMaintenance, MaintenanceScope
from domus.domain.errors import Forbidden, IntegrationUnavailable, InvalidInput
from domus.domain.recurrence_rules import NominalDate
from domus.infrastructure.sqlite import SQLiteDatabase


class Clock:
    def now(self):
        return int(datetime(2026, 3, 28, tzinfo=UTC).timestamp() * 1000)


def configured(tmp_path, number=1, *, count=1, start=None, limits=None, timed=False):
    creation, _, store, _, ids = setup(tmp_path)
    rules = []
    for index in range(number):
        value = request(timed=timed)
        value = replace(
            value,
            pattern=replace(
                value.pattern,
                count=count,
                start=value.pattern.start if start is None else NominalDate(start),
            ),
        )
        rules.append(
            creation.create_fixed(f"configure-{index}", value).result.decode()["schedule_id"]
        )
    scope = MaintenanceScope(store.installation, "home")
    clock = Clock()
    stepper = FixedMaintenance(store, scope, creation.planner, clock, ids)
    runner = FairFixedRunner(
        store,
        scope,
        stepper,
        creation.planner.times,
        clock,
        RunLimits() if limits is None else limits,
    )
    return runner, store, rules


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_definitions", 0),
        ("max_definitions", 51),
        ("max_slots", 0),
        ("max_slots", 1001),
        ("max_periods", 0),
        ("max_periods", 64001),
        ("horizon_days", 6),
        ("horizon_days", 367),
        ("max_slots", True),
    ],
)
def test_invalid_run_limits_cannot_enter_a_runner(field, value):
    with pytest.raises(InvalidInput):
        replace(RunLimits(), **{field: value})


def test_more_than_fifty_rules_receive_turns_across_durable_restart(tmp_path):
    runner, store, rules = configured(tmp_path, 101)
    results = []
    for _ in range(3):
        result = runner.tick()
        results.append(result)
        assert len(result.selected_schedule_ids) <= 50
        reopened = SQLiteDatabase(store.path, store.installation)
        runner = replace(
            runner, transactions=reopened, stepper=replace(runner.stepper, transactions=reopened)
        )
    assert [result.created for result in results] == [50, 50, 1]
    assert set().union(*(set(result.selected_schedule_ids) for result in results)) == set(rules)
    with store.read() as unit:
        assert len(unit.tasks.occurrences("home", limit=101)) == 101
        assert unit.recurrence.frontier("home").revision >= 3
        assert (
            unit.recurrence.frontier("home").after_schedule_id
            == results[-1].selected_schedule_ids[-1]
        )


def test_actual_global_thousand_slot_limit_retains_the_next_obligation_for_another_tick(tmp_path):
    runner, store, _ = configured(tmp_path, count=1001, start=date(1970, 1, 1))
    first = runner.tick()
    assert first.status == "budget_exhausted" and first.created == 1000
    assert first.periods_scanned <= 4096
    second = runner.tick()
    assert second.status == "complete" and second.created == 1
    with store.read() as unit:
        total = 0
        after = None
        while rows := unit.tasks.occurrences("home", limit=101, after=after):
            total += len(rows)
            after = rows[-1].occurrence_id
        assert total == 1001


def test_stop_after_one_atomic_step_retains_only_that_step_and_starts_no_next_work(
    tmp_path, monkeypatch
):
    runner, store, _ = configured(tmp_path, count=3)
    stopped = Event()
    step = FixedMaintenance.step

    def stop_after(self, *args, **kwargs):
        result = step(self, *args, **kwargs)
        stopped.set()
        return result

    monkeypatch.setattr(FixedMaintenance, "step", stop_after)
    result = runner.tick(should_continue=lambda: not stopped.is_set())
    assert result.status == "stopped" and result.created == 1
    with store.read() as unit:
        assert len(unit.tasks.occurrences("home")) == 1


def test_stop_before_admission_creates_no_frontier_or_work(tmp_path):
    runner, store, _ = configured(tmp_path)
    result = runner.tick(should_continue=lambda: False)
    assert result.status == "stopped" and result.created == 0
    with store.read() as unit:
        assert unit.recurrence.frontier("home") is None
        assert unit.tasks.occurrences("home") == ()


def test_one_unavailable_rule_does_not_starve_the_other_selected_rule(tmp_path, monkeypatch):
    runner, store, rules = configured(tmp_path, 2)
    step = FixedMaintenance.step

    def fail_one(self, schedule_id, *args, **kwargs):
        if schedule_id == rules[0]:
            raise IntegrationUnavailable("timezone_source_unavailable")
        return step(self, schedule_id, *args, **kwargs)

    monkeypatch.setattr(FixedMaintenance, "step", fail_one)
    result = runner.tick()
    assert result.status == "attention" and result.attention_count == 1 and result.created == 1
    with store.read() as unit:
        assert len(unit.tasks.occurrences("home")) == 1


def test_installed_scope_is_checked_before_claim_or_any_step(tmp_path):
    runner, store, _ = configured(tmp_path)
    runner = replace(
        runner,
        scope=replace(runner.scope, installation=replace(store.installation, channel="stable")),
    )
    with pytest.raises(Forbidden):
        runner.tick()
    with store.read() as unit:
        assert unit.recurrence.frontier("home") is None
        assert unit.tasks.occurrences("home") == ()


def test_repeated_restart_after_every_first_step_cannot_starve_the_other_ninety_eight_rules(
    tmp_path, monkeypatch
):
    runner, store, rules = configured(tmp_path, 100)
    stopped = Event()
    step = FixedMaintenance.step
    observed = []

    def stop_after_first(self, schedule_id, *args, **kwargs):
        observed.append(schedule_id)
        result = step(self, schedule_id, *args, **kwargs)
        stopped.set()
        return result

    monkeypatch.setattr(FixedMaintenance, "step", stop_after_first)
    created = 0
    for _ in range(100):
        stopped.clear()
        result = runner.tick(should_continue=lambda: not stopped.is_set())
        created += result.created
        reopened = SQLiteDatabase(store.path, store.installation)
        runner = replace(
            runner, transactions=reopened, stepper=replace(runner.stepper, transactions=reopened)
        )
    assert created == 100
    assert set(observed) == set(rules) and len(observed) == len(set(observed))


def test_unavailable_rule_reports_only_a_safe_scoped_category(tmp_path, monkeypatch):
    runner, _, rules = configured(tmp_path)

    def unavailable(*args, **kwargs):
        raise IntegrationUnavailable("private fixture diagnostic")

    monkeypatch.setattr(FixedMaintenance, "step", unavailable)
    result = runner.tick()
    assert result.attention_items[0].schedule_id == rules[0]
    assert result.attention_items[0].code == "time_source_unavailable"
    assert "private" not in repr(result)
