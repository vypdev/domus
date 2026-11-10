"""Qualify a physical return from a closed purchase and its stock withdrawal."""

import sqlite3
from contextlib import closing
from dataclasses import replace
from pathlib import Path

import pytest
from test_activation_compatibility import identity_at
from test_household_commands import Actor, Clock
from test_inventory_catalog_http import INVENTORY, OUTSIDER, get, post, register
from test_inventory_catalog_storage import setup
from test_inventory_movements import history, legacy
from test_posted_receipt_correction import BOTH, post_purchase
from test_recurrence_http import USER
from test_rewards_http import member_context
from test_rewards_storage import race
from test_shared_shopping import queries
from test_shopping_http import SHOPPER, STOCKER, command, original, view
from test_shopping_storage import register as register_storage
from test_shopping_storage import report
from test_task_runtime import api as api

from domus.application.inventory import CatalogAction, InventoryCommands
from domus.domain.errors import Conflict, NotFound, StorageFailure
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
ACTION = CatalogAction.RETURN_RECEIPT
REASON = "Returned to the supplier"


def test_return_preserves_closed_purchase_and_recomputes_shared_need(api):
    with api.store.write() as unit:
        for member, user, permissions in (
            ("shopper", SHOPPER, (Permission.SHOPPING_MANAGE,)),
            ("stocker", STOCKER, (Permission.INVENTORY_MANAGE,)),
            ("returner", BOTH, (Permission.INVENTORY_MANAGE, Permission.SHOPPING_MANAGE)),
        ):
            unit.members.save(
                Member(
                    member,
                    "home",
                    user,
                    Role.VIEWER,
                    MemberStatus.ACTIVE,
                    1,
                    tuple(PermissionRule(permission, True) for permission in permissions),
                ),
                0,
            )
            unit.presentations.save(MemberPresentation(member, "home", member.capitalize(), 2), 1)
    api.user(USER, True)
    product = register(api, "rice", "Rice", "gram")
    assert (
        post(
            api,
            "target",
            "configure-replenishment",
            product_id=product,
            minimum="4.000001",
            target="4.000001",
            expected_revision="0",
        ).status_code
        == 200
    )
    purchase = command(
        api, "buy", "purchase", product_id=product, name=None, quantity="4.000001"
    ).json()["result"]["purchase_id"]
    receipt = command(
        api, "first", "receive", purchase_id=purchase, quantity="3.000001", expected_revision="1"
    ).json()["result"]["receipt_id"]
    params = {
        "purchase_id": purchase,
        "receipt_id": receipt,
        "reason": REASON,
        "expected_revision": "5",
    }
    assert (
        command(api, "pending", "return-receipt", **(params | {"expected_revision": "2"})).json()[
            "code"
        ]
        == "shopping_receipt_not_posted"
    )
    posting = command(
        api, "post-first", "post-receipt", purchase_id=purchase, receipt_id=receipt
    ).json()["result"]["movement_id"]
    assert (
        command(api, "open", "return-receipt", **(params | {"expected_revision": "3"})).json()[
            "code"
        ]
        == "shopping_purchase_not_settled"
    )
    other = command(
        api, "second", "receive", purchase_id=purchase, quantity="1", expected_revision="3"
    ).json()["result"]["receipt_id"]
    assert (
        command(
            api, "post-second", "post-receipt", purchase_id=purchase, receipt_id=other
        ).status_code
        == 200
    )
    independent = command(
        api, "independent", "purchase", product_id=product, name=None, quantity="1"
    ).json()["result"]["purchase_id"]
    loose = command(api, "loose", "purchase", product_id=None, name="Lemons", quantity="1").json()[
        "result"
    ]["purchase_id"]
    loose_receipt = command(
        api, "loose-arrival", "receive", purchase_id=loose, quantity="1", expected_revision="1"
    ).json()["result"]["receipt_id"]
    path = f"/{purchase}/receipts"
    before = view(api, path).json()
    before_stock = get(api).json()["products"]
    assert before_stock[0]["recorded"] == "4.000001" and before_stock[0]["shopping_needed"] == "0"
    for user in (SHOPPER, STOCKER):
        api.user(user)
        assert command(api, "denied", "return-receipt", user=user, **params).status_code == 403
        assert original(api, "denied", "return-receipt", user).status_code == 403
    api.user(BOTH)
    assert (
        command(api, "csrf", "return-receipt", user=BOTH, csrf=False, **params).status_code == 403
    )
    for invalid, code in (
        ({"reason": " "}, "invalid_inventory_reason"),
        ({"purchase_id": "foreign"}, "shopping_purchase_missing"),
        ({"receipt_id": loose_receipt}, "shopping_receipt_missing"),
        ({"expected_revision": "4"}, "revision_conflict"),
        (
            {"purchase_id": loose, "receipt_id": loose_receipt, "expected_revision": "2"},
            "shopping_receipt_untracked",
        ),
    ):
        reply = command(api, "rejected", "return-receipt", user=BOTH, **(params | invalid))
        assert reply.json()["code"] == code, reply.text
        assert original(api, "rejected", "return-receipt", BOTH).status_code == 404
        assert view(api, path, BOTH).json() == before
        assert get(api, BOTH).json()["products"] == before_stock
    response = command(api, "return", "return-receipt", user=BOTH, **params)
    assert response.status_code == 200, response.text
    saved = response.json()
    withdrawal = saved["result"]["movement_id"]
    assert saved["result"] == {
        "purchase_id": purchase,
        "receipt_id": receipt,
        "quantity": "3.000001",
        "movement_id": withdrawal,
        "revision": "6",
    }
    assert command(api, "return", "return-receipt", user=BOTH, **params).json() == saved
    assert original(api, "return", "return-receipt", BOTH).json() == saved
    assert (
        command(
            api, "return", "return-receipt", user=BOTH, **(params | {"reason": "Changed"})
        ).json()["code"]
        == "idempotency_conflict"
    )
    for action in ("return-receipt", "correct-posted-receipt"):
        assert (
            command(
                api, "another", action, user=BOTH, **(params | {"expected_revision": "6"})
            ).json()["code"]
            == "shopping_receipt_returned"
        )
    detail = view(api, path, BOTH).json()
    assert detail["purchase"] == before["purchase"] | {"revision": "6"}
    assert detail["purchase"]["remaining"] == "0"
    assert detail["receipts"][0] == before["receipts"][0]
    returned = detail["receipts"][1]["returned"]
    assert detail["receipts"][1] == before["receipts"][1] | {"returned": returned}
    assert returned == {
        "movement_id": withdrawal,
        "reason": REASON,
        "member_id": "returner",
        "author_alias": "Returner",
        "created_at": returned["created_at"],
    }
    assert returned["created_at"].isdigit()
    stock = get(api, BOTH).json()["products"][0]
    assert (stock["recorded"], stock["outstanding_purchase"], stock["shopping_needed"]) == (
        "1",
        "1",
        "2.000001",
    )
    shared = api.client.get(INVENTORY + "/shopping-list", headers=member_context(BOTH)).json()
    assert (
        next(item for item in shared["items"] if item["product_id"] == product)["total"]
        == "2.000001"
    )
    ledger = api.client.get(
        f"{INVENTORY}/products/{product}/movements", headers=member_context(BOTH)
    ).json()["movements"]
    assert [(entry["quantity"], entry["return_of"]) for entry in ledger] == [
        ("-3.000001", posting),
        ("1", None),
        ("3.000001", None),
    ]
    assert ledger[0]["reason"] == REASON
    assert ledger[2]["corrected_by"] is None

    partial = command(
        api,
        "partial",
        "receive",
        user=BOTH,
        purchase_id=independent,
        quantity="0.5",
        expected_revision="1",
    ).json()["result"]["receipt_id"]
    assert (
        command(
            api,
            "post-partial",
            "post-receipt",
            user=BOTH,
            purchase_id=independent,
            receipt_id=partial,
        ).status_code
        == 200
    )
    assert (
        command(
            api,
            "cancel",
            "cancel-balance",
            user=BOTH,
            purchase_id=independent,
            reason=REASON,
            expected_revision="3",
        ).status_code
        == 200
    )
    assert (
        command(
            api,
            "closed",
            "return-receipt",
            user=BOTH,
            purchase_id=independent,
            receipt_id=partial,
            reason=REASON,
            expected_revision="4",
        ).json()["code"]
        == "shopping_purchase_not_settled"
    )
    assert get(api, BOTH).json()["products"][0]["recorded"] == "1.5"
    with api.store.write() as unit:
        member = unit.members.get("home", "returner")
        unit.members.save(
            replace(
                member, exceptions=(PermissionRule(Permission.SHOPPING_MANAGE, True),), revision=2
            ),
            1,
        )
    assert original(api, "return", "return-receipt", BOTH).status_code == 403
    assert command(api, "return", "return-receipt", user=BOTH, **params).status_code == 403
    api.user(OUTSIDER)
    assert view(api, path, OUTSIDER).status_code == 403


