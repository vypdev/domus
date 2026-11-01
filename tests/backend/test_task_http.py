"""Both real compositions exercise task wire DTOs and existing authenticated boundaries."""

import pytest
from test_task_runtime import api as api

PREFIX = "/api/v1/tasks"


def create(api, key="create", **values):
    response = api.client.post(
        PREFIX + "/definitions", json={"title": "Wipe table", **values}, headers=api.headers(key)
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_title_only_create_detail_history_and_own_operation_replay(api):
    receipt = create(api)
    result = receipt["result"]
    assert result["state"] == "available" and result["revision"] == 1
    assert create(api) == receipt
    definitions = api.client.get(PREFIX + "/definitions").json()["items"]
    assert len(definitions) == 1 and definitions[0]["title"] == "Wipe table"
    detail = api.client.get(PREFIX + "/occurrences/" + result["occurrence_id"])
    assert detail.status_code == 200, detail.text
    assert detail.json()["work"]["definition_snapshot"]["content"]["title"] == "Wipe table"
    assert "complete" in detail.json()["allowed_actions"]
    own = api.client.get(PREFIX + "/operations/" + receipt["operation_id"])
    assert own.status_code == 200 and own.json()["result"] == result
    assert own.json()["delivery"] == "pending"
    history = api.client.get(PREFIX + "/occurrences/" + result["occurrence_id"] + "/history")
    assert history.status_code == 200 and len(history.json()["items"]) == 1
    assert "ha_user_id" not in history.text and "payload_fingerprint" not in history.text


@pytest.mark.parametrize(
    "fields",
    [
        {"actor_id": "forged"},
        {"household_id": "other"},
        {"material_lines": []},
        {"expected_revision": True},
        {"title": ""},
        {"tags": ["duplicate", "duplicate"]},
        {"state": "paused"},
        {"overrides": {"claim_allowed": "false"}},
    ],
)
def test_invalid_or_unsupported_creation_never_partially_writes(api, fields):
    response = api.client.post(
        PREFIX + "/definitions", json={"title": "Work", **fields}, headers=api.headers("invalid")
    )
    assert response.status_code == 422, response.text
    with api.store.read() as unit:
        assert not unit.tasks.definitions("home") and len(unit.audit.entries("home")) == 1


def checked(api, method, path, body, key):
    response = getattr(api.client, method)(PREFIX + path, json=body, headers=api.headers(key))
    assert response.status_code == 200, response.text
    return response.json()


def test_edit_assignment_dependencies_progress_completion_verification_and_reopening(api):
    policy = checked(api, "put", "/policy", {"expected_revision": 0, "rules": {}}, "policy")
    assert policy["result"]["revision"] == 1
    checked(
        api,
        "put",
        "/policy",
        {
            "expected_revision": 1,
            "rules": {"verification": "authorized_adult", "dependency_gate": "performed"},
        },
        "policy-update",
    )
    first = create(
        api,
        overrides={
            "point_value_minor": 1000,
            "eligible_roles": ["administrator", "adult", "restricted"],
        },
    )
    did, oid = first["result"]["definition_id"], first["result"]["occurrence_id"]
    definition = api.client.get(PREFIX + "/definitions/" + did).json()
    assert definition["overrides"]["point_value_minor"] == 1000
    updated = checked(
        api,
        "put",
        "/definitions/" + did,
        {
            "expected_revision": 1,
            "title": "Revised",
            "description": "Details",
            "priority": "high",
            "tags": ["daily"],
            "state": "active",
        },
        "edit",
    )
    assert updated["result"]["overrides"]["point_value_minor"] == 1000
    reset = checked(
        api,
        "put",
        "/definitions/" + did,
        {"expected_revision": 2, "title": "Revised", "state": "active", "overrides": {}},
        "reset",
    )
    assert reset["result"]["overrides"]["point_value_minor"] is None
    other = checked(api, "post", "/definitions/" + did + "/occurrences", {}, "another")
    assert other["result"]["definition_revision"] == 3
    prerequisite = other["result"]["occurrence_id"]
    member = api.client.get("/api/v1/members").json()["members"][0]["member_id"]
    checked(
        api,
        "put",
        "/occurrences/" + oid + "/assignment",
        {"expected_revision": 1, "assignee_ids": [member]},
        "assign",
    )
    checked(
        api,
        "put",
        "/occurrences/" + oid + "/dependencies",
        {"expected_revision": 2, "prerequisite_ids": [prerequisite]},
        "dependencies",
    )
    rows = api.client.get(
        PREFIX + "/occurrences",
        params={"assignee_id": member, "state": "assigned", "definition_id": did},
    ).json()["items"]
    assert len(rows) == 1 and rows[0]["occurrence_id"] == oid
    checked(
        api,
        "post",
        "/occurrences/" + oid + "/transition",
        {"expected_revision": 3, "target": "in_progress"},
        "start",
    )
    blocked = api.client.post(
        PREFIX + "/occurrences/" + oid + "/complete",
        json={"expected_revision": 4, "performer_ids": [member], "performed_at": 90},
        headers=api.headers("premature"),
    )
    assert blocked.status_code == 409 and blocked.json()["code"] == "task_dependencies_incomplete"
    checked(
        api,
        "post",
        "/occurrences/" + prerequisite + "/complete",
        {"expected_revision": 1, "performer_ids": [member], "performed_at": 90},
        "prerequisite-done",
    )
    payload = {"expected_revision": 4, "performer_ids": [member], "performed_at": 90}
    completed = checked(api, "post", "/occurrences/" + oid + "/complete", payload, "complete")
    assert (
        checked(api, "post", "/occurrences/" + oid + "/complete", payload, "complete") == completed
    )
    cycle = completed["result"]["cycle"]
    assert (
        cycle["verification"] == "pending"
        and completed["result"]["consumer_delivery"] == "unconfirmed"
    )
    verified = checked(
        api,
        "post",
        "/occurrences/" + oid + "/verify",
        {"expected_revision": 5, "cycle_id": cycle["cycle_id"], "decision": "approved"},
        "approve",
    )
    assert verified["result"]["cycle"]["verification"] == "approved"
    reopened = checked(
        api,
        "post",
        "/occurrences/" + oid + "/reopen",
        {"expected_revision": 6, "cycle_id": cycle["cycle_id"], "reason": "Repeat correctly"},
        "reopen",
    )
    assert (
        reopened["result"]["state"] == "assigned"
        and reopened["result"]["cycle"]["closed_at"] is not None
    )
    assert api.client.get(PREFIX + "/occurrences/" + oid).json()["cycle"] is None
    history = api.client.get(
        PREFIX + "/occurrences/" + oid + "/history", params={"limit": "2"}
    ).json()
    assert len(history["items"]) == 2 and history["next_cursor"]
    assert (
        api.client.get(
            PREFIX + "/occurrences/" + oid + "/history",
            params={"limit": "2", "cursor": history["next_cursor"]},
        ).status_code
        == 200
    )
    with api.store.write() as unit:
        unit.outbox.acknowledge(completed["operation_id"])
    own = api.client.get(PREFIX + "/operations/" + completed["operation_id"]).json()
    assert own["delivery"] == "delivered" and own["result"]["consumer_delivery"] == "unconfirmed"


def test_restricted_self_claim_still_requires_current_adult_verification(api):
    from domus.domain.identity import Member, MemberStatus, Role

    receipt = create(api)
    oid = receipt["result"]["occurrence_id"]
    with api.store.write() as unit:
        unit.members.save(
            Member("child", "home", "b" * 32, Role.RESTRICTED, MemberStatus.ACTIVE, 1), 0
        )
    api.user("b" * 32)
    claimed = checked(
        api, "post", "/occurrences/" + oid + "/claim", {"expected_revision": 1}, "claim"
    )
    assert claimed["result"]["assignee_ids"] == ["child"]
    completed = checked(
        api,
        "post",
        "/occurrences/" + oid + "/complete",
        {"expected_revision": 2, "performer_ids": ["child"], "performed_at": 90},
        "child-done",
    )
    cycle = completed["result"]["cycle"]
    assert cycle["verification"] == "pending"
    verify = {"expected_revision": 3, "cycle_id": cycle["cycle_id"], "decision": "approved"}
    assert (
        api.client.post(
            PREFIX + "/occurrences/" + oid + "/verify",
            json=verify,
            headers=api.headers("self-approval"),
        ).status_code
        == 403
    )
    assert api.client.get(PREFIX + "/operations/" + receipt["operation_id"]).status_code == 404
    api.user("a" * 32, True)
    approved = checked(api, "post", "/occurrences/" + oid + "/verify", verify, "adult-approval")
    assert approved["result"]["cycle"]["verified_by"]["role"] == "administrator"


@pytest.mark.parametrize(
    "kind", ["origin", "csrf", "duplicate_csrf", "duplicate_key", "missing_key", "forged_identity"]
)
def test_task_writes_keep_the_existing_boundary_and_durable_state(api, kind):
    headers = api.headers("boundary")
    if kind == "origin":
        headers["Origin"] = "https://foreign.invalid"
    if kind == "csrf":
        headers["X-CSRF-Token"] = "f" * 64
    if kind == "missing_key":
        headers.pop("Idempotency-Key")
    if kind == "forged_identity":
        headers["X-Remote-User-Id"] = "f" * 32
    values = list(headers.items())
    if kind == "duplicate_csrf":
        values.append(("X-CSRF-Token", headers["X-CSRF-Token"]))
    if kind == "duplicate_key":
        values.append(("Idempotency-Key", headers["Idempotency-Key"]))
    result = api.client.post(PREFIX + "/definitions", json={"title": "Rejected"}, headers=values)
    assert result.status_code in (401, 403, 422), result.text
    with api.store.read() as unit:
        assert not unit.tasks.definitions("home") and len(unit.audit.entries("home")) == 1


@pytest.mark.parametrize(
    "query",
    [
        "limit=0",
        "limit=101",
        "limit=1.0",
        "limit=true",
        "limit=01",
        "limit=1&limit=2",
        "unknown=1",
        "cursor=",
        "cursor=" + "x" * 513,
        "unknown=" + "x" * 8192,
    ],
)
def test_task_query_bounds_apply_in_both_compositions(api, query):
    result = api.client.get(PREFIX + "/definitions?" + query)
    assert result.status_code == 422, result.text


def test_signed_pages_survive_authorized_reads_and_current_revocation_blocks_later_pages(api):
    from dataclasses import replace

    from domus.domain.identity import Permission, PermissionRule

    for i in range(3):
        create(api, str(i))
    first = api.client.get(PREFIX + "/definitions", params={"limit": "1", "state": "active"})
    assert first.status_code == 200, first.text
    cursor = first.json()["next_cursor"]
    second = api.client.get(
        PREFIX + "/definitions", params={"limit": "1", "state": "active", "cursor": cursor}
    )
    assert second.status_code == 200 and second.json()["items"][0] != first.json()["items"][0]
    assert (
        api.client.get(PREFIX + "/definitions", params={"limit": "2", "cursor": cursor}).status_code
        == 422
    )
    with api.store.write() as unit:
        member = unit.members.list("home")[0]
        unit.members.save(
            replace(member, exceptions=(PermissionRule(Permission.TASKS_READ, False),), revision=2),
            1,
        )
    assert (
        api.client.get(
            PREFIX + "/definitions", params={"limit": "1", "state": "active", "cursor": cursor}
        ).status_code
        == 403
    )


def test_ha_outage_keeps_only_original_lease_reads_and_never_accepts_a_task_write(api):
    from domus.domain.errors import IdentityUnavailable

    receipt = create(api)
    headers = api.headers("outage")
    api.source.error = IdentityUnavailable("ha_unavailable")
    oid = receipt["result"]["occurrence_id"]
    for path in (
        "/policy",
        "/definitions",
        "/occurrences/" + oid,
        "/occurrences/" + oid + "/history",
        "/operations/" + receipt["operation_id"],
    ):
        assert api.client.get(PREFIX + path).status_code == 200
    assert (
        api.client.post(
            PREFIX + "/definitions", json={"title": "Blocked"}, headers=headers
        ).status_code
        == 503
    )
    api.clock.value += 3_600_000
    assert api.client.get(PREFIX + "/definitions").status_code in (401, 503)


@pytest.mark.parametrize(
    "body",
    [
        '{"title":"A","title":"B"}',
        '{"title":"A","overrides":{"claim_allowed":true,"claim_allowed":false}}',
        '{"title":"A","expected_revision":NaN}',
        '[{"title":"A"}]',
    ],
)
def test_duplicate_json_keys_and_non_objects_are_rejected_before_task_effects(api, body):
    headers = {**api.headers("json"), "Content-Type": "application/json"}
    result = api.client.post(PREFIX + "/definitions", content=body, headers=headers)
    assert result.status_code == 422
    assert api.client.get(PREFIX + "/definitions").json()["items"] == []


def test_query_model_accepts_real_integers_but_rejects_coerced_internal_values():
    from pydantic import ValidationError

    from domus.entrypoints.task_dto import DefinitionsQuery

    assert DefinitionsQuery.model_validate({"limit": 25}).limit == 25
    for value in (True, 1.5, 0, 101):
        with pytest.raises(ValidationError):
            DefinitionsQuery.model_validate({"limit": value})


def test_unknown_material_line_cannot_silently_complete_work(api):
    receipt = create(api)
    oid = receipt["result"]["occurrence_id"]
    member = api.client.get("/api/v1/members").json()["members"][0]["member_id"]
    result = api.client.post(
        PREFIX + "/occurrences/" + oid + "/complete",
        json={
            "expected_revision": 1,
            "performer_ids": [member],
            "performed_at": 90,
            "material_usages": [{"line_id": "unwired", "quantity": "1"}],
        },
        headers=api.headers("materials"),
    )
    assert result.status_code == 422 and result.json()["code"] == "invalid_material_reference"
    detail = api.client.get(PREFIX + "/occurrences/" + oid).json()
    assert detail["work"]["state"] == "available" and detail["cycle"] is None


@pytest.mark.parametrize("kind", ["body_size", "read_body", "content_type", "title_control"])
def test_task_routes_retain_bounded_json_and_domain_text_guards(api, kind):
    headers = api.headers("bounded")
    if kind == "body_size":
        result = api.client.post(
            PREFIX + "/definitions",
            content=b"x" * 65_537,
            headers={**headers, "Content-Type": "application/json"},
        )
        assert result.status_code == 413
    elif kind == "read_body":
        result = api.client.request("GET", PREFIX + "/definitions", content="{}")
        assert result.status_code == 422
    elif kind == "content_type":
        result = api.client.post(
            PREFIX + "/definitions",
            content='{"title":"Work"}',
            headers={**headers, "Content-Type": "text/plain"},
        )
        assert result.status_code == 422
    else:
        result = api.client.post(
            PREFIX + "/definitions", json={"title": "Bad\u0000title"}, headers=headers
        )
        assert result.status_code == 422 and result.json()["code"] == "invalid_task_text"
    with api.store.read() as unit:
        assert not unit.tasks.definitions("home") and len(unit.audit.entries("home")) == 1


def test_explicit_ha_rejection_removes_task_read_authority_instead_of_granting_outage_grace(api):
    from domus.domain.errors import IdentityRejected, IdentityUnavailable

    create(api)
    api.source.error = IdentityRejected("ha_subject_rejected")
    assert api.client.get(PREFIX + "/definitions").status_code == 401
    api.source.error = IdentityUnavailable("ha_unavailable")
    assert api.client.get(PREFIX + "/definitions").status_code in (401, 503)


def test_lost_response_after_task_commit_recovers_only_the_original_effect(api, monkeypatch):
    from domus.entrypoints import task_http

    original = task_http._receipt

    def fail(_):
        raise RuntimeError("private-response-detail")

    monkeypatch.setattr(task_http, "_receipt", fail)
    failed = api.client.post(
        PREFIX + "/definitions", json={"title": "Wipe table"}, headers=api.headers("uncertain")
    )
    assert failed.status_code == 500 and "private-response-detail" not in failed.text
    with api.store.read() as unit:
        assert len(unit.tasks.definitions("home")) == 1 and len(unit.audit.entries("home")) == 2
    monkeypatch.setattr(task_http, "_receipt", original)
    recovered = create(api, "uncertain")
    assert recovered["state"] == "committed"
    with api.store.read() as unit:
        assert len(unit.tasks.definitions("home")) == 1 and len(unit.audit.entries("home")) == 2


def test_offline_activation_preserves_historical_receipt_in_both_http_compositions(
    api,
):
    from fastapi.testclient import TestClient
    from test_activation_compatibility import identity_at
    from test_ingress_sessions import HEADERS

    from domus.composition import ingress, server
    from domus.infrastructure.application_runtime import SystemClock
    from domus.infrastructure.sqlite_activation import SQLiteActivation
    from domus.infrastructure.sqlite_restoration import SQLiteRestorations
    from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots

    created = create(api)
    oid = created["result"]["occurrence_id"]
    member = api.client.get("/api/v1/members").json()["members"][0]["member_id"]
    root = api.store.path.parent
    archive, target = (
        root.with_name(root.name + "-archives"),
        root.with_name(root.name + "-restored"),
    )
    identity_at(root, api.store.installation)
    clock = SystemClock()
    snapshot = SQLiteSnapshots(api.store, archive, api.store.installation, clock).create(
        "before-work"
    )
    payload = {"expected_revision": 1, "performer_ids": [member], "performed_at": 90}
    completed = checked(
        api, "post", "/occurrences/" + oid + "/complete", payload, "historical-work"
    )
    with api.store.write() as unit:
        unit.outbox.acknowledge(completed["operation_id"])
    api.runtime.close()
    SQLiteRestorations(api.store, archive, target, api.store.installation, clock, snapshot).prepare(
        "restore-http"
    )
    assert (
        SQLiteActivation(root, api.store.installation, clock, target).activate().state == "active"
    )
    if api.mode == "native":
        runtime = ingress.create_owned_runtime(
            "private-supervisor-token", "edge", root, (api.origin,)
        )
        client = TestClient(
            runtime.app,
            base_url=api.origin,
            client=("172.30.32.2", 12000),
            headers=dict(HEADERS),
            raise_server_exceptions=False,
        )
    else:
        runtime = server.create_owned_runtime("http://ha.local", api.origin, "edge", root)
        runtime.identity.sign_in("code", "v" * 43, "restored-session", 100, 3_600_100)
        name = runtime.app.openapi()["components"]["securitySchemes"]["DomusSession"]["name"]
        client = TestClient(runtime.app, base_url=api.origin, raise_server_exceptions=False)
        client.cookies.set(name, "restored-session")
    try:
        restored = client.get(PREFIX + "/operations/" + completed["operation_id"])
        assert restored.status_code == 200, restored.text
        value = restored.json()
        assert value["state"] == "historical" and value["delivery"] == "suppressed"
        assert value["result"] == completed["result"] and value["archived_by"] == "restore-http"
        assert client.get(PREFIX + "/occurrences/" + oid).json()["cycle"] is None
        csrf = client.get("/api/v1/auth/csrf").json()["csrf_token"]
        replay = client.post(
            PREFIX + "/occurrences/" + oid + "/complete",
            json=payload,
            headers={
                "Origin": api.origin,
                "X-CSRF-Token": csrf,
                "Idempotency-Key": "historical-work",
            },
        )
        assert replay.status_code == 200 and replay.json()["state"] == "historical"
        assert client.get(PREFIX + "/occurrences/" + oid).json()["cycle"] is None
        assert client.get(PREFIX + "/occurrences/" + oid + "/history").json()["items"][-1][
            "historical"
        ]
    finally:
        client.close()
        runtime.close()
