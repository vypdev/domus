"""Run observations preserve scope, actual work and bounded recovery under failure and stopping."""

from dataclasses import replace
from datetime import UTC, date, datetime
from threading import Event

import pytest
from test_fair_recurrence import configured

from domus.application.fair_recurrence import RunLimits
from domus.application.fixed_materialization import FixedMaintenance
from domus.domain.errors import Forbidden, InvalidInput


def test_unconfigured_and_configured_without_rules_do_not_create_admission_metadata(tmp_path):
    from test_atomic_commands import store_at

    runner, store, _ = configured(tmp_path, 0)
    assert runner.tick().status == "complete"
    with store.read() as unit:
        assert unit.recurrence.frontier("home") is None
    empty = store_at(tmp_path / "empty.sqlite3")
    assert replace(runner, transactions=empty).tick().status == "unconfigured"
    with empty.read() as unit:
        assert unit.recurrence.frontier("home") is None


def test_a_miswired_step_scope_is_fatal_instead_of_an_unavailable_rule(tmp_path):
    runner, store, _ = configured(tmp_path)
    foreign = replace(
        runner.stepper.scope, installation=replace(store.installation, channel="stable")
    )
    runner = replace(runner, stepper=replace(runner.stepper, scope=foreign))
    with pytest.raises(Forbidden):
        runner.tick()
    with store.read() as unit:
        assert unit.tasks.occurrences("home") == ()


def test_global_period_budget_counts_empty_scan_work_and_keeps_its_durable_continuation(tmp_path):
    runner, store, rules = configured(
        tmp_path, count=3, start=date(1970, 1, 1), limits=RunLimits(max_periods=2)
    )
    first = runner.tick()
    assert first.status == "budget_exhausted" and first.created == 1 and first.periods_scanned == 2
    with store.read() as unit:
        progress = unit.recurrence.progress("home", rules[0])
        assert progress.cursor.period_index == 1 and progress.cursor.nominal_count == 1
        assert len(unit.tasks.occurrences("home")) == 1
    second = runner.tick()
    assert second.created == 1 and second.periods_scanned == 2


def test_future_rule_scan_is_complete_for_the_requested_horizon_without_fake_current_work(tmp_path):
    runner, store, _ = configured(tmp_path, start=date(2027, 1, 1))
    result = runner.tick()
    assert result.status == "complete" and result.created == 0 and result.periods_scanned == 0
    with store.read() as unit:
        assert unit.tasks.occurrences("home") == ()


def test_timed_horizon_materializes_the_actual_gap_resolved_deadline(tmp_path):
    runner, store, _ = configured(tmp_path, timed=True)
    assert runner.tick().created == 1
    with store.read() as unit:
        work = unit.tasks.occurrences("home")[0]
        assert work.due_at == int(datetime(2026, 3, 29, 1, tzinfo=UTC).timestamp() * 1000)


def test_current_original_slot_replay_is_charged_to_work_budget_without_duplicate_effect(tmp_path):
    from test_fixed_materialization import rewind

    runner, store, rules = configured(tmp_path)
    assert runner.tick().created == 1
    rewind(store, rules[0])
    result = runner.tick()
    assert result.replayed == 1 and result.created == 0
    with store.read() as unit:
        assert len(unit.tasks.occurrences("home")) == 1


def test_global_tick_reconciles_actual_restored_absence_without_new_tasks(tmp_path):
    from test_activation_compatibility import identity_at
    from test_sqlite_snapshots import Clock as SnapshotClock

    from domus.infrastructure.owned_storage import open_storage
    from domus.infrastructure.sqlite_activation import SQLiteActivation
    from domus.infrastructure.sqlite_restoration import SQLiteRestorations
    from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots

    root = tmp_path / "source"
    root.mkdir(mode=0o700)
    runner, store, _ = configured(root)
    identity_at(root, store.installation)
    archive = tmp_path / "snapshot"
    prepared = tmp_path / "prepared"
    checkpoint = SQLiteSnapshots(store, archive, store.installation, SnapshotClock()).create(
        "before-run"
    )
    assert runner.tick().created == 1
    SQLiteRestorations(
        store, archive, prepared, store.installation, SnapshotClock(), checkpoint
    ).prepare("restore-run")
    assert (
        SQLiteActivation(root, store.installation, SnapshotClock(), prepared).activate().state
        == "active"
    )
    storage = open_storage(root, "edge")
    try:
        service = replace(
            runner,
            transactions=storage.database,
            stepper=replace(runner.stepper, transactions=storage.database),
        )
        result = service.tick()
        assert result.created == 0 and result.historical_absent == 1
        with storage.database.read() as unit:
            assert unit.tasks.occurrences("home") == ()
    finally:
        storage.close()