@pytest.mark.parametrize("competitor", ["same-key", "return", "correction"])
def test_return_and_correction_races_allow_one_stock_withdrawal(tmp_path, competitor):
    _, store, first = setup(tmp_path)
    product = register_storage(first)
    purchase, receipt, posting = post_purchase(first, product)
    second = replace(first, transactions=SQLiteDatabase(store.path, store.installation))
    key = "first" if competitor == "same-key" else "competing"

    def other():
        if competitor == "correction":
            return second.correct_posted_receipt(key, purchase, receipt, REASON, 3)
        return second.return_posted_receipt(key, purchase, receipt, REASON, 3)

    results = race(
        lambda: first.return_posted_receipt("first", purchase, receipt, REASON, 3), other
    )
    accepted = next(value for value in results if isinstance(value, Receipt))
    if competitor == "same-key":
        assert results == (accepted, accepted)
    elif isinstance(results[0], Receipt) or competitor == "return":
        assert results.count("shopping_receipt_returned") == 1
    else:
        assert results[0] == "inventory_intake_corrected"
    detail = queries(first).physical_receipts(purchase, limit=25, cursor=None)
    assert detail.purchase.revision == "4"
    assert report(first, product).recorded == "0"
    assert len(history(store, first, product)) == 2
    with store.read() as unit:
        returned = unit.shopping.receipt_return("home", receipt)
        corrected = unit.inventory.correction_id("home", posting)
        assert (returned is None) != (corrected is None)
    if returned is not None:
        saved_key = "first" if isinstance(results[0], Receipt) else key
        assert first.original(ACTION, saved_key, first.actor.current()) == accepted
        assert detail.purchase.remaining == "0" and detail.receipts[0].returned is not None
    else:
        assert detail.purchase.remaining == "2" and detail.receipts[0].returned is None
        with pytest.raises(NotFound, match="operation_missing"):
            first.original(ACTION, "first", first.actor.current())


