"""Prove automation preview is bounded, current and read-only in both runtimes."""

import sqlite3
from contextlib import closing
from dataclasses import replace

import pytest
from test_inventory_catalog_http import VIEWER, post, register
from test_recurrence_http import CONTEXT, USER
from test_rewards_http import member_context
from test_task_runtime import api as api

from domus.domain.automation import (
    MAX_CONDITION_DEPTH,
    MAX_RULE_NODES,
    AutomationRule,
    ConditionGroup,
    NegatedCondition,
    StockCondition,
    simulate,
)
from domus.domain.errors import InvalidInput
from domus.domain.identity import Member, MemberStatus, Permission, PermissionRule, Role
from domus.domain.inventory import EffectKind, InventoryEffect, stock_units
from domus.domain.task_material_values import MaterialQuantity
from domus.domain.task_values import TaskContent

BASE = "/api/v1/automation"
TITLE = "Buy more tea"
ACTION = {"kind": "task.create", "title": TITLE}
RULE = {"version": 1, "trigger": {"kind": "manual"}, "condition": None, "action": ACTION}


def preview(api, headers, **changes):
    return api.client.post(BASE + "/preview", headers=headers, json=RULE | changes)


def snapshot(api):
    # Include complete rows, so an update to an existing effect also fails the assertion.
    tables = (
        "task_definitions",
        "task_occurrences",
        "receipts",
        "audit",
        "outbox",
        "inventory_materials",
        "inventory_movements",
        "inventory_effects",
        "points_task_receipts",
    )
    with closing(sqlite3.connect(api.store.path)) as connection:
        return tuple(connection.execute(f"SELECT * FROM {table}").fetchall() for table in tables)


def leaf(product_id):
    return {"kind": "stock_below_minimum", "product_id": product_id}


def decision(path, kind, matched, product_id=None):
    return {"path": path, "kind": kind, "matched": matched, "product_id": product_id}


def test_protected_preview_uses_current_authorized_stock_without_effects(api):
    api.user(USER, True)
    headers = api.headers() | CONTEXT
    headers.pop("Idempotency-Key")
    assert api.client.get(BASE + "/preview-access", headers=CONTEXT).json() == {
        "household_id": "home"
    }
    assert api.client.get(BASE + "/preview-access").status_code == 422
    assert preview(api, api.headers()).status_code == 422
    assert preview(api, headers | {"X-Domus-Context": "v1:forged"}).status_code == 403
    assert preview(api, headers | {"Origin": "https://wrong.example"}).status_code == 403
    assert preview(api, headers | {"X-CSRF-Token": "wrong"}).status_code == 403

    before = snapshot(api)
    baseline = {
        "version": 1,
        "trigger": "manual",
        "task_title": TITLE,
        "would_create": True,
        "conditions": [],
    }
    assert preview(api, headers).json() == baseline
    assert preview(api, headers).json() == baseline
    assert snapshot(api) == before

    product = register(api, "tea", "Tea", "piece")
    other = register(api, "coffee", "Coffee", "piece")
    policy = {"product_id": product, "minimum": "2", "target": "4", "expected_revision": "0"}
    assert post(api, "minimum", "configure-replenishment", **policy).status_code == 200
    before = snapshot(api)
    tree = {
        "kind": "all",
        "children": [
            {"kind": "any", "children": [leaf(other), leaf(product)]},
            {"kind": "not", "child": leaf(other)},
        ],
    }
    assert preview(api, headers, condition=tree).json() == baseline | {
        "conditions": [
            decision([0, 0], "stock_below_minimum", False, other),
            decision([0, 1], "stock_below_minimum", True, product),
            decision([0], "any", True),
            decision([1, 0], "stock_below_minimum", False, other),
            decision([1], "not", True),
            decision([], "all", True),
        ]
    }
    unknown = preview(api, headers, condition=leaf("other-household-product"))
    assert unknown.status_code == 404 and unknown.json()["code"] == "inventory_product_missing"
    assert snapshot(api) == before

    assert post(api, "stock", "intake", product_id=product, quantity="2").status_code == 200
    before = snapshot(api)
    assert preview(api, headers, condition=leaf(product)).json() == baseline | {
        "would_create": False,
        "conditions": [decision([], "stock_below_minimum", False, product)],
    }
    assert snapshot(api) == before

    with api.store.read() as unit:
        reference = unit.inventory.product("home", product).reference_id
    task = api.client.post(
        "/api/v1/tasks/definitions",
        headers=api.headers("work-with-reservation"),
        json={
            "title": "Tea tasting",
            "expected_revision": 0,
            "materials": [{"reference_id": reference, "planned_quantity": "1"}],
        },
    )
    assert task.status_code == 200, task.text
    work_id = task.json()["result"]["occurrence_id"]
    with api.store.write() as unit:
        work = unit.tasks.occurrence("home", work_id)
        (line,) = work.definition_snapshot.materials
        unit.inventory.add_effect(
            InventoryEffect(
                "home",
                "reserved-tea",
                EffectKind.RESERVATION,
                reference,
                work_id,
                work_id,
                line.line_id,
                stock_units(MaterialQuantity("1")),
            )
        )
    before = snapshot(api)
    assert preview(api, headers, condition=leaf(product)).json() == baseline | {
        "conditions": [decision([], "stock_below_minimum", True, product)],
    }
    assert snapshot(api) == before

    with api.store.write() as unit:
        member = unit.members.by_user("home", USER)
        unit.members.save(
            replace(
                member,
                exceptions=(PermissionRule(Permission.TASKS_CREATE, False),),
                revision=member.revision + 1,
            ),
            member.revision,
        )
        unit.members.save(Member("viewer", "home", VIEWER, Role.VIEWER, MemberStatus.ACTIVE, 1), 0)
    before = snapshot(api)
    assert api.client.get(BASE + "/preview-access", headers=CONTEXT).status_code == 403
    assert preview(api, headers, condition=leaf("unknown")).status_code == 403
    api.user(VIEWER)
    assert (
        api.client.get(BASE + "/preview-access", headers=member_context(VIEWER)).status_code == 403
    )
    assert preview(api, api.headers() | member_context(VIEWER)).status_code == 403
    assert snapshot(api) == before


