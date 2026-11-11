"""Catalog permissions and exact intake through both protected production compositions."""

import pytest
from test_recurrence_http import USER
from test_rewards_http import member_context
from test_task_runtime import api as api

from domus.domain.identity import Member, MemberStatus, Role
from domus.domain.member_profiles import MemberPresentation
from domus.infrastructure.application_runtime import SystemClock

INVENTORY = "/api/v1/inventory"
VIEWER = "b" * 32
OUTSIDER = "c" * 32


def post(api, key, action, *, user=USER, **payload):
    return api.client.post(
        INVENTORY + "/commands",
        json={"action": "inventory." + action, **payload},
        headers=api.headers(key) | member_context(user),
    )


def get(api, user=USER, **params):
    return api.client.get(INVENTORY, headers=member_context(user), params=params)


def register(api, key, name, unit):
    result = post(api, key, "register-product", name=name, base_unit=unit)
    assert result.status_code == 200, result.text
    return result.json()["result"]["product_id"]


def test_catalog_is_scoped_bounded_and_writes_require_current_grants(api):
    with api.store.write() as unit:
        unit.members.save(Member("viewer", "home", VIEWER, Role.VIEWER, MemberStatus.ACTIVE, 1), 0)
    api.user(USER, True)
    assert get(api).json() == {
        "location_id": "pantry",
        "may_manage": True,
        "may_shop": True,
        "may_request": True,
        "products": [],
        "next_cursor": None,
        "locations": [],
    }
    for quantity in ("1.25", "0.000001"):
        assert get(api, limit=quantity).status_code == 422
    ids = {
        register(api, "soap", "Soap", "millilitre"),
        register(api, "sponges", "Sponges", "piece"),
    }
    page = get(api, limit=1)
    assert page.status_code == 200, page.text
    first = page.json()
    assert len(first["products"]) == 1 and first["next_cursor"]
    second = get(api, limit=1, cursor=first["next_cursor"]).json()
    assert second["next_cursor"] is None and len(second["products"]) == 1
    assert {first["products"][0]["product_id"], second["products"][0]["product_id"]} == ids
    assert get(api, limit=2, cursor=first["next_cursor"]).json()["code"] == "invalid_task_cursor"
    api.user(VIEWER)
    viewer = get(api, VIEWER).json()
    assert viewer["may_manage"] is False and len(viewer["products"]) == 2
    assert get(api, VIEWER, limit=1, cursor=first["next_cursor"]).status_code == 422
    assert get(api).status_code == 403
    assert (
        post(
            api, "forged", "register-product", user=VIEWER, name="Tea", base_unit="gram"
        ).status_code
        == 403
    )
    assert (
        post(
            api, "forged", "intake", user=VIEWER, product_id=next(iter(ids)), quantity="1"
        ).status_code
        == 403
    )
    assert (
        api.client.get(
            INVENTORY + "/requests/inventory.register-product/soap", headers=member_context(VIEWER)
        ).status_code
        == 403
    )
    api.user(OUTSIDER)
    assert get(api, OUTSIDER).status_code == 403


