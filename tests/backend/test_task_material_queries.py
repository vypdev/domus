"""Material reads preserve cycle scope, current outcomes and immutable original receipts."""

from dataclasses import replace

import pytest
from test_task_commands import resource
from test_task_material_commands import configured
from test_task_materials import intent, posting
from test_task_queries import queries
from test_tasks import cycle, definition

from domus.application.task_commands import CompleteTask, CreateTask, ReopenTask
from domus.application.task_material_commands import material_result
from domus.domain.errors import Forbidden, InvalidInput, NotFound, StorageFailure
from domus.domain.identity import Permission, PermissionRule
from domus.domain.task_material_policy import cycle_materials
from domus.domain.task_material_values import MaterialQuantity, MaterialSelection, MaterialUsage
from domus.domain.task_values import MaterialRecording


def source():
    value = intent()
    work = definition(materials=(value.line,)).new_occurrence("occurrence", 20)
    attempt = cycle(recorded_by="recorder", performed_at=90, recorded_at=100)
    return work, attempt, value


def test_pure_material_source_supports_open_closed_and_unplanned_cycles():
    work, attempt, value = source()
    assert cycle_materials(work, attempt, (value,)) == (value,)
    assert cycle_materials(work, replace(attempt, closed_at=101), (value,)) == (value,)
    assert cycle_materials(definition().new_occurrence("occurrence", 20), attempt, ()) == ()


@pytest.mark.parametrize("values", [None, [], (None,), (), (intent(), intent()), (intent(),) * 33])
def test_source_rejects_missing_duplicate_untyped_and_unbounded_intents(values):
    work, attempt, _ = source()
    with pytest.raises(InvalidInput, match="invalid_material_references"):
        cycle_materials(work, attempt, values)


@pytest.mark.parametrize(
    "changes",
    [
        {"household_id": "other"},
        {"occurrence_id": "other"},
        {"definition_revision": 2},
    ],
)
def test_source_rejects_a_cycle_outside_the_frozen_occurrence(changes):
    work, attempt, value = source()
    with pytest.raises(InvalidInput, match="invalid_material_references"):
        cycle_materials(work, replace(attempt, **changes), (value,))


@pytest.mark.parametrize(
    "changes",
    [
        {"occurrence_id": "other"},
        {"cycle_id": "other"},
        {"recorded_by": "other"},
        {"performed_at": 89},
        {"created_at": 99},
    ],
)
def test_source_rejects_rewritten_original_attribution(changes):
    work, attempt, value = source()
    with pytest.raises(InvalidInput, match="invalid_material_references"):
        cycle_materials(work, attempt, (replace(value, **changes),))


@pytest.mark.parametrize("kind", ["household", "line", "mode", "unknown", "same_intent"])
def test_source_rejects_foreign_or_rewritten_line_bindings_and_recording_policy(kind):
    work, attempt, value = source()
    if kind == "household":
        line = replace(value.line, binding=replace(value.line.binding, household_id="other"))
        values = (replace(value, household_id="other", line=line),)
    elif kind == "line":
        values = (replace(value, line=replace(value.line, planned_quantity=MaterialQuantity("3"))),)
    elif kind == "mode":
        values = (replace(value, recording_mode=MaterialRecording.SEPARATE),)
    else:
        line = replace(
            value.line, line_id="second", binding=replace(value.line.binding, reference_id="second")
        )
        values = (value, replace(value, line=line))
        if kind == "same_intent":
            work = replace(
                work,
                definition_snapshot=replace(work.definition_snapshot, materials=(value.line, line)),
            )
    with pytest.raises(InvalidInput, match="invalid_material_references"):
        cycle_materials(work, attempt, values)


def test_source_returns_frozen_line_order_instead_of_repository_identity_order():
    work, attempt, value = source()
    line = replace(
        value.line, line_id="second", binding=replace(value.line.binding, reference_id="second")
    )
    first, second = replace(value, intent_id="z"), replace(value, intent_id="a", line=line)
    work = replace(
        work, definition_snapshot=replace(work.definition_snapshot, materials=(value.line, line))
    )
    assert cycle_materials(work, attempt, (second, first)) == (first, second)


