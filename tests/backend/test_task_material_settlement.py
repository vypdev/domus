"""Explicit material settlements exercise actual SQLite, current grants and original evidence."""

from dataclasses import replace

import pytest
from test_task_material_commands import prepare_material_work
from test_task_material_http import complete, create, selection
from test_task_material_http import inventory as inventory
from test_task_queries import queries
from test_task_runtime import api as api

from domus.application.task_commands import CompleteTask, SettleTaskMaterial
from domus.domain.errors import Conflict, Forbidden, InvalidInput
from domus.domain.identity import Permission, PermissionRule
from domus.domain.task_material_values import (
    MaterialAction,
    MaterialPendingReason,
    MaterialQuantity,
    MaterialUsage,
)
from domus.domain.task_values import MaterialRecording, TaskOverrides


def prepared(tmp_path, *, quantity="2", mode=MaterialRecording.SEPARATE):
    commands, child, store, actor, ids, inventory, work = prepare_material_work(
        tmp_path, overrides=TaskOverrides(material_recording=mode)
    )
    usages = (
        None
        if quantity is None
        else (
            MaterialUsage(
                work.definition_snapshot.materials[0].line_id, MaterialQuantity(quantity)
            ),
        )
    )
    original = child.complete(
        "complete", CompleteTask(work.occurrence_id, 2, ("child",), 90, usages)
    )
    with store.read() as unit:
        cycle = unit.tasks.cycle("home", original.result.decode()["cycle"]["cycle_id"])
        value = unit.task_materials.list("home", cycle.cycle_id)[0]
    return commands, child, store, actor, ids, inventory, work, original, cycle, value


def request(value, action=MaterialAction.POST, *, quantity=None, reason=""):
    return SettleTaskMaterial(
        value.occurrence_id,
        value.revision,
        value.cycle_id,
        value.intent_id,
        action,
        None if quantity is None else MaterialQuantity(quantity),
        reason,
    )


def current(store, value):
    with store.read() as unit:
        return unit.task_materials.get("home", value.intent_id)


@pytest.mark.parametrize(
    "changes",
    [
        {"occurrence_id": "bad/id"},
        {"expected_revision": True},
        {"cycle_id": ""},
        {"intent_id": "bad/id"},
        {"action": "post"},
        {"action": None},
        {"quantity": MaterialQuantity("1")},
        {"action": MaterialAction.CORRECT},
        {"action": MaterialAction.CORRECT, "quantity": MaterialQuantity("1")},
        {"action": MaterialAction.DISMISS},
        {"reason": "\x00"},
    ],
)
def test_settlement_request_rejects_invalid_scope_shape_and_missing_reason(changes):
    values = dict(
        occurrence_id="work",
        expected_revision=1,
        cycle_id="cycle",
        intent_id="intent",
        action=MaterialAction.POST,
    )
    with pytest.raises(InvalidInput):
        SettleTaskMaterial(**(values | changes))


def test_request_quantities_are_canonical_top_level_strings():
    value = SettleTaskMaterial(
        "work",
        2,
        "cycle",
        "intent",
        MaterialAction.CORRECT,
        MaterialQuantity("0.25"),
        "Actual total",
    )
    assert value.document().decode()["quantity"] == "0.25"


def test_explicit_post_commits_once_without_changing_work_or_cycle_revisions(tmp_path):
    _, child, store, _, ids, inventory, work, _, cycle, value = prepared(tmp_path)
    receipt = child.settle_material("post", request(value))
    result = receipt.result.decode()
    assert result["material"]["state"] == "posted"
    assert result["material"]["quantity"] == result["material"]["confirmed_quantity"] == "2"
    assert result["material_source"]["performer_ids"] == ["child"]
    allocated = ids.count
    assert child.settle_material("post", request(value)) == receipt and ids.count == allocated
    assert len(inventory.settlements) == len(inventory.movements()) == 1
    with store.read() as unit:
        assert unit.tasks.cycle("home", cycle.cycle_id) == cycle
        assert unit.tasks.occurrence("home", work.occurrence_id).revision == 3
    service = queries(store, child.actor.current())
    assert service.operation(receipt.operation_id).receipt == receipt
    assert service.history(work.occurrence_id).items[-1].action == "task.material.settle"


