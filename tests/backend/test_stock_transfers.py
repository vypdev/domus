"""Qualify storage locations and exact transfers through the real household ledger."""

import sqlite3
from contextlib import closing
from dataclasses import replace
from pathlib import Path

import pytest
from test_activation_compatibility import identity_at
from test_household_commands import Actor, Clock
from test_inventory_catalog_http import INVENTORY, VIEWER, get, post, register
from test_inventory_catalog_storage import register as register_stock
from test_inventory_catalog_storage import setup
from test_recurrence_http import USER
from test_rewards_http import member_context
from test_rewards_storage import race
from test_shared_shopping import queries
from test_task_runtime import api as api

from domus.application.inventory import CatalogAction, InventoryCommands
from domus.domain.errors import Conflict, InvalidInput, NotFound, StorageFailure
from domus.domain.identity import HumanIdentity, Member, MemberStatus, Role
from domus.domain.inventory import (
    MAX_NAMED_LOCATIONS,
    PANTRY,
    BaseUnit,
    MovementKind,
    StorageLocation,
)
from domus.domain.storage import Installation, Receipt
from domus.domain.task_material_values import MaterialQuantity
from domus.infrastructure import sqlite as storage
from domus.infrastructure.application_runtime import SecureIdentifiers
from domus.infrastructure.owned_storage import open_storage
from domus.infrastructure.sqlite import SCHEMA_VERSION, SQLiteDatabase
from domus.infrastructure.sqlite_activation import SQLiteActivation
from domus.infrastructure.sqlite_inventory import SQLiteInventory, verify_inventory_locations
from domus.infrastructure.sqlite_restoration import SQLiteRestorations
from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots

M = MaterialQuantity


def location(commands, key="add", name="Cupboard"):
    return commands.add_location(key, name).result.decode()["location_id"]


