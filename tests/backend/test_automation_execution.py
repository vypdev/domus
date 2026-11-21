"""Manual runs use a pinned revision and one atomic, authorized task command."""

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier, Event

import pytest
from test_automation_drafts import DRAFTS, effects, read, save
from test_automation_preview import ACTION, CONTEXT, USER, leaf
from test_inventory_catalog_http import post, register
from test_task_runtime import api as api

from domus.application.automation_execution import RUN_AUTOMATION, SET_AUTOMATION_CONTROL
from domus.domain.errors import StorageFailure
from domus.domain.identity import MAX_REVISION, MemberStatus, Permission, PermissionRule
from domus.infrastructure.sqlite_receipts import SQLiteReceipts

REQUESTS = "/api/v1/automation/execution/requests"


def initial_draft(api, **rule):
    api.user(USER, True)
    response = save(api, "draft", **rule)
    assert response.status_code == 200, response.text
    return response.json()["result"]["rule_id"]


def configure(api, rule_id, key, *, revision="1", expected="0", enabled=True):
    return api.client.post(
        f"{DRAFTS}/{rule_id}/execution",
        json={
            "rule_revision": revision,
            "expected_control_revision": expected,
            "enabled": enabled,
        },
        headers=api.headers(key) | CONTEXT,
    )


def run(api, rule_id, key, *, revision="1", control="1"):
    return api.client.post(
        f"{DRAFTS}/{rule_id}/runs",
        json={"rule_revision": revision, "control_revision": control},
        headers=api.headers(key) | CONTEXT,
    )


def result(response):
    assert response.status_code == 200, response.text
    assert response.json()["state"] == "committed"
    return response.json()["result"]


def denied(response, status, code):
    assert (response.status_code, response.json()["code"]) == (status, code), response.text


def hold_receipt_writer(monkeypatch, action, key):
    entered = Event()
    release = Event()
    add = SQLiteReceipts.add

    def held_add(repository, receipt):
        add(repository, receipt)
        if receipt.command.action == action and receipt.command.key == key:
            assert repository.connection.in_transaction
            assert repository.connection.execute("PRAGMA busy_timeout").fetchone()[0] == 250
            entered.set()
            assert release.wait(timeout=5)

    monkeypatch.setattr(SQLiteReceipts, "add", held_add)
    return entered, release


def busy(response):
    denied(response, 503, "storage_busy")
    assert response.headers["Retry-After"] == "1"


def audit(api):
    with api.store.read() as unit:
        return unit.audit.entries("home")


def one_task_effect(api, before, execution):
    rows, pending = effects(api)
    previous_rows, previous_pending = before
    assert len(rows[0]) == len(previous_rows[0]) + 1 == 1
    assert len(rows[1]) == len(previous_rows[1]) + 1 == 1
    assert rows[2:] == previous_rows[2:]
    assert pending[:-1] == previous_pending
    assert len(pending) == len(previous_pending) + 1
    assert pending[-1].event_id == execution["task_operation_id"]
    assert pending[-1].event_type == "task.create"
    with api.store.read() as unit:
        receipt = unit.receipts.get_operation("home", USER, execution["task_operation_id"])
        assert receipt.command.action == "task.create"
        assert receipt.result.decode()["occurrence_id"] == execution["task_occurrence_id"]
        work = unit.tasks.occurrence("home", execution["task_occurrence_id"])
        assert work.definition_snapshot.content.title == ACTION["title"]