def test_authorized_restricted_participant_corrects_confirmed_consumption_with_both_cas_steps(
    tmp_path,
):
    _, child, store, _, _, inventory, _, _, _, value = prepared(
        tmp_path, mode=MaterialRecording.REVIEW_ON_COMPLETION
    )
    original = value.posting
    receipt = child.settle_material(
        "correct",
        request(value, MaterialAction.CORRECT, quantity="3", reason="Adjusted actual total"),
    )
    changed = current(store, value)
    assert changed.revision == value.revision + 2 and changed.effect_revision == 2
    assert changed.submitted_quantity.value == "2" and changed.quantity.value == "3"
    assert changed.posting.movement_id != original.movement_id
    assert (
        len(inventory.movements()) == 2
        and receipt.result.decode()["material"]["confirmed_quantity"] == "3"
    )
    later = request(changed, MaterialAction.CORRECT, quantity="4", reason="Final actual total")
    child.settle_material("later", later)
    assert (
        child.settle_material(
            "correct",
            request(value, MaterialAction.CORRECT, quantity="3", reason="Adjusted actual total"),
        )
        == receipt
    )
    assert current(store, value).quantity.value == "4" and len(inventory.movements()) == 3


def test_pending_stock_retry_preserves_the_effect_key_and_original_pending_receipt(tmp_path):
    _, child, store, _, _, inventory, _, _, _, value = prepared(tmp_path)
    inventory.pending = MaterialPendingReason.STOCK_SHORTAGE
    pending = child.settle_material("attempt", request(value))
    changed = current(store, value)
    assert changed.state.value == "pending_regularization"
    inventory.pending = None
    posted = child.settle_material("retry", request(changed))
    assert posted.result.decode()["material"]["state"] == "posted"
    assert child.settle_material("attempt", request(value)) == pending
    assert len(inventory.movements()) == 1
    assert inventory.settlements[0].source_key == inventory.settlements[1].source_key


@pytest.mark.parametrize("action", [MaterialAction.CORRECT, MaterialAction.DISMISS])
def test_unknown_actual_can_be_recorded_as_zero_or_dismissed_without_inventory(tmp_path, action):
    _, child, store, _, _, inventory, _, _, _, value = prepared(tmp_path, quantity=None)
    original = request(
        value,
        action,
        quantity="0" if action is MaterialAction.CORRECT else None,
        reason="Reviewed unused material",
    )
    receipt = child.settle_material("review", original)
    assert current(store, value).state.value == (
        "not_used" if action is MaterialAction.CORRECT else "dismissed"
    )
    assert not inventory.settlements and not inventory.movements()
    assert child.settle_material("review", original) == receipt


def test_current_denial_precedes_original_settlement_receipt_disclosure(tmp_path):
    _, child, store, _, _, inventory, _, _, _, value = prepared(tmp_path)
    receipt = child.settle_material("post", request(value))
    with store.write() as unit:
        member = unit.members.get("home", "child")
        unit.members.save(
            replace(
                member,
                exceptions=(PermissionRule(Permission.TASKS_MATERIAL_USE, False),),
                revision=2,
            ),
            1,
        )
    with pytest.raises(Forbidden):
        child.settle_material("post", request(value))
    with pytest.raises(Forbidden):
        queries(store, child.actor.current()).operation(receipt.operation_id)
    assert len(inventory.movements()) == 1


def test_stale_resource_and_changed_key_payload_never_request_another_effect(tmp_path):
    _, child, store, _, _, inventory, _, _, _, value = prepared(tmp_path)
    child.settle_material("post", request(value))
    with pytest.raises(Conflict, match="revision_conflict"):
        child.settle_material("new-key", request(value))
    with pytest.raises(Conflict, match="idempotency_conflict"):
        child.settle_material("post", replace(request(value), reason="Different payload"))
    assert len(inventory.movements()) == 1


def http_work(api):
    created = create(
        api, materials=[selection()], overrides={"material_recording": "separate_recording"}
    )
    line = api.client.get("/api/v1/tasks/definitions/" + created["result"]["definition_id"]).json()[
        "materials"
    ][0]
    completed = complete(
        api, created, {"material_usages": [{"line_id": line["line_id"], "quantity": "2"}]}
    ).json()
    result = completed["result"]
    material = result["materials"][0]
    path = (
        "/api/v1/tasks/occurrences/"
        + result["occurrence_id"]
        + "/materials/"
        + material["intent_id"]
        + "/settlement"
    )
    return result, material, path


