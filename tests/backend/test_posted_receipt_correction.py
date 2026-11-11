"""Qualify one linked correction across a posted receipt and Pantry stock."""

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
ACTION = CatalogAction.CORRECT_POSTED_RECEIPT
REASON = "Three units actually arrived"
BOTH = "f" * 32


def test_linked_correction_updates_both_histories_and_requires_both_grants(api):
    with api.store.write() as unit:
        for member, user, permissions in (
            ("shopper", SHOPPER, (Permission.SHOPPING_MANAGE,)),
            ("stocker", STOCKER, (Permission.INVENTORY_MANAGE,)),
            ("corrector", BOTH, (Permission.INVENTORY_MANAGE, Permission.SHOPPING_MANAGE)),
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
    product = register(api, "flour", "Flour", "gram")
    purchase = command(
        api, "buy", "purchase", product_id=product, name=None, quantity="6.000001"
    ).json()["result"]["purchase_id"]
    wrong = command(
        api, "mistake", "receive", purchase_id=purchase, quantity="4.000001", expected_revision="1"
    ).json()["result"]["receipt_id"]
    params = {
        "purchase_id": purchase,
        "receipt_id": wrong,
        "reason": REASON,
        "expected_revision": "4",
    }
    assert (
        command(
            api, "pending", "correct-posted-receipt", **(params | {"expected_revision": "2"})
        ).json()["code"]
        == "shopping_receipt_not_posted"
    )
    original_movement = command(
        api, "post-wrong", "post-receipt", purchase_id=purchase, receipt_id=wrong
    ).json()["result"]["movement_id"]
    assert (
        post(
            api,
            "unlinked",
            "correct-intake",
            product_id=product,
            movement_id=original_movement,
            reason=REASON,
        ).json()["code"]
        == "shopping_receipt_requires_linked_correction"
    )
    other = command(
        api, "other", "receive", purchase_id=purchase, quantity="0.5", expected_revision="3"
    ).json()["result"]["receipt_id"]
    loose = command(api, "loose", "purchase", product_id=None, name="Lemons", quantity="1").json()[
        "result"
    ]["purchase_id"]
    loose_receipt = command(
        api, "loose-arrival", "receive", purchase_id=loose, quantity="1", expected_revision="1"
    ).json()["result"]["receipt_id"]
    path = f"/{purchase}/receipts"
    before = view(api, path).json()
    before_stock = get(api).json()["products"]
    assert before_stock[0]["recorded"] == "4.000001"
    for user in (SHOPPER, STOCKER):
        api.user(user)
        assert (
            command(api, "denied", "correct-posted-receipt", user=user, **params).status_code == 403
        )
        assert original(api, "denied", "correct-posted-receipt", user).status_code == 403

    api.user(BOTH)
    assert (
        command(api, "csrf", "correct-posted-receipt", user=BOTH, csrf=False, **params).status_code
        == 403
    )
    for invalid, code in (
        ({"reason": " "}, "invalid_inventory_reason"),
        ({"purchase_id": "foreign"}, "shopping_purchase_missing"),
        ({"receipt_id": loose_receipt}, "shopping_receipt_missing"),
        ({"expected_revision": "3"}, "revision_conflict"),
        (
            {"purchase_id": loose, "receipt_id": loose_receipt, "expected_revision": "2"},
            "shopping_receipt_untracked",
        ),
    ):
        reply = command(api, "rejected", "correct-posted-receipt", user=BOTH, **(params | invalid))
        assert reply.json()["code"] == code, reply.text
        assert original(api, "rejected", "correct-posted-receipt", BOTH).status_code == 404
        assert view(api, path, BOTH).json() == before
        assert get(api, BOTH).json()["products"] == before_stock

    response = command(api, "correct", "correct-posted-receipt", user=BOTH, **params)
    assert response.status_code == 200, response.text
    saved = response.json()
    compensation = saved["result"]["movement_id"]
    assert saved["result"] == {
        "purchase_id": purchase,
        "receipt_id": wrong,
        "quantity": "4.000001",
        "movement_id": compensation,
        "revision": "5",
    }
    assert command(api, "correct", "correct-posted-receipt", user=BOTH, **params).json() == saved
    assert original(api, "correct", "correct-posted-receipt", BOTH).json() == saved
    assert (
        command(
            api, "correct", "correct-posted-receipt", user=BOTH, **(params | {"reason": "Changed"})
        ).json()["code"]
        == "idempotency_conflict"
    )
    assert (
        command(
            api,
            "duplicate",
            "correct-posted-receipt",
            user=BOTH,
            **(params | {"expected_revision": "5"}),
        ).json()["code"]
        == "inventory_intake_corrected"
    )
    detail = view(api, path, BOTH).json()
    assert detail["purchase"] == before["purchase"] | {
        "received": "0.5",
        "remaining": "5.500001",
        "revision": "5",
    }
    assert detail["receipts"][0] == before["receipts"][0]
    assert detail["receipts"][0]["receipt_id"] == other
    correction = detail["receipts"][1]["correction"]
    assert detail["receipts"][1] == before["receipts"][1] | {"correction": correction}
    assert correction == {
        "movement_id": compensation,
        "reason": REASON,
        "member_id": "corrector",
        "author_alias": "Corrector",
        "created_at": correction["created_at"],
        "legacy": False,
    }
    assert correction["created_at"].isdigit()
    current = get(api, BOTH).json()["products"][0]
    assert (current["recorded"], current["outstanding_purchase"]) == ("0", "6.000001")
    ledger = api.client.get(
        f"{INVENTORY}/products/{product}/movements", headers=member_context(BOTH)
    ).json()["movements"]
    assert [(entry["quantity"], entry["shopping_receipt"]) for entry in ledger] == [
        ("-4.000001", False),
        ("4.000001", True),
    ]
    assert ledger[0]["corrects"] == original_movement
    assert ledger[1]["corrected_by"] == compensation
    fixed = command(
        api,
        "fixed",
        "receive",
        user=BOTH,
        purchase_id=purchase,
        quantity="3",
        expected_revision="5",
    ).json()["result"]["receipt_id"]
    assert (
        command(
            api, "fixed-post", "post-receipt", user=BOTH, purchase_id=purchase, receipt_id=fixed
        ).status_code
        == 200
    )
    assert (
        command(
            api,
            "close",
            "cancel-balance",
            user=BOTH,
            purchase_id=purchase,
            reason=REASON,
            expected_revision="7",
        ).status_code
        == 200
    )
    assert (
        command(
            api,
            "closed",
            "correct-posted-receipt",
            user=BOTH,
            **(params | {"receipt_id": fixed, "expected_revision": "8"}),
        ).json()["code"]
        == "shopping_receipt_balance_cancelled"
    )
    assert get(api, BOTH).json()["products"][0]["recorded"] == "3"
    with api.store.write() as unit:
        member = unit.members.get("home", "corrector")
        unit.members.save(
            replace(
                member, exceptions=(PermissionRule(Permission.INVENTORY_MANAGE, True),), revision=2
            ),
            1,
        )
    assert original(api, "correct", "correct-posted-receipt", BOTH).status_code == 403
    assert command(api, "correct", "correct-posted-receipt", user=BOTH, **params).status_code == 403
    api.user(OUTSIDER)
    assert view(api, path, OUTSIDER).status_code == 403


def post_purchase(commands, product, amount="2"):
    purchase = commands.purchase("buy", product, None, M(amount)).result.decode()["purchase_id"]
    receipt = commands.receive_purchase("arrival", purchase, M(amount), 1).result.decode()[
        "receipt_id"
    ]
    posting = commands.post_purchase_receipt("post", purchase, receipt).result.decode()[
        "movement_id"
    ]
    return purchase, receipt, posting


def test_reservation_floor_and_write_failure_preserve_both_sides(tmp_path, monkeypatch):
    store, commands, product, reference = legacy(tmp_path, monkeypatch)
    purchase, receipt, posting = post_purchase(commands, product)
    commands.adjust("less", product, "-2.75", "Physical count")
    before = queries(commands).physical_receipts(purchase, limit=25, cursor=None)
    before_ledger = history(store, commands, product)
    with pytest.raises(Conflict, match="inventory_insufficient_stock"):
        commands.correct_posted_receipt("correct", purchase, receipt, REASON, 3)
    assert queries(commands).physical_receipts(purchase, limit=25, cursor=None) == before
    assert history(store, commands, product) == before_ledger
    commands.adjust("more", product, "0.5", "Physical count")
    before_ledger = history(store, commands, product)

    def fail(*_):
        raise StorageFailure("interrupted_receipt_link")

    with monkeypatch.context() as patch:
        patch.setattr(SQLiteShopping, "link_receipt_correction", fail)
        with pytest.raises(StorageFailure, match="interrupted_receipt_link"):
            commands.correct_posted_receipt("correct", purchase, receipt, REASON, 3)
    assert queries(commands).physical_receipts(purchase, limit=25, cursor=None) == before
    assert history(store, commands, product) == before_ledger
    with pytest.raises(NotFound, match="operation_missing"):
        commands.original(ACTION, "correct", commands.actor.current())
    commands.correct_posted_receipt("correct", purchase, receipt, REASON, 3)
    with store.read() as unit:
        assert unit.inventory.balance("home", reference) == 1_000_001
        assert unit.inventory.reserved("home", reference) == 875_000
        assert unit.inventory.correction_id("home", posting) is not None


@pytest.mark.parametrize("competitor", ["same-key", "correction", "purchase"])
def test_linked_correction_races_with_independent_writers(tmp_path, competitor):
    _, store, first = setup(tmp_path)
    product = register_storage(first)
    purchase, receipt, posting = post_purchase(first, product)
    second = replace(first, transactions=SQLiteDatabase(store.path, store.installation))
    key = "first" if competitor == "same-key" else "competing"

    def other():
        if competitor == "purchase":
            return second.purchase(key, product, None, M("1"))
        return second.correct_posted_receipt(key, purchase, receipt, REASON, 3)

    results = race(
        lambda: first.correct_posted_receipt("first", purchase, receipt, REASON, 3), other
    )
    accepted = next(result for result in results if isinstance(result, Receipt))
    if competitor == "same-key":
        assert results == (accepted, accepted)
    else:
        reason = (
            "shopping_purchase_open" if competitor == "purchase" else "inventory_intake_corrected"
        )
        assert results.count(reason) == 1
    with store.read() as unit:
        moved = unit.inventory.correction_id("home", posting)
        assert unit.shopping.receipt_correction("home", receipt) == moved
        if moved is None:
            assert unit.shopping.outstanding("home", product) == 1_000_000
        else:
            assert unit.shopping.outstanding("home", product) == 2_000_000
    if moved is None:
        assert report(first, product).recorded == "2"
        with pytest.raises(NotFound, match="operation_missing"):
            first.original(ACTION, "first", first.actor.current())
    else:
        assert report(first, product).recorded == "0"
        saved_key = "first" if isinstance(results[0], Receipt) else key
        assert first.original(ACTION, saved_key, first.actor.current()) == accepted


def test_existing_open_purchase_blocks_reopening(tmp_path):
    _, store, commands = setup(tmp_path)
    product = register_storage(commands)
    purchase, receipt, posting = post_purchase(commands, product)
    commands.purchase("second-purchase", product, None, M("1"))
    with pytest.raises(Conflict, match="shopping_purchase_open"):
        commands.correct_posted_receipt("correct", purchase, receipt, REASON, 3)
    assert report(commands, product).recorded == "2"
    with store.read() as unit:
        assert unit.inventory.correction_id("home", posting) is None
        assert unit.shopping.outstanding("home", product) == 1_000_000


def test_snapshot_checks_link_and_rejects_mismatched_receipt_quantity(tmp_path):
    _, store, commands = setup(tmp_path)
    product = register_storage(commands)
    purchase = commands.purchase("buy", product, None, M("3")).result.decode()["purchase_id"]
    receipt = commands.receive_purchase("arrival", purchase, M("1"), 1).result.decode()[
        "receipt_id"
    ]
    posting = commands.post_purchase_receipt("post", purchase, receipt).result.decode()[
        "movement_id"
    ]
    pending = commands.receive_purchase("pending", purchase, M("1"), 3).result.decode()[
        "receipt_id"
    ]
    with closing(sqlite3.connect(store.path, autocommit=True)) as db:
        db.row_factory = sqlite3.Row
        db.execute("UPDATE shopping_receipts SET quantity=2 WHERE receipt_id=?", (receipt,))
        with pytest.raises(StorageFailure, match="invalid_shopping_records"):
            commands.correct_posted_receipt("correct", purchase, receipt, REASON, 4)
        db.execute("UPDATE shopping_receipts SET quantity=1000000 WHERE receipt_id=?", (receipt,))
        correction = commands.correct_posted_receipt("correct", purchase, receipt, REASON, 4)
        movement = correction.result.decode()["movement_id"]
        verify_shopping_records(db)
        db.execute("UPDATE shopping_receipt_corrections SET receipt_id=?", (pending,))
        with pytest.raises(StorageFailure, match="invalid_shopping_records"):
            verify_shopping_records(db)
        db.execute("UPDATE shopping_receipt_corrections SET receipt_id=?", (receipt,))
        for invalid in (posting, "missing"):
            db.execute("UPDATE shopping_receipt_corrections SET movement_id=?", (invalid,))
            with pytest.raises(StorageFailure, match="invalid_shopping_records"):
                verify_shopping_records(db)
        db.execute("UPDATE shopping_receipt_corrections SET movement_id=?", (movement,))
        verify_shopping_records(db)


def test_schema_27_migration_legacy_history_and_activated_restore(tmp_path, monkeypatch):
    root = tmp_path / "owned"
    root.mkdir(mode=0o700)
    path = root / "domus.sqlite3"
    fixture = Path(__file__).parents[1] / "fixtures/sqlite/v27-posted-receipt-correction-source.sql"
    with closing(sqlite3.connect(path, autocommit=True)) as db:
        db.executescript(fixture.read_text())
        assert db.execute("PRAGMA user_version").fetchone() == (27,)
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
            "receipts",
        )
        old = {table: db.execute("SELECT * FROM " + table).fetchall() for table in tables}
        posted = {
            row[0]: row[1:]
            for row in db.execute(
                "SELECT p.name,p.purchase_id,r.receipt_id,p.revision,p.product_id,r.movement_id "
                "FROM shopping_purchases p JOIN shopping_receipts r "
                "USING(household_id,purchase_id) "
                "WHERE r.movement_id IS NOT NULL"
            )
        }
        assert old["shopping_receipt_voids"] and old["shopping_cancellations"]
        db.row_factory = sqlite3.Row
        verify_shopping_records(db, version=27)
    path.chmod(0o600)
    store = SQLiteDatabase(path, installation)
    before = path.read_bytes()
    with monkeypatch.context() as patch:
        patch.setattr(
            storage,
            "SHOPPING_RECEIPT_CORRECTION_STATEMENTS",
            (*storage.SHOPPING_RECEIPT_CORRECTION_STATEMENTS, "invalid SQL"),
        )
        with pytest.raises(StorageFailure):
            store.initialize(require_existing=True)
    assert path.read_bytes() == before
    store.initialize(require_existing=True)
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("PRAGMA user_version").fetchone() == (31,)
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        for table, rows in old.items():
            actual = db.execute("SELECT * FROM " + table).fetchall()
            if table == "inventory_movements":
                rows = [(*row, None) for row in rows]
            assert actual == rows
        assert db.execute("SELECT * FROM shopping_receipt_corrections").fetchall() == []
    identity_at(root, installation)
    actor = Actor()
    actor.human = HumanIdentity("ha_admin", True, True, False)
    commands = InventoryCommands(store, actor, Clock(), SecureIdentifiers())
    oil, old_receipt, old_revision, oil_product, oil_movement = posted["Oil"]
    legacy_operation = commands.original(
        CatalogAction.CORRECT_INTAKE, "legacy-posted-reversal", actor.current()
    )
    assert (
        commands.correct_intake(
            "legacy-posted-reversal", oil_product, oil_movement, "Legacy inventory reversal"
        )
        == legacy_operation
    )
    oil_history = queries(commands).physical_receipts(oil, limit=25, cursor=None)
    historical = next(entry for entry in oil_history.receipts if entry.receipt_id == old_receipt)
    assert historical.correction is not None and historical.correction.legacy
    assert historical.correction.movement_id == legacy_operation.result.decode()["movement_id"]
    with pytest.raises(Conflict, match="inventory_intake_corrected"):
        commands.correct_posted_receipt("duplicate-legacy", oil, old_receipt, REASON, old_revision)
    assert queries(commands).physical_receipts(oil, limit=25, cursor=None) == oil_history

    early = posted["Session flour"][:3]
    late = posted["Pears"][:3]
    first = commands.correct_posted_receipt("early", early[0], early[1], REASON, early[2])
    archive, target = tmp_path / "archive", tmp_path / "prepared"
    checkpoint = SQLiteSnapshots(store, archive, installation, Clock()).create("posted")
    later = commands.correct_posted_receipt("later", late[0], late[1], REASON, late[2])
    SQLiteRestorations(store, archive, target, installation, Clock(), checkpoint).prepare("restore")
    assert SQLiteActivation(root, installation, Clock(), target).activate().state == "active"
    reopened = open_storage(root, "edge")
    try:
        recovery = replace(commands, transactions=reopened.database)
        assert (
            recovery.correct_posted_receipt("early", early[0], early[1], REASON, early[2]) == first
        )
        archived = recovery.correct_posted_receipt("later", late[0], late[1], REASON, late[2])
        assert archived.historical and archived.operation_id == later.operation_id
        assert archived.result == later.result
        detail = queries(recovery).physical_receipts(late[0], limit=25, cursor=None)
        assert detail.receipts[0].correction is None and detail.purchase.remaining == "0"
        current = recovery.correct_posted_receipt("fresh", late[0], late[1], REASON, late[2])
        assert current.result.decode()["quantity"] == later.result.decode()["quantity"]
    finally:
        reopened.close()
