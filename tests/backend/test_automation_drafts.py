"""Qualify typed drafts and durable command recovery in both HTTP compositions."""

import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from threading import Barrier

import pytest
from test_automation_preview import ACTION, CONTEXT, RULE, USER, leaf, preview
from test_inventory_catalog_http import post, register
from test_task_runtime import api as api

from domus.domain.automation import (
    MAX_CONDITION_DEPTH,
    AutomationRule,
    Condition,
    ConditionGroup,
    NegatedCondition,
    StockCondition,
)
from domus.domain.errors import InvalidInput
from domus.domain.identity import MAX_REVISION, MemberStatus, Permission, PermissionRule
from domus.domain.storage import JsonDocument
from domus.domain.task_values import TaskContent

DRAFTS = "/api/v1/automation/drafts"


@pytest.mark.parametrize(
    "condition",
    [
        None,
        StockCondition("tea"),
        ConditionGroup(
            "all",
            (
                ConditionGroup("any", (StockCondition("coffee"),)),
                NegatedCondition(StockCondition("tea")),
            ),
        ),
    ],
)
def test_draft_rule_document_round_trips_the_exact_version_one_definition(
    condition: Condition | None,
) -> None:
    rule = AutomationRule(1, "manual", condition, TaskContent("Reponer té"))
    document = rule.document()
    assert document.decode()["action"] == {"kind": "task.create", "title": "Reponer té"}
    assert AutomationRule.from_document(document) == rule
    assert AutomationRule.from_document(document).document() == document


def test_draft_rule_document_preserves_a_condition_at_the_maximum_depth() -> None:
    condition: Condition = StockCondition("tea")
    for _ in range(MAX_CONDITION_DEPTH - 1):
        condition = ConditionGroup("all", (condition,))
    rule = AutomationRule(1, "manual", condition, TaskContent("Buy tea"))
    assert AutomationRule.from_document(rule.document()) == rule


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"household_id": "elsewhere"}, "invalid_automation_rule"),
        ({"version": True}, "invalid_automation_rule"),
        ({"version": 2}, "invalid_automation_rule"),
        ({"trigger": {"kind": "manual", "schedule": "daily"}}, "invalid_automation_rule"),
        ({"action": {"kind": "notification", "title": "Buy tea"}}, "invalid_automation_rule"),
        ({"condition": {"kind": "not", "child": None}}, "invalid_automation_condition"),
        ({"condition": {"kind": "any", "children": []}}, "invalid_automation_condition"),
        (
            {"condition": {"kind": "stock_below_minimum", "product_id": "tea", "code": ""}},
            "invalid_automation_condition",
        ),
    ],
)
def test_draft_rule_document_rejects_invalid_records(
    changes: dict[str, object], reason: str
) -> None:
    baseline = AutomationRule(1, "manual", None, TaskContent("Buy tea")).document()
    with pytest.raises(InvalidInput, match=reason):
        AutomationRule.from_document(JsonDocument.from_value(baseline.decode() | changes))


def test_draft_rule_document_rejects_task_fields_the_format_cannot_preserve() -> None:
    rule = AutomationRule(1, "manual", None, TaskContent("Buy tea", description="Loose leaf"))
    with pytest.raises(InvalidInput, match="invalid_automation_rule"):
        rule.document()


def save(api, key, *, rule_id=None, revision="0", **rule):
    return api.client.post(
        DRAFTS,
        json=RULE | rule | {"rule_id": rule_id, "expected_revision": revision},
        headers=api.headers(key) | CONTEXT,
    )


def read(api, path=DRAFTS, **kwargs):
    return api.client.get(path, headers=CONTEXT, **kwargs)


def effects(api):
    tables = (
        "task_definitions",
        "task_occurrences",
        "inventory_movements",
        "inventory_effects",
        "points_task_receipts",
    )
    with closing(sqlite3.connect(api.store.path)) as connection, api.store.read() as unit:
        rows = tuple(connection.execute(f"SELECT * FROM {table}").fetchall() for table in tables)
        return rows, unit.outbox.pending()


