"""Integrated recurrence evidence with original operations and independent SQLite handles."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from datetime import date
from threading import Event

from test_activation_compatibility import identity_at
from test_mixed_recurrence import mixed
from test_recurrence_review import reviewed
from test_relative_lifecycle_consumer import completed
from test_sqlite_snapshots import Clock
from test_task_commands import counts

from domus.application.calendar_queries import CalendarQueries
from domus.application.fair_recurrence import RelativeRunServices, RunLimits
from domus.application.recurrence_review import RecurrenceReview
from domus.application.relative_state_review import RelativeSettings
from domus.application.task_requests import (
    AssignTask,
    CompleteTask,
    CreateTask,
    ReopenTask,
    TransitionTask,
    VerifyTask,
)
from domus.domain.calendar_values import CalendarFilters, CalendarRange
from domus.domain.recurrence_time import RelativeInterval
from domus.domain.relative_lifecycle import RelativeClosure
from domus.domain.relative_recurrence import SuccessorVisibility
from domus.domain.task_values import OccurrenceState, TaskContent, VerificationState
from domus.infrastructure.owned_storage import open_storage
from domus.infrastructure.sqlite import SQLiteDatabase
from domus.infrastructure.sqlite_activation import SQLiteActivation
from domus.infrastructure.sqlite_restoration import SQLiteRestorations
from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots
from domus.infrastructure.sqlite_tasks import SQLiteTasks
from domus.infrastructure.task_cursor import TaskCursor


def _ready_sources(tmp_path, *, manual_first):
    runner, store, _, rule, tasks = mixed(tmp_path, limits=RunLimits(max_sources=1))
    runner.tick()
    with store.read() as unit:
        parent = unit.recurrence.relative_progress("home", rule).current_occurrence_id
        member = unit.members.by_user("home", "ha_admin").member_id
        assert not unit.calendar.rules_pending("home")
    ordinary = tasks.create("ordinary", CreateTask(TaskContent("Manual control"))).result.decode()
    order = (
        (ordinary["occurrence_id"], parent) if manual_first else (parent, ordinary["occurrence_id"])
    )
    receipts = tuple(
        tasks.complete(f"performed-{index}", CompleteTask(oid, 1, (member,), 90))
        for index, oid in enumerate(order)
    )
    with store.read() as unit:
        records = unit.tasks.lifecycle_sources("home")
        assert tuple(record.original.evidence.receipt for record in records) == receipts
    return runner, store, rule, tasks, records


def test_nonactionable_final_scan_unit_keeps_the_next_source_for_a_fresh_runner(tmp_path):
    runner, store, rule, _, (ordinary, relative) = _ready_sources(tmp_path, manual_first=True)
    first = runner.tick()
    assert first.status == "source_pending" and first.source_rows_examined == 1
    assert not first.source_scan_complete and first.relative_slots_observed == 0
    with store.read() as unit:
        assert unit.recurrence.relative_inbox_after("home") == ordinary.original.evidence.position
        assert (
            unit.recurrence.relative_source("home", relative.event(store.installation).event_key)
            is None
        )

    fresh = SQLiteDatabase(store.path, store.installation)
    services = runner.relative
    reopened = replace(
        runner,
        transactions=fresh,
        stepper=replace(runner.stepper, transactions=fresh),
        relative=RelativeRunServices(
            replace(services.initial, transactions=fresh),
            replace(services.sources, transactions=fresh),
            replace(services.lifecycle, transactions=fresh),
        ),
    )
    second = reopened.tick()
    assert second.source_rows_examined == 1 and not second.source_scan_complete
    assert second.relative_slots_observed == 1
    assert reopened.tick().source_scan_complete
    with fresh.read() as unit:
        assert unit.recurrence.relative_inbox_after("home") == relative.original.evidence.position
        assert len(unit.recurrence.relative_slots("home", rule)) == 2


def test_calendar_stays_pending_when_the_watermark_has_passed_unresolved_work(tmp_path):
    runner, store, _, tasks, (relative, ordinary) = _ready_sources(tmp_path, manual_first=False)
    admitted = runner.relative.sources.ingest(limit=2)
    assert admitted.after_position == ordinary.original.evidence.position
    with store.read() as unit:
        assert not unit.tasks.lifecycle_sources("home", after=admitted.after_position)
        assert not unit.calendar.rules_pending("home")
        assert unit.recurrence.relative_sources_pending("home")
        assert (
            unit.recurrence.relative_source_outcome(
                "home", relative.event(store.installation).event_key
            )
            is None
        )

    calendar = CalendarQueries(
        store, runner.scope, tasks.actor.current(), TaskCursor(tasks.clock, b"k" * 32), runner.times
    )
    period = CalendarRange(date(2040, 1, 1), date(2040, 1, 2))
    incomplete = calendar.page(period, CalendarFilters())
    assert incomplete.entries == () and incomplete.count == 0 and incomplete.pending
    assert runner.tick().relative_slots_observed == 1
    complete = calendar.page(period, CalendarFilters())
    assert complete.entries == () and complete.count == 0 and not complete.pending


def test_a_committing_start_wins_against_an_independent_invalidation_writer(tmp_path, monkeypatch):
    store, rule, parent, source, lifecycle, original, tasks, member = completed(tmp_path)
    generated = lifecycle.consume(rule, original.event_key)
    successor = generated.occurrence_id
    tasks.assign("assign-successor", AssignTask(successor, 1, (member.member_id,)))
    tasks.reopen(
        "reopen-source", ReopenTask(parent, 2, original.cycle.cycle_id, "Review the source")
    )
    (reopening,) = source.ingest().items
    with store.read() as unit:
        cycles = unit.tasks.cycles("home")
        events_before = len(unit.outbox.pending())
    start_written, invalidate_entered = Event(), Event()
    save = SQLiteTasks.save_occurrence

    def hold_started_work(self, work, revision):
        save(self, work, revision)
        if work.occurrence_id == successor and work.state is OccurrenceState.IN_PROGRESS:
            start_written.set()
            assert invalidate_entered.wait(3)

    class InvalidationDatabase(SQLiteDatabase):
        @contextmanager
        def write(self):
            invalidate_entered.set()
            with super().write() as unit:
                yield unit

    monkeypatch.setattr(SQLiteTasks, "save_occurrence", hold_started_work)
    independent = replace(
        lifecycle, transactions=InvalidationDatabase(store.path, store.installation, busy_timeout=5)
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        start = pool.submit(
            tasks.transition, "started", TransitionTask(successor, 2, OccurrenceState.IN_PROGRESS)
        )
        assert start_written.wait(3)
        invalidate = pool.submit(independent.consume, rule, reopening.event.event_key)
        started, reviewed_invalidation = start.result(), invalidate.result()
    assert reviewed_invalidation.status == "review"
    assert independent.consume(rule, reopening.event.event_key) == reviewed_invalidation
    with store.read() as unit:
        assert unit.tasks.occurrence("home", successor).state is OccurrenceState.IN_PROGRESS
        assert unit.tasks.cycles("home") == cycles
        assert {event.event_id for event in unit.outbox.pending()[events_before:]} == {
            started.operation_id,
            reviewed_invalidation.receipt.operation_id,
        }


def test_delayed_approval_after_a_reviewed_rule_edit_and_restore_cannot_grant_again(tmp_path):
    root = tmp_path / "source"
    root.mkdir(mode=0o700)
    store, rule, parent, source, lifecycle, event, tasks, _ = completed(root, child=True)
    generated = lifecycle.consume(rule, event.event_key)
    review = RecurrenceReview(
        store,
        store.installation,
        tasks.actor,
        tasks.actor.current,
        tasks.clock,
        tasks.identifiers,
        lifecycle.planner,
    )
    choice = RelativeSettings(rule, 1, RelativeInterval(12), SuccessorVisibility.AT_VERIFICATION)
    _, change = reviewed(review, choice)
    review.apply("new-interval", change)
    identity_at(root, store.installation)
    archive, target = tmp_path / "archive", tmp_path / "prepared"
    checkpoint = SQLiteSnapshots(store, archive, store.installation, Clock()).create("new-rule")
    approval = tasks.verify(
        "delayed", VerifyTask(parent, 2, event.cycle.cycle_id, VerificationState.APPROVED)
    )
    SQLiteRestorations(store, archive, target, store.installation, Clock(), checkpoint).prepare(
        "restore-before-approval"
    )
    assert SQLiteActivation(root, store.installation, Clock(), target).activate().state == "active"
    restored = open_storage(root, "edge")
    try:
        fresh = restored.database
        with fresh.read() as unit:
            current = unit.recurrence.relative_schedule("home", rule)
            key = RelativeClosure.cycle_key(current, event.cycle, store.installation)
            closure = unit.recurrence.relative_closure("home", key)
            assert current.revision == 2 and closure.schedule.revision == 1
        (later,) = replace(source, transactions=fresh).ingest().items
        assert later.event.event_id == approval.operation_id and not later.original.current
        initial = counts(fresh)
        outcome = replace(lifecycle, transactions=fresh).consume(rule, later.event.event_key)
        assert outcome == generated
        assert counts(fresh) == initial
        with fresh.read() as unit:
            assert unit.tasks.cycle("home", event.cycle.cycle_id) == event.cycle
            assert len(unit.recurrence.relative_slots("home", rule)) == 2
    finally:
        restored.close()