def test_enable_exact_revision_and_keep_it_through_draft_edits(api):
    rule_id = initial_draft(api, action=ACTION | {"title": "Original pantry task"})
    state = f"{DRAFTS}/{rule_id}/execution"
    assert read(api, state).json() == {
        "rule_id": rule_id,
        "latest_revision": "1",
        "latest_title": "Original pantry task",
        "control": None,
    }
    denied(read(api, f"{DRAFTS}/missing-rule/execution"), 404, "automation_draft_missing")
    denied(configure(api, rule_id, "disable-inactive", enabled=False), 409, "automation_disabled")
    denied(run(api, rule_id, "disabled"), 409, "automation_disabled")
    denied(configure(api, rule_id, "missing", revision="2"), 404, "automation_draft_missing")
    before = effects(api)
    activation = configure(api, rule_id, "enable")
    assert result(activation)["enabled"] is True
    assert configure(api, rule_id, "enable").json() == activation.json()
    assert read(api, f"{REQUESTS}/configure/enable").json() == activation.json()
    denied(configure(api, rule_id, "enable", revision="2"), 409, "idempotency_conflict")
    assert effects(api) == before

    assert (
        save(
            api,
            "edit",
            rule_id=rule_id,
            revision="1",
            action=ACTION
            | {
                "title": "Updated pantry task",
            },
        ).status_code
        == 200
    )
    assert read(api, state).json() == {
        "rule_id": rule_id,
        "latest_revision": "2",
        "latest_title": "Updated pantry task",
        "control": {
            "rule_revision": "1",
            "control_revision": "1",
            "enabled": True,
            "title": "Original pantry task",
        },
    }
    denied(run(api, rule_id, "wrong-rule-revision", revision="2"), 409, "revision_conflict")
    receipt = run(api, rule_id, "run-one")
    execution = result(receipt)
    assert execution["rule_revision"] == execution["control_revision"] == "1"
    assert execution["condition_matched"] is True
    assert execution["member_id"] == result(activation)["member_id"]
    with api.store.read() as unit:
        occurrence = unit.tasks.occurrence("home", execution["task_occurrence_id"])
        task = unit.receipts.get_operation("home", USER, execution["task_operation_id"])
        assert occurrence.definition_snapshot.content.title == "Original pantry task"
        assert task.result.decode()["occurrence_id"] == occurrence.occurrence_id
        pending = unit.outbox.pending()
        assert pending[:-1] == before[1]
        assert pending[-1].event_id == task.operation_id
        assert pending[-1].event_type == "task.create"

    denied(configure(api, rule_id, "old-activation"), 409, "revision_conflict")
    denied(
        configure(api, rule_id, "wrong-disable", expected="1", revision="2", enabled=False),
        409,
        "revision_conflict",
    )
    assert (
        result(configure(api, rule_id, "disable", expected="1", enabled=False))["enabled"] is False
    )
    denied(run(api, rule_id, "disabled-now"), 409, "automation_disabled")
    assert run(api, rule_id, "run-one").json() == receipt.json()
    assert read(api, f"{REQUESTS}/run/run-one").json() == receipt.json()
    assert (
        result(configure(api, rule_id, "reactivate", expected="2", revision="2"))[
            "control_revision"
        ]
        == "3"
    )
    denied(run(api, rule_id, "stale-confirmation", control="1"), 409, "revision_conflict")
    assert (
        result(run(api, rule_id, "second-run", revision="2", control="3"))["rule_revision"] == "2"
    )


def test_stock_is_evaluated_when_each_request_is_admitted(api):
    api.user(USER, True)
    product = register(api, "tea", "Tea", "piece")
    assert (
        post(
            api,
            "minimum",
            "configure-replenishment",
            product_id=product,
            minimum="2",
            target="4",
            expected_revision="0",
        ).status_code
        == 200
    )
    rule_id = initial_draft(api, condition=leaf(product))
    assert result(configure(api, rule_id, "enable"))["enabled"] is True
    assert post(api, "refill", "intake", product_id=product, quantity="2").status_code == 200

    before = effects(api)
    did_not_match = run(api, rule_id, "above-minimum")
    outcome = result(did_not_match)
    assert outcome["condition_matched"] is False
    assert outcome["task_occurrence_id"] is outcome["task_operation_id"] is None
    assert effects(api) == before
    assert read(api, f"{REQUESTS}/run/above-minimum").json() == did_not_match.json()
    assert (
        post(
            api, "use-stock", "adjust", product_id=product, quantity="-1", reason="Counted less"
        ).status_code
        == 200
    )
    assert result(run(api, rule_id, "below-minimum"))["condition_matched"] is True
    assert run(api, rule_id, "above-minimum").json() == did_not_match.json()


@pytest.mark.parametrize("permission", [Permission.AUTOMATIONS_CONFIGURE, Permission.TASKS_CREATE])
def test_revocation_prevents_admission_and_original_recovery(api, permission):
    rule_id = initial_draft(api)
    result(configure(api, rule_id, "enable"))
    result(run(api, rule_id, "committed"))
    before = effects(api)
    if permission is Permission.AUTOMATIONS_CONFIGURE:
        api.user(USER, False)
    else:
        with api.store.write() as unit:
            owner = unit.members.by_user("home", USER)
            unit.members.save(
                replace(
                    owner,
                    exceptions=(PermissionRule(permission, False),),
                    revision=owner.revision + 1,
                ),
                owner.revision,
            )
    denied(read(api, f"{DRAFTS}/{rule_id}/execution"), 403, "permission_denied")
    denied(run(api, rule_id, "revoked"), 403, "permission_denied")
    denied(run(api, rule_id, "committed"), 403, "permission_denied")
    denied(read(api, f"{REQUESTS}/run/committed"), 403, "permission_denied")
    assert effects(api) == before


