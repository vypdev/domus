"""Material commands use actual SQLite and explicit transaction-bound Inventory fakes."""

from dataclasses import replace

import pytest
from test_task_commands import child_commands, fixture, resource
from test_task_material_values import binding

from domus.application.task_commands import (
    CompleteTask,
    CreateTask,
    UpdateTaskDefinition,
)
from domus.application.task_material_ports import InventoryMaterialResult
from domus.domain.task_material_values import (
    MaterialPendingReason,
    MaterialQuantity,
    MaterialSelection,
    MaterialUsage,
)
from domus.domain.task_values import TaskContent


def test_new_material_fields_preserve_original_canonical_request_when_omitted():
    from domus.application.task_requests import CompleteTask, UpdateTaskDefinition
    from domus.domain.task_values import DefinitionState

    create = CreateTask(TaskContent("Work"))
    assert "materials" not in create.document().decode()
    explicit = replace(create, materials=())
    assert explicit.document().decode() == {**create.document().decode(), "materials": []}
    update = UpdateTaskDefinition("definition", 1, TaskContent("Work"), DefinitionState.ACTIVE)
    assert "materials" not in update.document().decode()
    complete = CompleteTask("occurrence", 1, ("member",), 90)
    assert "material_usages" not in complete.document().decode()
    assert (
        replace(complete, material_usages=()).document().fingerprint
        != complete.document().fingerprint
    )


def test_material_request_documents_use_canonical_strings_not_internal_value_wrappers():
    create = CreateTask(
        TaskContent("Work"), materials=(MaterialSelection("binding", MaterialQuantity("0.25")),)
    )
    assert create.document().decode()["materials"] == [
        {"reference_id": "binding", "planned_quantity": "0.25"}
    ]
    complete = CompleteTask(
        "occurrence",
        1,
        ("member",),
        90,
        material_usages=(MaterialUsage("line", MaterialQuantity("0")),),
    )
    assert complete.document().decode()["material_usages"] == [{"line_id": "line", "quantity": "0"}]


class Inventory:
    """Fictional catalog/confirmations; real attached SQLite tests the caller transaction only."""

    def __init__(self, path):
        import sqlite3
        from contextlib import closing

        self.path = path
        self.bindings = {"binding": binding()}
        self.pending = None
        self.pending_by_reference = {}
        self.resolutions = []
        self.settlements = []
        with closing(sqlite3.connect(path, autocommit=True)) as connection:
            connection.execute(
                "CREATE TABLE movements(source_key TEXT PRIMARY KEY, document TEXT NOT NULL)"
            )

    def factory(self, unit):
        from types import SimpleNamespace

        connection = unit.tasks.connection
        connection.execute("ATTACH DATABASE ? AS fixture_inventory", (str(self.path),))
        return SimpleNamespace(
            resolve=self.resolve, settle=lambda request: self.settle(connection, request)
        )

    def resolve(self, household_id, actor_member_id, reference_id):
        self.resolutions.append((household_id, actor_member_id, reference_id))
        return self.bindings.get(reference_id)

    def settle(self, connection, request):
        import json
        from dataclasses import asdict

        from domus.domain.task_materials import MaterialPosting

        self.settlements.append(request)
        pending = self.pending_by_reference.get(
            request.intent.line.binding.reference_id, self.pending
        )
        if pending is not None:
            return InventoryMaterialResult(pending_reason=pending)
        row = connection.execute(
            "SELECT document FROM fixture_inventory.movements WHERE source_key=?",
            (request.source_key,),
        ).fetchone()
        if row is not None:
            value = json.loads(row[0])
            value["quantity"] = MaterialQuantity(value["quantity"])
            return InventoryMaterialResult(posting=MaterialPosting(**value))
        value = request.intent
        posting = MaterialPosting(
            value.intent_id,
            value.household_id,
            value.occurrence_id,
            value.cycle_id,
            value.line.line_id,
            value.line.binding.reference_id,
            value.line.binding.revision,
            value.revision,
            value.effect_revision,
            value.quantity,
            "fixture-operation-" + request.source_key[-64:],
            "fixture-movement-" + request.source_key[-64:],
            value.updated_at,
        )
        document = asdict(posting)
        document["quantity"] = posting.quantity.value
        connection.execute(
            "INSERT INTO fixture_inventory.movements VALUES (?,?)",
            (request.source_key, json.dumps(document)),
        )
        return InventoryMaterialResult(posting=posting)

    def movements(self):
        import sqlite3
        from contextlib import closing

        with closing(sqlite3.connect(self.path, autocommit=True)) as connection:
            return connection.execute(
                "SELECT source_key,document FROM movements ORDER BY source_key"
            ).fetchall()


def configured(tmp_path):
    commands, store, actor, identifiers = fixture(tmp_path)
    inventory = Inventory(tmp_path / "fixture-inventory.sqlite3")
    commands = replace(commands, inventory_factory=inventory.factory)
    child, _ = child_commands(store, identifiers=identifiers)
    child = replace(child, inventory_factory=inventory.factory)
    return commands, child, store, actor, identifiers, inventory


def prepare_material_work(tmp_path, *, overrides=None, selected=True):
    from domus.application.task_commands import AssignTask
    from domus.domain.task_values import TaskOverrides

    commands, child, store, actor, identifiers, inventory = configured(tmp_path)
    request = CreateTask(
        TaskContent("Use cleaner"),
        overrides=TaskOverrides() if overrides is None else overrides,
        materials=(MaterialSelection("binding", MaterialQuantity("2")),) if selected else None,
    )
    receipt = commands.create("create", request)
    definition_id, work_id = resource(receipt)
    commands.assign("assign", AssignTask(work_id, 1, ("child",)))
    with store.read() as unit:
        work = unit.tasks.occurrence("home", work_id)
    return commands, child, store, actor, identifiers, inventory, work


