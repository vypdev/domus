"""Check attributed balance cancellation against receipts and incoming supply."""

import sqlite3
from contextlib import closing
from dataclasses import replace
from pathlib import Path

import pytest
from test_activation_compatibility import identity_at
from test_household_commands import Actor, Clock
from test_inventory_catalog_http import INVENTORY, VIEWER, get, post, register
from test_inventory_catalog_storage import setup
from test_recurrence_http import USER
from test_rewards_http import member_context
from test_rewards_storage import race
from test_shared_shopping import queries
from test_shopping_http import command, original, view
from test_task_runtime import api as api

from domus.application.inventory import CatalogAction, InventoryCommands
from domus.domain.errors import InvalidInput, NotFound, StorageFailure
from domus.domain.identity import (
    HumanIdentity,
    Member,
    MemberStatus,
    Permission,
    PermissionRule,
    Role,
)
from domus.domain.member_profiles import MemberPresentation
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
ACTION = CatalogAction.CANCEL_BALANCE
SHOPPER = "d" * 32
REASON = "Supplier confirmed the shortage"


def test_protected_cancel_preserves_receipts_and_reopens_demand(api):
    with api.store.write() as unit:
        unit.members.save(
            Member(
                "shopper",
                "home",
                SHOPPER,
                Role.VIEWER,
                MemberStatus.ACTIVE,
                1,
                (PermissionRule(Permission.SHOPPING_MANAGE, True),),
            ),
            0,
        )
        unit.presentations.save(MemberPresentation("shopper", "home", "Shopper", 2), 1)
        unit.members.save(Member("viewer", "home", VIEWER, Role.VIEWER, MemberStatus.ACTIVE, 1), 0)
    api.user(USER, True)
    product = register(api, "flour", "Flour", "gram")
    policy = post(
        api,
        "policy",
        "configure-replenishment",
        product_id=product,
        minimum="6.000001",
        target="6.000001",
        expected_revision="0",
    )
    assert policy.status_code == 200, policy.text
    extra = command(
        api, "lemons", "add-extra", name="Lemons", product_id=None, quantity="2"
    ).json()["result"]["extra_id"]
    recorded = command(
        api,
        "trip",
        "record-session",
        items=[
            {"product_id": product, "extra_id": None, "quantity": "6.000001"},
            {"product_id": None, "extra_id": extra, "quantity": "2"},
        ],
    )
    assert recorded.status_code == 200, recorded.text
    session = recorded.json()["result"]
    purchase = session["purchase_ids"][0]
    item_path = f"/{purchase}/receipts"
    arrived = command(
        api, "arrive", "receive", purchase_id=purchase, quantity="4.000001", expected_revision="1"
    )
    assert arrived.status_code == 200, arrived.text
    receipt_id = arrived.json()["result"]["receipt_id"]
    before = view(api, item_path).json()
    assert before["purchase"]["cancelled"] == "0" and before["cancellation"] is None
    assert get(api).json()["products"][0]["shopping_needed"] == "0"

    params = {"purchase_id": purchase, "reason": REASON, "expected_revision": "2"}
    api.user(VIEWER)
    assert command(api, "no", "cancel-balance", user=VIEWER, **params).status_code == 403
    api.user(SHOPPER)
    assert (
        command(api, "csrf", "cancel-balance", user=SHOPPER, csrf=False, **params).status_code
        == 403
    )
    for payload, code in (
        (params | {"reason": " "}, "invalid_inventory_reason"),
        (params | {"purchase_id": "foreign"}, "shopping_purchase_missing"),
        (params | {"expected_revision": "1"}, "revision_conflict"),
    ):
        rejected = command(api, "rejected", "cancel-balance", user=SHOPPER, **payload)
        assert rejected.json()["code"] == code, rejected.text
        assert original(api, "rejected", "cancel-balance", SHOPPER).status_code == 404
        assert view(api, item_path, SHOPPER).json() == before

    response = command(api, "cancel", "cancel-balance", user=SHOPPER, **params)
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved["result"] == {"purchase_id": purchase, "cancelled": "2", "revision": "3"}
    assert command(api, "cancel", "cancel-balance", user=SHOPPER, **params).json() == saved
    assert original(api, "cancel", "cancel-balance", SHOPPER).json() == saved
    assert (
        command(
            api, "cancel", "cancel-balance", user=SHOPPER, **(params | {"reason": "Changed"})
        ).json()["code"]
        == "idempotency_conflict"
    )
    assert (
        command(
            api, "closed", "cancel-balance", user=SHOPPER, **(params | {"expected_revision": "3"})
        ).json()["code"]
        == "shopping_balance_closed"
    )
    assert (
        command(
            api,
            "late",
            "receive",
            user=SHOPPER,
            purchase_id=purchase,
            quantity="1",
            expected_revision="3",
        ).json()["code"]
        == "shopping_receipt_exceeds_purchase"
    )
    assert (
        command(
            api, "premature", "purchase", user=SHOPPER, product_id=product, name=None, quantity="2"
        ).json()["code"]
        == "shopping_purchase_open"
    )
    detail = view(api, item_path, SHOPPER).json()
    assert detail["receipts"] == before["receipts"]
    assert detail["cancellation"]["quantity"] == "2"
    assert detail["cancellation"]["reason"] == REASON
    assert detail["cancellation"]["author_alias"] == "Shopper"
    assert detail["cancellation"]["member_id"] == "shopper"
    assert detail["cancellation"]["created_at"].isdigit()
    purchase_view = detail["purchase"]
    assert tuple(
        purchase_view[key]
        for key in ("purchased", "received", "remaining", "pending_stock", "cancelled")
    ) == (
        "6.000001",
        "4.000001",
        "0",
        "4.000001",
        "2",
    )
    current = get(api, SHOPPER).json()["products"][0]
    assert current["outstanding_purchase"] == "4.000001" and current["shopping_needed"] == "2"
    shared = api.client.get(INVENTORY + "/shopping-list", headers=member_context(SHOPPER)).json()
    assert next(item for item in shared["items"] if item["product_id"] == product)["total"] == "2"
    api.user(USER, True)
    posted = command(api, "post", "post-receipt", purchase_id=purchase, receipt_id=receipt_id)
    assert posted.status_code == 200, posted.text
    grouped = api.client.get(
        INVENTORY + "/purchase-sessions/" + session["session_id"], headers=member_context(USER)
    )
    assert grouped.json()["items"][0] == purchase_view | {"pending_stock": "0", "revision": "4"}
    current = get(api).json()["products"][0]
    assert (current["outstanding_purchase"], current["shopping_needed"], current["recorded"]) == (
        "0",
        "2",
        "4.000001",
    )
    assert (
        command(
            api, "replacement", "purchase", product_id=product, name=None, quantity="2"
        ).status_code
        == 200
    )
    with api.store.write() as unit:
        member = unit.members.get("home", "shopper")
        unit.members.save(replace(member, exceptions=(), revision=2), 1)
    api.user(SHOPPER)
    assert original(api, "cancel", "cancel-balance", SHOPPER).status_code == 403


