"""Bounded task evidence pages merge current and restored positions without replay."""

from dataclasses import replace

import pytest
from test_sqlite_history import install
from test_task_execution_commands import perform, prepared

from domus.domain.errors import InvalidInput, StorageFailure
from domus.domain.restoration import RetainedOperation
from domus.infrastructure.sqlite_history import encode_operation, iter_operations


def test_current_task_history_is_scoped_ordered_bounded_and_not_a_delivery_confirmation(tmp_path):
    commands, child, store, oid, _, _ = prepared(tmp_path)
    original = perform(child, store, oid, ("child",))
    with store.read() as unit:
        rows = unit.tasks.history("home", oid)
        assert [item.evidence.receipt.command.action for item in rows] == [
            "task.create",
            "task.assign",
            "task.complete",
        ]
        assert all(item.current and item.archived_by is None for item in rows)
        assert not any(item.evidence.delivered for item in rows)
        first = unit.tasks.history("home", oid, limit=1)
        second = unit.tasks.history("home", oid, limit=1, after=first[0].evidence.position)
        assert first == rows[:1] and second == rows[1:2]
        assert not unit.tasks.history("other", oid) and not unit.tasks.history("home", "unknown")
        operation = unit.tasks.operation(
            "home", child.actor.current().ha_user_id, original.operation_id
        )
        assert operation == rows[-1]
        assert unit.tasks.operation("home", "ha_admin", original.operation_id) is None
        assert unit.tasks.operation("other", "ha_child", original.operation_id) is None
        assert unit.tasks.operation("home", "ha_child", "unknown") is None
    with store.write() as unit:
        unit.outbox.acknowledge(original.operation_id)
    with store.read() as unit:
        assert unit.tasks.history("home", oid)[-1].evidence.delivered


def test_history_merges_more_than_a_page_and_current_retained_rows_are_not_duplicated(tmp_path):
    _, child, store, oid, _, _ = prepared(tmp_path)
    perform(child, store, oid, ("child",))
    with store._connection() as connection:
        originals = tuple(iter_operations(connection))
    # Isolated retained evidence fixture: keep original operations current and add
    # processed historical task facts. This does not simulate checkpoint activation.
    template = next(
        item for item in originals if item.evidence.receipt.command.action == "task.complete"
    )
    history = []
    for i in range(130):
        evidence = template.evidence
        command = replace(evidence.receipt.command, key=f"historical-{i:03}")
        opid = f"historical-operation-{i:03}"
        history.append(
            RetainedOperation(
                replace(
                    evidence,
                    receipt=replace(evidence.receipt, command=command, operation_id=opid),
                    audit=replace(evidence.audit, command=command, operation_id=opid),
                    event=replace(evidence.event, event_id=opid),
                    position=100 + i,
                ),
                False,
                "restore-one",
            )
        )
    retained = [replace(item, archived_by="restore-one") for item in originals]
    install(store, sorted([*retained, *history], key=lambda item: item.evidence.command_scope))
    with store.read() as unit:
        seen, after = [], 0
        while batch := unit.tasks.history("home", oid, limit=17, after=after):
            seen.extend(batch)
            after = batch[-1].evidence.position
        assert len(seen) == 133 and len({item.evidence.position for item in seen}) == 133
        assert sum(item.current for item in seen) == 3
        assert all(item.archived_by == "restore-one" for item in seen)
        fact = history[0]
        assert unit.tasks.operation("home", "ha_child", fact.evidence.receipt.operation_id) == fact
        assert unit.outbox.pending()[-1].event_id == template.evidence.receipt.operation_id


@pytest.mark.parametrize(
    "limit,after", [(0, 0), (102, 0), (True, 0), (1, True), (1, -1), (1, 2**63)]
)
def test_history_rejects_unbounded_or_invalid_frontiers(tmp_path, limit, after):
    _, _, store, oid, _, _ = prepared(tmp_path)
    with store.read() as unit:
        with pytest.raises(InvalidInput):
            unit.tasks.history("home", oid, limit=limit, after=after)


def test_history_refuses_a_retained_projection_that_disagrees_with_current_evidence(tmp_path):
    _, _, store, oid, _, _ = prepared(tmp_path)
    with store._connection() as connection:
        originals = tuple(iter_operations(connection))
    install(store, [replace(item, archived_by="restore-one") for item in originals])
    selected = next(
        item for item in originals if item.evidence.receipt.command.action == "task.assign"
    )
    with store._connection() as connection:
        changed = replace(selected, current=False, archived_by="restore-one")
        connection.execute(
            "UPDATE retained_operations SET current=0,document=? WHERE operation_id=?",
            (encode_operation(changed), selected.evidence.receipt.operation_id),
        )
    with store.read() as unit:
        with pytest.raises(StorageFailure):
            unit.tasks.history("home", oid)
        with pytest.raises(StorageFailure):
            unit.tasks.operation(
                "home",
                selected.evidence.receipt.command.actor_id,
                selected.evidence.receipt.operation_id,
            )


def test_task_operation_refuses_an_orphan_current_retained_projection(tmp_path):
    _, _, store, oid, _, _ = prepared(tmp_path)
    with store._connection() as connection:
        originals = tuple(iter_operations(connection))
    install(store, [replace(item, archived_by="restore-one") for item in originals])
    selected = next(
        item for item in originals if item.evidence.receipt.command.action == "task.assign"
    )
    opid = selected.evidence.receipt.operation_id
    with store._connection() as connection:
        for table, key in (
            ("receipts", "operation_id"),
            ("audit", "operation_id"),
            ("outbox", "event_id"),
        ):
            connection.execute(f"DELETE FROM {table} WHERE {key}=?", (opid,))
    with store.read() as unit:
        with pytest.raises(StorageFailure):
            unit.tasks.operation("home", selected.evidence.receipt.command.actor_id, opid)


def test_history_refuses_cross_source_position_reuse_in_a_corrupted_file(tmp_path):
    _, _, store, oid, _, _ = prepared(tmp_path)
    with store.read() as unit:
        original = unit.tasks.history("home", oid)[0]
    evidence = original.evidence
    command = replace(evidence.receipt.command, key="colliding-position")
    opid = "historical-collision"
    value = RetainedOperation(
        replace(
            evidence,
            receipt=replace(evidence.receipt, command=command, operation_id=opid),
            audit=replace(evidence.audit, command=command, operation_id=opid),
            event=replace(evidence.event, event_id=opid),
        ),
        False,
        "restore-one",
    )
    with store._connection() as connection:
        connection.execute(
            "INSERT INTO retained_operations VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                *value.evidence.command_scope,
                opid,
                evidence.position,
                0,
                "restore-one",
                encode_operation(value),
                None,
            ),
        )
    with store.read() as unit:
        with pytest.raises(StorageFailure):
            unit.tasks.history("home", oid)


def test_invalid_current_evidence_is_a_storage_failure_not_caller_input(tmp_path):
    _, _, store, oid, _, _ = prepared(tmp_path)
    with store._connection() as connection:
        connection.execute(
            "UPDATE receipts SET payload_fingerprint='broken' WHERE action='task.assign'"
        )
    with store.read() as unit:
        with pytest.raises(StorageFailure, match="invalid_task_operation"):
            unit.tasks.history("home", oid)
