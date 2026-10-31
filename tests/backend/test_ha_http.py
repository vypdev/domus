"""HA OAuth transport uses fixed validated origins and never exposes token payloads."""

import asyncio
from urllib.parse import parse_qs

import httpx
import pytest

from domus.domain.errors import IdentityRejected, IdentityUnavailable, InvalidInput
from domus.infrastructure.ha_config import HAEndpoint, OAuthConfiguration
from domus.infrastructure.ha_http import HomeAssistantOAuth

VERIFIER = "v" * 43
TOKEN = {
    "access_token": "private-access",
    "refresh_token": "private-refresh",
    "expires_in": 1800,
    "token_type": "Bearer",
    "ha_auth_provider": "homeassistant",
}


def configuration() -> OAuthConfiguration:
    return OAuthConfiguration(
        HAEndpoint("http://homeassistant.local:8123"), "https://domus.example"
    )


def test_configuration_normalizes_fixed_origins_and_supervisor_socket_path() -> None:
    config = OAuthConfiguration(HAEndpoint("https://HA.EXAMPLE:443/"), "https://DOMUS.EXAMPLE/")
    assert config.ha.origin == "https://ha.example"
    assert config.ha.websocket_url == "wss://ha.example/api/websocket"
    assert config.client_id == "https://domus.example/"
    assert config.callback_url == "https://domus.example/api/v1/auth/callback"
    assert (
        HAEndpoint("http://homeassistant.local:8123").websocket_url
        == "ws://homeassistant.local:8123/api/websocket"
    )
    supervisor = HAEndpoint.supervisor()
    assert supervisor.websocket_url == "ws://supervisor/core/websocket"
    assert supervisor.host == "supervisor" and supervisor.port == 80
    with pytest.raises(InvalidInput, match="invalid_ha_endpoint"):
        HAEndpoint("http://other", supervised=True)
    with pytest.raises(InvalidInput, match="supervisor_uses_ingress"):
        OAuthConfiguration(supervisor, "https://domus.example")


@pytest.mark.parametrize(
    "url",
    [
        "",
        "ftp://host",
        "https://user:password@host",
        "https://host/path",
        "https://host?x=1",
        "https://host#fragment",
        "https://host?",
        "https://host#",
        "https://host:0",
        "https://host:65536",
        "https://host:bad",
        "https://host\\evil",
        "https://host/\n",
        "https://%68ost",
        "https://",
        "https://[invalid]",
        "https://[fe80::1%25eth0]",
        "https://a..example",
        123,
        "https://" + "x" * 2049,
    ],
)
def test_invalid_operator_origin_is_rejected_before_io(url: object) -> None:
    with pytest.raises(InvalidInput, match="invalid_origin"):
        HAEndpoint(url)


def test_public_http_requires_explicit_loopback_development_and_ipv6_is_preserved() -> None:
    for url in ("http://localhost:8099", "http://127.0.0.1:8099", "http://[::1]:8099"):
        with pytest.raises(InvalidInput, match="insecure_public_origin"):
            OAuthConfiguration(HAEndpoint("http://ha.local"), url)
        assert (
            OAuthConfiguration(
                HAEndpoint("http://ha.local"), url, development_http=True
            ).public_origin
            == url
        )
    with pytest.raises(InvalidInput, match="insecure_public_origin"):
        OAuthConfiguration(
            HAEndpoint("http://ha.local"), "http://localhost.evil", development_http=True
        )
    assert HAEndpoint("https://[::1]:8123").host == "::1"
    assert HAEndpoint("http://127.0.0.1").port == 80
    assert HAEndpoint("https://ha.local").port == 443


