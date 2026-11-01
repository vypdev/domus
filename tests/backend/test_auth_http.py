"""Strict authentication HTTP contracts never trust request-chosen identity or origins."""

import asyncio
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from test_standalone_sessions import fixture as identity_fixture

from domus.application.authentication import Authentication
from domus.application.sessions import SessionGuard
from domus.domain.errors import (
    Conflict,
    DomusError,
    Forbidden,
    IdentityUnavailable,
    InvalidInput,
    StorageFailure,
    Unauthenticated,
)
from domus.domain.storage import Installation
from domus.entrypoints.entry_context import EntryHTTPContext
from domus.entrypoints.http import HTTPSettings, _HTTPBoundary, create_app
from domus.infrastructure.memory_attempts import MemoryLoginAttempts


class Entropy:
    def __init__(self) -> None:
        self.values = iter(
            ("s" * 43, "v" * 43, "b" * 43, "x" * 43, "t" * 43, "v" * 43, "c" * 43, "y" * 43)
        )

    def new(self) -> str:
        return next(self.values)


def fixture() -> tuple:
    identity, oauth, socket, clock = identity_fixture()
    flow = Authentication(MemoryLoginAttempts(), identity, clock, Entropy())
    settings = HTTPSettings("https://domus.example", "domus-edge", b"k" * 32)
    app = create_app(
        flow,
        SessionGuard(identity, identity, clock),
        identity,
        settings,
        correlation=lambda: "cor_test",
        entry=EntryHTTPContext(
            Installation("047cc6fb-dfb0-4fa4-b3c3-e0fe54d116b6", "edge"),
            "standalone",
            clock,
            clock,
            False,
        ),
    )
    client = TestClient(
        app, base_url=settings.origin, follow_redirects=False, raise_server_exceptions=False
    )
    return client, identity, oauth, socket, clock, settings


def login(client: TestClient) -> None:
    start = client.get("/api/v1/auth/start")
    assert start.status_code == 303
    state = parse_qs(urlsplit(start.headers["location"]).query)["state"][0]
    callback = client.get("/api/v1/auth/callback", params={"state": state, "code": "code"})
    assert callback.status_code == 303
    assert callback.headers["location"] == "/"


def test_happy_path_sets_secure_host_only_cookies_and_identity_view_has_no_credentials() -> None:
    client, _, _, _, _, settings = fixture()
    before = client.get("/api/v1/session")
    assert before.status_code == 401 and before.json()["code"] == "session_required"
    start = client.get("/api/v1/auth/start")
    cookie = start.headers["set-cookie"]
    assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=lax" in cookie
    assert "Domain=" not in cookie and "Path=/" in cookie
    assert settings.browser_cookie in cookie and "__Host-" in cookie
    state = parse_qs(urlsplit(start.headers["location"]).query)["state"][0]
    callback = client.get("/api/v1/auth/callback", params={"code": "code", "state": state})
    assert callback.status_code == 303
    assert settings.session_cookie in callback.headers["set-cookie"]
    result = client.get("/api/v1/session")
    assert result.status_code == 200
    assert result.json()["ha_user_id"] == "a" * 32
    assert result.json()["access"] == "full"
    assert result.json()["ha_administrator"] is False
    for sensitive in ("private-access", "private-refresh", "csrf_token", "session_id"):
        assert sensitive not in result.text
    assert result.headers["cache-control"] == "no-store"
    assert result.headers["referrer-policy"] == "no-referrer"


def test_outage_status_is_read_only_and_logout_still_clears_local_access() -> None:
    client, identity, oauth, socket, _, settings = fixture()
    login(client)
    session_id = client.cookies.get(settings.session_cookie)
    socket.error = IdentityUnavailable("ha_unavailable")
    assert client.get("/api/v1/session").json()["access"] == "read_only"
    csrf = client.get("/api/v1/auth/csrf").json()["csrf_token"]
    oauth.revoke_error = IdentityUnavailable("ha_unavailable")
    response = client.post(
        "/api/v1/auth/logout", json={}, headers={"Origin": settings.origin, "X-CSRF-Token": csrf}
    )
    assert response.status_code == 200
    assert response.json()["state"] == "logged_out"
    assert response.json()["upstream_revoked"] is False
    assert "not confirmed" in response.json()["action_required"]
    assert identity.get(session_id) is None
    assert client.cookies.get(settings.session_cookie) is None
    assert client.get("/api/v1/session").status_code == 401


