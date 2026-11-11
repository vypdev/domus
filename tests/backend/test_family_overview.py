"""Read only the verified member's posted work-period points in both compositions."""

from dataclasses import replace
from types import SimpleNamespace

from test_family_http import CHILD_CONTEXT, CHILD_USER, NEXT_WEEK, WEEK, timestamp
from test_recurrence_http import CONTEXT, USER
from test_task_commands import counts, resource
from test_task_runtime import api as api

from domus.application.points import PointsConsumer
from domus.application.task_commands import TaskCommands
from domus.application.task_requests import CompleteTask, CreateTask, VerifyTask
from domus.domain.identity import (
    HumanIdentity,
    Member,
    MemberStatus,
    Permission,
    PermissionRule,
    Role,
)
from domus.domain.task_values import TaskContent, TaskOverrides, VerificationState
from domus.infrastructure.application_runtime import SecureIdentifiers, SystemClock

ROUTE = "/api/v1/family/overview"


def record(commands, clock, key, member, at, points):
    clock.value = at - 60_000
    _, occurrence = resource(
        commands.create(
            key + "-create",
            CreateTask(
                TaskContent(key.replace("-", " ").capitalize()),
                overrides=TaskOverrides(point_value_minor=points),
            ),
        )
    )
    clock.value = at
    result = commands.complete(key, CompleteTask(occurrence, 1, (member,), at)).result.decode()
    return occurrence, result["revision"], result["cycle"]["cycle_id"]


def approve(commands, clock, key, work, at):
    clock.value = at
    occurrence, revision, cycle = work
    commands.verify(key, VerifyTask(occurrence, revision, cycle, VerificationState.APPROVED))


def test_family_overview_observes_posted_points_and_current_household_week(api, monkeypatch):
    api.user(USER, True)
    with api.store.write() as unit:
        home = unit.households.current()
        unit.households.save(replace(home, time_zone="Europe/Madrid", revision=2), 1)
        owner = unit.members.by_user("home", USER).member_id
        unit.members.save(
            Member("child", "home", CHILD_USER, Role.RESTRICTED, MemberStatus.ACTIVE, 1), 0
        )
    observation = SimpleNamespace(value=timestamp(4, 10))
    monkeypatch.setattr(SystemClock, "now", lambda self: observation.value)
    clock = SimpleNamespace(value=0)
    clock.now = lambda: clock.value
    actor = SimpleNamespace(current=lambda: HumanIdentity(USER, True, True, False))
    commands = TaskCommands(api.store, actor, clock, SecureIdentifiers())
    worker = PointsConsumer(api.store, api.store.installation, clock)

    def overview(headers=CHILD_CONTEXT):
        result = api.client.get(ROUTE, headers=headers)
        assert result.status_code == 200, result.text
        assert result.headers["cache-control"] == "no-store"
        return result.json()

    assert overview(CONTEXT) == {"period": NEXT_WEEK, "earned_minor": 0, "completed_count": 0}
    sunday = record(commands, clock, "sunday-work", "child", timestamp(31, 21, 50), 125)
    approve(commands, clock, "late-approval", sunday, timestamp(31, 22, 5))
    worker.tick(lambda: True)
    current = record(commands, clock, "current-work", "child", timestamp(2, 10), 175)
    approve(commands, clock, "current-approval", current, timestamp(2, 10, 30))
    record(commands, clock, "another-member", owner, timestamp(2, 11), 900)
    worker.tick(lambda: True)
    future = record(commands, clock, "future-week", "child", timestamp(8, 10), 500)
    approve(commands, clock, "future-approval", future, timestamp(8, 10, 30))
    worker.tick(lambda: True)
    record(commands, clock, "awaiting-verification", "child", timestamp(3, 9), 225)
    approved = record(commands, clock, "awaiting-posting", "child", timestamp(3, 10), 325)
    approve(commands, clock, "queued-award", approved, timestamp(3, 10, 30))

    assert overview(CONTEXT) == {"period": NEXT_WEEK, "earned_minor": 900, "completed_count": 1}
    api.user(CHILD_USER)
    original = counts(api.store)
    expected = {"period": NEXT_WEEK, "earned_minor": 175, "completed_count": 3}
    assert overview() == expected
    assert overview() == expected
    report = api.client.get("/api/v1/family", headers=CHILD_CONTEXT, params=NEXT_WEEK)
    assert report.status_code == 200, report.text
    assert report.json()["earned_minor"] == expected["earned_minor"]
    assert report.json()["completed_count"] == expected["completed_count"]
    assert report.json()["pending_verification_minor"] == 225
    assert report.json()["pending_posting_minor"] == 325

    observation.value = timestamp(31, 21, 59)
    assert overview() == {"period": WEEK, "earned_minor": 125, "completed_count": 1}
    observation.value = timestamp(31, 22)
    assert overview() == expected
    observation.value = timestamp(7, 22)
    assert overview() == {
        "period": {"start": "2026-06-08", "end": "2026-06-15"},
        "earned_minor": 500,
        "completed_count": 1,
    }
    assert counts(api.store) == original


def test_family_overview_rejects_unverified_or_revoked_scope(api):
    api.user(USER, True)
    assert api.client.get(ROUTE).status_code == 422
    assert api.client.get(ROUTE, headers={"X-Domus-Context": "v1:forged"}).status_code == 403
    assert api.client.get(ROUTE, headers=CONTEXT, params={"member_id": "other"}).status_code == 422
    with api.store.write() as unit:
        viewer = Member("child", "home", CHILD_USER, Role.RESTRICTED, MemberStatus.ACTIVE, 1)
        unit.members.save(viewer, 0)
    api.user(CHILD_USER)
    assert api.client.get(ROUTE, headers=CHILD_CONTEXT).status_code == 200
    for revision, permission in enumerate((Permission.TASKS_READ, Permission.HOUSEHOLD_READ), 2):
        with api.store.write() as unit:
            unit.members.save(
                replace(viewer, revision=revision, exceptions=(PermissionRule(permission, False),)),
                revision - 1,
            )
        denied = api.client.get(ROUTE, headers=CHILD_CONTEXT)
        assert denied.status_code == 403
        assert not {"period", "earned_minor", "completed_count"} & denied.json().keys()
