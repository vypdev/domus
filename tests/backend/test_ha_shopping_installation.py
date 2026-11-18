"""Qualify the complete scoped Home Assistant shopping snapshot."""

import json
import re
import sqlite3
from contextlib import closing
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_ha_app_launcher import launch as launch
from test_ha_calendar_installation import (
    ORIGIN,
    PUBLIC,
    SUPERVISOR,
    WINDOW,
    bearer,
    digest,
    header,
    runtime,
)
from test_ha_deadline_installation import PRIVATE, deadline_bearer
from test_ha_stock_installation import stock_bearer
from test_inventory_catalog_http import post, register
from test_recurrence_http import USER
from test_shared_shopping import attention
from test_shopping_http import command
from test_stock_attention import configure, reserve
from test_task_commands import fixture
from test_task_runtime import api as api

from domus.application.shopping_list import HA_SHOPPING_ITEM_LIMIT
from domus.composition import ha_app, ingress, server
from domus.domain.errors import InvalidInput
from domus.domain.inventory import BaseUnit
from domus.domain.shopping_needs import ShoppingExtra
from domus.domain.storage import Installation
from domus.entrypoints.ha_calendar_http import CALENDAR_PATH
from domus.entrypoints.ha_deadline_http import DEADLINE_PATH
from domus.entrypoints.ha_shopping_http import SHOPPING_DIGEST_ENV, SHOPPING_PATH
from domus.entrypoints.ha_stock_http import STOCK_PATH


def shopping_bearer(installation, seed="a"):
    return f"{installation.instance_id}.{installation.channel}.shopping.{seed * 64}"


def stored_facts(store):
    with closing(sqlite3.connect(f"{store.path.as_uri()}?mode=ro", uri=True)) as connection:
        return tuple(connection.iterdump())


def test_scoped_list_matches_current_outstanding_rows_and_preserves_identities(api):
    api.user(USER, True)
    installation = api.store.installation
    purpose = shopping_bearer(installation)
    native = api.mode == "native"
    service = runtime(
        native, installation, api.store.path, None, shopping_fingerprint=digest(purpose)
    )
    client = TestClient(service.app, base_url=PRIVATE if native else PUBLIC)
    headers = header(purpose)
    try:
        assert client.get(SHOPPING_PATH, headers=headers).json() == {"items": []}
        product = register(api, "shared-product", "Tea filters", "piece")
        configure(api, product, "shared-policy")
        assert (
            post(api, "shared-stock", "intake", product_id=product, quantity="2").status_code == 200
        )
        reserve(api, product)
        assert command(
            api, "shared-buy", "purchase", product_id=product, name=None, quantity="1"
        ).is_success
        assert command(
            api, "tracked-extra", "add-extra", product_id=product, name=None, quantity="1"
        ).is_success
        assert command(
            api, "shared-extra", "add-extra", product_id=None, name="Tea filters", quantity="1"
        ).is_success

        before = stored_facts(api.store)
        response = client.get(SHOPPING_PATH, headers=headers)
        assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
        published = response.json()["items"]
        assert client.get(SHOPPING_PATH, headers=headers).json()["items"] == published
        assert stored_facts(api.store) == before
        assert [item["name"] for item in published] == ["Tea filters", "Tea filters"]
        assert [item["quantity"] for item in published] == ["3", "1"]
        authoritative = attention(api).json()["items"]
        assert [(item["name"], item["quantity"], item["unit"]) for item in published] == [
            (item["name"], item["total"], item["base_unit"]) for item in authoritative
        ]
        assert all(set(item) == {"name", "quantity", "uid", "unit"} for item in published)
        identities = [item["uid"] for item in published]
        assert all(re.fullmatch("[0-9a-f]{64}", uid) for uid in identities)
        assert len(set(identities)) == 2
        assert product not in response.text

        assert post(api, "shared-use", "intake", product_id=product, quantity="1").is_success
        updated = client.get(SHOPPING_PATH, headers=headers).json()["items"]
        # Available units now equal the minimum, so only the two manual extras remain.
        assert [item["uid"] for item in updated] == identities
        assert [item["quantity"] for item in updated] == ["1", "1"]
    finally:
        service.close()


@pytest.mark.parametrize("native", [False, True], ids=["standalone", "ingress"])
def test_shopping_grant_is_separate_opt_in_and_revocable(tmp_path, native):
    _, store, _, _ = fixture(tmp_path)
    installation = store.installation
    calendar, deadlines, stock = (
        bearer(installation),
        deadline_bearer(installation),
        stock_bearer(installation),
    )
    shopping, rotated = shopping_bearer(installation), shopping_bearer(installation, "b")
    for fingerprint in (None, digest(shopping), digest(rotated)):
        service = runtime(
            native,
            installation,
            store.path,
            digest(calendar),
            deadline_fingerprint=digest(deadlines),
            stock_fingerprint=digest(stock),
            shopping_fingerprint=fingerprint,
        )
        client = TestClient(service.app, base_url=PRIVATE if native else PUBLIC)
        try:
            assert client.get(CALENDAR_PATH, params=WINDOW, headers=header(calendar)).is_success
            assert client.get(DEADLINE_PATH, headers=header(deadlines)).is_success
            assert client.get(STOCK_PATH, headers=header(stock)).is_success
            assert (
                client.get(CALENDAR_PATH, params=WINDOW, headers=header(shopping)).status_code
                == 401
            )
            assert client.get(DEADLINE_PATH, headers=header(shopping)).status_code == 401
            assert client.get(STOCK_PATH, headers=header(shopping)).status_code == 401
            response = client.get(SHOPPING_PATH, headers=header(shopping))
            if fingerprint is None:
                assert response.status_code == 404
                continue
            if fingerprint == digest(rotated):
                assert response.status_code == 401
                assert client.get(SHOPPING_PATH, headers=header(rotated)).json() == {"items": []}
                continue
            assert response.status_code == 200 and response.json() == {"items": []}
            for wrong in (
                rotated,
                calendar,
                deadlines,
                stock,
                shopping.replace(installation.instance_id, str(uuid4())),
                shopping.replace(".edge.", ".stable."),
            ):
                denied = client.get(SHOPPING_PATH, headers=header(wrong))
                assert denied.status_code == 401
                assert denied.json() == {"error": "invalid_shopping_credential"}
            assert client.get(SHOPPING_PATH).status_code == 401
            assert client.post(SHOPPING_PATH, headers=header(shopping)).status_code == 405
            assert (
                client.get(
                    SHOPPING_PATH, params={"household": "other"}, headers=header(shopping)
                ).status_code
                == 422
            )
            headers = {**header(shopping), **{f"x-extra-{index}": "x" for index in range(33)}}
            assert client.get(SHOPPING_PATH, headers=headers).status_code == 422
            if native:
                forbidden = TestClient(service.app, base_url="http://native:8099")
            else:
                forbidden = TestClient(
                    service.app, base_url="http://domus.example", client=("192.0.2.1", 80)
                )
            assert not forbidden.get(SHOPPING_PATH, headers=header(shopping)).is_success
        finally:
            service.close()


