"""Exercise protected purchase, arrival and stock posting in both deployments."""

from dataclasses import replace

from test_inventory_catalog_http import INVENTORY, OUTSIDER, VIEWER, get, register
from test_recurrence_http import USER
from test_rewards_http import member_context
from test_task_runtime import api as api

from domus.domain.identity import Member, MemberStatus, Permission, PermissionRule, Role
from domus.domain.member_profiles import MemberPresentation

SHOPPER = "d" * 32
STOCKER = "e" * 32


def command(api, key, action, *, user=USER, csrf=True, **payload):
    headers = api.headers(key) | member_context(user)
    if not csrf:
        headers = {key: value for key, value in headers.items() if key.lower() != "x-csrf-token"}
    return api.client.post(
        INVENTORY + "/commands", json={"action": "shopping." + action, **payload}, headers=headers
    )


def view(api, path="", user=USER, **params):
    return api.client.get(
        INVENTORY + "/purchases" + path, headers=member_context(user), params=params
    )


def original(api, key, action, user=USER):
    return api.client.get(
        INVENTORY + "/requests/shopping." + action + "/" + key, headers=member_context(user)
    )


def test_exact_partial_shopping_and_independent_current_grants(api):
    with api.store.write() as unit:
        for member, user, permission in (
            ("shopper", SHOPPER, Permission.SHOPPING_MANAGE),
            ("stocker", STOCKER, Permission.INVENTORY_MANAGE),
        ):
            unit.members.save(
                Member(
                    member,
                    "home",
                    user,
                    Role.VIEWER,
                    MemberStatus.ACTIVE,
                    1,
                    (PermissionRule(permission, True),),
                ),
                0,
            )
            unit.presentations.save(MemberPresentation(member, "home", member.capitalize(), 2), 1)
        unit.members.save(Member("viewer", "home", VIEWER, Role.VIEWER, MemberStatus.ACTIVE, 1), 0)
    api.user(USER, True)
    product = register(api, "product", "Oil", "millilitre")
    fields = {"product_id": product, "name": None, "quantity": "6.000001"}
    assert view(api).json() == {"purchases": [], "next_cursor": None}
    api.user(SHOPPER)
    info = get(api, SHOPPER).json()
    assert info["may_shop"] and not info["may_manage"]
    assert command(api, "buy", "purchase", user=SHOPPER, csrf=False, **fields).status_code == 403
    assert (
        command(api, "buy", "purchase", user=SHOPPER, **(fields | {"name": "Both"})).json()["code"]
        == "invalid_shopping_item"
    )
    assert (
        command(api, "buy", "purchase", user=SHOPPER, **(fields | {"quantity": "0"})).json()["code"]
        == "invalid_material_quantity"
    )
    assert (
        command(
            api, "buy", "purchase", user=SHOPPER, **(fields | {"product_id": "foreign"})
        ).json()["code"]
        == "inventory_product_missing"
    )
    bought = command(api, "buy", "purchase", user=SHOPPER, **fields)
    assert bought.status_code == 200, bought.text
    purchase = bought.json()["result"]["purchase_id"]
    assert command(api, "buy", "purchase", user=SHOPPER, **fields).json() == bought.json()
    assert original(api, "buy", "purchase", SHOPPER).json() == bought.json()
    assert (
        command(api, "buy", "purchase", user=SHOPPER, **(fields | {"quantity": "6"})).json()["code"]
        == "idempotency_conflict"
    )
    assert (
        command(api, "other-buy", "purchase", user=SHOPPER, **fields).json()["code"]
        == "shopping_purchase_open"
    )
    arrivals = "/" + purchase + "/receipts"
    assert view(api, arrivals, SHOPPER).json()["receipts"] == []
    receive = {"purchase_id": purchase, "quantity": "4.000001", "expected_revision": "1"}
    assert (
        command(api, "arrival", "receive", user=SHOPPER, **(receive | {"quantity": "7"})).json()[
            "code"
        ]
        == "shopping_receipt_exceeds_purchase"
    )
    assert (
        command(
            api, "arrival", "receive", user=SHOPPER, **(receive | {"purchase_id": "foreign"})
        ).json()["code"]
        == "shopping_purchase_missing"
    )
    arrival = command(api, "arrival", "receive", user=SHOPPER, **receive)
    assert arrival.status_code == 200, arrival.text
    assert original(api, "arrival", "receive", SHOPPER).json() == arrival.json()
    receipt = arrival.json()["result"]["receipt_id"]
    post = {"purchase_id": purchase, "receipt_id": receipt}
    assert command(api, "post", "post-receipt", user=SHOPPER, **post).status_code == 403
    assert (
        command(api, "different-arrival", "receive", user=SHOPPER, **receive).json()["code"]
        == "revision_conflict"
    )
    row = view(api, user=SHOPPER).json()["purchases"][0]
    assert (row["purchased"], row["received"], row["remaining"], row["pending_stock"]) == (
        "6.000001",
        "4.000001",
        "2",
        "4.000001",
    )
    assert row["author_alias"] == "Shopper" and row["revision"] == "2"
    assert get(api, SHOPPER).json()["products"][0]["recorded"] == "0"
    api.user(STOCKER)
    assert command(api, "buy", "purchase", user=STOCKER, **fields).status_code == 403
    assert command(api, "arrival", "receive", user=STOCKER, **receive).status_code == 403
    assert (
        command(
            api, "post", "post-receipt", user=STOCKER, **(post | {"receipt_id": "foreign"})
        ).json()["code"]
        == "shopping_receipt_missing"
    )
    posted = command(api, "post", "post-receipt", user=STOCKER, **post)
    assert posted.status_code == 200, posted.text
    assert original(api, "post", "post-receipt", STOCKER).json() == posted.json()
    assert command(api, "post", "post-receipt", user=STOCKER, **post).json() == posted.json()
    assert (
        command(api, "double", "post-receipt", user=STOCKER, **post).json()["code"]
        == "shopping_receipt_posted"
    )
    api.user(VIEWER)
    assert not get(api, VIEWER).json()["may_shop"]
    assert get(api, VIEWER).json()["products"][0]["recorded"] == "4.000001"
    physical = view(api, arrivals, VIEWER).json()["receipts"][0]
    assert physical["author_alias"] == "Shopper"
    assert physical["movement_id"] == posted.json()["result"]["movement_id"]
    assert original(api, "post", "post-receipt", VIEWER).status_code == 403
    assert command(api, "post", "post-receipt", user=VIEWER, **post).status_code == 403
    api.user(OUTSIDER)
    assert view(api, user=OUTSIDER).status_code == 403
    api.user(SHOPPER)
    with api.store.write() as unit:
        member = unit.members.get("home", "shopper")
        unit.members.save(replace(member, exceptions=(), revision=2), 1)
    assert original(api, "buy", "purchase", SHOPPER).status_code == 403
    assert command(api, "buy", "purchase", user=SHOPPER, **fields).status_code == 403


