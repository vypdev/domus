"""Actual native and standalone task routes use bounded material inputs and live scoped reads."""

from dataclasses import replace
from functools import partial

import pytest
from test_task_http import PREFIX, checked, create
from test_task_material_commands import Inventory
from test_task_runtime import api as api

from domus.composition import tasks
from domus.domain.identity import Permission, PermissionRule
from domus.domain.task_material_values import MaterialPendingReason


@pytest.fixture
def inventory(api, tmp_path, monkeypatch):
    value = Inventory(tmp_path / "fixture-http-inventory.sqlite3")
    value.bindings["binding"] = replace(value.bindings["binding"], precision=2)
    monkeypatch.setattr(
        tasks, "TaskCommands", partial(tasks.TaskCommands, inventory_factory=value.factory)
    )
    return value


def selection(quantity="2", **extra):
    return {"reference_id": "binding", "planned_quantity": quantity, **extra}


def complete(api, receipt, usages, key="complete"):
    member = api.client.get("/api/v1/members").json()["members"][0]["member_id"]
    return api.client.post(
        PREFIX + "/occurrences/" + receipt["result"]["occurrence_id"] + "/complete",
        json={
            "expected_revision": 1,
            "performer_ids": [member],
            "performed_at": 90,
            **usages,
        },
        headers=api.headers(key),
    )


def test_both_http_modes_record_read_and_replay_canonical_materials(api, inventory):
    created = create(api, materials=[selection("0.25")])
    did, oid = created["result"]["definition_id"], created["result"]["occurrence_id"]
    detail = api.client.get(PREFIX + "/occurrences/" + oid).json()
    line = detail["work"]["definition_snapshot"]["materials"][0]
    assert (
        line["planned_quantity"] == "0.25"
        and line["binding"]["product_id"] == inventory.bindings["binding"].product_id
    )
    payload = {"material_usages": [{"line_id": line["line_id"], "quantity": "0.5"}]}
    response = complete(api, created, payload)
    assert response.status_code == 200, response.text
    outcome = response.json()["result"]["materials"][0]
    assert outcome["state"] == "posted" and outcome["quantity"] == "0.5"
    assert outcome["movement_id"] and outcome["action_required"] is None
    assert complete(api, created, payload).json() == response.json()
    changed = complete(api, created, {"material_usages": []})
    assert changed.status_code == 409 and changed.json()["code"] == "idempotency_conflict"
    current = api.client.get(PREFIX + "/occurrences/" + oid).json()
    live = {
        **outcome,
        "confirmed_quantity": "0.5",
        "confirmed_effect_revision": 1,
        "posted_at": current["cycle"]["recorded_at"],
    }
    assert current["materials"] == [live]
    assert current["consumer_delivery"] == "unconfirmed"
    path = PREFIX + "/occurrences/" + oid + "/materials"
    view = api.client.get(path, params={"cycle_id": outcome["cycle_id"]})
    assert view.status_code == 200, view.text
    assert view.json()["materials"] == [live]
    assert len(inventory.settlements) == len(inventory.movements()) == 1
    checked(
        api,
        "post",
        "/occurrences/" + oid + "/reopen",
        {"expected_revision": 2, "cycle_id": outcome["cycle_id"], "reason": "Repeat work"},
        "reopen",
    )
    assert api.client.get(PREFIX + "/occurrences/" + oid).json()["materials"] == []
    old = api.client.get(path, params={"cycle_id": outcome["cycle_id"]}).json()
    assert old["cycle"]["closed_at"] is not None and old["materials"] == [live]
    assert len(inventory.settlements) == 1
    edited = checked(
        api,
        "put",
        "/definitions/" + did,
        {
            "expected_revision": 1,
            "title": "New plan",
            "state": "active",
            "materials": [selection("3")],
        },
        "edit",
    )
    assert edited["result"]["materials"][0]["line_id"] == line["line_id"]
    assert edited["result"]["materials"][0]["planned_quantity"] == "3"
    assert api.client.get(PREFIX + "/occurrences/" + oid).json()["work"]["definition_snapshot"][
        "materials"
    ] == [line]
    checked(
        api,
        "put",
        "/definitions/" + did,
        {"expected_revision": 2, "title": "New plan", "state": "active", "materials": []},
        "clear",
    )
    assert api.client.get(PREFIX + "/definitions/" + did).json()["materials"] == []


@pytest.mark.parametrize(
    "quantity",
    [
        True,
        1,
        1.5,
        None,
        {},
        [],
        "",
        "01",
        "1.0",
        "1e2",
        "-1",
        "+1",
        "0.0000001",
        "1000000000000",
        "１",
        "1\n",
    ],
)
def test_wire_material_quantities_are_strict_before_any_write(api, quantity):
    response = api.client.post(
        PREFIX + "/definitions",
        json={"title": "Work", "materials": [selection(quantity)]},
        headers=api.headers("invalid-quantity"),
    )
    assert response.status_code == 422, response.text
    with api.store.read() as unit:
        assert not unit.tasks.definitions("home") and len(unit.audit.entries("home")) == 1