def test_draft_round_trip_pagination_and_preview_leave_no_pending_effect(api):
    api.user(USER, True)
    assert read(api).json() == {"drafts": [], "next_cursor": None}
    product = register(api, "tea", "Tea", "piece")
    assert (
        post(
            api,
            "configure-tea",
            "configure-replenishment",
            product_id=product,
            minimum="2",
            target="4",
            expected_revision="0",
        ).status_code
        == 200
    )
    before = effects(api)
    rule = {"action": ACTION | {"title": "Reponer té"}, "condition": leaf(product)}
    saved = save(api, "save-tea", **rule)
    assert saved.status_code == 200, saved.text
    receipt = saved.json()
    rule_id = receipt["result"]["rule_id"]
    state = {"rule_id": rule_id, "revision": "1", "state": "draft", "enabled": False}
    assert receipt["result"] == state | {"member_id": receipt["result"]["member_id"]}
    reopened = read(api, f"{DRAFTS}/{rule_id}")
    assert reopened.json() == RULE | rule | state
    assert read(api).json() == {
        "drafts": [state | {"title": rule["action"]["title"]}],
        "next_cursor": None,
    }
    assert preview(api, api.headers() | CONTEXT, **rule).json()["would_create"] is True
    assert effects(api) == before
    assert post(api, "stock-tea", "intake", product_id=product, quantity="2").status_code == 200
    updated = effects(api)
    assert preview(api, api.headers() | CONTEXT, **rule).json()["would_create"] is False
    assert effects(api) == updated

    tallest = leaf(product)
    for _ in range(MAX_CONDITION_DEPTH - 1):
        tallest = {"kind": "all", "children": [tallest]}
    second = save(api, "second-draft", condition=tallest)
    assert second.status_code == 200, second.text
    second_id = second.json()["result"]["rule_id"]
    assert read(api, f"{DRAFTS}/{second_id}").json()["condition"] == tallest
    first_page = read(api, params={"limit": 1}).json()
    assert len(first_page["drafts"]) == 1 and first_page["next_cursor"]
    cursor = first_page["next_cursor"]
    next_page = read(api, params={"limit": 1, "cursor": cursor}).json()
    assert [item["rule_id"] for item in first_page["drafts"] + next_page["drafts"]] == sorted(
        (rule_id, second_id)
    )
    assert next_page["next_cursor"] is None
    wrong_limit = read(api, params={"limit": 2, "cursor": cursor})
    assert (wrong_limit.status_code, wrong_limit.json()["code"]) == (422, "invalid_task_cursor")


def test_draft_denies_revoked_grants_and_preserves_the_last_valid_revision(api):
    api.user(USER, True)
    created = save(api, "first")
    assert created.status_code == 200, created.text
    rule_id = created.json()["result"]["rule_id"]
    path = f"{DRAFTS}/{rule_id}"
    before = read(api, path).json()
    for changes, expected in (
        ({"enabled": True}, (422, "invalid_request")),
        ({"condition": leaf("other-household-product")}, (404, "inventory_product_missing")),
    ):
        rejected = save(api, "edit", rule_id=rule_id, revision="1", **changes)
        assert (rejected.status_code, rejected.json()["code"]) == expected
    bad_revision = save(api, "edit", rule_id=rule_id)
    assert (bad_revision.status_code, bad_revision.json()["code"]) == (422, "invalid_revision")
    bad_creation = save(api, "edit", revision="1")
    assert (bad_creation.status_code, bad_creation.json()["code"]) == (422, "invalid_revision")
    too_large = save(api, "edit", rule_id=rule_id, revision=str(MAX_REVISION + 1))
    assert (too_large.status_code, too_large.json()["code"]) == (422, "invalid_request")
    missing = read(api, f"{DRAFTS}/elsewhere")
    assert (missing.status_code, missing.json()["code"]) == (404, "automation_draft_missing")
    assert read(api, path).json() == before

    original = f"{DRAFTS}/requests/first"
    with api.store.write() as unit:
        member = unit.members.by_user("home", USER)
        restricted = replace(
            member,
            exceptions=(PermissionRule(Permission.TASKS_CREATE, False),),
            revision=member.revision + 1,
        )
        unit.members.save(restricted, member.revision)
    assert read(api, path).json() == before
    assert read(api, original).status_code == 403
    assert save(api, "first").status_code == 403
    with api.store.write() as unit:
        unit.members.save(
            replace(restricted, status=MemberStatus.SUSPENDED, revision=restricted.revision + 1),
            restricted.revision,
        )
    assert all(read(api, route).status_code == 403 for route in (DRAFTS, path, original))
    assert save(api, "edit", rule_id=rule_id, revision="1").status_code == 403