def test_create_resolves_server_bindings_and_retains_one_line_identity_in_frozen_occurrence(
    tmp_path,
):
    commands, _, store, actor, identifiers, inventory = configured(tmp_path)
    request = CreateTask(
        TaskContent("Use cleaner"), materials=(MaterialSelection("binding", MaterialQuantity("2")),)
    )
    receipt = commands.create("create", request)
    definition_id, work_id = resource(receipt)
    allocated = identifiers.count
    with store.read() as unit:
        item = unit.tasks.definition("home", definition_id)
        work = unit.tasks.occurrence("home", work_id)
        assert len(item.materials) == 1 and work.definition_snapshot == item
        assert item.materials[0].binding == binding()
        assert item.materials[0].planned_quantity.value == "2"
        local = unit.members.by_user("home", actor.human.ha_user_id)
        assert inventory.resolutions == [("home", local.member_id, "binding")]
    assert commands.create("create", request) == receipt and identifiers.count == allocated
    assert len(inventory.resolutions) == 1 and not inventory.movements()


def test_actual_completion_retains_work_intents_and_transaction_bound_inventory_confirmation(
    tmp_path,
):
    commands, child, store, _, identifiers, inventory, work = prepare_material_work(tmp_path)
    line = work.definition_snapshot.materials[0]
    request = CompleteTask(
        work.occurrence_id,
        work.revision,
        ("child",),
        90,
        (MaterialUsage(line.line_id, MaterialQuantity("1")),),
    )
    receipt = child.complete("complete", request)
    allocated = identifiers.count
    with store.read() as unit:
        done = unit.tasks.occurrence("home", work.occurrence_id)
        cycle = unit.tasks.cycle("home", done.current_cycle_id)
        assert cycle.verification.value == "pending"
        intents = unit.task_materials.list("home", cycle.cycle_id)
        assert len(intents) == 1
        value = intents[0]
        assert value.state.value == "posted" and value.quantity.value == "1"
        assert value.line == line and value.authorized_at_recording
        assert value.posting.movement_id == receipt.result.decode()["materials"][0]["movement_id"]
        assert value.recorded_by == "child" and value.performed_at == 90
        assert len(unit.audit.entries("home")) == len(unit.outbox.pending()) == 4
    assert len(inventory.movements()) == 1
    assert child.complete("complete", request) == receipt and identifiers.count == allocated
    assert len(inventory.settlements) == len(inventory.movements()) == 1


@pytest.mark.parametrize(
    "value",
    [
        [],
        "binding",
        ("binding",),
        tuple(MaterialSelection(str(i), MaterialQuantity("1")) for i in range(33)),
        (MaterialSelection("binding", MaterialQuantity("1")),) * 2,
    ],
)
def test_selection_requests_reject_unbounded_untyped_or_duplicate_values(value):
    from domus.domain.errors import InvalidInput
    from domus.domain.task_values import DefinitionState

    with pytest.raises(InvalidInput):
        CreateTask(TaskContent("Work"), materials=value)
    with pytest.raises(InvalidInput):
        UpdateTaskDefinition(
            "definition", 1, TaskContent("Work"), DefinitionState.ACTIVE, materials=value
        )


@pytest.mark.parametrize(
    "value",
    [
        [],
        "line",
        ("line",),
        tuple(MaterialUsage(str(i), MaterialQuantity("1")) for i in range(33)),
        (MaterialUsage("line", MaterialQuantity("1")),) * 2,
    ],
)
def test_completion_requests_reject_unbounded_untyped_or_duplicate_usages(value):
    from domus.domain.errors import InvalidInput

    with pytest.raises(InvalidInput):
        CompleteTask("occurrence", 1, ("member",), 90, value)


@pytest.mark.parametrize("change", ["missing", "foreign", "different_reference", "precision"])
def test_bad_catalog_selection_rejects_creation_before_allocating_task_identities(tmp_path, change):
    from domus.domain.errors import InvalidInput, StorageFailure

    commands, _, store, _, identifiers, inventory = configured(tmp_path)
    if change == "missing":
        inventory.bindings.clear()
    elif change == "foreign":
        inventory.bindings["binding"] = binding(household_id="other")
    elif change == "different_reference":
        inventory.bindings["binding"] = binding(reference_id="other")
    else:
        inventory.bindings["binding"] = binding(precision=0)
    allocated = identifiers.count
    with pytest.raises((InvalidInput, StorageFailure)):
        commands.create(
            "create",
            CreateTask(
                TaskContent("Work"),
                materials=(MaterialSelection("binding", MaterialQuantity("0.25")),),
            ),
        )
    assert identifiers.count == allocated and not inventory.movements()
    with store.read() as unit:
        assert unit.tasks.definitions("home") == () and unit.tasks.policy("home") is None
        assert len(unit.audit.entries("home")) == len(unit.outbox.pending()) == 1