def test_both_actual_http_compositions_post_correct_and_recover_original_results(api, inventory):
    result, material, path = http_work(api)
    body = {
        "expected_revision": material["revision"],
        "cycle_id": material["cycle_id"],
        "action": "post",
    }
    posted = api.client.post(path, json=body, headers=api.headers("post-material"))
    assert posted.status_code == 200, posted.text
    value = posted.json()["result"]["material"]
    corrected = api.client.post(
        path,
        json={
            "expected_revision": value["revision"],
            "cycle_id": value["cycle_id"],
            "action": "correct",
            "quantity": "3",
            "reason": "Adjusted total",
        },
        headers=api.headers("correct-material"),
    )
    assert corrected.status_code == 200, corrected.text
    assert corrected.json()["result"]["material"]["revision"] == value["revision"] + 2
    assert (
        api.client.post(path, json=body, headers=api.headers("post-material")).json()
        == posted.json()
    )
    detail = api.client.get("/api/v1/tasks/occurrences/" + result["occurrence_id"]).json()
    assert detail["materials"][0]["confirmed_quantity"] == "3"
    history = api.client.get(
        "/api/v1/tasks/occurrences/" + result["occurrence_id"] + "/history"
    ).json()["items"][-1]
    assert (
        history["material_action"] == "correct"
        and history["material_intent_id"] == material["intent_id"]
    )
    assert history["reason"] == "Adjusted total"
    assert len(inventory.movements()) == len(inventory.settlements) == 2


@pytest.mark.parametrize(
    "change",
    [
        {"action": "unknown"},
        {"actor_id": "forged"},
        {"household_id": "other"},
        {"material_source": {}},
        {"action": "post", "quantity": "1"},
        {"action": "correct"},
        {"action": "correct", "quantity": "1"},
        {"action": "correct", "quantity": "1.0", "reason": "Total"},
        {"action": "correct", "quantity": 1, "reason": "Total"},
        {"action": "dismiss"},
        {"expected_revision": 0},
        {"cycle_id": "invalid/id"},
    ],
)
def test_invalid_http_settlement_never_changes_intent_or_requests_inventory(api, inventory, change):
    _, material, path = http_work(api)
    response = api.client.post(
        path,
        json={
            "expected_revision": material["revision"],
            "cycle_id": material["cycle_id"],
            "action": "post",
            **change,
        },
        headers=api.headers("invalid-settlement"),
    )
    assert response.status_code == 422, response.text
    with api.store.read() as unit:
        assert (
            unit.task_materials.get("home", material["intent_id"]).revision == material["revision"]
        )
    assert not inventory.movements() and not inventory.settlements


def test_closed_original_cycle_settlement_does_not_touch_a_later_performance(tmp_path):
    from domus.application.task_commands import ReopenTask

    commands, child, store, _, _, inventory, work, _, cycle, value = prepared(tmp_path)
    commands.reopen("reopen", ReopenTask(work.occurrence_id, 3, cycle.cycle_id, "Repeat correctly"))
    later = child.complete("later", CompleteTask(work.occurrence_id, 4, ("child",), 90))
    before = later.result.decode()["cycle"]
    receipt = child.settle_material("original-material", request(value))
    assert receipt.result.decode()["cycle"]["cycle_id"] == cycle.cycle_id
    assert receipt.result.decode()["cycle"]["closed_at"] is not None
    with store.read() as unit:
        live = unit.tasks.occurrence("home", work.occurrence_id)
        assert live.revision == 5 and live.current_cycle_id == before["cycle_id"]
        assert unit.task_materials.list("home", before["cycle_id"])[0].quantity is None
    assert len(inventory.movements()) == 1


