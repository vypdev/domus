"""Cycle closure survives generation changes and never fabricates human work or compensation."""

from dataclasses import FrozenInstanceError, replace

import pytest
from test_relative_recurrence_records import values
from test_tasks import definition

from domus.domain.errors import InvalidInput
from domus.domain.identity import Role
from domus.domain.relative_lifecycle import (
    RelativeClosure,
    RelativeClosureKind,
    RelativeEventOutcome,
    SuccessorDisposition,
    WorkHistory,
    successor_disposition,
)
from domus.domain.relative_recurrence import RelativeOperation
from domus.domain.storage import CommandKey, JsonDocument, Receipt, RestorationProvenance
from domus.domain.task_values import OccurrenceState, TaskPerformer, VerificationState


@pytest.mark.parametrize(
    "status,damage",
    [
        (s, d)
        for s in ("generated", "reopened")
        for d in ("status", "schedule", "shape", "kind", "historical")
    ]
    + [("generated", "occurrence"), ("generated", "slot")]
    + [("cancel", d) for d in ("status", "kind", "key", "historical", "occurrence")],
)
def test_c37_outcome_preserves_original_receipt_meaning_and_rejects_mixed_valid_fields(
    status, damage
):
    value = closure(
        kind=RelativeClosureKind.REOPENED if status == "reopened" else RelativeClosureKind.GENERATED
    )
    occurrence = None if value.successor is None else value.successor.occurrence_id
    body = {"version": 1, "relative_closure": value.document().decode()}
    command = value.operation.command
    if status == "generated":
        body.update(
            slot_key=value.successor.key,
            occurrence_id=occurrence,
            schedule_id=value.schedule.schedule_id,
        )
    if status == "cancel":
        command = replace(command, action="recurrence.relative.invalidate", key=value.key)
        body = {
            "version": 1,
            "closure_key": value.key,
            "disposition": status,
            "occurrence_id": occurrence,
        }
    receipt = Receipt(
        command,
        "a" * 64,
        value.operation.operation_id,
        JsonDocument.from_value(body),
        value.recorded_at,
    )
    original = RelativeEventOutcome(status, value.schedule.schedule_id, receipt, occurrence)
    historical = replace(receipt, restoration=RestorationProvenance("restored", False))
    assert replace(original, receipt=historical).status == status
    if status != "reopened":
        assert (
            RelativeEventOutcome(
                "historical_absent", original.schedule_id, historical, occurrence
            ).receipt
            == historical
        )
    changed = {
        "status": status,
        "schedule_id": original.schedule_id,
        "receipt": receipt,
        "occurrence_id": occurrence,
    }
    if damage == "status":
        changed["status"] = "reopened" if status == "generated" else "generated"
    if damage == "schedule":
        changed["schedule_id"] = "other"
    if damage == "occurrence":
        changed["occurrence_id"] = None
    if damage == "historical":
        changed["status"] = "historical_absent"
    if damage == "shape":
        body["relative_closure"] = None
    if damage == "kind":
        if status == "cancel":
            body["disposition"] = "retained"
        else:
            body["relative_closure"]["kind"] = "rejected"
    if damage == "slot":
        body["slot_key"] = "other"
    if damage == "key":
        body["closure_key"] = "other"
    changed["receipt"] = replace(receipt, result=JsonDocument.from_value(body))
    with pytest.raises(InvalidInput, match="invalid_relative_outcome"):
        RelativeEventOutcome(**changed)


