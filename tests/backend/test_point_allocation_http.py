"""Both compositions apply current allocation authority and preserve frozen pending awards."""

import pytest
from test_recurrence_http import CONTEXT, USER
from test_task_http import create
from test_task_runtime import api as api

from domus.application.points import PointsConsumer
from domus.domain.identity import Member, MemberStatus, Role
from domus.infrastructure.application_runtime import SystemClock

ALLOCATION = "/api/v1/family/allocation"
TASKS = "/api/v1/tasks"
CHILD = "b" * 32
CHILD_CONTEXT = {"X-Domus-Context": CONTEXT["X-Domus-Context"].replace(USER, CHILD)}


def test_created_fractional_base_flows_through_preview_and_posted_award(api):
    api.user(USER, True)
    configured = api.client.put(
        ALLOCATION,
        json={"expected_revision": 0, "policy": {"mode": "conserve_total", "precision": 2}},
        headers=api.headers("precise-policy") | CONTEXT,
    )
    assert configured.status_code == 200, configured.text
    created = create(api, overrides={"point_value_minor": 225})["result"]
    member = api.client.get("/api/v1/authorization").json()["member"]["member_id"]
    occurrence = created["occurrence_id"]
    work = {"expected_revision": created["revision"], "performer_ids": [member]}
    preview = api.client.post(
        ALLOCATION + "/preview",
        json=work | {"occurrence_id": occurrence},
        headers=api.headers("base-preview") | CONTEXT,
    )
    assert preview.status_code == 200, preview.text
    expected = preview.json()
    assert expected["allocation"]["base_minor"] == expected["actual_total"] == 225
    clock = SystemClock()
    completed = api.client.post(
        TASKS + "/occurrences/" + occurrence + "/complete",
        json=work
        | {"performed_at": clock.now(), "allocation_fingerprint": expected["fingerprint"]},
        headers=api.headers("base-complete") | CONTEXT,
    )
    assert completed.status_code == 200, completed.text
    cycle_id = completed.json()["result"]["cycle"]["cycle_id"]
    worker = PointsConsumer(api.store, api.store.installation, clock)
    assert worker.tick(lambda: True) == 1 and worker.tick(lambda: True) == 0
    (award,) = worker.ledger("home", cycle_id)
    assert dict(award.shares) == {member: 225}


@pytest.mark.parametrize(
    "mode", ["conserve_total", "full_per_participant", "equal_share", "manual"]
)
def test_task_creation_obeys_current_base_precision_without_changing_allocation(api, mode):
    api.user(USER, True)
    policy = {"mode": mode, "precision": 0}
    if mode == "equal_share":
        policy["rounding"] = "floor"
    settings = api.client.put(
        ALLOCATION,
        json={"expected_revision": 0, "policy": policy},
        headers=api.headers("whole-policy") | CONTEXT,
    )
    assert settings.status_code == 200, settings.text
    body = {"title": "Check the filter", "overrides": {"point_value_minor": 225}}
    definitions = TASKS + "/definitions"
    headers = api.headers("fractional-base") | CONTEXT
    reply = api.client.post(definitions, json=body, headers=headers)
    if mode in ("conserve_total", "full_per_participant"):
        assert reply.status_code == 422 and reply.json()["code"] == "points_precision_two_required"
        assert api.client.get(definitions).json()["items"] == []
        assert api.client.get(TASKS + "/requests/task.create/fractional-base").status_code == 404
        body["overrides"]["point_value_minor"] = 200
        reply = api.client.post(definitions, json=body, headers=headers)
    assert reply.status_code == 200, reply.text
    assert reply.json()["result"]["point_value_minor"] == body["overrides"]["point_value_minor"]
    assert (
        api.client.get(ALLOCATION, headers=CONTEXT).json()["household"]["policy"]["precision"] == 0
    )