@pytest.mark.parametrize(
    ("base_unit", "amount", "maximum"),
    [
        ("piece", "1", "999999999999"),
        ("gram", "0.000001", "999999999999.999999"),
        ("millilitre", "0.000001", "999999999999.999999"),
    ],
)
def test_exact_stock_capacity_rejects_partial_posting_and_forced_binding(
    api, base_unit, amount, maximum
):
    api.user(USER, True)
    product_id = register(api, "product", "Cleaning product", base_unit)
    payload = {"product_id": product_id}
    path = INVENTORY + "/requests/inventory.intake/intake"
    assert api.client.get(path, headers=member_context(USER)).status_code == 404
    assert (
        api.client.get(
            INVENTORY, params={"household_id": "other"}, headers=member_context(USER)
        ).status_code
        == 422
    )
    assert (
        post(
            api, "bad-location", "intake", **payload, quantity=amount, location_id="elsewhere"
        ).status_code
        == 422
    )
    assert (
        post(
            api, "change-unit", "intake", **payload, quantity=amount, base_unit="litre"
        ).status_code
        == 422
    )
    assert (
        post(api, "no-product", "intake", product_id="foreign", quantity=amount).json()["code"]
        == "inventory_product_missing"
    )
    for invalid in ("0", "-1", "0.0000001", "1000000000000"):
        assert post(api, "invalid", "intake", **payload, quantity=invalid).status_code == 422
    assert post(api, "invalid", "register-product", name=" ", base_unit="piece").status_code == 422
    assert (
        post(api, "invalid", "register-product", name="Oil", base_unit="litre").status_code == 422
    )
    if base_unit == "piece":
        assert (
            post(api, "fraction", "intake", **payload, quantity="0.1").json()["code"]
            == "invalid_material_precision"
        )
    accepted = post(api, "intake", "intake", **payload, quantity=maximum)
    assert accepted.status_code == 200, accepted.text
    receipt = accepted.json()
    assert receipt["result"] == {
        **payload,
        "movement_id": receipt["result"]["movement_id"],
        "base_unit": base_unit,
        "quantity": maximum,
    }
    assert post(api, "intake", "intake", **payload, quantity=maximum).json() == receipt
    assert api.client.get(path, headers=member_context(USER)).json() == receipt
    assert (
        post(api, "intake", "intake", **payload, quantity=amount).json()["code"]
        == "idempotency_conflict"
    )
    assert (
        post(api, "overflow", "intake", **payload, quantity=amount).json()["code"]
        == "inventory_stock_capacity"
    )
    products = get(api).json()["products"]
    with api.store.read() as unit:
        reference = unit.inventory.product("home", product_id).reference_id
    assert products == [
        {
            **payload,
            "name": "Cleaning product",
            "reference_id": reference,
            "base_unit": base_unit,
            "recorded": maximum,
            "reserved": "0",
            "available": maximum,
            "outstanding_purchase": "0",
            "shopping_needed": "0",
            "replenishment": {
                "source_id": product_id,
                "minimum": "0",
                "target": "0",
                "revision": "0",
                "needed": "0",
            },
        }
    ]


def test_replenishment_policy_uses_current_grants_and_exact_values(api):
    with api.store.write() as unit:
        unit.members.save(Member("viewer", "home", VIEWER, Role.VIEWER, MemberStatus.ACTIVE, 1), 0)
    api.user(USER, True)
    oil = register(api, "oil", "Oil", "millilitre")
    piece = register(api, "piece", "Boxes", "piece")
    action = "configure-replenishment"
    policy = {
        "product_id": oil,
        "minimum": "1.250002",
        "target": "2.500001",
        "expected_revision": "0",
    }
    assert post(api, "seed", "intake", product_id=oil, quantity="1.250001").status_code == 200
    for invalid, code in (
        ({"minimum": "3"}, "invalid_replenishment_bounds"),
        ({"product_id": piece}, "invalid_material_precision"),
        ({"product_id": "other-household-product"}, "inventory_product_missing"),
        ({"target": "999999999999.9999999"}, "invalid_request"),
        ({"target": "1000000000000"}, "invalid_request"),
        ({"expected_revision": "9223372036854775808"}, "invalid_revision"),
        ({"expected_revision": 0}, "invalid_request"),
        ({"household_id": "other"}, "invalid_request"),
    ):
        assert post(api, "policy", action, **(policy | invalid)).json()["code"] == code
    without_csrf = api.headers("policy") | member_context(USER)
    without_csrf = {
        name: value for name, value in without_csrf.items() if name.lower() != "x-csrf-token"
    }
    assert (
        api.client.post(
            INVENTORY + "/commands",
            json={"action": "inventory." + action, **policy},
            headers=without_csrf,
        ).status_code
        == 403
    )
    first = post(api, "policy", action, **policy)
    assert first.status_code == 200, first.text
    receipt = first.json()
    assert receipt["result"] == {
        "product_id": oil,
        "minimum": "1.250002",
        "target": "2.500001",
        "revision": "1",
    }
    original = INVENTORY + "/requests/inventory.configure-replenishment/policy"
    assert api.client.get(original, headers=member_context(USER)).json() == receipt
    assert post(api, "policy", action, **policy).json() == receipt
    assert post(api, "stale", action, **policy).json()["code"] == "revision_conflict"
    assert (
        post(api, "policy", action, **(policy | {"target": "5"})).json()["code"]
        == "idempotency_conflict"
    )
    api.user(VIEWER)
    products = {row["product_id"]: row for row in get(api, VIEWER).json()["products"]}
    assert products[oil]["replenishment"] == {
        "source_id": oil,
        "minimum": "1.250002",
        "target": "2.500001",
        "revision": "1",
        "needed": "1.25",
    }
    assert post(api, "policy", action, user=VIEWER, **policy).status_code == 403
    assert api.client.get(original, headers=member_context(VIEWER)).status_code == 403
    api.user(OUTSIDER)
    assert post(api, "policy", action, user=OUTSIDER, **policy).status_code == 403
    assert get(api, OUTSIDER).status_code == 403