def test_stop_during_horizon_lookup_never_calls_the_next_step(tmp_path, monkeypatch):
    from domus.infrastructure.recurrence_time import PinnedRecurrenceTime

    runner, store, _ = configured(tmp_path)
    stopped = Event()
    after = PinnedRecurrenceTime.after_local_days

    def cancel(self, *args, **kwargs):
        result = after(self, *args, **kwargs)
        stopped.set()
        return result

    def forbidden_step(*args, **kwargs):
        pytest.fail("A new step started after cancellation")

    monkeypatch.setattr(PinnedRecurrenceTime, "after_local_days", cancel)
    monkeypatch.setattr(FixedMaintenance, "step", forbidden_step)
    assert runner.tick(should_continue=lambda: not stopped.is_set()).status == "stopped"
    with store.read() as unit:
        assert unit.tasks.occurrences("home") == ()


def test_stop_during_step_planning_is_a_stopped_run_without_a_business_write(tmp_path, monkeypatch):
    from domus.application.fixed_recurrence import FixedRecurrencePlanner

    runner, store, _ = configured(tmp_path)
    stopped = Event()
    expand = FixedRecurrencePlanner.expand

    def cancel(self, *args, **kwargs):
        result = expand(self, *args, **kwargs)
        stopped.set()
        return result

    monkeypatch.setattr(FixedRecurrencePlanner, "expand", cancel)
    result = runner.tick(should_continue=lambda: not stopped.is_set())
    assert result.status == "stopped" and result.created == 0
    with store.read() as unit:
        assert unit.tasks.occurrences("home") == ()


def test_an_unknown_postcommit_step_outcome_reports_uncertainty_and_retains_real_work(
    tmp_path, monkeypatch
):
    runner, store, _ = configured(tmp_path)
    step = FixedMaintenance.step

    def unknown(self, *args, **kwargs):
        return replace(step(self, *args, **kwargs), status="unknown fixture state")

    monkeypatch.setattr(FixedMaintenance, "step", unknown)
    result = runner.tick()
    assert result.status == "attention" and result.attention_items[0].code == "result_unconfirmed"
    with store.read() as unit:
        assert len(unit.tasks.occurrences("home")) == 1


@pytest.mark.parametrize(
    "kind,code",
    [
        ("idempotency_conflict", "original_proof_conflict"),
        ("conflict", "source_changed"),
        ("busy", "storage_busy"),
        ("storage", "result_unconfirmed"),
        ("invalid", "invalid_rule"),
        ("missing", "source_changed"),
        ("unknown", "recurrence_unavailable"),
    ],
)
def test_attention_categories_preserve_scoped_identity_and_never_echo_raw_diagnostics(
    tmp_path, monkeypatch, kind, code
):
    from domus.domain.errors import Conflict, DomusError, NotFound, StorageBusy, StorageFailure

    runner, _, rules = configured(tmp_path)
    errors = {
        "idempotency_conflict": Conflict("idempotency_conflict"),
        "conflict": Conflict("private fixture"),
        "busy": StorageBusy("private fixture"),
        "storage": StorageFailure("private fixture"),
        "invalid": InvalidInput("private fixture"),
        "missing": NotFound("private fixture"),
        "unknown": DomusError("private fixture"),
    }

    def fail(*args, **kwargs):
        raise errors[kind]

    monkeypatch.setattr(FixedMaintenance, "step", fail)
    result = runner.tick()
    assert (
        result.attention_items[0].schedule_id == rules[0] and result.attention_items[0].code == code
    )
    assert "private" not in repr(result)