def test_lost_private_credential_is_unknown_upstream_revocation_not_a_fabricated_success() -> None:
    client, identity, _, _, _, settings = fixture()
    login(client)
    session_id = client.cookies.get(settings.session_cookie)
    csrf = client.get("/api/v1/auth/csrf").json()["csrf_token"]
    identity.remove(session_id)
    response = client.post(
        "/api/v1/auth/logout", json={}, headers={"Origin": settings.origin, "X-CSRF-Token": csrf}
    )
    assert response.status_code == 200 and response.json()["state"] == "logged_out"
    assert response.json()["upstream_revoked"] is None
    assert "not confirmed" in response.json()["action_required"]


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Origin": "https://evil.example"},
        {"Origin": "https://domus.example"},
        {"Origin": "https://domus.example", "X-CSRF-Token": "wrong"},
    ],
)
def test_cookie_mutations_require_exact_origin_and_session_bound_csrf(headers: dict) -> None:
    client, _, oauth, _, _, _ = fixture()
    login(client)
    response = client.post("/api/v1/auth/logout", json={}, headers=headers)
    assert response.status_code == 403 and response.json()["code"] == "request_forbidden"
    assert oauth.revoked == []
    assert client.get("/api/v1/session").status_code == 200


def test_successful_logout_uses_original_cookie_and_empty_strict_body() -> None:
    client, identity, oauth, _, _, settings = fixture()
    login(client)
    old = client.cookies.get(settings.session_cookie)
    csrf = client.get("/api/v1/auth/csrf").json()["csrf_token"]
    headers = {"Origin": settings.origin, "X-CSRF-Token": csrf}
    rejected = client.post(
        "/api/v1/auth/logout", json={"member_id": "another", "secret": "private"}, headers=headers
    )
    assert rejected.status_code == 422 and "private" not in rejected.text
    assert identity.get(old) is not None
    response = client.post("/api/v1/auth/logout", json={}, headers=headers)
    assert response.status_code == 200 and response.json()["upstream_revoked"] is True
    assert identity.get(old) is None and oauth.revoked == ["private-refresh"]


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/session?member_id=someone",
        "/api/v1/auth/start?ha_url=https://evil.example",
        "/api/v1/auth/callback?code=private-code&state=bad",
        "/api/v1/auth/callback/",
    ],
)
def test_unknown_unbounded_or_route_mismatched_inputs_never_establish_session(path: str) -> None:
    client, _, oauth, _, _, _ = fixture()
    response = client.get(path)
    assert response.status_code in (404, 422)
    assert "private-code" not in response.text
    assert oauth.revoked == []


@pytest.mark.parametrize(
    "headers",
    [
        {"Host": "evil.example"},
        {"Host": "user@domus.example"},
        {"X-Remote-User-Id": "a" * 32},
        {"X-Ingress-Path": "/forged"},
    ],
)
def test_standalone_rejects_wrong_host_and_ingress_identity_headers(headers: dict) -> None:
    client, _, _, _, _, _ = fixture()
    response = client.get("/api/v1/auth/start", headers=headers)
    assert response.status_code == 403
    assert "location" not in response.headers and "set-cookie" not in response.headers


def test_duplicate_callback_fields_or_browser_cookie_cannot_consume_attempt() -> None:
    client, _, _, _, _, settings = fixture()
    start = client.get("/api/v1/auth/start")
    state = parse_qs(urlsplit(start.headers["location"]).query)["state"][0]
    duplicate = client.get(
        "/api/v1/auth/callback", params=[("state", state), ("state", state), ("code", "code")]
    )
    assert duplicate.status_code == 422
    token = client.cookies.get(settings.browser_cookie)
    response = client.get(
        "/api/v1/auth/callback",
        params={"code": "code", "state": state},
        headers={"Cookie": f"{settings.browser_cookie}={token}; {settings.browser_cookie}={token}"},
    )
    assert response.status_code == 401
    assert (
        client.get("/api/v1/auth/callback", params={"code": "code", "state": state}).status_code
        == 303
    )


