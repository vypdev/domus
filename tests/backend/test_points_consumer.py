"""Real recurrence, lifecycle, and SQLite witnesses for the Points owner."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from threading import Barrier, Event
from types import SimpleNamespace

import pytest
from test_activation_compatibility import identity_at
from test_household_commands import Clock
from test_recurrence_creation import request as fixed_request
from test_recurrence_creation import setup as fixed_setup
from test_recurrence_review import reviewed
from test_relative_recurrence_creation import request as relative_request
from test_relative_recurrence_creation import setup as relative_setup
from test_task_commands import fixture, resource
from test_task_runtime import api as api

from domus.application.fixed_materialization import FixedMaintenance, MaintenanceScope
from domus.application.fixed_missed_policy import FixedMissedPolicy
from domus.application.fixed_skip_review import FixedSkip
from domus.application.points import PointsConsumer
from domus.application.recurrence_review import RecurrenceReview
from domus.application.recurrence_sources import RecurrenceSourceObservations
from domus.application.relative_lifecycle import RelativeLifecycle
from domus.application.relative_materialization import RelativeMaintenance
from domus.application.relative_recurrence import RelativeRecurrencePlanner
from domus.application.task_requests import (
    CompleteTask,
    CreateTask,
    CreateTaskOccurrence,
    ReopenTask,
    VerifyTask,
)
from domus.domain.errors import Conflict, Forbidden, StorageFailure
from domus.domain.recurrence_rule_text import parse_fixed_pattern
from domus.domain.recurrence_rules import NominalDate
from domus.domain.storage import Installation
from domus.domain.task_values import (
    MissedOccurrencePolicy,
    TaskContent,
    TaskOverrides,
    VerificationState,
)
from domus.infrastructure import sqlite as storage
from domus.infrastructure.owned_storage import open_storage
from domus.infrastructure.sqlite import SQLiteDatabase
from domus.infrastructure.sqlite_activation import SQLiteActivation
from domus.infrastructure.sqlite_points import SQLitePoints
from domus.infrastructure.sqlite_restoration import SQLiteRestorations
from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots


def running():
    return True


def consumer(store):
    return PointsConsumer(store, store.installation, Clock())


def task_value(task, minor):
    return replace(task, overrides=TaskOverrides(point_value_minor=minor))


def cycle_of(receipt):
    return receipt.result.decode()["cycle"]["cycle_id"]


def adult_id(store, commands):
    with store.read() as unit:
        return unit.members.by_user("home", commands.actor.current().ha_user_id).member_id


def test_pending_relative_work_advances_once_before_approval_posts_points(tmp_path):
    creation, tasks, store, _, ids = relative_setup(tmp_path)
    value = relative_request()
    saved = creation.create("schedule", replace(value, task=task_value(value.task, 125)))
    schedule = saved.result.decode()["schedule_id"]
    scope = MaintenanceScope(store.installation, "home")
    initial = RelativeMaintenance(store, scope, creation.times, Clock(), ids).initial(schedule)
    oid = initial.occurrence_id
    completed = tasks.complete("perform", CompleteTask(oid, 1, ("child",), 90))
    source = RecurrenceSourceObservations(store, scope)
    (record,) = source.ingest().items
    lifecycle = RelativeLifecycle(
        store, scope, RelativeRecurrencePlanner(creation.times), Clock(), ids
    )
    successor = lifecycle.consume(schedule, record.event.event_key)
    assert successor.status == "generated" and successor.occurrence_id != oid
    points = consumer(store)
    cid = cycle_of(completed)
    assert points.tick(running) == 1 and points.ledger("home", cid) == ()
    with store.read() as unit:
        assert unit.points.processed("home", completed.operation_id) is not None
    assert (
        SQLiteSnapshots(store, tmp_path / "pending", store.installation, Clock())
        .create("pending-points")
        .schema_version
        == storage.SCHEMA_VERSION
    )
    approved = tasks.verify("approve", VerifyTask(oid, 2, cid, VerificationState.APPROVED))
    restarted = consumer(SQLiteDatabase(store.path, store.installation))
    assert restarted.tick(running) == 1 and restarted.tick(running) == 0
    (award,) = restarted.ledger("home", cid)
    assert (award.event_id, award.shares, award.performed_at, award.precision) == (
        approved.operation_id,
        (("child", 125),),
        90,
        2,
    )
    assert lifecycle.consume(schedule, record.event.event_key) == successor
    with store.read() as unit:
        assert len(unit.tasks.occurrences("home")) == 2
    performed = tasks.complete(
        "perform-successor", CompleteTask(successor.occurrence_id, 1, (adult_id(store, tasks),), 95)
    )
    assert restarted.tick(running) == 1
    downstream_cycle = cycle_of(performed)
    downstream_award = restarted.ledger("home", downstream_cycle)
    assert downstream_award[0].shares[0][1] == 125
    reopened = tasks.reopen("reopen-source", ReopenTask(oid, 3, cid, "Review the source"))
    reopening = next(
        item.event for item in source.ingest().items if item.event.event_id == reopened.operation_id
    )
    assert lifecycle.consume(schedule, reopening.event_key).status == "review"
    assert restarted.tick(running) == 1
    assert restarted.ledger("home", cid) == (award, award.reverse(reopened.operation_id, 100))
    assert restarted.ledger("home", downstream_cycle) == downstream_award


def test_weekly_missed_slots_stay_on_anchor_and_never_earn_points(tmp_path):
    root = tmp_path / "source"
    root.mkdir(mode=0o700)
    setup, tasks, store, actor, ids = fixed_setup(root)
    identity_at(root, store.installation)
    start = date(2026, 3, 30)
    selected = fixed_request()
    task = task_value(selected.task, 200)
    schedule = setup.create_fixed(
        "weekly",
        replace(
            selected,
            task=task,
            pattern=parse_fixed_pattern("FREQ=WEEKLY;COUNT=5", NominalDate(start)),
        ),
    ).result.decode()["schedule_id"]
    missed_clock = SimpleNamespace(
        now=lambda: int(datetime(2026, 4, 23, tzinfo=UTC).timestamp() * 1000)
    )
    maintenance = FixedMaintenance(
        store, MaintenanceScope(store.installation, "home"), setup.planner, missed_clock, ids
    )
    cutoff = NominalDate(start + timedelta(days=29))
    slots = [maintenance.step(schedule, cutoff) for _ in range(5)]
    assert [step.status for step in slots] == ["created"] * 5
    with store.read() as unit:
        assert sorted(
            slot.planned.nominal.local for slot in unit.recurrence.slots("home", schedule)
        ) == [start + timedelta(days=index * 7) for index in range(5)]
        for step in slots[:4]:
            work = unit.tasks.occurrence("home", step.occurrence_id)
            assert work.state.value == "available" and work.current_cycle_id is None
        assert unit.points.position("home") == 0
    review = RecurrenceReview(
        store,
        store.installation,
        actor,
        actor.current,
        missed_clock,
        ids,
        RelativeRecurrencePlanner(setup.planner.times),
    )
    skipped, future = slots[0], slots[-1]
    skip = FixedSkip(
        schedule, 1, skipped.receipt.command.key, skipped.occurrence_id, 1, "Missed work"
    )
    with pytest.raises(Conflict, match="recurrence_skip_policy_required"):
        review.preview("keep-missed", skip)
    _, policy_change = reviewed(
        review,
        FixedMissedPolicy(schedule, 1, 0, MissedOccurrencePolicy.SKIP_AFTER_REVIEW),
        "review-explicit-skip-policy",
    )
    review.apply("enable-explicit-skip", policy_change)
    with pytest.raises(Conflict, match="recurrence_slot_not_overdue"):
        review.preview(
            "future-not-missed",
            replace(skip, slot_key=future.receipt.command.key, occurrence_id=future.occurrence_id),
        )
    _, reviewed_skip = reviewed(review, skip, "review-overdue-skip")
    skipped_result = review.apply("skip-overdue", reviewed_skip)
    assert skipped_result.result.decode()["work"]["state"] == "skipped"
    restarted = replace(review, transactions=SQLiteDatabase(store.path, store.installation))
    assert restarted.apply("skip-overdue", reviewed_skip) == skipped_result
    points = PointsConsumer(store, store.installation, missed_clock)
    assert points.tick(running) == 0
    archive, prepared = tmp_path / "archive", tmp_path / "prepared"
    snapshot = SQLiteSnapshots(store, archive, store.installation, missed_clock).create("missed")
    later_clock = SimpleNamespace(
        now=lambda: int(datetime(2026, 4, 27, 12, tzinfo=UTC).timestamp() * 1000)
    )
    later = replace(tasks, clock=later_clock).complete(
        "later", CompleteTask(future.occurrence_id, 1, (adult_id(store, tasks),), later_clock.now())
    )
    points = replace(points, clock=later_clock)
    assert points.tick(running) == 1
    assert points.ledger("home", cycle_of(later))[0].shares[0][1] == 200
    with closing(sqlite3.connect(store.path)) as connection:
        assert connection.execute("SELECT count(*) FROM points_task_receipts").fetchone() == (1,)
    assert points.tick(running) == 0
    SQLiteRestorations(store, archive, prepared, store.installation, later_clock, snapshot).prepare(
        "restore"
    )
    assert (
        SQLiteActivation(root, store.installation, later_clock, prepared).activate().state
        == "active"
    )
    selected = open_storage(root, "edge")
    try:
        assert consumer(selected.database).tick(running) == 0
        with selected.database.read() as unit:
            assert unit.points.position("home") == 0
            for index, step in enumerate(slots[:4]):
                work = unit.tasks.occurrence("home", step.occurrence_id)
                assert work.state.value == ("skipped" if index == 0 else "available")
                assert work.current_cycle_id is None
    finally:
        selected.close()


def test_concurrent_replay_rollback_and_linked_reversal_preserve_other_cycles(
    tmp_path, monkeypatch
):
    tasks, store, _, _ = fixture(tmp_path)
    did, first = resource(tasks.create("work", task_value(CreateTask(TaskContent("Work")), 1000)))
    child = tasks.create_occurrence("downstream", CreateTaskOccurrence(did, 0))
    later = child.result.decode()["occurrence_id"]
    member = adult_id(store, tasks)
    performers = (member, "child", "other")
    events = [
        tasks.complete(key, CompleteTask(oid, 1, performers, 90))
        for key, oid in (("first", first), ("later", later))
    ]
    cycles = [cycle_of(event) for event in events]
    for number, (oid, cid) in enumerate(zip((first, later), cycles, strict=True)):
        tasks.verify(f"approval-{number}", VerifyTask(oid, 2, cid, VerificationState.APPROVED))

    points = consumer(store)
    original = SQLitePoints.add

    def fail_after_post(self, event, fingerprint, posting):
        original(self, event, fingerprint, posting)
        if posting is not None:
            raise StorageFailure("injected_points_rollback")

    with monkeypatch.context() as patch:
        patch.setattr(SQLitePoints, "add", fail_after_post)
        with pytest.raises(StorageFailure, match="injected_points_rollback"):
            points.tick(running)
    assert all(points.ledger("home", cid) == () for cid in cycles)
    with store.read() as unit:
        assert unit.points.position("home") == 0

    start = Barrier(2)

    def consume_independently():
        start.wait(timeout=3)
        return consumer(SQLiteDatabase(store.path, store.installation, busy_timeout=5)).tick(
            running
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        runs = [pool.submit(consume_independently) for _ in range(2)]
        assert sorted(run.result(timeout=5) for run in runs) == [0, 4]
    first_award, later_award = [points.ledger("home", cid)[0] for cid in cycles]
    assert sorted(amount for _, amount in first_award.shares) == [300, 300, 400]
    assert sorted(amount for _, amount in later_award.shares) == [300, 300, 400]
    assert first_award.shares != later_award.shares
    reopened = tasks.reopen("reopen", ReopenTask(first, 3, cycles[0], "Original work needs review"))
    assert points.tick(running) == 1
    assert points.ledger("home", cycles[0]) == (
        first_award,
        first_award.reverse(reopened.operation_id, 100),
    )
    assert points.ledger("home", cycles[1]) == (later_award,)
    assert points.tick(running) == 0


def test_delayed_completion_of_closed_cycle_has_no_posting_or_reversal(tmp_path):
    tasks, store, _, _ = fixture(tmp_path)
    _, oid = resource(tasks.create("work", task_value(CreateTask(TaskContent("Work")), 200)))
    done = tasks.complete("perform", CompleteTask(oid, 1, (adult_id(store, tasks),), 90))
    cid = cycle_of(done)
    reopened = tasks.reopen("reopen", ReopenTask(oid, 2, cid, "Closed before delivery"))
    points = consumer(store)
    assert points.tick(lambda: False) == 0
    assert points.tick(running) == 2 and points.ledger("home", cid) == ()
    with store.read() as unit:
        assert unit.points.processed("home", done.operation_id)
        assert unit.points.processed("home", reopened.operation_id)


def test_migration_imports_genuine_schema_15_without_precredit_or_partial_ddl(
    tmp_path, monkeypatch
):
    path = tmp_path / "source.sqlite3"
    fixture_path = Path(__file__).parents[1] / "fixtures/sqlite/v15-points-source.sql"
    with closing(sqlite3.connect(path, autocommit=True)) as connection:
        connection.executescript(fixture_path.read_text())
        identity = Installation(
            *connection.execute("SELECT instance_id,channel FROM installation").fetchone()
        )
    store = SQLiteDatabase(path, identity)
    baseline = path.read_bytes()
    with monkeypatch.context() as patch:
        patch.setattr(storage, "POINTS_STATEMENTS", (*storage.POINTS_STATEMENTS, "invalid SQL"))
        with pytest.raises(StorageFailure):
            store.initialize(require_existing=True)
    assert path.read_bytes() == baseline
    store.initialize(require_existing=True)
    with store.read() as unit:
        eligible, pending = sorted(unit.tasks.cycles("home"), key=lambda cycle: cycle.verification)
        assert unit.points.position("home") == 0
    points = consumer(store)
    assert points.tick(running) == 2
    assert points.ledger("home", pending.cycle_id) == ()
    assert points.ledger("home", eligible.cycle_id)[0].shares[0][1] == 300


def test_checkpoint_restore_preserves_award_and_does_not_replay_historical_reversal(tmp_path):
    root = tmp_path / "source"
    root.mkdir(mode=0o700)
    tasks, store, _, _ = fixture(root)
    identity_at(root, store.installation)
    _, oid = resource(tasks.create("work", task_value(CreateTask(TaskContent("Work")), 200)))
    done = tasks.complete("perform", CompleteTask(oid, 1, (adult_id(store, tasks),), 90))
    points = consumer(store)
    assert points.tick(running) == 1
    cid = cycle_of(done)
    original = points.ledger("home", cid)
    archive, prepared = tmp_path / "archive", tmp_path / "prepared"
    snapshot = SQLiteSnapshots(store, archive, store.installation, Clock()).create("posted")
    tasks.reopen("reopen", ReopenTask(oid, 2, cid, "Reopen after checkpoint"))
    assert points.tick(running) == 1 and len(points.ledger("home", cid)) == 2
    SQLiteRestorations(store, archive, prepared, store.installation, Clock(), snapshot).prepare(
        "restore"
    )
    assert (
        SQLiteActivation(root, store.installation, Clock(), prepared).activate().state == "active"
    )
    selected = open_storage(root, "edge")
    try:
        restored = consumer(selected.database)
        assert restored.ledger("home", cid) == original
        assert restored.tick(running) == 0
    finally:
        selected.close()


def test_points_runtime_has_same_internal_consumer_and_owned_worker(api, monkeypatch):
    from test_task_http import checked, create

    oid = create(api)["result"]["occurrence_id"]
    member = api.client.get("/api/v1/members").json()["members"][0]["member_id"]
    done = checked(
        api,
        "post",
        f"/occurrences/{oid}/complete",
        {"expected_revision": 1, "performer_ids": [member], "performed_at": 90},
        "perform",
    )
    worked = Event()
    worker = api.runtime.points_worker
    original = worker._tick

    def observed(keep_running):
        result = original(keep_running)
        worked.set()
        return result

    monkeypatch.setattr(worker, "_tick", observed)
    with api.client:
        assert worked.wait(3)
        assert api.runtime.points.ledger("home", done["result"]["cycle"]["cycle_id"])[0].shares == (
            (member, 0),
        )
    assert not worker.is_running


def test_unconfigured_and_foreign_points_consumers_have_no_effect(tmp_path):
    from test_household_commands import fixture as household

    _, store, _, _, _ = household(tmp_path / "unconfigured.sqlite3")
    assert consumer(store).tick(running) == 0
    foreign = replace(
        consumer(store), installation=Installation(store.installation.instance_id, "stable")
    )
    with pytest.raises(Forbidden, match="maintenance_scope_denied"):
        foreign.tick(running)
    with pytest.raises(Forbidden, match="maintenance_scope_denied"):
        foreign.ledger("home", "any-cycle")


def test_restored_open_snapshot_cannot_credit_a_cycle_already_closed_before_restore(tmp_path):
    root = tmp_path / "source"
    root.mkdir(mode=0o700)
    tasks, store, _, _ = fixture(root)
    identity_at(root, store.installation)
    _, oid = resource(tasks.create("work", task_value(CreateTask(TaskContent("Work")), 250)))
    done = tasks.complete("perform", CompleteTask(oid, 1, (adult_id(store, tasks),), 90))
    cid = cycle_of(done)
    archive, prepared = tmp_path / "archive", tmp_path / "prepared"
    snapshot = SQLiteSnapshots(store, archive, store.installation, Clock()).create("pending")
    tasks.reopen("reopen", ReopenTask(oid, 2, cid, "Closed before the Points worker ran"))
    SQLiteRestorations(store, archive, prepared, store.installation, Clock(), snapshot).prepare(
        "restore"
    )
    result = SQLiteActivation(root, store.installation, Clock(), prepared).activate()
    assert result.state == "active"
    selected = open_storage(root, "edge")
    try:
        points = consumer(selected.database)
        assert points.tick(running) == 1
        assert points.ledger("home", cid) == ()
    finally:
        selected.close()


def test_same_event_replay_requires_identical_original_fingerprint(tmp_path):
    from domus.application.task_events import TaskEventFeed

    tasks, store, _, _ = fixture(tmp_path)
    _, oid = resource(tasks.create("work", task_value(CreateTask(TaskContent("Work")), 100)))
    tasks.complete("perform", CompleteTask(oid, 1, (adult_id(store, tasks),), 90))
    (event,) = TaskEventFeed(store, store.installation).read().items
    points = consumer(store)
    assert points.tick(running) == 1
    original = points.ledger("home", event.cycle.cycle_id)
    with store.write() as unit:
        points._record(unit, event)
    with pytest.raises(StorageFailure, match="invalid_points_source"), store.write() as unit:
        points._record(unit, replace(event, occurred_at=event.occurred_at + 1))
    assert points.ledger("home", event.cycle.cycle_id) == original


@pytest.mark.parametrize(
    ("mutation", "effect", "error"),
    [
        ("position=1", 1, "invalid_points_source"),
        ("fingerprint=printf('%064d', 0)", 1, "invalid_points_source"),
        ("document=json_remove(document, '$.shares')", 1, "invalid_points_posting"),
        ("document=json_set(document, '$.shares[0][1]', 0)", 1, "invalid_points_posting"),
        ("document=json_set(document, '$.shares[0][1]', 0)", 2, "invalid_points_posting"),
        ("document=json_set(document, '$.event_id', 'another')", 2, "invalid_points_posting"),
    ],
)
def test_snapshot_rejects_tampered_receipts_and_ledger_facts(tmp_path, mutation, effect, error):
    from domus.domain.errors import DatabaseRejected

    tasks, store, _, _ = fixture(tmp_path)
    _, oid = resource(tasks.create("work", task_value(CreateTask(TaskContent("Work")), 100)))
    completed = tasks.complete("perform", CompleteTask(oid, 1, (adult_id(store, tasks),), 90))
    points = consumer(store)
    assert points.tick(running) == 1
    tasks.reopen("reopen", ReopenTask(oid, 2, cycle_of(completed), "Review original work"))
    assert points.tick(running) == 1
    snapshots = SQLiteSnapshots(store, tmp_path / "snapshot", store.installation, Clock())
    assert snapshots.create("pristine").schema_version == storage.SCHEMA_VERSION
    with closing(sqlite3.connect(store.path, autocommit=True)) as connection:
        connection.execute(f"UPDATE points_task_receipts SET {mutation} WHERE effect=?", (effect,))
    with pytest.raises(DatabaseRejected, match="invalid_snapshot_records") as rejected:
        snapshots.create("corrupt")
    assert str(rejected.value.__cause__) == error


@pytest.mark.parametrize(
    "changes",
    [
        {"precision": False},
        {"precision": 1},
        {"policy_version": "unsupported"},
        {"shares": ()},
        {"shares": (("member", True),)},
        {"shares": (("member", 1_000_100),)},
        {"shares": (("member", 99),)},
        {"shares": (("member", -100),)},
        {"shares": (("member", 100),), "reverses": "award"},
        {"shares": (("first", 1_000_000), ("second", 100))},
    ],
)
def test_postings_reject_invalid_precision_shares_and_totals(changes):
    from domus.domain.errors import InvalidInput
    from domus.domain.points import PointsPosting

    original = PointsPosting("event", "cycle", "definition", (("member", 100),), 5, 10, 0, None)
    with pytest.raises(InvalidInput, match="invalid_points_posting"):
        replace(original, **changes)


def test_a_reversal_cannot_be_reversed_again():
    from domus.domain.errors import InvalidInput
    from domus.domain.points import PointsPosting

    original = PointsPosting("event", "cycle", "definition", (("member", 0),), 5, 10, 0, None)
    with pytest.raises(InvalidInput, match="invalid_points_reversal"):
        original.reverse("close", 11).reverse("repeat", 12)
