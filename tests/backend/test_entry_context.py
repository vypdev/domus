"""Real HTTP contexts expose composition facts and reject stale client context assertions."""

from dataclasses import dataclass, replace
from pathlib import Path

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from test_auth_http import login
from test_household_http import fixture as standalone_fixture
from test_household_http import write_headers
from test_ingress_sessions import PREFIX, USER
from test_native_http import INSTANCE
from test_native_http import fixture as native_fixture
from test_standalone_sessions import fixture as identity_fixture

from domus.application.sessions import SessionStatus
from domus.composition import ingress, server
from domus.domain.errors import Forbidden, IdentityUnavailable, InvalidInput, StorageFailure
from domus.domain.identity import HumanIdentity
from domus.domain.storage import Installation
from domus.entrypoints.entry_context import EntryHTTPContext


def test_native_metadata_uses_actual_installation_prefix_and_original_lease_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, client, lookup, clock = native_fixture(tmp_path, monkeypatch)
    first = client.get("/api/v1/session").json()
    context = first["context"]
    assert context["installation_id"] == INSTANCE and context["channel"] == "edge"
    assert context["deployment"] == "native" and context["application_base"] == PREFIX + "/"
    assert context["household_api_available"] is True
    assert context["expires_at"] - context["server_time"] == 3_600_000
    assert context["server_time"] > 1_700_000_000_000
    clock.value += 1234
    lookup.error = IdentityUnavailable("ha_unavailable")
    grace = client.get("/api/v1/session").json()
    assert grace["access"] == "read_only"
    assert grace["context"]["server_time"] == context["server_time"] + 1234
    assert grace["context"]["expires_at"] == context["expires_at"]
    assert "csrf_token" not in first and "session_id" not in first
    runtime.close()


def test_standalone_metadata_is_fixed_root_and_reads_create_no_household(tmp_path: Path) -> None:
    client, store, _, _, _, _ = standalone_fixture(tmp_path)
    login(client)
    session = client.get("/api/v1/session", headers={"X-Forwarded-Prefix": "/foreign/"}).json()
    assert session["context"] == {
        "installation_id": INSTANCE,
        "channel": "edge",
        "deployment": "standalone",
        "application_base": "/",
        "household_api_available": True,
        "server_time": 100,
        "expires_at": 3_600_100,
    }
    assert client.get("/api/v1/authorization").json()["state"] == "unconfigured"
    with store.read() as unit:
        assert unit.households.current() is None


@pytest.mark.parametrize("deployment", ["native", "standalone"])
@pytest.mark.parametrize("changed", ["installation", "channel", "subject", "duplicate", "empty"])
def test_context_mismatch_cannot_read_or_create_a_household(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, deployment: str, changed: str
) -> None:
    runtime = None
    if deployment == "native":
        runtime, client, _, _ = native_fixture(tmp_path, monkeypatch)
        subject = USER
    else:
        client, _, _, _, _, _ = standalone_fixture(tmp_path)
        login(client)
        subject = "a" * 32
    actual = f"v1:{INSTANCE}:edge:{subject}"
    stale = actual
    if changed == "installation":
        stale = actual.replace(INSTANCE, "00000000-0000-0000-0000-000000000000")
    if changed == "channel":
        stale = actual.replace(":edge:", ":stable:")
    if changed == "subject":
        stale = actual[:-32] + "f" * 32
    if changed == "empty":
        stale = ""
    assertion = [("X-Domus-Context", stale)]
    if changed == "duplicate":
        assertion *= 2
    csrf = client.get("/api/v1/auth/csrf").json()["csrf_token"]
    origin = str(client.base_url).rstrip("/")
    for path in ("/api/v1/session", "/api/v1/authorization", "/api/v1/auth/csrf"):
        result = client.get(path, headers=assertion)
        assert result.status_code == 403, result.text
        assert "installation_id" not in result.text and subject not in result.text
    result = client.post(
        "/api/v1/household",
        json={"name": "Home", "time_zone": "UTC", "expected_revision": 0},
        headers=assertion
        + [("Origin", origin), ("X-CSRF-Token", csrf), ("Idempotency-Key", "stale-context")],
    )
    assert result.status_code == 403
    assert client.get("/api/v1/authorization").json()["state"] == "unconfigured"
    if runtime:
        runtime.close()


