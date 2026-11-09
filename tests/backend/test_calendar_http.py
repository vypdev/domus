"""Ingress and standalone expose the same context-bound calendar read."""

from dataclasses import replace
from datetime import date
from types import SimpleNamespace

import pytest
from test_recurrence_http import CONTEXT, USER, seed_manual
from test_task_http import checked
from test_task_runtime import api as api

from domus.application.fixed_materialization import MaintenanceScope
from domus.application.recurrence_sources import RecurrenceSourceObservations
from domus.application.relative_lifecycle import RelativeLifecycle
from domus.application.relative_materialization import RelativeMaintenance
from domus.application.relative_recurrence import RelativeRecurrencePlanner
from domus.application.relative_recurrence_commands import (
    CreateRelativeTask,
    RelativeRecurrenceCommands,
)
from domus.application.task_requests import CreateTask
from domus.domain.identity import HumanIdentity
from domus.domain.recurrence_rules import NominalDate
from domus.domain.recurrence_time import RelativeInterval, TimePolicy
from domus.domain.task_values import TaskContent
from domus.infrastructure.application_runtime import SecureIdentifiers, SystemClock
from domus.infrastructure.recurrence_time import PinnedRecurrenceTime
from domus.infrastructure.sqlite import SQLiteDatabase

BASE = "/api/v1/tasks/calendar"


def test_calendar_http_requires_current_context_and_closed_range(api):
    api.user(USER, True)
    seed_manual(api)
    params = {"start": "2026-12-01", "end": "2027-01-01", "kind": "due", "limit": 1}
    assert api.client.get(BASE, params=params).status_code == 422
    response = api.client.get(BASE, params=params, headers=CONTEXT)
    assert response.status_code == 200, response.text
    assert response.json() == {
        "period": {"start": "2026-12-01", "end": "2027-01-01"},
        "time_zone": "UTC",
        "entries": [],
        "count": 0,
        "occurrence_count": 0,
        "next_cursor": None,
        "pending": True,
    }
    assert (
        api.client.get(BASE, params=params | {"kind": "unknown"}, headers=CONTEXT).status_code
        == 422
    )
    assert (
        api.client.get(BASE, params=params | {"start": "2026-02-30"}, headers=CONTEXT).status_code
        == 422
    )
    assert (
        api.client.get(BASE, params=params | {"secret": "forged"}, headers=CONTEXT).status_code
        == 422
    )


def test_owner_calendar_preferences_are_private_and_recover_exact_int64(api):
    from domus.domain.identity import Member, MemberStatus, Role

    api.user(USER, True)
    route = BASE + "/preferences"
    assert api.client.get(route).status_code == 422
    assert api.client.get(route, headers=CONTEXT).json() == {"week_start": "monday", "revision": 1}
    with api.store.write() as unit:
        owner = unit.members.by_user("home", USER)
        unit.members.save(
            Member("calendar-other", "home", "b" * 32, Role.ADMINISTRATOR, MemberStatus.ACTIVE, 1),
            0,
        )
        unit.calendar_preferences.connection.execute(
            "UPDATE calendar_preferences SET revision=? WHERE member_id=?",
            (2**53 + 1, owner.member_id),
        )

    requested = {"expected_revision": 2**53 + 1, "week_start": "sunday"}
    headers = api.headers("change-week") | CONTEXT
    for invalid in (
        requested | {"week_start": "tuesday"},
        requested | {"member_id": "calendar-other"},
        requested | {"expected_revision": True},
    ):
        assert api.client.put(route, headers=headers, json=invalid).status_code == 422
    assert (
        api.client.put(
            route, headers=headers | {"Origin": "https://forged.example"}, json=requested
        ).status_code
        == 403
    )
    response = api.client.put(route, headers=headers, json=requested)
    assert response.status_code == 200, response.text
    assert response.json()["result"]["revision"] == 2**53 + 2
    assert api.client.put(route, headers=headers, json=requested).json() == response.json()
    original = route + "/requests/change-week"
    assert api.client.get(original, headers=CONTEXT).json() == response.json()
    assert api.client.get(route, headers=CONTEXT).json() == {
        "week_start": "sunday",
        "revision": 2**53 + 2,
    }
    with api.store.read() as unit:
        assert unit.preferences.get("home", owner.member_id).revision == 1
        assert unit.presentations.get("home", owner.member_id).revision == 1
        audit = unit.audit.entries("home")[-1]
        assert audit.detail.decode() == {"revision": 2**53 + 2}
    api.user("b" * 32, True)
    assert api.client.get(original, headers=CONTEXT).status_code == 403
    other = {"X-Domus-Context": CONTEXT["X-Domus-Context"].replace(USER, "b" * 32)}
    assert api.client.get(original, headers=other).status_code == 404
    assert api.client.get(route, headers=other).json() == {"week_start": "monday", "revision": 1}