@pytest.mark.parametrize("action", ["create", "update"])
def test_material_link_and_receipt_disclosure_require_current_inventory_permission(
    tmp_path, action
):
    from test_task_queries import queries

    from domus.domain.errors import Forbidden
    from domus.domain.identity import Permission, PermissionRule
    from domus.domain.task_values import DefinitionState

    commands, _, store, actor, _, inventory = configured(tmp_path)
    request = CreateTask(
        TaskContent("Work"), materials=(MaterialSelection("binding", MaterialQuantity("1")),)
    )
    original = commands.create("create", request)
    if action == "update":
        definition_id, _ = resource(original)
        request = UpdateTaskDefinition(
            definition_id, 1, TaskContent("Updated"), DefinitionState.ACTIVE, materials=()
        )
        original = commands.update_definition("update", request)
    with store.write() as unit:
        member = unit.members.by_user("home", actor.human.ha_user_id)
        unit.members.save(
            replace(
                member, exceptions=(PermissionRule(Permission.INVENTORY_MANAGE, False),), revision=2
            ),
            1,
        )
    call = commands.create if action == "create" else commands.update_definition
    with pytest.raises(Forbidden):
        call(action, request)
    with pytest.raises(Forbidden):
        queries(store, actor.current()).operation(original.operation_id)
    assert len(inventory.resolutions) == 1


def test_definition_edits_preserve_line_identity_until_inventory_target_changes_and_freeze_old_work(
    tmp_path,
):
    from domus.application.task_commands import CreateTaskOccurrence
    from domus.domain.task_values import DefinitionState

    commands, _, store, _, _, inventory, original = prepare_material_work(tmp_path)
    definition_id = original.definition_snapshot.definition_id
    line = original.definition_snapshot.materials[0]
    inventory.bindings["binding"] = binding(revision=2, label="Renamed cleaner")
    request = UpdateTaskDefinition(
        definition_id,
        1,
        TaskContent("New title"),
        DefinitionState.ACTIVE,
        materials=(MaterialSelection("binding", MaterialQuantity("3")),),
    )
    receipt = commands.update_definition("edit", request)
    assert receipt.result.decode()["materials"][0]["planned_quantity"] == "3"
    with store.read() as unit:
        edited = unit.tasks.definition("home", definition_id)
        assert (
            edited.materials[0].line_id == line.line_id
            and edited.materials[0].binding.revision == 2
        )
        assert unit.tasks.occurrence("home", original.occurrence_id) == original
    commands.update_definition(
        "rename",
        UpdateTaskDefinition(definition_id, 2, TaskContent("Only title"), DefinitionState.ACTIVE),
    )
    inventory.bindings["binding"] = binding(revision=3, location_id="new-location")
    commands.update_definition("retarget", replace(request, expected_revision=3))
    created = commands.create_occurrence("occurrence", CreateTaskOccurrence(definition_id))
    with store.read() as unit:
        current = unit.tasks.definition("home", definition_id)
        assert current.materials[0].line_id != line.line_id
        assert unit.tasks.occurrence("home", resource(created)[1]).definition_snapshot == current
        assert unit.tasks.occurrence("home", original.occurrence_id) == original
    commands.update_definition(
        "clear",
        UpdateTaskDefinition(
            definition_id, 4, TaskContent("No materials"), DefinitionState.ACTIVE, materials=()
        ),
    )
    with store.read() as unit:
        assert unit.tasks.definition("home", definition_id).materials == ()
        assert unit.tasks.occurrence("home", original.occurrence_id) == original


@pytest.mark.parametrize(
    "quantity,mode,pending,denied,expected,reason,movements",
    [
        (
            None,
            "review_on_completion",
            None,
            False,
            "pending_recording",
            "actual_quantity_required",
            0,
        ),
        ("0", "review_on_completion", None, False, "not_used", None, 0),
        (
            "1",
            "separate_recording",
            None,
            False,
            "pending_processing",
            "explicit_settlement_required",
            0,
        ),
        (
            "1",
            "review_on_completion",
            MaterialPendingReason.STOCK_SHORTAGE,
            False,
            "pending_regularization",
            "insufficient_stock",
            0,
        ),
        (
            "1",
            "review_on_completion",
            MaterialPendingReason.INVENTORY_UNAVAILABLE,
            False,
            "pending_processing",
            "inventory_unavailable",
            0,
        ),
        (
            "1",
            "review_on_completion",
            MaterialPendingReason.BINDING_CHANGED,
            False,
            "pending_regularization",
            "inventory_binding_changed",
            0,
        ),
        (
            "1",
            "review_on_completion",
            None,
            True,
            "pending_authorization",
            "material_permission_required",
            0,
        ),
        ("0", "review_on_completion", None, True, "not_used", None, 0),
        ("1", "review_on_completion", None, False, "posted", None, 1),
    ],
)
def test_valid_work_retains_distinct_unknown_zero_separate_shortage_unavailable_and_denied_outcomes(
    tmp_path, quantity, mode, pending, denied, expected, reason, movements
):
    from test_sqlite_task_integrity import validate

    from domus.domain.identity import Permission, PermissionRule
    from domus.domain.task_values import MaterialRecording, TaskOverrides

    commands, child, store, _, _, inventory, work = prepare_material_work(
        tmp_path, overrides=TaskOverrides(material_recording=MaterialRecording(mode))
    )
    inventory.pending = pending
    if denied:
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
    usages = (
        None
        if quantity is None
        else (
            MaterialUsage(
                work.definition_snapshot.materials[0].line_id, MaterialQuantity(quantity)
            ),
        )
    )
    request = CompleteTask(work.occurrence_id, work.revision, ("child",), 90, usages)
    result = child.complete("complete", request)
    outcome = result.result.decode()["materials"][0]
    assert outcome["state"] == expected and outcome["pending_reason"] == reason
    assert outcome["submitted_quantity"] == quantity
    assert len(inventory.movements()) == movements
    with store.read() as unit:
        saved = unit.task_materials.get("home", outcome["intent_id"])
        assert saved.authorized_at_recording is (not denied)
        assert saved.state.value == expected
        assert unit.tasks.occurrence("home", work.occurrence_id).state.value == "completed"
    validate(store)
    calls = len(inventory.settlements)
    assert child.complete("complete", request) == result and len(inventory.settlements) == calls


