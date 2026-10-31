"""Malformed history, incomplete imports and sequence changes fail without losing facts."""

from dataclasses import replace

import pytest
from test_household_commands import fixture
from test_restoration_values import record
from test_sqlite_history import current_fixture, install

from domus.domain.errors import Conflict, InvalidInput, StorageFailure
from domus.domain.storage import CommandKey, JsonDocument
from domus.infrastructure.sqlite_history import (
    SQLiteHistory,
    encode_operation,
    iter_operations,
    verify_history,
)


@pytest.mark.parametrize(
    "change",
    ["facts", "acknowledgement", "archive", "order", "current", "missing", "position_collision"],
)
def test_conflicting_import_is_atomic_even_if_the_caller_commits_after_catching_it(
    tmp_path, change
):
    _, store, _, _ = current_fixture(tmp_path)
    with store._connection() as connection:
        original = tuple(iter_operations(connection))
    install(store, original)
    a = record("z", current=False, archived_by="restore-1", position=8, delivered=True)
    values = sorted([*original, a], key=lambda v: v.evidence.command_scope)
    install(store, values)
    if change == "facts":
        altered = replace(
            a,
            evidence=replace(
                a.evidence,
                receipt=replace(
                    a.evidence.receipt, result=JsonDocument.from_value({"different": True})
                ),
            ),
        )
        attempted = [altered if v == a else v for v in values]
    elif change == "acknowledgement":
        attempted = [
            replace(a, evidence=replace(a.evidence, delivered=False)) if v == a else v
            for v in values
        ]
    elif change == "archive":
        attempted = [replace(a, archived_by="different") if v == a else v for v in values]
    elif change == "order":
        attempted = [*values, values[-1]]
    elif change == "current":
        attempted = [replace(a, current=True) if v == a else v for v in values]
    elif change == "position_collision":
        attempted = sorted(
            [*values, record("zz", current=False, archived_by="restore-2", position=8)],
            key=lambda v: v.evidence.command_scope,
        )
    else:
        attempted = list(original)
    with store._connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        with pytest.raises(Conflict):
            SQLiteHistory(connection).install(attempted)
        connection.execute("COMMIT")
        assert tuple(iter_operations(connection)) == tuple(values)


def test_current_projection_and_omitted_base_facts_are_not_silently_imported(tmp_path):
    _, store, _, current = current_fixture(tmp_path)
    for attempted in (
        [],
        [replace(current, current=False, archived_by="restore-1")],
        [replace(current, evidence=replace(current.evidence, delivered=True, position=2))],
    ):
        with pytest.raises(Conflict):
            install(store, attempted)
    with store._connection() as connection:
        assert tuple(iter_operations(connection)) == (current,)


@pytest.mark.parametrize(
    "kind",
    [
        "json",
        "utf8",
        "oversized",
        "columns",
        "closed_binding",
        "current_missing",
        "current_changed",
        "current_ack_regressed",
        "historical_collision",
        "sequence",
        "sequence_type",
        "sequence_duplicate",
        "delivery",
    ],
)
def test_corrupt_history_and_projection_never_verify(tmp_path, kind):
    _, store, _, current = current_fixture(tmp_path)
    install(store, [current])
    with store._connection() as connection:
        if kind == "json":
            connection.execute("UPDATE retained_operations SET document='{}'")
        elif kind == "utf8":
            connection.execute("UPDATE retained_operations SET document=x'ff'")
        elif kind == "oversized":
            connection.execute("UPDATE retained_operations SET document=?", ("x" * 262_145,))
        elif kind == "columns":
            connection.execute("UPDATE retained_operations SET operation_id='different'")
        elif kind == "closed_binding":
            connection.execute("UPDATE retained_operations SET closed_recovery_id='fabricated'")
        elif kind == "current_missing":
            connection.execute("DELETE FROM receipts")
        elif kind == "current_changed":
            connection.execute("UPDATE receipts SET result='{}'")
        elif kind == "current_ack_regressed":
            delivered = replace(current, evidence=replace(current.evidence, delivered=True))
            connection.execute(
                "UPDATE retained_operations SET document=?", (encode_operation(delivered),)
            )
        elif kind == "historical_collision":
            historical = replace(current, current=False, archived_by="restore-1")
            connection.execute(
                "UPDATE retained_operations SET current=0,archived_by='restore-1',document=?",
                (encode_operation(historical),),
            )
        elif kind == "sequence":
            connection.execute("UPDATE sqlite_sequence SET seq=0 WHERE name='outbox'")
        elif kind == "sequence_type":
            connection.execute("UPDATE sqlite_sequence SET seq='wrong' WHERE name='outbox'")
        elif kind == "sequence_duplicate":
            connection.execute("INSERT INTO sqlite_sequence(name,seq) VALUES ('outbox',1)")
        else:
            connection.execute("PRAGMA ignore_check_constraints=ON")
            connection.execute("UPDATE outbox SET delivered=2")
        with pytest.raises(StorageFailure):
            verify_history(connection)


