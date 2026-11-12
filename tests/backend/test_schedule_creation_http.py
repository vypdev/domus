"""Exercise the protected scheduled creation routes against the real household database."""

from dataclasses import replace

import pytest
from test_recurrence_http import CONTEXT, USER
from test_task_runtime import api as api

from domus.application.schedule_creation_policy import schedule_creation_policy
from domus.application.task_queries import TaskQueries
from domus.domain.errors import Forbidden
from domus.domain.identity import HumanIdentity, Member, MemberStatus, Role
from domus.infrastructure.task_cursor import TaskCursor

TASKS = "/api/v1/tasks"
CREATION = TASKS + "/recurrence/creation"


def test_scheduled_creation_service_rejects_foreign_policy_and_noncreation_action(api):
    with api.store.read() as unit, pytest.raises(Forbidden):
        schedule_creation_policy(unit, "outside", "tzdata:fixture")
    query = TaskQueries(
        api.store,
        HumanIdentity(USER, True, True, False),
        TaskCursor(api.clock, b"k" * 32),
        api.store.installation,
    )
    with pytest.raises(Forbidden):
        query.original_schedule("task.create", "legacy-request")


@pytest.mark.parametrize("kind", ["fixed", "relative"])
def test_atomic_scheduled_creation_and_original_recovery(api, kind):
    api.user(USER, True)
    workspace = api.client.get(TASKS + "/access")
    assert workspace.status_code == 200, workspace.text
    policy = workspace.json()["schedule_policy"]
    payload = {
        "task": {"title": "Recurring inspection", "overrides": {"point_value_minor": 225}},
        "start": {"kind": "date", "local": "2027-01-02"},
        "policy": policy,
    } | (
        {"rrule": "FREQ=WEEKLY;BYDAY=SA;COUNT=2"}
        if kind == "fixed"
        else {"interval_days": 15, "visibility": "at_verification"}
    )
    path = CREATION + "/" + kind
    key = "scheduled-create"
    original = CREATION + f"/requests/recurrence.{kind}.create/{key}"
    headers = api.headers(key) | CONTEXT
    assert api.client.post(path, json=payload, headers=api.headers(key)).status_code == 422
    assert api.client.get(original, headers=CONTEXT).status_code == 404
    invalid = {"rrule": "FREQ=DAILY;BYSECOND=30"} if kind == "fixed" else {"interval_days": 0}
    assert api.client.post(path, json=payload | invalid, headers=headers).status_code == 422
    forged = payload | {"policy": policy | {"revision": policy["revision"] + 1}}
    assert api.client.post(path, json=forged, headers=headers).status_code == 409
    allocation = "/api/v1/family/allocation"
    for revision, precision in ((0, 0), (1, 2)):
        configured = api.client.put(
            allocation,
            json={
                "expected_revision": revision,
                "policy": {"mode": "conserve_total", "precision": precision},
            },
            headers=api.headers(f"policy-{precision}") | CONTEXT,
        )
        assert configured.status_code == 200, configured.text
        if precision == 0:
            rejected = api.client.post(path, json=payload, headers=headers)
            assert rejected.status_code == 422
            assert rejected.json()["code"] == "points_precision_two_required"
            assert api.client.get(original, headers=CONTEXT).status_code == 404
    assert api.client.get(TASKS + "/definitions").json()["items"] == []

    committed = api.client.post(path, json=payload, headers=headers)
    assert committed.status_code == 200, committed.text
    receipt = committed.json()
    assert receipt["result"]["processing"] == "pending"
    assert receipt["result"]["first_occurrence_id"] is None
    assert receipt["result"]["point_value_minor"] == 225
    assert api.client.get(TASKS + "/occurrences").json()["items"] == []
    with api.store.write() as unit:
        home = unit.households.get("home")
        unit.households.save(replace(home, revision=home.revision + 1), home.revision)
        unit.members.save(
            Member("child", "home", "b" * 32, Role.RESTRICTED, MemberStatus.ACTIVE, 1), 0
        )
    assert api.client.post(path, json=payload, headers=headers).json() == receipt
    recovered = api.client.get(original, headers=CONTEXT)
    assert recovered.status_code == 200, recovered.text
    assert recovered.json() == receipt | {
        "action": f"recurrence.{kind}.create",
        "command_key": key,
        "delivery": "pending",
    }
    with api.store.write() as unit:
        assert unit.outbox.acknowledge(receipt["operation_id"])
    assert api.client.get(original, headers=CONTEXT).json()["delivery"] == "delivered"
    changed = payload | {"task": {"title": "Different inspection"}}
    assert api.client.post(path, json=changed, headers=headers).status_code == 409
    assert len(api.client.get(TASKS + "/definitions").json()["items"]) == 1
    api.user("b" * 32)
    child_context = {"X-Domus-Context": CONTEXT["X-Domus-Context"].replace(USER, "b" * 32)}
    assert api.client.get(TASKS + "/access").json()["schedule_policy"] is None
    assert api.client.get(original, headers=child_context).status_code == 403
    assert (
        api.client.post(
            path, json=payload, headers=api.headers("child") | child_context
        ).status_code
        == 403
    )
