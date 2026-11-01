"""Shell/assets are nonpersonal and fixed-base; personal API response policy remains strict."""

import json
import re
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from test_ui_bundle import build

from domus.domain.errors import DomusError, Forbidden, InvalidInput, StorageFailure
from domus.entrypoints.http import HTTPSettings, _HTTPBoundary
from domus.entrypoints.native_http import _NativeBoundary
from domus.entrypoints.ui_bundle import load_bundle
from domus.entrypoints.ui_http import attach_ui

ORIGIN = "http://ha.example:8123"
PREFIX = "/api/hassio_ingress/abcdefghijklmnop"


def fixture(tmp_path: Path, deployment: str, *, available: bool = True, nonce=None) -> tuple:
    app = FastAPI(redirect_slashes=False)
    if deployment == "native":
        app.add_middleware(_NativeBoundary, origins=(ORIGIN,), correlation=lambda: "cor_test")
    else:
        app.add_middleware(
            _HTTPBoundary,
            settings=HTTPSettings(ORIGIN, "domus-test", b"x" * 32),
            correlation=lambda: "cor_test",
        )

    @app.exception_handler(DomusError)
    async def rejected(request: Request, error: DomusError) -> JSONResponse:
        return JSONResponse(
            {"state": "blocked"},
            status_code=422
            if isinstance(error, InvalidInput)
            else 500
            if isinstance(error, StorageFailure)
            else 403,
        )

    @app.get("/api/private")
    def personal() -> dict:
        return {"state": "protected-placeholder"}

    bindings: list[str] = []

    def bind(request: Request) -> None:
        bindings.append(request.url.path)
        if request.headers.get("X-Test-Deny"):
            raise Forbidden("request_forbidden")

    bundle = load_bundle(build(tmp_path / "ui")) if available else None
    attach_ui(app, bundle, deployment, bind, **({"nonce": nonce} if nonce else {}))
    headers = {"X-Ingress-Path": PREFIX} if deployment == "native" else {}
    client = TestClient(
        app,
        base_url=ORIGIN,
        client=("172.30.32.2", 1234),
        headers=headers,
        raise_server_exceptions=False,
    )
    return client, bindings


@pytest.mark.parametrize("deployment", ["native", "standalone"])
def test_shell_uses_public_bootstrap_and_matching_strict_csp_without_business_or_login_work(
    tmp_path: Path, deployment: str
) -> None:
    client, bindings = fixture(tmp_path, deployment)
    response = client.get("/")
    assert response.status_code == 200
    match = re.search(
        r'<script id="domus-bootstrap" type="application/json">([^<]+)</script>', response.text
    )
    assert match
    bootstrap = json.loads(match[1])
    base = PREFIX + "/" if deployment == "native" else "/"
    assert bootstrap == {
        "version": 1,
        "deployment": deployment,
        "application_base": base,
        "style_nonce": bootstrap["style_nonce"],
    }
    assert re.fullmatch(r"[A-Za-z0-9_-]{32}", bootstrap["style_nonce"])
    assert f"'nonce-{bootstrap['style_nonce']}'" in response.headers["content-security-policy"]
    assert "script-src 'self'" in response.headers["content-security-policy"]
    assert "unsafe-inline" not in response.headers["content-security-policy"]
    assert "unsafe-eval" not in response.headers["content-security-policy"]
    assert f'src="{base}assets/index-safe.js"' in response.text
    assert f'href="{base}assets/index-safe.css"' in response.text
    assert "__DOMUS_BOOTSTRAP" not in response.text and "set-cookie" not in response.headers
    assert bindings == ["/"] and client.cookies == {}
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    another = client.get("/")
    assert another.headers["content-security-policy"] != response.headers["content-security-policy"]


@pytest.mark.parametrize("deployment", ["native", "standalone"])
def test_only_registered_assets_are_served_with_their_mime_and_head_semantics(
    tmp_path: Path, deployment: str
) -> None:
    client, bindings = fixture(tmp_path, deployment)
    for filename, mime in (("index-safe.js", "text/javascript"), ("index-safe.css", "text/css")):
        resource = client.get("/assets/" + filename)
        head = client.head("/assets/" + filename)
        assert resource.status_code == head.status_code == 200
        assert resource.headers["content-type"].startswith(mime)
        assert (
            head.content == b""
            and head.headers["content-length"] == resource.headers["content-length"]
        )
        assert "script-src 'self'" not in resource.headers["content-security-policy"]
    assert len(bindings) == 4
    assert client.head("/").status_code == 200


@pytest.mark.parametrize(
    "path",
    [
        "/assets/missing.js",
        "/assets/index.html",
        "/assets/../private.json",
        "/.vite/manifest.json",
        "/missing-route",
    ],
)
def test_unknown_resources_never_receive_shell_success(tmp_path: Path, path: str) -> None:
    client, _ = fixture(tmp_path, "standalone")
    response = client.get(path)
    assert response.status_code == 404
    assert "domus-bootstrap" not in response.text


@pytest.mark.parametrize("deployment", ["native", "standalone"])
def test_query_or_denied_binding_never_relaxes_csp_or_returns_a_shell(
    tmp_path: Path, deployment: str
) -> None:
    client, _ = fixture(tmp_path, deployment)
    assert client.get("/?actor=forged").status_code == 422
    for path in ("/", "/assets/index-safe.js"):
        denied = client.get(path, headers={"X-Test-Deny": "1"})
        assert denied.status_code == 403
        assert "nonce-" not in denied.headers["content-security-policy"]


@pytest.mark.parametrize("deployment", ["native", "standalone"])
def test_missing_build_is_explicit_and_api_policy_does_not_inherit_the_shell_nonce(
    tmp_path: Path, deployment: str
) -> None:
    client, _ = fixture(tmp_path, deployment, available=False)
    response = client.get("/")
    assert response.status_code == 503 and "UI assets are unavailable" in response.text
    assert (
        "domus-bootstrap" not in response.text
        and "nonce-" not in response.headers["content-security-policy"]
    )
    assert client.get("/assets/index-safe.js").status_code == 404
    personal = client.get("/api/private")
    assert personal.status_code == 200
    assert "script-src 'self'" not in personal.headers["content-security-policy"]


@pytest.mark.parametrize("nonce", [lambda: "bad", lambda: '"; script-src *'])
def test_invalid_nonce_provider_cannot_expand_the_response_policy(tmp_path: Path, nonce) -> None:
    client, _ = fixture(tmp_path, "standalone", nonce=nonce)
    response = client.get("/")
    assert (
        response.status_code == 500 and "nonce-" not in response.headers["content-security-policy"]
    )


def test_ui_middleware_forwards_the_actual_application_lifespan(tmp_path: Path) -> None:
    client, _ = fixture(tmp_path, "standalone")
    with client:
        assert client.get("/").status_code == 200


def test_unknown_deployment_is_refused_before_routes_are_installed() -> None:
    with pytest.raises(InvalidInput):
        attach_ui(FastAPI(), None, "unknown", lambda request: None)
