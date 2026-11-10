"""Exercise grouped recording, individual receipts and durable recovery."""

import sqlite3
from contextlib import closing
from dataclasses import replace
from pathlib import Path

import pytest
from test_activation_compatibility import identity_at
from test_household_commands import Actor, Clock
from test_inventory_catalog_http import INVENTORY, OUTSIDER, VIEWER, register
from test_inventory_catalog_storage import register as register_stock
from test_inventory_catalog_storage import setup
from test_recurrence_http import USER
from test_rewards_http import member_context
from test_rewards_storage import race
from test_shared_shopping import queries
from test_shopping_http import command, original
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
from domus.domain.shopping import MAX_SESSION_ITEMS, SessionSelection
from domus.domain.storage import Installation, Receipt
from domus.domain.task_material_values import MaterialQuantity
from domus.infrastructure import sqlite as storage
from domus.infrastructure.application_runtime import SecureIdentifiers
from domus.infrastructure.owned_storage import open_storage
from domus.infrastructure.sqlite import SQLiteDatabase
from domus.infrastructure.sqlite_activation import SQLiteActivation
from domus.infrastructure.sqlite_restoration import SQLiteRestorations
from domus.infrastructure.sqlite_shopping import verify_shopping_sessions
from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots

M = MaterialQuantity
ACTION = CatalogAction.RECORD_SESSION
ROUTE = INVENTORY + "/purchase-sessions"


def read(api, path="", user=USER, **params):
    return api.client.get(ROUTE + path, headers=member_context(user), params=params)


def selected(*, product=None, extra=None, quantity="1"):
    return {"product_id": product, "extra_id": extra, "quantity": quantity}


def test_protected_grouping_and_independent_receipts(api):
    with api.store.write() as unit:
        unit.members.save(Member("viewer", "home", VIEWER, Role.VIEWER, MemberStatus.ACTIVE, 1), 0)
    api.user(USER, True)
    with api.store.write() as unit:
        member = unit.members.by_user("home", USER)
        unit.presentations.save(MemberPresentation(member.member_id, "home", "Shopper", 2), 1)
    oil = register(api, "oil", "Oil", "millilitre")

    def extra(key, *, product=None, name=None):
        response = command(api, key, "add-extra", product_id=product, name=name, quantity="1")
        assert response.status_code == 200, response.text
        return response.json()["result"]["extra_id"]

    tracked_extra = extra("tracked-extra", product=oil)
    free = extra("free", name="Oil")
    cleared = extra("cleared", name="Spare")
    assert command(api, "clear", "clear-extra", extra_id=cleared).status_code == 200
    assert read(api).json() == {"sessions": [], "next_cursor": None}

    tracked, untracked = (
        selected(product=oil, quantity="6.000001"),
        selected(extra=free, quantity="3"),
    )
    for items, code in (
        ([tracked, tracked], "invalid_shopping_session"),
        ([tracked, selected()], "invalid_shopping_item"),
        ([tracked, selected(product=oil, extra=free)], "invalid_shopping_item"),
        ([untracked, selected(product="foreign")], "inventory_product_missing"),
        ([tracked, selected(extra="foreign")], "shopping_extra_missing"),
        ([tracked, selected(extra=tracked_extra)], "shopping_extra_missing"),
        ([tracked, selected(extra=cleared)], "shopping_extra_cleared"),
        ([tracked, selected(extra=free, quantity="1.5")], "invalid_material_precision"),
        ([tracked, selected(extra=free, quantity="0")], "invalid_material_quantity"),
    ):
        reply = command(api, "rejected", "record-session", items=items)
        assert reply.json()["code"] == code, reply.text
        assert original(api, "rejected", "record-session").status_code == 404
    assert (
        api.client.get(INVENTORY + "/purchases", headers=member_context(USER)).json()["purchases"]
        == []
    )
    assert (
        command(api, "csrf", "record-session", csrf=False, items=[tracked, untracked]).status_code
        == 403
    )
    for items in ([tracked], [tracked] * (MAX_SESSION_ITEMS + 1)):
        assert command(api, "limit", "record-session", items=items).status_code == 422

    accepted = command(api, "trip", "record-session", items=[tracked, untracked])
    assert accepted.status_code == 200, accepted.text
    record = accepted.json()
    session = record["result"]["session_id"]
    bought, loose = record["result"]["purchase_ids"]
    assert command(api, "trip", "record-session", items=[tracked, untracked]).json() == record
    assert original(api, "trip", "record-session").json() == record
    assert (
        command(api, "trip", "record-session", items=[untracked, tracked]).json()["code"]
        == "idempotency_conflict"
    )
    assert (
        command(api, "other", "record-session", items=[untracked, tracked]).json()["code"]
        == "shopping_purchase_open"
    )
    assert read(api, "/missing").status_code == 404
    assert read(api, "/" + session, cursor="foreign").status_code == 422
    assert read(api, limit=0).status_code == 422

    detail = read(api, "/" + session).json()
    assert detail["session"]["author_alias"] == "Shopper"
    first, second = detail["items"]
    assert first["purchase_id"] == bought and second["purchase_id"] == loose
    assert first["product_id"] == oil and second["product_id"] is None
    assert first["name"] == second["name"] == "Oil"
    assert first["purchased"] == "6.000001" and second["purchased"] == "3"
    arrival = command(
        api, "arrival", "receive", purchase_id=bought, quantity="4.000001", expected_revision="1"
    )
    assert arrival.status_code == 200, arrival.text
    assert (
        command(
            api, "loose", "receive", purchase_id=loose, quantity="3", expected_revision="1"
        ).status_code
        == 200
    )
    current, complete = read(api, "/" + session).json()["items"]
    assert (
        current["purchased"],
        current["received"],
        current["remaining"],
        current["pending_stock"],
    ) == (
        "6.000001",
        "4.000001",
        "2",
        "4.000001",
    )
    assert (complete["received"], complete["remaining"], complete["pending_stock"]) == (
        "3",
        "0",
        "0",
    )
    posted = command(
        api,
        "post",
        "post-receipt",
        purchase_id=bought,
        receipt_id=arrival.json()["result"]["receipt_id"],
    )
    assert posted.status_code == 200, posted.text
    assert read(api, "/" + session).json()["items"][0]["pending_stock"] == "0"
    assert (
        command(
            api,
            "later",
            "record-session",
            items=[untracked, selected(extra=extra("new", name="Pears"))],
        ).status_code
        == 200
    )
    page = read(api, limit=1).json()
    assert page["next_cursor"] and page["sessions"][0]["session_id"] != session
    assert read(api, limit=1, cursor=page["next_cursor"]).json()["sessions"] == [detail["session"]]
    api.user(VIEWER)
    assert read(api, "/" + session, VIEWER).status_code == 200
    assert read(api, user=VIEWER, limit=1, cursor=page["next_cursor"]).status_code == 422
    assert (
        command(
            api, "denied", "record-session", user=VIEWER, items=[tracked, untracked]
        ).status_code
        == 403
    )
    assert original(api, "trip", "record-session", VIEWER).status_code == 403
    api.user(OUTSIDER)
    assert read(api, user=OUTSIDER).status_code == 403


