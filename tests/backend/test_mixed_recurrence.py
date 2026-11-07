"""Fixed and relative rules share owned bounded turns and independent source scanning."""

from dataclasses import replace

from test_fair_recurrence import configured
from test_household_commands import Clock
from test_relative_recurrence_creation import request

from domus.application.fair_recurrence import RelativeRunServices, RunLimits
from domus.application.recurrence_sources import RecurrenceSourceObservations
from domus.application.relative_lifecycle import RelativeLifecycle
from domus.application.relative_materialization import RelativeMaintenance
from domus.application.relative_recurrence import RelativeRecurrencePlanner
from domus.application.relative_recurrence_commands import RelativeRecurrenceCommands
from domus.application.task_commands import TaskCommands
from domus.application.task_requests import CompleteTask, ReopenTask
from domus.domain.identity import HumanIdentity
from domus.domain.task_values import OccurrenceState
from domus.infrastructure.sqlite import SQLiteDatabase


class Actor:
    def current(self):
        return HumanIdentity("ha_admin", True, True, False)


def mixed(tmp_path, *, limits=None, fixed=1, slots=1):
    runner, store, fixed_rules = configured(tmp_path, fixed, count=slots, limits=limits)
    clock, actor, ids = runner.clock, Actor(), runner.stepper.identifiers
    creation = RelativeRecurrenceCommands(store, actor, clock, ids, runner.times)
    relative = creation.create("relative", request()).result.decode()["schedule_id"]
    services = RelativeRunServices(
        RelativeMaintenance(store, runner.scope, runner.times, clock, ids),
        RecurrenceSourceObservations(store, runner.scope),
        RelativeLifecycle(store, runner.scope, RelativeRecurrencePlanner(runner.times), clock, ids),
    )
    tasks = TaskCommands(store, actor, clock, ids)
    return replace(runner, relative=services), store, fixed_rules, relative, tasks


def test_mixed_rules_share_one_slot_limit_and_restart_the_same_frontier(tmp_path):
    limits = RunLimits(max_definitions=2, max_slots=1)
    runner, store, fixed, relative, _ = mixed(tmp_path, limits=limits)
    first = runner.tick()
    assert first.created == 1 and first.status == "budget_exhausted"
    assert set(first.selected_schedule_ids) == {relative, fixed[0]}
    reopened = SQLiteDatabase(store.path, store.installation)
    runner = replace(runner, transactions=reopened)
    second = runner.tick()
    assert second.created == 1
    assert second.selected_schedule_ids[0] != first.selected_schedule_ids[0]
    with store.read() as unit:
        assert len(unit.tasks.occurrences("home")) == 2
        assert unit.recurrence.relative_progress("home", relative).current_occurrence_id is not None


def test_separate_scan_budget_and_owned_reopening_preserve_one_original_cycle(tmp_path):
    runner, store, _, schedule, tasks = mixed(tmp_path, limits=RunLimits(max_sources=1))
    runner.tick()
    with store.read() as unit:
        parent = unit.recurrence.relative_progress("home", schedule).current_occurrence_id
        member = unit.members.by_user("home", "ha_admin").member_id
    done = tasks.complete("actual", CompleteTask(parent, 1, (member,), Clock().now()))
    generated = runner.tick()
    assert generated.source_rows_examined == 1 and not generated.source_scan_complete
    assert generated.relative_slots_observed == 1
    assert generated.status == "source_pending"
    with store.read() as unit:
        successor = unit.recurrence.relative_progress("home", schedule).current_occurrence_id
        assert successor != parent
    tasks.reopen("again", ReopenTask(parent, 2, done.result.decode()["cycle"]["cycle_id"], "Again"))
    invalidated = runner.tick()
    assert invalidated.relative_slots_observed == 1
    with store.read() as unit:
        assert unit.tasks.occurrence("home", successor).state is OccurrenceState.CANCELLED
    complete = runner.tick()
    assert complete.status == "complete" and complete.source_scan_complete


def test_source_budget_keeps_unread_positions_after_restart(tmp_path):
    runner, store, _, schedule, tasks = mixed(tmp_path, limits=RunLimits(max_sources=1))
    runner.tick()
    with store.read() as unit:
        parent = unit.recurrence.relative_progress("home", schedule).current_occurrence_id
        member = unit.members.by_user("home", "ha_admin").member_id
    completed = tasks.complete("done", CompleteTask(parent, 1, (member,), Clock().now()))
    reopened = tasks.reopen(
        "opened", ReopenTask(parent, 2, completed.result.decode()["cycle"]["cycle_id"], "Again")
    )
    first = runner.tick()
    assert first.source_rows_examined == 1 and not first.source_scan_complete
    assert first.relative_slots_observed == 0
    with store.read() as unit:
        assert unit.recurrence.relative_inbox_after("home") < next(
            row.original.evidence.position
            for row in unit.tasks.lifecycle_sources("home")
            if row.original.evidence.receipt.operation_id == reopened.operation_id
        )
    reopened_store = SQLiteDatabase(store.path, store.installation)
    second = replace(runner, transactions=reopened_store).tick()
    assert second.source_rows_examined == 1 and not second.source_scan_complete
    assert runner.tick().source_scan_complete
    with store.read() as unit:
        assert len(unit.recurrence.relative_slots("home", schedule)) == 1


