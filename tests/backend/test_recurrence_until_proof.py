"""Instant UNTIL needs original resolved boundary proof, not an untrusted closed flag."""

from dataclasses import replace
from datetime import datetime

import pytest
from test_recurrence_creation import request, setup
from test_sqlite_snapshots import Clock

from domus.application.fixed_materialization import FixedMaintenance, MaintenanceScope
from domus.domain.errors import Conflict, DatabaseRejected, StorageFailure
from domus.domain.recurrence_time import NominalTime, TimePolicy
from domus.infrastructure.sqlite_recurrence_records import progress_document
from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots


def configured(tmp_path):
    commands, _, store, _, ids = setup(tmp_path)
    value = request(timed=True)
    policy = TimePolicy("UTC", commands.planner.times.data_identity)
    start = NominalTime(datetime(2026, 1, 1, 12))
    end = commands.planner.times.resolve(NominalTime(datetime(2026, 1, 2, 12)), policy).instant_ms
    value = replace(value, policy=policy, pattern=replace(value.pattern, start=start, until=end))
    receipt = commands.create_fixed("time-until", value)
    rule = receipt.result.decode()["schedule_id"]
    service = FixedMaintenance(
        store, MaintenanceScope(store.installation, "home"), commands.planner, commands.clock, ids
    )
    return service, store, rule, NominalTime(datetime(2026, 1, 5, 12))


@pytest.mark.parametrize(
    "change", ["closed-initial", "consumed-after-cutoff", "consumed-after-cutoff-closed"]
)
@pytest.mark.parametrize("surface", ["value", "read", "write", "snapshot", "step"])
def test_instant_until_rejects_unproved_exhaustion_and_consumption(tmp_path, change, surface):
    service, store, rid, before = configured(tmp_path)
    with store.read() as unit:
        rule = unit.recurrence.schedule("home", rid)
        progress = unit.recurrence.progress("home", rid)
    cursor = (
        replace(progress.cursor, closed=True)
        if change == "closed-initial"
        else replace(
            progress.cursor,
            period_index=2,
            offset=1,
            nominal_count=3,
            closed=change.endswith("closed"),
        )
    )
    altered = replace(progress, cursor=cursor, range_complete=cursor.closed)
    if surface == "value":
        assert not altered.matches_schedule(rule)
        return
    if surface == "write":
        with pytest.raises(Conflict, match="recurrence_cursor_mismatch"):
            with store.write() as unit:
                unit.recurrence.save_progress(replace(altered, revision=2), 1)
        return
    with store._connection() as connection:
        connection.execute(
            "UPDATE recurrence_progress SET document=?", (progress_document(altered).encoded,)
        )
    original = store.path.read_bytes()
    if surface == "read":
        with store.read() as unit:
            with pytest.raises(StorageFailure):
                unit.recurrence.progress("home", rid)
    elif surface == "snapshot":
        with pytest.raises(DatabaseRejected, match="invalid_snapshot_records"):
            SQLiteSnapshots(store, tmp_path / "bad", store.installation, Clock()).create("bad")
    else:
        with pytest.raises(StorageFailure):
            service.step(rid, before)
    assert store.path.read_bytes() == original
    with store.read() as unit:
        assert unit.tasks.occurrences("home") == ()


def test_real_inclusive_until_saves_original_last_and_excluded_boundary_without_writer_provider_io(
    tmp_path, monkeypatch
):
    from domus.infrastructure.recurrence_time import PinnedRecurrenceTime

    service, store, rid, before = configured(tmp_path)
    original_resolve = PinnedRecurrenceTime.resolve

    def outside_writer(self, *args):
        # An independent writer must still be admitted while timezone work executes.
        with store.write():
            pass
        return original_resolve(self, *args)

    monkeypatch.setattr(PinnedRecurrenceTime, "resolve", outside_writer)
    first = service.step(rid, before)
    assert first.status == "created"
    second = service.step(rid, before)
    assert second.status == "created"
    final = service.step(rid, before)
    assert final.cursor.closed
    with store.read() as unit:
        rule = unit.recurrence.schedule("home", rid)
        progress = unit.recurrence.progress("home", rid)
        evidence = progress.evidence
        assert evidence is not None and evidence.operation_id == final.receipt.operation_id
        assert evidence.time.last.resolved.instant_ms == rule.pattern.until
        assert evidence.time.terminal.resolved.instant_ms > rule.pattern.until
        assert evidence.time.cursor == progress.cursor and progress.matches_schedule(rule)
    assert service.step(rid, before).status == "current"
    assert (
        SQLiteSnapshots(store, tmp_path / "good", store.installation, Clock())
        .create("good")
        .database_bytes
        > 0
    )


def test_exact_prior_unreleased_layout_is_refused_unchanged_before_temporal_evidence_use(tmp_path):
    import hashlib
    import sqlite3
    from contextlib import closing
    from pathlib import Path

    from domus.domain.storage import Installation
    from domus.infrastructure.sqlite import SQLiteDatabase

    source = Path("tests/fixtures/sqlite/unreleased-b2bcc69-schema8.sql")
    assert (
        hashlib.sha256(source.read_bytes()).hexdigest()
        == "6c33c79693647e6fed34e693c943012e28ef05a4b153b8901b7e35014105cd63"
    )
    path = tmp_path / "prior.sqlite3"
    with closing(sqlite3.connect(path, autocommit=True)) as c:
        c.executescript(source.read_text())
        identity = Installation(
            *c.execute("SELECT instance_id,channel FROM installation").fetchone()
        )
        assert c.execute("SELECT COUNT(*) FROM recurrence_slots").fetchone()[0] == 2
    before = path.read_bytes()
    store = SQLiteDatabase(path, identity)
    for method in (store.read, store.write):
        with pytest.raises(DatabaseRejected, match="unsupported_schema"):
            with method():
                pytest.fail("Unknown unreleased layout was admitted")
        assert path.read_bytes() == before
    with pytest.raises(DatabaseRejected, match="unrelated_database"):
        store.initialize(require_existing=True)
    assert path.read_bytes() == before