@pytest.mark.parametrize(
    "mode", ["disabled_scoped", "general_denial_only", "current_completion_denied"]
)
def test_task_scoped_authority_distinguishes_general_stock_access_and_current_performance_grants(
    tmp_path, mode
):
    from domus.domain.errors import Forbidden
    from domus.domain.identity import Permission, PermissionRule
    from domus.domain.task_values import TaskOverrides

    overrides = (
        TaskOverrides(task_scoped_material_consumption=False) if mode == "disabled_scoped" else None
    )
    _, child, store, _, _, inventory, work = prepare_material_work(tmp_path, overrides=overrides)
    permission = (
        Permission.TASKS_COMPLETE
        if mode == "current_completion_denied"
        else Permission.INVENTORY_MANAGE
    )
    with store.write() as unit:
        member = unit.members.get("home", "child")
        unit.members.save(
            replace(member, exceptions=(PermissionRule(permission, False),), revision=2), 1
        )
    request = CompleteTask(
        work.occurrence_id,
        work.revision,
        ("child",),
        90,
        (MaterialUsage(work.definition_snapshot.materials[0].line_id, MaterialQuantity("1")),),
    )
    if mode == "current_completion_denied":
        with pytest.raises(Forbidden):
            child.complete("complete", request)
        assert not inventory.settlements and not inventory.movements()
    else:
        outcome = child.complete("complete", request).result.decode()["materials"][0]
        assert outcome["state"] == (
            "pending_authorization" if mode == "disabled_scoped" else "posted"
        )
        assert len(inventory.movements()) == (0 if mode == "disabled_scoped" else 1)


def test_missing_optional_inventory_provider_keeps_performed_work_pending_and_replay_inert(
    tmp_path,
):
    _, child, store, _, _, inventory, work = prepare_material_work(tmp_path)
    child = replace(child, inventory_factory=None)
    request = CompleteTask(
        work.occurrence_id,
        work.revision,
        ("child",),
        90,
        (MaterialUsage(work.definition_snapshot.materials[0].line_id, MaterialQuantity("1")),),
    )
    result = child.complete("complete", request)
    assert result.result.decode()["materials"][0]["pending_reason"] == "inventory_unavailable"
    assert not inventory.movements() and not inventory.settlements
    assert (
        replace(child, inventory_factory=inventory.factory).complete("complete", request) == result
    )
    assert not inventory.movements() and not inventory.settlements


def test_absent_inventory_rejects_new_material_links_without_creating_catalog_or_tasks(tmp_path):
    from domus.domain.errors import IntegrationUnavailable

    commands, store, _, _ = fixture(tmp_path)
    with pytest.raises(IntegrationUnavailable):
        commands.create(
            "create",
            CreateTask(
                TaskContent("Work"),
                materials=(MaterialSelection("binding", MaterialQuantity("1")),),
            ),
        )
    with store.read() as unit:
        assert unit.tasks.definitions("home") == () and unit.tasks.policy("home") is None
        assert len(unit.audit.entries("home")) == 1


def test_inventory_child_effect_and_task_work_roll_back_together_when_audit_fails(
    tmp_path, monkeypatch
):
    from domus.domain.errors import StorageFailure
    from domus.infrastructure.sqlite import SQLiteAudit

    _, child, store, _, _, inventory, work = prepare_material_work(tmp_path)
    request = CompleteTask(
        work.occurrence_id,
        work.revision,
        ("child",),
        90,
        (MaterialUsage(work.definition_snapshot.materials[0].line_id, MaterialQuantity("1")),),
    )
    append = SQLiteAudit.append

    def fail(self, entry):
        if entry.command.action == "task.complete":
            raise StorageFailure("injected audit failure")
        append(self, entry)

    with monkeypatch.context() as patch:
        patch.setattr(SQLiteAudit, "append", fail)
        with pytest.raises(StorageFailure):
            child.complete("complete", request)
    assert len(inventory.settlements) == 1 and not inventory.movements()
    with store.read() as unit:
        assert unit.tasks.occurrence("home", work.occurrence_id) == work
        assert unit.tasks.cycles("home", work.occurrence_id) == ()
        assert len(unit.audit.entries("home")) == len(unit.outbox.pending()) == 3
    result = child.complete("complete", request)
    assert result.result.decode()["materials"][0]["state"] == "posted"
    assert len(inventory.movements()) == 1


def test_completed_database_commit_then_lost_return_recovers_without_another_material_effect(
    tmp_path,
):
    from contextlib import contextmanager

    from domus.domain.errors import StorageFailure

    _, child, store, _, _, inventory, work = prepare_material_work(tmp_path)
    request = CompleteTask(
        work.occurrence_id,
        work.revision,
        ("child",),
        90,
        (MaterialUsage(work.definition_snapshot.materials[0].line_id, MaterialQuantity("1")),),
    )

    class LostReturn:
        def read(self):
            return store.read()

        @contextmanager
        def write(self):
            with store.write() as unit:
                yield unit
            raise StorageFailure("injected loss after real commit")

    with pytest.raises(StorageFailure):
        replace(child, transactions=LostReturn()).complete("complete", request)
    assert len(inventory.movements()) == len(inventory.settlements) == 1
    result = child.complete("complete", request)
    assert result.result.decode()["materials"][0]["state"] == "posted"
    assert len(inventory.movements()) == len(inventory.settlements) == 1
    with store.read() as unit:
        assert len(unit.tasks.cycles("home", work.occurrence_id)) == 1
        assert len(unit.audit.entries("home")) == len(unit.outbox.pending()) == 4