@pytest.mark.parametrize(
    "values",
    [
        [selection()] * 2,
        [selection()] * 33,
        [selection(product_id="forged")],
        [selection(reference_id="unknown")],
        [selection("0.001")],
    ],
)
def test_selection_identity_precision_and_bounds_cannot_be_forged(api, inventory, values):
    response = api.client.post(
        PREFIX + "/definitions",
        json={"title": "Work", "materials": values},
        headers=api.headers("invalid-selection"),
    )
    assert response.status_code == 422, response.text
    with api.store.read() as unit:
        assert not unit.tasks.definitions("home") and unit.tasks.policy("home") is None


def test_unavailable_inventory_linking_is_explicit_and_atomic(api):
    response = api.client.post(
        PREFIX + "/definitions",
        json={"title": "Work", "materials": [selection()]},
        headers=api.headers("unavailable"),
    )
    assert response.status_code == 503 and response.json()["code"] == "inventory_unavailable"
    with api.store.read() as unit:
        assert not unit.tasks.definitions("home") and unit.tasks.policy("home") is None


@pytest.mark.parametrize(
    "usage,state,reason",
    [
        (None, "pending_recording", "actual_quantity_required"),
        ("0", "not_used", None),
        ("2", "pending_regularization", "insufficient_stock"),
    ],
)
def test_unknown_zero_and_shortage_outcomes_preserve_work_without_a_movement(
    api, inventory, usage, state, reason
):
    inventory.pending = MaterialPendingReason.STOCK_SHORTAGE
    created = create(api, materials=[selection()])
    definition_id = created["result"]["definition_id"]
    line_id = api.client.get(PREFIX + "/definitions/" + definition_id).json()["materials"][0][
        "line_id"
    ]
    payload = (
        {} if usage is None else {"material_usages": [{"line_id": line_id, "quantity": usage}]}
    )
    response = complete(api, created, payload)
    assert response.status_code == 200, response.text
    result = response.json()["result"]
    assert result["state"] == "completed" and result["materials"][0]["state"] == state
    assert result["materials"][0]["pending_reason"] == reason
    assert not inventory.movements()


@pytest.mark.parametrize("field", ["materials", "material_usages"])
def test_omitted_and_null_new_fields_preserve_old_receipts_but_empty_is_distinct(api, field):
    created = create(api)
    if field == "materials":
        assert create(api, materials=None) == created
        response = api.client.post(
            PREFIX + "/definitions",
            json={"title": "Wipe table", "materials": []},
            headers=api.headers("create"),
        )
    else:
        original = complete(api, created, {})
        assert original.status_code == 200
        assert complete(api, created, {"material_usages": None}).json() == original.json()
        response = complete(api, created, {"material_usages": []})
    assert response.status_code == 409 and response.json()["code"] == "idempotency_conflict"


def test_material_read_query_requires_exact_cycle_scope_and_current_read_permission(api, inventory):
    created = create(api, materials=[selection()])
    completed = complete(api, created, {}).json()["result"]
    oid, cid = completed["occurrence_id"], completed["cycle"]["cycle_id"]
    path = PREFIX + "/occurrences/" + oid + "/materials"
    for query in ({}, {"cycle_id": "bad/id"}, {"cycle_id": cid, "actor_id": "forged"}):
        assert api.client.get(path, params=query).status_code == 422
    for query in ([("cycle_id", cid), ("cycle_id", cid)],):
        assert api.client.get(path, params=query).status_code == 422
    missing = api.client.get(path, params={"cycle_id": "missing"})
    assert missing.status_code == 404 and missing.json()["code"] == "task_cycle_missing"
    other = create(api, key="other")
    foreign = api.client.get(
        PREFIX + "/occurrences/" + other["result"]["occurrence_id"] + "/materials",
        params={"cycle_id": cid},
    )
    assert foreign.status_code == 404
    with api.store.write() as unit:
        person = unit.members.list("home")[0]
        unit.members.save(
            replace(person, exceptions=(PermissionRule(Permission.TASKS_READ, False),), revision=2),
            1,
        )
    assert api.client.get(path, params={"cycle_id": cid}).status_code == 403