@pytest.mark.parametrize("competitor", ["same-key", "cancel", "arrival"])
def test_balance_races_and_original_retry(tmp_path, competitor):
    _, store, commands = setup(tmp_path)
    purchase = commands.purchase("buy", None, "Lemons", M("6")).result.decode()["purchase_id"]
    other = replace(commands, transactions=SQLiteDatabase(store.path, store.installation))
    key = "first" if competitor == "same-key" else "competing"

    def second():
        if competitor == "arrival":
            return other.receive_purchase(key, purchase, M("4"), 1)
        return other.cancel_purchase_balance(key, purchase, REASON, 1)

    results = race(lambda: commands.cancel_purchase_balance("first", purchase, REASON, 1), second)
    if competitor == "same-key":
        assert isinstance(results[0], Receipt) and results[0] == results[1]
    else:
        assert results.count("revision_conflict") == 1
    accepted = next(result for result in results if isinstance(result, Receipt))
    data = accepted.result.decode()
    query = queries(commands)
    if "cancelled" not in data:
        assert query.physical_receipts(purchase, limit=25, cursor=None).purchase.remaining == "2"
        with pytest.raises(NotFound, match="operation_missing"):
            commands.original(ACTION, "first", commands.actor.current())
        accepted = commands.cancel_purchase_balance("after-arrival", purchase, REASON, 2)
        assert accepted.result.decode()["cancelled"] == "2"
    else:
        saved_key = "first" if isinstance(results[0], Receipt) else key
        assert commands.original(ACTION, saved_key, commands.actor.current()) == accepted
        assert commands.cancel_purchase_balance(saved_key, purchase, REASON, 1) == accepted
        assert accepted.result.decode()["cancelled"] == "6"
    detail = query.physical_receipts(purchase, limit=25, cursor=None)
    assert detail.purchase.remaining == "0" and detail.cancellation is not None
    assert detail.purchase.cancelled == accepted.result.decode()["cancelled"]


