"""Read authoritative Overview counts through both protected task compositions."""

from dataclasses import replace
from datetime import UTC, date, datetime

import pytest
from test_recurrence_review import fixed_move, review_service, reviewed
from test_relative_materialization import configured as relative_configured
from test_task_runtime import api as api
from test_tasks import definition

from domus.application.reschedule_review import RescheduleSelection
from domus.application.task_queries import TaskQueries
from domus.domain.identity import Member, MemberStatus, Permission, PermissionRule, Role
from domus.domain.recurrence_rules import NominalDate
from domus.domain.task_values import OccurrenceState, TaskRules
from domus.domain.tasks import HouseholdTaskPolicy
from domus.infrastructure.application_runtime import SystemClock
from domus.infrastructure.task_cursor import TaskCursor

OVERVIEW = "/api/v1/tasks/overview"
OTHER_USER = "b" * 32


def test_overview_groups_authorized_records_and_counts_beyond_the_page(api):
    empty = {"total": 0, "items": []}
    assert api.client.get(OVERVIEW).json() == {
        "assigned": empty,
        "unclaimed": empty,
        "due_today": empty,
        "overdue": empty,
    }
    assert api.client.get(OVERVIEW, params={"member_id": "other"}).status_code == 422

    task = definition()
    with api.store.write() as unit:
        member = unit.members.list("home")[0]
        unit.members.save(
            Member("other", "home", OTHER_USER, Role.ADULT, MemberStatus.ACTIVE, 1), 0
        )
        unit.tasks.save_policy(HouseholdTaskPolicy("home", TaskRules()), 0)
        unit.tasks.save_definition(task, 0)
        for number in range(27):
            unit.tasks.save_occurrence(task.new_occurrence(f"unclaimed-{number:02}", 20), 0)
            unit.tasks.save_occurrence(
                task.new_occurrence(f"assigned-{number:02}", 20, assignees=(member.member_id,)),
                0,
            )
        blocked = task.new_occurrence("blocked", 20, assignees=(member.member_id,))
        unit.tasks.save_occurrence(blocked, 0)
        unit.tasks.save_occurrence(blocked.transition(OccurrenceState.BLOCKED, "Waiting"), 1)
        started = task.new_occurrence("started", 20, assignees=(member.member_id,))
        unit.tasks.save_occurrence(started, 0)
        unit.tasks.save_occurrence(started.transition(OccurrenceState.IN_PROGRESS), 1)
        other = task.new_occurrence("other-task", 20, assignees=("other",))
        unit.tasks.save_occurrence(other, 0)
        closed = task.new_occurrence("closed", 20, assignees=(member.member_id,))
        unit.tasks.save_occurrence(closed, 0)
        unit.tasks.save_occurrence(closed.transition(OccurrenceState.CANCELLED, "Done"), 1)

    response = api.client.get(OVERVIEW)
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["assigned"] == {
        "total": 29,
        "items": [
            {"occurrence_id": f"assigned-{number:02}", "title": "Wipe table", "state": "assigned"}
            for number in range(25)
        ],
    }
    assert report["unclaimed"] == {
        "total": 27,
        "items": [
            {"occurrence_id": f"unclaimed-{number:02}", "title": "Wipe table", "state": "available"}
            for number in range(25)
        ],
    }
    assert api.client.get("/api/v1/tasks/occurrences/assigned-00").status_code == 200

    with api.store.write() as unit:
        for number in range(27):
            item = unit.tasks.occurrence("home", f"assigned-{number:02}")
            unit.tasks.save_occurrence(item.assign(("other",)), item.revision)
    refreshed = api.client.get(OVERVIEW).json()
    assert refreshed["assigned"] == {
        "total": 2,
        "items": [
            {"occurrence_id": "blocked", "title": "Wipe table", "state": "blocked"},
            {"occurrence_id": "started", "title": "Wipe table", "state": "in_progress"},
        ],
    }
    assert refreshed["unclaimed"] == report["unclaimed"]


def test_overview_requires_current_task_read_authority(api):
    assert api.client.get(OVERVIEW).status_code == 200
    with api.store.write() as unit:
        member = unit.members.list("home")[0]
        unit.members.save(
            replace(member, exceptions=(PermissionRule(Permission.TASKS_READ, False),), revision=2),
            1,
        )
    denied = api.client.get(OVERVIEW)
    assert denied.status_code == 403
    assert not {"assigned", "unclaimed", "due_today", "overdue"} & denied.json().keys()


def millis(year, month, day, hour=0, minute=0):
    return int(datetime(year, month, day, hour, minute, tzinfo=UTC).timestamp()) * 1000


