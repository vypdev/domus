"""Exercise the protected scheduled creation routes against the real household database."""

from dataclasses import replace

import pytest
from test_inventory_catalog_http import get as catalog
from test_inventory_catalog_http import register
from test_recurrence_http import CONTEXT, USER
from test_task_runtime import api as api

from domus.application.schedule_creation_policy import schedule_creation_policy
from domus.application.task_queries import TaskQueries
from domus.domain.errors import Forbidden, InvalidInput
from domus.domain.identity import (
    HumanIdentity,
    Member,
    MemberStatus,
    Permission,
    PermissionRule,
    Role,
)
from domus.infrastructure.task_cursor import TaskCursor

TASKS = "/api/v1/tasks"
CREATION = TASKS + "/recurrence/creation"


def material_schedule_body(api, kind, task):
    return {
        "task": task,
        "start": {"kind": "date", "local": "2027-01-02"},
        "policy": api.client.get(TASKS + "/access").json()["schedule_policy"],
    } | (
        {"rrule": "FREQ=WEEKLY;BYDAY=SA;COUNT=2"}
        if kind == "fixed"
        else {"interval_days": 15, "visibility": "at_verification"}
    )


def test_material_choice_hint_retires_catalog_labels_when_catalog_read_is_revoked(api):
    api.user(USER, True)
    assert api.client.get(TASKS + "/access").json()["can_link_materials"] is True
    with api.store.write() as unit:
        member = unit.members.list("home")[0]
        unit.members.save(
            replace(
                member, exceptions=(PermissionRule(Permission.HOUSEHOLD_READ, False),), revision=2
            ),
            1,
        )
    response = api.client.get(TASKS + "/access")
    assert response.status_code == 200, response.text
    assert response.json()["can_create"] is True and response.json()["can_link_materials"] is False
    assert (
        api.client.post(
            TASKS + "/definitions",
            json={"title": "Still title-only"},
            headers=api.headers("title-only-without-catalog"),
        ).status_code
        == 200
    )


@pytest.mark.parametrize(
    "problem",
    [
        "metadata",
        "time",
        "historical_current",
        "contradiction",
        "absent_current",
        "missing_projection",
    ],
)
def test_scheduled_original_rejects_corrupt_or_unavailable_provenance(api, monkeypatch, problem):
    from domus.domain.errors import StorageFailure
    from domus.domain.restoration import RetainedOperation
    from domus.domain.storage import CommandKey
    from domus.infrastructure.sqlite_history import encode_operation
    from domus.infrastructure.sqlite_recurrence import SQLiteRecurrences

    api.user(USER, True)
    body = material_schedule_body(api, "fixed", {"title": "Durable original"})
    receipt = api.client.post(
        CREATION + "/fixed", json=body, headers=api.headers("provenance") | CONTEXT
    )
    assert receipt.status_code == 200, receipt.text
    command = CommandKey("home", USER, "recurrence.fixed.create", "provenance")
    if problem == "missing_projection":
        monkeypatch.setattr(SQLiteRecurrences, "creation", lambda *_: None)
        response = api.client.get(
            CREATION + "/requests/recurrence.fixed.create/provenance", headers=CONTEXT
        )
        assert response.status_code == 500 and "result" not in response.json()
        return
    with api.store.write() as unit:
        original = unit.recurrence.creation(command)
        connection = unit.recurrence.connection
        oid = original.evidence.receipt.operation_id
        if problem == "metadata":
            connection.execute("UPDATE audit SET actor_id='outside' WHERE operation_id=?", (oid,))
        elif problem == "time":
            connection.execute("PRAGMA ignore_check_constraints=ON")
            for table, key in (
                ("receipts", "operation_id"),
                ("audit", "operation_id"),
                ("outbox", "event_id"),
            ):
                connection.execute(f"UPDATE {table} SET created_at=-1 WHERE {key}=?", (oid,))
        else:
            evidence = original.evidence
            if problem == "contradiction":
                evidence = replace(
                    evidence, receipt=replace(evidence.receipt, payload_fingerprint="f" * 64)
                )
            retained = RetainedOperation(
                evidence, problem != "historical_current", "restored-provenance"
            )
            connection.execute(
                "INSERT INTO retained_operations VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    *evidence.command_scope,
                    oid,
                    evidence.position,
                    int(retained.current),
                    retained.archived_by,
                    encode_operation(retained),
                    None,
                ),
            )
            if problem == "absent_current":
                connection.execute("DELETE FROM audit WHERE operation_id=?", (oid,))
    with api.store.read() as unit, pytest.raises(StorageFailure):
        unit.recurrence.creation(command)


