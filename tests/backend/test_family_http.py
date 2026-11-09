"""Real SQLite and both protected production compositions exercise Family's read projection."""

from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace

from test_recurrence_http import CONTEXT, USER
from test_task_commands import resource
from test_task_runtime import api as api

from domus.application.points import PointsConsumer
from domus.application.task_commands import TaskCommands
from domus.application.task_requests import (
    AssignTask,
    CompleteTask,
    CreateTask,
    ReopenTask,
    TransitionTask,
    VerifyTask,
)
from domus.domain.identity import HumanIdentity, Member, MemberStatus, Role
from domus.domain.task_values import OccurrenceState, TaskContent, TaskOverrides, VerificationState
from domus.infrastructure.application_runtime import SecureIdentifiers
from domus.infrastructure.sqlite import SQLiteDatabase

ROUTE = "/api/v1/family"
CHILD_USER = "b" * 32
CHILD_CONTEXT = {"X-Domus-Context": CONTEXT["X-Domus-Context"].replace(USER, CHILD_USER)}
WEEK = {"start": "2026-05-25", "end": "2026-06-01"}
MONTH = {"start": "2026-05-01", "end": "2026-06-01"}
NEXT_WEEK = {"start": "2026-06-01", "end": "2026-06-08"}


def timestamp(day, hour, minute=0):
    return int(
        datetime(2026, 5 if day == 31 else 6, day, hour, minute, tzinfo=UTC).timestamp() * 1000
    )


def test_family_scope_is_current_and_rejects_caller_scope(api):
    api.user(USER, True)
    assert api.client.get(ROUTE, params=WEEK).status_code == 422
    for params in (WEEK | {"member_id": "child"}, WEEK | {"start": "2026-05-32"}):
        assert api.client.get(ROUTE, params=params, headers=CONTEXT).status_code == 422
    assert (
        api.client.get(ROUTE, params=WEEK, headers={"X-Domus-Context": "v1:forged"}).status_code
        == 403
    )
    valid = api.client.get(ROUTE, params=WEEK, headers=CONTEXT)
    assert valid.status_code == 200, valid.text
    assert valid.headers["cache-control"] == "no-store"
    assert valid.json()["available_minor"] == 0
    with api.store.write() as unit:
        current = unit.members.by_user("home", USER)
        unit.members.save(
            replace(current, status=MemberStatus.SUSPENDED, revision=current.revision + 1),
            current.revision,
        )
    denied = api.client.get(ROUTE, params=WEEK, headers=CONTEXT)
    assert denied.status_code == 403
    assert "posted_minor" not in denied.json()


def test_actual_work_period_retains_pending_award_reversal_and_effort_after_restart(api):
    api.user(USER, True)
    with api.store.write() as unit:
        home = unit.households.current()
        unit.households.save(replace(home, time_zone="Europe/Madrid", revision=2), 1)
        unit.members.save(
            Member("child", "home", CHILD_USER, Role.RESTRICTED, MemberStatus.ACTIVE, 1), 0
        )
    clock = SimpleNamespace(value=timestamp(31, 21, 10))
    clock.now = lambda: clock.value
    actor = SimpleNamespace(current=lambda: HumanIdentity(USER, True, True, False))
    tasks = TaskCommands(api.store, actor, clock, SecureIdentifiers())
    created = tasks.create(
        "create-task",
        CreateTask(TaskContent("Water plants"), overrides=TaskOverrides(point_value_minor=125)),
    )
    _, work = resource(created)
    clock.value = timestamp(31, 21, 20)
    assigned = tasks.assign("assign", AssignTask(work, 1, ("child",)))
    started = tasks.transition(
        "start",
        TransitionTask(work, assigned.result.decode()["revision"], OccurrenceState.IN_PROGRESS),
    )
    work_time = timestamp(31, 21, 50)
    clock.value = work_time
    completion = tasks.complete(
        "complete", CompleteTask(work, started.result.decode()["revision"], ("child",), work_time)
    )
    result = completion.result.decode()
    cycle = result["cycle"]["cycle_id"]
    worker = PointsConsumer(api.store, api.store.installation, clock)
    assert worker.tick(lambda: True) == 1

    def report(period=WEEK, **query):
        response = api.client.get(ROUTE, params=period | query, headers=CHILD_CONTEXT)
        assert response.status_code == 200, response.text
        return response.json()

    api.user(CHILD_USER)
    pending = report()
    assert pending["time_zone"] == "Europe/Madrid"
    assert pending["completed_count"] == pending["tracked_count"] == 1
    assert pending["elapsed_ms"] == 30 * 60_000
    assert pending["pending_verification_minor"] == 125
    assert pending["pending_posting_minor"] == pending["available_minor"] == 0
    assert report(NEXT_WEEK)["completed_count"] == 0

    clock.value = timestamp(31, 22, 5)
    approved = tasks.verify(
        "approve", VerifyTask(work, result["revision"], cycle, VerificationState.APPROVED)
    )
    waiting = report(MONTH)
    assert waiting["pending_posting_minor"] == 125
    assert waiting["pending_verification_minor"] == waiting["available_minor"] == 0
    verified_at = clock.value
    clock.value = timestamp(31, 22, 7)
    restarted = replace(worker, store=SQLiteDatabase(api.store.path, api.store.installation))
    assert restarted.tick(lambda: True) == 1
    assert restarted.tick(lambda: True) == 0
    posted = report()
    assert posted["posted_minor"] == posted["available_minor"] == posted["earned_minor"] == 125
    assert posted["pending_posting_minor"] == 0
    assert report(MONTH)["earned_minor"] == 125
    assert report(NEXT_WEEK)["earned_minor"] == 0
    (award,) = posted["history"]
    assert award == {
        "event_id": approved.operation_id,
        "cycle_id": cycle,
        "occurrence_id": work,
        "title": "Water plants",
        "amount_minor": 125,
        "performed_at": work_time,
        "verified_at": verified_at,
        "posted_at": clock.value,
        "reverses": None,
        "policy_version": "conserve_total.v1",
    }
    api.user(USER, True)
    other = api.client.get(ROUTE, params=WEEK, headers=CONTEXT).json()
    assert other["available_minor"] == 0 and other["history"] == []

    clock.value = timestamp(5, 18)
    reopened = tasks.reopen(
        "reopen", ReopenTask(work, approved.result.decode()["revision"], cycle, "Review work")
    )
    assert restarted.tick(lambda: True) == 1
    assert restarted.tick(lambda: True) == 0
    api.user(CHILD_USER)
    first = report(limit=1)
    assert first["earned_minor"] == first["posted_minor"] == first["available_minor"] == 0
    assert first["completed_count"] == 1
    (reversal,) = first["history"]
    assert reversal == {
        **award,
        "event_id": reopened.operation_id,
        "amount_minor": -125,
        "posted_at": clock.value,
        "reverses": approved.operation_id,
    }
    token = first["next_cursor"]
    assert report(limit=1, cursor=token)["history"] == [award]
    bad_period = api.client.get(
        ROUTE, params=MONTH | {"limit": 1, "cursor": token}, headers=CHILD_CONTEXT
    )
    assert bad_period.status_code == 422


