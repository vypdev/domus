"""Checkpoint reconciliation retains processed truth without replaying rolled-away effects."""

from dataclasses import replace

import pytest

from domus.domain.errors import Conflict, InvalidInput
from domus.domain.restoration import OperationEvidence, RetainedOperation, reconcile_operations
from domus.domain.storage import AuditEntry, CommandKey, JsonDocument, OutboxEvent, Receipt


def evidence(key: str = "a", *, delivered: bool = False, position: int = 1) -> OperationEvidence:
    command = CommandKey("home", "human", "household.update", key)
    value = JsonDocument.from_value({"name": key, "revision": position})
    receipt = Receipt(command, value.fingerprint, "operation-" + key, value, 100)
    return OperationEvidence(
        receipt,
        AuditEntry(receipt.operation_id, command, value, 100),
        OutboxEvent(receipt.operation_id, "home", command.action, value, 100),
        position,
        delivered,
    )


def record(key: str = "a", *, current=True, archived_by=None, delivered=False, position=1):
    return RetainedOperation(
        evidence(key, delivered=delivered, position=position), current, archived_by
    )


def reconcile(checkpoint, current):
    return tuple(reconcile_operations(iter(checkpoint), iter(current), "restore-1"))


def test_evidence_roundtrip_is_complete_canonical_and_returns_independent_values() -> None:
    original = record(archived_by="restore-before")
    assert RetainedOperation.from_value(original.value()) == original
    value = original.value()
    value["result"]["name"] = "changed"
    assert original.evidence.receipt.result.decode()["name"] == "a"
    assert original.evidence.command_scope == ("home", "human", "household.update", "a")
    assert (
        RetainedOperation.from_value(record(current=False, archived_by="old").value()).current
        is False
    )


@pytest.mark.parametrize(
    "change",
    [
        {"position": True},
        {"position": 0},
        {"position": 2**63},
        {"delivered": 1},
        {"receipt": None},
        {"audit": None},
        {"event": None},
        {"receipt": replace(evidence().receipt, payload_fingerprint="not-a-digest")},
        {"receipt": replace(evidence().receipt, operation_id="unsafe id")},
        {"receipt": replace(evidence().receipt, created_at=True)},
        {"receipt": replace(evidence().receipt, created_at=-1)},
        {"receipt": replace(evidence().receipt, created_at=2**63)},
        {"audit": replace(evidence().audit, operation_id="different")},
        {
            "audit": replace(
                evidence().audit, command=CommandKey("other", "human", "household.update", "a")
            )
        },
        {"audit": replace(evidence().audit, created_at=101)},
        {"event": replace(evidence().event, event_id="different")},
        {"event": replace(evidence().event, household_id="other")},
        {"event": replace(evidence().event, event_type="other")},
        {"event": replace(evidence().event, created_at=101)},
        {"receipt": replace(evidence().receipt, result={})},
        {"audit": replace(evidence().audit, detail={})},
        {"event": replace(evidence().event, payload={})},
    ],
)
def test_incomplete_or_inconsistent_atomic_facts_are_rejected(change: dict) -> None:
    with pytest.raises(InvalidInput):
        replace(evidence(), **change)


@pytest.mark.parametrize("current,archived", [(1, None), (False, None), (True, "bad id")])
def test_retained_state_cannot_invent_historical_provenance(current, archived) -> None:
    with pytest.raises(InvalidInput):
        RetainedOperation(evidence(), current, archived)
    with pytest.raises(InvalidInput):
        RetainedOperation(None, True)


@pytest.mark.parametrize("kind", ["list", "missing", "extra", "scope", "payload", "current"])
def test_record_parser_rejects_unknown_missing_and_invalid_fields(kind: str) -> None:
    value = record().value()
    if kind == "list":
        value = []
    elif kind == "missing":
        del value["result"]
    elif kind == "extra":
        value["extra"] = True
    elif kind == "scope":
        value["actor_id"] = "bad actor"
    elif kind == "payload":
        value["event_payload"] = []
    else:
        value["current"] = 1
    with pytest.raises(InvalidInput):
        RetainedOperation.from_value(value)


def test_later_operations_are_historical_and_not_selected_business_state() -> None:
    a, b, c = record(), record("b", position=2), record("c", position=3)
    result = reconcile([a], [a, b, c])
    assert result == (
        a,
        replace(b, current=False, archived_by="restore-1"),
        replace(c, current=False, archived_by="restore-1"),
    )
    assert b.current and b.archived_by is None
    assert result[1].evidence.receipt == b.evidence.receipt
    assert result[1].evidence.audit == b.evidence.audit
    assert result[1].evidence.event == b.evidence.event


def test_empty_checkpoint_keeps_complete_history_without_recreating_a_household() -> None:
    result = reconcile([], [record(), record("b", position=2)])
    assert len(result) == 2 and not any(item.current for item in result)
    assert reconcile([], []) == ()


def test_later_acknowledgement_is_preserved_for_current_and_historical_events() -> None:
    snapshot = record()
    source = record(delivered=True)
    assert reconcile([snapshot], [source]) == (source,)
    historical = reconcile([], [source])[0]
    assert historical.evidence.delivered is True and not historical.current
    undelivered = reconcile([], [snapshot])[0]
    assert undelivered.evidence.delivered is False and not undelivered.current