@pytest.mark.parametrize("binding", ["missing", "malformed", "wrong", "expired"])
def test_invalid_login_binding_explains_restart_without_exchanging_code(
    binding: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _, oauth, socket, clock, settings = fixture()
    start = client.get("/api/v1/auth/start")
    state = parse_qs(urlsplit(start.headers["location"]).query)["state"][0]
    if binding == "missing":
        client.cookies.clear()
    elif binding == "malformed":
        client.cookies.clear()
        client.cookies.set(settings.browser_cookie, "invalid!binding")
    elif binding == "wrong":
        client.cookies.clear()
        client.cookies.set(settings.browser_cookie, "w" * 43)
    else:
        clock.value += 300_000

    def forbidden_exchange(*args: object) -> None:
        pytest.fail("An invalid browser attempt must not exchange an HA code")

    monkeypatch.setattr(oauth, "exchange", forbidden_exchange)
    response = client.get("/api/v1/auth/callback", params={"state": state, "code": "private-code"})
    assert response.status_code == 401
    assert response.json()["code"] in ("invalid_login_attempt", "login_attempt_expired")
    assert "sign-in attempt" in response.json()["message"]
    assert "/api/v1/auth/start" in response.json()["action_required"]
    assert "five minutes" in response.json()["action_required"]
    assert "private-code" not in response.text and state not in response.text
    assert client.cookies.get(settings.session_cookie) is None
    assert socket.tokens == [] and oauth.revoked == []


def test_missing_browser_binding_can_recover_through_a_new_bound_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = iter(value * 43 for value in ("s", "v", "b", "t", "v", "c", "x"))
    monkeypatch.setattr(Entropy, "new", lambda self: next(values))
    client, _, _, _, _, _ = fixture()
    start = client.get("/api/v1/auth/start")
    state = parse_qs(urlsplit(start.headers["location"]).query)["state"][0]
    client.cookies.clear()
    rejected = client.get("/api/v1/auth/callback", params={"state": state, "code": "code"})
    assert rejected.status_code == 401
    login(client)
    assert client.get("/api/v1/session").json()["access"] == "full"


def test_reauthentication_rotates_cookie_and_removes_previous_browser_session() -> None:
    client, identity, _, _, _, settings = fixture()
    login(client)
    old = client.cookies.get(settings.session_cookie)
    login(client)
    assert client.cookies.get(settings.session_cookie) != old
    assert identity.get(old) is None


def test_openapi_contract_and_no_http_console_approval() -> None:
    client, _, _, _, _, _ = fixture()
    paths = client.get("/api/v1/openapi.json").json()["paths"]
    assert set(paths) == {
        "/api/v1/auth/start",
        "/api/v1/auth/callback",
        "/api/v1/auth/logout",
        "/api/v1/auth/csrf",
        "/api/v1/session",
    }
    assert client.post("/api/v1/recovery/approve").status_code == 403
    assert client.get("/docs").status_code == 404


def test_published_openapi_schema_and_security_match_actual_routes() -> None:
    client, _, _, _, _, settings = fixture()
    actual = client.get("/api/v1/openapi.json").json()
    reference = json.loads(
        (Path(__file__).resolve().parents[2] / "docs/contracts/auth-api.openapi.json").read_text()
    )
    assert actual["paths"] == reference["paths"]
    assert actual["components"]["schemas"] == reference["components"]["schemas"]
    scheme = actual["components"]["securitySchemes"]["DomusSession"]
    assert scheme == {"type": "apiKey", "in": "cookie", "name": settings.session_cookie}
    operation = actual["paths"]["/api/v1/auth/logout"]["post"]
    assert operation["security"] == [{"DomusSession": []}]
    assert {item["name"] for item in operation["parameters"]} == {
        "Origin",
        "X-CSRF-Token",
        "X-Domus-Context",
    }
    context = next(item for item in operation["parameters"] if item["name"] == "X-Domus-Context")
    assert context["required"] is False
    assert operation["responses"]["422"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/ErrorResponse"
    )


def test_bearer_transport_credential_cannot_replace_a_domus_cookie() -> None:
    client, _, _, _, _, _ = fixture()
    response = client.get(
        "/api/v1/session", headers={"Authorization": "Bearer fixture-transport-token"}
    )
    assert response.status_code == 401 and response.json()["code"] == "session_required"


def test_declined_login_consumes_only_the_bound_attempt_and_clears_browser_cookie() -> None:
    client, _, oauth, _, _, settings = fixture()
    start = client.get("/api/v1/auth/start")
    state = parse_qs(urlsplit(start.headers["location"]).query)["state"][0]
    invalid = client.get(
        "/api/v1/auth/callback", params={"state": state, "code": "code", "error": "access_denied"}
    )
    assert invalid.status_code == 422
    result = client.get("/api/v1/auth/callback", params={"state": state, "error": "access_denied"})
    assert result.status_code == 401 and result.json()["code"] == "sign_in_declined"
    assert client.cookies.get(settings.browser_cookie) is None
    assert oauth.revoked == []


@pytest.mark.parametrize(
    "failure,status,code",
    [
        (Unauthenticated("session_required"), 401, "session_required"),
        (Forbidden("permission_denied"), 403, "permission_denied"),
        (InvalidInput("invalid_request"), 422, "invalid_request"),
        (Conflict("login_attempt_exists"), 409, "login_attempt_exists"),
        (IdentityUnavailable("ha_unavailable"), 503, "ha_unavailable"),
        (DomusError("ha_unavailable"), 500, "internal_error"),
        (StorageFailure("ha_unavailable"), 500, "internal_error"),
        (InvalidInput("private-provider-payload"), 500, "internal_error"),
        (RuntimeError("private-provider-payload"), 500, "internal_error"),
    ],
)
def test_error_envelope_maps_only_known_failures_and_never_echoes_provider_detail(
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
    status: int,
    code: str,
) -> None:
    client, identity, _, _, _, _ = fixture()

    def fail(*arguments: object) -> str:
        raise failure

    monkeypatch.setattr(identity, "authorization_url", fail)
    response = client.get("/api/v1/auth/start", headers={"X-Correlation-Id": "untrusted-input"})
    assert response.status_code == status and response.json()["code"] == code
    assert response.json()["correlation_id"] == "cor_test"
    assert (
        "private-provider-payload" not in response.text and "untrusted-input" not in response.text
    )


def test_http_bounds_and_malformed_host_fail_before_any_protected_action() -> None:
    client, _, oauth, _, _, settings = fixture()
    for host in (
        "domus.example:bad",
        "domus.example/path",
        "domus.example:8443",
        "domus.example:0",
    ):
        assert client.get("/api/v1/auth/start", headers={"Host": host}).status_code == 403
    assert client.get("/api/v1/auth/start?x=" + "x" * 8193).status_code == 422
    assert client.request("GET", "/api/v1/auth/start", json={"actor": "forged"}).status_code == 422
    login(client)
    csrf = client.get("/api/v1/auth/csrf").json()["csrf_token"]
    result = client.post(
        "/api/v1/auth/logout",
        json={"private": "x" * 70_000},
        headers={"Origin": settings.origin, "X-CSRF-Token": csrf},
    )
    assert result.status_code == 413 and result.json()["code"] == "request_too_large"
    assert oauth.revoked == []
    assert (
        client.post(
            "/api/v1/recovery/approve",
            json={},
            headers={"Origin": settings.origin, "X-CSRF-Token": csrf},
        ).status_code
        == 404
    )


def test_http_settings_are_bounded_and_explicit_loopback_development_has_distinct_cookies() -> None:
    with pytest.raises(InvalidInput):
        HTTPSettings("https://domus.example", "invalid cookie", b"k" * 32)
    with pytest.raises(InvalidInput):
        HTTPSettings("https://domus.example", "domus-edge", b"short")
    settings = HTTPSettings("http://127.0.0.1:8099", "domus-edge", b"k" * 32)
    assert not settings.secure and settings.session_cookie == "domus-edge-session"
    assert settings.browser_cookie == "domus-edge-browser"


def test_header_count_and_size_are_bounded_before_login_state_is_allocated() -> None:
    client, _, _, _, _, _ = fixture()
    assert client.get("/api/v1/auth/start", headers={"X-Padding": "x" * 17_000}).status_code == 422
    assert (
        client.get(
            "/api/v1/auth/start", headers={f"X-{index}": "x" for index in range(101)}
        ).status_code
        == 422
    )
    assert client.get("/api/v1/auth/start").status_code == 303


def test_lifespan_and_method_mismatch_use_framework_contract_without_redirects() -> None:
    client, _, _, _, _, _ = fixture()
    with client:
        assert client.get("/api/v1/openapi.json").status_code == 200
        assert client.get("/api/v1/auth/logout").status_code == 405


def test_fragmented_body_and_late_disconnect_are_preserved_and_cache_headers_are_overridden() -> (
    None
):
    settings = HTTPSettings("https://domus.example", "domus-edge", b"k" * 32)
    scope = {
        "type": "http",
        "method": "POST",
        "query_string": b"",
        "headers": [
            (b"host", b"domus.example"),
            (b"origin", b"https://domus.example"),
            (b"cookie", f"{settings.session_cookie}=fixture".encode()),
            (b"x-csrf-token", settings.csrf("fixture").encode()),
        ],
    }
    incoming = iter(
        [
            {"type": "http.request", "body": b"a", "more_body": True},
            {"type": "http.request", "body": b"b", "more_body": False},
            {"type": "http.disconnect"},
        ]
    )
    received, sent = [], []

    async def receive() -> dict:
        return next(incoming)

    async def send(message: dict) -> None:
        sent.append(message)

    async def app(scope: dict, receive: object, send: object) -> None:
        received.append(await receive())
        received.append(await receive())
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"cache-control", b"public")],
            }
        )
        await send({"type": "http.response.body", "body": b"ok"})

    asyncio.run(_HTTPBoundary(app, settings, lambda: "cor_test")(scope, receive, send))
    assert received == [
        {"type": "http.request", "body": b"ab", "more_body": False},
        {"type": "http.disconnect"},
    ]
    assert dict(sent[0]["headers"])[b"cache-control"] == b"no-store"


