"""Use real SQLite transactions for purchase races, recovery and compatibility."""

import sqlite3
from contextlib import closing
from dataclasses import replace
from pathlib import Path

import pytest
from test_activation_compatibility import identity_at
from test_household_commands import Actor, Clock
from test_inventory_catalog_storage import register, setup
from test_pantry_replenishment import report
from test_rewards_storage import race

from domus.application.inventory import CatalogAction, InventoryCommands
from domus.domain.errors import Conflict, NotFound, StorageFailure
from domus.domain.identity import HumanIdentity
from domus.domain.inventory import BaseUnit
from domus.domain.storage import Installation, Receipt
from domus.domain.task_material_values import MaterialQuantity
from domus.infrastructure import sqlite as storage
from domus.infrastructure.application_runtime import SecureIdentifiers
from domus.infrastructure.owned_storage import open_storage
from domus.infrastructure.sqlite import SQLiteDatabase
from domus.infrastructure.sqlite_activation import SQLiteActivation
from domus.infrastructure.sqlite_restoration import SQLiteRestorations
from domus.infrastructure.sqlite_shopping import SQLiteShopping, verify_shopping_records
from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots

M = MaterialQuantity


@pytest.mark.parametrize("duplicate", [True, False])
def test_real_writers_cannot_duplicate_tracked_purchases_arrivals_or_posts(tmp_path, duplicate):
    _, store, first = setup(tmp_path)
    product = register(first)
    second = replace(first, transactions=SQLiteDatabase(store.path, store.installation))
    actor = second.actor.current()

    def accepted(operation, action, conflict):
        keys = ("same", "same" if duplicate else "competing")
        results = race(lambda: operation(first, keys[0]), lambda: operation(second, keys[1]))
        key, saved = next(
            (key, receipt)
            for key, receipt in zip(keys, results, strict=True)
            if isinstance(receipt, Receipt)
        )
        if duplicate:
            assert results == (saved, saved)
        else:
            assert results.count(conflict) == 1
        assert second.original(action, key, actor) == saved
        assert operation(second, key) == saved
        return saved.result.decode()

    purchase = accepted(
        lambda owner, key: owner.purchase(key, product, None, M("6")),
        CatalogAction.PURCHASE,
        "shopping_purchase_open",
    )["purchase_id"]
    receipt = accepted(
        lambda owner, key: owner.receive_purchase(key, purchase, M("4"), 1),
        CatalogAction.RECEIVE_PURCHASE,
        "revision_conflict",
    )["receipt_id"]
    accepted(
        lambda owner, key: owner.post_purchase_receipt(key, purchase, receipt),
        CatalogAction.POST_RECEIPT,
        "shopping_receipt_posted",
    )
    with second.transactions.read() as unit:
        assert unit.shopping.purchase("home", purchase).remaining == 2_000_000
        assert unit.shopping.outstanding("home", product) == 2_000_000
        assert len(unit.shopping.receipts("home", purchase, 100, 10)) == 1
    assert report(second, product).recorded == "4"


def test_capacity_and_interrupted_post_preserve_physical_receipt(tmp_path, monkeypatch):
    _, store, commands = setup(tmp_path)
    product = register(commands)
    max_stock = "999999999999.999999"
    commands.intake("full", product, M(max_stock))
    purchase = commands.purchase("buy", product, None, M("1")).result.decode()["purchase_id"]
    receipt = commands.receive_purchase("arrive", purchase, M("1"), 1).result.decode()["receipt_id"]
    with pytest.raises(Conflict, match="inventory_stock_capacity"):
        commands.post_purchase_receipt("post", purchase, receipt)
    assert report(commands, product).recorded == max_stock
    commands.adjust("space", product, "-1", "Make room")

    def fail(*_):
        raise StorageFailure("interrupted_post")

    with monkeypatch.context() as patch:
        patch.setattr(SQLiteShopping, "link_movement", fail)
        before = report(commands, product)
        with pytest.raises(StorageFailure, match="interrupted_post"):
            commands.post_purchase_receipt("post", purchase, receipt)
        assert report(commands, product) == before
    with store.read() as unit:
        assert unit.shopping.receipt("home", receipt).movement_id is None
        assert unit.shopping.purchase("home", purchase).pending == 1_000_000
    posted = commands.post_purchase_receipt("post", purchase, receipt)
    assert report(commands, product).recorded == max_stock
    assert commands.post_purchase_receipt("post", purchase, receipt) == posted
    next_purchase = commands.purchase("next", product, None, M("1")).result.decode()["purchase_id"]
    with pytest.raises(NotFound, match="shopping_receipt_missing"):
        commands.post_purchase_receipt("mismatch", next_purchase, receipt)


