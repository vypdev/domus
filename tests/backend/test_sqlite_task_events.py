"""The consumer source reads current durable facts independently of transport acknowledgement."""

import pytest
from test_task_events import prepared

from domus.application.task_commands import CompleteTask, ReopenTask
from domus.application.task_events import TaskEventFeed
from domus.domain.errors import InvalidInput


def test_delivered_transport_rows_remain_available_to_each_owning_consumer(tmp_path):
    _, store, _, _, _, done = prepared(tmp_path)
    feed = TaskEventFeed(store, store.installation)
    original = feed.read()
    with store.write() as unit:
        assert unit.outbox.acknowledge(done.operation_id)
    assert feed.read() == original


@pytest.mark.parametrize(
    "values",
    [
        {"limit": True},
        {"limit": 0},
        {"limit": 102},
        {"after": True},
        {"after": -1},
        {"after": 2**63},
    ],
)
def test_sqlite_event_source_enforces_its_own_bounded_port_contract(tmp_path, values):
    _, store, _, _, _, _ = prepared(tmp_path)
    with store.read() as unit:
        with pytest.raises(InvalidInput):
            unit.tasks.lifecycle_events("home", **values)


def test_event_pages_keep_positions_and_distinct_cycles_beyond_maximum_page(tmp_path):
    commands, store, _, _, oid, done = prepared(tmp_path)
    cid = done.result.decode()["cycle"]["cycle_id"]
    member = done.result.decode()["cycle"]["performers"][0]["member_id"]
    for number in range(60):
        commands.reopen(f"reopen-{number}", ReopenTask(oid, 2 + number * 2, cid, "Perform again"))
        done = commands.complete(
            f"again-{number}", CompleteTask(oid, 3 + number * 2, (member,), 90)
        )
        cid = done.result.decode()["cycle"]["cycle_id"]
    feed = TaskEventFeed(store, store.installation)
    first = feed.read(limit=100)
    second = feed.read(limit=100, after=first.next_position)
    rows = first.items + second.items
    assert len(first.items) == 100 and len(second.items) == 21 and second.next_position is None
    assert [value.position for value in rows] == sorted({value.position for value in rows})
    assert len({value.event_key for value in rows}) == 121
    assert len({value.cycle_key for value in rows}) == 61


def test_original_schema6_produces_only_live_original_snapshots_after_migration(tmp_path):
    from test_sqlite_task_reviews import frozen

    store = frozen(tmp_path / "old.sqlite3")
    store.initialize(require_existing=True)
    rows = TaskEventFeed(store, store.installation).read().items
    assert len(rows) == 4
    assert rows[-1].event_id == "identity-20" and rows[-1].closes_awards
    assert all(value.cycle.cycle_id != "identity-21" for value in rows)
    assert rows[0].cycle.closed_at is None and not rows[0].points_eligible
    assert rows[1].cycle.closed_at is None and rows[1].points_eligible


def test_actual_restore_does_not_reintroduce_historical_approval_or_reopening(tmp_path):
    from test_activation_compatibility import identity_at
    from test_sqlite_snapshots import Clock

    from domus.application.task_commands import VerifyTask
    from domus.domain.task_values import VerificationState
    from domus.infrastructure.owned_storage import open_storage
    from domus.infrastructure.sqlite_activation import SQLiteActivation
    from domus.infrastructure.sqlite_restoration import SQLiteRestorations
    from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots

    root = tmp_path / "source"
    root.mkdir(mode=0o700)
    commands, store, _, _, oid, done = prepared(root, child=True)
    identity_at(root, store.installation)
    archive, target = tmp_path / "archive", tmp_path / "prepared"
    checkpoint = SQLiteSnapshots(store, archive, store.installation, Clock()).create("pending")
    cid = done.result.decode()["cycle"]["cycle_id"]
    approved = commands.verify("approve", VerifyTask(oid, 2, cid, VerificationState.APPROVED))
    reopened = commands.reopen("reopen", ReopenTask(oid, 3, cid, "Perform again"))
    assert len(TaskEventFeed(store, store.installation).read().items) == 3
    SQLiteRestorations(store, archive, target, store.installation, Clock(), checkpoint).prepare(
        "restore-events"
    )
    assert SQLiteActivation(root, store.installation, Clock(), target).activate().state == "active"
    selected = open_storage(root, "edge")
    try:
        rows = TaskEventFeed(selected.database, store.installation).read().items
        assert len(rows) == 1 and rows[0].event_id == done.operation_id
        assert not rows[0].points_eligible and not rows[0].closes_awards
        assert rows[0].cycle.verification is VerificationState.PENDING
        with selected.database.read() as unit:
            assert not unit.tasks.operation(
                "home", approved.command.actor_id, approved.operation_id
            ).current
            assert not unit.tasks.operation(
                "home", reopened.command.actor_id, reopened.operation_id
            ).current
    finally:
        selected.close()