def closure(*, kind=RelativeClosureKind.GENERATED):
    schedule, _, slot, cycle = values(restricted=kind is RelativeClosureKind.REJECTED)
    if kind is RelativeClosureKind.REJECTED:
        cycle = cycle.verify(
            VerificationState.REJECTED,
            TaskPerformer("reviewer", Role.ADULT),
            cycle.recorded_at + 1,
            "Please repeat",
        )
    if kind is RelativeClosureKind.REOPENED:
        cycle = cycle.close(cycle.recorded_at + 1)
    slot = slot if kind is RelativeClosureKind.GENERATED else None
    key = RelativeClosure.cycle_key(schedule, cycle, values()[2].installation)
    command = (
        slot.command
        if slot
        else CommandKey("home", "system:recurrence", "recurrence.relative.close", key)
    )
    return RelativeClosure(
        values()[2].installation,
        schedule,
        cycle,
        kind,
        slot.created_at if slot else cycle.recorded_at + 100,
        RelativeOperation(command, "closed-operation"),
        slot,
    )


def successor(value, *, state=OccurrenceState.AVAILABLE):
    work = definition(created_at=100).new_occurrence(
        value.successor.occurrence_id, value.recorded_at
    )
    if state is OccurrenceState.COMPLETED:
        done = replace(
            value.cycle.completion_snapshot(),
            occurrence_id=work.occurrence_id,
            cycle_id="downstream-cycle",
            performed_at=work.created_at + 1,
            recorded_at=work.created_at + 1,
        )
        return work.complete(done, requirements=())
    return replace(
        work,
        state=state,
        assignee_ids=("adult",)
        if state in (OccurrenceState.ASSIGNED, OccurrenceState.IN_PROGRESS)
        else (),
        state_reason="Previously stopped"
        if state in (OccurrenceState.CANCELLED, OccurrenceState.SKIPPED, OccurrenceState.BLOCKED)
        else "",
    )


@pytest.mark.parametrize("kind", list(RelativeClosureKind))
def test_closure_keeps_exact_fact_and_original_proof_without_closing_human_cycle(kind):
    value = closure(kind=kind)
    document = value.document()
    receipt = Receipt(
        value.operation.command,
        "a" * 64,
        value.operation.operation_id,
        JsonDocument.from_value({"relative_closure": document.decode()}),
        value.recorded_at,
    )
    assert value.matches_receipt(receipt)
    assert value.matches_receipt(
        replace(receipt, restoration=RestorationProvenance("restored", False))
    )
    assert not value.matches_receipt(None)
    assert not value.matches_receipt(replace(receipt, operation_id="another"))
    assert not value.matches_receipt(
        replace(receipt, command=replace(receipt.command, key="other"))
    )
    assert not value.matches_receipt(replace(receipt, result=JsonDocument("{}")))
    assert not value.matches_receipt(
        replace(
            receipt,
            result=JsonDocument.from_value(
                {"relative_closure": {**document.decode(), "recorded_at": str(value.recorded_at)}}
            ),
        )
    )
    assert document.decode()["kind"] == kind.value
    assert value.matches_source(value.schedule, value.cycle)
    with pytest.raises(FrozenInstanceError):
        value.recorded_at = 0
    if kind is RelativeClosureKind.GENERATED:
        assert (
            value.cycle.closed_at is None
            and value.successor.source.cycle == value.cycle.completion_snapshot()
        )


def test_cycle_identity_ignores_generation_and_verification_but_preserves_all_scope():
    value = closure()
    edited = replace(
        value.schedule,
        revision=2,
        pattern_revision=2,
        interval=replace(value.schedule.interval, days=60),
    )
    assert value.key == RelativeClosure.cycle_key(edited, value.cycle, value.installation)
    assert value.matches_source(edited, value.cycle.close(value.recorded_at))
    for changed in [
        replace(value.schedule, schedule_id="other"),
        replace(value.schedule, definition_id="other"),
        replace(value.schedule, household_id="other"),
        replace(value.schedule, created_at=101),
    ]:
        assert not value.matches_source(changed, value.cycle)
    assert not value.matches_source(
        value.schedule, replace(value.cycle, performed_at=value.cycle.performed_at - 1)
    )
    assert value.key != RelativeClosure.cycle_key(
        value.schedule, value.cycle, replace(value.installation, channel="stable")
    )
    assert value.key != RelativeClosure.cycle_key(
        value.schedule, replace(value.cycle, cycle_id="other"), value.installation
    )
    assert value.key != RelativeClosure.cycle_key(
        value.schedule, replace(value.cycle, occurrence_id="other"), value.installation
    )