@pytest.mark.parametrize("point", ["staged", "confirmed", "audit", "outbox"])
def test_correction_rolls_back_all_cas_and_child_inventory_writes(tmp_path, monkeypatch, point):
    from domus.domain.errors import StorageFailure
    from domus.infrastructure.sqlite import SQLiteAudit, SQLiteOutbox
    from domus.infrastructure.sqlite_task_materials import SQLiteTaskMaterials

    _, child, store, _, _, inventory, _, _, _, value = prepared(
        tmp_path, mode=MaterialRecording.REVIEW_ON_COMPLETION
    )
    before = inventory.movements()
    if point in ("staged", "confirmed"):
        save = SQLiteTaskMaterials.save
        calls = []

        def fail(self, updated, expected):
            save(self, updated, expected)
            calls.append(updated.revision)
            if len(calls) == (1 if point == "staged" else 2):
                raise StorageFailure("fixture_write_failed")

        monkeypatch.setattr(SQLiteTaskMaterials, "save", fail)
    else:
        cls = SQLiteAudit if point == "audit" else SQLiteOutbox
        append = cls.append

        def fail(self, item):
            append(self, item)
            raise StorageFailure("fixture_write_failed")

        monkeypatch.setattr(cls, "append", fail)
    with pytest.raises(StorageFailure):
        child.settle_material(
            "failed-correction",
            request(value, MaterialAction.CORRECT, quantity="3", reason="Actual total"),
        )
    assert current(store, value) == value and inventory.movements() == before
    with store.read() as unit:
        assert all(entry.command.key != "failed-correction" for entry in unit.audit.entries("home"))


@pytest.mark.parametrize("checkpoint_position", ["before_completion", "before_settlement"])
def test_actual_restore_recovers_historical_settlement_without_intent_or_cycle_effect(
    tmp_path, checkpoint_position
):
    from test_activation_compatibility import identity_at
    from test_sqlite_snapshots import Clock

    from domus.infrastructure.owned_storage import open_storage
    from domus.infrastructure.sqlite_activation import SQLiteActivation
    from domus.infrastructure.sqlite_restoration import SQLiteRestorations
    from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots

    root = tmp_path / "source"
    root.mkdir(mode=0o700)
    _, child, store, _, _, inventory, work = prepare_material_work(
        root, overrides=TaskOverrides(material_recording=MaterialRecording.SEPARATE)
    )
    external = tmp_path / "fictional-inventory.sqlite3"
    inventory.path.rename(external)
    inventory.path = external
    identity_at(root, store.installation)
    snapshots = SQLiteSnapshots(store, tmp_path / "archive", store.installation, Clock())
    if checkpoint_position == "before_completion":
        checkpoint = snapshots.create("before")
    original = child.complete(
        "complete",
        CompleteTask(
            work.occurrence_id,
            2,
            ("child",),
            90,
            (MaterialUsage(work.definition_snapshot.materials[0].line_id, MaterialQuantity("2")),),
        ),
    )
    with store.read() as unit:
        value = unit.task_materials.list("home", original.result.decode()["cycle"]["cycle_id"])[0]
    if checkpoint_position == "before_settlement":
        checkpoint = snapshots.create("before")
    command = request(value)
    receipt = child.settle_material("settlement", command)
    movements, calls = inventory.movements(), len(inventory.settlements)
    SQLiteRestorations(
        store, tmp_path / "archive", tmp_path / "prepared", store.installation, Clock(), checkpoint
    ).prepare("restore-settlement")
    assert (
        SQLiteActivation(root, store.installation, Clock(), tmp_path / "prepared").activate().state
        == "active"
    )
    selected = open_storage(root, "edge")
    try:
        service = replace(child, transactions=selected.database)
        restored = service.settle_material("settlement", command)
        assert restored.historical and restored.result == receipt.result
        assert restored.operation_id == receipt.operation_id
        query = queries(selected.database, child.actor.current())
        assert query.operation(receipt.operation_id).receipt.historical
        item = next(
            value
            for value in query.history(work.occurrence_id).items
            if value.operation_id == receipt.operation_id
        )
        assert item.historical and item.material_action is MaterialAction.POST
        with selected.database.read() as unit:
            restored_value = unit.task_materials.get("home", value.intent_id)
            if checkpoint_position == "before_completion":
                assert restored_value is None and unit.tasks.cycle("home", value.cycle_id) is None
            else:
                assert restored_value == value and restored_value.posting is None
        assert inventory.movements() == movements and len(inventory.settlements) == calls
    finally:
        selected.close()