@pytest.mark.parametrize("disconnect", [False, True])
def test_body_deadline_and_disconnect_never_call_inner_application(
    monkeypatch: pytest.MonkeyPatch,
    disconnect: bool,
) -> None:
    from domus.entrypoints import bounded_http

    settings = HTTPSettings("https://domus.example", "domus-edge", b"k" * 32)
    scope = {
        "type": "http",
        "method": "GET",
        "query_string": b"",
        "headers": [(b"host", b"domus.example")],
    }
    real_timeout = asyncio.timeout
    sent = []

    def immediate_deadline(seconds: float) -> asyncio.Timeout:
        assert seconds == 5
        return real_timeout(0)

    async def receive() -> dict:
        if disconnect:
            return {"type": "http.disconnect"}
        await asyncio.Event().wait()
        pytest.fail("A blocked request body must be cancelled")

    async def send(message: dict) -> None:
        sent.append(message)

    async def forbidden(*arguments: object) -> None:
        pytest.fail("No application action is allowed before receiving a valid body")

    monkeypatch.setattr(bounded_http, "timeout", immediate_deadline)
    asyncio.run(_HTTPBoundary(forbidden, settings, lambda: "cor_test")(scope, receive, send))
    assert sent == [] if disconnect else sent[0]["status"] == 408
