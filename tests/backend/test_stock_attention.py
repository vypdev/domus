"""Stock attention uses current authorized Pantry facts in both compositions."""

from dataclasses import replace
from types import SimpleNamespace

from test_inventory_catalog_http import INVENTORY, OUTSIDER, VIEWER, post, register
from test_recurrence_http import USER
from test_rewards_http import member_context
from test_shopping_http import command
from test_task_commands import counts
from test_task_runtime import api as api

from domus.application.inventory import InventoryCommands
from domus.domain.identity import (
    HumanIdentity,
    Member,
    MemberStatus,
    Permission,
    PermissionRule,
    Role,
)
from domus.domain.inventory import EffectKind
from domus.domain.task_material_values import MaterialQuantity
from domus.infrastructure.application_runtime import SecureIdentifiers, SystemClock

ROUTE = INVENTORY + "/stock-attention"
EMPTY = {"total": 0, "items": []}


def read(api, user=USER, **params):
    return api.client.get(ROUTE, headers=member_context(user), params=params)


def configure(api, product, key, minimum="2", target="4"):
    result = post(
        api,
        key,
        "configure-replenishment",
        product_id=product,
        minimum=minimum,
        target=target,
        expected_revision="0",
    )
    assert result.status_code == 200, result.text


def reserve(api, product):
    with api.store.read() as unit:
        reference = unit.inventory.product("home", product).reference_id
    task = api.client.post(
        "/api/v1/tasks/definitions",
        headers=api.headers("attention-task"),
        json={
            "title": "Prepare the filters",
            "expected_revision": 0,
            "materials": [{"reference_id": reference, "planned_quantity": "1"}],
        },
    )
    assert task.status_code == 200, task.text
    actor = SimpleNamespace(current=lambda: HumanIdentity(USER, True, True, False))
    commands = InventoryCommands(api.store, actor, SystemClock(), SecureIdentifiers())
    commands.commit_effect(
        "attention-reservation",
        EffectKind.RESERVATION,
        reference,
        MaterialQuantity("1"),
        occurrence_id=task.json()["result"]["occurrence_id"],
    )
    return reference


def test_stock_attention_respects_current_household_grants_and_actual_stock(api):
    api.user(USER, True)
    assert api.client.get(ROUTE).status_code == 422
    assert read(api, cursor="unsupported").status_code == 422
    assert read(api).json() == EMPTY
    product = register(api, "attention-product", "Paper filters", "piece")
    configure(api, product, "attention-policy")
    assert (
        post(api, "attention-intake", "intake", product_id=product, quantity="2").status_code == 200
    )
    assert read(api).json() == EMPTY

    reference = reserve(api, product)
    purchase = command(
        api, "attention-purchase", "purchase", product_id=product, name=None, quantity="4"
    )
    assert purchase.status_code == 200, purchase.text
    expected = {
        "total": 1,
        "items": [
            {
                "product_id": product,
                "name": "Paper filters",
                "base_unit": "piece",
                "available": "1",
                "minimum": "2",
            },
        ],
    }
    original = counts(api.store)
    assert read(api).json() == expected
    assert read(api).json() == expected
    assert counts(api.store) == original
    with api.store.read() as unit:
        assert unit.inventory.balance("home", reference) == 2_000_000
        assert unit.inventory.reserved("home", reference) == 1_000_000
        assert unit.shopping.outstanding("home", product) == 4_000_000

    with api.store.write() as unit:
        viewer = Member(
            "viewer",
            "home",
            VIEWER,
            Role.VIEWER,
            MemberStatus.ACTIVE,
            1,
            (PermissionRule(Permission.TASKS_READ, False),),
        )
        unit.members.save(viewer, 0)
    api.user(VIEWER)
    assert api.client.get("/api/v1/tasks/overview").status_code == 403
    assert read(api, VIEWER).json() == expected
    assert read(api).status_code == 403
    with api.store.write() as unit:
        unit.members.save(
            replace(
                viewer, exceptions=(PermissionRule(Permission.HOUSEHOLD_READ, False),), revision=2
            ),
            1,
        )
    denied = read(api, VIEWER)
    assert denied.status_code == 403 and not {"total", "items"} & denied.json().keys()
    api.user(OUTSIDER)
    assert read(api, OUTSIDER).status_code == 403

    api.user(USER, True)
    for key in ("reach-minimum", "exceed-minimum"):
        assert post(api, key, "intake", product_id=product, quantity="1").status_code == 200
        assert read(api).json() == EMPTY


def test_stock_attention_streams_exact_total_and_first_twenty_five_catalog_rows(api):
    api.user(USER, True)
    qualifying = {}
    for number in range(30):
        name = f"Stock product {number:02}"
        product = register(api, f"stock-product-{number}", name, "gram")
        if number % 10 == 0:
            continue
        configure(api, product, f"stock-policy-{number}", minimum="0.125", target="0.25")
        qualifying[product] = name

    response = read(api)
    assert response.status_code == 200, response.text
    summary = response.json()
    assert summary["total"] == 27
    assert summary["items"] == [
        {
            "product_id": product,
            "name": qualifying[product],
            "base_unit": "gram",
            "available": "0",
            "minimum": "0.125",
        }
        for product in sorted(qualifying)[:25]
    ]