@pytest.mark.parametrize("kind", ["receipt", "operation", "delivery"])
def test_incomplete_current_projection_cannot_be_presented_as_historical(tmp_path, kind):
    _, store, created, current = current_fixture(tmp_path)
    install(store, [current])
    with store._connection() as connection:
        if kind == "receipt":
            connection.execute("UPDATE receipts SET result='{}'")
        elif kind == "operation":
            connection.execute("DELETE FROM receipts")
        else:
            connection.execute("DELETE FROM outbox")
    with store.read() as unit:
        with pytest.raises(StorageFailure):
            if kind == "receipt":
                unit.receipts.get(created.command)
            elif kind == "operation":
                unit.receipts.get_operation("home", created.command.actor_id, created.operation_id)
            else:
                unit.outbox.delivered(created.operation_id)


def test_duplicate_historical_id_and_projection_receipt_cannot_be_stored_as_new_current_work(
    tmp_path,
):
    _, store, _, _, _ = fixture(tmp_path / "database")
    a = record(current=False, archived_by="restore-1")
    install(store, [a])
    with store.write() as unit:
        for command in (
            a.evidence.receipt.command,
            replace(a.evidence.receipt.command, key="other"),
        ):
            with pytest.raises(Conflict):
                unit.receipts.add(replace(a.evidence.receipt, command=command))
        with pytest.raises(InvalidInput):
            unit.receipts.add(unit.receipts.get(a.evidence.receipt.command))


@pytest.mark.parametrize(
    "action,state,request_id",
    [
        ("recovery.complete", "wrong", "r"),
        ("recovery.cancel", "canceled", None),
        ("recovery.complete", "recovered", "bad id"),
    ],
)
def test_malformed_terminal_recovery_facts_do_not_create_a_guard(action, state, request_id):
    from domus.domain.recovery import closed_recovery

    receipt = replace(
        record().evidence.receipt,
        command=CommandKey("home", "human", action, "key"),
        result=JsonDocument.from_value({"state": state, "request_id": request_id}),
    )
    with pytest.raises(InvalidInput):
        closed_recovery(receipt)


def test_empty_import_does_not_require_a_household_or_fabricate_a_receipt(tmp_path):
    _, store, _, _, _ = fixture(tmp_path / "database")
    with store._connection() as connection:
        verify_history(connection)
    install(store, [])
    with store.read() as unit:
        assert unit.households.current() is None


def test_interrupted_schema_three_upgrade_rolls_back_the_new_history_table(tmp_path, monkeypatch):
    import sqlite3
    from contextlib import closing
    from pathlib import Path

    from domus.domain.storage import Installation
    from domus.infrastructure.sqlite import SQLiteDatabase

    path = tmp_path / "old.sqlite3"
    source = Path(__file__).resolve().parents[1] / "fixtures/sqlite/v3.sql"
    with closing(sqlite3.connect(path, autocommit=True)) as connection:
        connection.executescript(source.read_text())
    before = path.read_bytes()
    original = sqlite3.connect

    class Failure(sqlite3.Connection):
        def execute(self, statement, parameters=()):
            if statement.startswith("CREATE INDEX retained_recovery"):
                raise sqlite3.OperationalError("injected failure")
            return super().execute(statement, parameters)

    monkeypatch.setattr(sqlite3, "connect", lambda *a, **kw: original(*a, **kw, factory=Failure))
    store = SQLiteDatabase(path, Installation("047cc6fb-dfb0-4fa4-b3c3-e0fe54d116b6", "edge"))
    with pytest.raises(StorageFailure):
        store.initialize()
    monkeypatch.undo()
    assert before == path.read_bytes()
    with store._connection() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 3
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master WHERE name='retained_operations'"
            ).fetchone()
            is None
        )
    store.initialize()