def test_shopping_snapshot_has_an_exact_capacity_and_never_serves_a_partial_list(tmp_path):
    _, store, _, _ = fixture(tmp_path)
    installation = store.installation
    shopping = shopping_bearer(installation)
    with store.write() as unit:
        member = unit.members.by_user("home", "ha_admin")
        assert member is not None
        for index in range(HA_SHOPPING_ITEM_LIMIT):
            unit.shopping.add_extra(
                "home",
                ShoppingExtra(
                    f"shopping-fixture-{index}",
                    None,
                    f"Fixture {index}",
                    BaseUnit.PIECE,
                    1_000_000,
                    member.member_id,
                    index + 1,
                ),
            )
    service = runtime(True, installation, store.path, None, shopping_fingerprint=digest(shopping))
    try:
        client = TestClient(service.app, base_url=PRIVATE)
        response = client.get(SHOPPING_PATH, headers=header(shopping))
        assert response.status_code == 200
        rows = response.json()["items"]
        assert len(rows) == HA_SHOPPING_ITEM_LIMIT == 1000
        assert [row["name"] for row in rows] == [f"Fixture {i}" for i in range(1000)]
        assert len({row["uid"] for row in rows}) == 1000
        with store.write() as unit:
            unit.shopping.add_extra(
                "home",
                ShoppingExtra(
                    "shopping-extra-overflow",
                    None,
                    "Overflow",
                    BaseUnit.PIECE,
                    1_000_000,
                    member.member_id,
                    1001,
                ),
            )
        response = client.get(SHOPPING_PATH, headers=header(shopping))
        assert response.status_code == 503
        assert response.json() == {"error": "shopping_list_unavailable"}
    finally:
        service.close()


def test_shopping_requires_persistent_secure_origin_and_valid_digest(tmp_path):
    instance = str(uuid4())
    with pytest.raises(InvalidInput, match="ha_shopping_requires_persistent_secure_origin"):
        server.create_runtime(
            "https://ha.example", PUBLIC, instance, "edge", ha_shopping_digest="a" * 64
        )
    with pytest.raises(InvalidInput, match="invalid_ha_shopping_digest"):
        runtime(
            False,
            Installation(instance, "edge"),
            tmp_path / "invalid.sqlite3",
            None,
            shopping_fingerprint="invalid",
        )
    installation = Installation(instance, "edge")
    shopping = shopping_bearer(installation)
    service = runtime(
        False,
        installation,
        tmp_path / "empty.sqlite3",
        None,
        shopping_fingerprint=digest(shopping),
    )
    try:
        response = TestClient(service.app, base_url=PUBLIC).get(
            SHOPPING_PATH, headers=header(shopping)
        )
        assert response.status_code == 503 and response.json() == {
            "error": "shopping_list_unavailable"
        }
    finally:
        service.close()


def test_launcher_accepts_shopping_only_and_does_not_pass_digest_as_argument(launch, capsys):
    root, calls = launch
    options = root / "options.json"
    options.write_text(json.dumps({"public_origins": [ORIGIN], "ha_shopping_digest": 42}))
    assert ha_app.main(["--channel", "edge"]) == 2 and not calls
    assert "42" not in capsys.readouterr().err
    options.write_text(json.dumps({"public_origins": [ORIGIN], "ha_shopping_digest": "c" * 64}))
    assert ha_app.main(["--channel", "edge"]) == 0
    _, arguments, environment = calls[1]
    assert "c" * 64 not in arguments and environment[SHOPPING_DIGEST_ENV] == "c" * 64


def test_shopping_only_activates_the_private_listener(monkeypatch, tmp_path):
    _, store, _, _ = fixture(tmp_path)
    token = shopping_bearer(store.installation)
    monkeypatch.setenv("SUPERVISOR_TOKEN", SUPERVISOR)
    monkeypatch.setenv(SHOPPING_DIGEST_ENV, digest(token))

    def serve(app):
        response = TestClient(app, base_url=PRIVATE).get(SHOPPING_PATH, headers=header(token))
        assert response.json() == {"items": []}

    monkeypatch.setattr(ingress, "_serve_ha_projections", serve)
    assert (
        ingress.main(
            [
                "--channel",
                "edge",
                "--database",
                str(store.path),
                "--instance-id",
                store.installation.instance_id,
                "--public-origin",
                ORIGIN,
            ]
        )
        == 0
    )
    assert SHOPPING_DIGEST_ENV not in ingress.os.environ