@pytest.mark.parametrize("kind", ["fixed", "relative"])
def test_legacy_scheduled_original_distinguishes_omission_from_explicit_empty_plan(api, kind):
    api.user(USER, True)
    body = material_schedule_body(api, kind, {"title": "Legacy title-only schedule"})
    path = CREATION + "/" + kind
    headers = api.headers("legacy") | CONTEXT
    receipt = api.client.post(path, json=body, headers=headers)
    assert receipt.status_code == 200, receipt.text
    assert (
        api.client.post(
            path, json=body | {"task": body["task"] | {"materials": None}}, headers=headers
        ).json()
        == receipt.json()
    )
    assert (
        api.client.post(
            path, json=body | {"task": body["task"] | {"materials": []}}, headers=headers
        ).status_code
        == 409
    )
    with api.store.write() as unit:
        member = unit.members.list("home")[0]
        unit.members.save(
            replace(
                member, exceptions=(PermissionRule(Permission.INVENTORY_MANAGE, False),), revision=2
            ),
            1,
        )
    assert api.client.get(TASKS + "/access").json()["can_link_materials"] is False
    original = CREATION + f"/requests/recurrence.{kind}.create/legacy"
    assert api.client.get(original, headers=CONTEXT).status_code == 200
    assert (
        api.client.post(
            path,
            json=body | {"task": body["task"] | {"materials": []}},
            headers=api.headers("new-plan") | CONTEXT,
        ).status_code
        == 403
    )


@pytest.mark.parametrize("kind", ["fixed", "relative"])
def test_scheduled_material_late_write_failure_rolls_back_and_same_key_can_retry(
    api, monkeypatch, kind
):
    from domus.domain.errors import StorageFailure
    from domus.infrastructure.sqlite import SQLiteAudit

    api.user(USER, True)
    register(api, "stock-product", "Soap", "piece")
    reference = catalog(api).json()["products"][0]["reference_id"]
    body = material_schedule_body(
        api,
        kind,
        {
            "title": "Atomic material schedule",
            "materials": [{"reference_id": reference, "planned_quantity": "2"}],
        },
    )
    append = SQLiteAudit.append

    def failure(self, entry):
        append(self, entry)
        if entry.command.action == f"recurrence.{kind}.create":
            raise StorageFailure("injected_material_plan_failure")

    monkeypatch.setattr(SQLiteAudit, "append", failure)
    path = CREATION + "/" + kind
    assert (
        api.client.post(path, json=body, headers=api.headers("atomic-plan") | CONTEXT).status_code
        == 500
    )
    with api.store.read() as unit:
        assert unit.tasks.definitions("home") == () and unit.tasks.policy("home") is None
        assert (
            unit.recurrence.schedules("home") == ()
            and unit.recurrence.relative_schedules("home") == ()
        )
        assert unit.inventory.balance("home", reference) == 0
    assert (
        api.client.get(
            CREATION + f"/requests/recurrence.{kind}.create/atomic-plan", headers=CONTEXT
        ).status_code
        == 404
    )
    monkeypatch.setattr(SQLiteAudit, "append", append)
    receipt = api.client.post(path, json=body, headers=api.headers("atomic-plan") | CONTEXT)
    assert receipt.status_code == 200, receipt.text
    assert (
        api.client.post(path, json=body, headers=api.headers("atomic-plan") | CONTEXT).json()
        == receipt.json()
    )


