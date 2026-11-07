"""Ingress and standalone expose the same context-bound calendar read."""

from test_recurrence_http import CONTEXT, USER, seed_manual
from test_task_runtime import api as api

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
