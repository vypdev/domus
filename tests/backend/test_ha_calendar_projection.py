"""Home Assistant wire data has the same identities and authority as the calendar."""

from dataclasses import replace
from datetime import date, datetime

import pytest
from test_recurrence_creation import request
from test_recurrence_http import CONTEXT, USER
from test_task_runtime import api as api

from domus.application.fixed_materialization import FixedMaintenance, MaintenanceScope
from domus.application.fixed_recurrence import FixedRecurrencePlanner
from domus.application.recurrence_commands import RecurrenceCommands
from domus.domain.errors import IntegrationUnavailable
from domus.domain.identity import HumanIdentity
from domus.domain.nominal_recurrence import CalendarNominalExpansion
from domus.domain.recurrence_rules import NominalDate
from domus.domain.recurrence_time import NominalTime
from domus.infrastructure.application_runtime import SecureIdentifiers, SystemClock
from domus.infrastructure.recurrence_time import PinnedRecurrenceTime
from domus.infrastructure.sqlite_calendar import SQLiteCalendar

BASE = "/api/v1/tasks/calendar"


def seed(api, *, timed):
    class Actor:
        def current(self):
            return HumanIdentity(USER, True, True, False)

    planner = FixedRecurrencePlanner(CalendarNominalExpansion(), PinnedRecurrenceTime())
    clock, identifiers = SystemClock(), SecureIdentifiers()
    service = RecurrenceCommands(api.store, Actor(), clock, identifiers, planner)
    spec = request(timed=timed)
    result = service.create_fixed(
        f"seed-{timed}", replace(spec, pattern=replace(spec.pattern, count=1))
    )
    maintenance = FixedMaintenance(
        api.store, MaintenanceScope(api.store.installation, "home"), planner, clock, identifiers
    )
    before = NominalTime(datetime(2026, 3, 30)) if timed else NominalDate(date(2026, 3, 30))
    schedule = result.result.decode()["schedule_id"]
    maintenance.step(schedule, before)
    return schedule


def test_ha_projection_keeps_uids_offsets_and_date_only_markers_through_retry(api, monkeypatch):
    api.user(USER, True)
    seed(api, timed=True)
    seed(api, timed=False)
    params = {"start": "2026-03-29", "end": "2026-03-30", "kind": "planned", "limit": 1}
    url = BASE + "/home-assistant"
    assert api.client.get(url, params=params).status_code == 422
    first = api.client.get(url, params=params, headers=CONTEXT)
    assert first.status_code == 200, first.text
    data = first.json()
    assert api.client.get(url, params=params, headers=CONTEXT).json()["events"] == data["events"]
    second_params = params | {"cursor": data["next_cursor"]}
    second = api.client.get(url, params=second_params, headers=CONTEXT).json()
    assert data["external_sync"] == second["external_sync"] == "disabled"
    assert data["count"] == second["count"] == 2
    first_ui = api.client.get(BASE, params=params, headers=CONTEXT).json()
    second_ui = api.client.get(BASE, params=second_params, headers=CONTEXT).json()
    assert [e["uid"] for e in data["events"] + second["events"]] == [
        e["entry_id"] for e in first_ui["entries"] + second_ui["entries"]
    ]
    assert {(e["start"], e["all_day"]) for e in data["events"] + second["events"]} == {
        ("2026-03-29", True),
        ("2026-03-29T03:00:00+02:00", False),
    }

    def unavailable(*_args, **_kwargs):
        raise IntegrationUnavailable("recurrence_time_source_invalid")

    monkeypatch.setattr(SQLiteCalendar, "page", unavailable)
    failed = api.client.get(url, params=params, headers=CONTEXT)
    assert failed.status_code == 503
    assert "events" not in failed.json()


@pytest.mark.parametrize(
    "facts",
    [
        {"local_date": None},
        {"local_time": None},
        {"local_time": "bad"},
        {"resolved_local": "2026-04-02T00:00:00"},
    ],
)
def test_projection_rejects_inconsistent_temporal_facts(facts):
    from domus.application.calendar_queries import CalendarEntry, CalendarPage
    from domus.application.ha_calendar_projection import ha_calendar_projection
    from domus.domain.calendar_values import CalendarKind, CalendarRange, CalendarTiming
    from domus.domain.errors import StorageFailure
    from domus.domain.task_values import OccurrenceState, Priority

    day = date(2026, 3, 29)
    entry = CalendarEntry(
        "due:task",
        CalendarKind.DUE,
        CalendarTiming.MANUAL,
        "task",
        "Filter",
        OccurrenceState.AVAILABLE,
        Priority.NORMAL,
        (),
        (),
        None,
        None,
        day,
        "03:00:00",
        1774746000000,
    )
    with pytest.raises(StorageFailure, match="invalid_calendar_projection"):
        ha_calendar_projection(
            CalendarPage(
                CalendarRange(day, date(2026, 3, 30)),
                "Europe/Madrid",
                (replace(entry, **facts),),
                1,
                None,
                False,
            )
        )