def completed(tmp_path):
    commands, _, store, actor, ids, inventory = configured(tmp_path)
    created = commands.create(
        "create",
        CreateTask(
            definition().content, materials=(MaterialSelection("binding", MaterialQuantity("2")),)
        ),
    )
    _, oid = resource(created)
    with store.read() as unit:
        member = unit.members.by_user("home", actor.human.ha_user_id)
        line = unit.tasks.occurrence("home", oid).definition_snapshot.materials[0]
    request = CompleteTask(
        oid, 1, (member.member_id,), 90, (MaterialUsage(line.line_id, MaterialQuantity("2")),)
    )
    receipt = commands.complete("complete", request)
    return commands, store, actor, ids, inventory, oid, receipt, request


def test_queries_show_current_outcome_without_changing_the_original_receipt_or_inventory(tmp_path):
    commands, store, actor, ids, inventory, oid, receipt, request = completed(tmp_path)
    original = receipt.result.decode()["materials"][0]
    service = queries(store, actor.current())
    attempt_id = original["cycle_id"]
    with store.write() as unit:
        value = unit.task_materials.get("home", original["intent_id"])
        changed = value.correct(MaterialQuantity("3"), "Recorded total correction", 110)
        unit.task_materials.save(changed, value.revision)
    pending = service.materials(oid, attempt_id).materials[0]
    assert pending.quantity == "3" and pending.confirmed_quantity == "2"
    assert pending.confirmed_effect_revision == value.posting.effect_revision
    assert pending.posted_at == value.posting.posted_at
    with store.write() as unit:
        confirmed = changed.confirm(posting(changed, posted_at=111), 112)
        unit.task_materials.save(confirmed, changed.revision)
    count, calls = ids.count, len(inventory.settlements)
    view = service.materials(oid, attempt_id)
    outcome = view.materials[0]
    assert view.occurrence_id == oid and view.cycle.cycle_id == attempt_id
    assert outcome.quantity == "3" and outcome.submitted_quantity == "2"
    assert outcome.confirmed_quantity == "3" and outcome.confirmed_effect_revision == 2
    assert outcome.posted_at == 111
    assert outcome.state == "corrected" and outcome.revision == confirmed.revision
    assert service.occurrence(oid).materials == view.materials
    assert commands.complete("complete", request).result == receipt.result
    assert receipt.result.decode()["materials"][0] == original == material_result(value)
    assert ids.count == count and len(inventory.settlements) == calls
    reopened = commands.reopen("reopen", ReopenTask(oid, 2, attempt_id, "Another performance"))
    assert reopened.result.decode()["state"] == "available"
    assert service.occurrence(oid).materials == ()
    archived = service.materials(oid, attempt_id)
    assert archived.cycle.closed_at is not None and archived.materials == view.materials


@pytest.mark.parametrize("occurrence_id,cycle_id", [("missing", "missing"), (None, "missing")])
def test_material_queries_do_not_disclose_missing_or_unrelated_cycles(
    tmp_path, occurrence_id, cycle_id
):
    _, store, actor, _, _, oid, receipt, _ = completed(tmp_path)
    service = queries(store, actor.current())
    with pytest.raises(NotFound):
        service.materials(oid if occurrence_id is None else occurrence_id, cycle_id)
    with pytest.raises(InvalidInput):
        service.materials(oid, "invalid/identity")
    with store.write() as unit:
        person = unit.members.by_user("home", actor.human.ha_user_id)
        unit.members.save(
            replace(person, exceptions=(PermissionRule(Permission.TASKS_READ, False),), revision=2),
            1,
        )
    with pytest.raises(Forbidden):
        service.materials("missing", receipt.result.decode()["cycle"]["cycle_id"])


def test_material_query_fails_closed_on_missing_sources_in_both_views(tmp_path, monkeypatch):
    from domus.infrastructure.sqlite_task_materials import SQLiteTaskMaterials

    _, store, actor, _, _, oid, receipt, _ = completed(tmp_path)
    monkeypatch.setattr(SQLiteTaskMaterials, "list", lambda *args, **kwargs: ())
    service = queries(store, actor.current())
    for read in (
        lambda: service.occurrence(oid),
        lambda: service.materials(oid, receipt.result.decode()["cycle"]["cycle_id"]),
    ):
        with pytest.raises(StorageFailure, match="invalid_material_references"):
            read()
