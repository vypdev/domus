"""Protected history reads exact, member-scoped manual automation receipts."""

from dataclasses import replace

import pytest
from test_automation_drafts import DRAFTS, read, save
from test_automation_execution import configure, denied, initial_draft, result, run
from test_automation_preview import USER, leaf, snapshot
from test_inventory_catalog_http import register
from test_rewards_http import member_context
from test_task_runtime import api as api

from domus.application.automation_run_history import AutomationRunHistory
from domus.application.fixed_materialization import MaintenanceScope
from domus.domain.errors import InvalidInput
from domus.domain.identity import (
    HumanIdentity,
    Member,
    MemberStatus,
    Permission,
    PermissionRule,
    Role,
)
from domus.domain.storage import JsonDocument, RestorationProvenance
from domus.infrastructure.sqlite_receipts import SQLiteReceipts
from domus.infrastructure.task_cursor import TaskCursor

OTHER = "b" * 32


def path(rule_id):
    return f"{DRAFTS}/{rule_id}/runs"


def page(api, rule_id, **query):
    response = read(api, path(rule_id), params=query)
    assert response.status_code == 200, response.text
    return response.json()


def operation_ids(payload):
    return [item["operation_id"] for item in payload["items"]]


def test_pages_are_scoped_to_rule_and_current_invoking_member(api):
    rule_id = initial_draft(api)
    assert page(api, rule_id) == {"rule_id": rule_id, "items": [], "next_cursor": None}
    denied(read(api, path("missing-rule")), 404, "automation_draft_missing")
    alternate = result(save(api, "other-draft"))["rule_id"]
    result(configure(api, rule_id, "on"))
    result(configure(api, alternate, "other-on"))
    first = run(api, rule_id, "first").json()
    second = run(api, rule_id, "second").json()
    other_rule = run(api, alternate, "other-rule").json()
    head = page(api, rule_id, limit=1)
    assert operation_ids(head) == [second["operation_id"]]
    cursor = head["next_cursor"]
    denied(
        read(api, path(alternate), params={"limit": 1, "cursor": cursor}),
        422,
        "invalid_task_cursor",
    )
    denied(
        read(api, path(rule_id), params={"limit": 2, "cursor": cursor}), 422, "invalid_task_cursor"
    )
    denied(read(api, path(rule_id), params={"limit": 0}), 422, "invalid_request")
    denied(read(api, path(rule_id), params={"limit": 101}), 422, "invalid_request")
    third = run(api, rule_id, "third").json()
    next_page = page(api, rule_id, limit=1, cursor=cursor)
    assert operation_ids(next_page) == [first["operation_id"]]
    assert next_page["next_cursor"] is None
    assert operation_ids(page(api, rule_id, limit=100)) == [
        third["operation_id"],
        second["operation_id"],
        first["operation_id"],
    ]
    assert operation_ids(page(api, alternate)) == [other_rule["operation_id"]]

    with api.store.write() as unit:
        unit.members.save(
            Member("second-admin", "home", OTHER, Role.ADMINISTRATOR, MemberStatus.ACTIVE, 1), 0
        )
    api.user(OTHER, True)
    context = member_context(OTHER)
    assert api.client.get(path(rule_id), headers=context).json()["items"] == []
    unrelated = api.client.post(
        path(rule_id),
        json={"rule_revision": "1", "control_revision": "1"},
        headers=api.headers("second-admin-run") | context,
    )
    result(unrelated)
    assert operation_ids(api.client.get(path(rule_id), headers=context).json()) == [
        unrelated.json()["operation_id"]
    ]
    denied(
        api.client.get(path(rule_id), params={"limit": 1, "cursor": cursor}, headers=context),
        422,
        "invalid_task_cursor",
    )

    api.user(USER, True)
    before = snapshot(api)
    assert operation_ids(page(api, rule_id)) == [
        third["operation_id"],
        second["operation_id"],
        first["operation_id"],
    ]
    assert snapshot(api) == before
    api.user(USER, False)
    denied(
        read(api, path(rule_id), params={"limit": 1, "cursor": cursor}), 403, "permission_denied"
    )
    denied(read(api, path(rule_id)), 403, "permission_denied")


