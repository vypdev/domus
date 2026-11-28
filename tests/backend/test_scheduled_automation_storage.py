"""Durable admissions, CAS and genuine prior-schema data use the real SQLite adapter."""

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest
from test_automation_scheduling_values import run, schedule
from test_task_commands import fixture

from domus.application.automation_scheduled_cancellation import ScheduledCancellations
from domus.application.automation_scheduled_documents import (
    read_run,
    read_schedule,
    run_document,
    schedule_document,
)
from domus.application.fixed_materialization import MaintenanceScope
from domus.domain.automation import AutomationControl
from domus.domain.automation_scheduling import ScheduledOutcome
from domus.domain.errors import Conflict, DatabaseRejected, InvalidInput, StorageFailure
from domus.infrastructure import sqlite as storage
from domus.infrastructure.sqlite import SQLiteDatabase
from domus.infrastructure.sqlite_snapshots import _verify_database

FIXTURES = Path(__file__).parents[1] / "fixtures/sqlite"


def source(tmp_path):
    _, store, _, _ = fixture(tmp_path)
    value = schedule()
    value = replace(value, grant=replace(value.grant, installation=store.installation))
    with store.write() as unit:
        unit.automation_drafts.append("home", value.grant.draft)
        unit.automation_controls.save("home", AutomationControl("daily", 1, 1, True), 0)
        unit.scheduled_automations.save_schedule(value, 0)
    admitted = replace(run(), grant=value.grant)
    return store, value, admitted


def following(value, days=1):
    planned = replace(
        value.planned,
        nominal=replace(
            value.planned.nominal, local=value.planned.nominal.local + timedelta(days=days)
        ),
        resolved_local=value.planned.resolved_local + timedelta(days=days),
    )
    return replace(value, planned=planned, admitted_at=planned.instant_ms)


def test_roundtrip_is_closed_and_retains_exact_timing_and_grant_snapshots():
    saved = schedule()
    assert read_schedule(schedule_document(saved).encoded) == saved
    value = run()
    assert read_run(run_document(value).encoded) == value
    assert (
        read_run(run_document(value.finish(ScheduledOutcome.NO_TASK, 0)).encoded).finished_at == 0
    )
    saved = replace(saved, last_nominal=saved.next_time.nominal.local.date() - timedelta(days=1))
    from domus.domain.automation_scheduling import DailySuppression

    saved = replace(
        saved, suppression=DailySuppression(saved.next_time, saved.next_time.instant_ms)
    )
    assert read_schedule(schedule_document(saved).encoded) == saved


@pytest.mark.parametrize("kind", ["schedule", "run"])
def test_noncanonical_persisted_records_are_rejected_before_a_document_compare_and_swap(kind):
    document = schedule_document(schedule()) if kind == "schedule" else run_document(run())
    reformatted = json.dumps(document.decode(), indent=2)
    with pytest.raises(StorageFailure, match="invalid_daily_automation_record"):
        (read_schedule if kind == "schedule" else read_run)(reformatted)


@pytest.mark.parametrize("kind", ["schedule", "run"])
@pytest.mark.parametrize("corruption", ["version", "extra", "missing", "scope", "time", "array"])
def test_corrupt_or_expanded_canonical_documents_are_rejected(kind, corruption):
    value = schedule_document(schedule()) if kind == "schedule" else run_document(run())
    data = value.decode()
    if corruption == "version":
        data["version"] = 2
    elif corruption == "extra":
        data["grant"]["global_admin"] = True
    elif corruption == "missing":
        del data["grant"]["rule_revision"]
    elif corruption == "scope":
        data["grant"]["installation_id"] = "fake"
    elif corruption == "time":
        data["next_time" if kind == "schedule" else "planned"]["nominal"] = "nonsense"
    else:
        data["grant"] = []
    with pytest.raises(StorageFailure, match="invalid_daily_automation_record"):
        (read_schedule if kind == "schedule" else read_run)(json.dumps(data))