def test_suspended_member_cannot_admit_a_rule(api):
    rule_id = initial_draft(api)
    result(configure(api, rule_id, "enable"))
    with api.store.write() as unit:
        owner = unit.members.by_user("home", USER)
        unit.members.save(
            replace(owner, status=MemberStatus.SUSPENDED, revision=owner.revision + 1),
            owner.revision,
        )
    denied(run(api, rule_id, "suspended"), 403, "permission_denied")


@pytest.mark.parametrize("held_writer", [False, True])
def test_duplicate_concurrent_requests_retain_one_task_and_receipt(api, monkeypatch, held_writer):
    rule_id = initial_draft(api)
    result(configure(api, rule_id, "enable"))
    barrier = Barrier(2)
    headers = api.headers("duplicate") | CONTEXT
    body = {"rule_revision": "1", "control_revision": "1"}
    writer = hold_receipt_writer(monkeypatch, RUN_AUTOMATION, "duplicate") if held_writer else None
    before = effects(api)
    before_audit = audit(api)

    def invoke(contender):
        barrier.wait(timeout=5)
        if writer is not None and contender == 1:
            assert writer[0].wait(timeout=5)
        try:
            return api.client.post(f"{DRAFTS}/{rule_id}/runs", json=body, headers=headers)
        finally:
            if writer is not None and contender == 1:
                writer[1].set()

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(invoke, 0)
        second = executor.submit(invoke, 1)
        replies = first.result(), second.result()
    statuses = sorted(response.status_code for response in replies)
    assert statuses in ([200, 200], [200, 503])
    if held_writer:
        assert statuses == [200, 503]
    accepted = next(response for response in replies if response.status_code == 200)
    execution = result(accepted)
    one_task_effect(api, before, execution)
    after = effects(api), audit(api)
    assert after[1][: len(before_audit)] == before_audit
    added = after[1][len(before_audit) :]
    assert len(added) == 2
    assert {entry.operation_id for entry in added} == {
        accepted.json()["operation_id"],
        execution["task_operation_id"],
    }
    assert read(api, f"{REQUESTS}/run/duplicate").json() == accepted.json()
    completed = []
    for response in replies:
        if response.status_code == 503:
            busy(response)
            # The winner committed this same key. Retry its unchanged original once.
            response = api.client.post(f"{DRAFTS}/{rule_id}/runs", json=body, headers=headers)
        assert result(response) == execution
        assert response.json() == accepted.json()
        assert (effects(api), audit(api)) == after
        completed.append(response)
    replies = tuple(completed)
    assert result(replies[0]) == result(replies[1])
    assert replies[0].json() == replies[1].json()
    assert len(effects(api)[0][1]) == 1
    denied(run(api, rule_id, "duplicate", control="2"), 409, "idempotency_conflict")
    assert read(api, f"{REQUESTS}/run/duplicate").json() == accepted.json()
    assert (effects(api), audit(api)) == after