def test_product_history_is_protected_and_pages_across_later_appends(api, monkeypatch):
    now = SystemClock().now()
    monkeypatch.setattr(SystemClock, "now", lambda _clock: now)
    with api.store.write() as unit:
        unit.members.save(Member("viewer", "home", VIEWER, Role.VIEWER, MemberStatus.ACTIVE, 1), 0)
    api.user(USER, True)
    product = register(api, "oil", "Oil", "millilitre")
    other = register(api, "tea", "Tea", "gram")
    path = f"{INVENTORY}/products/{product}/movements"

    def history(user=USER, **params):
        return api.client.get(path, headers=member_context(user), params=params)

    assert history().json()["movements"] == []
    with api.store.write() as unit:
        actor = unit.members.by_user("home", USER).member_id
        unit.presentations.save(MemberPresentation(actor, "home", "Kitchen lead", 2), 1)
    first = post(api, "intake", "intake", product_id=product, quantity="5.000001").json()["result"]
    adjustment = {"product_id": product, "quantity": "-0.000001", "reason": "Counted one less"}
    second = post(api, "adjust", "adjust", **adjustment).json()["result"]
    response = history(limit=1)
    assert response.status_code == 200, response.text
    page = response.json()
    assert page["product_name"] == "Oil" and page["base_unit"] == "millilitre"
    (movement,) = page["movements"]
    assert movement == {
        "movement_id": second["movement_id"],
        "quantity": "-0.000001",
        "kind": "adjustment",
        "member_id": actor,
        "author_alias": "Kitchen lead",
        "created_at": movement["created_at"],
        "reason": adjustment["reason"],
        "task_occurrence_id": None,
        "corrects": None,
        "corrected_by": None,
        "shopping_receipt": False,
        "return_of": None,
        "transfer": None,
    }
    cursor = page["next_cursor"]
    assert cursor
    for limit in (0, 101, 2):
        assert history(limit=limit, cursor=cursor).status_code == 422
    assert (
        api.client.get(
            f"{INVENTORY}/products/{other}/movements",
            headers=member_context(USER),
            params={"limit": 1, "cursor": cursor},
        ).json()["code"]
        == "invalid_task_cursor"
    )
    recent = post(api, "later", "adjust", **(adjustment | {"quantity": "1"})).json()["result"]
    older = history(limit=1, cursor=cursor).json()
    assert older["next_cursor"] is None
    assert older["movements"][0]["movement_id"] == first["movement_id"]
    assert older["movements"][0]["created_at"] == movement["created_at"]
    assert history().json()["movements"][0]["movement_id"] == recent["movement_id"]
    before = history().json()
    deleted = api.client.delete(path, headers=api.headers("delete") | member_context(USER))
    assert deleted.status_code == (403 if api.mode == "native" else 405)
    assert history().json() == before

    api.user(VIEWER)
    assert history(VIEWER).status_code == 200
    assert history(VIEWER, limit=1, cursor=cursor).status_code == 422
    assert post(api, "adjust", "adjust", user=VIEWER, **adjustment).status_code == 403
    assert (
        post(
            api,
            "correct",
            "correct-intake",
            user=VIEWER,
            product_id=product,
            movement_id=first["movement_id"],
            reason="Duplicate",
        ).status_code
        == 403
    )
    api.user(OUTSIDER)
    assert history(OUTSIDER).status_code == 403