def test_schedule_cas_scoped_paging_and_reopen_preserve_the_active_binding(tmp_path):
    store, value, _ = source(tmp_path)
    with store.write() as unit:
        records = unit.scheduled_automations
        assert records.schedule("other", "daily") is None
        assert records.schedules("home") == (value,)
        assert records.schedules("home", after="daily") == ()
        assert records.schedules("other") == ()
        for requested, expected in ((value, 0), (value, 2), (replace(value, revision=3), 2)):
            with pytest.raises(Conflict):
                records.save_schedule(requested, expected)
        value = replace(value, revision=2)
        records.save_schedule(value, 1)
    reopened = SQLiteDatabase(store.path, store.installation)
    with reopened.read() as unit:
        assert unit.scheduled_automations.schedule("home", "daily") == value


def test_one_admission_across_two_real_writers_and_terminal_outcome_is_immutable(tmp_path):
    store, _, value = source(tmp_path)

    def admit(_):
        try:
            with store.write() as unit:
                unit.scheduled_automations.admit(value)
            return "admitted"
        except Conflict as failure:
            return failure.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(admit, range(2))) == [
            "admitted",
            "daily_automation_trigger_admitted",
        ]
    with store.write() as unit:
        records = unit.scheduled_automations
        assert records.run("other", value.key) is None
        assert records.pending("home") == records.pending("home", rule_id="daily") == (value,)
        assert records.pending("home", rule_id="other") == ()
        finished = value.finish(ScheduledOutcome.NO_TASK, value.admitted_at)
        records.finish(finished)
        assert records.pending("home") == ()
        assert records.run("home", value.key) == finished
        with pytest.raises(Conflict, match="daily_automation_run_finished"):
            records.finish(value.finish(ScheduledOutcome.CANCELLED, value.admitted_at))


def test_outcomes_and_cursor_update_roll_back_with_the_callers_writer(tmp_path):
    store, current, value = source(tmp_path)
    with pytest.raises(RuntimeError, match="crash"):
        with store.write() as unit:
            unit.scheduled_automations.admit(value)
            unit.scheduled_automations.save_schedule(replace(current, revision=2), 1)
            raise RuntimeError("crash")
    with store.read() as unit:
        assert unit.scheduled_automations.run("home", value.key) is None
        assert unit.scheduled_automations.schedule("home", "daily") == current


def test_disabling_cancels_only_queued_work_and_history_paginates_without_reordering(tmp_path):
    store, _, first = source(tmp_path)
    second = following(first)
    cancellations = ScheduledCancellations(
        store,
        MaintenanceScope(store.installation, "home"),
        Mock(now=Mock(return_value=second.admitted_at)),
        Mock(new=Mock(return_value="cancel-storage-operation")),
    )
    with store.write() as unit:
        records = unit.scheduled_automations
        records.admit(first)
        records.admit(second)
        completed = first.finish(ScheduledOutcome.NO_TASK, first.admitted_at)
        records.finish(completed)
        assert cancellations.pending(unit, "daily") == 1
        cancelled = records.run("home", second.key)
        assert cancelled.outcome is ScheduledOutcome.CANCELLED
        assert cancellations.pending(unit, "daily") == 0
        assert records.history("home", "daily", limit=1) == (cancelled,)
        assert records.history("home", "daily", before=(cancelled.admitted_at, cancelled.key)) == (
            completed,
        )
        assert records.history("other", "daily") == ()


