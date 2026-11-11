"""Shared Shopping projects exact needs and preserves attributed manual requests."""

import sqlite3
from contextlib import closing
from dataclasses import replace
from pathlib import Path

import pytest
from test_activation_compatibility import identity_at
from test_household_commands import Actor, Clock
from test_inventory_catalog_http import INVENTORY, OUTSIDER, VIEWER, get, post, register
from test_inventory_catalog_storage import register as register_stock
from test_inventory_catalog_storage import setup
from test_pantry_replenishment import configure
from test_recurrence_http import USER
from test_rewards_http import member_context
from test_rewards_storage import race
from test_shopping_http import command, original
from test_task_commands import resource
from test_task_runtime import api as api

from domus.application.fixed_materialization import MaintenanceScope
from domus.application.inventory import CatalogAction, InventoryCommands, InventorySettlement
from domus.application.inventory_queries import InventoryQueries
from domus.application.task_requests import CompleteTask, CreateTask
from domus.domain.errors import StorageFailure
from domus.domain.identity import (
    HumanIdentity,
    Member,
    MemberStatus,
    Permission,
    PermissionRule,
    Role,
)
from domus.domain.inventory import BaseUnit, EffectKind
from domus.domain.member_profiles import MemberPresentation
from domus.domain.storage import Installation, Receipt
from domus.domain.task_material_values import (
    MaterialPendingReason,
    MaterialQuantity,
    MaterialSelection,
    MaterialUsage,
)
from domus.domain.task_values import TaskContent
from domus.infrastructure import sqlite as storage
from domus.infrastructure.application_runtime import SecureIdentifiers
from domus.infrastructure.owned_storage import open_storage
from domus.infrastructure.sqlite import SQLiteDatabase
from domus.infrastructure.sqlite_activation import SQLiteActivation
from domus.infrastructure.sqlite_restoration import SQLiteRestorations
from domus.infrastructure.sqlite_shopping import verify_shopping_extras
from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots
from domus.infrastructure.task_cursor import TaskCursor

M = MaterialQuantity
REQUESTER = "d" * 32
MANAGER = "e" * 32


def view(api, path="", user=USER, **params):
    return api.client.get(
        INVENTORY + "/shopping-list" + path, headers=member_context(user), params=params
    )


def sources(product):
    return f"/{product}/sources"


