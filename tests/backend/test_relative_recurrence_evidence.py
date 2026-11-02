"""Relative original proof binds facts, while never granting current maintenance authority."""

from dataclasses import replace

import pytest
from test_relative_recurrence_records import values

from domus.domain.errors import InvalidInput
from domus.domain.relative_recurrence import RelativeOperation
from domus.domain.storage import JsonDocument, Receipt, RestorationProvenance


def original(timed=True):
    rule, progress, slot, _ = values(timed)
    progress = replace(
        progress,
        current_occurrence_id=slot.occurrence_id,
        current_slot_key=slot.key,
        source_after=17,
        last_run_at=slot.created_at,
        evidence=RelativeOperation(slot.command, "original"),
    )
    receipt = Receipt(
        slot.command,
        JsonDocument.from_value({}).fingerprint,
        "original",
        JsonDocument.from_value(
            {
                "slot_key": slot.key,
                "occurrence_id": slot.occurrence_id,
                "schedule_id": rule.schedule_id,
                "definition_id": rule.definition_id,
                "relative_slot_fingerprint": slot.evidence_fingerprint,
                "relative_progress": progress.state_document().decode(),
            }
        ),
        slot.created_at,
    )
    return rule, progress, slot, receipt


@pytest.mark.parametrize("timed", [False, True])
def test_complete_original_proof_binds_progress_and_slot_without_mutable_record_revision(timed):
    rule, progress, slot, receipt = original(timed)
    assert progress.matches_schedule(rule) and progress.matches_receipt(receipt)
    assert slot.matches_receipt(receipt)
    assert (
        progress.state_document()
        == replace(progress, revision=2, last_run_at=slot.created_at + 1).state_document()
    )
    assert (
        replace(slot, schedule=replace(rule, revision=2)).evidence_fingerprint
        == slot.evidence_fingerprint
    )
    changed = replace(slot, occurrence_id="other")
    assert changed.key == slot.key and changed.evidence_fingerprint != slot.evidence_fingerprint
    assert not changed.matches_receipt(receipt)
    absent = replace(receipt, restoration=RestorationProvenance("restore", False))
    assert progress.matches_receipt(absent) and not slot.matches_receipt(absent)


@pytest.mark.parametrize("change", ["none", "command", "operation", "position", "boolean"])
def test_progress_rejects_a_different_original_scope_operation_or_continuation(change):
    _, progress, _, receipt = original()
    if change == "none":
        receipt = None
    elif change == "command":
        receipt = replace(receipt, command=replace(receipt.command, key="other"))
    elif change == "operation":
        receipt = replace(receipt, operation_id="other")
    else:
        body = receipt.result.decode()
        body["relative_progress"]["pattern_revision" if change == "boolean" else "source_after"] = (
            True if change == "boolean" else 18
        )
        receipt = replace(receipt, result=JsonDocument.from_value(body))
    assert not progress.matches_receipt(receipt)


def test_unconsumed_bootstrap_is_the_only_progress_that_needs_no_original():
    rule, progress, _, _ = original()
    empty = values()[1]
    assert empty.pristine and empty.matches_receipt(None)
    assert not replace(progress, evidence=None).matches_receipt(None)
    assert not replace(empty, source_after=1).matches_receipt(None)
    assert not replace(empty, last_run_at=100).matches_receipt(None)
    foreign = replace(
        progress,
        evidence=replace(
            progress.evidence, command=replace(progress.evidence.command, household_id="other")
        ),
    )
    assert not foreign.matches_schedule(rule)
    with pytest.raises(InvalidInput):
        replace(empty, evidence="wrong")
    with pytest.raises(InvalidInput):
        RelativeOperation(None, "operation")
    with pytest.raises(InvalidInput):
        RelativeOperation(progress.evidence.command, "")


@pytest.mark.parametrize("change", ["none", "command", "fingerprint", "slot", "definition"])
def test_slot_cannot_borrow_another_original_materialization(change):
    _, _, slot, receipt = original()
    if change == "none":
        receipt = None
    elif change == "command":
        receipt = replace(receipt, command=replace(receipt.command, actor_id="other"))
    else:
        body = receipt.result.decode()
        body[
            {
                "fingerprint": "relative_slot_fingerprint",
                "slot": "slot_key",
                "definition": "definition_id",
            }[change]
        ] = "other"
        receipt = replace(receipt, result=JsonDocument.from_value(body))
    assert not slot.matches_receipt(receipt)


def test_unchanged_cycle_identity_cannot_replace_original_performers_in_evidence():
    _, _, slot, receipt = original()
    source = slot.source
    cycle = replace(
        source.cycle, performers=(replace(source.cycle.performers[0], member_id="different"),)
    )
    altered = replace(slot, source=replace(source, cycle=cycle))
    assert altered.key == slot.key and altered.evidence_fingerprint != slot.evidence_fingerprint
    assert not altered.matches_receipt(receipt)


@pytest.mark.parametrize("binding", [None, True, "", "a" * 63, "A" * 64])
def test_relative_continuation_binding_is_a_canonical_exact_fingerprint(binding):
    progress = values()[1]
    with pytest.raises(InvalidInput):
        replace(progress, binding=binding)