def test_concurrent_different_key_completions_have_one_cycle_receipt_and_material_effect(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from domus.domain.errors import Conflict

    _, child, store, _, _, inventory, work = prepare_material_work(tmp_path)
    request = CompleteTask(
        work.occurrence_id,
        work.revision,
        ("child",),
        90,
        (MaterialUsage(work.definition_snapshot.materials[0].line_id, MaterialQuantity("1")),),
    )
    barrier = Barrier(2)

    def submit(key):
        barrier.wait()
        try:
            return child.complete(key, request)
        except Conflict as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(submit, ("first", "second")))
    assert sum(isinstance(value, Conflict) for value in outcomes) == 1
    assert len(inventory.movements()) == len(inventory.settlements) == 1
    with store.read() as unit:
        assert len(unit.tasks.cycles("home", work.occurrence_id)) == 1
        assert len(unit.audit.entries("home")) == len(unit.outbox.pending()) == 4


def test_permission_stock_approval_and_reopen_changes_never_auto_settle_old_usage(tmp_path):
    from domus.application.task_commands import ReopenTask, VerifyTask
    from domus.domain.identity import Permission, PermissionRule
    from domus.domain.task_values import VerificationState

    commands, child, store, _, _, inventory, work = prepare_material_work(tmp_path)
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
    request = CompleteTask(
        work.occurrence_id,
        work.revision,
        ("child",),
        90,
        (MaterialUsage(work.definition_snapshot.materials[0].line_id, MaterialQuantity("1")),),
    )
    result = child.complete("complete", request)
    outcome = result.result.decode()["materials"][0]
    assert outcome["state"] == "pending_authorization"
    cycle_id = outcome["cycle_id"]
    with store.write() as unit:
        member = unit.members.get("home", "child")
        unit.members.save(replace(member, exceptions=(), revision=3), 2)
    commands.verify(
        "approve", VerifyTask(work.occurrence_id, 3, cycle_id, VerificationState.APPROVED)
    )
    commands.reopen("reopen", ReopenTask(work.occurrence_id, 4, cycle_id, "Work again"))
    inventory.pending = None
    assert child.complete("complete", request) == result
    with store.read() as unit:
        assert (
            unit.task_materials.get("home", outcome["intent_id"]).state.value
            == "pending_authorization"
        )
        assert unit.tasks.cycle("home", cycle_id).closed_at is not None
    assert not inventory.settlements and not inventory.movements()


@pytest.mark.parametrize("wrong", ["foreign_line", "precision", "unrelated_usage"])
def test_invalid_usage_fails_before_work_intents_or_inventory_effects(tmp_path, wrong):
    from domus.domain.errors import InvalidInput

    commands, child, store, _, _, inventory, work = prepare_material_work(
        tmp_path, selected=wrong != "unrelated_usage"
    )
    if wrong == "precision":
        quantity = MaterialQuantity("0.000001")
        # Use a real new occurrence with a frozen precision-zero binding.
        inventory.bindings["binding"] = binding(precision=0)
        created = commands.create(
            "zero-precision",
            CreateTask(
                TaskContent("Whole units"),
                materials=(MaterialSelection("binding", MaterialQuantity("1")),),
            ),
        )
        from domus.application.task_commands import AssignTask

        oid = resource(created)[1]
        commands.assign("assign-whole", AssignTask(oid, 1, ("child",)))
        with store.read() as unit:
            work = unit.tasks.occurrence("home", oid)
        identity = work.definition_snapshot.materials[0].line_id
    else:
        identity, quantity = "foreign-line", MaterialQuantity("1")
    before = len(inventory.settlements)
    with pytest.raises(InvalidInput):
        child.complete(
            "invalid",
            CompleteTask(
                work.occurrence_id,
                work.revision,
                ("child",),
                90,
                (MaterialUsage(identity, quantity),),
            ),
        )
    with store.read() as unit:
        assert unit.tasks.occurrence("home", work.occurrence_id) == work
        assert unit.tasks.cycles("home", work.occurrence_id) == ()
    assert len(inventory.settlements) == before and not inventory.movements()


def test_two_material_lines_preserve_success_and_shortage_separately_under_one_receipt(tmp_path):
    from test_sqlite_task_integrity import validate

    from domus.application.task_commands import AssignTask

    commands, child, store, _, _, inventory = configured(tmp_path)
    inventory.bindings["second"] = binding(reference_id="second", product_id="other-product")
    inventory.pending_by_reference["second"] = MaterialPendingReason.STOCK_SHORTAGE
    selections = tuple(
        MaterialSelection(reference, MaterialQuantity("2")) for reference in ("binding", "second")
    )
    _, oid = resource(
        commands.create("create", CreateTask(TaskContent("Two materials"), materials=selections))
    )
    commands.assign("assign", AssignTask(oid, 1, ("child",)))
    with store.read() as unit:
        work = unit.tasks.occurrence("home", oid)
    usages = tuple(
        MaterialUsage(line.line_id, MaterialQuantity("1"))
        for line in work.definition_snapshot.materials
    )
    request = CompleteTask(oid, 2, ("child",), 90, usages)
    receipt = child.complete("complete", request)
    result = receipt.result.decode()["materials"]
    assert [row["state"] for row in result] == ["posted", "pending_regularization"]
    assert result[0]["movement_id"] and result[1]["movement_id"] is None
    assert result[0]["action_required"] is None and result[1]["action_required"]
    assert len(inventory.movements()) == 1 and len(inventory.settlements) == 2
    assert child.complete("complete", request) == receipt
    validate(store)