def test_repeated_restore_keeps_first_history_and_can_select_a_known_effect_again() -> None:
    original = record()
    first = reconcile([], [original])[0]
    again = reconcile([], [first])[0]
    assert again == first
    selected = reconcile([original], [first])[0]
    assert selected.current and selected.archived_by == "restore-1"
    assert selected.evidence == original.evidence
    assert reconcile([first], [selected]) == (first,)


@pytest.mark.parametrize("change", ["id", "result", "audit", "event", "position", "fingerprint"])
def test_same_command_with_different_committed_facts_is_never_silently_selected(change) -> None:
    source = record()
    fact = source.evidence
    replacement = JsonDocument.from_value({"different": True})
    if change == "id":
        fact = replace(
            fact,
            receipt=replace(fact.receipt, operation_id="other"),
            audit=replace(fact.audit, operation_id="other"),
            event=replace(fact.event, event_id="other"),
        )
    elif change == "result":
        fact = replace(fact, receipt=replace(fact.receipt, result=replacement))
    elif change == "audit":
        fact = replace(fact, audit=replace(fact.audit, detail=replacement))
    elif change == "event":
        fact = replace(fact, event=replace(fact.event, payload=replacement))
    elif change == "position":
        fact = replace(fact, position=2)
    else:
        fact = replace(fact, receipt=replace(fact.receipt, payload_fingerprint="0" * 64))
    with pytest.raises(Conflict, match="restore_evidence_conflict"):
        reconcile([source], [replace(source, evidence=fact)])


def test_missing_checkpoint_fact_and_regressed_delivery_or_history_are_rejected() -> None:
    with pytest.raises(Conflict, match="restore_checkpoint_unexplained"):
        reconcile([record("a")], [])
    with pytest.raises(Conflict, match="restore_checkpoint_unexplained"):
        reconcile([record("a")], [record("b")])
    with pytest.raises(Conflict, match="restore_delivery_regressed"):
        reconcile([record(delivered=True)], [record()])
    for prior in (None, "different-restore"):
        with pytest.raises(Conflict, match="restore_history_conflict"):
            reconcile([record(archived_by="old-restore")], [record(archived_by=prior)])


@pytest.mark.parametrize("side", ["checkpoint", "source"])
@pytest.mark.parametrize(
    "kind", ["duplicate_scope", "unsorted", "duplicate_id", "duplicate_position", "invalid"]
)
def test_frontiers_must_have_unique_sorted_scopes_and_operation_identities(side, kind) -> None:
    a, b = record(), record("b", position=2)
    if kind == "duplicate_scope":
        values = [a, a]
    elif kind == "unsorted":
        values = [b, a]
    elif kind == "duplicate_id":
        b = replace(
            b,
            evidence=replace(
                b.evidence,
                receipt=replace(b.evidence.receipt, operation_id="operation-a"),
                audit=replace(b.evidence.audit, operation_id="operation-a"),
                event=replace(b.evidence.event, event_id="operation-a"),
            ),
        )
        values = [a, b]
    elif kind == "duplicate_position":
        values = [a, replace(b, evidence=replace(b.evidence, position=1))]
    else:
        values = [None]
    with pytest.raises(InvalidInput):
        reconcile(values if side == "checkpoint" else [], values if side == "source" else [a, b])


def test_invalid_restore_id_is_rejected_and_earlier_extra_source_keys_are_preserved() -> None:
    with pytest.raises(InvalidInput):
        tuple(reconcile_operations([], [], "bad restore"))
    a, b, c = record(position=2), record("b", position=1), record("c", position=3)
    result = reconcile([b], [a, b, c])
    assert [item.current for item in result] == [False, True, False]


def test_streaming_does_not_consume_an_entire_frontier_before_the_first_result() -> None:
    def current():
        yield record()
        raise RuntimeError("second row requested")

    values = reconcile_operations([], current(), "restore-1")
    assert next(values).current is False
    with pytest.raises(RuntimeError, match="second row requested"):
        next(values)


def test_a_checkpoint_cannot_omit_an_earlier_retained_operation() -> None:
    a, b = record(), record("b", position=2)
    with pytest.raises(Conflict, match="restore_checkpoint_incomplete"):
        reconcile([b], [a, b])


def test_wall_clock_regression_does_not_change_the_operation_frontier() -> None:
    a, b = record(), record("b", position=2)
    fact = b.evidence
    b = replace(
        b,
        evidence=replace(
            fact,
            receipt=replace(fact.receipt, created_at=50),
            audit=replace(fact.audit, created_at=50),
            event=replace(fact.event, created_at=50),
        ),
    )
    assert reconcile([a], [a, b])[1].evidence.receipt.created_at == 50


def test_large_valid_individual_payloads_are_not_rejected_by_an_aggregate_json_limit() -> None:
    large = JsonDocument.from_value({"data": "x" * 60000})
    fact = evidence()
    fact = replace(
        fact,
        receipt=replace(fact.receipt, result=large),
        audit=replace(fact.audit, detail=large),
        event=replace(fact.event, payload=large),
    )
    retained = RetainedOperation(fact, True)
    assert RetainedOperation.from_value(retained.value()) == retained
