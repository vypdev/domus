"""Verify authority, boundaries, and privacy of the low-stock projection."""

import json
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
from test_task_commands import counts, fixture

from domus.composition import ha_app, ingress, server
from domus.domain.errors import InvalidInput
from domus.domain.storage import Installation
from domus.entrypoints.ha_calendar_http import CALENDAR_PATH
from domus.entrypoints.ha_deadline_http import DEADLINE_PATH
from domus.entrypoints.ha_stock_http import STOCK_DIGEST_ENV, STOCK_PATH


def stock_bearer(installation, seed="a"):
    return f"{installation.instance_id}.{installation.channel}.stock.{seed * 64}"


@pytest.mark.parametrize("native", [False, True], ids=["standalone", "ingress"])
def test_stock_count_requires_an_independent_revocable_grant(tmp_path, native):
    _, store, _, _ = fixture(tmp_path)
    installation = store.installation
    stock = stock_bearer(installation)
    replacement = stock_bearer(installation, "b")
    calendar = bearer(installation)
    deadlines = deadline_bearer(installation)
    before = counts(store)

    for fingerprint in (None, digest(stock), digest(replacement)):
        service = runtime(
            native,
            installation,
            store.path,
            digest(calendar),
            deadline_fingerprint=digest(deadlines),
            stock_fingerprint=fingerprint,
        )
        client = TestClient(service.app, base_url=PRIVATE if native else PUBLIC)
        try:
            assert client.get(CALENDAR_PATH, params=WINDOW, headers=header(calendar)).is_success
            assert client.get(DEADLINE_PATH, headers=header(deadlines)).is_success
            assert (
                client.get(CALENDAR_PATH, params=WINDOW, headers=header(stock)).status_code == 401
            )
            assert client.get(DEADLINE_PATH, headers=header(stock)).status_code == 401
            response = client.get(STOCK_PATH, headers=header(stock))
            if fingerprint is None:
                assert response.status_code == 404
                continue
            if fingerprint == digest(replacement):
                assert response.status_code == 401
                assert client.get(STOCK_PATH, headers=header(replacement)).json() == {
                    "low_stock_products": 0
                }
                continue
            assert response.status_code == 200
            assert response.headers["cache-control"] == "no-store"
            assert response.json() == {"low_stock_products": 0}
            wrong_grants = [
                replacement,
                calendar,
                deadlines,
                stock.replace(installation.instance_id, str(uuid4())),
                stock.replace(".edge.", ".stable."),
            ]
            for wrong in wrong_grants:
                rejected = client.get(STOCK_PATH, headers=header(wrong))
                assert rejected.status_code == 401
                assert rejected.json() == {"error": "invalid_stock_credential"}
            assert client.get(STOCK_PATH).status_code == 401
            assert client.post(STOCK_PATH, headers=header(stock)).status_code == 405
            assert (
                client.get(
                    STOCK_PATH, params={"household": "other"}, headers=header(stock)
                ).status_code
                == 422
            )
            headers = {**header(stock), **{f"x-extra-{index}": "x" for index in range(33)}}
            assert client.get(STOCK_PATH, headers=headers).status_code == 422
            if native:
                forbidden_transport = TestClient(service.app, base_url="http://native:8099")
            else:
                forbidden_transport = TestClient(
                    service.app, base_url="http://domus.example", client=("192.0.2.1", 80)
                )
            assert not forbidden_transport.get(STOCK_PATH, headers=header(stock)).is_success
        finally:
            service.close()
    assert counts(store) == before


@pytest.mark.parametrize("native", [False, True], ids=["standalone", "ingress"])
def test_stock_count_reports_unavailable_before_setup(tmp_path, native):
    installation = Installation(str(uuid4()), "edge")
    stock = stock_bearer(installation)
    service = runtime(
        native, installation, tmp_path / "empty.sqlite3", None, stock_fingerprint=digest(stock)
    )
    try:
        client = TestClient(service.app, base_url=PRIVATE if native else PUBLIC)
        response = client.get(STOCK_PATH, headers=header(stock))
        assert response.status_code == 503 and response.json() == {"error": "low_stock_unavailable"}
    finally:
        service.close()


def test_stock_requires_persistence_secure_origin_and_a_valid_digest(tmp_path):
    instance = str(uuid4())
    with pytest.raises(InvalidInput, match="ha_stock_requires_persistent_secure_origin"):
        server.create_runtime(
            "https://ha.example", PUBLIC, instance, "edge", ha_stock_digest="a" * 64
        )
    with pytest.raises(InvalidInput, match="ha_stock_requires_persistent_secure_origin"):
        server.create_runtime(
            "https://ha.example",
            "http://localhost:8099",
            instance,
            "edge",
            development_http=True,
            database=tmp_path / "insecure.sqlite3",
            ha_stock_digest="a" * 64,
        )
    with pytest.raises(InvalidInput, match="invalid_ha_stock_digest"):
        runtime(
            False,
            Installation(instance, "edge"),
            tmp_path / "invalid.sqlite3",
            None,
            stock_fingerprint="invalid",
        )


def test_private_launcher_accepts_a_stock_digest_without_a_command_argument(launch, capsys):
    root, calls = launch
    options = root / "options.json"
    options.write_text(json.dumps({"public_origins": [ORIGIN], "ha_stock_digest": 42}))
    assert ha_app.main(["--channel", "edge"]) == 2 and not calls
    assert "42" not in capsys.readouterr().err
    options.write_text(json.dumps({"public_origins": [ORIGIN], "ha_stock_digest": "c" * 64}))
    assert ha_app.main(["--channel", "edge"]) == 0
    _, arguments, environment = calls[1]
    assert "c" * 64 not in arguments
    assert environment[STOCK_DIGEST_ENV] == "c" * 64


def test_stock_alone_activates_the_private_listener(monkeypatch, tmp_path):
    _, store, _, _ = fixture(tmp_path)
    stock = stock_bearer(store.installation)
    monkeypatch.setenv("SUPERVISOR_TOKEN", SUPERVISOR)
    monkeypatch.setenv(STOCK_DIGEST_ENV, digest(stock))

    def serve(app):
        response = TestClient(app, base_url=PRIVATE).get(STOCK_PATH, headers=header(stock))
        assert response.json() == {"low_stock_products": 0}

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
    assert STOCK_DIGEST_ENV not in ingress.os.environ