@pytest.mark.parametrize(
    "policy,member_allow,expected",
    [
        (False, None, "pending_authorization"),
        (False, True, "posted"),
        (True, False, "pending_authorization"),
    ],
)
def test_scoped_material_grants_follow_current_profile_and_member_precedence(
    tmp_path, policy, member_allow, expected
):
    from domus.domain.identity import Permission, PermissionRule, ProfileRule, Role

    _, child, store, _, _, inventory, work = prepare_material_work(tmp_path)
    with store.write() as unit:
        current = unit.policies.get("home")
        unit.policies.save(
            replace(
                current,
                adjustments=(ProfileRule(Role.RESTRICTED, Permission.TASKS_MATERIAL_USE, policy),),
                revision=2,
            ),
            1,
        )
        if member_allow is not None:
            member = unit.members.get("home", "child")
            unit.members.save(
                replace(
                    member,
                    exceptions=(PermissionRule(Permission.TASKS_MATERIAL_USE, member_allow),),
                    revision=2,
                ),
                1,
            )
    request = CompleteTask(
        work.occurrence_id,
        work.revision,
        ("child",),
        90,
        (MaterialUsage(work.definition_snapshot.materials[0].line_id, MaterialQuantity("1")),),
    )
    result = child.complete("complete", request).result.decode()["materials"][0]
    assert result["state"] == expected
    assert len(inventory.movements()) == (1 if expected == "posted" else 0)


def test_general_inventory_authority_can_use_linked_materials_with_scoped_mode_disabled(tmp_path):
    from domus.domain.identity import Role
    from domus.domain.task_values import TaskOverrides

    _, child, store, _, _, inventory, work = prepare_material_work(
        tmp_path, overrides=TaskOverrides(task_scoped_material_consumption=False)
    )
    with store.write() as unit:
        member = unit.members.get("home", "child")
        unit.members.save(replace(member, role=Role.ADULT, revision=2), 1)
    receipt = child.complete(
        "complete",
        CompleteTask(
            work.occurrence_id,
            2,
            ("child",),
            90,
            (MaterialUsage(work.definition_snapshot.materials[0].line_id, MaterialQuantity("1")),),
        ),
    )
    assert receipt.result.decode()["materials"][0]["state"] == "posted"
    assert len(inventory.movements()) == 1


@pytest.mark.parametrize(
    "change",
    ["household", "work", "cycle", "line", "recorder", "performed", "created", "mode", "action"],
)
def test_material_authority_rejects_detached_source_and_untyped_actions(tmp_path, change):
    from domus.application.task_authorization import TaskAccess, TaskMaterialAccess
    from domus.domain.errors import Forbidden, StorageFailure
    from domus.domain.task_material_values import MaterialAction
    from domus.domain.task_materials import MaterialIntent
    from domus.domain.task_values import MaterialRecording

    _, child, store, _, _, _, work = prepare_material_work(tmp_path)
    receipt = child.complete("complete", CompleteTask(work.occurrence_id, 2, ("child",), 90))
    outcome = receipt.result.decode()["materials"][0]
    with store.read() as unit:
        stored = unit.task_materials.get("home", outcome["intent_id"])
        value = MaterialIntent.record(
            stored.intent_id,
            stored.household_id,
            stored.occurrence_id,
            stored.cycle_id,
            stored.line,
            MaterialQuantity("1"),
            recorded_by=stored.recorded_by,
            performed_at=stored.performed_at,
            recorded_at=stored.created_at,
            recording_mode=stored.recording_mode,
            authorized=True,
        )
        if change == "household":
            value = replace(
                value,
                household_id="other",
                line=replace(value.line, binding=replace(value.line.binding, household_id="other")),
            )
        elif change == "work":
            value = replace(value, occurrence_id="missing")
        elif change == "cycle":
            value = replace(value, cycle_id="missing")
        elif change == "line":
            value = replace(value, line=replace(value.line, planned_quantity=MaterialQuantity("3")))
        elif change == "recorder":
            value = replace(value, recorded_by="other")
        elif change == "performed":
            value = replace(value, performed_at=91)
        elif change == "created":
            value = replace(value, created_at=101, updated_at=101)
        elif change == "mode":
            value = replace(value, recording_mode=MaterialRecording.SEPARATE)
        authority = TaskMaterialAccess(TaskAccess(child.actor.current()), unit, "home")
        with pytest.raises((Forbidden, StorageFailure)):
            authority.require(value, None if change == "action" else MaterialAction.POST)
        with pytest.raises(Forbidden):
            authority.link_actor("other")