@pytest.mark.parametrize(
    "change",
    [
        {"installation": None},
        {"schedule": None},
        {"cycle": None},
        {"kind": "generated"},
        {"operation": None},
        {"recorded_at": True},
        {"recorded_at": -1},
        {"recorded_at": 100},
        {"successor": None},
    ],
)
def test_invalid_or_incomplete_grant_never_becomes_a_closure(change):
    with pytest.raises(InvalidInput):
        replace(closure(), **change)


@pytest.mark.parametrize("change", ["installation", "schedule", "cycle", "time", "command"])
def test_successor_and_command_must_match_exact_original_cycle_and_scope(change):
    value = closure()
    if change == "installation":
        slot = replace(value.successor, installation=replace(value.installation, channel="stable"))
        changes = {"successor": slot}
    elif change == "schedule":
        changes = {"schedule": replace(value.schedule, revision=2)}
    elif change == "cycle":
        changes = {"cycle": replace(value.cycle, cycle_id="other")}
    elif change == "time":
        changes = {"recorded_at": value.recorded_at + 1}
    else:
        changes = {
            "operation": replace(
                value.operation, command=replace(value.operation.command, key="other")
            )
        }
    with pytest.raises(InvalidInput):
        replace(value, **changes)


@pytest.mark.parametrize(
    "kind",
    [
        RelativeClosureKind.REJECTED,
        RelativeClosureKind.REOPENED,
        RelativeClosureKind.HISTORICAL_ABSENT,
    ],
)
def test_non_grant_fences_cannot_hide_a_successor_or_an_unrelated_command(kind):
    value = closure(kind=kind)
    with pytest.raises(InvalidInput):
        replace(value, successor=closure().successor)
    for field, bad in [
        ("actor_id", "human"),
        ("household_id", "other"),
        ("action", "task.complete"),
        ("key", "other"),
    ]:
        with pytest.raises(InvalidInput):
            replace(
                value,
                operation=replace(
                    value.operation, command=replace(value.operation.command, **{field: bad})
                ),
            )
    if kind is not RelativeClosureKind.HISTORICAL_ABSENT:
        with pytest.raises(InvalidInput):
            replace(value, cycle=value.cycle.completion_snapshot())


@pytest.mark.parametrize("state", list(OccurrenceState))
@pytest.mark.parametrize("history", list(WorkHistory))
def test_reopening_only_cancels_proven_unstarted_work_and_preserves_started_or_unknown_history(
    state, history
):
    value = closure()
    work = successor(value, state=state)
    result = successor_disposition(value, value.cycle.close(value.recorded_at), work, history)
    expected = (
        SuccessorDisposition.RETAINED
        if state in (OccurrenceState.CANCELLED, OccurrenceState.SKIPPED)
        else SuccessorDisposition.REVIEW
        if state in (OccurrenceState.IN_PROGRESS, OccurrenceState.COMPLETED)
        or history is not WorkHistory.UNSTARTED
        else SuccessorDisposition.CANCEL
    )
    assert result is expected
    assert work.state is state and value.cycle.closed_at is None


def test_absence_is_not_permission_to_recreate_and_source_loss_requires_review():
    value = closure()
    assert (
        successor_disposition(
            value, value.cycle.close(value.recorded_at), None, WorkHistory.UNSTARTED
        )
        is SuccessorDisposition.ABSENT
    )
    assert (
        successor_disposition(value, None, successor(value), WorkHistory.UNSTARTED)
        is SuccessorDisposition.REVIEW
    )
    assert (
        successor_disposition(value, value.cycle, successor(value), WorkHistory.UNSTARTED)
        is SuccessorDisposition.CURRENT
    )
    fenced = closure(kind=RelativeClosureKind.REOPENED)
    assert (
        successor_disposition(fenced, fenced.cycle, None, WorkHistory.UNKNOWN)
        is SuccessorDisposition.CLOSED
    )


