"""Daily automation planning uses the server's current household time policy."""

from dataclasses import replace
from datetime import datetime
from unittest.mock import Mock

import pytest
from test_automation_drafts import read
from test_automation_execution import denied, initial_draft
from test_automation_preview import CONTEXT, USER, snapshot
from test_task_runtime import api as api

from domus.application.automation_schedule_preview import AutomationSchedulePreview
from domus.application.fixed_materialization import MaintenanceScope
from domus.domain.errors import IntegrationUnavailable, InvalidInput
from domus.domain.fold_policy import FoldPolicy
from domus.domain.identity import HumanIdentity, Permission, PermissionRule
from domus.domain.recurrence_time import MAX_INSTANT_MS, NominalTime, TimePolicy
from domus.infrastructure.application_runtime import SystemClock
from domus.infrastructure.recurrence_time import PinnedRecurrenceTime

PATH = "/api/v1/automation/schedule-preview"


def ms(value):
    return round(datetime.fromisoformat(value).timestamp() * 1000)


def now(monkeypatch, utc):
    value = ms(utc)
    monkeypatch.setattr(SystemClock, "now", lambda _: value)
    return value


def time_policy(api, zone, repeated=FoldPolicy.FIRST):
    with api.store.write() as unit:
        home = unit.households.current()
        unit.households.save(
            replace(home, time_zone=zone, repeated_time=repeated, revision=home.revision + 1),
            home.revision,
        )


def daily(api, time):
    result = read(api, PATH, params={"time": time})
    assert result.status_code == 200, result.text
    return result.json()


@pytest.mark.parametrize(
    ("utc", "first"),
    [
        ("2026-06-10T07:29:59.999Z", "2026-06-10"),
        ("2026-06-10T07:30:00Z", "2026-06-11"),
        ("2026-06-10T18:00:00Z", "2026-06-11"),
    ],
)
def test_exact_five_start_after_now_and_never_write(api, monkeypatch, utc, first):
    initial_draft(api)
    current = now(monkeypatch, utc)
    before = snapshot(api)
    payload = daily(api, "07:30")
    assert payload["time_zone"] == "UTC" and payload["requested_time"] == "07:30"
    entries = payload["items"]
    assert len(entries) == 5 and entries[0]["requested_date"] == first
    assert current < entries[0]["instant_ms"]
    for index, item in enumerate(entries):
        assert item == {
            "requested_date": item["requested_date"],
            "resolved_local": item["requested_date"] + "T07:30:00.000",
            "instant_ms": entries[0]["instant_ms"] + 86_400_000 * index,
            "offset_seconds": 0,
            "resolution": "exact",
        }
    assert snapshot(api) == before


def test_spring_gap_returns_requested_and_committed_wall_times(api, monkeypatch):
    api.user(USER, True)
    time_policy(api, "Europe/Madrid")
    now(monkeypatch, "2026-03-28T13:00:00Z")
    payload = daily(api, "02:30")
    assert payload["time_zone"] == "Europe/Madrid" and payload["requested_time"] == "02:30"
    assert payload["items"][0] == {
        "requested_date": "2026-03-29",
        "resolved_local": "2026-03-29T03:00:00.000",
        "instant_ms": ms("2026-03-29T01:00:00Z"),
        "offset_seconds": 7200,
        "resolution": "gap_first_valid",
    }
    assert payload["items"][1]["resolved_local"] == "2026-03-30T02:30:00.000"
    assert payload["items"][1]["resolution"] == "exact"


@pytest.mark.parametrize(
    ("choice", "utc", "offset", "resolution"),
    [
        (FoldPolicy.FIRST, "2026-10-25T00:30:00Z", 7200, "fold_first"),
        (FoldPolicy.SECOND, "2026-10-25T01:30:00Z", 3600, "fold_second"),
    ],
)
def test_autumn_uses_the_household_choice(api, monkeypatch, choice, utc, offset, resolution):
    api.user(USER, True)
    time_policy(api, "Europe/Madrid", choice)
    now(monkeypatch, "2026-10-24T13:00:00Z")
    assert daily(api, "02:30")["items"][0] == {
        "requested_date": "2026-10-25",
        "resolved_local": "2026-10-25T02:30:00.000",
        "instant_ms": ms(utc),
        "offset_seconds": offset,
        "resolution": resolution,
    }


def test_skipped_local_date_preserves_five_distinct_instants(api, monkeypatch):
    api.user(USER, True)
    time_policy(api, "Pacific/Apia")
    now(monkeypatch, "2011-12-29T12:00:00Z")
    items = daily(api, "00:00")["items"]
    assert [item["requested_date"] for item in items] == [
        "2011-12-30",
        "2012-01-01",
        "2012-01-02",
        "2012-01-03",
        "2012-01-04",
    ]
    assert items[0]["resolved_local"] == "2011-12-31T00:00:00.000"
    assert items[0]["resolution"] == "gap_first_valid"


def test_query_and_current_permission_rejections_are_safe(api):
    api.user(USER, True)
    for query in (
        {},
        {"time": "24:00"},
        {"time": "07:60"},
        {"time": "7:30"},
        {"time": "07:30\n"},
        {"time": "07:30", "time_zone": "UTC"},
        [("time", "12:00"), ("time", "13:00")],
    ):
        denied(read(api, PATH, params=query), 422, "invalid_request")
    foreign = CONTEXT["X-Domus-Context"].replace(USER, "b" * 32)
    result = api.client.get(PATH, params={"time": "02:30"}, headers={"X-Domus-Context": foreign})
    assert result.status_code == 403 and "items" not in result.json()

    with api.store.write() as unit:
        member = unit.members.by_user("home", USER)
        unit.members.save(
            replace(
                member,
                revision=member.revision + 1,
                exceptions=(PermissionRule(Permission.TASKS_CREATE, False),),
            ),
            member.revision,
        )
    denied(read(api, PATH, params={"time": "02:30"}), 403, "permission_denied")


def test_date_bounds_and_failed_resolution_keep_the_preview_finite(api, monkeypatch):
    api.user(USER, True)
    scope = MaintenanceScope(api.store.installation, "home")
    human = HumanIdentity(USER, True, True, False)
    clock = SystemClock()
    times = PinnedRecurrenceTime()
    service = AutomationSchedulePreview(api.store, scope, human, clock, times)
    with pytest.raises(InvalidInput, match="invalid_daily_automation_time"):
        service.daily("midnight")
    with monkeypatch.context() as patch:
        patch.setattr(SystemClock, "now", lambda _: MAX_INSTANT_MS)
        with pytest.raises(InvalidInput, match="recurrence_time_out_of_range"):
            service.daily("00:00")
    now(monkeypatch, "2026-01-01T13:00:00Z")
    stuck = Mock(wraps=times)
    stuck.data_identity = times.data_identity
    stuck.resolve.return_value = times.resolve(
        NominalTime(datetime(2026, 1, 1, 12)), TimePolicy("UTC", times.data_identity)
    )
    with pytest.raises(IntegrationUnavailable, match="daily_automation_times_unavailable"):
        replace(service, times=stuck).daily("12:00")
    assert stuck.resolve.call_count == 7
