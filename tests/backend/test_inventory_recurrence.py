"""Compound recurrence acceptance with real Points, reservations and physical movements."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, contextmanager
from dataclasses import replace
from datetime import date
from hashlib import sha256
from pathlib import Path
from threading import Event

import pytest
from test_activation_compatibility import identity_at
from test_household_commands import Actor, Clock
from test_points_consumer import adult_id, consumer, cycle_of, running
from test_recurrence_creation import request as fixed_request
from test_recurrence_creation import setup as fixed_setup
from test_recurrence_review import reviewed
from test_relative_recurrence_creation import request as relative_request
from test_relative_recurrence_creation import setup as relative_setup
from test_task_commands import fixture
from test_task_http import PREFIX, create
from test_task_material_http import complete, selection
from test_task_material_settlement import request as settlement_request
from test_task_runtime import api as api

from domus.application.fixed_batch_review import FixedReplacement
from domus.application.fixed_materialization import FixedMaintenance, MaintenanceScope
from domus.application.inventory import InventoryCommands, InventorySettlement
from domus.application.recurrence_review import RecurrenceReview, ReviewAction
from domus.application.recurrence_sources import RecurrenceSourceObservations
from domus.application.relative_lifecycle import RelativeLifecycle
from domus.application.relative_materialization import RelativeMaintenance
from domus.application.relative_recurrence import RelativeRecurrencePlanner
from domus.application.task_material_ports import MaterialPostingRequest
from domus.application.task_requests import (
    AssignTask,
    CompleteTask,
    CreateTask,
    ReopenTask,
    TransitionTask,
)
from domus.domain.errors import Conflict, DatabaseRejected, Forbidden, InvalidInput, StorageFailure
from domus.domain.identity import HumanIdentity
from domus.domain.inventory import EffectKind
from domus.domain.recurrence_rule_text import parse_fixed_pattern
from domus.domain.recurrence_rules import NominalDate
from domus.domain.storage import Installation
from domus.domain.task_material_values import (
    MaterialAction,
    MaterialBinding,
    MaterialQuantity,
    MaterialSelection,
    MaterialUsage,
)
from domus.domain.task_values import MaterialRecording, OccurrenceState, TaskContent, TaskOverrides
from domus.infrastructure import sqlite as storage
from domus.infrastructure.application_runtime import SecureIdentifiers
from domus.infrastructure.owned_storage import open_storage
from domus.infrastructure.sqlite import SQLiteAudit, SQLiteDatabase
from domus.infrastructure.sqlite_activation import SQLiteActivation
from domus.infrastructure.sqlite_inventory import SQLiteInventory
from domus.infrastructure.sqlite_restoration import SQLiteRestorations
from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots
from domus.infrastructure.sqlite_tasks import SQLiteTasks

BINDING = MaterialBinding("home", "binding", "soap", "litre", "utility-room", 1, 6, "Soap")
Q = MaterialQuantity
MATERIALS = (MaterialSelection(BINDING.reference_id, Q("2")),)


def _inventory(service, store):
    return InventoryCommands(store, service.actor, service.clock, service.identifiers)


def _with_stock(service, store):
    return replace(
        service,
        inventory_factory=lambda unit: InventorySettlement(
            unit.inventory, service.clock, service.identifiers
        ),
    )


def _commit(inventory, key, kind, quantity, occurrence=None):
    receipt = inventory.commit_effect(
        key, kind, BINDING.reference_id, Q(quantity), occurrence_id=occurrence
    )
    return receipt.result.decode()["effect_id"]


def _stock(store):
    with store.read() as unit:
        balance = unit.inventory.balance("home", BINDING.reference_id)
        reserved = unit.inventory.reserved("home", BINDING.reference_id)
    with closing(sqlite3.connect(store.path)) as db:
        movements = db.execute(
            "SELECT movement_id,delta,corrects FROM inventory_movements ORDER BY position"
        ).fetchall()
    return balance, reserved, movements


def _effect(store, effect_id):
    with store.read() as unit:
        return unit.inventory.effect("home", effect_id)


@contextmanager
def _restore(store, root, tmp_path, snapshot):
    archive = tmp_path / "archive"
    target = tmp_path / "prepared"
    SQLiteRestorations(store, archive, target, store.installation, Clock(), snapshot).prepare(
        "restore"
    )
    assert SQLiteActivation(root, store.installation, Clock(), target).activate().state == "active"
    restored = open_storage(root, "edge")
    try:
        yield restored
    finally:
        restored.close()


def _fixed(tmp_path, replacement="FREQ=DAILY;COUNT=3;INTERVAL=2"):
    creator, _, store, actor, ids = fixed_setup(tmp_path)
    inventory = _inventory(creator, store)
    inventory.receive("initial-stock", BINDING, Q("10"))
    creator = _with_stock(creator, store)
    start = NominalDate(date(2026, 3, 27))
    choice = fixed_request()
    schedule = creator.create_fixed(
        "fixed",
        replace(
            choice,
            task=replace(choice.task, materials=MATERIALS),
            pattern=parse_fixed_pattern("FREQ=DAILY;COUNT=3", start),
        ),
    ).result.decode()["schedule_id"]
    scope = MaintenanceScope(store.installation, "home")
    planner = RelativeRecurrencePlanner(creator.planner.times)
    maintenance = FixedMaintenance(store, scope, creator.planner, creator.clock, ids)
    old = tuple(
        maintenance.step(schedule, NominalDate(date(2026, 3, 31))).occurrence_id for _ in range(3)
    )
    review = RecurrenceReview(
        store, store.installation, actor, actor.current, creator.clock, ids, planner
    )
    selection = FixedReplacement(
        schedule,
        1,
        parse_fixed_pattern(replacement, NominalDate(date(2026, 3, 28))),
        "Review linked Inventory commitments",
    )
    return store, inventory, review, selection, old


def test_reviewed_batch_recovers_original_stock_reservations_and_demand(tmp_path):
    root = tmp_path / "source"
    root.mkdir(mode=0o700)
    store, inventory, review, selection, (_, first, second) = _fixed(root)
    identity_at(root, store.installation)
    reservation = _commit(inventory, "hold", EffectKind.RESERVATION, "2", first)
    demand = _commit(inventory, "need", EffectKind.DEMAND, "3", second)
    extra = _commit(inventory, "manual", EffectKind.DEMAND, "1")
    original_effects = {key: _effect(store, key) for key in (reservation, demand, extra)}
    original_stock = _stock(store)
    preview, change = reviewed(review, selection)
    assert {
        row["effect_id"] for row in preview.result.decode()["plan"]["source"]["inventory_effects"]
    } == {reservation, demand}
    accepted = review.apply("replace", change)
    # The initial response is unavailable to the restarted reviewer. Recover by the original key.
    restarted = replace(review, transactions=SQLiteDatabase(store.path, store.installation))
    recovered = restarted.original(ReviewAction.APPLY, "replace")
    assert recovered == accepted == restarted.apply("replace", change)
    result = recovered.result.decode()
    assert set(result["replacements"]) == {first, second}
    assert result["inventory_retained"] == []
    links = {item["id"]: (item["from"], item["to"]) for item in result["inventory_transferred"]}
    assert links == {
        reservation: (first, result["replacements"][first]),
        demand: (second, result["replacements"][second]),
    }
    for effect_id, (_, replacement) in links.items():
        assert _effect(store, effect_id) == replace(
            original_effects[effect_id], occurrence_id=replacement, revision=2
        )
    assert _effect(store, extra) == original_effects[extra]
    assert original_stock[0:2] == (10_000_000, 2_000_000)
    assert _stock(store) == original_stock
    snapshot = SQLiteSnapshots(store, tmp_path / "archive", store.installation, Clock()).create(
        "batch"
    )
    with _restore(store, root, tmp_path, snapshot) as restored:
        restored_review = replace(review, transactions=restored.database)
        assert restored_review.apply("replace", change) == accepted
        assert _effect(restored.database, reservation) == _effect(store, reservation)
        assert _effect(restored.database, demand) == _effect(store, demand)
        assert _effect(restored.database, extra) == original_effects[extra]
        assert _stock(restored.database) == original_stock


def test_reviewed_batch_inventory_change_and_rollback_are_atomic(tmp_path, monkeypatch):
    store, inventory, review, selection, (_, first, second) = _fixed(
        tmp_path, replacement="FREQ=DAILY;COUNT=1"
    )
    _, stale = reviewed(review, selection)
    kept = _commit(inventory, "unpaired", EffectKind.DEMAND, "2", second)
    moved = _commit(inventory, "paired", EffectKind.RESERVATION, "2", first)
    before = [_effect(store, key) for key in (kept, moved)]
    with pytest.raises(Conflict, match="recurrence_review_stale"):
        review.apply("stale", stale)
    _, current = reviewed(review, selection, "current-preview")
    append = SQLiteAudit.append

    def fail(unit, entry):
        append(unit, entry)
        if entry.command.action == "recurrence.review.apply":
            raise StorageFailure("after_inventory_transfer")

    with monkeypatch.context() as patch:
        patch.setattr(SQLiteAudit, "append", fail)
        with pytest.raises(StorageFailure, match="after_inventory_transfer"):
            review.apply("replacement", current)
    assert [_effect(store, key) for key in (kept, moved)] == before
    with store.read() as unit:
        assert unit.recurrence.schedule("home", selection.schedule_id).revision == 1
        assert unit.tasks.occurrence("home", first).state is OccurrenceState.AVAILABLE
    result = review.apply("replacement", current).result.decode()
    assert result["inventory_retained"] == [kept]
    assert result["inventory_transferred"] == [
        {"id": moved, "from": first, "to": result["replacements"][first]}
    ]
    assert _effect(store, kept) == before[0]


def _relative(root):
    creator, tasks, store, actor, ids = relative_setup(root)
    inventory = _inventory(creator, store)
    inventory.receive("initial-stock", BINDING, Q("10"))
    tasks = _with_stock(tasks, store)
    creator = _with_stock(creator, store)
    selection = relative_request()
    schedule = creator.create(
        "relative",
        replace(
            selection,
            task=replace(
                selection.task, overrides=TaskOverrides(point_value_minor=125), materials=MATERIALS
            ),
        ),
    ).result.decode()["schedule_id"]
    scope = MaintenanceScope(store.installation, "home")
    source = RecurrenceSourceObservations(store, scope)
    lifecycle = RelativeLifecycle(
        store, scope, RelativeRecurrencePlanner(creator.times), Clock(), ids
    )
    parent = (
        RelativeMaintenance(store, scope, creator.times, Clock(), ids)
        .initial(schedule)
        .occurrence_id
    )
    member = adult_id(store, tasks)
    first = _perform(store, tasks, parent, member, "source", "0.25", 90)
    (completed,) = source.ingest().items
    successor = lifecycle.consume(schedule, completed.event.event_key).occurrence_id
    return store, inventory, tasks, source, lifecycle, schedule, parent, first, successor, member


def _perform(store, tasks, occurrence, member, key, amount, at):
    with store.read() as unit:
        work = unit.tasks.occurrence("home", occurrence)
    line = work.definition_snapshot.materials[0]
    return tasks.complete(
        key,
        CompleteTask(
            occurrence, work.revision, (member,), at, (MaterialUsage(line.line_id, Q(amount)),)
        ),
    )


def test_source_reopening_keeps_completed_successor_and_real_stock_after_restore(tmp_path):
    root = tmp_path / "source"
    root.mkdir(mode=0o700)
    store, inventory, tasks, source, lifecycle, rule, parent, first, successor, member = _relative(
        root
    )
    identity_at(root, store.installation)
    reserved = _commit(inventory, "hold", EffectKind.RESERVATION, "2", successor)
    downstream = _perform(store, tasks, successor, member, "successor", "1.125", 95)
    points = consumer(store)
    assert points.tick(running) == 2
    original_cycle, downstream_cycle = cycle_of(first), cycle_of(downstream)
    (award,) = points.ledger("home", original_cycle)
    (downstream_award,) = points.ledger("home", downstream_cycle)
    assert award.shares == downstream_award.shares == ((member, 125),)
    stock = _stock(store)
    assert stock[:2] == (8_625_000, 875_000)
    assert len(stock[2]) == 3 and stock[2][-1][1:] == (-1_125_000, None)
    with store.read() as unit:
        recorded = unit.task_materials.list("home", downstream_cycle)[0]
        movement = unit.inventory.movement_by_id("home", recorded.posting.movement_id)
        assert movement.posting == recorded.posting
        assert stock[2][-1][0] == movement.movement_id
    reopened = tasks.reopen("reopen", ReopenTask(parent, 2, original_cycle, "Review original work"))
    close = next(
        item.event for item in source.ingest().items if item.event.event_id == reopened.operation_id
    )
    result = lifecycle.consume(rule, close.event_key)
    assert result.status == "review" and lifecycle.consume(rule, close.event_key) == result
    assert points.tick(running) == 1 and points.tick(running) == 0
    assert points.ledger("home", original_cycle) == (
        award,
        award.reverse(reopened.operation_id, 100),
    )
    assert points.ledger("home", downstream_cycle) == (downstream_award,)
    assert _stock(store) == stock
    with store.read() as unit:
        assert unit.tasks.occurrence("home", successor).state is OccurrenceState.COMPLETED
    snapshot = SQLiteSnapshots(store, tmp_path / "archive", store.installation, Clock()).create(
        "downstream"
    )
    with _restore(store, root, tmp_path, snapshot) as restored:
        assert _stock(restored.database) == stock
        assert _effect(restored.database, reserved).remaining == 875_000
        ledger = consumer(restored.database)
        assert ledger.ledger("home", downstream_cycle) == (downstream_award,)
        assert ledger.ledger("home", original_cycle) == points.ledger("home", original_cycle)
        assert ledger.tick(running) == 0
        resumed = replace(lifecycle, transactions=restored.database)
        assert resumed.consume(rule, close.event_key) == result
        with restored.database.read() as unit:
            assert unit.tasks.occurrence("home", successor).state is OccurrenceState.COMPLETED


def test_started_work_wins_independent_invalidation_and_preserves_inventory(tmp_path, monkeypatch):
    store, inventory, tasks, source, lifecycle, rule, parent, first, successor, member = _relative(
        tmp_path
    )
    reserved = _commit(inventory, "hold", EffectKind.RESERVATION, "2", successor)
    demand = _commit(inventory, "demand", EffectKind.DEMAND, "3", successor)
    expected = [_effect(store, key) for key in (reserved, demand)]
    stock = _stock(store)
    assert stock[:2] == (9_750_000, 2_000_000)
    tasks.assign("assign", AssignTask(successor, 1, (member,)))
    tasks.reopen("reopen", ReopenTask(parent, 2, cycle_of(first), "Review original work"))
    (reopening,) = source.ingest().items
    started, racing = Event(), Event()
    save = SQLiteTasks.save_occurrence

    def hold(self, work, revision):
        save(self, work, revision)
        if work.occurrence_id == successor and work.state is OccurrenceState.IN_PROGRESS:
            started.set()
            assert racing.wait(3)

    class Independent(SQLiteDatabase):
        @contextmanager
        def write(self):
            racing.set()
            with super().write() as unit:
                yield unit

    monkeypatch.setattr(SQLiteTasks, "save_occurrence", hold)
    invalidator = replace(
        lifecycle, transactions=Independent(store.path, store.installation, busy_timeout=5)
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        start = pool.submit(
            tasks.transition, "start", TransitionTask(successor, 2, OccurrenceState.IN_PROGRESS)
        )
        assert started.wait(3)
        close = pool.submit(invalidator.consume, rule, reopening.event.event_key)
        start.result()
        result = close.result()
    assert (
        result.status == "review" and invalidator.consume(rule, reopening.event.event_key) == result
    )
    with store.read() as unit:
        assert unit.tasks.occurrence("home", successor).state is OccurrenceState.IN_PROGRESS
        assert (
            sum(item.event_id == result.receipt.operation_id for item in unit.outbox.pending()) == 1
        )
    assert [_effect(store, key) for key in (reserved, demand)] == expected
    assert _stock(store) == stock


def test_genuine_schema_16_inventory_migration_preserves_points_and_is_atomic(
    tmp_path, monkeypatch
):
    source = Path(__file__).parents[1] / "fixtures/sqlite/v16-inventory-source.sql"
    assert (
        sha256(source.read_bytes()).hexdigest()
        == "032954fc9be4ca2f96359c34df1e6e2a23e5562a481ddbc8fbcb9dcbbeebeb8b"
    )
    database = tmp_path / "prior.sqlite3"
    with closing(sqlite3.connect(database, autocommit=True)) as connection:
        connection.executescript(source.read_text())
        assert connection.execute("PRAGMA user_version").fetchone() == (16,)
        installation = Installation(
            *connection.execute("SELECT instance_id,channel FROM installation").fetchone()
        )
        before = connection.execute(
            "SELECT * FROM points_task_receipts ORDER BY position"
        ).fetchall()
    saved = database.read_bytes()
    store = SQLiteDatabase(database, installation)
    with monkeypatch.context() as patch:
        patch.setattr(
            storage, "INVENTORY_STATEMENTS", (*storage.INVENTORY_STATEMENTS, "invalid SQL")
        )
        with pytest.raises(StorageFailure):
            store.initialize(require_existing=True)
    assert database.read_bytes() == saved
    store.initialize(require_existing=True)
    with store.read() as unit:
        eligible, pending = sorted(unit.tasks.cycles("home"), key=lambda cycle: cycle.verification)
        assert unit.points.ledger("home", eligible.cycle_id)[0].shares[0][1] == 300
        assert unit.points.ledger("home", pending.cycle_id) == ()
        assert unit.inventory.material("home", BINDING.reference_id) is None
    with closing(sqlite3.connect(database)) as connection:
        assert (
            connection.execute("SELECT * FROM points_task_receipts ORDER BY position").fetchall()
            == before
        )
        assert connection.execute("PRAGMA user_version").fetchone() == (17,)


def test_real_task_material_posts_in_both_compositions_and_keeps_shortage_pending(api):
    with api.store.read() as unit:
        (admin,) = unit.members.list("home")
    actor = Actor()
    actor.human = HumanIdentity(admin.ha_user_id, True, True, False)
    inventory = InventoryCommands(api.store, actor, Clock(), SecureIdentifiers())
    stock = inventory.receive("receive", BINDING, Q("1.125"))
    assert inventory.receive("receive", BINDING, Q("1.125")) == stock
    created = create(api, materials=[selection("0.25")])
    occurrence = created["result"]["occurrence_id"]
    line = api.client.get(PREFIX + "/occurrences/" + occurrence).json()["work"][
        "definition_snapshot"
    ]["materials"][0]
    actual = {"material_usages": [{"line_id": line["line_id"], "quantity": "0.125001"}]}
    response = complete(api, created, actual)
    assert response.status_code == 200, response.text
    outcome = response.json()["result"]["materials"][0]
    assert outcome["state"] == "posted"
    assert complete(api, created, actual).json() == response.json()
    assert _stock(api.store) == (
        999_999,
        0,
        [
            (stock.result.decode()["movement_id"], 1_125_000, None),
            (outcome["movement_id"], -125_001, None),
        ],
    )
    other = create(api, materials=[selection("1")], key="next-work")
    other_id = other["result"]["occurrence_id"]
    line = api.client.get(PREFIX + "/occurrences/" + other_id).json()["work"][
        "definition_snapshot"
    ]["materials"][0]
    result = complete(
        api, other, {"material_usages": [{"line_id": line["line_id"], "quantity": "1"}]}, "shortage"
    )
    assert result.status_code == 200, result.text
    assert result.json()["result"]["materials"][0]["state"] == "pending_regularization"
    assert len(_stock(api.store)[2]) == 2
    with pytest.raises(Forbidden, match="permission_denied"):
        replace(inventory, household_id="another").receive(
            "foreign", replace(BINDING, household_id="another"), Q("1")
        )
    assert len(_stock(api.store)[2]) == 2


def test_manager_commands_cannot_overbook_or_create_unbound_effects(tmp_path):
    tasks, store, actor, _ = fixture(tmp_path)
    inventory = _inventory(tasks, store)
    with pytest.raises(InvalidInput, match="invalid_inventory_receipt"):
        inventory.receive("zero", BINDING, Q("0"))
    with pytest.raises(InvalidInput, match="invalid_material_reference"):
        _commit(inventory, "unknown", EffectKind.DEMAND, "1")
    inventory.receive("receive", BINDING, Q("999999999999.999999"))
    with pytest.raises(Conflict, match="inventory_binding_changed"):
        inventory.receive("different-unit", replace(BINDING, unit_id="piece"), Q("1"))
    with pytest.raises(Conflict, match="inventory_stock_capacity"):
        inventory.receive("over-capacity", BINDING, Q("0.000001"))
    with pytest.raises(InvalidInput, match="invalid_inventory_effect"):
        _commit(inventory, "no-occurrence", EffectKind.RESERVATION, "1")
    with pytest.raises(InvalidInput, match="invalid_material_reference"):
        _commit(inventory, "unknown-work", EffectKind.DEMAND, "1", "missing")
    plain = tasks.create("plain", CreateTask(TaskContent("No materials"))).result.decode()
    with pytest.raises(InvalidInput, match="invalid_material_reference"):
        _commit(inventory, "unlinked-line", EffectKind.DEMAND, "1", plain["occurrence_id"])
    tasks = _with_stock(tasks, store)
    linked = tasks.create(
        "with-materials", CreateTask(TaskContent("Wash"), materials=MATERIALS)
    ).result.decode()["occurrence_id"]
    _commit(inventory, "hold", EffectKind.RESERVATION, "1", linked)
    with pytest.raises(Conflict, match="inventory_insufficient_stock"):
        _commit(inventory, "too-much", EffectKind.RESERVATION, "999999999999.999999", linked)
    actor.human = HumanIdentity("ha_child", False, True, False)
    with pytest.raises(Forbidden, match="permission_denied"):
        _commit(inventory, "restricted", EffectKind.DEMAND, "1")
    with store.read() as unit:
        assert unit.inventory.effects("home", ()) == ()
        assert unit.inventory.effect("foreign", "missing") is None


def _separate_material(tmp_path):
    tasks, store, _, _ = fixture(tmp_path)
    inventory = _inventory(tasks, store)
    received = inventory.receive("receive", BINDING, Q("2"))
    tasks = _with_stock(tasks, store)
    receipt = tasks.create(
        "task",
        CreateTask(
            TaskContent("Wash"),
            overrides=TaskOverrides(material_recording=MaterialRecording.SEPARATE),
            materials=MATERIALS,
        ),
    )
    oid = receipt.result.decode()["occurrence_id"]
    hold = _commit(inventory, "hold", EffectKind.RESERVATION, "2", oid)
    result = _perform(store, tasks, oid, adult_id(store, tasks), "perform", "1.125", 90)
    cid = cycle_of(result)
    with store.read() as unit:
        pending = unit.task_materials.list("home", cid)[0]
    return tasks, inventory, store, hold, pending, received.result.decode()["movement_id"]


def test_inventory_posts_and_corrects_one_exact_source_with_rollback_and_retry(
    tmp_path, monkeypatch
):
    tasks, inventory, store, hold, pending, _ = _separate_material(tmp_path)
    before = _stock(store)
    append = SQLiteInventory.append

    def fail(records, movement, balance):
        append(records, movement, balance)
        raise StorageFailure("after_stock")

    with monkeypatch.context() as patch:
        patch.setattr(SQLiteInventory, "append", fail)
        with pytest.raises(StorageFailure, match="after_stock"):
            tasks.settle_material("post", settlement_request(pending))
    assert _stock(store) == before
    assert _effect(store, hold).remaining == 2_000_000
    first = tasks.settle_material("post", settlement_request(pending))
    assert tasks.settle_material("post", settlement_request(pending)) == first
    with store.write() as unit:
        confirmed = unit.task_materials.get("home", pending.intent_id)
        settlement = InventorySettlement(unit.inventory, tasks.clock, tasks.identifiers)
        source = MaterialPostingRequest(pending, pending.recorded_by)
        assert settlement.settle(source).posting == confirmed.posting
        with pytest.raises(Conflict, match="inventory_effect_stale"):
            unit.inventory.update_effect(unit.inventory.effect("home", hold), 1)
    assert _stock(store)[:2] == (875_000, 875_000)
    assert _effect(store, hold).revision == 2
    inventory.receive("restock", BINDING, Q("1"))
    revised = tasks.settle_material(
        "correct",
        settlement_request(confirmed, MaterialAction.CORRECT, quantity="1", reason="Actual use"),
    )
    assert revised.result.decode()["material"]["state"] == "corrected"
    with store.read() as unit:
        posted = unit.task_materials.get("home", pending.intent_id).posting
        movement = unit.inventory.movement_by_id("home", posted.movement_id)
        assert movement.corrects == confirmed.posting.movement_id
        assert movement.reason == "Actual use" and movement.delta == 125_000
    assert _stock(store)[:2] == (2_000_000, 875_000)
    SQLiteSnapshots(store, tmp_path / "verified", store.installation, Clock()).create("corrected")
    with store.write() as unit:
        missing = replace(confirmed.posting, movement_id="missing")
        damaged = replace(confirmed.correct(Q("0.5"), "Check", 100), posting=missing)
        settlement = InventorySettlement(unit.inventory, tasks.clock, tasks.identifiers)
        with pytest.raises(StorageFailure, match="invalid_inventory_posting_source"):
            settlement.settle(MaterialPostingRequest(damaged, pending.recorded_by))


def test_bound_stock_cannot_be_spent_by_other_work_or_after_binding_changes(tmp_path):
    tasks, _, store, hold, pending, _ = _separate_material(tmp_path)
    other = tasks.create(
        "other",
        CreateTask(
            TaskContent("Another wash"),
            overrides=TaskOverrides(material_recording=MaterialRecording.REVIEW_ON_COMPLETION),
            materials=MATERIALS,
        ),
    )
    result = _perform(
        store,
        tasks,
        other.result.decode()["occurrence_id"],
        adult_id(store, tasks),
        "blocked",
        "1",
        90,
    )
    assert result.result.decode()["materials"][0]["pending_reason"] == "insufficient_stock"
    assert _stock(store)[:2] == (2_000_000, 2_000_000)
    assert _effect(store, hold).remaining == 2_000_000
    with closing(sqlite3.connect(store.path, autocommit=True)) as db:
        db.execute("UPDATE inventory_materials SET unit_id='piece'")
    result = tasks.settle_material("post", settlement_request(pending))
    assert result.result.decode()["material"]["pending_reason"] == "inventory_binding_changed"
    assert len(_stock(store)[2]) == 1


@pytest.mark.parametrize(
    "damage",
    [
        "posting-time",
        "posting-delta",
        "wrong-correction-source",
        "physical-balance",
        "reserve-overdrawn",
        "negative-ledger",
    ],
)
def test_snapshot_rejects_inconsistent_inventory_records(tmp_path, damage):
    tasks, _, store, _, pending, receipt_id = _separate_material(tmp_path)
    tasks.settle_material("post", settlement_request(pending))
    with store.read() as unit:
        initial = unit.task_materials.get("home", pending.intent_id)
    tasks.settle_material(
        "correct",
        settlement_request(initial, MaterialAction.CORRECT, quantity="1", reason="Adjusted"),
    )
    with closing(sqlite3.connect(store.path, autocommit=True)) as db:
        statements = {
            "posting-time": ("UPDATE inventory_movements SET created_at=99 WHERE position=2", ()),
            "posting-delta": ("UPDATE inventory_movements SET delta=-1 WHERE position=2", ()),
            "wrong-correction-source": (
                "UPDATE inventory_movements SET corrects=? WHERE position=3",
                (receipt_id,),
            ),
            "physical-balance": ("UPDATE inventory_materials SET balance=1", ()),
            "reserve-overdrawn": ("UPDATE inventory_effects SET remaining=3000000", ()),
            "negative-ledger": ("UPDATE inventory_movements SET delta=1 WHERE position=1", ()),
        }
        statement, arguments = statements[damage]
        db.execute(statement, arguments)
    with pytest.raises(DatabaseRejected, match="invalid_snapshot_records"):
        SQLiteSnapshots(store, tmp_path / "corrupt", store.installation, Clock()).create("damaged")
