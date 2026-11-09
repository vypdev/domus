"""Exercise protected calendar limits, member facts and cursor scope in both deployments."""

from dataclasses import replace
from datetime import UTC, datetime, time, timedelta
from types import SimpleNamespace

from test_recurrence_http import CONTEXT, USER, seed_manual
from test_task_http import checked
from test_task_runtime import api as api

from domus.application.fixed_materialization import FixedMaintenance, MaintenanceScope
from domus.application.fixed_recurrence import FixedRecurrencePlanner
from domus.application.recurrence_commands import CreateFixedTask, RecurrenceCommands
from domus.application.task_requests import CreateTask
from domus.domain.errors import IdentityUnavailable
from domus.domain.identity import HumanIdentity, Member, MemberStatus, Role
from domus.domain.nominal_recurrence import CalendarNominalExpansion
from domus.domain.recurrence_rules import FixedPattern, Frequency, NominalDate
from domus.domain.recurrence_time import TimePolicy
from domus.domain.task_values import TaskContent
from domus.infrastructure.application_runtime import SecureIdentifiers, SystemClock
from domus.infrastructure.recurrence_time import PinnedRecurrenceTime

BASE = "/api/v1/tasks/calendar"
OTHER = "b" * 32


def test_excessive_calendar_range_returns_the_actual_supported_limit(api):
    api.user(USER, True)
    params = {"start": "2026-01-01", "end": "2027-01-03", "kind": "planned"}
    response = api.client.get(BASE, params=params, headers=CONTEXT)
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_calendar_range"
    assert response.json()["action_required"] == (
        "Choose valid calendar dates up to 366 days apart. The end date is exclusive."
    )
    accepted = api.client.get(BASE, params=params | {"end": "2027-01-02"}, headers=CONTEXT)
    assert accepted.status_code == 200, accepted.text


def test_late_completion_keeps_saturday_anchor_and_member_filters_distinguish_history(api):
    api.user(USER, True)
    times, clock, ids = PinnedRecurrenceTime(), SystemClock(), SecureIdentifiers()
    planner = FixedRecurrencePlanner(CalendarNominalExpansion(), times)
    actor = SimpleNamespace(current=lambda: HumanIdentity(USER, True, True, False))
    scope = MaintenanceScope(api.store.installation, "home")
    creation = RecurrenceCommands(api.store, actor, clock, ids, planner)
    today = datetime.fromtimestamp(clock.now() / 1000, UTC).date()
    monday = today - timedelta(days=today.weekday() + 7)
    first_date = monday - timedelta(days=2)
    second_date = first_date + timedelta(days=7)
    receipt = creation.create_fixed(
        "weekly",
        CreateFixedTask(
            CreateTask(TaskContent("Inspect the filter")),
            FixedPattern(NominalDate(first_date), Frequency.WEEKLY, count=2),
            TimePolicy("UTC", times.data_identity),
        ),
    )
    rule = receipt.result.decode()["schedule_id"]
    runner = FixedMaintenance(api.store, scope, planner, clock, ids)
    saturday = runner.step(rule, NominalDate(monday + timedelta(days=1)))
    assert saturday.status == "created"
    with api.store.write() as unit:
        owner = unit.members.by_user("home", USER)
        for member_id, user in (("assignee", OTHER), ("performer", "c" * 32)):
            unit.members.save(
                Member(member_id, "home", user, Role.RESTRICTED, MemberStatus.ACTIVE, 1), 0
            )
    path = f"/occurrences/{saturday.occurrence_id}"
    checked(
        api,
        "put",
        path + "/assignment",
        {"expected_revision": 1, "assignee_ids": ["assignee"]},
        "assign",
    )
    performed_at = int(datetime.combine(monday, time(12), UTC).timestamp() * 1000)
    completion = checked(
        api,
        "post",
        path + "/complete",
        {"expected_revision": 2, "performer_ids": ["performer"], "performed_at": performed_at},
        "performed-on-monday",
    )
    checked(
        api,
        "post",
        path + "/verify",
        {
            "expected_revision": 3,
            "cycle_id": completion["result"]["cycle"]["cycle_id"],
            "decision": "approved",
        },
        "approve",
    )
    next_saturday = runner.step(rule, NominalDate(second_date + timedelta(days=1)))
    assert next_saturday.status == "created"
    params = {
        "start": first_date.isoformat(),
        "end": (today + timedelta(days=2)).isoformat(),
        "timing": "fixed_calendar",
    }

    def entries(**filters):
        response = api.client.get(BASE, params=params | filters, headers=CONTEXT)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["count"] == len(body["entries"])
        return body["entries"]

    assignee = entries(member_id="assignee")
    assert {(row["kind"], row["local_date"]) for row in assignee} == {
        ("planned", first_date.isoformat()),
        ("due", first_date.isoformat()),
    }
    (actual,) = entries(member_id="performer")
    assert actual["kind"] == "performed" and actual["local_date"] == monday.isoformat()
    (approval,) = entries(member_id=owner.member_id, kind="approval")
    assert (
        approval["verification"] == "approved"
        and approval["occurrence_id"] == saturday.occurrence_id
    )
    assert {(row["local_date"], row["occurrence_id"]) for row in entries(kind="planned")} == {
        (first_date.isoformat(), saturday.occurrence_id),
        (second_date.isoformat(), next_saturday.occurrence_id),
    }
    outsider = api.client.get(BASE, params=params | {"member_id": "foreign"}, headers=CONTEXT)
    assert outsider.status_code == 403 and "Inspect the filter" not in outsider.text
    api.user(OTHER)
    member_context = {"X-Domus-Context": CONTEXT["X-Domus-Context"].replace(USER, OTHER)}
    filtered = params | {"member_id": "assignee"}
    response = api.client.get(BASE, params=filtered, headers=member_context)
    assert response.status_code == 200 and response.json()["entries"] == assignee
    with api.store.write() as unit:
        member = unit.members.get("home", "assignee")
        unit.members.save(
            replace(member, status=MemberStatus.SUSPENDED, revision=member.revision + 1),
            member.revision,
        )
    denied = api.client.get(BASE, params=filtered, headers=member_context)
    assert denied.status_code == 403 and "Inspect the filter" not in denied.text