@pytest.mark.parametrize("kind", ["fixed", "relative"])
def test_scheduled_original_validates_closed_durable_authority_evidence(api, kind):
    from domus.application.task_authorization import TaskAccess, recorded_schedule_authorization
    from domus.domain.errors import StorageFailure
    from domus.domain.storage import CommandKey, JsonDocument

    api.user(USER, True)
    body = material_schedule_body(api, kind, {"title": "Original proof", "materials": []})
    assert (
        api.client.post(
            CREATION + "/" + kind, json=body, headers=api.headers("proof") | CONTEXT
        ).status_code
        == 200
    )
    with api.store.read() as unit:
        evidence = unit.recurrence.creation(
            CommandKey("home", USER, f"recurrence.{kind}.create", "proof")
        ).evidence
    access = TaskAccess(HumanIdentity(USER, True, True, False))
    original = evidence.audit.detail.decode()
    for problem in (
        "transition",
        "extra",
        "request",
        "request_shape",
        "version",
        "version_value",
        "fingerprint",
        "result",
        "event",
        "task",
        "task_shape",
        "overrides",
        "override_keys",
        "materials",
    ):
        detail = evidence.audit.detail.decode()
        request = detail["request"]
        if problem == "transition":
            detail["transition"] = "other"
        if problem == "extra":
            detail["extra"] = "other"
        if problem == "request":
            detail["request"] = None
        if problem == "request_shape":
            request["actor"] = "other"
        if problem == "version":
            request["version"] = True
        if problem == "version_value":
            request["version"] = 2
        if problem == "result":
            detail["result"] = {}
        if problem == "task":
            request["task"] = []
        if problem == "task_shape":
            request["task"].pop("content")
        if problem == "overrides":
            request["task"]["overrides"] = []
        if problem == "override_keys":
            request["task"]["overrides"] = {}
        if problem == "materials":
            request["task"]["materials"] = [{"reference_id": "forged", "planned_quantity": "1.0"}]
        altered = replace(
            evidence,
            audit=replace(evidence.audit, detail=JsonDocument.from_value(detail)),
            receipt=replace(
                evidence.receipt,
                payload_fingerprint="0" * 64
                if problem == "fingerprint"
                else JsonDocument.from_value(detail["request"]).fingerprint
                if isinstance(detail["request"], dict)
                else evidence.receipt.payload_fingerprint,
            ),
        )
        if problem == "event":
            altered = replace(
                altered, event=replace(altered.event, payload=JsonDocument.from_value({}))
            )
        with pytest.raises(StorageFailure, match="invalid_recurrence_operation"):
            recorded_schedule_authorization(access, altered)
    assert original == evidence.audit.detail.decode()
    command = replace(evidence.receipt.command, action="task.create")
    unsupported = replace(
        evidence,
        receipt=replace(evidence.receipt, command=command),
        audit=replace(evidence.audit, command=command),
        event=replace(evidence.event, event_type=command.action),
    )
    with pytest.raises(StorageFailure, match="invalid_recurrence_operation"):
        recorded_schedule_authorization(access, unsupported)


@pytest.mark.parametrize("kind", ["fixed", "relative"])
@pytest.mark.parametrize(("quantity", "unit"), [("0", "piece"), ("1.25", "gram")])
def test_scheduled_material_plan_is_atomic_exact_and_original_is_current_authorized(
    api, kind, quantity, unit
):
    api.user(USER, True)
    product = register(api, "material-product", "Scheduled soap", unit)
    choice = next(item for item in catalog(api).json()["products"] if item["product_id"] == product)
    selection = {"reference_id": choice["reference_id"], "planned_quantity": quantity}
    payload = {
        "task": {"title": "Planned cleaning", "materials": [selection]},
        "start": {"kind": "date", "local": "2027-01-02"},
        "policy": api.client.get(TASKS + "/access").json()["schedule_policy"],
    } | (
        {"rrule": "FREQ=WEEKLY;BYDAY=SA;COUNT=2"}
        if kind == "fixed"
        else {"interval_days": 15, "visibility": "at_verification"}
    )
    path = CREATION + "/" + kind
    headers = api.headers("planned-schedule") | CONTEXT
    original = CREATION + f"/requests/recurrence.{kind}.create/planned-schedule"
    created = api.client.post(path, json=payload, headers=headers)
    assert created.status_code == 200, created.text
    receipt = created.json()
    definition_path = TASKS + "/definitions/" + receipt["result"]["definition_id"]
    definition = api.client.get(definition_path).json()
    line = definition["materials"][0]
    assert line["planned_quantity"] == quantity
    assert line["binding"]["unit_id"] == unit
    assert line["binding"]["location_id"] == "pantry"
    assert line["binding"]["product_id"] == product
    assert api.client.post(path, json=payload, headers=headers).json() == receipt
    recovered = api.client.get(original, headers=CONTEXT)
    assert recovered.status_code == 200, recovered.text
    assert recovered.json()["operation_id"] == receipt["operation_id"]
    changed = payload | {"task": payload["task"] | {"materials": []}}
    assert api.client.post(path, json=changed, headers=headers).status_code == 409

    # Editing the current definition cannot erase the original command's linking authority.
    edited = api.client.put(
        definition_path,
        json={"expected_revision": 1, "title": "Edited plan", "state": "active", "materials": []},
        headers=api.headers("clear-plan"),
    )
    assert edited.status_code == 200, edited.text
    with api.store.write() as work:
        member = work.members.list("home")[0]
        work.members.save(
            replace(
                member, exceptions=(PermissionRule(Permission.INVENTORY_MANAGE, False),), revision=2
            ),
            1,
        )
    assert api.client.get(original, headers=CONTEXT).status_code == 403
    assert api.client.post(path, json=payload, headers=headers).status_code == 403
    plain = payload | {"task": {"title": "Title-only remains available"}}
    assert (
        api.client.post(path, json=plain, headers=api.headers("title-only") | CONTEXT).status_code
        == 200
    )


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
    with api.store.read() as unit, pytest.raises(InvalidInput, match="invalid_recurrence_create"):
        from domus.domain.storage import CommandKey

        unit.recurrence.creation(CommandKey("home", USER, "task.create", "other"))