def test_adjustment_and_reversal_wire_retain_linked_facts_and_receipts(api):
    api.user(USER, True)
    product = register(api, "soap", "Soap", "millilitre")
    other = register(api, "salt", "Salt", "piece")
    payload = {"product_id": product, "reason": "Inventory check"}
    path = f"{INVENTORY}/products/{product}/movements"
    assert (
        api.client.get(
            f"{INVENTORY}/products/unknown/movements", headers=member_context(USER)
        ).status_code
        == 404
    )
    assert post(api, "bad", "adjust", product_id=product, quantity="1").status_code == 422
    for quantity in ("-0", "0", "0.0000001", "1.2e3", 1):
        assert post(api, "bad", "adjust", **payload, quantity=quantity).status_code == 422
    assert (
        post(api, "bad", "adjust", **(payload | {"reason": " "}), quantity="1").json()["code"]
        == "invalid_inventory_reason"
    )
    assert post(api, "bad", "adjust", **payload, quantity="1", base_unit="gram").status_code == 422
    assert (
        post(api, "bad", "adjust", **(payload | {"product_id": other}), quantity="0.1").json()[
            "code"
        ]
        == "invalid_material_precision"
    )
    assert (
        post(api, "below", "adjust", **payload, quantity="-1").json()["code"]
        == "inventory_insufficient_stock"
    )
    added = post(api, "intake", "intake", product_id=product, quantity="1.250001").json()["result"]
    correct = payload | {"movement_id": added["movement_id"]}
    assert (
        post(api, "cross", "correct-intake", **(correct | {"product_id": other})).json()["code"]
        == "inventory_movement_missing"
    )
    assert (
        post(api, "missing", "correct-intake", **(correct | {"movement_id": "unknown"})).status_code
        == 404
    )
    assert post(api, "forged", "correct-intake", **correct, quantity="-1").status_code == 422

    first = post(api, "correct", "correct-intake", **correct).json()
    compensation = first["result"]
    assert compensation == {
        "product_id": product,
        "movement_id": compensation["movement_id"],
        "base_unit": "millilitre",
        "quantity": "-1.250001",
        "corrects": added["movement_id"],
    }
    assert post(api, "correct", "correct-intake", **correct).json() == first
    assert (
        api.client.get(
            f"{INVENTORY}/requests/inventory.correct-intake/correct", headers=member_context(USER)
        ).json()
        == first
    )
    assert (
        post(api, "correct", "correct-intake", **(correct | {"reason": "Changed"})).json()["code"]
        == "idempotency_conflict"
    )
    assert (
        post(api, "fresh", "correct-intake", **correct).json()["code"]
        == "inventory_intake_corrected"
    )
    assert (
        post(
            api,
            "forged",
            "correct-intake",
            **(correct | {"movement_id": compensation["movement_id"]}),
        ).json()["code"]
        == "inventory_correction_requires_intake"
    )
    correction, original = api.client.get(path, headers=member_context(USER)).json()["movements"]
    assert (
        correction["kind"] == "intake_correction"
        and correction["corrects"] == original["movement_id"]
    )
    assert original["kind"] == "intake" and original["quantity"] == "1.250001"
    assert original["corrected_by"] == correction["movement_id"]
    assert get(api).json()["products"][0]["recorded"] == "0"
    maximum = post(api, "maximum", "adjust", **payload, quantity="999999999999.999999")
    assert maximum.status_code == 200
    assert (
        post(api, "overflow", "adjust", **payload, quantity="0.000001").json()["code"]
        == "inventory_stock_capacity"
    )