def test_shared_list_exact_attribution_and_current_permissions(api):
    with api.store.write() as unit:
        for member, user, grants in (
            (
                "requester",
                REQUESTER,
                (
                    PermissionRule(Permission.SHOPPING_REQUEST, True),
                    PermissionRule(Permission.TASKS_READ, False),
                ),
            ),
            ("manager", MANAGER, (PermissionRule(Permission.SHOPPING_MANAGE, True),)),
            ("viewer", VIEWER, ()),
        ):
            unit.members.save(
                Member(member, "home", user, Role.VIEWER, MemberStatus.ACTIVE, 1, grants), 0
            )
            unit.presentations.save(MemberPresentation(member, "home", member.capitalize(), 2), 1)
    api.user(USER, True)
    assert view(api).json() == {"items": [], "next_cursor": None}
    product = register(api, "rice", "Rice", "gram")
    inactive = register(api, "unused", "Unused", "piece")
    reference = next(
        row["reference_id"] for row in get(api).json()["products"] if row["product_id"] == product
    )
    assert post(api, "stock", "intake", product_id=product, quantity="1").status_code == 200
    assert (
        post(
            api,
            "policy",
            "configure-replenishment",
            product_id=product,
            minimum="2",
            target="5",
            expected_revision="0",
        ).status_code
        == 200
    )
    planned = api.client.post(
        "/api/v1/tasks/definitions",
        headers=api.headers("plan") | member_context(USER),
        json={
            "title": "Prepare dinner",
            "expected_revision": 0,
            "materials": [{"reference_id": reference, "planned_quantity": "2.000001"}],
        },
    )
    assert planned.status_code == 200, planned.text
    api.user(REQUESTER)
    assert get(api, REQUESTER).json()["may_request"]
    tracked = {"product_id": product, "name": None, "quantity": "2.000002"}
    free = {"product_id": None, "name": "Rice", "quantity": "1"}
    assert (
        command(api, "csrf", "add-extra", user=REQUESTER, csrf=False, **tracked).status_code == 403
    )
    assert (
        command(
            api, "foreign", "add-extra", user=REQUESTER, **(tracked | {"product_id": "foreign"})
        ).json()["code"]
        == "inventory_product_missing"
    )
    assert (
        command(
            api, "fraction", "add-extra", user=REQUESTER, **(free | {"quantity": "0.5"})
        ).json()["code"]
        == "invalid_material_precision"
    )
    added = command(api, "tracked", "add-extra", user=REQUESTER, **tracked)
    assert added.status_code == 200, added.text
    assert command(api, "tracked", "add-extra", user=REQUESTER, **tracked).json() == added.json()
    assert original(api, "tracked", "add-extra", REQUESTER).json() == added.json()
    assert (
        command(
            api, "tracked", "add-extra", user=REQUESTER, **(tracked | {"quantity": "2"})
        ).json()["code"]
        == "idempotency_conflict"
    )
    untracked = command(api, "free", "add-extra", user=REQUESTER, **free).json()["result"][
        "extra_id"
    ]
    tracked_id = added.json()["result"]["extra_id"]
    assert (
        command(api, "no-clear", "clear-extra", user=REQUESTER, extra_id=tracked_id).status_code
        == 403
    )
    rows = view(api, user=REQUESTER).json()["items"]
    tracked_row, free_row = rows
    assert tracked_row["name"] == free_row["name"] == "Rice"
    assert tracked_row["product_id"] == product and free_row["extra_id"] == untracked
    assert (
        tracked_row["pantry"],
        tracked_row["tasks"],
        tracked_row["manual"],
        tracked_row["total"],
    ) == ("4", "0", "2.000002", "6.000002")
    assert free_row["attribution"]["author_alias"] == "Requester"
    detail = view(api, sources(product), REQUESTER, limit=1).json()
    assert detail["next_cursor"] and detail["sources"][0]["kind"] != "task"
    more = view(api, sources(product), REQUESTER, limit=1, cursor=detail["next_cursor"]).json()
    assert {source["kind"] for source in detail["sources"] + more["sources"]} == {"pantry", "extra"}
    extra = next(
        source for source in detail["sources"] + more["sources"] if source["kind"] == "extra"
    )
    assert extra["origin_id"] == tracked_id and extra["attribution"]["author_alias"] == "Requester"
    assert (
        view(api, sources(inactive), REQUESTER, limit=1, cursor=detail["next_cursor"]).status_code
        == 422
    )
    assert view(api, sources("foreign"), REQUESTER).status_code == 404
    assert view(api, user=REQUESTER, limit=1, limit_duplicate="1").status_code == 422
    cursor = view(api, user=REQUESTER, limit=1).json()["next_cursor"]
    assert view(api, user=REQUESTER, limit=1, cursor=cursor).json()["items"] == []
    api.user(VIEWER)
    assert view(api, user=VIEWER, limit=1, cursor=cursor).status_code == 422
    assert command(api, "denied", "add-extra", user=VIEWER, **free).status_code == 403
    api.user(OUTSIDER)
    assert view(api, user=OUTSIDER).status_code == 403
    api.user(MANAGER)
    task_detail = view(api, sources(product), MANAGER).json()
    assert task_detail["item"]["tasks"] == "1.000001"
    assert (
        next(source for source in task_detail["sources"] if source["kind"] == "task")["name"]
        == "Prepare dinner"
    )
    assert (
        command(api, "missing", "clear-extra", user=MANAGER, extra_id="foreign").json()["code"]
        == "shopping_extra_missing"
    )
    cleared = command(api, "clear", "clear-extra", user=MANAGER, extra_id=tracked_id)
    assert cleared.status_code == 200, cleared.text
    assert original(api, "clear", "clear-extra", MANAGER).json() == cleared.json()
    assert (
        command(api, "clear", "clear-extra", user=MANAGER, extra_id=tracked_id).json()
        == cleared.json()
    )
    assert (
        command(api, "again", "clear-extra", user=MANAGER, extra_id=tracked_id).json()["code"]
        == "shopping_extra_cleared"
    )
    assert view(api, sources(product), MANAGER).json()["item"]["manual"] == "0"
    api.user(REQUESTER)
    with api.store.write() as unit:
        requester = unit.members.get("home", "requester")
        unit.members.save(replace(requester, exceptions=(), revision=2), 1)
    assert original(api, "tracked", "add-extra", REQUESTER).status_code == 403
    assert command(api, "tracked", "add-extra", user=REQUESTER, **tracked).status_code == 403


def queries(commands):
    store = commands.transactions
    return InventoryQueries(
        store,
        MaintenanceScope(store.installation, "home"),
        commands.actor.current(),
        TaskCursor(Clock(), b"x" * 32),
    )


