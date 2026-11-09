"""Real SQLite range counts, durable timing facts and current authorization."""

from dataclasses import replace
from datetime import date

import pytest
from test_recurrence_review import fixed_move, reviewed
from test_task_commands import fixture

from domus.application.calendar_queries import CalendarQueries
from domus.application.fixed_materialization import MaintenanceScope
from domus.application.recurrence_sources import RecurrenceSourceObservations
from domus.application.task_category_commands import TaskCategoryCommands
from domus.application.task_requests import (
    CompleteTask,
    CreateTask,
    CreateTaskOccurrence,
    VerifyTask,
)
from domus.domain.calendar_values import (
    CalendarFilters,
    CalendarKind,
    CalendarRange,
    CalendarTiming,
)
from domus.domain.errors import Forbidden, InvalidInput
from domus.domain.identity import HumanIdentity
from domus.domain.task_values import OccurrenceState, Priority, TaskContent, VerificationState
from domus.infrastructure.recurrence_time import PinnedRecurrenceTime
from domus.infrastructure.task_cursor import TaskCursor


def query(store, actor, clock):
    scope = MaintenanceScope(store.installation, "home")
    return CalendarQueries(
        store, scope, actor.human, TaskCursor(clock, b"k" * 32), PinnedRecurrenceTime()
    )


def test_date_only_slots_keep_original_and_effective_dates_through_move(tmp_path):
    review, choice, _, _ = fixed_move(tmp_path)
    store = review.transactions
    calendar = query(store, review.actor, review.clock)
    period = CalendarRange(date(2026, 3, 29), date(2026, 4, 3))
    _, move = reviewed(review, choice)
    review.apply("move", move)
    filters = CalendarFilters(timing=CalendarTiming.FIXED)
    first = calendar.page(period, filters, limit=1)
    second = calendar.page(period, filters, limit=1, cursor=first.next_cursor)
    assert first.count == second.count == 2
    assert first.occurrence_count == second.occurrence_count == 1
    assert first.pending and second.next_cursor is None
    (due,), (planned,) = first.entries, second.entries
    assert due.kind is CalendarKind.DUE and due.local_date == date(2026, 4, 2)
    assert planned.kind is CalendarKind.PLANNED and planned.local_date == date(2026, 3, 29)
    assert due.instant_ms is planned.instant_ms is due.local_time is planned.local_time is None
    assert due.slot_key == planned.slot_key == choice.slot_key
    with pytest.raises(InvalidInput, match="invalid_task_cursor"):
        calendar.page(
            period, replace(filters, kind=CalendarKind.DUE), limit=1, cursor=first.next_cursor
        )
    with pytest.raises(InvalidInput, match="invalid_calendar_cursor"):
        calendar.page(period, filters, cursor="unknown~bad")
    foreign = replace(calendar, human=HumanIdentity("ha_child", False, True, False))
    with pytest.raises(InvalidInput, match="invalid_task_cursor"):
        foreign.page(period, filters, limit=1, cursor=first.next_cursor)
    with pytest.raises(Forbidden):
        calendar.page(period, replace(filters, member_id="outside"))
    with pytest.raises(Forbidden):
        replace(calendar, human=HumanIdentity("stranger", False, True, False)).page(period, filters)


def test_combined_filters_count_actual_performers_independently_of_assignees(tmp_path):
    tasks, store, actor, identifiers = fixture(tmp_path)
    catalog = TaskCategoryCommands(store, actor, actor.current, tasks.clock, identifiers)
    garden = catalog.create("garden-category", "Garden").result.decode()["category_id"]
    other = catalog.create("other-category", "Other").result.decode()["category_id"]
    result = tasks.create(
        "manual",
        CreateTask(
            TaskContent(
                "Filter", priority=Priority.HIGH, tags=("independent-tag",), category_id=garden
            )
        ),
    )
    resource = result.result.decode()
    work = tasks.create_occurrence(
        "due", CreateTaskOccurrence(resource["definition_id"], assignee_ids=("child",), due_at=70)
    ).result.decode()
    done = tasks.complete("done", CompleteTask(work["occurrence_id"], 1, ("other",), 80))
    tasks.verify(
        "approved",
        VerifyTask(
            work["occurrence_id"],
            2,
            done.result.decode()["cycle"]["cycle_id"],
            VerificationState.APPROVED,
        ),
    )
    calendar = query(store, actor, tasks.clock)
    period = CalendarRange(date(1970, 1, 1), date(1970, 1, 2))
    filters = CalendarFilters(
        timing=CalendarTiming.MANUAL,
        state=OccurrenceState.COMPLETED,
        priority=Priority.HIGH,
        category=garden,
    )
    (due,) = calendar.page(period, replace(filters, member_id="child")).entries
    (performed,) = calendar.page(period, replace(filters, member_id="other")).entries
    assert (due.kind, due.instant_ms, due.member_ids) == (CalendarKind.DUE, 70, ("child",))
    assert (performed.kind, performed.instant_ms, performed.member_ids) == (
        CalendarKind.PERFORMED,
        80,
        ("other",),
    )
    approval = calendar.page(period, replace(filters, kind=CalendarKind.APPROVAL))
    assert approval.count == 1 and approval.entries[0].verification is VerificationState.APPROVED
    assert approval.entries[0].local_time == "00:00:00.100000"
    assert calendar.page(period, filters).pending
    RecurrenceSourceObservations(store, calendar.scope).ingest()
    assert not calendar.page(period, filters).pending
    assert calendar.page(period, replace(filters, category=other)).count == 0