def test_calendar_outage_honors_current_permissions_and_original_read_deadline(api):
    from datetime import UTC, datetime

    from test_recurrence_http import BASE as REVIEW_BASE

    from domus.domain.errors import IdentityUnavailable
    from domus.domain.identity import MemberStatus

    api.user(USER, True)
    choice = seed_manual(api)
    with api.store.read() as unit:
        work = unit.tasks.occurrence("home", choice["occurrence_id"])
        definition = work.definition_snapshot.definition_id
    due_at = int(datetime(2026, 12, 12, 14, tzinfo=UTC).timestamp() * 1000)
    added = api.client.post(
        f"/api/v1/tasks/definitions/{definition}/occurrences",
        json={"expected_revision": 0, "due_at": due_at},
        headers=api.headers("add-due"),
    )
    assert added.status_code == 200, added.text
    headers = api.headers("outage-preview") | CONTEXT
    params = {"start": "2026-12-12", "end": "2026-12-13", "kind": "due"}
    first = api.client.get(BASE, params=params, headers=CONTEXT)
    assert first.status_code == 200 and first.json()["count"] == 1
    assert first.json()["entries"][0]["instant_ms"] == due_at
    with api.store.read() as unit:
        owner = unit.members.by_user("home", USER)
        events = unit.outbox.pending()

    api.source.error = IdentityUnavailable("ha_unavailable")
    api.clock.value += 3_599_999
    assert api.client.get(BASE, params=params, headers=CONTEXT).json() == first.json()
    blocked = api.client.post(f"{REVIEW_BASE}/adoption/preview", json=choice, headers=headers)
    assert blocked.status_code == 503
    with api.store.write() as unit:
        suspended = replace(owner, status=MemberStatus.SUSPENDED, revision=owner.revision + 1)
        unit.members.save(suspended, owner.revision)
    revoked = api.client.get(BASE, params=params, headers=CONTEXT)
    assert revoked.status_code == 403 and "Clean the filter" not in revoked.text
    with api.store.write() as unit:
        unit.members.save(replace(owner, revision=suspended.revision + 1), suspended.revision)
    api.clock.value += 1
    expired = api.client.get(BASE, params=params, headers=CONTEXT)
    assert expired.status_code in (401, 503) and "Clean the filter" not in expired.text
    with api.store.read() as unit:
        assert unit.outbox.pending() == events
        assert unit.tasks.occurrence("home", work.occurrence_id) == work


@pytest.mark.parametrize("started", [False, True])
def test_calendar_marks_a_retained_successor_after_source_reopening(api, started):
    api.user(USER, True)
    times = PinnedRecurrenceTime()
    ids = SecureIdentifiers()
    clock = SystemClock()
    admin = SimpleNamespace(current=lambda: HumanIdentity(USER, True, True, False))
    rule = (
        RelativeRecurrenceCommands(api.store, admin, clock, ids, times)
        .create(
            "calendar-relative",
            CreateRelativeTask(
                CreateTask(TaskContent("Inspect the filter")),
                NominalDate(date(1970, 1, 1)),
                RelativeInterval(2),
                TimePolicy("UTC", times.data_identity),
            ),
        )
        .result.decode()
    )
    schedule = rule["schedule_id"]
    scope = MaintenanceScope(api.store.installation, "home")
    source = RecurrenceSourceObservations(api.store, scope)
    lifecycle = RelativeLifecycle(api.store, scope, RelativeRecurrencePlanner(times), clock, ids)
    initial = RelativeMaintenance(api.store, scope, times, clock, ids).initial(schedule)
    parent_path = f"/occurrences/{initial.occurrence_id}"
    member = api.client.get("/api/v1/authorization").json()["member"]["member_id"]
    completed = checked(
        api,
        "post",
        parent_path + "/complete",
        {"expected_revision": 1, "performer_ids": [member], "performed_at": 90},
        "calendar-complete",
    )
    (record,) = source.ingest().items
    successor = lifecycle.consume(schedule, record.event.event_key)
    if started:
        path = f"/occurrences/{successor.occurrence_id}"
        checked(
            api,
            "put",
            path + "/assignment",
            {"expected_revision": 1, "assignee_ids": [member]},
            "calendar-assign",
        )
        checked(
            api,
            "post",
            path + "/transition",
            {"expected_revision": 2, "target": "in_progress"},
            "calendar-start",
        )
    period = {"start": "1970-01-01", "end": "1970-01-05", "timing": "completion_relative"}

    def calendar():
        response = api.client.get(BASE, params=period, headers=CONTEXT)
        assert response.status_code == 200, response.text
        return response.json()["entries"]

    previous = calendar()
    assert all(not row["relative_review_required"] for row in previous)
    reopened = checked(
        api,
        "post",
        parent_path + "/reopen",
        {
            "expected_revision": 2,
            "cycle_id": completed["result"]["cycle"]["cycle_id"],
            "reason": "Inspect the source again",
        },
        "calendar-reopen",
    )
    (change,) = source.ingest().items
    assert change.event.event_id == reopened["operation_id"]
    result = lifecycle.consume(schedule, change.event.event_key)
    assert result.status == ("review" if started else "cancel")
    fresh = SQLiteDatabase(api.store.path, api.store.installation)
    assert (
        replace(lifecycle, transactions=fresh).consume(schedule, change.event.event_key) == result
    )

    before = {
        row["entry_id"] for row in previous if row["occurrence_id"] == successor.occurrence_id
    }
    entries = calendar()
    retained = [row for row in entries if row["occurrence_id"] == successor.occurrence_id]
    assert {row["kind"] for row in retained} == {"due", "planned"}
    assert {row["entry_id"] for row in retained} == before
    assert all(row["relative_review_required"] is started for row in retained)
    assert all(row["state"] == ("in_progress" if started else "cancelled") for row in retained)
    assert all(not row["relative_review_required"] for row in entries if row not in retained)
    with fresh.read() as unit:
        assert unit.receipts.get(result.receipt.command) == result.receipt
        assert len(unit.tasks.cycles("home")) == 1