def test_unavailable_source_scan_leaves_fixed_and_relative_initial_work_fair(tmp_path, monkeypatch):
    from domus.domain.errors import StorageBusy

    runner, store, _, _, _ = mixed(tmp_path)

    def unavailable(*args, **kwargs):
        raise StorageBusy("fictional")

    monkeypatch.setattr(RecurrenceSourceObservations, "ingest", unavailable)
    result = runner.tick()
    assert result.created == 2 and result.status == "source_pending"
    assert result.source_rows_examined == 0 and not result.source_scan_complete
    with store.read() as unit:
        assert len(unit.tasks.occurrences("home")) == 2


def test_paused_relative_rule_still_invalidates_an_unstarted_successor(tmp_path):
    from domus.domain.recurrence_records import ScheduleState

    runner, store, _, schedule, tasks = mixed(tmp_path)
    runner.tick()
    with store.read() as unit:
        parent = unit.recurrence.relative_progress("home", schedule).current_occurrence_id
        member = unit.members.by_user("home", "ha_admin").member_id
    original = tasks.complete("done", CompleteTask(parent, 1, (member,), Clock().now()))
    runner.tick()
    with store.write() as unit:
        rule = unit.recurrence.relative_schedule("home", schedule)
        successor = unit.recurrence.relative_progress("home", schedule).current_occurrence_id
        unit.recurrence.save_relative_schedule(
            replace(rule, state=ScheduleState.PAUSED, revision=2), 1
        )
    tasks.reopen(
        "opened", ReopenTask(parent, 2, original.result.decode()["cycle"]["cycle_id"], "Again")
    )
    result = runner.tick()
    assert schedule in result.selected_schedule_ids
    assert result.relative_slots_observed == 1
    with store.read() as unit:
        assert unit.tasks.occurrence("home", successor).state is OccurrenceState.CANCELLED


def test_spending_period_budget_does_not_stop_another_definition_from_running(tmp_path):
    runner, store, fixed, relative, _ = mixed(
        tmp_path, fixed=2, slots=2, limits=RunLimits(max_periods=1)
    )
    result = runner.tick()
    assert result.periods_scanned == 1 and result.status == "budget_exhausted"
    assert relative in result.selected_schedule_ids
    with store.read() as unit:
        assert unit.recurrence.relative_progress("home", relative).current_occurrence_id
        assert len(unit.recurrence.slots("home", fixed[0])) == 1
        assert unit.recurrence.slots("home", fixed[1]) == ()


def test_source_scope_failure_stops_the_shared_runner_before_admitting_work(tmp_path):
    import pytest

    from domus.domain.errors import Forbidden

    runner, store, _, _, _ = mixed(tmp_path)
    foreign = replace(runner.scope, installation=replace(store.installation, channel="stable"))
    runner = replace(
        runner,
        relative=replace(runner.relative, sources=replace(runner.relative.sources, scope=foreign)),
    )
    with pytest.raises(Forbidden):
        runner.tick()
    with store.read() as unit:
        assert unit.recurrence.frontier("home") is None


def test_stop_while_ingesting_retains_page_but_does_not_admit_definitions(tmp_path, monkeypatch):
    from threading import Event

    runner, store, _, _, _ = mixed(tmp_path)
    stop = Event()
    ingest = RecurrenceSourceObservations.ingest

    def stopped(self, **values):
        page = ingest(self, **values)
        stop.set()
        return page

    monkeypatch.setattr(RecurrenceSourceObservations, "ingest", stopped)
    result = runner.tick(should_continue=lambda: not stop.is_set())
    assert result.status == "stopped" and result.source_rows_examined == 1
    with store.read() as unit:
        assert unit.recurrence.frontier("home") is None


def test_stopped_cycle_step_leaves_its_pending_original_untouched(tmp_path):
    runner, store, _, schedule, tasks = mixed(tmp_path)
    runner.tick()
    with store.read() as unit:
        parent = unit.recurrence.relative_progress("home", schedule).current_occurrence_id
        member = unit.members.by_user("home", "ha_admin").member_id
    tasks.complete("done", CompleteTask(parent, 1, (member,), Clock().now()))
    (observed,) = runner.relative.sources.ingest().items
    step = runner.relative.lifecycle.consume(
        schedule, observed.event.event_key, should_continue=lambda: False
    )
    assert step.status == "stopped"
    with store.read() as unit:
        assert unit.recurrence.relative_sources_pending("home")