def test_family_report_reconciles_original_period_after_snapshot_restore(tmp_path):
    from datetime import date

    from test_activation_compatibility import identity_at
    from test_household_commands import Clock
    from test_points_consumer import adult_id, cycle_of
    from test_task_commands import fixture

    from domus.application.family_queries import FamilyQueries
    from domus.application.fixed_materialization import MaintenanceScope
    from domus.domain.calendar_values import CalendarRange
    from domus.infrastructure.owned_storage import open_storage
    from domus.infrastructure.recurrence_time import PinnedRecurrenceTime
    from domus.infrastructure.sqlite_activation import SQLiteActivation
    from domus.infrastructure.sqlite_restoration import SQLiteRestorations
    from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots
    from domus.infrastructure.task_cursor import TaskCursor

    root = tmp_path / "owned"
    root.mkdir(mode=0o700)
    tasks, store, actor, _ = fixture(root)
    identity_at(root, store.installation)
    clock = Clock()
    worker = PointsConsumer(store, store.installation, clock)
    service = FamilyQueries(
        store,
        MaintenanceScope(store.installation, "home"),
        actor.current(),
        TaskCursor(clock, b"x" * 32),
        PinnedRecurrenceTime(),
    )
    period = CalendarRange(date(1970, 1, 1), date(1970, 1, 8))
    task = CreateTask(TaskContent("First work"), overrides=TaskOverrides(point_value_minor=100))
    _, work = resource(tasks.create("work", task))
    owner = adult_id(store, tasks)
    first = tasks.complete("work-done", CompleteTask(work, 1, (owner,), 90))
    assert worker.tick(lambda: True) == 1
    tasks.reopen("reopen", ReopenTask(work, 2, cycle_of(first), "Reopen first cycle"))
    assert worker.tick(lambda: True) == 1
    original = service.report(period, limit=25, cursor=None)
    assert original.earned_minor == original.available_minor == 0
    assert original.completed_count == 1 and original.tracked_count == 0
    assert [item.amount_minor for item in original.history] == [-100, 100]
    archive, prepared = tmp_path / "archive", tmp_path / "prepared"
    snapshot = SQLiteSnapshots(store, archive, store.installation, clock).create("after-reversal")
    tasks.complete("work-again", CompleteTask(work, 3, (owner,), 95))
    assert worker.tick(lambda: True) == 1
    assert service.report(period, limit=25, cursor=None).available_minor == 100
    SQLiteRestorations(store, archive, prepared, store.installation, clock, snapshot).prepare(
        "restore-family"
    )
    assert SQLiteActivation(root, store.installation, clock, prepared).activate().state == "active"
    selected = open_storage(root, "edge")
    try:
        assert replace(worker, store=selected.database).tick(lambda: True) == 0
        assert (
            replace(service, transactions=selected.database).report(period, limit=25, cursor=None)
            == original
        )
    finally:
        selected.close()