def test_code_exchange_is_exact_server_side_form_and_token_repr_is_redacted() -> None:
    requests = []

    def provider(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert str(request.url) == "http://homeassistant.local:8123/auth/token"
        assert request.headers["content-type"].startswith("application/x-www-form-urlencoded")
        assert parse_qs(request.content.decode()) == {
            "grant_type": ["authorization_code"],
            "code": ["approved-code"],
            "client_id": ["https://domus.example/"],
            "code_verifier": [VERIFIER],
        }
        return httpx.Response(200, json=TOKEN)

    tokens = HomeAssistantOAuth(configuration(), transport=httpx.MockTransport(provider)).exchange(
        "approved-code", VERIFIER
    )
    assert (
        tokens.access_token == TOKEN["access_token"]
        and tokens.refresh_token == TOKEN["refresh_token"]
    )
    assert tokens.expires_in == 1800 and tokens.provider == "homeassistant"
    assert "private-access" not in repr(tokens) and "private-refresh" not in repr(tokens)
    assert len(requests) == 1


def test_refresh_and_revoke_use_fixed_client_and_do_not_change_refresh_identity() -> None:
    calls = []

    def provider(request: httpx.Request) -> httpx.Response:
        calls.append(parse_qs(request.content.decode()))
        if request.url.path == "/auth/revoke":
            return httpx.Response(200)
        return httpx.Response(
            200, json={"access_token": "new-access", "expires_in": 1800, "token_type": "Bearer"}
        )

    client = HomeAssistantOAuth(configuration(), transport=httpx.MockTransport(provider))
    renewed = client.refresh("private-refresh", "homeassistant")
    assert renewed.refresh_token == "private-refresh" and renewed.access_token == "new-access"
    assert renewed.provider == "homeassistant"
    client.revoke("private-refresh")
    assert calls == [
        {
            "grant_type": ["refresh_token"],
            "refresh_token": ["private-refresh"],
            "client_id": ["https://domus.example/"],
        },
        {"token": ["private-refresh"]},
    ]


@pytest.mark.parametrize(
    "status,exception",
    [
        (400, IdentityRejected),
        (401, IdentityRejected),
        (403, IdentityRejected),
        (302, IdentityRejected),
        (429, IdentityUnavailable),
        (500, IdentityUnavailable),
        (204, IdentityRejected),
    ],
)
def test_provider_status_is_allowlisted_and_redirects_are_never_followed(
    status: int, exception: type[Exception]
) -> None:
    calls = []

    def provider(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(
            status,
            headers={"location": "https://attacker.example/private"},
            text="private-provider-details",
        )

    client = HomeAssistantOAuth(configuration(), transport=httpx.MockTransport(provider))
    with pytest.raises(exception) as failure:
        client.exchange("code", VERIFIER)
    assert "private" not in str(failure.value)
    assert calls == ["http://homeassistant.local:8123/auth/token"]


@pytest.mark.parametrize(
    "change", ["access", "refresh", "expiry", "bool_expiry", "type", "provider"]
)
def test_malformed_token_result_cannot_become_a_grant(change: str) -> None:
    payload = dict(TOKEN)
    if change == "access":
        payload["access_token"] = ""
    elif change == "refresh":
        payload.pop("refresh_token")
    elif change == "expiry":
        payload["expires_in"] = 0
    elif change == "bool_expiry":
        payload["expires_in"] = True
    elif change == "type":
        payload["token_type"] = "Other"
    else:
        payload["ha_auth_provider"] = "unsafe provider"
    client = HomeAssistantOAuth(
        configuration(), transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
    )
    with pytest.raises(IdentityRejected, match="invalid_ha_protocol"):
        client.exchange("code", VERIFIER)


@pytest.mark.parametrize("content", [b"not json", b'{"a":1,"a":2}', b"[]", b"\xff", b" " * 65_537])
def test_invalid_duplicate_oversized_and_non_utf8_response_fails_closed(content: bytes) -> None:
    client = HomeAssistantOAuth(
        configuration(),
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=content)),
    )
    with pytest.raises(IdentityRejected, match="invalid_ha_protocol"):
        client.exchange("code", VERIFIER)


@pytest.mark.parametrize(
    "error", [httpx.ConnectError("private-address"), httpx.ReadTimeout("private-token")]
)
def test_network_errors_are_availability_without_transport_detail(
    error: httpx.RequestError,
) -> None:
    def provider(_: httpx.Request) -> httpx.Response:
        raise error

    client = HomeAssistantOAuth(configuration(), transport=httpx.MockTransport(provider))
    with pytest.raises(IdentityUnavailable, match="ha_unavailable") as failure:
        client.exchange("code", VERIFIER)
    assert "private" not in str(failure.value)


@pytest.mark.parametrize(
    "code,verifier", [("", VERIFIER), ("code", "short"), ("bad code", VERIFIER)]
)
def test_invalid_code_or_pkce_verifier_is_not_transmitted(code: str, verifier: str) -> None:
    def forbidden_io(_: httpx.Request) -> httpx.Response:
        pytest.fail("Invalid input must not contact HA")

    with pytest.raises(InvalidInput):
        HomeAssistantOAuth(configuration(), transport=httpx.MockTransport(forbidden_io)).exchange(
            code, verifier
        )


def test_nonempty_revocation_response_and_unsolicited_encoding_are_rejected() -> None:
    client = HomeAssistantOAuth(
        configuration(),
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=b"unexpected body")),
    )
    with pytest.raises(IdentityRejected, match="invalid_ha_protocol"):
        client.revoke("private-refresh")
    client = HomeAssistantOAuth(
        configuration(),
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, headers={"content-encoding": "unsupported"})
        ),
    )
    with pytest.raises(IdentityRejected, match="invalid_ha_protocol"):
        client.exchange("code", VERIFIER)


def test_absolute_budget_cancels_a_blocked_provider_without_real_waits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from domus.infrastructure import ha_http

    real_timeout = asyncio.timeout

    def immediate_deadline(seconds: float) -> asyncio.Timeout:
        assert seconds == 5
        return real_timeout(0)

    async def blocked(request: httpx.Request) -> httpx.Response:
        await asyncio.Event().wait()
        pytest.fail("An indefinitely blocked provider must be cancelled")

    monkeypatch.setattr(ha_http, "timeout", immediate_deadline)
    client = HomeAssistantOAuth(configuration(), transport=httpx.MockTransport(blocked))
    with pytest.raises(IdentityUnavailable, match="ha_unavailable"):
        client.exchange("code", VERIFIER)