def test_session_recovery_requires_the_actors_current_shopping_grant(api):
    shopper = "d" * 32
    with api.store.write() as unit:
        unit.members.save(
            Member(
                "shopper",
                "home",
                shopper,
                Role.VIEWER,
                MemberStatus.ACTIVE,
                1,
                (PermissionRule(Permission.SHOPPING_MANAGE, True),),
            ),
            0,
        )
    api.user(USER, True)
    extras = [
        command(api, name, "add-extra", product_id=None, name=name, quantity="1").json()["result"][
            "extra_id"
        ]
        for name in ("Lemons", "Bread")
    ]
    api.user(shopper)
    reply = command(
        api,
        "trip",
        "record-session",
        user=shopper,
        items=[selected(extra=extra) for extra in extras],
    )
    assert reply.status_code == 200, reply.text
    assert original(api, "trip", "record-session", shopper).json() == reply.json()
    with api.store.write() as unit:
        member = unit.members.get("home", "shopper")
        unit.members.save(replace(member, exceptions=(), revision=2), 1)
    assert original(api, "trip", "record-session", shopper).status_code == 403
    assert (
        read(api, user=shopper).json()["sessions"][0]["session_id"]
        == reply.json()["result"]["session_id"]
    )


def add_free(commands, key, name):
    return commands.add_extra(key, None, name, M("1")).result.decode()["extra_id"]


@pytest.mark.parametrize("competitor", ["same-key", "session", "individual"])
def test_session_races_and_retry_use_one_transaction(tmp_path, competitor):
    _, store, commands = setup(tmp_path)
    product = register_stock(commands)
    loose = add_free(commands, "free", "Lemons")
    items = (SessionSelection(None, loose, M("2")), SessionSelection(product, None, M("6")))
    other = replace(commands, transactions=SQLiteDatabase(store.path, store.installation))
    key = "same" if competitor == "same-key" else "other"

    def second():
        if competitor == "individual":
            return other.purchase(key, product, None, M("6"))
        return other.record_purchase_session(key, items)

    results = race(lambda: commands.record_purchase_session("same", items), second)
    if competitor == "same-key":
        assert isinstance(results[0], Receipt) and results[0] == results[1]
    else:
        assert results.count("shopping_purchase_open") == 1
    accepted = next(result for result in results if isinstance(result, Receipt))
    result = accepted.result.decode()
    sessions = queries(commands).purchase_sessions(limit=25, cursor=None).sessions
    if "session_id" in result:
        saved_key = "same" if isinstance(results[0], Receipt) else key
        assert commands.original(ACTION, saved_key, commands.actor.current()) == accepted
        assert commands.record_purchase_session(saved_key, items) == accepted
        assert [session.session_id for session in sessions] == [result["session_id"]]
        assert len(queries(commands).purchases(limit=25, cursor=None).purchases) == 2
    else:
        assert sessions == ()
        assert len(queries(commands).purchases(limit=25, cursor=None).purchases) == 1
        with pytest.raises(NotFound, match="operation_missing"):
            commands.original(ACTION, "same", commands.actor.current())

    for invalid in (items[:1], items * MAX_SESSION_ITEMS):
        with pytest.raises(InvalidInput, match="invalid_shopping_session"):
            commands.record_purchase_session("invalid", invalid)


