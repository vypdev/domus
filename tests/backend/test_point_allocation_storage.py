"""Durable allocation across a real v17 upgrade, concurrent writes and snapshots."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from datetime import date
from pathlib import Path
from threading import Barrier

import pytest
from test_household_commands import Clock
from test_points_consumer import consumer, cycle_of
from test_task_commands import fixture, resource

from domus.application.family_queries import FamilyQueries
from domus.application.fixed_materialization import MaintenanceScope
from domus.application.point_allocations import AllocationCommands
from domus.application.task_requests import CompleteTask, CreateTask, ReopenTask, VerifyTask
from domus.domain.calendar_values import CalendarRange
from domus.domain.errors import Conflict, DatabaseRejected, StorageFailure
from domus.domain.identity import HumanIdentity
from domus.domain.point_allocation import AllocationMode, AllocationPolicy
from domus.domain.storage import Installation
from domus.domain.task_values import TaskContent, TaskOverrides, VerificationState
from domus.infrastructure import sqlite as storage
from domus.infrastructure.recurrence_time import PinnedRecurrenceTime
from domus.infrastructure.sqlite import SQLiteDatabase
from domus.infrastructure.sqlite_point_allocations import verify_point_allocations
from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots
from domus.infrastructure.task_cursor import TaskCursor


def test_real_schema17_migrates_without_rewriting_pending_or_posted_awards(tmp_path, monkeypatch):
    path = tmp_path / "domus.sqlite3"
    fixture_path = Path(__file__).parents[1] / "fixtures/sqlite/v17-allocation-source.sql"
    with closing(sqlite3.connect(path, autocommit=True)) as connection:
        connection.executescript(fixture_path.read_text())
        installation = Installation(
            *connection.execute("SELECT instance_id,channel FROM installation").fetchone()
        )
        assert connection.execute("PRAGMA user_version").fetchone() == (17,)
        original = connection.execute(
            "SELECT * FROM points_task_receipts ORDER BY position"
        ).fetchall()
    path.chmod(0o600)
    store = SQLiteDatabase(path, installation)
    before = path.read_bytes()
    with monkeypatch.context() as patch:
        patch.setattr(storage, "ALLOCATION_STATEMENTS", (*storage.ALLOCATION_STATEMENTS, "broken"))
        with pytest.raises(StorageFailure):
            store.initialize(require_existing=True)
    assert path.read_bytes() == before
    store.initialize(require_existing=True)
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (25,)
        assert (
            connection.execute("SELECT * FROM points_task_receipts ORDER BY position").fetchall()
            == original
        )
    bounds = CalendarRange(date(1970, 1, 1), date(1970, 1, 2))

    def report(user, admin=False):
        return FamilyQueries(
            store,
            MaintenanceScope(installation, "home"),
            HumanIdentity(user, admin, True, False),
            TaskCursor(Clock(), b"x" * 32),
            PinnedRecurrenceTime(),
        ).report(bounds, limit=10, cursor=None)

    assert report("ha_child").pending_verification_minor == 125
    (award,) = report("ha_admin", True).history
    assert award.amount_minor == award.allocation.total_minor == 300
    assert award.policy_version == "conserve_total.v1" and award.allocation.policy_revision == 0
    checkpoint = SQLiteSnapshots(store, tmp_path / "checkpoint", installation, Clock()).create(
        "legacy"
    )
    assert checkpoint.schema_version == 25


def test_concurrent_replay_freezes_once_and_reopened_pending_work_uses_fresh_policy(tmp_path):
    tasks, store, actor, ids = fixture(tmp_path)
    definition, occurrence = resource(
        tasks.create(
            "create",
            CreateTask(TaskContent("Garden"), overrides=TaskOverrides(point_value_minor=1000)),
        )
    )
    settings = AllocationCommands(store, actor, Clock(), ids)
    initial = settings.configure("initial", None, AllocationPolicy(), 0)
    complete = CompleteTask(occurrence, 1, ("child", "other"), 90)
    start = Barrier(2)

    def record():
        start.wait()
        return tasks.complete("record", complete)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = [future.result() for future in (pool.submit(record), pool.submit(record))]
    assert first == second
    cycle_id = cycle_of(first)
    with store.read() as unit:
        (cycle,) = unit.tasks.cycles("home")
        frozen = unit.point_allocations.snapshot("home", cycle_id)
        assert cycle.cycle_id == cycle_id and frozen.policy_revision == 1
        assert frozen.allocation.shares == (("child", 500), ("other", 500))
    reopened = tasks.reopen("before-award", ReopenTask(occurrence, 2, cycle_id, "Record again"))
    assert (
        consumer(store).tick(lambda: True) == 2 and consumer(store).ledger("home", cycle_id) == ()
    )
    full = AllocationPolicy(AllocationMode.FULL_PER_PARTICIPANT)
    with pytest.raises(Conflict, match="revision_conflict"):
        settings.configure("stale", None, full, 0)
    assert settings.configure("initial", None, AllocationPolicy(), 0) == initial
    settings.configure("override", definition, full, 0)
    second = tasks.complete(
        "record-again", replace(complete, expected_revision=reopened.result.decode()["revision"])
    )
    second_id = cycle_of(second)
    assert second_id != cycle_id
    tasks.verify(
        "approve",
        VerifyTask(
            occurrence, second.result.decode()["revision"], second_id, VerificationState.APPROVED
        ),
    )
    reopened_store = SQLiteDatabase(store.path, store.installation)
    points = consumer(reopened_store)
    assert points.tick(lambda: True) == 2 and points.tick(lambda: True) == 0
    (award,) = points.ledger("home", second_id)
    assert award.shares == (("child", 1000), ("other", 1000))
    with reopened_store.read() as unit:
        assert unit.point_allocations.snapshot("home", cycle_id) == frozen


@pytest.mark.parametrize(
    ("statement", "expected"),
    [
        ("UPDATE point_allocation_settings SET document='{}'", "invalid_points_policy"),
        ("UPDATE point_completion_allocations SET document='{}'", "invalid_points_allocation"),
        (
            "UPDATE point_completion_allocations SET definition_id='wrong'",
            "invalid_points_allocation",
        ),
        (
            "UPDATE point_completion_allocations SET document=json_set("
            "document,'$.base',0,'$.allocation.next_recipient',NULL,"
            "'$.allocation.shares',json('[[\"child\",0],[\"other\",0]]'))",
            "invalid_points_allocation",
        ),
        (
            "UPDATE point_completion_allocations SET document=json_set("
            "document,'$.previous_recipient','child','$.allocation.next_recipient','other',"
            "'$.allocation.shares',json('[[\"child\",600],[\"other\",500]]')) WHERE position=2",
            "invalid_points_rotation",
        ),
    ],
)
def test_checkpoint_rejects_corrupted_settings_frozen_award_and_rotation(
    tmp_path, statement, expected
):
    tasks, store, actor, ids = fixture(tmp_path)
    settings = AllocationCommands(store, actor, Clock(), ids)
    settings.configure("default", None, AllocationPolicy(), 0)
    _, work = resource(
        tasks.create(
            "create",
            CreateTask(TaskContent("Garden"), overrides=TaskOverrides(point_value_minor=1100)),
        )
    )
    original = tasks.complete("first", CompleteTask(work, 1, ("child", "other"), 90))
    tasks.reopen("reopen", ReopenTask(work, 2, cycle_of(original), "Try again"))
    tasks.complete("second", CompleteTask(work, 3, ("child", "other"), 90))
    with closing(sqlite3.connect(store.path, autocommit=True)) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute(statement)
        with pytest.raises(StorageFailure, match=expected):
            verify_point_allocations(connection)
    snapshots = SQLiteSnapshots(store, tmp_path / "checkpoint", store.installation, Clock())
    with pytest.raises(DatabaseRejected, match="invalid_snapshot_(database|records)"):
        snapshots.create("corrupted")


def test_writer_failure_after_freezing_rolls_back_cycle_and_rotation(tmp_path, monkeypatch):
    from domus.infrastructure.sqlite_point_allocations import SQLitePointAllocations

    tasks, store, actor, ids = fixture(tmp_path)
    AllocationCommands(store, actor, Clock(), ids).configure("default", None, AllocationPolicy(), 0)
    definition, occurrence = resource(
        tasks.create(
            "create",
            CreateTask(TaskContent("Garden"), overrides=TaskOverrides(point_value_minor=1100)),
        )
    )
    original = SQLitePointAllocations.freeze

    def interrupted(repository, *args):
        original(repository, *args)
        raise StorageFailure("allocation_interrupted")

    request = CompleteTask(occurrence, 1, ("child", "other"), 90)
    with monkeypatch.context() as patch:
        patch.setattr(SQLitePointAllocations, "freeze", interrupted)
        with pytest.raises(StorageFailure, match="allocation_interrupted"):
            tasks.complete("complete", request)
    with store.read() as unit:
        assert unit.tasks.cycles("home") == ()
        assert unit.point_allocations.last_conserved("home", definition) is None
    committed = tasks.complete("complete", request)
    assert tasks.complete("complete", request) == committed
    with store.read() as unit:
        allocation = unit.point_allocations.snapshot("home", cycle_of(committed))
        assert allocation.previous_recipient is None
        assert allocation.allocation.shares == (("child", 600), ("other", 500))