def test_material_reads_use_original_outage_lease_and_never_establish_write_authority(
    api, inventory
):
    from domus.domain.errors import IdentityUnavailable

    created = create(api, materials=[selection()])
    result = complete(api, created, {}).json()["result"]
    path = PREFIX + "/occurrences/" + result["occurrence_id"] + "/materials"
    params = {"cycle_id": result["cycle"]["cycle_id"]}
    before = api.client.get(path, params=params)
    headers = api.headers("outage-write")
    api.source.error = IdentityUnavailable("ha_unavailable")
    assert api.client.get(path, params=params).json() == before.json()
    assert (
        api.client.post(
            PREFIX + "/definitions", json={"title": "Blocked", "materials": []}, headers=headers
        ).status_code
        == 503
    )
    assert not inventory.movements() and not inventory.settlements
    api.clock.value += 3_600_000
    assert api.client.get(path, params=params).status_code in (401, 503)


def test_link_replay_and_clear_recheck_current_inventory_permission(api, inventory):
    created = create(api, materials=[selection()])
    with api.store.write() as unit:
        member = unit.members.list("home")[0]
        unit.members.save(
            replace(
                member, exceptions=(PermissionRule(Permission.INVENTORY_MANAGE, False),), revision=2
            ),
            1,
        )
    for method, path, body in (
        ("post", "/definitions", {"title": "Wipe table", "materials": [selection()]}),
        (
            "put",
            "/definitions/" + created["result"]["definition_id"],
            {"title": "Wipe table", "state": "active", "expected_revision": 1, "materials": []},
        ),
    ):
        response = getattr(api.client, method)(
            PREFIX + path, json=body, headers=api.headers("create")
        )
        assert response.status_code == 403
    assert len(inventory.resolutions) == 1 and not inventory.movements()


def test_denied_material_consumption_retains_work_and_visible_pending_intent(api, inventory):
    created = create(api, materials=[selection()])
    oid = created["result"]["occurrence_id"]
    line = api.client.get(PREFIX + "/occurrences/" + oid).json()["work"]["definition_snapshot"][
        "materials"
    ][0]
    with api.store.write() as unit:
        member = unit.members.list("home")[0]
        unit.members.save(
            replace(
                member,
                exceptions=(PermissionRule(Permission.TASKS_MATERIAL_USE, False),),
                revision=2,
            ),
            1,
        )
    response = complete(
        api, created, {"material_usages": [{"line_id": line["line_id"], "quantity": "2"}]}
    )
    assert response.status_code == 200, response.text
    outcome = api.client.get(PREFIX + "/occurrences/" + oid).json()["materials"][0]
    assert outcome["state"] == "pending_authorization" and outcome["action_required"]
    assert outcome["confirmed_quantity"] is None and outcome["posted_at"] is None
    assert not inventory.movements() and not inventory.settlements


@pytest.mark.parametrize(
    "kind", ["number", "alias", "duplicate", "unbounded", "foreign", "target", "precision"]
)
def test_invalid_completion_materials_never_write_work_or_inventory(api, inventory, kind):
    created = create(api, materials=[selection()])
    oid = created["result"]["occurrence_id"]
    path = PREFIX + "/occurrences/" + oid
    line = api.client.get(path).json()["work"]["definition_snapshot"]["materials"][0]
    usage = {"line_id": line["line_id"], "quantity": "1"}
    values = {
        "number": [{**usage, "quantity": 1}],
        "alias": [{**usage, "quantity": "1.0"}],
        "duplicate": [usage] * 2,
        "unbounded": [usage] * 33,
        "foreign": [{**usage, "line_id": "other"}],
        "target": [{**usage, "product_id": "other"}],
        "precision": [{**usage, "quantity": "0.001"}],
    }
    response = complete(api, created, {"material_usages": values[kind]})
    assert response.status_code == 422, response.text
    detail = api.client.get(path).json()
    assert detail["work"]["state"] == "available" and detail["cycle"] is None
    assert detail["materials"] == [] and not inventory.movements() and not inventory.settlements


def test_malformed_consumer_result_rolls_back_even_child_sql_under_actual_http(
    api, inventory, monkeypatch
):
    created = create(api, materials=[selection()])
    oid = created["result"]["occurrence_id"]
    path = PREFIX + "/occurrences/" + oid
    line = api.client.get(path).json()["work"]["definition_snapshot"]["materials"][0]
    settle = inventory.settle

    def invalid(connection, request):
        settle(connection, request)
        return {"private": "must-not-leak"}

    monkeypatch.setattr(inventory, "settle", invalid)
    response = complete(
        api, created, {"material_usages": [{"line_id": line["line_id"], "quantity": "2"}]}
    )
    assert response.status_code == 500 and response.json()["code"] == "internal_error"
    assert "must-not-leak" not in response.text
    detail = api.client.get(path).json()
    assert detail["cycle"] is None and detail["materials"] == []
    assert len(inventory.settlements) == 1 and not inventory.movements()
