"""Equivalent but noncanonical stored JSON fails both direct reads and checkpoint inspection."""

import json

import pytest
from test_fixed_materialization import configured
from test_household_commands import Clock
from test_recurrence_records import values

from domus.domain.errors import DatabaseRejected, StorageFailure
from domus.domain.recurrence_frontier import RecurrenceFrontier
from domus.infrastructure.sqlite_recurrence_records import (
    frontier_document,
    progress_document,
    read_frontier,
    read_progress,
    read_schedule,
    read_slot,
    schedule_document,
    slot_document,
)
from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots


@pytest.mark.parametrize("timed", [False, True])
@pytest.mark.parametrize("kind", ["rule", "progress", "slot", "frontier"])
@pytest.mark.parametrize("change", ["outer-space", "pretty", "reordered", "escaped-key"])
def test_semantically_equal_noncanonical_documents_are_refused_before_record_construction(
    timed, kind, change
):
    rule, progress, slot = values(timed)
    value, encode, decode = {
        "rule": (rule, schedule_document, read_schedule),
        "progress": (progress, progress_document, read_progress),
        "slot": (slot, slot_document, read_slot),
        "frontier": (RecurrenceFrontier("home", "last", 100), frontier_document, read_frontier),
    }[kind]
    original = encode(value).encoded
    row = json.loads(original)
    altered = {
        "outer-space": " " + original + "\n",
        "pretty": json.dumps(row, indent=2),
        "reordered": json.dumps(dict(reversed(tuple(row.items()))), separators=(",", ":")),
        "escaped-key": original.replace('"household_id"', r'"\u0068ousehold_id"'),
    }[change]
    assert altered != original and json.loads(altered) == row
    assert decode(original) == value
    with pytest.raises(StorageFailure, match="invalid_recurrence_record"):
        decode(altered)


@pytest.mark.parametrize("kind", ["rules", "progress", "slots", "frontiers"])
def test_actual_noncanonical_storage_is_not_repaired_by_read_or_checkpoint(tmp_path, kind):
    service, store, _, _, rule_id, before = configured(tmp_path)
    created = service.step(rule_id, before)
    with store.write() as unit:
        unit.recurrence.save_frontier(RecurrenceFrontier("home", rule_id, 100), 0)
    with store._connection() as connection:
        connection.execute(f"UPDATE recurrence_{kind} SET document=' ' || document")
    source = store.path.read_bytes()
    with store.read() as unit:
        read = {
            "rules": lambda: unit.recurrence.schedule("home", rule_id),
            "progress": lambda: unit.recurrence.progress("home", rule_id),
            "slots": lambda: unit.recurrence.slot("home", created.receipt.command.key),
            "frontiers": lambda: unit.recurrence.frontier("home"),
        }[kind]
        with pytest.raises(StorageFailure, match="invalid_recurrence_record"):
            read()
    with pytest.raises(DatabaseRejected, match="invalid_snapshot_records"):
        SQLiteSnapshots(store, tmp_path / "checkpoint", store.installation, Clock()).create("bad")
    assert store.path.read_bytes() == source