def test_allocation_policy_and_override_remain_frozen_through_approval(api):
    api.user(USER, True)
    with api.store.write() as unit:
        owner = unit.members.by_user("home", USER).member_id
        for person, ha_user in (("child", CHILD), ("other", "c" * 32)):
            unit.members.save(
                Member(person, "home", ha_user, Role.RESTRICTED, MemberStatus.ACTIVE, 1), 0
            )
    record = create(api, overrides={"point_value_minor": 1000})["result"]
    definition_id, occurrence_id = record["definition_id"], record["occurrence_id"]

    def command(method, url, body, key):
        response = getattr(api.client, method)(url, json=body, headers=api.headers(key) | CONTEXT)
        assert response.status_code == 200, response.text
        return response.json()

    def settings():
        response = api.client.get(
            ALLOCATION, headers=CONTEXT, params={"definition_id": definition_id}
        )
        assert response.status_code == 200
        return response.json()

    assert settings() == {"household": None, "override": None}
    assert api.client.get(ALLOCATION + "/requests/missing", headers=CONTEXT).status_code == 404
    assert (
        api.client.get(ALLOCATION, headers=CONTEXT, params={"definition_id": "missing"}).status_code
        == 403
    )
    full = {"mode": "full_per_participant", "precision": 0}
    configured = command("put", ALLOCATION, {"expected_revision": 0, "policy": full}, "full")
    assert (
        command("put", ALLOCATION, {"expected_revision": 0, "policy": full}, "full") == configured
    )
    assert api.client.get(ALLOCATION + "/requests/full", headers=CONTEXT).json() == configured
    bad = api.client.put(
        ALLOCATION,
        json={"expected_revision": 0, "policy": full},
        headers=api.headers("stale") | CONTEXT,
    )
    assert bad.status_code == 409
    ceiling = {"mode": "equal_share", "precision": 0, "rounding": "ceil"}
    override = {"definition_id": definition_id, "expected_revision": 0, "policy": ceiling}
    command("put", ALLOCATION, override, "ceiling")
    assert settings()["override"] == {"revision": 1, "policy": ceiling}

    performers = [owner, "child", "other"]
    selected = {"expected_revision": record["revision"], "performer_ids": performers}
    draft = {"occurrence_id": occurrence_id, **selected}
    first = command("post", ALLOCATION + "/preview", draft, "preview-ceiling")
    assert first["actual_total"] == 1200

    floor = ceiling | {"rounding": "floor"}
    command("put", ALLOCATION, override | {"expected_revision": 1, "policy": floor}, "floor")
    clock = SystemClock()
    completion = TASKS + "/occurrences/" + occurrence_id + "/complete"
    performed_at = clock.now()
    complete_body = {**selected, "performed_at": performed_at}
    rejected = api.client.post(
        completion,
        json=complete_body | {"allocation_fingerprint": first["fingerprint"]},
        headers=api.headers("stale-preview") | CONTEXT,
    )
    assert rejected.status_code == 409
    saved_preview = command("post", ALLOCATION + "/preview", draft, "preview-floor")
    assert saved_preview["actual_total"] == 900
    done_body = complete_body | {"allocation_fingerprint": saved_preview["fingerprint"]}
    done = command("post", completion, done_body, "complete")["result"]
    assert done["cycle"]["verification"] == "pending"
    assert command("post", completion, done_body, "complete")["result"] == done
    cycle_id = done["cycle"]["cycle_id"]

    command("put", ALLOCATION, override | {"expected_revision": 2, "policy": None}, "clear")
    assert settings()["override"] == {"policy": None, "revision": 3}
    assert settings()["household"]["policy"]["mode"] == "full_per_participant"
    with api.store.read() as unit:
        assert unit.point_allocations.snapshot("home", cycle_id).policy_revision == 2
        assert unit.points.ledger("home", cycle_id) == ()

    occurrence = TASKS + "/occurrences/" + occurrence_id
    approved = command(
        "post",
        occurrence + "/verify",
        {"expected_revision": done["revision"], "cycle_id": cycle_id, "decision": "approved"},
        "approve",
    )["result"]
    worker = PointsConsumer(api.store, api.store.installation, clock)
    assert worker.tick(lambda: True) == 2 and worker.tick(lambda: True) == 0
    (award,) = worker.ledger("home", cycle_id)
    assert award.policy_version == "allocation.v2"
    assert dict(award.shares) == dict.fromkeys(performers, 300)
    reopened = command(
        "post",
        occurrence + "/reopen",
        {"expected_revision": approved["revision"], "cycle_id": cycle_id, "reason": "Review work"},
        "reopen",
    )["result"]
    assert worker.tick(lambda: True) == 1
    _, reversal = worker.ledger("home", cycle_id)
    assert reversal.policy_version == award.policy_version
    assert reversal.reverses == award.event_id
    assert dict(reversal.shares) == dict.fromkeys(performers, -300)
    inherited = command(
        "post",
        ALLOCATION + "/preview",
        draft | {"expected_revision": reopened["revision"]},
        "inherited",
    )
    assert inherited["actual_total"] == 3000 and not inherited["allocation"]["task_override"]