def test_original_stock_decisions_and_task_privacy_survive_edits_and_disable(api):
    rule_id = initial_draft(api)
    result(configure(api, rule_id, "enable"))
    matched = run(api, rule_id, "matched").json()
    old_task = matched["result"]["task_occurrence_id"]
    product = register(api, "product", "Tea", "piece")
    stock = leaf(product)
    condition = {"kind": "all", "children": [stock, {"kind": "not", "child": stock}]}
    result(save(api, "change", rule_id=rule_id, revision="1", condition=condition))
    result(configure(api, rule_id, "activate-change", revision="2", expected="1"))
    unmatched = run(api, rule_id, "unmatched", revision="2", control="2").json()
    result(configure(api, rule_id, "turn-off", revision="2", expected="2", enabled=False))
    rows = page(api, rule_id)["items"]
    assert rows == [
        {
            "operation_id": unmatched["operation_id"],
            "created_at": unmatched["created_at"],
            "rule_revision": "2",
            "condition_matched": False,
            "task_created": False,
            "historical": False,
            "task_occurrence_id": None,
        },
        {
            "operation_id": matched["operation_id"],
            "created_at": matched["created_at"],
            "rule_revision": "1",
            "condition_matched": True,
            "task_created": True,
            "historical": False,
            "task_occurrence_id": old_task,
        },
    ]
    assert read(api, f"/api/v1/tasks/occurrences/{old_task}").status_code == 200
    with api.store.write() as unit:
        member = unit.members.by_user("home", USER)
        unit.members.save(
            replace(
                member,
                exceptions=(PermissionRule(Permission.TASKS_READ, False),),
                revision=member.revision + 1,
            ),
            member.revision,
        )
    assert page(api, rule_id)["items"] == [rows[0], rows[1] | {"task_occurrence_id": None}]
    denied(read(api, f"/api/v1/tasks/occurrences/{old_task}"), 403, "permission_denied")


class AdjustableClock:
    now_ms = 100

    def now(self):
        return self.now_ms


def service(api, clock, key=b"s" * 32, household_id="home"):
    return AutomationRunHistory(
        api.store,
        MaintenanceScope(api.store.installation, household_id),
        lambda: HumanIdentity(USER, True, True, False),
        TaskCursor(clock, key),
    )


def test_cursor_expiry_restart_and_marker_validation(api):
    rule_id = initial_draft(api)
    result(configure(api, rule_id, "enable"))
    result(run(api, rule_id, "first"))
    result(run(api, rule_id, "second"))
    clock = AdjustableClock()
    history = service(api, clock)
    first = history.page(rule_id, limit=1, cursor=None)
    with pytest.raises(InvalidInput, match="invalid_task_cursor"):
        service(api, clock, b"r" * 32).page(rule_id, limit=1, cursor=first.next_cursor)
    invalid_markers = ("1x", "0", "01", str(2**63))
    binding = JsonDocument.from_value(
        {
            "query": "manual-automation-runs-v1",
            "installation": api.store.installation.instance_id,
            "channel": "edge",
            "household": "home",
            "actor": USER,
            "member": result(run(api, rule_id, "first"))["member_id"],
            "rule": rule_id,
            "limit": 1,
        }
    )
    for marker in invalid_markers:
        token = history.cursors.encode(binding, marker)
        with pytest.raises(InvalidInput, match="invalid_task_cursor"):
            history.page(rule_id, limit=1, cursor=token)
    for size in (True, 0, 101):
        with pytest.raises(InvalidInput, match="invalid_page_size"):
            history.page(rule_id, limit=size, cursor=None)
    clock.now_ms += 300_000
    with pytest.raises(InvalidInput, match="invalid_task_cursor"):
        history.page(rule_id, limit=1, cursor=first.next_cursor)
    assert history.page(rule_id, limit=1, cursor=None).items == first.items


@pytest.mark.parametrize(
    "changes",
    (
        {"rule_revision": None},
        {"rule_revision": "01"},
        {"rule_revision": "unexpected"},
        {"rule_revision": "0"},
        {"condition_matched": None},
        {"condition_matched": False},
        {"task_occurrence_id": None},
        {"task_operation_id": None},
        {"task_occurrence_id": "bad id"},
        {"task_operation_id": "bad id"},
    ),
)
def test_corrupt_receipt_cannot_publish_an_invented_outcome(api, monkeypatch, changes):
    rule_id = initial_draft(api)
    result(configure(api, rule_id, "enable"))
    result(run(api, rule_id, "manual"))
    load = SQLiteReceipts.get_operation

    def corrupt(self, *args):
        receipt = load(self, *args)
        return replace(receipt, result=JsonDocument.from_value(receipt.result.decode() | changes))

    monkeypatch.setattr(SQLiteReceipts, "get_operation", corrupt)
    response = read(api, path(rule_id))
    denied(response, 500, "internal_error")
    assert "bad id" not in response.text


@pytest.mark.parametrize("missing", [True, False])
def test_mismatched_current_or_retained_projection_fails_closed(api, monkeypatch, missing):
    rule_id = initial_draft(api)
    result(configure(api, rule_id, "enable"))
    result(run(api, rule_id, "manual"))
    load = SQLiteReceipts.get_operation

    def corrupt(self, *args):
        if missing:
            return None
        receipt = load(self, *args)
        return replace(receipt, restoration=RestorationProvenance("restore", False))

    monkeypatch.setattr(SQLiteReceipts, "get_operation", corrupt)
    denied(read(api, path(rule_id)), 500, "internal_error")