def test_cancellation_rolls_back_with_original_receipt_and_checks_snapshot_integrity(
    tmp_path, monkeypatch
):
    _, store, commands = setup(tmp_path)
    purchase = commands.purchase("buy", None, "Lemons", M("2")).result.decode()["purchase_id"]
    before = queries(commands).physical_receipts(purchase, limit=25, cursor=None)

    def fail(*_):
        raise StorageFailure("interrupted_cancellation")

    with monkeypatch.context() as patch:
        patch.setattr(SQLiteShopping, "add_cancellation", fail)
        with pytest.raises(StorageFailure, match="interrupted_cancellation"):
            commands.cancel_purchase_balance("cancel", purchase, REASON, 1)
    assert queries(commands).physical_receipts(purchase, limit=25, cursor=None) == before
    with pytest.raises(NotFound, match="operation_missing"):
        commands.original(ACTION, "cancel", commands.actor.current())
    commands.cancel_purchase_balance("cancel", purchase, REASON, 1)
    with closing(sqlite3.connect(store.path, autocommit=True)) as db:
        db.row_factory = sqlite3.Row
        verify_shopping_records(db)
        db.execute("UPDATE shopping_cancellations SET reason=' '")
        with pytest.raises(InvalidInput, match="invalid_inventory_reason"):
            verify_shopping_records(db)
        db.execute("DELETE FROM shopping_cancellations")
        with pytest.raises(StorageFailure, match="invalid_shopping_records"):
            verify_shopping_records(db)


def test_v25_migration_and_activated_restore_of_cancelled_balances(tmp_path, monkeypatch):
    root = tmp_path / "owned"
    root.mkdir(mode=0o700)
    path = root / "domus.sqlite3"
    fixture = Path(__file__).parents[1] / "fixtures/sqlite/v25-purchase-balance-source.sql"
    with closing(sqlite3.connect(path, autocommit=True)) as db:
        db.executescript(fixture.read_text())
        assert db.execute("PRAGMA user_version").fetchone() == (25,)
        installation = Installation(
            *db.execute("SELECT instance_id,channel FROM installation").fetchone()
        )
        tables = (
            "inventory_movements",
            "inventory_effects",
            "shopping_sessions",
            "shopping_session_items",
            "shopping_purchases",
            "shopping_receipts",
            "shopping_extras",
            "receipts",
        )
        existing = {table: db.execute("SELECT * FROM " + table).fetchall() for table in tables}
        tracked, free = (row[3] for row in existing["shopping_session_items"])
        assert {row[-1] is None for row in existing["shopping_receipts"]} == {True, False}
        db.row_factory = sqlite3.Row
        verify_shopping_records(db, has_cancellations=False)
    path.chmod(0o600)
    store = SQLiteDatabase(path, installation)
    baseline = path.read_bytes()
    with monkeypatch.context() as patch:
        patch.setattr(
            storage,
            "SHOPPING_CANCELLATION_STATEMENTS",
            (*storage.SHOPPING_CANCELLATION_STATEMENTS, "invalid SQL"),
        )
        with pytest.raises(StorageFailure):
            store.initialize(require_existing=True)
    assert path.read_bytes() == baseline
    store.initialize(require_existing=True)
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("PRAGMA user_version").fetchone() == (26,)
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        for table, rows in existing.items():
            actual = db.execute("SELECT * FROM " + table).fetchall()
            expected = [(*row, 0) for row in rows] if table == "shopping_purchases" else rows
            assert actual == expected
    identity_at(root, installation)
    actor = Actor()
    actor.human = HumanIdentity("ha_admin", True, True, False)
    commands = InventoryCommands(store, actor, Clock(), SecureIdentifiers())
    committed = commands.cancel_purchase_balance("cancel-free", free, REASON, 1)
    archive, target = tmp_path / "archive", tmp_path / "prepared"
    checkpoint = SQLiteSnapshots(store, archive, installation, Clock()).create("balance")
    later = commands.cancel_purchase_balance("cancel-tracked", tracked, REASON, 2)
    SQLiteRestorations(store, archive, target, installation, Clock(), checkpoint).prepare("restore")
    assert SQLiteActivation(root, installation, Clock(), target).activate().state == "active"
    reopened = open_storage(root, "edge")
    try:
        recovery = replace(commands, transactions=reopened.database)
        assert recovery.cancel_purchase_balance("cancel-free", free, REASON, 1) == committed
        historical = recovery.cancel_purchase_balance("cancel-tracked", tracked, REASON, 2)
        assert historical.historical and historical.operation_id == later.operation_id
        assert historical.result == later.result
        view = queries(recovery).physical_receipts(tracked, limit=25, cursor=None)
        assert view.purchase.remaining == "2" and view.cancellation is None
        assert recovery.cancel_purchase_balance("fresh", tracked, REASON, 2).result == later.result
    finally:
        reopened.close()