@pytest.mark.parametrize(
    "change", ["closure", "cycle", "history", "occurrence", "household", "definition"]
)
def test_invalidation_rejects_foreign_or_untyped_facts(change):
    value = closure()
    cycle = value.cycle.close(value.recorded_at)
    work = successor(value)
    args = [value, cycle, work, WorkHistory.UNSTARTED]
    if change == "closure":
        args[0] = None
    elif change == "cycle":
        args[1] = replace(cycle, cycle_id="foreign")
    elif change == "history":
        args[3] = "unstarted"
    elif change == "occurrence":
        args[2] = replace(work, occurrence_id="other")
    elif change == "household":
        args[2] = replace(
            work,
            household_id="other",
            definition_snapshot=replace(work.definition_snapshot, household_id="other"),
        )
    else:
        args[2] = replace(
            work, definition_snapshot=replace(work.definition_snapshot, definition_id="other")
        )
    with pytest.raises(InvalidInput):
        successor_disposition(*args)


@pytest.mark.parametrize("field", ["schedule", "cycle", "installation", "household"])
def test_cycle_key_rejects_untyped_or_foreign_source_facts(field):
    value = closure()
    args = [value.schedule, value.cycle, value.installation]
    if field == "household":
        args[1] = replace(value.cycle, household_id="foreign")
    else:
        args[["schedule", "cycle", "installation"].index(field)] = None
    with pytest.raises(InvalidInput, match="invalid_relative_closure"):
        RelativeClosure.cycle_key(*args)


def test_non_grant_closure_cannot_predate_the_rule_and_zero_is_an_actual_timestamp():
    value = closure(kind=RelativeClosureKind.HISTORICAL_ABSENT)
    cycle = replace(value.cycle, performed_at=0, recorded_at=0)
    with pytest.raises(InvalidInput, match="invalid_relative_closure"):
        replace(value, cycle=cycle, recorded_at=value.schedule.created_at - 1)
    zero = replace(
        value, schedule=replace(value.schedule, created_at=0), cycle=cycle, recorded_at=0
    )
    assert zero.document().decode()["recorded_at"] == 0
    assert zero.cycle.recorded_at == 0


@pytest.mark.parametrize("kind", [RelativeClosureKind.REJECTED, RelativeClosureKind.REOPENED])
def test_terminal_consumer_proof_cannot_predate_the_observed_human_decision(kind):
    value = closure(kind=kind)
    with pytest.raises(InvalidInput, match="invalid_relative_closure"):
        replace(value, recorded_at=value.cycle.recorded_at)


def test_late_approval_keeps_the_original_basis_and_rejection_invalidates_only_the_successor():
    schedule, _, slot, cycle = values(restricted=True)
    value = RelativeClosure(
        slot.installation,
        schedule,
        cycle,
        RelativeClosureKind.GENERATED,
        slot.created_at,
        RelativeOperation(slot.command, "original-grant"),
        slot,
    )
    before = value.document()
    actor = TaskPerformer("reviewer", Role.ADULT)
    approved = cycle.verify(VerificationState.APPROVED, actor, value.recorded_at + 1000)
    assert value.matches_source(schedule, approved)
    assert (
        successor_disposition(value, approved, successor(value), WorkHistory.UNSTARTED)
        is SuccessorDisposition.CURRENT
    )
    rejected = cycle.verify(VerificationState.REJECTED, actor, value.recorded_at + 1000, "Repeat")
    assert value.matches_source(schedule, rejected)
    assert (
        successor_disposition(value, rejected, successor(value), WorkHistory.UNSTARTED)
        is SuccessorDisposition.CANCEL
    )
    assert (
        successor_disposition(value, rejected, successor(value), WorkHistory.STARTED)
        is SuccessorDisposition.REVIEW
    )
    assert value.document() == before
    assert not value.matches_source(None, cycle)
    assert not value.matches_source(schedule, None)