def test_free_text_and_bounded_attributed_pages(api):
    api.user(USER, True)
    fields = {"product_id": None, "name": "Apples", "quantity": "2"}
    assert (
        command(api, "buy", "purchase", **(fields | {"quantity": "1.5"})).json()["code"]
        == "invalid_material_precision"
    )
    purchase = command(api, "buy", "purchase", **fields).json()["result"]["purchase_id"]
    for revision in (1, 2):
        receipt = command(
            api,
            f"arrive-{revision}",
            "receive",
            purchase_id=purchase,
            quantity="1",
            expected_revision=str(revision),
        ).json()["result"]["receipt_id"]
    assert (
        command(api, "post", "post-receipt", purchase_id=purchase, receipt_id=receipt).json()[
            "code"
        ]
        == "shopping_receipt_untracked"
    )
    assert get(api).json()["products"] == []
    assert view(api, "/foreign/receipts").status_code == 404
    first = view(api, f"/{purchase}/receipts", limit=1).json()
    assert (
        first["receipts"][0]["receipt_id"] == receipt
        and first["receipts"][0]["movement_id"] is None
    )
    assert (
        view(api, f"/{purchase}/receipts", limit=2, cursor=first["next_cursor"]).status_code == 422
    )
    assert view(api, limit=1, cursor=first["next_cursor"]).status_code == 422
    assert (
        len(
            view(api, f"/{purchase}/receipts", limit=1, cursor=first["next_cursor"]).json()[
                "receipts"
            ]
        )
        == 1
    )
    second = command(api, "second", "purchase", **fields).json()["result"]["purchase_id"]
    page = view(api, limit=1).json()
    assert page["purchases"][0]["purchase_id"] == second
    command(api, "newest", "purchase", **fields)
    old = view(api, limit=1, cursor=page["next_cursor"]).json()
    assert old["next_cursor"] is None
    item = old["purchases"][0]
    assert (item["purchase_id"], item["product_id"], item["remaining"], item["pending_stock"]) == (
        purchase,
        None,
        "0",
        "0",
    )
