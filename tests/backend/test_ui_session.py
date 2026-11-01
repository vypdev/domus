"""Actual composed identities/SQLite remain authoritative behind nonpersonal UI delivery."""

import json
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from test_auth_http import login
from test_household_http import fixture as standalone_fixture
from test_ingress_sessions import HEADERS, Clock
from test_native_http import fixture as native_fixture
from test_ui_bundle import build

from domus.domain.errors import IdentityUnavailable
from domus.entrypoints.native_http import create_native_app
from domus.entrypoints.ui_bundle import load_bundle


def test_native_shell_and_assets_use_only_source_binding_and_never_convert_it_to_human_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = load_bundle(build(tmp_path / "ui"))
    runtime, client, lookup, _ = native_fixture(tmp_path, monkeypatch, bundle)
    lookup.error = IdentityUnavailable("ha_unavailable")
    assert client.get("/").status_code == 200
    assert client.get("/assets/index-safe.js").status_code == 200
    assert client.get("/api/v1/session").status_code == 503
    client.headers.pop("Cookie")
    assert client.get("/").status_code == 401
    assert client.get("/assets/index-safe.js").status_code == 401
    runtime.close()


def test_standalone_shell_is_nonpersonal_and_oauth_returns_only_to_the_fixed_root(
    tmp_path: Path,
) -> None:
    bundle = load_bundle(build(tmp_path / "ui"))
    client, store, _, settings, _, _ = standalone_fixture(tmp_path, bundle)
    response = client.get("/")
    assert response.status_code == 200 and client.cookies == {}
    match = re.search(r'type="application/json">([^<]+)</script>', response.text)
    assert match and set(json.loads(match[1])) == {
        "version",
        "deployment",
        "application_base",
        "style_nonce",
    }
    assert client.get("/api/v1/session").status_code == 401
    with store.read() as unit:
        assert unit.households.current() is None
    login(client)
    assert settings.session_cookie in client.cookies
    assert client.get("/api/v1/authorization").json()["state"] == "unconfigured"
    assert (
        "script-src 'self'" not in client.get("/api/v1/session").headers["content-security-policy"]
    )
    with store.read() as unit:
        assert unit.households.current() is None


def test_raw_native_factory_keeps_conservative_proof_without_an_explicit_binding_port() -> None:
    proof = Mock(side_effect=IdentityUnavailable("ha_unavailable"))
    app = create_native_app(
        lambda request: SimpleNamespace(status=proof),
        ("http://ha.example:8123",),
        "edge",
        Clock(),
        correlation=lambda: "cor_test",
    )
    client = TestClient(
        app,
        base_url="http://ha.example:8123",
        client=("172.30.32.2", 1234),
        headers=dict(HEADERS),
    )
    assert client.get("/").status_code == 503
    proof.assert_called_once()