def test_timed_planned_fact_keeps_nominal_and_gap_adjusted_time(tmp_path):
    from test_fixed_materialization import configured

    materializer, store, actor, _, schedule, before = configured(tmp_path, timed=True)
    step = materializer.step(schedule, before)
    calendar = query(store, actor, materializer.clock)
    period = CalendarRange(date(2026, 3, 29), date(2026, 3, 30))
    page = calendar.page(period, CalendarFilters(kind=CalendarKind.PLANNED))
    (entry,) = page.entries
    assert entry.occurrence_id == step.occurrence_id and entry.instant_ms > 0
    assert entry.nominal_local == "2026-03-29T02:30:00"
    assert entry.local_time == "03:00:00" and entry.time_zone == "Europe/Madrid"
    assert not page.pending


def test_calendar_local_authority_and_range_are_rechecked_after_zone_resolution(
    tmp_path, monkeypatch
):
    from domus.domain.errors import Conflict
    from domus.infrastructure.sqlite import SQLiteDatabase, SQLiteHouseholds

    tasks, store, actor, _ = fixture(tmp_path)
    calendar = query(store, actor, tasks.clock)
    period = CalendarRange(date(1970, 1, 1), date(1970, 1, 2))
    filters = CalendarFilters()
    with pytest.raises(InvalidInput, match="invalid_page_size"):
        calendar.page(period, filters, limit=0)
    empty = SQLiteDatabase(tmp_path / "empty.sqlite3", store.installation)
    empty.initialize()
    with pytest.raises(Forbidden):
        replace(calendar, transactions=empty).page(period, filters)
    current = SQLiteHouseholds.current
    calls = 0

    def changed(self):
        nonlocal calls
        home = current(self)
        calls += 1
        return home if calls == 1 else replace(home, revision=home.revision + 1)

    with monkeypatch.context() as patch:
        patch.setattr(SQLiteHouseholds, "current", changed)
        with pytest.raises(Conflict, match="calendar_context_changed"):
            calendar.page(period, filters)


def test_calendar_refuses_corrupt_projection_and_time_provider(tmp_path, monkeypatch):
    from domus.domain.calendar_values import CalendarCandidate, CalendarPosition
    from domus.domain.errors import IntegrationUnavailable, StorageFailure

    tasks, store, actor, _ = fixture(tmp_path)
    result = tasks.create("task", CreateTask(TaskContent("Manual fixture"))).result.decode()
    oid = result["occurrence_id"]
    calendar = query(store, actor, tasks.clock)

    def position(kind, source=oid):
        return CalendarPosition(kind, source)

    invalid = (
        CalendarCandidate(position(CalendarKind.DUE), "absent", CalendarTiming.MANUAL, None),
        CalendarCandidate(position(CalendarKind.PLANNED), oid, CalendarTiming.MANUAL, None),
        CalendarCandidate(position(CalendarKind.DUE), oid, CalendarTiming.MANUAL, None),
        CalendarCandidate(position(CalendarKind.DUE), oid, CalendarTiming.FIXED, "missing"),
        CalendarCandidate(
            position(CalendarKind.APPROVAL, "absent"), oid, CalendarTiming.MANUAL, None
        ),
    )
    with store.read() as unit:
        for row in invalid:
            with pytest.raises(StorageFailure, match="invalid_calendar_projection"):
                calendar._entry(unit, row)
    completion = tasks.complete("completed", CompleteTask(oid, 1, ("other",), 90))
    cycle = completion.result.decode()["cycle"]["cycle_id"]
    with store.read() as unit, pytest.raises(StorageFailure, match="invalid_calendar_projection"):
        calendar._entry(
            unit,
            CalendarCandidate(
                position(CalendarKind.APPROVAL, cycle), oid, CalendarTiming.MANUAL, None
            ),
        )
    monkeypatch.setattr(PinnedRecurrenceTime, "local_at", lambda *_: None)
    with pytest.raises(IntegrationUnavailable, match="recurrence_time_source_invalid"):
        calendar.page(CalendarRange(date(1970, 1, 1), date(1970, 1, 2)), CalendarFilters())