def test_reservations_automatic_supply_and_closed_work(tmp_path):
    tasks, store, commands = setup(tmp_path)
    tasks = replace(
        tasks,
        inventory_factory=lambda unit: InventorySettlement(
            unit.inventory, Clock(), commands.identifiers
        ),
    )
    product = register_stock(commands)
    commands.intake("stock", product, M("3"))
    configure(commands, "policy", product, "2", "5")
    reference = queries(commands).report(limit=1, cursor=None).products[0].reference_id
    salt = commands.register("salt", "Salt", BaseUnit.GRAM).result.decode()["product_id"]
    with store.read() as unit:
        salt_reference = unit.inventory.product("home", salt).reference_id

    def plan(key, amount):
        return resource(
            tasks.create(
                key,
                CreateTask(
                    TaskContent(key),
                    materials=(
                        MaterialSelection(reference, M(amount)),
                        MaterialSelection(salt_reference, M("1")),
                    ),
                ),
            )
        )[1]

    first = plan("reserved", "2")
    commands.commit_effect(
        "reserve", EffectKind.RESERVATION, reference, M("2"), occurrence_id=first
    )
    extra = commands.add_extra("add", product, None, M("2"))
    detail = queries(commands).shopping_sources(product, limit=25, cursor=None)
    assert (detail.item.pantry, detail.item.tasks, detail.item.manual, detail.item.total) == (
        "4",
        "0",
        "2",
        "6",
    )
    assert next(line for line in detail.sources if line.kind == "task").reserved == "2"
    a, b = sorted((plan("independent-a", "3.000001"), plan("independent-b", "3.000001")))
    commands.commit_effect("demand", EffectKind.DEMAND, reference, M("2.000001"), occurrence_id=a)
    purchase = commands.purchase("buy", product, None, M("5")).result.decode()["purchase_id"]
    arrival = commands.receive_purchase("physical", purchase, M("0.25"), 1)
    detail = queries(commands).shopping_sources(product, limit=25, cursor=None)
    by_id = {line.origin_id: line for line in detail.sources}
    assert (by_id[product].incoming, by_id[a].stock, by_id[a].incoming, by_id[a].to_buy) == (
        "4",
        "1",
        "1",
        "0.000001",
    )
    assert (by_id[b].stock, by_id[b].incoming, by_id[b].to_buy) == ("0", "0", "3.000001")
    assert (detail.item.pantry, detail.item.tasks, detail.item.manual, detail.item.total) == (
        "0",
        "3.000002",
        "2",
        "5.000002",
    )
    commands.post_purchase_receipt("post", purchase, arrival.result.decode()["receipt_id"])
    with store.read() as unit:
        member = unit.members.by_user("home", "ha_admin")
        line = next(
            line
            for line in unit.tasks.occurrence("home", b).definition_snapshot.materials
            if line.binding.reference_id == reference
        )
    tasks.complete(
        "complete",
        CompleteTask(
            b, 1, (member.member_id,), 95, material_usages=(MaterialUsage(line.line_id, M("6")),)
        ),
    )
    detail = queries(commands).shopping_sources(product, limit=25, cursor=None)
    assert b not in {line.origin_id for line in detail.sources}
    with store.read() as unit:
        cycle = unit.tasks.occurrence("home", b).current_cycle_id
        pending = unit.task_materials.list("home", cycle)
        assert {item.pending_reason for item in pending} == {
            MaterialPendingReason.STOCK_SHORTAGE,
            MaterialPendingReason.ACTUAL_QUANTITY_REQUIRED,
        }
    assert detail.item.manual == "2"
    assert commands.original(CatalogAction.ADD_EXTRA, "add", commands.actor.current()) == extra


@pytest.mark.parametrize("duplicate", [True, False])
def test_concurrent_clears_and_exact_retry(tmp_path, duplicate):
    _, store, commands = setup(tmp_path)
    other = replace(commands, transactions=SQLiteDatabase(store.path, store.installation))
    request = commands.add_extra("add", None, "Apples", M("2"))
    extra = request.result.decode()["extra_id"]
    keys = ("same", "same" if duplicate else "competing")
    results = race(
        lambda: commands.clear_extra(keys[0], extra), lambda: other.clear_extra(keys[1], extra)
    )
    key, saved = next(
        (key, result)
        for key, result in zip(keys, results, strict=True)
        if isinstance(result, Receipt)
    )
    assert results == (saved, saved) if duplicate else results.count("shopping_extra_cleared") == 1
    later = other.add_extra("later", None, "Apples", M("1"))
    assert other.clear_extra(key, extra) == saved
    assert other.original(CatalogAction.CLEAR_EXTRA, key, other.actor.current()) == saved
    assert [
        item.extra_id for item in queries(other).shopping_list(limit=25, cursor=None).items
    ] == [later.result.decode()["extra_id"]]
    with store.read() as unit:
        cleared = unit.shopping.extra("home", extra)
        assert cleared.cleared_by is not None and cleared.cleared_at is not None