def test_locations_transfer_and_current_grants_in_both_modes(api):
    with api.store.write() as unit:
        unit.members.save(Member("viewer", "home", VIEWER, Role.VIEWER, MemberStatus.ACTIVE, 1), 0)
    api.user(USER, True)
    product = register(api, "flour", "Flour", "gram")
    assert post(api, "intake", "intake", product_id=product, quantity="251").status_code == 200
    assert (
        post(
            api,
            "policy",
            "configure-replenishment",
            product_id=product,
            minimum="2",
            target="10",
            expected_revision="0",
        ).status_code
        == 200
    )
    added = post(api, "add", "add-location", name="Cupboard")
    assert added.status_code == 200, added.text
    cupboard = added.json()["result"]["location_id"]
    assert post(api, "add", "add-location", name="Cupboard").json() == added.json()
    assert post(api, "add", "add-location", name="Drawer").json()["code"] == "idempotency_conflict"
    assert (
        post(api, "duplicate", "add-location", name="CUPBOARD").json()["code"]
        == "inventory_location_exists"
    )
    assert (
        post(api, "bad", "add-location", name="Pantry").json()["code"]
        == "invalid_inventory_location_name"
    )

    args = dict(
        product_id=product, source_location=PANTRY, destination_location=cupboard, quantity="250.5"
    )
    url = f"{INVENTORY}/products/{product}/movements"
    original = f"{INVENTORY}/requests/inventory.transfer/move"
    missing = post(api, "bad", "transfer", **(args | {"destination_location": "foreign"}))
    assert missing.status_code == 404 and missing.json()["code"] == "inventory_location_missing"
    assert (
        post(api, "bad", "transfer", **(args | {"source_location": cupboard})).json()["code"]
        == "inventory_same_location"
    )
    assert (
        api.client.post(
            INVENTORY + "/commands",
            json={"action": "inventory.transfer", **args},
            headers={"Idempotency-Key": "no-csrf"} | member_context(USER),
        ).status_code
        == 403
    )
    saved = post(api, "move", "transfer", **args)
    assert saved.status_code == 200, saved.text
    result = saved.json()["result"]
    assert result["quantity"] == "250.5" and result["source_location"] == PANTRY
    assert result["destination_location"] == cupboard
    assert post(api, "move", "transfer", **args).json() == saved.json()
    assert api.client.get(original, headers=member_context(USER)).json() == saved.json()
    assert get(api).json()["products"][0]["shopping_needed"] == "9.5"

    api.user(VIEWER)
    assert get(api, VIEWER).json()["locations"] == [{"location_id": cupboard, "name": "Cupboard"}]
    report = api.client.get(url, headers=member_context(VIEWER)).json()
    assert report["total"] == {"recorded": "251", "reserved": "0", "available": "251"}
    assert [item["stock"]["recorded"] for item in report["locations"]] == ["0.5", "250.5"]
    deposit, withdrawal, intake = report["movements"]
    assert (deposit["kind"], withdrawal["kind"], intake["kind"]) == (
        "transfer",
        "transfer",
        "intake",
    )
    assert (deposit["quantity"], withdrawal["quantity"]) == ("250.5", "-250.5")
    assert (deposit["movement_id"], withdrawal["movement_id"]) == (
        result["deposit_id"],
        result["withdrawal_id"],
    )
    assert deposit["transfer"] == withdrawal["transfer"]
    assert (
        deposit["member_id"] == withdrawal["member_id"]
        and deposit["created_at"] == withdrawal["created_at"]
    )
    assert post(api, "move", "transfer", user=VIEWER, **args).status_code == 403
    assert post(api, "add", "add-location", user=VIEWER, name="Other").status_code == 403
    assert api.client.get(original, headers=member_context(VIEWER)).status_code == 403

    api.user(USER, True)
    reversed_args = args | {"source_location": cupboard, "destination_location": PANTRY}
    assert post(api, "back", "transfer", **reversed_args).status_code == 200
    assert get(api).json()["products"][0]["shopping_needed"] == "0"
    with api.store.write() as unit:
        member = unit.members.by_user("home", USER)
        unit.members.save(
            replace(member, status=MemberStatus.SUSPENDED, revision=member.revision + 1),
            member.revision,
        )
    assert api.client.get(original, headers=member_context(USER)).status_code == 403


def test_rejected_quantities_and_second_leg_failure_roll_back(tmp_path, monkeypatch):
    _, store, commands = setup(tmp_path)
    product = register_stock(commands)
    destination = location(commands)
    commands.intake("intake", product, M("5"))
    before = queries(commands).history(product, limit=25, cursor=None)
    with pytest.raises(Conflict, match="inventory_insufficient_stock"):
        commands.transfer("empty", product, destination, PANTRY, M("1"))
    with pytest.raises(Conflict, match="inventory_insufficient_stock"):
        commands.transfer("too-much", product, PANTRY, destination, M("6"))
    with pytest.raises(InvalidInput, match="invalid_material_quantity"):
        commands.transfer("zero", product, PANTRY, destination, M("0"))

    append = SQLiteInventory.append

    def fail_on_deposit(stock, movement, balance):
        if movement.kind is MovementKind.TRANSFER and movement.delta > 0:
            raise StorageFailure("injected_transfer_failure")
        append(stock, movement, balance)

    with monkeypatch.context() as patch:
        patch.setattr(SQLiteInventory, "append", fail_on_deposit)
        with pytest.raises(StorageFailure, match="injected_transfer_failure"):
            commands.transfer("move", product, PANTRY, destination, M("3"))
    assert queries(commands).history(product, limit=25, cursor=None) == before
    with store.read() as unit:
        assert destination not in unit.inventory.location_bindings("home", product)
    with pytest.raises(NotFound, match="operation_missing"):
        commands.original(CatalogAction.TRANSFER, "move", commands.actor.current())

    commands.intake("capacity", product, M("999999999994.999999"))
    commands.transfer("move", product, PANTRY, destination, M("999999999999.999999"))
    commands.intake("refill", product, M("1"))
    with pytest.raises(Conflict, match="inventory_stock_capacity"):
        commands.transfer("full", product, PANTRY, destination, M("1"))
    whole = commands.register("whole", "Apples", BaseUnit.PIECE).result.decode()["product_id"]
    with pytest.raises(InvalidInput, match="invalid_material_precision"):
        commands.transfer("fraction", whole, PANTRY, destination, M("0.5"))