def test_overview_timed_deadlines_use_one_clock_and_the_household_day(api, monkeypatch):
    now = millis(2026, 3, 29, 21, 30)
    next_day = millis(2026, 3, 29, 22)
    monkeypatch.setattr(SystemClock, "now", lambda _: now)
    task = definition()
    with api.store.write() as unit:
        home = unit.households.get("home")
        unit.households.save(replace(home, time_zone="Europe/Madrid", revision=2), 1)
        unit.tasks.save_policy(HouseholdTaskPolicy("home", TaskRules()), 0)
        unit.tasks.save_definition(task, 0)
        for number in range(27):
            for name, due in ((f"late-{number:02}", now - 1), (f"today-{number:02}", now + 1)):
                unit.tasks.save_occurrence(task.new_occurrence(name, 20, due_at=due), 0)
        for name, due in (
            ("at-now", now),
            ("last-today", next_day - 1),
            ("next-day", next_day),
            ("undated", None),
        ):
            unit.tasks.save_occurrence(task.new_occurrence(name, 20, due_at=due), 0)
        closed = task.new_occurrence("already-closed", 20, due_at=now - 1)
        unit.tasks.save_occurrence(closed, 0)
        unit.tasks.save_occurrence(closed.transition(OccurrenceState.CANCELLED, "Withdrawn"), 1)

    response = api.client.get(OVERVIEW)
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["due_today"]["total"] == 29
    assert report["overdue"]["total"] == 27
    assert len(report["due_today"]["items"]) == len(report["overdue"]["items"]) == 25
    first, last = report["due_today"]["items"][:2]
    assert first["occurrence_id"] == "at-now" and last["occurrence_id"] == "last-today"
    assert first["deadline"] == {
        "local_date": None,
        "instant_ms": str(now),
        "time_zone": "Europe/Madrid",
    }
    assert last["deadline"]["instant_ms"] == str(next_day - 1)
    assert [item["occurrence_id"] for item in report["overdue"]["items"]] == [
        f"late-{number:02}" for number in range(25)
    ]
    now = next_day
    after_midnight = api.client.get(OVERVIEW).json()
    assert after_midnight["overdue"]["total"] == 56
    assert [item["occurrence_id"] for item in after_midnight["due_today"]["items"]] == ["next-day"]


@pytest.mark.parametrize("kind", ["fixed", "relative"])
def test_date_only_overview_uses_the_reviewed_deadline_and_saved_zone(tmp_path, kind):
    moved_day = date(2026, 4, 2)
    if kind == "fixed":
        service, choice, _, _ = fixed_move(tmp_path)
        store = service.transactions
    else:
        initial, store, actor, identifiers, schedule_id, _ = relative_configured(tmp_path)
        work = initial.initial(schedule_id)
        service = review_service(initial, store, actor, identifiers)
        choice = RescheduleSelection(
            schedule_id,
            1,
            work.receipt.command.key,
            work.occurrence_id,
            1,
            NominalDate(moved_day),
            "Review the new date",
        )
    _, move = reviewed(service, choice)
    service.apply("move", move)
    queries = TaskQueries(
        store, service.actor.current(), TaskCursor(service.clock, b"k" * 32), store.installation
    )
    times = service.planner.times
    with store.write() as unit:
        home = unit.households.get("home")
        unit.households.save(
            replace(home, time_zone="UTC", revision=home.revision + 1), home.revision
        )

    class ObservationClock:
        value = millis(2026, 4, 1, 21, 59)
        reads = 0

        def now(self):
            self.reads += 1
            return self.value

    clock = ObservationClock()
    before = queries.overview(clock, times)
    assert before.due_today.total == before.overdue.total == 0
    clock.value = millis(2026, 4, 1, 22)
    today = queries.overview(clock, times)
    assert today.due_today.total == 1 and today.overdue.total == 0
    (work,) = today.due_today.items
    assert work.occurrence_id == choice.occurrence_id
    assert (work.deadline.local_date, work.deadline.instant_ms, work.deadline.time_zone) == (
        moved_day,
        None,
        "Europe/Madrid",
    )
    clock.value = millis(2026, 4, 2, 22)
    overdue = queries.overview(clock, times)
    assert overdue.due_today.total == 0 and overdue.overdue.total == 1
    assert overdue.overdue.items == (work,)
    assert clock.reads == 3
    with store.write() as unit:
        home = unit.households.get("home")
        unit.households.save(
            replace(home, time_zone="Europe/Madrid", revision=home.revision + 1),
            home.revision,
        )
    assert queries.overview(clock, times).overdue == overdue.overdue
    assert clock.reads == 4