def test_v23_migration_and_activated_restore_of_extra_receipts(tmp_path, monkeypatch):
    root = tmp_path / "source"
    root.mkdir(mode=0o700)
    path = root / "domus.sqlite3"
    fixture = Path(__file__).parents[1] / "fixtures/sqlite/v23-shared-shopping-source.sql"
    with closing(sqlite3.connect(path, autocommit=True)) as db:
        db.executescript(fixture.read_text())
        assert db.execute("PRAGMA user_version").fetchone() == (23,)
        installation = Installation(
            *db.execute("SELECT instance_id,channel FROM installation").fetchone()
        )
        tables = (
            "inventory_products",
            "inventory_replenishment",
            "inventory_movements",
            "inventory_effects",
            "task_material_intents",
            "shopping_purchases",
            "shopping_receipts",
            "receipts",
        )
        existing = {table: db.execute("SELECT * FROM " + table).fetchall() for table in tables}
        product = db.execute(
            "SELECT product_id FROM inventory_products WHERE name='Oil'"
        ).fetchone()[0]
        assert any(row[-1] is None for row in existing["shopping_receipts"])
        assert any(row[-1] is not None for row in existing["shopping_receipts"])
    path.chmod(0o600)
    store = SQLiteDatabase(path, installation)
    baseline = path.read_bytes()
    with monkeypatch.context() as patch:
        patch.setattr(
            storage,
            "SHOPPING_EXTRA_STATEMENTS",
            (*storage.SHOPPING_EXTRA_STATEMENTS, "invalid SQL"),
        )
        with pytest.raises(StorageFailure):
            store.initialize(require_existing=True)
    assert path.read_bytes() == baseline
    store.initialize(require_existing=True)
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("PRAGMA user_version").fetchone() == (30,)
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        for table, rows in existing.items():
            expected = [(*row, 0) for row in rows] if table == "shopping_purchases" else rows
            actual = db.execute("SELECT * FROM " + table).fetchall()
            if table == "inventory_movements":
                expected = [(*row, None) for row in expected]
            assert actual == expected
    identity_at(root, installation)
    actor = Actor()
    actor.human = HumanIdentity("ha_admin", True, True, False)
    commands = InventoryCommands(store, actor, Clock(), SecureIdentifiers())
    added = commands.add_extra("add", product, None, M("0.000001"))
    cleared_before = commands.add_extra("spare", None, "Spare", M("1")).result.decode()["extra_id"]
    commands.clear_extra("clear-spare", cleared_before)
    extra = added.result.decode()["extra_id"]
    archive, target = tmp_path / "archive", tmp_path / "prepared"
    checkpoint = SQLiteSnapshots(store, archive, installation, Clock()).create("shared-shopping")
    later = commands.clear_extra("clear", extra)
    SQLiteRestorations(store, archive, target, installation, Clock(), checkpoint).prepare("restore")
    assert SQLiteActivation(root, installation, Clock(), target).activate().state == "active"
    restored = open_storage(root, "edge")
    try:
        recovery = replace(commands, transactions=restored.database)
        assert (
            queries(recovery).shopping_sources(product, limit=25, cursor=None).item.manual
            == "0.000001"
        )
        assert recovery.add_extra("add", product, None, M("0.000001")) == added
        assert recovery.clear_extra("clear", extra).operation_id == later.operation_id
        assert recovery.original(CatalogAction.CLEAR_EXTRA, "clear", actor.human).historical
        assert (
            queries(recovery).shopping_sources(product, limit=25, cursor=None).item.manual
            == "0.000001"
        )
        recovery.clear_extra("new-clear", extra)
        assert queries(recovery).shopping_sources(product, limit=25, cursor=None).item.manual == "0"
    finally:
        restored.close()


@pytest.mark.parametrize(
    "damage",
    [
        "UPDATE shopping_extras SET quantity=1000001 WHERE product_id IS NULL",
        "UPDATE shopping_extras SET base_unit='millilitre' WHERE product_id IS NOT NULL",
        "UPDATE shopping_extras SET product_id='missing' WHERE product_id IS NOT NULL",
    ],
)
def test_snapshot_verifies_extra_records(tmp_path, damage):
    _, store, commands = setup(tmp_path)
    product = commands.register("product", "Oil", BaseUnit.GRAM).result.decode()["product_id"]
    commands.add_extra("tracked", product, None, M("0.000001"))
    commands.add_extra("free", None, "Oranges", M("2"))
    with closing(sqlite3.connect(store.path, autocommit=True)) as db:
        db.row_factory = sqlite3.Row
        verify_shopping_extras(db)
        db.execute(damage)
        with pytest.raises(StorageFailure, match="invalid_shopping_records"):
            verify_shopping_extras(db)