@pytest.mark.parametrize("same_key", [True, False])
def test_competing_writers_replay_and_activated_restore(tmp_path, same_key):
    root = tmp_path / "owned"
    root.mkdir(mode=0o700)
    _, store, commands = setup(root)
    identity_at(root, store.installation)
    product = register_stock(commands)
    destination = location(commands)
    commands.intake("intake", product, M("5"))
    archive, target = tmp_path / "archive", tmp_path / "prepared"
    checkpoint = SQLiteSnapshots(store, archive, store.installation, Clock()).create("pre-transfer")
    reopened = replace(commands, transactions=SQLiteDatabase(store.path, store.installation))
    second = "first" if same_key else "second"
    results = race(
        lambda: commands.transfer("first", product, PANTRY, destination, M("5")),
        lambda: reopened.transfer(second, product, PANTRY, destination, M("5")),
    )
    winner, receipt = next(
        (key, item)
        for key, item in zip(("first", second), results, strict=True)
        if isinstance(item, Receipt)
    )
    if same_key:
        assert results == (receipt, receipt)
    else:
        assert results.count("inventory_insufficient_stock") == 1
    assert reopened.transfer(winner, product, PANTRY, destination, M("5")) == receipt
    with pytest.raises(Conflict, match="idempotency_conflict"):
        reopened.transfer(winner, product, PANTRY, destination, M("4"))
    assert len(queries(reopened).history(product, limit=25, cursor=None).movements) == 3
    SQLiteRestorations(store, archive, target, store.installation, Clock(), checkpoint).prepare(
        "restore"
    )
    assert SQLiteActivation(root, store.installation, Clock(), target).activate().state == "active"
    owned = open_storage(root, "edge")
    try:
        current = replace(commands, transactions=owned.database)
        historical = current.transfer(winner, product, PANTRY, destination, M("5"))
        assert historical.historical and historical.result == receipt.result
        restored = queries(current).history(product, limit=25, cursor=None)
        assert len(restored.movements) == 1 and restored.locations[0].stock.available == "5"
    finally:
        owned.close()


@pytest.mark.parametrize(
    "version, fixture",
    [
        (20, "v20-inventory-history-source.sql"),
        (29, "v29-stock-location-source.sql"),
    ],
)
def test_location_migration_preserves_earlier_history(tmp_path, monkeypatch, version, fixture):
    path = tmp_path / "domus.sqlite3"
    source = Path(__file__).parents[1] / "fixtures/sqlite" / fixture
    with closing(sqlite3.connect(path, autocommit=True)) as db:
        db.executescript(source.read_text())
        installation = Installation(
            *db.execute("SELECT instance_id,channel FROM installation").fetchone()
        )
        assert db.execute("PRAGMA user_version").fetchone() == (version,)
        tables = ["inventory_materials", "inventory_movements", "inventory_effects", "receipts"]
        if version == 29:
            tables += ["shopping_receipts", "shopping_receipt_returns"]
            assert db.execute("SELECT COUNT(*) FROM shopping_receipt_returns").fetchone() == (1,)
        original = {table: db.execute("SELECT * FROM " + table).fetchall() for table in tables}
    path.chmod(0o600)
    store = SQLiteDatabase(path, installation)
    previous = path.read_bytes()
    with monkeypatch.context() as patch:
        patch.setattr(storage, "LOCATION_STATEMENTS", (*storage.LOCATION_STATEMENTS, "bad SQL"))
        with pytest.raises(StorageFailure):
            store.initialize(require_existing=True)
    assert path.read_bytes() == previous
    store.initialize(require_existing=True)
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("PRAGMA user_version").fetchone() == (SCHEMA_VERSION,)
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        for table, expected in original.items():
            actual = db.execute("SELECT * FROM " + table).fetchall()
            if table == "inventory_movements":
                assert all(row[-1] is None for row in actual)
                actual = [row[: len(expected[0])] for row in actual]
            assert actual == expected
        assert db.execute("SELECT * FROM inventory_locations").fetchall() == []
        assert db.execute("SELECT * FROM inventory_transfers").fetchall() == []
        product = db.execute(
            "SELECT product_id FROM inventory_products WHERE name='Oil'"
        ).fetchone()[0]

    actor = Actor()
    actor.human = HumanIdentity("ha_admin", True, True, False)
    commands = InventoryCommands(store, actor, Clock(), SecureIdentifiers())
    cupboard = location(commands)
    before = queries(commands).history(product, limit=25, cursor=None)
    pantry = before.locations[0].stock
    assert pantry.reserved != "0"
    with pytest.raises(Conflict, match="inventory_insufficient_stock"):
        commands.transfer("reserved", product, PANTRY, cupboard, M(pantry.recorded))
    assert queries(commands).history(product, limit=25, cursor=None) == before