def coherent_bundle(original, request=None, result=None):
    from domus.domain.storage import JsonDocument

    detail = original.audit.detail.decode()
    body = detail["request"] if request is None else request
    result = original.receipt.result.decode() if result is None else result
    return replace(
        original,
        receipt=replace(
            original.receipt,
            payload_fingerprint=JsonDocument.from_value(body).fingerprint,
            result=JsonDocument.from_value(result),
        ),
        audit=replace(
            original.audit,
            detail=JsonDocument.from_value(
                {"transition": "task.material.settled", "request": body, "result": result}
            ),
        ),
        event=replace(
            original.event,
            payload=JsonDocument.from_value(
                {"version": 1, "kind": "task.material.settled", **result}
            ),
        ),
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("source", None),
        ("source", []),
        ("source_extra", True),
        ("source_performer_ids", "child"),
        ("source_performer_ids", []),
        ("source_performer_ids", ["child", "child"]),
        ("source_intent_id", "other"),
        ("source_occurrence_id", "other"),
        ("source_cycle_id", "other"),
        ("source_line_id", "other"),
        ("source_definition_revision", True),
        ("cycle", None),
        ("material", None),
        ("definition_revision", True),
        ("definition_revision", 2),
        ("occurrence_id", "other"),
        ("cycle_household_id", "other"),
        ("cycle_definition_revision", True),
        ("cycle_performers", None),
        ("cycle_performers", [True]),
        ("cycle_performers", [{"member_id": "child", "role": "future"}]),
        ("cycle_performers", [{"member_id": "other", "role": "restricted"}]),
        ("cycle_performers", [{"member_id": "child", "role": "restricted", "extra": 1}]),
        ("material_line_id", "other"),
        ("material_action", "correct"),
    ],
)
def test_consistent_evidence_bundle_cannot_smuggle_invalid_authority_selectors(
    tmp_path, field, value
):
    from domus.application.task_authorization import recorded_request
    from domus.domain.errors import StorageFailure

    _, child, store, _, _, _, _, _, _, intent = prepared(tmp_path)
    receipt = child.settle_material("post", request(intent))
    with store.read() as unit:
        original = unit.tasks.operation("home", "ha_child", receipt.operation_id).evidence
    result = original.receipt.result.decode()
    if field == "source":
        result["material_source"] = value
    elif field.startswith("source_"):
        result["material_source"][field.removeprefix("source_")] = value
    elif field.startswith("cycle_"):
        result["cycle"][field.removeprefix("cycle_")] = value
    elif field == "material_line_id":
        result["material"]["line_id"] = value
    else:
        result[field] = value
    with pytest.raises(StorageFailure, match="invalid_task_operation"):
        recorded_request(coherent_bundle(original, result=result))


def test_concurrent_corrections_serialize_on_intent_revision_before_another_effect(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    _, child, store, _, _, inventory, _, _, _, value = prepared(
        tmp_path, mode=MaterialRecording.REVIEW_ON_COMPLETION
    )
    barrier = Barrier(2)

    def correct(total):
        barrier.wait(timeout=5)
        try:
            return child.settle_material(
                "correct-" + total,
                request(value, MaterialAction.CORRECT, quantity=total, reason="Reviewed total"),
            )
        except Conflict as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(correct, ("3", "4")))
    assert sum(isinstance(value, Conflict) for value in results) == 1
    assert current(store, value).revision == value.revision + 2
    assert current(store, value).quantity.value in ("3", "4")
    assert len(inventory.movements()) == 2


def test_uncertain_return_after_real_commit_recovers_the_original_settlement_once(tmp_path):
    from contextlib import contextmanager
    from types import SimpleNamespace

    from domus.domain.errors import StorageFailure

    _, child, store, _, _, inventory, _, _, _, value = prepared(tmp_path)

    @contextmanager
    def lost_return():
        with store.write() as unit:
            yield unit
        raise StorageFailure("fixture_return_lost")

    uncertain = replace(child, transactions=SimpleNamespace(read=store.read, write=lost_return))
    with pytest.raises(StorageFailure):
        uncertain.settle_material("uncertain", request(value))
    receipt = child.settle_material("uncertain", request(value))
    assert receipt.result.decode()["material"]["state"] == "posted"
    assert child.settle_material("uncertain", request(value)) == receipt
    assert len(inventory.movements()) == len(inventory.settlements) == 1


@pytest.mark.parametrize("selector", ["occurrence_id", "cycle_id", "intent_id"])
def test_missing_settlement_resources_fail_before_any_material_provider_binding(tmp_path, selector):
    _, child, _, _, _, inventory, _, _, _, value = prepared(tmp_path)

    def unexpected(_):
        pytest.fail("Denied selectors must not bind Inventory")

    child = replace(child, inventory_factory=unexpected)
    with pytest.raises(Forbidden):
        child.settle_material("missing", replace(request(value), **{selector: "missing"}))
    assert not inventory.movements()


