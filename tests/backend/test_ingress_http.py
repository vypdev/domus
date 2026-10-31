"""Native HA entry proves the actual peer and exact human without another sign-in."""

import pytest
from fastapi.testclient import TestClient

from domus.domain.errors import (
    DomusError,
    Forbidden,
    IdentityRejected,
    IdentityUnavailable,
    InvalidInput,
)
from domus.domain.identity import HumanIdentity
from domus.entrypoints.ingress_http import create_ingress_app
from domus.infrastructure.ha_config import HAEndpoint
from domus.infrastructure.ha_ingress import SupervisorIdentity

SUBJECT = "a" * 32
PREFIX = "/api/hassio_ingress/" + "b" * 32


class Lookup:
    endpoint = HAEndpoint.supervisor()

    def __init__(self) -> None:
        self.calls = []
        self.error = None

    def directory_user(self, token: str, subject: str) -> HumanIdentity:
        assert token == "private-supervisor-token"
        self.calls.append(subject)
        if self.error:
            raise self.error
        return HumanIdentity(subject, False, True, False)


def fixture(peer: str | None = "172.30.32.2", channel: str = "edge") -> tuple:
    lookup = Lookup()
    identity = SupervisorIdentity(lookup, "private-supervisor-token")
    app = create_ingress_app(identity.prove, channel, correlation=lambda: "cor_fixture")
    return (
        TestClient(
            app,
            client=(peer, 12000) if peer is not None else None,
            headers={"X-Ingress-Path": PREFIX, "X-Remote-User-Id": SUBJECT},
            raise_server_exceptions=False,
        ),
        lookup,
    )


@pytest.mark.parametrize("channel", ["stable", "edge"])
def test_native_home_uses_ha_identity_without_oauth_cookie_or_external_assets(channel: str) -> None:
    client, lookup = fixture(channel=channel)
    response = client.get("/")
    assert response.status_code == 200
    assert f"Domus {channel.title()}" in response.text
    assert "No additional login is required" in response.text
    assert "Household setup is not available" in response.text
    assert 'href="./"' in response.text and '<html lang="en">' in response.text
    assert SUBJECT not in response.text and "private-supervisor-token" not in response.text
    assert "set-cookie" not in response.headers and client.cookies == {}
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "default-src 'none'" in response.headers["content-security-policy"]
    assert lookup.calls == [SUBJECT]


def test_identity_endpoint_requires_fresh_lookup_each_time_without_technical_user_promotion() -> (
    None
):
    client, lookup = fixture()
    for _ in range(2):
        response = client.get("/api/v1/identity")
        assert response.status_code == 200
        assert response.json()["ha_user_id"] == SUBJECT
        assert response.json()["ha_administrator"] is False
        assert response.json()["source"] == "home_assistant_ingress"
        assert "token" not in response.text and "session_id" not in response.text
    assert lookup.calls == [SUBJECT, SUBJECT]


@pytest.mark.parametrize("peer", ["127.0.0.1", "172.30.33.4", "192.168.1.2"])
def test_forged_source_headers_do_not_override_actual_peer(peer: str) -> None:
    client, lookup = fixture(peer)
    response = client.get("/", headers={"X-Forwarded-For": "172.30.32.2"})
    assert response.status_code == 403
    assert "Home Assistant app page" in response.json()["action_required"]
    assert lookup.calls == []


@pytest.mark.parametrize(
    "prefixes", [[], ["/wrong"], [PREFIX + "/../"], [PREFIX + "?query"], [PREFIX, PREFIX]]
)
def test_untrusted_or_ambiguous_base_paths_are_rejected_before_ha_lookup(prefixes: list) -> None:
    client, lookup = fixture()
    client.headers.clear()
    response = client.get(
        "/", headers=[("X-Remote-User-Id", SUBJECT)] + [("X-Ingress-Path", p) for p in prefixes]
    )
    assert response.status_code == 403 and lookup.calls == []


@pytest.mark.parametrize("subjects", [[], ["invalid"], [SUBJECT, SUBJECT]])
def test_missing_malformed_or_duplicate_identity_is_never_a_default_user(subjects: list) -> None:
    client, lookup = fixture()
    client.headers.clear()
    response = client.get(
        "/", headers=[("X-Ingress-Path", PREFIX)] + [("X-Remote-User-Id", s) for s in subjects]
    )
    assert response.status_code == 401 and lookup.calls == []


@pytest.mark.parametrize(
    "error,status",
    [
        (IdentityUnavailable("private-upstream-detail"), 503),
        (IdentityRejected("private-upstream-detail"), 401),
        (Forbidden("private-upstream-detail"), 403),
        (Forbidden("ha_directory_forbidden"), 403),
        (DomusError("private-upstream-detail"), 500),
        (RuntimeError("private-upstream-detail"), 500),
    ],
)
def test_provider_failure_is_safe_and_never_starts_an_oauth_flow(
    error: Exception, status: int
) -> None:
    client, lookup = fixture()
    lookup.error = error
    response = client.get("/api/v1/identity")
    assert response.status_code == status
    assert "private-upstream-detail" not in response.text
    assert "No separate Domus login is required" in response.json()["action_required"]
    assert "location" not in response.headers and "set-cookie" not in response.headers


@pytest.mark.parametrize("peer", ["127.0.0.1", "::1", "172.30.32.2"])
def test_process_health_is_nonpersonal_and_does_not_claim_ha_availability(peer: str) -> None:
    client, lookup = fixture(peer)
    client.headers.clear()
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "scope": "process"}
    assert lookup.calls == []


@pytest.mark.parametrize("path", ["/api/v1/auth/start", "/docs", "/api/v1/recovery/approve"])
def test_preview_exposes_no_standalone_oauth_or_business_command_route(path: str) -> None:
    client, lookup = fixture()
    assert client.get(path).status_code == 404
    assert lookup.calls == []


def test_invalid_channel_oversized_headers_queries_bodies_and_mutations_are_rejected() -> None:
    with pytest.raises(InvalidInput):
        fixture(channel="unknown")
    client, lookup = fixture()
    assert client.get("/?member_id=another").status_code == 422
    assert client.get("/", headers={"X-Large": "x" * 16_384}).status_code == 422
    assert client.get("/", headers={f"X-{i}": "x" for i in range(101)}).status_code == 422
    assert client.request("GET", "/", content="body").status_code == 422
    assert client.post("/api/v1/identity", json={}).status_code == 403
    assert client.delete("/").status_code == 403
    assert lookup.calls == []


def test_missing_socket_peer_and_unknown_health_peer_fail_closed() -> None:
    client, lookup = fixture("172.30.33.4")
    assert client.get("/health").status_code == 403
    client, lookup = fixture(None)
    assert client.get("/").status_code == 403
    assert lookup.calls == []


def test_head_is_not_a_hidden_identity_or_mutation_handler() -> None:
    client, lookup = fixture()
    # HEAD is admitted by the boundary but has no mutation or identity handler.
    assert client.head("/").status_code == 405
    assert lookup.calls == []