@pytest.mark.parametrize("held_action", [None, RUN_AUTOMATION, SET_AUTOMATION_CONTROL])
def test_disable_serializes_against_manual_admission(api, monkeypatch, held_action):
    rule_id = initial_draft(api)
    result(configure(api, rule_id, "enable"))
    barrier = Barrier(2)
    run_headers = api.headers("race-run") | CONTEXT
    disable_headers = api.headers("race-disable") | CONTEXT
    run_body = {"rule_revision": "1", "control_revision": "1"}
    disable_body = {"rule_revision": "1", "expected_control_revision": "1", "enabled": False}
    before = effects(api)
    before_audit = audit(api)
    held_key = "race-run" if held_action == RUN_AUTOMATION else "race-disable"
    writer = (
        hold_receipt_writer(monkeypatch, held_action, held_key) if held_action is not None else None
    )

    def invoke(path, payload, headers):
        barrier.wait(timeout=5)
        action = RUN_AUTOMATION if path == "runs" else SET_AUTOMATION_CONTROL
        if writer is not None and action != held_action:
            assert writer[0].wait(timeout=5)
        try:
            return api.client.post(f"{DRAFTS}/{rule_id}/{path}", json=payload, headers=headers)
        finally:
            if writer is not None and action != held_action:
                writer[1].set()

    with ThreadPoolExecutor(max_workers=2) as executor:
        requested = executor.submit(invoke, "runs", run_body, run_headers)
        disabled = executor.submit(
            invoke,
            "execution",
            disable_body,
            disable_headers,
        )
        run_response, disable_response = requested.result(), disabled.result()

    if held_action == RUN_AUTOMATION:
        assert (run_response.status_code, disable_response.status_code) == (200, 503)
    elif held_action == SET_AUTOMATION_CONTROL:
        assert (run_response.status_code, disable_response.status_code) == (503, 200)
    if run_response.status_code == 503:
        busy(run_response)
        assert disable_response.status_code == 200
        denied(read(api, f"{REQUESTS}/run/race-run"), 404, "operation_missing")
        unchanged = effects(api), audit(api)
        # Disable already committed. The same run original must still be rejected.
        run_response = api.client.post(
            f"{DRAFTS}/{rule_id}/runs", json=run_body, headers=run_headers
        )
        assert (effects(api), audit(api)) == unchanged
    if disable_response.status_code == 503:
        busy(disable_response)
        assert run_response.status_code == 200
        assert read(api, f"{REQUESTS}/run/race-run").json() == run_response.json()
        unchanged_effects, previous_audit = effects(api), audit(api)
        # The admitted task stays intact while disabling the same control explicitly.
        disable_response = api.client.post(
            f"{DRAFTS}/{rule_id}/execution", json=disable_body, headers=disable_headers
        )
        assert result(disable_response)["enabled"] is False
        assert effects(api) == unchanged_effects
        current_audit = audit(api)
        assert current_audit[: len(previous_audit)] == previous_audit
        assert len(current_audit) == len(previous_audit) + 1
        assert current_audit[-1].operation_id == disable_response.json()["operation_id"]
    assert result(disable_response)["enabled"] is False
    assert read(api, f"{REQUESTS}/configure/race-disable").json() == disable_response.json()
    state = read(api, f"{DRAFTS}/{rule_id}/execution").json()
    assert state["control"]["control_revision"] == "2" and state["control"]["enabled"] is False
    denied(run(api, rule_id, "after-disable"), 409, "automation_disabled")
    if run_response.status_code == 200:
        assert result(run_response)["task_occurrence_id"]
        assert len(effects(api)[0][1]) == 1
        assert read(api, f"{REQUESTS}/run/race-run").json() == run_response.json()
        execution = result(run_response)
        one_task_effect(api, before, execution)
        expected_operations = {
            run_response.json()["operation_id"],
            execution["task_operation_id"],
            disable_response.json()["operation_id"],
        }
    else:
        denied(run_response, 409, "automation_disabled")
        assert len(effects(api)[0][1]) == 0
        denied(read(api, f"{REQUESTS}/run/race-run"), 404, "operation_missing")
        assert effects(api) == before
        expected_operations = {disable_response.json()["operation_id"]}
    current_audit = audit(api)
    assert current_audit[: len(before_audit)] == before_audit
    added = current_audit[len(before_audit) :]
    assert len(added) == len(expected_operations)
    assert {entry.operation_id for entry in added} == expected_operations


def test_failed_run_receipt_rolls_back_the_ordinary_task(api, monkeypatch):
    rule_id = initial_draft(api)
    result(configure(api, rule_id, "enable"))
    before = effects(api)
    original = SQLiteReceipts.add

    def fail_run(self, receipt):
        if receipt.command.action == RUN_AUTOMATION:
            raise StorageFailure("storage_failure")
        original(self, receipt)

    with monkeypatch.context() as patch:
        patch.setattr(SQLiteReceipts, "add", fail_run)
        response = run(api, rule_id, "rollback")
        assert response.status_code == 500, response.text

    assert effects(api) == before
    denied(read(api, f"{REQUESTS}/run/rollback"), 404, "operation_missing")
    assert result(run(api, rule_id, "rollback"))["task_occurrence_id"]
    assert len(effects(api)[0][1]) == 1


@pytest.mark.parametrize("invalid", ["0", "01", "-1", str(MAX_REVISION + 1), True])
def test_run_revision_contract_rejects_invalid_int64_text(api, invalid):
    rule_id = initial_draft(api)
    response = run(api, rule_id, "invalid", control=invalid)
    denied(response, 422, "invalid_request")


def test_published_manual_revisions_use_exact_int64_text(api):
    schemas = api.client.get("/api/v1/openapi.json").json()["components"]["schemas"]
    for field, accepts_zero in (("RevisionText", False), ("ControlRevisionText", True)):
        pattern = schemas[field]["pattern"]
        for value in (0, 1, MAX_REVISION - 1, MAX_REVISION, MAX_REVISION + 1):
            assert bool(re.fullmatch(pattern, str(value))) == (
                (0 if accepts_zero else 1) <= value <= MAX_REVISION
            )