@pytest.mark.parametrize("kind", ["household", "occurrence", "definition", "line"])
def test_original_scope_cannot_be_used_against_different_current_work(tmp_path, kind):
    from domus.application.task_material_scope import MaterialScope

    _, _, _, _, _, _, work, _, cycle, value = prepared(tmp_path)
    scope = MaterialScope.source(work, cycle, value)
    if kind == "household":
        changed = replace(scope, household_id="other")
    elif kind == "occurrence":
        changed = replace(scope, occurrence_id="other")
    elif kind == "definition":
        changed = replace(scope, definition_revision=2)
    else:
        changed = replace(scope, line_id="other")
    with pytest.raises(InvalidInput):
        changed.require_work(work)


@pytest.mark.parametrize("kind", ["missing", "different"])
def test_broken_operation_repository_cannot_substitute_original_settlement_evidence(
    tmp_path, monkeypatch, kind
):
    from domus.domain.errors import StorageFailure
    from domus.infrastructure.sqlite_tasks import SQLiteTasks

    _, child, _, _, _, inventory, _, _, _, value = prepared(tmp_path)
    child.settle_material("post", request(value))
    operation = SQLiteTasks.operation

    def changed(self, *args):
        row = operation(self, *args)
        if kind == "missing":
            return None
        return replace(
            row,
            evidence=replace(
                row.evidence,
                receipt=replace(row.evidence.receipt, payload_fingerprint="0" * 64),
            ),
        )

    monkeypatch.setattr(SQLiteTasks, "operation", changed)
    with pytest.raises(StorageFailure):
        child.settle_material("post", request(value))
    assert len(inventory.movements()) == 1


def test_changed_original_target_cannot_replay_a_receipt_for_a_different_cycle(tmp_path):
    from domus.application.task_commands import ReopenTask

    commands, child, store, _, _, inventory, work, _, cycle, value = prepared(tmp_path)
    child.settle_material("same-key", request(value))
    commands.reopen(
        "reopen", ReopenTask(work.occurrence_id, 3, cycle.cycle_id, "Another performance")
    )
    later = child.complete("later", CompleteTask(work.occurrence_id, 4, ("child",), 90))
    with store.read() as unit:
        second = unit.task_materials.list("home", later.result.decode()["cycle"]["cycle_id"])[0]
    with pytest.raises(Conflict, match="idempotency_conflict"):
        child.settle_material("same-key", request(second))
    assert current(store, second) == second and len(inventory.movements()) == 1


@pytest.mark.parametrize("change", ["performers", "definition"])
def test_coherently_forged_receipt_context_cannot_override_live_original_scope(
    tmp_path, monkeypatch, change
):
    from domus.domain.errors import StorageFailure
    from domus.infrastructure.sqlite import SQLiteReceipts
    from domus.infrastructure.sqlite_tasks import SQLiteTasks

    _, child, store, _, _, inventory, _, _, _, value = prepared(tmp_path)
    receipt = child.settle_material("post", request(value))
    with store.read() as unit:
        row = unit.tasks.operation("home", "ha_child", receipt.operation_id)
    result = row.evidence.receipt.result.decode()
    if change == "performers":
        result["material_source"]["performer_ids"] = ["other"]
        result["cycle"]["performers"][0]["member_id"] = "other"
    else:
        result["material_source"]["definition_revision"] = result["cycle"][
            "definition_revision"
        ] = result["definition_revision"] = 2
    corrupted = coherent_bundle(row.evidence, result=result)
    get = SQLiteReceipts.get

    def changed(self, command):
        return corrupted.receipt if command == receipt.command else get(self, command)

    monkeypatch.setattr(SQLiteReceipts, "get", changed)
    monkeypatch.setattr(SQLiteTasks, "operation", lambda *args: replace(row, evidence=corrupted))
    with pytest.raises(StorageFailure):
        child.settle_material("post", request(value))
    assert len(inventory.movements()) == 1