def test_return_preserves_reservations_and_rolls_back_failed_link(tmp_path, monkeypatch):
    store, commands, product, reference = legacy(tmp_path, monkeypatch)
    purchase, receipt, posting = post_purchase(commands, product)
    commands.adjust("less", product, "-2.75", "Physical count")
    before = queries(commands).physical_receipts(purchase, limit=25, cursor=None)
    before_ledger = history(store, commands, product)
    with pytest.raises(Conflict, match="inventory_insufficient_stock"):
        commands.return_posted_receipt("return", purchase, receipt, REASON, 3)
    assert queries(commands).physical_receipts(purchase, limit=25, cursor=None) == before
    assert history(store, commands, product) == before_ledger
    commands.adjust("more", product, "0.5", "Physical count")
    before_ledger = history(store, commands, product)

    def fail(*_):
        raise StorageFailure("interrupted_return_link")

    with monkeypatch.context() as patch:
        patch.setattr(SQLiteShopping, "link_receipt_return", fail)
        with pytest.raises(StorageFailure, match="interrupted_return_link"):
            commands.return_posted_receipt("return", purchase, receipt, REASON, 3)
    assert queries(commands).physical_receipts(purchase, limit=25, cursor=None) == before
    assert history(store, commands, product) == before_ledger
    with pytest.raises(NotFound, match="operation_missing"):
        commands.original(ACTION, "return", commands.actor.current())
    commands.return_posted_receipt("return", purchase, receipt, REASON, 3)
    with store.read() as unit:
        assert unit.inventory.balance("home", reference) == 1_000_001
        assert unit.inventory.reserved("home", reference) == 875_000
        assert unit.inventory.correction_id("home", posting) is None