def test_openapi_draft_revision_pattern_matches_the_exact_signed_range(api):
    schema = api.client.get("/api/v1/openapi.json").json()["components"]["schemas"]
    pattern = schema["AutomationDraftBody"]["properties"]["expected_revision"]["pattern"]
    assert all(re.fullmatch(pattern, value) is None for value in ("-1", "01", "1.0", "+1"))
    for exponent in range(19):
        boundary = (MAX_REVISION // 10**exponent) * 10**exponent
        for revision in (10**exponent, boundary - 1, boundary, boundary + 1):
            assert bool(re.fullmatch(pattern, str(revision))) == (0 <= revision <= MAX_REVISION)
    assert re.fullmatch(pattern, "0")
    assert re.fullmatch(pattern, str(10**19)) is None


def test_concurrent_draft_edits_and_original_request_replay(api):
    api.user(USER, True)
    first = save(api, "initial").json()
    rule_id = first["result"]["rule_id"]
    assert save(api, "initial").json() == first
    assert read(api, f"{DRAFTS}/requests/initial").json() == first
    missing = read(api, f"{DRAFTS}/requests/unknown")
    assert (missing.status_code, missing.json()["code"]) == (404, "operation_missing")

    contenders = [
        (
            key,
            api.headers(key) | CONTEXT,
            RULE
            | {"rule_id": rule_id, "expected_revision": "1", "action": ACTION | {"title": key}},
        )
        for key in ("first-edit", "second-edit")
    ]
    start = Barrier(2)

    def edit(item):
        key, headers, body = item
        start.wait(timeout=10)
        return key, api.client.post(DRAFTS, headers=headers, json=body)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = sorted(pool.map(edit, contenders), key=lambda item: item[1].status_code)
    (winner, accepted), (_, rejected) = results
    assert accepted.status_code == 200 and accepted.json()["result"]["revision"] == "2"
    assert (rejected.status_code, rejected.json()["code"]) == (409, "revision_conflict")
    assert read(api, f"{DRAFTS}/requests/{winner}").json() == accepted.json()
    wrong_payload = save(api, winner, rule_id=rule_id, revision="1")
    assert (wrong_payload.status_code, wrong_payload.json()["code"]) == (
        409,
        "idempotency_conflict",
    )
    latest = read(api, f"{DRAFTS}/{rule_id}").json()
    assert latest["revision"] == "2" and latest["action"]["title"] == winner
    assert read(api, f"{DRAFTS}/requests/initial").json() == first
    with closing(sqlite3.connect(api.store.path)) as connection:
        rows = connection.execute(
            "SELECT revision,definition FROM automation_draft_revisions "
            "WHERE household_id='home' AND rule_id=? ORDER BY revision",
            (rule_id,),
        ).fetchall()
        assert [revision for revision, _ in rows] == [1, 2]
        assert [
            AutomationRule.from_document(JsonDocument(definition)).task.title
            for _, definition in rows
        ] == [ACTION["title"], winner]
