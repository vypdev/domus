"""The barcode companion uses real protected commands, SQLite writers and activation."""

import sqlite3
from contextlib import closing
from dataclasses import replace
from pathlib import Path

import pytest
from test_activation_compatibility import identity_at
from test_household_commands import Actor, Clock, Identifiers
from test_inventory_catalog_storage import register, setup
from test_rewards_storage import race

from domus.application.fixed_materialization import MaintenanceScope
from domus.application.inventory import CatalogAction, InventoryCommands
from domus.application.inventory_queries import InventoryQueries
from domus.domain.errors import Conflict, DatabaseRejected, InvalidInput, StorageFailure
from domus.domain.inventory import BarcodeAssociation, BaseUnit, canonical_gtin
from domus.domain.storage import Installation
from domus.infrastructure import sqlite as storage
from domus.infrastructure.owned_storage import open_storage
from domus.infrastructure.sqlite import SQLiteDatabase
from domus.infrastructure.sqlite_activation import SQLiteActivation
from domus.infrastructure.sqlite_receipts import SQLiteReceipts
from domus.infrastructure.sqlite_restoration import SQLiteRestorations
from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots
from domus.infrastructure.task_cursor import TaskCursor


def queries(store, commands):
    return InventoryQueries(
        store,
        MaintenanceScope(store.installation, "home"),
        commands.actor.current(),
        TaskCursor(Clock(), b"b" * 32),
    )


@pytest.mark.parametrize("barcode", ["96385074", "036000291452", "0036000291452", "00036000291452"])
def test_each_supported_printed_length_keeps_zeroes_and_validates_its_digit(barcode):
    canonical = canonical_gtin(barcode)
    assert canonical == barcode.zfill(14)
    assert canonical_gtin(canonical) == canonical
    invalid = barcode[:-1] + str((int(barcode[-1]) + 1) % 10)
    with pytest.raises(InvalidInput, match="invalid_inventory_barcode"):
        canonical_gtin(invalid)


@pytest.mark.parametrize(
    "barcode",
    [
        None,
        36000291452,
        "",
        "1234567",
        "123456789",
        "1234567890",
        "12345678901",
        "0" * 15,
        " 96385074",
        "96385074 ",
        "９６３８５０７４",
        "9638507x",
        "9638507\n",
    ],
)
def test_reject_original_shape_before_any_canonical_padding(barcode):
    with pytest.raises(InvalidInput, match="invalid_inventory_barcode"):
        canonical_gtin(barcode)


def test_association_requires_the_canonical_key_and_valid_stable_identifiers():
    with pytest.raises(InvalidInput, match="invalid_inventory_barcode"):
        BarcodeAssociation("036000291452", "link", "product")
    for association, product in (("", "product"), ("link", "")):
        with pytest.raises(InvalidInput):
            BarcodeAssociation("00036000291452", association, product)


def test_equivalent_lookup_and_original_replay_preserve_product_and_stock(tmp_path):
    _, store, commands = setup(tmp_path)
    product = register(commands)
    service = queries(store, commands)
    assert service.barcode("036000291452").product is None
    first = commands.link_barcode("link", "036000291452", product)
    assert commands.link_barcode("link", "00036000291452", product) == first
    assert commands.original(CatalogAction.LINK_BARCODE, "link", commands.actor.current()) == first
    result = service.barcode("0036000291452")
    assert result.barcode == "00036000291452" and result.may_manage
    assert result.product.product_id == product and result.product.name == "Oil"
    assert result.association.association_id == first.result.decode()["association_id"]
    assert (
        replace(commands, transactions=SQLiteDatabase(store.path, store.installation)).original(
            CatalogAction.LINK_BARCODE, "link", commands.actor.current()
        )
        == first
    )
    with store.read() as unit:
        assert unit.inventory.barcode("other", result.barcode) is None
        assert unit.inventory.balance("home", result.product.reference_id) == 0
    other = commands.register("other", "Other product", BaseUnit.PIECE).result.decode()[
        "product_id"
    ]
    with pytest.raises(Conflict, match="idempotency_conflict"):
        commands.link_barcode("link", result.barcode, other)


def test_two_equivalent_writers_have_one_winner_and_stale_removal_preserves_relink(tmp_path):
    _, store, commands = setup(tmp_path)
    products = [
        register(commands),
        commands.register("second", "Tea", BaseUnit.GRAM).result.decode()["product_id"],
    ]
    other = replace(commands, transactions=SQLiteDatabase(store.path, store.installation))

    def attempt(service, key, code, product):
        try:
            return service.link_barcode(key, code, product)
        except Conflict as error:
            return error.code

    results = race(
        lambda: attempt(commands, "one", "036000291452", products[0]),
        lambda: attempt(other, "two", "00036000291452", products[1]),
    )
    assert sum(result == "inventory_barcode_linked" for result in results) == 1
    winner = next(result for result in results if result != "inventory_barcode_linked")
    association = winner.result.decode()
    removed = commands.remove_barcode("remove", **association)
    assert commands.remove_barcode("remove", **association) == removed
    replacement = commands.link_barcode(
        "replacement", association["barcode"], association["product_id"]
    )
    assert replacement.result.decode()["association_id"] != association["association_id"]
    with pytest.raises(Conflict, match="inventory_barcode_changed"):
        commands.remove_barcode("stale", **association)
    assert (
        queries(store, commands).barcode(association["barcode"]).association.association_id
        == replacement.result.decode()["association_id"]
    )
    with pytest.raises(Conflict, match="inventory_barcode_changed"):
        commands.remove_barcode(
            "wrong-product",
            association["barcode"],
            "missing",
            replacement.result.decode()["association_id"],
        )