def test_manual_amounts_require_current_points_authority(api):
    api.user(USER, True)
    with api.store.write() as unit:
        unit.members.save(
            Member("child", "home", CHILD, Role.RESTRICTED, MemberStatus.ACTIVE, 1), 0
        )
    record = create(api)["result"]
    policy = {"mode": "manual", "precision": 2}
    update = {"expected_revision": 0, "policy": policy}
    configure = api.client.put(ALLOCATION, json=update, headers=api.headers("manual") | CONTEXT)
    assert configure.status_code == 200, configure.text
    occurrence = record["occurrence_id"]
    detail_url = TASKS + "/occurrences/" + occurrence
    managed = api.client.get(detail_url, headers=CONTEXT)
    assert managed.status_code == 200
    assert managed.json()["completion_points"] == "manual"
    assert "complete" in managed.json()["allowed_actions"]
    amounts = [{"member_id": "child", "amount_minor": 125}]
    completion = {
        "expected_revision": record["revision"],
        "performer_ids": ["child"],
        "manual_shares": amounts,
    }
    preview = ALLOCATION + "/preview"
    api.user(CHILD)
    claim = api.client.post(
        detail_url + "/claim",
        json={"expected_revision": record["revision"]},
        headers=api.headers("claim") | CHILD_CONTEXT,
    )
    assert claim.status_code == 200, claim.text
    completion["expected_revision"] = claim.json()["result"]["revision"]
    restricted = api.client.get(detail_url, headers=CHILD_CONTEXT)
    assert restricted.status_code == 200
    assert restricted.json()["completion_points"] == "manager_required"
    assert "complete" not in restricted.json()["allowed_actions"]
    denied = api.client.put(ALLOCATION, json=update, headers=api.headers("edit") | CHILD_CONTEXT)
    assert denied.status_code == 403
    assert api.client.get(ALLOCATION, headers=CHILD_CONTEXT).status_code == 403
    denied = api.client.post(
        preview,
        json=completion | {"occurrence_id": occurrence},
        headers=api.headers("preview") | CHILD_CONTEXT,
    )
    assert denied.status_code == 403
    body = completion | {"performed_at": SystemClock().now()}
    route = TASKS + "/occurrences/" + occurrence + "/complete"
    denied = api.client.post(route, json=body, headers=api.headers("complete") | CHILD_CONTEXT)
    assert denied.status_code == 403
    api.user(USER, True)
    review = api.client.post(
        preview,
        json=completion | {"occurrence_id": occurrence},
        headers=api.headers("manual-preview") | CONTEXT,
    )
    assert review.status_code == 200, review.text
    assert review.json()["allocation"]["shares"] == [["child", 125]]
    accepted = api.client.post(
        route,
        json=body | {"allocation_fingerprint": review.json()["fingerprint"]},
        headers=api.headers("complete") | CONTEXT,
    )
    assert accepted.status_code == 200, accepted.text
    cycle_id = accepted.json()["result"]["cycle"]["cycle_id"]
    with api.store.read() as unit:
        allocation = unit.point_allocations.snapshot("home", cycle_id).allocation
    assert allocation.shares == (("child", 125),)


