"""Catalog permissions and exact intake through both protected production compositions."""

import pytest
from test_recurrence_http import USER
from test_rewards_http import member_context
from test_task_runtime import api as api

from domus.domain.identity import Member, MemberStatus, Role

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
        "products": [],
        "next_cursor": None,
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
    assert get(api).json()["products"] == [
        {
            **payload,
            "name": "Cleaning product",
            "base_unit": base_unit,
            "recorded": maximum,
            "reserved": "0",
            "available": maximum,
        }
    ]