def test_valid_assertion_preserves_strict_server_authorization_and_original_receipt(
    tmp_path: Path,
) -> None:
    client, _, _, _, _, _ = standalone_fixture(tmp_path)
    login(client)
    assertion = {"X-Domus-Context": f"v1:{INSTANCE}:edge:{'a' * 32}"}
    assert client.get("/api/v1/authorization", headers=assertion).json()["setup_allowed"]
    payload = {"name": "Home", "time_zone": "UTC", "expected_revision": 0}
    headers = {**write_headers(client, "original"), **assertion}
    result = client.post("/api/v1/household", json=payload, headers=headers)
    assert result.status_code == 200
    assert client.post("/api/v1/household", json=payload, headers=headers).json() == result.json()


@dataclass
class Clock:
    value: int

    def now(self) -> int:
        return self.value


def test_real_standalone_preview_composition_reports_stable_and_no_household_apis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, oauth, socket, clock = identity_fixture()

    def exchange(code: str, verifier: str):
        # This boundary fake accepts production entropy; fixed-verifier tests live in auth suites.
        assert code == "code" and len(verifier) == 43
        return oauth.issued

    monkeypatch.setattr(oauth, "exchange", exchange)
    monkeypatch.setattr(server, "HomeAssistantOAuth", lambda _: oauth)
    monkeypatch.setattr(server, "HomeAssistantWebSocket", lambda _: socket)
    monkeypatch.setattr(server, "MonotonicClock", lambda: clock)
    monkeypatch.setattr(server, "SystemClock", lambda: Clock(1_800_000_000_000))
    runtime = server.create_runtime("http://ha.local", "https://domus.example", INSTANCE, "stable")
    with TestClient(
        runtime.app, base_url="https://domus.example", follow_redirects=False
    ) as client:
        login(client)
        context = client.get("/api/v1/session").json()["context"]
        assert context["channel"] == "stable" and context["household_api_available"] is False
        assert context["application_base"] == "/" and context["deployment"] == "standalone"
        assert context["server_time"] == 1_800_000_000_000
        assert client.get("/api/v1/authorization").status_code == 404
    runtime.close()


def test_context_assertion_never_grants_ha_administrator_authority(tmp_path: Path) -> None:
    client, _, socket, _, _, _ = standalone_fixture(tmp_path)
    socket.human = replace(socket.human, is_administrator=False)
    login(client)
    assertion = {"X-Domus-Context": f"v1:{INSTANCE}:edge:{socket.human.ha_user_id}"}
    assert client.get("/api/v1/authorization", headers=assertion).json()["setup_allowed"] is False
    result = client.post(
        "/api/v1/household",
        json={"name": "Home", "time_zone": "UTC", "expected_revision": 0},
        headers={**write_headers(client), **assertion},
    )
    assert result.status_code == 403


def test_epoch_clock_changes_cannot_extend_an_existing_process_lease() -> None:
    lease, utc = Clock(100), Clock(1_800_000_000_000)
    entry = EntryHTTPContext(Installation(INSTANCE, "edge"), "standalone", lease, utc, True)
    request = Request({"type": "http", "headers": []})
    status = SessionStatus(HumanIdentity("a" * 32, True, True, False), True, 3_600_100)
    first = entry.describe(request, status)
    utc.value += 1_000_000
    lease.value += 1000
    later = entry.describe(request, status)
    assert later.server_time == first.server_time + 1000
    assert later.expires_at == first.expires_at


@pytest.mark.parametrize("value", [True, -1, 2**53])
@pytest.mark.parametrize("provider", ["lease", "utc"])
def test_invalid_clock_anchor_cannot_publish_context(value: int, provider: str) -> None:
    lease, utc = Clock(100), Clock(1_800_000_000_000)
    if provider == "lease":
        lease.value = value
    else:
        utc.value = value
    with pytest.raises(StorageFailure, match="invalid_entry_clock"):
        EntryHTTPContext(Installation(INSTANCE, "edge"), "standalone", lease, utc, True)


