"""Qualify append-only correction of a tracked receipt before Pantry posting."""

import sqlite3
from contextlib import closing
from dataclasses import replace
from pathlib import Path

import pytest
from test_activation_compatibility import identity_at
from test_household_commands import Actor, Clock
from test_inventory_catalog_http import VIEWER, get, register
from test_inventory_catalog_storage import setup
from test_recurrence_http import USER
from test_rewards_storage import race
from test_shared_shopping import queries
from test_shopping_http import SHOPPER, command, original, view
from test_shopping_storage import register as register_storage
from test_shopping_storage import report
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
ACTION = CatalogAction.VOID_RECEIPT
REASON = "Only three units arrived"


def test_void_recomputes_pending_receipts_and_keeps_original_history(api):
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
    purchase = command(
        api, "buy", "purchase", product_id=product, name=None, quantity="5.000001"
    ).json()["result"]["purchase_id"]
    other = command(
        api, "other", "receive", purchase_id=purchase, quantity="0.333333", expected_revision="1"
    ).json()["result"]["receipt_id"]
    wrong = command(
        api, "wrong", "receive", purchase_id=purchase, quantity="4.000001", expected_revision="2"
    ).json()["result"]["receipt_id"]
    free = command(api, "loose", "purchase", product_id=None, name="Lemons", quantity="2").json()[
        "result"
    ]["purchase_id"]
    untracked = command(
        api, "loose-received", "receive", purchase_id=free, quantity="1", expected_revision="1"
    ).json()["result"]["receipt_id"]
    path = f"/{purchase}/receipts"
    before = view(api, path).json()
    stock = get(api).json()["products"]
    assert stock[0]["outstanding_purchase"] == "5.000001"
    assert before["receipts"][0]["voided"] is None

    params = {
        "purchase_id": purchase,
        "receipt_id": wrong,
        "reason": REASON,
        "expected_revision": "3",
    }
    api.user(VIEWER)
    assert command(api, "denied", "void-receipt", user=VIEWER, **params).status_code == 403
    api.user(SHOPPER)
    assert (
        command(api, "csrf", "void-receipt", user=SHOPPER, csrf=False, **params).status_code == 403
    )
    for invalid, code in (
        ({"reason": " "}, "invalid_inventory_reason"),
        ({"purchase_id": "foreign"}, "shopping_purchase_missing"),
        ({"receipt_id": untracked}, "shopping_receipt_missing"),
        ({"expected_revision": "2"}, "revision_conflict"),
        (
            {"purchase_id": free, "receipt_id": untracked, "expected_revision": "2"},
            "shopping_receipt_untracked",
        ),
    ):
        reply = command(api, "rejected", "void-receipt", user=SHOPPER, **(params | invalid))
        assert reply.json()["code"] == code, reply.text
        assert original(api, "rejected", "void-receipt", SHOPPER).status_code == 404
        assert view(api, path, SHOPPER).json() == before
        assert get(api, SHOPPER).json()["products"] == stock

    response = command(api, "void", "void-receipt", user=SHOPPER, **params)
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved["result"] == {
        "purchase_id": purchase,
        "receipt_id": wrong,
        "quantity": "4.000001",
        "revision": "4",
    }
    assert command(api, "void", "void-receipt", user=SHOPPER, **params).json() == saved
    assert original(api, "void", "void-receipt", SHOPPER).json() == saved
    assert (
        command(
            api, "void", "void-receipt", user=SHOPPER, **(params | {"reason": "Changed"})
        ).json()["code"]
        == "idempotency_conflict"
    )
    detail = view(api, path, SHOPPER, limit=1).json()
    correction = detail["receipts"][0]["voided"]
    assert correction["reason"] == REASON and correction["author_alias"] == "Shopper"
    assert correction["member_id"] == "shopper" and correction["created_at"].isdigit()
    assert detail["receipts"][0] == before["receipts"][0] | {"voided": correction}
    assert detail["purchase"] == before["purchase"] | {
        "received": "0.333333",
        "pending_stock": "0.333333",
        "remaining": "4.666668",
        "revision": "4",
    }
    assert view(api, path, SHOPPER, cursor=detail["next_cursor"], limit=1).json()["receipts"] == [
        before["receipts"][1]
    ]
    assert get(api, SHOPPER).json()["products"] == stock
    assert (
        command(
            api, "second", "void-receipt", user=SHOPPER, **(params | {"expected_revision": "4"})
        ).json()["code"]
        == "shopping_receipt_voided"
    )
    fixed = command(
        api,
        "correct",
        "receive",
        user=SHOPPER,
        purchase_id=purchase,
        quantity="3",
        expected_revision="4",
    )
    assert fixed.status_code == 200, fixed.text
    corrected = fixed.json()["result"]["receipt_id"]
    api.user(USER, True)
    assert (
        command(api, "wrong-post", "post-receipt", purchase_id=purchase, receipt_id=wrong).json()[
            "code"
        ]
        == "shopping_receipt_voided"
    )
    assert (
        command(
            api, "correct-post", "post-receipt", purchase_id=purchase, receipt_id=corrected
        ).status_code
        == 200
    )
    assert (
        command(
            api,
            "posted",
            "void-receipt",
            **(params | {"receipt_id": corrected, "expected_revision": "6"}),
        ).json()["code"]
        == "shopping_receipt_posted"
    )
    assert (
        command(
            api,
            "close",
            "cancel-balance",
            purchase_id=purchase,
            reason=REASON,
            expected_revision="6",
        ).status_code
        == 200
    )
    closed = view(api, path).json()
    assert closed["purchase"]["pending_stock"] == "0.333333"
    assert get(api).json()["products"][0]["recorded"] == "3"
    assert (
        command(
            api,
            "closed",
            "void-receipt",
            **(params | {"receipt_id": other, "expected_revision": "7"}),
        ).json()["code"]
        == "shopping_receipt_balance_cancelled"
    )
    assert view(api, path).json() == closed
    with api.store.write() as unit:
        member = unit.members.get("home", "shopper")
        unit.members.save(replace(member, exceptions=(), revision=2), 1)
    api.user(SHOPPER)
    assert original(api, "void", "void-receipt", SHOPPER).status_code == 403


