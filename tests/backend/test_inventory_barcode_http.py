"""Barcode admission uses both protected production HTTP compositions."""

import pytest
from test_inventory_catalog_http import INVENTORY, VIEWER, post, register
from test_recurrence_http import USER
from test_rewards_http import member_context
from test_task_runtime import api as api

from domus.domain.errors import StorageFailure
from domus.domain.identity import Member, MemberStatus, Role
from domus.infrastructure.sqlite_inventory import SQLiteInventory


def lookup(api, barcode="036000291452", *, user=USER, **params):
    return api.client.get(
        INVENTORY + "/barcode",
        params={"barcode": barcode, **params},
        headers=member_context(user),
    )


def test_reader_can_lookup_but_only_current_manager_can_change_or_recover(api):
    api.user(USER, True)
    product = register(api, "product", "Soap", "piece")
    result = lookup(api)
    assert result.status_code == 200, result.text
    assert result.json() == {
        "barcode": "00036000291452",
        "may_manage": True,
        "association": None,
        "product": None,
    }
    response = post(api, "link", "link-barcode", barcode="036000291452", product_id=product)
    assert response.status_code == 200, response.text
    receipt = response.json()
    association = receipt["result"]
    found = lookup(api, "0036000291452").json()
    assert found["association"] == association
    assert found["product"]["product_id"] == product and found["product"]["name"] == "Soap"
    with api.store.write() as unit:
        unit.members.save(Member("viewer", "home", VIEWER, Role.VIEWER, MemberStatus.ACTIVE, 1), 0)
    api.user(VIEWER)
    assert lookup(api, user=VIEWER).json() == {**found, "may_manage": False}
    for action in ("link-barcode", "remove-barcode"):
        payload = {"barcode": "036000291452", "product_id": product}
        if action == "remove-barcode":
            payload["association_id"] = association["association_id"]
        assert post(api, "forbidden", action, user=VIEWER, **payload).status_code == 403
        assert (
            api.client.get(
                INVENTORY + "/requests/inventory." + action + "/link",
                headers=member_context(VIEWER),
            ).status_code
            == 403
        )
    api.user(USER, True)
    assert (
        post(api, "replay", "link-barcode", barcode="036000291452", product_id=product).json()[
            "code"
        ]
        == "inventory_barcode_linked"
    )
    assert (
        api.client.get(
            INVENTORY + "/requests/inventory.link-barcode/link", headers=member_context(USER)
        ).json()
        == receipt
    )
    assert post(api, "remove", "remove-barcode", **association).status_code == 200
    assert lookup(api).json()["product"] is None
    assert (
        post(
            api, "missing", "link-barcode", barcode="036000291452", product_id="missing"
        ).status_code
        == 404
    )


@pytest.mark.parametrize(
    "barcode", ["96385075", "000000000", "036000291452 ", "９６３８５０７４", 36000291452]
)
def test_invalid_code_never_queries_or_writes_a_link(api, monkeypatch, barcode):
    api.user(USER, True)
    product = register(api, "product", "Soap", "piece")

    def unexpected(*_):
        raise AssertionError("An invalid barcode reached storage")

    monkeypatch.setattr(SQLiteInventory, "barcode", unexpected)
    if isinstance(barcode, str):
        assert lookup(api, barcode).status_code == 422
    assert (
        post(api, "invalid", "link-barcode", barcode=barcode, product_id=product).status_code == 422
    )


def test_lookup_unavailability_is_distinct_and_read_retry_retains_the_same_key(api, monkeypatch):
    api.user(USER, True)

    def fail(*_):
        raise StorageFailure("synthetic_barcode_storage")

    with monkeypatch.context() as patch:
        patch.setattr(SQLiteInventory, "barcode", fail)
        unavailable = lookup(api)
        assert unavailable.status_code == 500
        assert unavailable.json()["code"] == "internal_error"
    assert lookup(api).json()["product"] is None
    assert lookup(api, household_id="foreign").status_code == 422
    assert api.client.get(INVENTORY + "/barcode", headers=member_context(USER)).status_code == 422