def test_schema_24_upgrade_and_restore_of_sessions_and_original_receipts(tmp_path, monkeypatch):
    root = tmp_path / "owned"
    root.mkdir(mode=0o700)
    path = root / "domus.sqlite3"
    fixture = Path(__file__).parents[1] / "fixtures/sqlite/v24-purchase-session-source.sql"
    with closing(sqlite3.connect(path, autocommit=True)) as db:
        db.executescript(fixture.read_text())
        assert db.execute("PRAGMA user_version").fetchone() == (24,)
        installation = Installation(
            *db.execute("SELECT instance_id,channel FROM installation").fetchone()
        )
        tables = (
            "inventory_movements",
            "inventory_effects",
            "inventory_replenishment",
            "shopping_purchases",
            "shopping_receipts",
            "shopping_extras",
            "receipts",
        )
        existing = {table: db.execute("SELECT * FROM " + table).fetchall() for table in tables}
        assert {row[-1] is None for row in existing["shopping_receipts"]} == {True, False}
        assert {row[-1] is None for row in existing["shopping_extras"]} == {True, False}
    path.chmod(0o600)
    store = SQLiteDatabase(path, installation)
    baseline = path.read_bytes()
    with monkeypatch.context() as patch:
        patch.setattr(
            storage,
            "SHOPPING_SESSION_STATEMENTS",
            (*storage.SHOPPING_SESSION_STATEMENTS, "invalid SQL"),
        )
        with pytest.raises(StorageFailure):
            store.initialize(require_existing=True)
    assert path.read_bytes() == baseline
    store.initialize(require_existing=True)
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("PRAGMA user_version").fetchone() == (26,)
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        for table, rows in existing.items():
            expected = [(*row, 0) for row in rows] if table == "shopping_purchases" else rows
            assert db.execute("SELECT * FROM " + table).fetchall() == expected
    identity_at(root, installation)
    actor = Actor()
    actor.human = HumanIdentity("ha_admin", True, True, False)
    commands = InventoryCommands(store, actor, Clock(), SecureIdentifiers())
    items = tuple(
        SessionSelection(None, add_free(commands, key, name), M("2"))
        for key, name in (("fruit", "Fruit"), ("bread", "Bread"))
    )
    committed = commands.record_purchase_session("first", items)
    archive, target = tmp_path / "archive", tmp_path / "prepared"
    checkpoint = SQLiteSnapshots(store, archive, installation, Clock()).create("sessions")
    later = commands.record_purchase_session("later", items)
    SQLiteRestorations(store, archive, target, installation, Clock(), checkpoint).prepare("restore")
    assert SQLiteActivation(root, installation, Clock(), target).activate().state == "active"
    reopened = open_storage(root, "edge")
    try:
        recovery = replace(commands, transactions=reopened.database)
        original_id = committed.result.decode()["session_id"]
        assert recovery.record_purchase_session("first", items) == committed
        historical = recovery.record_purchase_session("later", items)
        assert historical.historical and historical.operation_id == later.operation_id
        assert historical.result == later.result
        assert (
            queries(recovery).purchase_sessions(limit=25, cursor=None).sessions[0].session_id
            == original_id
        )
        with pytest.raises(NotFound, match="shopping_session_missing"):
            queries(recovery).purchase_session(later.result.decode()["session_id"])
    finally:
        reopened.close()


@pytest.mark.parametrize(
    "damage",
    [
        "DELETE FROM shopping_session_items WHERE ordinal=1",
        "UPDATE shopping_sessions SET created_at=created_at+1",
    ],
)
def test_snapshot_rejects_invalid_session_groups(tmp_path, damage):
    _, store, commands = setup(tmp_path)
    items = tuple(
        SessionSelection(None, add_free(commands, key, name), M("1"))
        for key, name in (("a", "Apples"), ("b", "Bread"))
    )
    commands.record_purchase_session("session", items)
    with closing(sqlite3.connect(store.path, autocommit=True)) as db:
        db.row_factory = sqlite3.Row
        verify_shopping_sessions(db)
        db.execute(damage)
        with pytest.raises(StorageFailure, match="invalid_shopping_records"):
            verify_shopping_sessions(db)