def test_relative_timed_projection_loads_exact_slot_and_its_due_instant(tmp_path):
    from test_relative_materialization import configured

    from domus.domain.calendar_values import CalendarCandidate, CalendarPosition
    from domus.domain.errors import StorageFailure

    service, store, actor, _, rule, _ = configured(tmp_path, timed=True)
    effect = service.initial(rule)
    calendar = query(store, actor, service.clock)
    period = CalendarRange(date(2026, 3, 29), date(2026, 3, 30))
    entries = calendar.page(period, CalendarFilters(timing=CalendarTiming.RELATIVE)).entries
    assert {item.kind for item in entries} == {CalendarKind.DUE, CalendarKind.PLANNED}
    assert len({item.instant_ms for item in entries}) == 1
    candidate = CalendarCandidate(
        CalendarPosition(CalendarKind.DUE, effect.occurrence_id),
        effect.occurrence_id,
        CalendarTiming.RELATIVE,
        effect.receipt.command.key,
    )
    with store.write() as unit:
        work = unit.tasks.occurrence("home", effect.occurrence_id)
        unit.tasks.save_occurrence(replace(work, due_at=None, revision=2), 1)
    with store.read() as unit, pytest.raises(StorageFailure, match="invalid_calendar_projection"):
        calendar._entry(unit, candidate)


@pytest.mark.parametrize("duplicate", [False, True])
def test_sqlite_calendar_refuses_malformed_or_duplicate_selected_keys(duplicate):
    from types import SimpleNamespace

    from domus.domain.errors import StorageFailure
    from domus.infrastructure.sqlite_calendar import SQLiteCalendar

    row = {
        "kind": "due" if duplicate else "unrecognized",
        "source_id": "task-1",
        "occurrence_id": "task-1",
        "timing": "manual",
        "slot_key": None,
    }

    class Selected(list):
        def fetchone(self):
            return len(self), 1

    connection = SimpleNamespace(execute=lambda *_: Selected((row, row)))
    adapter = SQLiteCalendar(connection)
    with pytest.raises(StorageFailure, match="invalid_calendar_projection"):
        adapter.page(
            "home",
            CalendarRange(date(1970, 1, 1), date(1970, 1, 2)),
            CalendarFilters(),
            0,
            86_400_000,
            25,
            None,
        )


def test_distinct_task_count_preserves_both_completion_cycle_identities(tmp_path):
    from domus.application.task_requests import ReopenTask

    tasks, store, actor, _ = fixture(tmp_path)
    created = tasks.create("two-cycles", CreateTask(TaskContent("Repeat work"))).result.decode()
    occurrence = tasks.create_occurrence(
        "deadline", CreateTaskOccurrence(created["definition_id"], due_at=40)
    ).result.decode()["occurrence_id"]
    first = tasks.complete("first", CompleteTask(occurrence, 1, ("child",), 60)).result.decode()
    first_cycle = first["cycle"]["cycle_id"]
    tasks.verify(
        "first-approval", VerifyTask(occurrence, 2, first_cycle, VerificationState.APPROVED)
    )
    tasks.reopen("repeat", ReopenTask(occurrence, 3, first_cycle, "Do it again"))
    second = tasks.complete("second", CompleteTask(occurrence, 4, ("other",), 70)).result.decode()
    second_cycle = second["cycle"]["cycle_id"]
    tasks.verify(
        "second-approval", VerifyTask(occurrence, 5, second_cycle, VerificationState.APPROVED)
    )

    calendar = query(store, actor, tasks.clock)
    period = CalendarRange(date(1970, 1, 1), date(1970, 1, 2))
    complete = calendar.page(period, CalendarFilters())
    assert (complete.count, complete.occurrence_count) == (5, 1)
    assert {entry.entry_id for entry in complete.entries} == {
        f"due:{occurrence}",
        f"performed:{first_cycle}",
        f"performed:{second_cycle}",
        f"approval:{first_cycle}",
        f"approval:{second_cycle}",
    }
    after = None
    observed = []
    while True:
        page = calendar.page(period, CalendarFilters(), limit=2, cursor=after)
        assert (page.count, page.occurrence_count) == (5, 1)
        observed.extend(page.entries)
        after = page.next_cursor
        if after is None:
            break
    assert tuple(observed) == complete.entries
