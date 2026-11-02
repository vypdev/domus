"""Fair rule selection has a small scoped durable cursor, separate from task/work progress."""

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, replace
from threading import Barrier

import pytest
from test_sqlite_snapshots import Clock
from test_task_commands import counts, fixture

from domus.domain.errors import Conflict, DatabaseRejected, InvalidInput, StorageFailure
from domus.domain.recurrence_frontier import RecurrenceFrontier
from domus.infrastructure.sqlite import SQLiteDatabase
from domus.infrastructure.sqlite_recurrence_records import frontier_document, read_frontier
from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots


@pytest.mark.parametrize(
    "field,value",
    [
        ("household_id", ""),
        ("after_schedule_id", ""),
        ("selected_at", True),
        ("selected_at", -1),
        ("revision", 0),
        ("revision", True),
    ],
)
def test_frontier_rejects_invalid_scope_revision_or_clock(field, value):
    with pytest.raises(InvalidInput):
        replace(RecurrenceFrontier("home", None, 100), **{field: value})


def test_frontier_is_immutable_and_can_keep_a_removed_selection_key():
    value = RecurrenceFrontier("home", "retired-rule", 100)
    with pytest.raises(FrozenInstanceError):
        value.revision = 2
    assert read_frontier(frontier_document(value).encoded) == value
    assert (
        read_frontier(
            frontier_document(replace(value, after_schedule_id=None)).encoded
        ).after_schedule_id
        is None
    )


def test_frontier_commits_reopens_and_never_creates_task_or_business_evidence(tmp_path):
    _, store, _, _ = fixture(tmp_path)
    initial = counts(store)
    value = RecurrenceFrontier("home", "removed-rule", 100)
    with store.write() as unit:
        assert unit.recurrence.frontier("home") is None
        unit.recurrence.save_frontier(value, 0)
    reopened = SQLiteDatabase(store.path, store.installation)
    with reopened.read() as unit:
        assert unit.recurrence.frontier("home") == value
        assert unit.recurrence.frontier("other") is None
    assert counts(store) == initial
    assert (
        SQLiteSnapshots(store, tmp_path / "checkpoint", store.installation, Clock())
        .create("frontier")
        .schema_version
        == 8
    )


def test_frontier_cas_and_duplicate_initialization_preserve_the_current_selection(tmp_path):
    _, store, _, _ = fixture(tmp_path)
    value = RecurrenceFrontier("home", "first", 100)
    with store.write() as unit:
        unit.recurrence.save_frontier(value, 0)
    updated = replace(value, after_schedule_id="last", selected_at=101, revision=2)
    with store.write() as unit:
        unit.recurrence.save_frontier(updated, 1)
    for proposed, expected in [(value, 0), (updated, 1), (replace(updated, revision=3), 1)]:
        with pytest.raises(Conflict):
            with store.write() as unit:
                unit.recurrence.save_frontier(proposed, expected)
    with store.read() as unit:
        assert unit.recurrence.frontier("home") == updated


def test_failed_frontier_claim_and_foreign_household_leave_no_partial_record(tmp_path):
    _, store, _, _ = fixture(tmp_path)
    value = RecurrenceFrontier("home", "first", 100)
    with pytest.raises(RuntimeError, match="fixture_failure"):
        with store.write() as unit:
            unit.recurrence.save_frontier(value, 0)
            raise RuntimeError("fixture_failure")
    with pytest.raises(Conflict):
        with store.write() as unit:
            unit.recurrence.save_frontier(replace(value, household_id="other"), 0)
    with store.read() as unit:
        assert unit.recurrence.frontier("home") is None


@pytest.mark.parametrize(
    "change", ["unknown-version", "extra-field", "bool-revision", "duplicate-key"]
)
def test_closed_frontier_codec_never_guesses_or_coerces_stored_data(change):
    document = frontier_document(RecurrenceFrontier("home", None, 100)).decode()
    if change == "unknown-version":
        document["version"] = 2
    elif change == "extra-field":
        document["unexpected"] = None
    elif change == "bool-revision":
        document["revision"] = True
    raw = json.dumps(document) if change != "duplicate-key" else '{"version":1,"version":1}'
    with pytest.raises(StorageFailure, match="invalid_recurrence_record"):
        read_frontier(raw)


def test_corrupt_frontier_header_is_rejected_by_read_and_checkpoint_without_repair(tmp_path):
    _, store, _, _ = fixture(tmp_path)
    value = RecurrenceFrontier("home", "first", 100)
    with store.write() as unit:
        unit.recurrence.save_frontier(value, 0)
    with store._connection() as connection:
        connection.execute("UPDATE recurrence_frontiers SET after_schedule_id='other'")
    before = store.path.read_bytes()
    with store.read() as unit:
        with pytest.raises(StorageFailure, match="invalid_recurrence_record"):
            unit.recurrence.frontier("home")
    with pytest.raises(DatabaseRejected, match="invalid_snapshot_records"):
        SQLiteSnapshots(store, tmp_path / "bad", store.installation, Clock()).create("bad")
    assert store.path.read_bytes() == before


def test_two_independent_initial_claims_commit_only_one_frontier(tmp_path):
    _, store, _, _ = fixture(tmp_path)
    gate = Barrier(2)

    def claim(key):
        independent = SQLiteDatabase(store.path, store.installation, busy_timeout=5)
        gate.wait(timeout=5)
        try:
            with independent.write() as unit:
                unit.recurrence.save_frontier(RecurrenceFrontier("home", key, 100), 0)
            return "saved"
        except Conflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as workers:
        assert sorted(workers.map(claim, ("a", "z"))) == ["conflict", "saved"]
    with store.read() as unit:
        assert unit.recurrence.frontier("home").after_schedule_id in ("a", "z")


def test_genuine_prior_unreleased_schema8_layout_is_refused_without_mutating_its_data(tmp_path):
    import hashlib
    import sqlite3
    from contextlib import closing
    from pathlib import Path

    from test_sqlite_transactions import IDENTITY

    fixture = Path("tests/fixtures/sqlite/unreleased-c581-schema8.sql")
    assert (
        hashlib.sha256(fixture.read_bytes()).hexdigest()
        == "2f884cd00b735ddf60c567a908bf05e709f887f699953bce7808326e017647b4"
    )
    path = tmp_path / "prior-unreleased.sqlite3"
    with closing(sqlite3.connect(path, autocommit=True)) as connection:
        connection.executescript(fixture.read_text())
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 8
        assert connection.execute("SELECT COUNT(*) FROM recurrence_slots").fetchone()[0] == 1
    before = path.read_bytes()
    store = SQLiteDatabase(path, IDENTITY)
    for method in (store.read, store.write):
        with pytest.raises(DatabaseRejected, match="unrelated_database"):
            with method():
                pytest.fail("An unknown prior development layout was accepted")
        assert path.read_bytes() == before
    with pytest.raises(DatabaseRejected, match="unrelated_database"):
        store.initialize(require_existing=True)
    assert path.read_bytes() == before