@pytest.mark.parametrize("kind", ["fixed", "relative"])
def test_http_material_plan_survives_initial_and_successor_snapshots_without_new_consumption(
    api, kind
):
    from datetime import date

    from domus.application.fixed_materialization import FixedMaintenance, MaintenanceScope
    from domus.application.fixed_recurrence import FixedRecurrencePlanner
    from domus.application.recurrence_sources import RecurrenceSourceObservations
    from domus.application.relative_lifecycle import RelativeLifecycle
    from domus.application.relative_materialization import RelativeMaintenance
    from domus.application.relative_recurrence import RelativeRecurrencePlanner
    from domus.domain.nominal_recurrence import CalendarNominalExpansion
    from domus.domain.recurrence_rules import NominalDate
    from domus.infrastructure.application_runtime import SecureIdentifiers, SystemClock
    from domus.infrastructure.recurrence_time import PinnedRecurrenceTime

    api.user(USER, True)
    product = register(api, "recurring-material", "Recurring soap", "millilitre")
    choice = next(item for item in catalog(api).json()["products"] if item["product_id"] == product)
    body = material_schedule_body(
        api,
        kind,
        {
            "title": "Recurring material plan",
            "materials": [{"reference_id": choice["reference_id"], "planned_quantity": "1.25"}],
        },
    ) | {"start": {"kind": "date", "local": "2020-01-04"}}
    created = api.client.post(
        CREATION + "/" + kind, json=body, headers=api.headers("recurring-plan") | CONTEXT
    )
    assert created.status_code == 200, created.text
    schedule = created.json()["result"]["schedule_id"]
    scope = MaintenanceScope(api.store.installation, "home")
    times, clock, ids = PinnedRecurrenceTime(), SystemClock(), SecureIdentifiers()
    fixed = FixedMaintenance(
        api.store, scope, FixedRecurrencePlanner(CalendarNominalExpansion(), times), clock, ids
    )
    before = NominalDate(date(2020, 1, 12))
    initial = (
        fixed.step(schedule, before)
        if kind == "fixed"
        else RelativeMaintenance(api.store, scope, times, clock, ids).initial(schedule)
    )
    first = api.client.get(TASKS + "/occurrences/" + initial.occurrence_id).json()
    lines = first["work"]["definition_snapshot"]["materials"]
    assert len(lines) == 1 and lines[0]["planned_quantity"] == "1.25"
    assert lines[0]["binding"]["product_id"] == product
    assert first["materials"] == []
    member = api.client.get("/api/v1/members").json()["members"][0]["member_id"]
    payload = {
        "expected_revision": first["work"]["revision"],
        "performer_ids": [member],
        "performed_at": clock.now(),
        "material_usages": [{"line_id": lines[0]["line_id"], "quantity": "0"}],
    }
    path = TASKS + "/occurrences/" + initial.occurrence_id + "/complete"
    headers = api.headers("recurring-complete")
    completed = api.client.post(path, json=payload, headers=headers)
    assert completed.status_code == 200, completed.text
    result = completed.json()["result"]["materials"][0]
    assert result["state"] == "not_used" and result["movement_id"] is None
    assert api.client.post(path, json=payload, headers=headers).json() == completed.json()
    if kind == "fixed":
        successor = fixed.step(schedule, before)
    else:
        (record,) = RecurrenceSourceObservations(api.store, scope).ingest().items
        lifecycle = RelativeLifecycle(
            api.store, scope, RelativeRecurrencePlanner(times), clock, ids
        )
        successor = lifecycle.consume(schedule, record.event.event_key)
        assert lifecycle.consume(schedule, record.event.event_key) == successor
    assert successor.occurrence_id and successor.occurrence_id != initial.occurrence_id
    current = api.client.get(TASKS + "/occurrences/" + successor.occurrence_id).json()
    assert current["work"]["definition_snapshot"]["materials"] == lines
    assert current["materials"] == [] and current["cycle"] is None
    original = api.client.get(TASKS + "/occurrences/" + initial.occurrence_id).json()
    assert original["work"]["revision"] == 2 and len(original["materials"]) == 1
    assert original["materials"][0]["intent_id"] == result["intent_id"]
    assert (
        next(item for item in catalog(api).json()["products"] if item["product_id"] == product)[
            "recorded"
        ]
        == "0"
    )