def test_preview_enforces_closed_types_and_exact_bounds(api):
    api.user(USER, True)
    headers = api.headers() | CONTEXT
    product = register(api, "tea", "Tea", "piece")
    for changes in (
        {"version": 2},
        {"version": True},
        {"version": "1"},
        {"trigger": {"kind": "scheduled"}},
        {"trigger": {"kind": "manual", "script": "run"}},
        {"action": {"kind": "notify", "title": TITLE}},
        {"action": ACTION | {"code": "run()"}},
        {"action": ACTION | {"title": "á" * 161}},
        {"household_id": "elsewhere"},
        {"condition": {"kind": "not", "child": None}},
        {"condition": {"kind": "all", "children": []}},
        {"condition": leaf("bad id")},
        {"condition": {"kind": "expression", "source": "return true"}},
    ):
        response = preview(api, headers, **changes)
        assert (response.status_code, response.json()["code"]) == (422, "invalid_request"), (
            response.text
        )
    assert (
        preview(api, headers, action=ACTION | {"title": " \t"}).json()["code"]
        == "invalid_task_text"
    )
    exact_title = "🧹" * 160
    assert (
        preview(api, headers, action=ACTION | {"title": exact_title}).json()["task_title"]
        == exact_title
    )

    condition = leaf(product)
    for _ in range(MAX_CONDITION_DEPTH - 1):
        condition = {"kind": "not", "child": condition}
    result = preview(api, headers, condition=condition).json()
    assert result["would_create"] is True and len(result["conditions"]) == MAX_CONDITION_DEPTH
    too_deep = preview(api, headers, condition={"kind": "not", "child": condition})
    assert too_deep.json()["code"] == "automation_condition_depth"
    children = [leaf(product)] * (MAX_RULE_NODES - 3)
    result = preview(api, headers, condition={"kind": "any", "children": children}).json()
    assert result["would_create"] is False and len(result["conditions"]) == MAX_RULE_NODES - 2
    too_many = preview(
        api, headers, condition={"kind": "any", "children": [*children, leaf(product)]}
    )
    assert too_many.json()["code"] == "automation_rule_node_limit"


def test_domain_rejects_invalid_in_memory_rules_and_simulates_unconditional_action():
    content = TaskContent(TITLE)
    for args in (
        (True, "manual", None, content),
        (2, "manual", None, content),
        (1, "schedule", None, content),
        (1, "manual", None, TITLE),
    ):
        with pytest.raises(InvalidInput, match="invalid_automation_rule"):
            AutomationRule(*args)
    for kind, children in (("bad", (StockCondition("tea"),)), ("all", []), ("any", ())):
        with pytest.raises(InvalidInput, match="invalid_automation_condition"):
            ConditionGroup(kind, children)
    with pytest.raises(InvalidInput, match="invalid_automation_condition"):
        AutomationRule(1, "manual", NegatedCondition(None), content)
    result = simulate(
        AutomationRule(1, "manual", None, content), lambda _: pytest.fail("read stock")
    )
    assert result.task_title == TITLE and result.would_create and result.conditions == ()
