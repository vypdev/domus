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