@pytest.mark.parametrize(
    "field,raw",
    [
        ("materials", None),
        ("materials", {}),
        (
            "materials",
            [{"reference_id": "binding", "planned_quantity": "1", "location_id": "forged"}],
        ),
        ("materials", [{"reference_id": "binding", "planned_quantity": 1.0}]),
        ("materials", [{"reference_id": "bad/id", "planned_quantity": "1"}]),
        ("materials", [{"reference_id": "binding", "planned_quantity": "01"}]),
        ("materials", [{"reference_id": "binding", "planned_quantity": "1"}] * 2),
        ("materials", [{"reference_id": str(i), "planned_quantity": "1"} for i in range(33)]),
        ("material_usages", None),
        ("material_usages", "line"),
        ("material_usages", [{"line_id": "line", "quantity": {"value": "1"}}]),
        ("material_usages", [{"line_id": "line", "quantity": "1"}] * 2),
    ],
)
def test_new_material_fields_in_retained_requests_are_strictly_validated(field, raw):
    from domus.application.task_requests import validate_recorded_material_request
    from domus.domain.errors import InvalidInput

    with pytest.raises(InvalidInput):
        validate_recorded_material_request({field: raw})


@pytest.mark.parametrize("state", ["posted", "authorization", "stock", "processing"])
def test_maximum_completion_and_child_material_outcomes_fit_the_atomic_evidence_budget(state):
    from domus.application.task_commands import _change, _cycle_result
    from domus.application.task_material_commands import material_result
    from domus.domain.identity import Role
    from domus.domain.storage import JsonDocument
    from domus.domain.task_material_values import MaterialBinding, MaterialLine
    from domus.domain.task_materials import MaterialIntent, MaterialPosting
    from domus.domain.task_values import (
        OccurrenceState,
        TaskContent,
        TaskPerformer,
        TaskRequirement,
        TaskRules,
        VerificationState,
    )
    from domus.domain.tasks import TaskCycle, TaskDefinition

    maximum = 2**63 - 1
    household, definition_id, occurrence_id, cycle_id = (
        letter * 128 for letter in ("h", "d", "o", "c")
    )
    performers = tuple(f"member{index:02}" + "x" * 120 for index in range(32))
    prerequisites = tuple(f"prior{index:02}" + "x" * 121 for index in range(32))
    subtasks = tuple(f"child{index:02}" + "x" * 121 for index in range(32))
    lines = tuple(
        MaterialLine(
            f"line{index:03}" + "x" * 121,
            MaterialBinding(
                household,
                f"ref{index:03}" + "x" * 122,
                "p" * 128,
                "u" * 128,
                "l" * 128,
                maximum,
                6,
                "l" * 160,
            ),
            MaterialQuantity("999999999999.999999"),
        )
        for index in range(32)
    )
    definition = TaskDefinition(
        definition_id, household, TaskContent("t" * 160), 1, revision=maximum, materials=lines
    )
    original = definition.new_occurrence(
        occurrence_id,
        1,
        assignees=performers,
        prerequisites=prerequisites,
        required_subtasks=subtasks,
    )
    cycle = TaskCycle.record(
        cycle_id,
        household,
        occurrence_id,
        recorded_by=performers[0],
        performers=tuple(TaskPerformer(identity, Role.ADMINISTRATOR) for identity in performers),
        rules=TaskRules(point_value_minor=1_000_000),
        definition_revision=maximum,
        task_policy_revision=maximum,
        identity_policy_revision=maximum,
        performed_at=maximum,
        recorded_at=maximum,
    )
    work = original.complete(
        cycle,
        requirements=tuple(
            TaskRequirement(identity, OccurrenceState.COMPLETED, VerificationState.NONE)
            for identity in (*prerequisites, *subtasks)
        ),
    )
    outcomes = []
    for index, line in enumerate(lines):
        value = MaterialIntent.record(
            f"intent{index:02}" + "x" * 120,
            household,
            occurrence_id,
            cycle_id,
            line,
            line.planned_quantity,
            recorded_by=performers[0],
            performed_at=maximum,
            recorded_at=maximum,
            recording_mode=cycle.rules.material_recording,
            authorized=state != "authorization",
        )
        if state == "posted":
            value = value.confirm(
                MaterialPosting(
                    value.intent_id,
                    household,
                    occurrence_id,
                    cycle_id,
                    line.line_id,
                    line.binding.reference_id,
                    maximum,
                    1,
                    1,
                    value.quantity,
                    f"operation{index:02}" + "x" * 117,
                    f"movement{index:02}" + "x" * 118,
                    maximum,
                ),
                maximum,
            )
        elif state in ("stock", "processing"):
            value = value.defer(
                MaterialPendingReason.STOCK_SHORTAGE
                if state == "stock"
                else MaterialPendingReason.INVENTORY_UNAVAILABLE,
                maximum,
            )
        outcomes.append(material_result(value))
    result = _cycle_result(work, cycle).decode()
    result["materials"] = outcomes
    request = CompleteTask(
        occurrence_id,
        1,
        performers,
        maximum,
        tuple(MaterialUsage(line.line_id, line.planned_quantity) for line in lines),
    )
    change = _change("task.completed", request, JsonDocument.from_value(result))
    for document in (change.result, change.audit_detail, change.event_payload):
        assert len(document.encoded.encode()) <= 65536
    assert len(change.result.decode()["materials"]) == 32


