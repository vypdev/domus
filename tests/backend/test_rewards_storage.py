"""Reward commands share the real SQLite writer with Points and recovery."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from threading import Barrier

import pytest
from test_activation_compatibility import identity_at
from test_household_commands import Clock
from test_points_consumer import adult_id, consumer, cycle_of
from test_task_commands import fixture, resource

from domus.application.reward_commands import RewardAction, RewardCommands
from domus.application.reward_funding import reward_balance
from domus.application.task_requests import CompleteTask, CreateTask, ReopenTask
from domus.domain.errors import Conflict, StorageFailure
from domus.domain.identity import Role
from domus.domain.rewards import RedemptionStage
from domus.domain.storage import Installation
from domus.domain.task_values import TaskContent, TaskOverrides
from domus.infrastructure import sqlite as storage
from domus.infrastructure.owned_storage import open_storage
from domus.infrastructure.sqlite import SQLiteDatabase
from domus.infrastructure.sqlite_activation import SQLiteActivation
from domus.infrastructure.sqlite_restoration import SQLiteRestorations
from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots


def setup(root, *, cost=800):
    tasks, store, actor, ids = fixture(root)
    commands = RewardCommands(store, actor, Clock(), ids)
    commands.configure("enabled", True, 0)
    offer = commands.offer("offer", None, "Movie", cost, True, tuple(Role), 0).result.decode()
    return tasks, store, commands, offer["offer_id"], adult_id(store, tasks)


def award(tasks, points, member, key, amount=1000):
    _, oid = resource(
        tasks.create(
            key, CreateTask(TaskContent(key), overrides=TaskOverrides(point_value_minor=amount))
        )
    )
    saved = tasks.complete(key, CompleteTask(oid, 1, (member,), 90))
    assert points.tick(lambda: True) == 1
    return ReopenTask(oid, 2, cycle_of(saved), "Review the original work")


def race(first, second):
    start = Barrier(2)

    def execute(operation):
        start.wait()
        try:
            return operation()
        except Conflict as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        return tuple(
            future.result()
            for future in (pool.submit(execute, first), pool.submit(execute, second))
        )


def test_two_requests_compete_for_one_funded_reservation(tmp_path):
    tasks, store, commands, offer, member = setup(tmp_path)
    award(tasks, consumer(store), member, "credit")
    first, second = race(
        lambda: commands.request("first", offer, 1),
        lambda: commands.request("second", offer, 1),
    )
    saved, rejected = (second, first) if isinstance(first, str) else (first, second)
    assert rejected == "insufficient_reward_points"
    with store.read() as unit:
        (redemption,) = unit.rewards.requests("home", member, after=None, limit=10)
        assert redemption.redemption_id == saved.result.decode()["redemption_id"]
        assert redemption.cost_minor == 800 and unit.rewards.reservations("home", member) == (
            800,
            1,
        )


@pytest.mark.parametrize("action", ["request", "deliver"])
def test_reversal_serializes_with_reward_admission_and_delivery(tmp_path, action):
    tasks, store, commands, offer, member = setup(tmp_path)
    points = consumer(store)
    reopen = award(tasks, points, member, "credit")
    redemption_id = None
    if action == "deliver":
        redemption_id = commands.request("request", offer, 1).result.decode()["redemption_id"]
        commands.approve("approve", redemption_id)
    tasks.reopen("reopen", reopen)
    result, processed = race(
        lambda: (
            commands.request("request", offer, 1)
            if action == "request"
            else commands.deliver("deliver", redemption_id)
        ),
        lambda: points.tick(lambda: True),
    )
    assert processed == 1
    with store.read() as unit:
        balance = reward_balance(unit, "home", member, unit.points.member_balance("home", member))
        requests = unit.rewards.requests("home", member, after=None, limit=10)
    if action == "request":
        assert balance.posted_minor == 0
        if isinstance(result, str):
            assert result == "insufficient_reward_points" and requests == ()
        else:
            assert requests[0].stage is RedemptionStage.REQUESTED
            assert balance.reserved_minor == 800 and balance.available_minor == -800
    elif isinstance(result, str):
        assert result == "reward_funding_hold"
        assert (
            requests[0].stage is RedemptionStage.FUNDING_HOLD and requests[0].approval is not None
        )
        assert balance.posted_minor == 0 and balance.reserved_minor == 800
    else:
        assert requests[0].stage is RedemptionStage.DELIVERED
        assert balance.posted_minor == -800 and balance.reserved_minor == 0


def test_cancellation_restores_funding_without_delivering_and_seals_history(tmp_path):
    tasks, store, commands, offer, member = setup(tmp_path, cost=500)
    points = consumer(store)
    reopen = award(tasks, points, member, "credit-one", 500)
    award(tasks, points, member, "credit-two", 500)
    first = commands.request("first", offer, 1).result.decode()["redemption_id"]
    second = commands.request("second", offer, 1).result.decode()["redemption_id"]
    commands.approve("approve", first)
    tasks.reopen("reopen", reopen)
    assert points.tick(lambda: True) == 1
    with store.read() as unit:
        held = unit.rewards.redemption("home", first)
        assert held.stage is RedemptionStage.FUNDING_HOLD and held.approval is not None
    commands.cancel("cancel", second, 1, "Free the reservation")
    with store.read() as unit:
        funded = unit.rewards.redemption("home", first)
        assert funded.stage is RedemptionStage.APPROVED and funded.approval == held.approval
        assert unit.rewards.reservations("home", member) == (500, 1)
        assert unit.rewards.spent("home", member) == 0
    snapshots = SQLiteSnapshots(store, tmp_path / "checkpoint", store.installation, Clock())
    checkpoint = snapshots.create("funded")
    assert snapshots.inspect() == checkpoint


def test_restore_preserves_hold_and_returns_later_delivery_as_historical(tmp_path):
    root = tmp_path / "source"
    root.mkdir(mode=0o700)
    tasks, store, commands, offer, member = setup(root)
    identity_at(root, store.installation)
    points = consumer(store)
    reopen = award(tasks, points, member, "credit")
    rid = commands.request("request", offer, 1).result.decode()["redemption_id"]
    commands.approve("approve", rid)
    tasks.reopen("reopen", reopen)
    assert points.tick(lambda: True) == 1
    archive, target = tmp_path / "archive", tmp_path / "prepared"
    checkpoint = SQLiteSnapshots(store, archive, store.installation, Clock()).create("held")
    award(tasks, points, member, "later-credit")
    delivered = commands.deliver("deliver", rid)
    assert commands.deliver("deliver", rid) == delivered
    prepared = SQLiteRestorations(store, archive, target, store.installation, Clock(), checkpoint)
    prepared.prepare("restore-rewards")
    assert SQLiteActivation(root, store.installation, Clock(), target).activate().state == "active"
    restored = open_storage(root, "edge")
    try:
        commands = replace(commands, store=restored.database)
        history = commands.original(RewardAction.DELIVER, "deliver", commands.actor.current())
        assert history.historical and history.operation_id == delivered.operation_id
        assert commands.deliver("deliver", rid) == history
        assert consumer(restored.database).tick(lambda: True) == 0
        with restored.database.read() as unit:
            record = unit.rewards.redemption("home", rid)
            assert record.stage is RedemptionStage.FUNDING_HOLD and record.approval is not None
            assert unit.rewards.reservations("home", member) == (800, 1)
            assert unit.rewards.spent("home", member) == 0
    finally:
        restored.close()


def test_real_schema18_migrates_without_creating_reservations(tmp_path, monkeypatch):
    path = tmp_path / "domus.sqlite3"
    fixture = Path(__file__).parents[1] / "fixtures/sqlite/v18-rewards-source.sql"
    with closing(sqlite3.connect(path, autocommit=True)) as connection:
        connection.executescript(fixture.read_text())
        installation = Installation(
            *connection.execute("SELECT instance_id,channel FROM installation").fetchone()
        )
        assert connection.execute("PRAGMA user_version").fetchone() == (18,)
        prior = connection.execute(
            "SELECT * FROM points_task_receipts ORDER BY position"
        ).fetchall()
    path.chmod(0o600)
    store = SQLiteDatabase(path, installation)
    baseline = path.read_bytes()
    with monkeypatch.context() as patch:
        patch.setattr(storage, "REWARD_STATEMENTS", (*storage.REWARD_STATEMENTS, "broken"))
        with pytest.raises(StorageFailure):
            store.initialize(require_existing=True)
    assert path.read_bytes() == baseline
    store.initialize(require_existing=True)
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (21,)
        assert (
            connection.execute("SELECT * FROM points_task_receipts ORDER BY position").fetchall()
            == prior
        )
    with store.read() as unit:
        assert unit.rewards.setting("home") is None
        assert unit.rewards.reservations("home", "identity-1") == (0, 0)
        assert unit.rewards.spent("home", "identity-1") == 0
        assert unit.points.member_balance("home", "identity-1") > 0


def test_reward_commands_fail_closed_at_revisions_limits_eligibility_and_original_scope(
    tmp_path, monkeypatch
):
    from domus.application import reward_commands
    from domus.domain.errors import Forbidden, InvalidInput, NotFound
    from domus.domain.storage import CommandKey, JsonDocument, Receipt

    tasks, store, commands, offer, member = setup(tmp_path, cost=100)
    with pytest.raises(InvalidInput, match="invalid_revision"):
        commands.configure("invalid", False, -1)
    with pytest.raises(Conflict, match="revision_conflict"):
        commands.configure("stale", False, 0)
    with pytest.raises(Forbidden, match="permission_denied"):
        commands.offer("unknown", "missing", "Unknown", 100, True, tuple(Role), 1)
    with pytest.raises(NotFound, match="operation_missing"):
        commands.original(RewardAction.REQUEST, "missing", commands.actor.current())
    with pytest.raises(Forbidden, match="reward_unavailable"):
        commands.request("missing-offer", "missing", 1)

    with monkeypatch.context() as patch:
        patch.setattr(reward_commands, "CATALOG_LIMIT", 1)
        with pytest.raises(Conflict, match="reward_catalog_capacity"):
            commands.offer("over-catalog", None, "Other", 100, True, tuple(Role), 0)
    commands.offer("disable", offer, "Movie", 100, False, tuple(Role), 1)
    with pytest.raises(Forbidden, match="reward_unavailable"):
        commands.request("disabled-offer", offer, 2)
    commands.offer("restrict", offer, "Movie", 100, True, (Role.ADULT,), 2)
    with pytest.raises(Forbidden, match="reward_unavailable"):
        commands.request("ineligible", offer, 3)
    commands.offer("enable", offer, "Movie", 100, True, tuple(Role), 3)
    award(tasks, consumer(store), member, "credit")
    rid = commands.request("first", offer, 4).result.decode()["redemption_id"]
    commands.approve("approve", rid)
    award(tasks, consumer(store), member, "additional-credit")
    with monkeypatch.context() as patch:
        patch.setattr(reward_commands, "OPEN_REDEMPTION_LIMIT", 1)
        with pytest.raises(Conflict, match="reward_request_capacity"):
            commands.request("over-requests", offer, 4)

    with store.write() as unit:
        actor = commands.actor.current()
        key = CommandKey("home", actor.ha_user_id, "reward.request", "previous-member")
        result = JsonDocument.from_value({"requester_member_id": "different-member"})
        unit.receipts.add(Receipt(key, result.fingerprint, "historical-reward", result, 100))
    with pytest.raises(Forbidden, match="permission_denied"):
        commands.original(RewardAction.REQUEST, "previous-member", commands.actor.current())


@pytest.mark.parametrize(
    ("update", "code"),
    [
        ("UPDATE reward_offers SET document='{}'", "invalid_reward_offer"),
        (
            "UPDATE reward_offers SET document=json_set(document,'$.offer_id','wrong')",
            "invalid_reward_offer",
        ),
        ("UPDATE reward_redemptions SET document='{}' WHERE position=1", "invalid_redemption"),
        ("UPDATE reward_redemptions SET cost_minor=1 WHERE position=1", "invalid_redemption"),
        ("DELETE FROM reward_spends", "invalid_reward_spend"),
        ("UPDATE reward_spends SET cost_minor=1", "invalid_reward_spend"),
        (
            "INSERT INTO reward_spends SELECT household_id,redemption_id,member_id,"
            "cost_minor,100,'Movie' "
            "FROM reward_redemptions WHERE position=2",
            "invalid_reward_spend",
        ),
        (
            "UPDATE reward_redemptions SET stage='funding_hold',"
            "document=json_set(document,'$.stage','funding_hold') "
            "WHERE position=2",
            "invalid_reward_funding",
        ),
        (
            "UPDATE reward_funding_changes SET source_id='missing' WHERE source='points'",
            "invalid_reward_funding",
        ),
        (
            "UPDATE reward_funding_changes SET source_id='missing' WHERE source='cancellation'",
            "invalid_reward_funding",
        ),
        (
            "UPDATE reward_funding_changes SET revision=100 WHERE source='points'",
            "invalid_reward_funding",
        ),
    ],
)
def test_corrupted_reward_evidence_cannot_be_used_for_restore(tmp_path, update, code):
    from domus.domain.errors import DatabaseRejected
    from domus.infrastructure.sqlite_rewards import verify_reward_records

    tasks, store, commands, offer, member = setup(tmp_path, cost=500)
    points = consumer(store)
    first_credit = award(tasks, points, member, "first", 500)
    award(tasks, points, member, "second", 1000)
    first = commands.request("first", offer, 1).result.decode()["redemption_id"]
    second = commands.request("second", offer, 1).result.decode()["redemption_id"]
    third = commands.request("third", offer, 1).result.decode()["redemption_id"]
    commands.approve("approve-first", first)
    commands.approve("approve-second", second)
    commands.deliver("deliver", first)
    tasks.reopen("reopen", first_credit)
    assert points.tick(lambda: True) == 1
    commands.cancel("cancel", third, 1, "Leave points available")
    with closing(sqlite3.connect(store.path, autocommit=True)) as connection:
        connection.row_factory = sqlite3.Row
        verify_reward_records(connection)
        connection.execute(update)
        with pytest.raises(StorageFailure, match=code):
            verify_reward_records(connection)
    snapshots = SQLiteSnapshots(store, tmp_path / "checkpoint", store.installation, Clock())
    with pytest.raises(DatabaseRejected, match="invalid_snapshot_records"):
        snapshots.create("corrupted")


def test_activated_checkpoint_retains_open_approved_delivered_and_cancelled_requests(tmp_path):
    root = tmp_path / "source"
    root.mkdir(mode=0o700)
    tasks, store, commands, offer, member = setup(root, cost=200)
    identity_at(root, store.installation)
    points = consumer(store)
    award(tasks, points, member, "credit")

    def request(key):
        return commands.request(key, offer, 1).result.decode()["redemption_id"]

    pending, approved, delivered, cancelled = map(
        request, ("pending", "approved", "delivered", "cancelled")
    )
    commands.approve("approve-one", approved)
    commands.approve("approve-two", delivered)
    commands.deliver("deliver", delivered)
    commands.cancel("cancel", cancelled, 1, "Plans changed")
    archive, target = tmp_path / "archive", tmp_path / "prepared"
    snapshot = SQLiteSnapshots(store, archive, store.installation, Clock()).create("all-stages")
    commands.cancel("cancel-after-snapshot", pending, 1, "Later change")
    SQLiteRestorations(store, archive, target, store.installation, Clock(), snapshot).prepare(
        "restore-stages"
    )
    assert SQLiteActivation(root, store.installation, Clock(), target).activate().state == "active"
    restored = open_storage(root, "edge")
    try:
        with restored.database.read() as unit:
            requests = unit.rewards.requests("home", member, after=None, limit=10)
            assert {item.redemption_id: item.stage for item in requests} == {
                pending: RedemptionStage.REQUESTED,
                approved: RedemptionStage.APPROVED,
                delivered: RedemptionStage.DELIVERED,
                cancelled: RedemptionStage.CANCELLED,
            }
            assert unit.rewards.reservations("home", member) == (400, 2)
            assert unit.rewards.spent("home", member) == 200
        assert consumer(restored.database).tick(lambda: True) == 0
    finally:
        restored.close()