def test_late_receipt_failure_rolls_back_the_link_and_removal(tmp_path, monkeypatch):
    _, store, commands = setup(tmp_path)
    product = register(commands)

    def fail(*_):
        raise StorageFailure("synthetic_receipt_failure")

    with monkeypatch.context() as patch:
        patch.setattr(SQLiteReceipts, "add", fail)
        with pytest.raises(StorageFailure, match="synthetic_receipt_failure"):
            commands.link_barcode("link", "036000291452", product)
    assert queries(store, commands).barcode("036000291452").association is None
    receipt = commands.link_barcode("link", "036000291452", product)
    with monkeypatch.context() as patch:
        patch.setattr(SQLiteReceipts, "add", fail)
        with pytest.raises(StorageFailure, match="synthetic_receipt_failure"):
            commands.remove_barcode("remove", **receipt.result.decode())
    assert queries(store, commands).barcode("036000291452").association is not None
    assert commands.remove_barcode("remove", **receipt.result.decode()).result == receipt.result


@pytest.mark.parametrize("version", [20, 30, 34])
def test_upgrade_atomicity_and_compatible_activation_keep_links_and_originals(
    tmp_path, monkeypatch, version
):
    root = tmp_path / "source"
    root.mkdir(mode=0o700)
    source = {
        20: "v20-inventory-history-source.sql",
        30: "v30-purchase-store-source.sql",
        34: "v34-barcode-upgrade-source.sql",
    }[version]
    path = root / "domus.sqlite3"
    with closing(sqlite3.connect(path, autocommit=True)) as db:
        db.executescript((Path(__file__).parents[1] / "fixtures/sqlite" / source).read_text())
        installation = Installation(
            *db.execute("SELECT instance_id,channel FROM installation").fetchone()
        )
    path.chmod(0o600)
    store = SQLiteDatabase(path, installation)
    identity_at(root, store.installation)
    with closing(sqlite3.connect(store.path)) as db:
        before = {
            table: db.execute("SELECT * FROM " + table).fetchall()
            for table in (
                "inventory_products",
                "inventory_materials",
                "inventory_movements",
                "receipts",
            )
        }
    original = store.path.read_bytes()
    with monkeypatch.context() as patch:
        patch.setattr(storage, "BARCODE_STATEMENT", "invalid SQL")
        with pytest.raises(StorageFailure):
            store.initialize(require_existing=True)
    assert store.path.read_bytes() == original
    store.initialize(require_existing=True)
    with closing(sqlite3.connect(store.path)) as db:
        assert db.execute("PRAGMA user_version").fetchone() == (38,)
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        for table, rows in before.items():
            current = db.execute("SELECT * FROM " + table).fetchall()
            if rows:
                assert [row[: len(rows[0])] for row in current] == rows
            else:
                assert current == []
    if version != 34:
        return
    identifiers = Identifiers()
    identifiers.count = 1_000_000
    commands = InventoryCommands(store, Actor(), Clock(), identifiers)
    product = before["inventory_products"][0][1]
    receipt = commands.link_barcode("link", "036000291452", product)
    archive, target = tmp_path / "archive", tmp_path / "prepared"
    snapshotter = SQLiteSnapshots(store, archive, store.installation, Clock())
    checkpoint = snapshotter.create("barcode")
    commands.remove_barcode("remove", **receipt.result.decode())
    SQLiteRestorations(store, archive, target, store.installation, Clock(), checkpoint).prepare(
        "restore"
    )
    assert SQLiteActivation(root, store.installation, Clock(), target).activate().state == "active"
    restored = open_storage(root, "edge")
    try:
        recovered = replace(commands, transactions=restored.database)
        assert (
            recovered.original(
                CatalogAction.LINK_BARCODE, "link", recovered.actor.current()
            ).operation_id
            == receipt.operation_id
        )
        assert (
            queries(restored.database, recovered).barcode("036000291452").product.product_id
            == product
        )
    finally:
        restored.close()


@pytest.mark.parametrize(
    "column,value", [("barcode", "00036000291453"), ("association_id", "invalid id")]
)
def test_snapshot_rejects_malformed_association_records(tmp_path, column, value):
    _, store, commands = setup(tmp_path)
    product = register(commands)
    commands.link_barcode("link", "036000291452", product)
    with closing(sqlite3.connect(store.path, autocommit=True)) as db:
        db.execute("UPDATE inventory_barcodes SET " + column + "=?", (value,))
    with pytest.raises(DatabaseRejected, match="invalid_snapshot_records"):
        SQLiteSnapshots(store, tmp_path / "archive", store.installation, Clock()).create("corrupt")