def test_policy_and_preview_rejections_leave_no_award_or_settings(api):
    api.user(USER, True)
    record = create(api, overrides={"point_value_minor": 125})["result"]
    context = api.headers("rejected") | CONTEXT
    policy = {"mode": "conserve_total", "precision": 0}
    for edit, status in (
        ({"expected_revision": 0, "policy": None}, 422),
        ({"expected_revision": 2**63 - 1, "policy": policy}, 422),
        ({"expected_revision": 0, "policy": policy, "definition_id": "missing"}, 403),
    ):
        assert api.client.put(ALLOCATION, json=edit, headers=context).status_code == status
    with api.store.read() as unit:
        actor = unit.members.by_user("home", USER)
        assert unit.point_allocations.setting("home", None) is None
    settings = api.client.get(ALLOCATION, headers=CONTEXT)
    assert settings.json() == {"household": None, "override": None}
    preview = ALLOCATION + "/preview"
    work = record["occurrence_id"]
    draft = {"occurrence_id": work, "expected_revision": 1, "performer_ids": [actor.member_id]}
    for change, status in (
        ({"occurrence_id": "missing"}, 403),
        ({"performer_ids": ["missing"]}, 403),
        ({"performer_ids": [actor.member_id, actor.member_id]}, 422),
        ({"expected_revision": 2}, 409),
    ):
        assert api.client.post(preview, json=draft | change, headers=context).status_code == status
    legacy = api.client.post(preview, json=draft, headers=context).json()["allocation"]
    assert legacy["precision"] == 2 and legacy["policy_revision"] == 0
    saved = api.client.put(
        ALLOCATION, json={"expected_revision": 0, "policy": policy}, headers=context
    )
    assert saved.status_code == 200, saved.text
    incompatible = api.client.post(preview, json=draft, headers=context)
    assert incompatible.status_code == 422
    assert incompatible.json()["code"] == "points_precision_two_required"
    assert (
        api.client.post(
            f"{TASKS}/occurrences/{work}/complete",
            json={key: value for key, value in draft.items() if key != "occurrence_id"}
            | {"performed_at": SystemClock().now(), "allocation_policy": policy},
            headers=context,
        ).status_code
        == 422
    )
    with api.store.read() as unit:
        assert unit.tasks.cycles("home") == ()
        assert unit.points.member_totals("home", actor.member_id, 0, 1) == (0, 0)


def test_family_limits_pending_details_and_counts_all_frozen_awards(api):
    from datetime import UTC, datetime, timedelta

    api.user(USER, True)
    with api.store.read() as unit:
        owner = unit.members.by_user("home", USER).member_id
    performed = SystemClock().now()
    for index in range(5):
        task = create(
            api, f"create-{index}", title=f"Pending {index}", overrides={"point_value_minor": 100}
        )["result"]
        recorded = api.client.post(
            TASKS + f"/occurrences/{task['occurrence_id']}/complete",
            json={
                "performer_ids": [owner],
                "expected_revision": 1,
                "performed_at": performed - 5 + index,
            },
            headers=api.headers(f"complete-{index}") | CONTEXT,
        )
        assert recorded.status_code == 200, recorded.text
    day = datetime.fromtimestamp(performed / 1000, UTC).date()
    response = api.client.get(
        "/api/v1/family",
        headers=CONTEXT,
        params={"start": day - timedelta(days=1), "end": day + timedelta(days=1)},
    )
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["pending_count"] == 5 and report["pending_posting_minor"] == 500
    assert [entry["title"] for entry in report["pending"]] == [
        "Pending 4",
        "Pending 3",
        "Pending 2",
        "Pending 1",
    ]
    assert all(entry["allocation"]["shares"] == [[owner, 100]] for entry in report["pending"])