def test_mixed_selection_validates_each_record_before_dispatch(tmp_path, monkeypatch):
    import pytest

    from domus.domain.errors import StorageFailure
    from domus.infrastructure.sqlite_recurrence import SQLiteRecurrences

    runner, store, _, _, _ = mixed(tmp_path)
    monkeypatch.setattr(SQLiteRecurrences, "schedule", lambda *args: None)
    with pytest.raises(StorageFailure, match="invalid_recurrence_record"):
        runner.tick()
    with store.read() as unit:
        assert unit.recurrence.frontier("home") is None


def test_unconfigured_mixed_runner_does_not_ingest_or_admit_any_source(tmp_path):
    from test_atomic_commands import store_at

    runner, _, _, _, _ = mixed(tmp_path)
    empty = store_at(tmp_path / "empty.sqlite3")
    assert replace(runner, transactions=empty).tick().status == "unconfigured"
    with empty.read() as unit:
        assert unit.recurrence.frontier("home") is None


def test_interrupted_relative_admission_stops_before_materializing(tmp_path, monkeypatch):
    from threading import Event

    runner, store, _, relative, _ = mixed(tmp_path, fixed=0)
    stop = Event()
    actual = RelativeMaintenance.initial

    def interrupted(self, *args, **kwargs):
        stop.set()
        return actual(self, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(RelativeMaintenance, "initial", interrupted)
        result = runner.tick(should_continue=lambda: not stop.is_set())
    assert result.status == "stopped" and result.created == 0
    with store.read() as unit:
        assert unit.recurrence.frontier("home").after_schedule_id == relative
        assert unit.recurrence.relative_slots("home", relative) == ()
    assert runner.tick().created == 1


def test_relative_bootstrap_replay_charges_the_shared_slot_budget(tmp_path):
    from test_relative_materialization import reset_progress

    runner, store, _, relative, _ = mixed(tmp_path, fixed=0, limits=RunLimits(max_slots=1))
    assert runner.tick().created == 1
    reset_progress(store, relative)
    result = runner.tick()
    assert result.created == 0 and result.replayed == 1
    with store.read() as unit:
        assert len(unit.recurrence.relative_slots("home", relative)) == 1


def test_existing_manual_work_requires_review_without_starving_fixed_work(tmp_path):
    from domus.application.task_requests import CreateTaskOccurrence

    runner, store, _, schedule, tasks = mixed(tmp_path)
    with store.read() as unit:
        rule = unit.recurrence.relative_schedule("home", schedule)
    tasks.create_occurrence("manual", CreateTaskOccurrence(rule.definition_id))
    result = runner.tick()
    assert result.status == "attention" and result.created == 1
    assert result.attention_items[0].code == "initial_review_required"
    with store.read() as unit:
        assert unit.recurrence.relative_slots("home", schedule) == ()


def test_restored_absent_bootstrap_charges_a_slot_without_recreating_work(tmp_path):
    from test_activation_compatibility import identity_at
    from test_sqlite_snapshots import Clock as SnapshotClock

    from domus.infrastructure.owned_storage import open_storage
    from domus.infrastructure.sqlite_activation import SQLiteActivation
    from domus.infrastructure.sqlite_restoration import SQLiteRestorations
    from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots

    root = tmp_path / "source"
    root.mkdir(mode=0o700)
    runner, store, _, rule, _ = mixed(root, fixed=0, limits=RunLimits(max_slots=1))
    identity_at(root, store.installation)
    archive, prepared = tmp_path / "archive", tmp_path / "prepared"
    clock = SnapshotClock()
    snapshot = SQLiteSnapshots(store, archive, store.installation, clock).create("before")
    assert runner.tick().created == 1
    SQLiteRestorations(store, archive, prepared, store.installation, clock, snapshot).prepare(
        "back"
    )
    SQLiteActivation(root, store.installation, clock, prepared).activate()
    restored = open_storage(root, "edge")
    try:
        service = runner.relative
        reopened = replace(
            runner,
            transactions=restored.database,
            relative=RelativeRunServices(
                replace(service.initial, transactions=restored.database),
                replace(service.sources, transactions=restored.database),
                replace(service.lifecycle, transactions=restored.database),
            ),
        )
        result = reopened.tick()
        assert result.historical_absent == 1 and result.created == 0
        with restored.database.read() as unit:
            assert unit.recurrence.relative_slots("home", rule) == ()
    finally:
        restored.close()


def test_more_than_fifty_mixed_definitions_get_distinct_bounded_turns(tmp_path):
    runner, store, fixed, relative, _ = mixed(tmp_path, fixed=50)
    first = runner.tick()
    assert len(first.selected_schedule_ids) == 50 and first.created == 50
    reopened = replace(runner, transactions=SQLiteDatabase(store.path, store.installation))
    second = reopened.tick()
    assert len(second.selected_schedule_ids) == 50 and second.created == 1
    assert set(first.selected_schedule_ids + second.selected_schedule_ids) == {*fixed, relative}
    with store.read() as unit:
        assert len(unit.tasks.occurrences("home", limit=100)) == 51