def test_location_bounds_and_verification_detect_corrupt_link(tmp_path, monkeypatch):
    _, store, commands = setup(tmp_path)
    with pytest.raises(InvalidInput, match="invalid_inventory_location"):
        StorageLocation(PANTRY, "New location")
    with pytest.raises(InvalidInput, match="invalid_inventory_location_name"):
        location(commands, "invalid", " ")
    product = register_stock(commands)
    commands.intake("intake", product, M("5"))
    destination = location(commands)
    transfer = commands.transfer("move", product, PANTRY, destination, M("4")).result.decode()
    with closing(sqlite3.connect(store.path)) as db:
        db.row_factory = sqlite3.Row
        verify_inventory_locations(db)
        with monkeypatch.context() as patch:
            patch.setattr("domus.infrastructure.sqlite_inventory.MAX_NAMED_LOCATIONS", 0)
            with pytest.raises(StorageFailure, match="invalid_inventory_locations"):
                verify_inventory_locations(db)
        for sql, value, error in (
            (
                "UPDATE inventory_transfers SET destination_location=?",
                "wrong",
                "invalid_inventory_transfer",
            ),
            (
                "UPDATE inventory_movements SET created_at=? WHERE delta<0",
                5,
                "invalid_inventory_transfer",
            ),
            ("UPDATE inventory_locations SET name_key=?", "wrong", "invalid_inventory_locations"),
            (
                "UPDATE inventory_materials SET label=? WHERE location_id!='pantry'",
                "wrong",
                "invalid_inventory_catalog_binding",
            ),
            (
                "UPDATE inventory_movements SET transfer_id=? WHERE delta<0",
                "wrong",
                "invalid_inventory_transfer",
            ),
            (
                "DELETE FROM inventory_transfers WHERE transfer_id=?",
                transfer["transfer_id"],
                "invalid_inventory_transfer",
            ),
        ):
            db.execute(sql, (value,))
            with pytest.raises(StorageFailure, match=error):
                verify_inventory_locations(db)
            db.rollback()

    with store.write() as unit:
        catalog = unit.inventory.product("home", product)
        unit.inventory.add_material(
            catalog.binding("home", location="legacy-shelf", reference="legacy-material")
        )

    class CollidingIdentifiers:
        def new(self):
            return "legacy-shelf"

    with pytest.raises(StorageFailure, match="inventory_location_identity_conflict"):
        location(
            replace(commands, identifiers=CollidingIdentifiers()), "collision", "Extra location"
        )
    for index in range(1, MAX_NAMED_LOCATIONS):
        location(commands, f"loc-{index}", f"Shelf {index}")
    with pytest.raises(Conflict, match="inventory_location_limit"):
        location(commands, "extra", "Extra location")