@pytest.mark.parametrize(
    "version, filename",
    [
        (20, "v20-inventory-history-source.sql"),
        (35, "v35-daily-automation-source.sql"),
    ],
)
def test_real_previous_schemas_preserve_every_old_row_and_failed_migration_is_atomic(
    tmp_path, monkeypatch, version, filename
):
    from domus.domain.storage import Installation

    path = tmp_path / "previous.sqlite3"
    with closing(sqlite3.connect(path, autocommit=True)) as db:
        db.executescript((FIXTURES / filename).read_text())
        assert db.execute("PRAGMA user_version").fetchone() == (version,)
        installation = Installation(
            *db.execute("SELECT instance_id,channel FROM installation").fetchone()
        )
        names = [
            row[0]
            for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        columns = {
            name: tuple(row[1] for row in db.execute(f'PRAGMA table_info("{name}")'))
            for name in names
        }
        before = {name: db.execute(f'SELECT * FROM "{name}"').fetchall() for name in names}
    path.chmod(0o600)
    store = SQLiteDatabase(path, installation)
    with closing(sqlite3.connect(path)) as db:
        db.row_factory = sqlite3.Row
        assert _verify_database(db, store, previous=True) == version
    original = path.read_bytes()
    with monkeypatch.context() as patch:
        patch.setattr(
            storage,
            "SCHEDULED_AUTOMATION_STATEMENTS",
            (
                storage.SCHEDULED_AUTOMATION_STATEMENTS[0],
                "invalid migration SQL",
            ),
        )
        with pytest.raises(StorageFailure):
            store.initialize(require_existing=True)
    assert path.read_bytes() == original
    store.initialize(require_existing=True)
    with closing(sqlite3.connect(path)) as db:
        db.row_factory = sqlite3.Row
        assert _verify_database(db, store, previous=False) == 38
        # Older independent migrations append columns (for example movement
        # corrections). Every original column and row must remain identical.
        after = {}
        for name in names:
            projection = ",".join('"' + column + '"' for column in columns[name])
            after[name] = [tuple(row) for row in db.execute(f'SELECT {projection} FROM "{name}"')]
        assert after == before
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    with store.read() as unit:
        assert unit.scheduled_automations.schedules("home") == ()
        assert unit.scheduled_automations.pending("home") == ()


def test_invalid_limits_and_outcomes_never_write_an_admission(tmp_path):
    store, value, queued = source(tmp_path)
    with store.write() as unit:
        records = unit.scheduled_automations
        for size in (True, 0, 102):
            with pytest.raises(InvalidInput):
                records.schedules("home", limit=size)
            with pytest.raises(InvalidInput):
                records.history("home", "daily", limit=size)
        for size in (True, 0, 1002):
            with pytest.raises(InvalidInput):
                records.pending_count("home", limit=size)
        with pytest.raises(InvalidInput):
            records.pending("home", limit=1002)
        with pytest.raises(InvalidInput):
            records.admit(queued.finish(ScheduledOutcome.CANCELLED, queued.admitted_at))
        with pytest.raises(InvalidInput):
            records.finish(queued)
        with pytest.raises(InvalidInput):
            records.save_schedule(
                replace(
                    value,
                    grant=replace(
                        value.grant, installation=replace(store.installation, channel="stable")
                    ),
                ),
                0,
            )
        with pytest.raises(InvalidInput):
            records.admit(
                replace(
                    queued,
                    grant=replace(
                        queued.grant, installation=replace(store.installation, channel="stable")
                    ),
                )
            )
        for before in ((-1, queued.key), (True, queued.key), (0, "bad/key")):
            with pytest.raises(InvalidInput):
                records.history("home", "daily", before=before)
            with pytest.raises(InvalidInput):
                records.pending("home", after=before)


@pytest.mark.parametrize(
    "table, field",
    [
        ("automation_daily_schedules", "next_at=next_at+1"),
        ("automation_scheduled_runs", "admitted_at=admitted_at+1"),
    ],
)
def test_checkpoint_rejects_header_document_disagreement(tmp_path, table, field):
    store, _, value = source(tmp_path)
    with store.write() as unit:
        unit.scheduled_automations.admit(value)
    with closing(sqlite3.connect(store.path, autocommit=True)) as db:
        db.execute(f"UPDATE {table} SET {field}")
        db.row_factory = sqlite3.Row
        with pytest.raises(DatabaseRejected, match="invalid_snapshot_records"):
            _verify_database(db, store, previous=False)