@pytest.mark.parametrize("kind", ["fixed", "relative"])
@pytest.mark.parametrize("position", ["before_creation", "after_creation"])
def test_restored_scheduled_material_original_keeps_absent_definition_and_current_grants(
    tmp_path, kind, position
):
    from test_activation_compatibility import identity_at
    from test_recurrence_creation import request as fixed_request
    from test_recurrence_creation import setup as fixed_setup
    from test_relative_recurrence_creation import request as relative_request
    from test_relative_recurrence_creation import setup as relative_setup
    from test_sqlite_snapshots import Clock
    from test_task_queries import queries

    from domus.application.inventory import InventoryCommands, InventorySettlement
    from domus.domain.task_material_values import (
        MaterialBinding,
        MaterialQuantity,
        MaterialSelection,
    )
    from domus.infrastructure.owned_storage import open_storage
    from domus.infrastructure.sqlite import SQLiteDatabase
    from domus.infrastructure.sqlite_activation import SQLiteActivation
    from domus.infrastructure.sqlite_restoration import SQLiteRestorations
    from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots

    root = tmp_path / "source"
    root.mkdir(mode=0o700)
    creator, _, store, actor, identifiers = (fixed_setup if kind == "fixed" else relative_setup)(
        root
    )
    binding = MaterialBinding("home", "soap-reference", "soap", "piece", "pantry", 1, 0, "Soap")
    inventory = InventoryCommands(store, actor, creator.clock, identifiers)
    inventory.receive("stock", binding, MaterialQuantity("10"))
    creator = replace(
        creator,
        inventory_factory=lambda unit: InventorySettlement(
            unit.inventory, creator.clock, identifiers
        ),
    )
    choice = (fixed_request if kind == "fixed" else relative_request)()
    choice = replace(
        choice,
        task=replace(
            choice.task, materials=(MaterialSelection(binding.reference_id, MaterialQuantity("2")),)
        ),
    )
    identity_at(root, store.installation)
    snapshots = SQLiteSnapshots(store, tmp_path / "archive", store.installation, Clock())
    if position == "before_creation":
        checkpoint = snapshots.create("checkpoint")
    create = creator.create_fixed if kind == "fixed" else creator.create
    receipt = create("material-schedule", choice)
    if position == "after_creation":
        checkpoint = snapshots.create("checkpoint")
    # Reopen the database adapter; original lookup does not resolve a new plan.
    restarted = SQLiteDatabase(store.path, store.installation)
    assert (
        queries(restarted, actor.current())
        .original_schedule(receipt.command.action, receipt.command.key)
        .receipt
        == receipt
    )
    SQLiteRestorations(
        store, tmp_path / "archive", tmp_path / "prepared", store.installation, Clock(), checkpoint
    ).prepare("restore-material-plan")
    assert (
        SQLiteActivation(root, store.installation, Clock(), tmp_path / "prepared").activate().state
        == "active"
    )
    restored = open_storage(root, "edge")
    try:
        query = queries(restored.database, actor.current())
        original = query.original_schedule(receipt.command.action, receipt.command.key)
        assert original.receipt.historical == (position == "before_creation")
        assert original.receipt.result == receipt.result
        assert original.receipt.operation_id == receipt.operation_id
        with restored.database.read() as unit:
            assert (
                unit.tasks.definition("home", receipt.result.decode()["definition_id"]) is None
            ) == (position == "before_creation")
            assert unit.inventory.balance("home", binding.reference_id) == 10_000_000
        if position == "after_creation":
            with restored.database.write() as unit:
                assert unit.outbox.acknowledge(receipt.operation_id)
            assert query.original_schedule(receipt.command.action, receipt.command.key).delivered
        with restored.database.write() as unit:
            member = unit.members.by_user("home", actor.current().ha_user_id)
            unit.members.save(
                replace(
                    member,
                    exceptions=(PermissionRule(Permission.INVENTORY_MANAGE, False),),
                    revision=member.revision + 1,
                ),
                member.revision,
            )
        with pytest.raises(Forbidden):
            query.original_schedule(receipt.command.action, receipt.command.key)
    finally:
        restored.close()


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