def test_upgrade_v22_preserves_pantry_and_restore_recovers_pending_and_posted(
    tmp_path, monkeypatch
):
    root = tmp_path / "source"
    root.mkdir(mode=0o700)
    path = root / "domus.sqlite3"
    fixture = Path(__file__).parents[1] / "fixtures/sqlite/v22-shopping-source.sql"
    with closing(sqlite3.connect(path, autocommit=True)) as db:
        db.executescript(fixture.read_text())
        assert db.execute("PRAGMA user_version").fetchone() == (22,)
        installation = Installation(
            *db.execute("SELECT instance_id,channel FROM installation").fetchone()
        )
        (product,) = db.execute(
            "SELECT product_id FROM inventory_products WHERE name='Oil'"
        ).fetchone()
        existing = {
            table: db.execute("SELECT * FROM " + table).fetchall()
            for table in (
                "inventory_products",
                "inventory_replenishment",
                "inventory_movements",
                "inventory_effects",
                "task_material_intents",
                "receipts",
            )
        }
    path.chmod(0o600)
    store = SQLiteDatabase(path, installation)
    baseline = path.read_bytes()
    with monkeypatch.context() as patch:
        patch.setattr(storage, "SHOPPING_STATEMENTS", (*storage.SHOPPING_STATEMENTS, "invalid SQL"))
        with pytest.raises(StorageFailure):
            store.initialize(require_existing=True)
    assert path.read_bytes() == baseline
    store.initialize(require_existing=True)
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("PRAGMA user_version").fetchone() == (25,)
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        for table, rows in existing.items():
            assert db.execute("SELECT * FROM " + table).fetchall() == rows
    identity_at(root, installation)
    actor = Actor()
    actor.human = HumanIdentity("ha_admin", True, True, False)
    commands = InventoryCommands(store, actor, Clock(), SecureIdentifiers())
    policy = commands.original(CatalogAction.CONFIGURE_REPLENISHMENT, "policy-v22", actor.human)
    assert policy.result.decode()["target"] == "5"
    before = report(commands, product)
    assert (before.recorded, before.reserved, before.available) == ("3.250001", "0.875", "2.375001")
    assert before.shopping_needed == "2.624999"
    purchase = commands.purchase("buy", product, None, M("2")).result.decode()["purchase_id"]
    bought = report(commands, product)
    assert (bought.recorded, bought.shopping_needed, bought.outstanding_purchase) == (
        "3.250001",
        "0.624999",
        "2",
    )
    first = commands.receive_purchase("first", purchase, M("0.25"), 1)
    second = commands.receive_purchase("second", purchase, M("0.5"), 2)
    first_id, second_id = (item.result.decode()["receipt_id"] for item in (first, second))
    posted = commands.post_purchase_receipt("post-first", purchase, first_id)
    before_restore = report(commands, product)
    assert (before_restore.reserved, before_restore.shopping_needed) == ("0.875", "0.624999")
    archive, target = tmp_path / "archive", tmp_path / "prepared"
    checkpoint = SQLiteSnapshots(store, archive, installation, Clock()).create("shopping")
    later = commands.post_purchase_receipt("post-second", purchase, second_id)
    SQLiteRestorations(store, archive, target, installation, Clock(), checkpoint).prepare("restore")
    assert SQLiteActivation(root, installation, Clock(), target).activate().state == "active"
    restored = open_storage(root, "edge")
    try:
        recovery = replace(commands, transactions=restored.database)
        assert report(recovery, product) == before_restore
        assert recovery.receive_purchase("second", purchase, M("0.5"), 2) == second
        assert recovery.post_purchase_receipt("post-first", purchase, first_id) == posted
        historical = recovery.post_purchase_receipt("post-second", purchase, second_id)
        assert historical.historical and historical.operation_id == later.operation_id
        with restored.database.read() as unit:
            assert unit.shopping.receipt("home", second_id).movement_id is None
            assert (
                unit.shopping.receipt("home", first_id).movement_id
                == posted.result.decode()["movement_id"]
            )
        recovery.post_purchase_receipt("new-post", purchase, second_id)
        assert report(recovery, product).recorded == "4.000001"
    finally:
        restored.close()


@pytest.mark.parametrize(
    "damage",
    [
        "UPDATE shopping_purchases SET base_unit='gram'",
        "UPDATE shopping_purchases SET purchased=2000001",
        "UPDATE shopping_receipts SET quantity=1000001",
        "UPDATE shopping_receipts SET movement_id='missing'",
        "UPDATE shopping_receipts SET movement_id=NULL",
        "UPDATE inventory_movements SET delta=2000000",
        "UPDATE shopping_purchases SET revision=5",
    ],
)
def test_snapshot_checks_shopping_amounts_provenance_and_revisions(tmp_path, damage):
    _, store, commands = setup(tmp_path)
    product = commands.register("boxes", "Boxes", BaseUnit.PIECE).result.decode()["product_id"]
    purchase = commands.purchase("buy", product, None, M("2")).result.decode()["purchase_id"]
    receipt = commands.receive_purchase("arrive", purchase, M("1"), 1).result.decode()["receipt_id"]
    commands.post_purchase_receipt("post", purchase, receipt)
    commands.purchase("free", None, "Apples", M("2"))
    with closing(sqlite3.connect(store.path, autocommit=True)) as db:
        db.row_factory = sqlite3.Row
        verify_shopping_records(db)
        if damage.startswith("UPDATE shopping_purchases"):
            db.execute(damage + " WHERE product_id IS NOT NULL")
        else:
            db.execute(damage)
        with pytest.raises(StorageFailure, match="invalid_shopping_records"):
            verify_shopping_records(db)