@pytest.mark.parametrize("field", ["materials", "material_usages"])
def test_corrupt_new_fields_in_a_consistent_evidence_bundle_fail_closed_before_disclosure(
    tmp_path, field
):
    from domus.application.task_authorization import recorded_request
    from domus.domain.errors import StorageFailure
    from domus.domain.storage import JsonDocument

    commands, child, store, _, _, _, work = prepare_material_work(tmp_path)
    if field == "materials":
        with store.read() as unit:
            receipt = next(
                entry
                for entry in unit.audit.entries("home")
                if entry.command.action == "task.create"
            )
            original = unit.tasks.operation(
                "home", receipt.command.actor_id, receipt.operation_id
            ).evidence
    else:
        result = child.complete(
            "complete",
            CompleteTask(
                work.occurrence_id,
                2,
                ("child",),
                90,
                (
                    MaterialUsage(
                        work.definition_snapshot.materials[0].line_id, MaterialQuantity("1")
                    ),
                ),
            ),
        )
        with store.read() as unit:
            original = unit.tasks.operation("home", "ha_child", result.operation_id).evidence
    detail = original.audit.detail.decode()
    detail["request"][field] = None
    payload = JsonDocument.from_value(detail["request"])
    changed = replace(
        original,
        receipt=replace(original.receipt, payload_fingerprint=payload.fingerprint),
        audit=replace(original.audit, detail=JsonDocument.from_value(detail)),
    )
    with pytest.raises(StorageFailure, match="invalid_task_operation"):
        recorded_request(changed)


def test_restore_of_material_work_retains_proof_and_never_reposts_historical_usage(
    tmp_path,
):
    from test_activation_compatibility import identity_at
    from test_sqlite_snapshots import Clock
    from test_task_queries import queries

    from domus.infrastructure.owned_storage import open_storage
    from domus.infrastructure.sqlite_activation import SQLiteActivation
    from domus.infrastructure.sqlite_restoration import SQLiteRestorations
    from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots

    root = tmp_path / "source"
    root.mkdir(mode=0o700)
    _, child, store, _, _, inventory, work = prepare_material_work(root)
    # This fictional consumer has its own attached SQL fixture, outside the owned application root.
    external = tmp_path / "fixture-inventory.sqlite3"
    inventory.path.rename(external)
    inventory.path = external
    identity_at(root, store.installation)
    archive, target = tmp_path / "checkpoint", tmp_path / "prepared"
    checkpoint = SQLiteSnapshots(store, archive, store.installation, Clock()).create(
        "before-material-work"
    )
    request = CompleteTask(
        work.occurrence_id,
        work.revision,
        ("child",),
        90,
        (MaterialUsage(work.definition_snapshot.materials[0].line_id, MaterialQuantity("1")),),
    )
    original = child.complete("complete", request)
    outcome = original.result.decode()["materials"][0]
    source_bytes = store.path.read_bytes()
    before_calls, before_movements = len(inventory.settlements), inventory.movements()
    prepared = SQLiteRestorations(
        store, archive, target, store.installation, Clock(), checkpoint
    ).prepare("restore-material-work")
    assert prepared.current_operations == 3 and prepared.operation_count == 4
    assert store.path.read_bytes() == source_bytes
    activation = SQLiteActivation(root, store.installation, Clock(), target).activate()
    assert activation.state == "active"
    selected = open_storage(root, "edge")
    try:
        service = replace(child, transactions=selected.database)
        restored = service.complete("complete", request)
        assert restored.historical and restored.operation_id == original.operation_id
        assert restored.result == original.result
        assert (
            len(inventory.settlements) == before_calls and inventory.movements() == before_movements
        )
        query = queries(selected.database, child.actor.current())
        operation = query.operation(original.operation_id)
        assert operation.receipt.historical
        history = query.history(work.occurrence_id).items
        item = next(item for item in history if item.operation_id == original.operation_id)
        assert item.outbox_delivery == "suppressed"
        with selected.database.read() as unit:
            assert unit.tasks.occurrence("home", work.occurrence_id) == work
            assert unit.tasks.cycle("home", outcome["cycle_id"]) is None
            assert unit.task_materials.get("home", outcome["intent_id"]) is None
            assert len(unit.audit.entries("home")) == len(unit.outbox.pending()) == 3
    finally:
        selected.close()


def test_configured_provider_unavailability_at_binding_keeps_valid_completion_pending(tmp_path):
    from domus.domain.errors import IntegrationUnavailable

    _, child, store, _, _, inventory, work = prepare_material_work(tmp_path)

    def unavailable(_unit):
        raise IntegrationUnavailable("inventory_unavailable")

    request = CompleteTask(
        work.occurrence_id,
        2,
        ("child",),
        90,
        (MaterialUsage(work.definition_snapshot.materials[0].line_id, MaterialQuantity("1")),),
    )
    result = replace(child, inventory_factory=unavailable).complete("complete", request)
    assert result.result.decode()["materials"][0]["pending_reason"] == "inventory_unavailable"
    assert not inventory.settlements and not inventory.movements()


def test_unexpected_provider_binding_failure_does_not_become_a_successful_pending_command(tmp_path):
    _, child, store, _, _, inventory, work = prepare_material_work(tmp_path)

    def broken(_unit):
        raise RuntimeError("injected unexpected provider failure")

    request = CompleteTask(
        work.occurrence_id,
        2,
        ("child",),
        90,
        (MaterialUsage(work.definition_snapshot.materials[0].line_id, MaterialQuantity("1")),),
    )
    with pytest.raises(RuntimeError):
        replace(child, inventory_factory=broken).complete("complete", request)
    with store.read() as unit:
        assert unit.tasks.occurrence("home", work.occurrence_id) == work
        assert unit.tasks.cycles("home", work.occurrence_id) == ()
        assert len(unit.audit.entries("home")) == len(unit.outbox.pending()) == 3
    assert not inventory.settlements and not inventory.movements()