@pytest.mark.parametrize("competitor", ["same-key", "void", "post"])
def test_void_races_with_independent_writers(tmp_path, competitor):
    _, store, commands = setup(tmp_path)
    product = register_storage(commands)
    purchase = commands.purchase("buy", product, None, M("6")).result.decode()["purchase_id"]
    receipt = commands.receive_purchase("receive", purchase, M("4"), 1).result.decode()[
        "receipt_id"
    ]
    second = replace(commands, transactions=SQLiteDatabase(store.path, store.installation))
    key = "void" if competitor == "same-key" else "competing"

    def other():
        if competitor == "post":
            return second.post_purchase_receipt(key, purchase, receipt)
        return second.void_purchase_receipt(key, purchase, receipt, REASON, 2)

    results = race(
        lambda: commands.void_purchase_receipt("void", purchase, receipt, REASON, 2), other
    )
    accepted = next(result for result in results if isinstance(result, Receipt))
    detail = queries(commands).physical_receipts(purchase, limit=25, cursor=None)
    assert detail.purchase.revision == "3" and detail.purchase.pending_stock == "0"
    if competitor == "same-key":
        assert results == (accepted, accepted)
    elif "movement_id" in accepted.result.decode():
        assert results[0] == "shopping_receipt_posted"
    else:
        assert results.count("shopping_receipt_voided") == 1
    if "movement_id" in accepted.result.decode():
        assert detail.receipts[0].voided is None and detail.purchase.remaining == "2"
        assert report(commands, product).recorded == "4"
        with pytest.raises(NotFound, match="operation_missing"):
            commands.original(ACTION, "void", commands.actor.current())
    else:
        saved_key = "void" if isinstance(results[0], Receipt) else key
        assert commands.original(ACTION, saved_key, commands.actor.current()) == accepted
        assert commands.void_purchase_receipt(saved_key, purchase, receipt, REASON, 2) == accepted
        assert detail.receipts[0].voided is not None and detail.purchase.remaining == "6"
        assert report(commands, product).recorded == "0"


@pytest.mark.parametrize("ineligible", ["posted", "untracked"])
def test_void_rollback_and_snapshot_integrity(tmp_path, monkeypatch, ineligible):
    _, store, commands = setup(tmp_path)
    product = register_storage(commands)
    purchase = commands.purchase("buy", product, None, M("6")).result.decode()["purchase_id"]
    first = commands.receive_purchase("receive", purchase, M("1"), 1).result.decode()["receipt_id"]
    if ineligible == "posted":
        commands.post_purchase_receipt("post", purchase, first)
        invalid = first
        revision = 3
    else:
        loose = commands.purchase("loose", None, "Lemons", M("1")).result.decode()["purchase_id"]
        invalid = commands.receive_purchase("loose-receive", loose, M("1"), 1).result.decode()[
            "receipt_id"
        ]
        revision = 2
    receipt = commands.receive_purchase("pending", purchase, M("3"), revision).result.decode()[
        "receipt_id"
    ]
    before = queries(commands).physical_receipts(purchase, limit=25, cursor=None)

    def fail(*_):
        raise StorageFailure("interrupted_receipt_void")

    with monkeypatch.context() as patch:
        patch.setattr(SQLiteShopping, "add_receipt_void", fail)
        with pytest.raises(StorageFailure, match="interrupted_receipt_void"):
            commands.void_purchase_receipt("void", purchase, receipt, REASON, revision + 1)
    assert queries(commands).physical_receipts(purchase, limit=25, cursor=None) == before
    with pytest.raises(NotFound, match="operation_missing"):
        commands.original(ACTION, "void", commands.actor.current())
    commands.void_purchase_receipt("void", purchase, receipt, REASON, revision + 1)
    with closing(sqlite3.connect(store.path, autocommit=True)) as db:
        db.row_factory = sqlite3.Row
        verify_shopping_records(db)
        db.execute("UPDATE shopping_receipt_voids SET reason=' '")
        with pytest.raises(InvalidInput, match="invalid_inventory_reason"):
            verify_shopping_records(db)
        db.execute("UPDATE shopping_receipt_voids SET reason=?", (REASON,))
        db.execute(
            "INSERT INTO shopping_receipt_voids "
            "SELECT household_id,?,reason,member_id,created_at FROM shopping_receipt_voids",
            (invalid,),
        )
        with pytest.raises(StorageFailure, match="invalid_shopping_records"):
            verify_shopping_records(db)