def test_pending_correction_preserves_confirmed_total_until_explicit_inventory_retry(tmp_path):
    _, child, store, _, _, inventory, work, original, _, value = prepared(
        tmp_path, mode=MaterialRecording.REVIEW_ON_COMPLETION
    )
    unavailable = replace(child, inventory_factory=None)
    command = request(value, MaterialAction.CORRECT, quantity="3", reason="Reviewed total")
    receipt = unavailable.settle_material("pending-correction", command)
    result = receipt.result.decode()["material"]
    assert result["quantity"] == "3" and result["confirmed_quantity"] == "2"
    assert result["effect_revision"] == 2 and result["confirmed_effect_revision"] == 1
    assert result["pending_reason"] == "inventory_unavailable"
    live = queries(store, child.actor.current()).occurrence(work.occurrence_id).materials[0]
    assert live.quantity == "3" and live.confirmed_quantity == "2"
    assert len(inventory.movements()) == 1
    child.settle_material("explicit-retry", request(current(store, value)))
    assert current(store, value).posting.quantity.value == "3"
    assert unavailable.settle_material("pending-correction", command) == receipt
    assert len(inventory.movements()) == 2
    assert original.result.decode()["materials"][0]["quantity"] == "2"


@pytest.mark.parametrize("guard", ["origin", "csrf", "ha_unavailable"])
def test_new_http_settlement_keeps_existing_session_origin_csrf_and_current_proof_guards(
    api, inventory, guard
):
    from domus.domain.errors import IdentityUnavailable

    _, material, path = http_work(api)
    headers = api.headers("guarded-settlement")
    if guard == "origin":
        headers["Origin"] = "https://other.example"
    elif guard == "csrf":
        headers["X-CSRF-Token"] = "invalid"
    else:
        api.source.error = IdentityUnavailable("ha_unavailable")
    response = api.client.post(
        path,
        json={
            "expected_revision": material["revision"],
            "cycle_id": material["cycle_id"],
            "action": "post",
        },
        headers=headers,
    )
    assert response.status_code == (503 if guard == "ha_unavailable" else 403), response.text
    assert not inventory.movements() and not inventory.settlements


def test_http_records_missing_actual_and_reports_normal_conflicts_without_new_effects(
    api, inventory
):
    created = create(api, materials=[selection()])
    completed = complete(api, created, {}).json()["result"]
    material = completed["materials"][0]
    path = (
        "/api/v1/tasks/occurrences/"
        + completed["occurrence_id"]
        + "/materials/"
        + material["intent_id"]
        + "/settlement"
    )
    original = {
        "expected_revision": material["revision"],
        "cycle_id": material["cycle_id"],
        "action": "post",
    }
    unknown = api.client.post(path, json=original, headers=api.headers("unknown-actual"))
    assert (
        unknown.status_code == 409 and unknown.json()["code"] == "material_actual_quantity_required"
    )
    corrected = api.client.post(
        path,
        json={
            **original,
            "action": "correct",
            "quantity": "2",
            "reason": "Recorded actual quantity",
        },
        headers=api.headers("record-actual"),
    )
    assert corrected.status_code == 200, corrected.text
    revision = corrected.json()["result"]["material"]["revision"]
    for action, extra, code in (
        ("post", {}, "material_already_settled"),
        ("dismiss", {"reason": "Cannot erase confirmed usage"}, "material_already_settled"),
        ("correct", {"quantity": "2", "reason": "Unchanged total"}, "material_unchanged"),
    ):
        response = api.client.post(
            path,
            json={**original, "expected_revision": revision, "action": action, **extra},
            headers=api.headers("conflict-" + action),
        )
        assert response.status_code == 409 and response.json()["code"] == code, response.text
    assert len(inventory.movements()) == len(inventory.settlements) == 1


def test_http_dismissal_retains_original_usage_without_inventing_a_movement(api, inventory):
    result, material, path = http_work(api)
    body = {
        "expected_revision": material["revision"],
        "cycle_id": material["cycle_id"],
        "action": "dismiss",
        "reason": "Reviewed unused request",
    }
    response = api.client.post(path, json=body, headers=api.headers("dismiss-material"))
    assert response.status_code == 200, response.text
    outcome = response.json()["result"]["material"]
    assert outcome["state"] == "dismissed" and outcome["submitted_quantity"] == "2"
    assert outcome["confirmed_quantity"] is None and outcome["movement_id"] is None
    assert (
        api.client.post(path, json=body, headers=api.headers("dismiss-material")).json()
        == response.json()
    )
    assert not inventory.movements() and not inventory.settlements