def test_an_outage_lease_does_not_authorize_another_members_cursor(api):
    api.user(USER, True)
    choice = seed_manual(api)
    with api.store.write() as unit:
        definition = unit.tasks.occurrence("home", choice["occurrence_id"]).definition_snapshot
        unit.members.save(
            Member("other", "home", OTHER, Role.ADMINISTRATOR, MemberStatus.ACTIVE, 1), 0
        )
    for index in (1, 2):
        checked(
            api,
            "post",
            f"/definitions/{definition.definition_id}/occurrences",
            {"expected_revision": 0, "due_at": index},
            f"due-{index}",
        )
    params = {"start": "1970-01-01", "end": "1970-01-02", "kind": "due", "limit": 1}
    owner = api.client.get(BASE, params=params, headers=CONTEXT)
    assert owner.status_code == 200, owner.text
    cursor = owner.json()["next_cursor"]
    assert cursor is not None

    api.user(OTHER, True)
    other_context = {"X-Domus-Context": CONTEXT["X-Domus-Context"].replace(USER, OTHER)}
    first = api.client.get(BASE, params=params, headers=other_context)
    assert first.status_code == 200, first.text
    own = first.json()["next_cursor"]
    assert own is not None and own != cursor
    before = api.store.path.read_bytes()
    api.source.error = IdentityUnavailable("ha_unavailable")
    api.clock.value += 3_599_999
    denied = api.client.get(BASE, params=params | {"cursor": cursor}, headers=other_context)
    assert denied.status_code == 422 and denied.json()["code"] == "invalid_task_cursor"
    assert "Clean the filter" not in denied.text
    next_page = api.client.get(BASE, params=params | {"cursor": own}, headers=other_context)
    assert next_page.status_code == 200, next_page.text
    assert next_page.json()["next_cursor"] is None
    api.clock.value += 1
    expired = api.client.get(BASE, params=params | {"cursor": own}, headers=other_context)
    assert expired.status_code in (401, 503) and "Clean the filter" not in expired.text
    assert api.store.path.read_bytes() == before