def test_schema_26_upgrade_restart_and_activated_restore(tmp_path, monkeypatch):
    root = tmp_path / "owned"
    root.mkdir(mode=0o700)
    path = root / "domus.sqlite3"
    fixture = Path(__file__).parents[1] / "fixtures/sqlite/v26-physical-receipt-void-source.sql"
    with closing(sqlite3.connect(path, autocommit=True)) as db:
        db.executescript(fixture.read_text())
        assert db.execute("PRAGMA user_version").fetchone() == (26,)
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
            "shopping_cancellations",
            "receipts",
        )
        existing = {table: db.execute("SELECT * FROM " + table).fetchall() for table in tables}
        assert existing["shopping_cancellations"] and existing["shopping_session_items"]
        pending = db.execute(
            "SELECT p.purchase_id,r.receipt_id,p.revision FROM shopping_purchases p "
            "JOIN shopping_receipts r USING(household_id,purchase_id) "
            "WHERE r.movement_id IS NULL ORDER BY r.position"
        ).fetchall()
        db.row_factory = sqlite3.Row
        verify_shopping_records(db, has_voids=False)
    path.chmod(0o600)
    store = SQLiteDatabase(path, installation)
    original_bytes = path.read_bytes()
    with monkeypatch.context() as patch:
        patch.setattr(
            storage,
            "SHOPPING_RECEIPT_VOID_STATEMENTS",
            (*storage.SHOPPING_RECEIPT_VOID_STATEMENTS, "invalid SQL"),
        )
        with pytest.raises(StorageFailure):
            store.initialize(require_existing=True)
    assert path.read_bytes() == original_bytes
    store.initialize(require_existing=True)
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("PRAGMA user_version").fetchone() == (27,)
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        for table, rows in existing.items():
            assert db.execute("SELECT * FROM " + table).fetchall() == rows
        assert db.execute("SELECT * FROM shopping_receipt_voids").fetchall() == []
    identity_at(root, installation)
    actor = Actor()
    actor.human = HumanIdentity("ha_admin", True, True, False)
    commands = InventoryCommands(store, actor, Clock(), SecureIdentifiers())
    early_purchase, early_receipt, early_revision = pending[0]
    later_purchase, later_receipt, later_revision = pending[1]
    first = commands.void_purchase_receipt(
        "early", early_purchase, early_receipt, REASON, early_revision
    )
    archive, target = tmp_path / "archive", tmp_path / "prepared"
    checkpoint = SQLiteSnapshots(store, archive, installation, Clock()).create("receipt-void")
    later = commands.void_purchase_receipt(
        "later", later_purchase, later_receipt, REASON, later_revision
    )
    SQLiteRestorations(store, archive, target, installation, Clock(), checkpoint).prepare("restore")
    assert SQLiteActivation(root, installation, Clock(), target).activate().state == "active"
    reopened = open_storage(root, "edge")
    try:
        recovery = replace(commands, transactions=reopened.database)
        assert (
            recovery.void_purchase_receipt(
                "early", early_purchase, early_receipt, REASON, early_revision
            )
            == first
        )
        historical = recovery.void_purchase_receipt(
            "later", later_purchase, later_receipt, REASON, later_revision
        )
        assert historical.historical and historical.operation_id == later.operation_id
        assert historical.result == later.result
        detail = queries(recovery).physical_receipts(later_purchase, limit=25, cursor=None)
        assert detail.receipts[0].voided is None
        assert (
            recovery.void_purchase_receipt(
                "fresh", later_purchase, later_receipt, REASON, later_revision
            ).result
            == later.result
        )
    finally:
        reopened.close()