@pytest.mark.parametrize("change", ["regression", "invalid_now", "invalid_expiry", "overflow"])
def test_context_time_inconsistency_fails_closed(change: str) -> None:
    lease, utc = Clock(100), Clock(1_800_000_000_000)
    entry = EntryHTTPContext(Installation(INSTANCE, "edge"), "standalone", lease, utc, True)
    expiry = 3_600_100
    if change == "regression":
        lease.value = 99
    if change == "invalid_now":
        lease.value = -1
    if change == "invalid_expiry":
        expiry = -1
    if change == "overflow":
        expiry = 2**53 - 1
    with pytest.raises(StorageFailure, match="invalid_entry_clock"):
        entry.describe(
            Request({"type": "http", "headers": []}),
            SessionStatus(HumanIdentity("a" * 32, True, True, False), True, expiry),
        )


@pytest.mark.parametrize("mode,available", [("unknown", True), ("native", 1)])
def test_invalid_composition_declaration_fails_before_metadata(mode: str, available: bool) -> None:
    with pytest.raises(InvalidInput):
        EntryHTTPContext(Installation(INSTANCE, "edge"), mode, Clock(0), Clock(0), available)


@pytest.mark.parametrize("value", [b"x" * 257, b"\xff"])
def test_oversized_or_non_ascii_context_cannot_echo_or_select_identity(value: bytes) -> None:
    entry = EntryHTTPContext(Installation(INSTANCE, "edge"), "standalone", Clock(0), Clock(0), True)
    request = Request({"type": "http", "headers": [(b"x-domus-context", value)]})
    with pytest.raises(Forbidden, match="request_forbidden"):
        entry.require(request, HumanIdentity("a" * 32, True, True, False))


def test_legacy_native_factory_without_installation_metadata_never_invents_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = ingress.create_native_app

    def legacy(*args, **kwargs):
        kwargs.pop("entry")
        return original(*args, **kwargs)

    monkeypatch.setattr(ingress, "create_native_app", legacy)
    runtime, client, _, _ = native_fixture(tmp_path, monkeypatch)
    result = client.get("/api/v1/session")
    assert result.status_code == 200 and result.json()["context"] is None
    assert result.json()["expires_in"] == 3600
    # The frontend must treat missing context as unavailable; an assertion cannot opt it into trust.
    response = client.get("/api/v1/authorization", headers={"X-Domus-Context": "invented"})
    assert response.status_code == 403
    runtime.close()


@pytest.mark.parametrize("deployment", ["native", "standalone"])
def test_integrated_task_routes_share_the_verified_context_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, deployment: str
) -> None:
    runtime = None
    if deployment == "native":
        runtime, client, _, _ = native_fixture(tmp_path, monkeypatch)
        subject = USER
    else:
        client, _, _, _, _, _ = standalone_fixture(tmp_path)
        login(client)
        subject = "a" * 32
    origin = str(client.base_url).rstrip("/")
    csrf = client.get("/api/v1/auth/csrf").json()["csrf_token"]
    created = client.post(
        "/api/v1/household",
        json={"name": "Home", "time_zone": "UTC", "expected_revision": 0},
        headers={"Origin": origin, "X-CSRF-Token": csrf, "Idempotency-Key": "task-context-home"},
    )
    assert created.status_code == 200
    actual = f"v1:{INSTANCE}:edge:{subject}"
    assert (
        client.get("/api/v1/tasks/policy", headers={"X-Domus-Context": actual}).status_code == 200
    )
    rejected = client.get(
        "/api/v1/tasks/policy", headers={"X-Domus-Context": actual.replace(":edge:", ":stable:")}
    )
    assert rejected.status_code == 403 and "default_rules" not in rejected.text
    assert (
        client.get("/api/v1/tasks/policy", headers={"X-Domus-Context": actual}).status_code == 200
    )
    if runtime:
        runtime.close()