def test_schema_28_migration_returns_and_activated_restore(tmp_path, monkeypatch):
    root = tmp_path / "owned"
    root.mkdir(mode=0o700)
    path = root / "domus.sqlite3"
    fixture = Path(__file__).parents[1] / "fixtures/sqlite/v28-physical-receipt-return-source.sql"
    with closing(sqlite3.connect(path, autocommit=True)) as db:
        db.executescript(fixture.read_text())
        assert db.execute("PRAGMA user_version").fetchone() == (28,)
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
            "shopping_receipt_voids",
            "shopping_cancellations",
            "shopping_receipt_corrections",
            "receipts",
        )
        old = {table: db.execute("SELECT * FROM " + table).fetchall() for table in tables}
        posted = {
            name: (purchase, receipt, revision)
            for name, purchase, receipt, revision in db.execute(
                "SELECT p.name,p.purchase_id,r.receipt_id,p.revision "
                "FROM shopping_purchases p JOIN shopping_receipts r "
                "USING(household_id,purchase_id) WHERE r.movement_id IS NOT NULL"
            )
        }
        pending = next(
            row[0]
            for row in db.execute(
                "SELECT receipt_id FROM shopping_receipts "
                "WHERE movement_id IS NULL ORDER BY position"
            )
        )
        assert old["shopping_receipt_voids"] and old["shopping_receipt_corrections"]
        db.row_factory = sqlite3.Row
        verify_shopping_records(db, version=28)
    path.chmod(0o600)
    store = SQLiteDatabase(path, installation)
    before = path.read_bytes()
    with monkeypatch.context() as patch:
        patch.setattr(
            storage,
            "SHOPPING_RECEIPT_RETURN_STATEMENTS",
            (*storage.SHOPPING_RECEIPT_RETURN_STATEMENTS, "invalid SQL"),
        )
        with pytest.raises(StorageFailure):
            store.initialize(require_existing=True)
    assert path.read_bytes() == before
    store.initialize(require_existing=True)
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("PRAGMA user_version").fetchone() == (29,)
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        for table, rows in old.items():
            assert db.execute("SELECT * FROM " + table).fetchall() == rows
        assert db.execute("SELECT * FROM shopping_receipt_returns").fetchall() == []
    identity_at(root, installation)
    actor = Actor()
    actor.human = HumanIdentity("ha_admin", True, True, False)
    commands = InventoryCommands(store, actor, Clock(), SecureIdentifiers())
    for name in ("Oil", "Session flour"):
        with pytest.raises(Conflict, match="inventory_intake_corrected"):
            commands.return_posted_receipt(
                "legacy", posted[name][0], posted[name][1], REASON, posted[name][2]
            )
    early = posted["Rice"]
    late = posted["Pears"]
    first = commands.return_posted_receipt("early", early[0], early[1], REASON, early[2])
    movement_id = first.result.decode()["movement_id"]
    with store.read() as unit:
        originals = {
            receipt_id: unit.shopping.receipt("home", receipt_id).return_source
            for receipt_id in (early[1], pending, posted["Oil"][1])
        }
    with closing(sqlite3.connect(path, autocommit=True)) as db:
        db.row_factory = sqlite3.Row
        verify_shopping_records(db)
        db.execute("UPDATE shopping_receipt_returns SET movement_id='wrong'")
        with pytest.raises(StorageFailure, match="invalid_shopping_records"):
            verify_shopping_records(db)
        db.execute("UPDATE shopping_receipt_returns SET movement_id=?", (movement_id,))
        db.execute("UPDATE inventory_movements SET delta=-1 WHERE movement_id=?", (movement_id,))
        with pytest.raises(StorageFailure, match="invalid_shopping_records"):
            verify_shopping_records(db)
        db.execute(
            "UPDATE inventory_movements SET delta=-4000001 WHERE movement_id=?", (movement_id,)
        )
        for receipt_id in (pending, posted["Oil"][1]):
            db.execute("UPDATE shopping_receipt_returns SET receipt_id=?", (receipt_id,))
            db.execute(
                "UPDATE inventory_movements SET source_key=? WHERE movement_id=?",
                (originals[receipt_id], movement_id),
            )
            with pytest.raises(StorageFailure, match="invalid_shopping_records"):
                verify_shopping_records(db)
        db.execute("UPDATE shopping_receipt_returns SET receipt_id=?", (early[1],))
        db.execute(
            "UPDATE inventory_movements SET source_key=? WHERE movement_id=?",
            (originals[early[1]], movement_id),
        )
        verify_shopping_records(db)
    archive, target = tmp_path / "archive", tmp_path / "prepared"
    checkpoint = SQLiteSnapshots(store, archive, installation, Clock()).create("returned")
    later = commands.return_posted_receipt("later", late[0], late[1], REASON, late[2])
    SQLiteRestorations(store, archive, target, installation, Clock(), checkpoint).prepare("restore")
    assert SQLiteActivation(root, installation, Clock(), target).activate().state == "active"
    reopened = open_storage(root, "edge")
    try:
        recovery = replace(commands, transactions=reopened.database)
        assert (
            recovery.return_posted_receipt("early", early[0], early[1], REASON, early[2]) == first
        )
        archived = recovery.return_posted_receipt("later", late[0], late[1], REASON, late[2])
        assert archived.historical and archived.operation_id == later.operation_id
        assert archived.result == later.result
        detail = queries(recovery).physical_receipts(late[0], limit=25, cursor=None)
        assert detail.receipts[0].returned is None and detail.purchase.remaining == "0"
        current = recovery.return_posted_receipt("fresh", late[0], late[1], REASON, late[2])
        assert current.result.decode()["quantity"] == later.result.decode()["quantity"]
    finally:
        reopened.close()
