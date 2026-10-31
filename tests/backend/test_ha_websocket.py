"""Disposable loopback HA protocol fixtures exercise the pinned real WebSocket client."""

import asyncio
import json
import logging
import socket
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from threading import Thread

import pytest
from websockets.http11 import Response
from websockets.sync.server import ServerConnection, serve

from domus.domain.errors import Forbidden, IdentityRejected, IdentityUnavailable, InvalidInput
from domus.domain.identity import HumanIdentity
from domus.infrastructure.ha_config import HAEndpoint
from domus.infrastructure.ha_http import OAuthTokens
from domus.infrastructure.ha_websocket import HomeAssistantWebSocket

USER = "a" * 32
GRANT = OAuthTokens("fixture-access", "fixture-refresh", 1800, "homeassistant")
CURRENT = {
    "id": USER,
    "is_admin": True,
    "credentials": [{"auth_provider_type": "homeassistant", "auth_provider_id": None}],
}


@contextmanager
def provider(handler: Callable[[ServerConnection], None], **kwargs: object) -> Iterator[HAEndpoint]:
    with serve(handler, "127.0.0.1", 0, ping_interval=None, close_timeout=0.2, **kwargs) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield HAEndpoint(f"http://127.0.0.1:{server.socket.getsockname()[1]}")
        finally:
            server.shutdown()
            thread.join(timeout=3)
            assert not thread.is_alive()


def scenario(
    result: object,
    *,
    operation: str = "auth/current_user",
    response_id: object = 1,
    success: object = True,
) -> Callable[[ServerConnection], None]:
    def handle(connection: ServerConnection) -> None:
        connection.send(json.dumps({"type": "auth_required", "ha_version": "2026.10.4"}))
        assert json.loads(connection.recv()) == {"type": "auth", "access_token": "fixture-access"}
        connection.send(json.dumps({"type": "auth_ok", "ha_version": "2026.10.4"}))
        assert json.loads(connection.recv()) == {"type": operation, "id": 1}
        connection.send(
            json.dumps({"type": "result", "id": response_id, "success": success, "result": result})
        )

    return handle


def test_oauth_current_user_proves_exact_human_and_boolean_admin() -> None:
    with provider(scenario(CURRENT)) as endpoint:
        assert HomeAssistantWebSocket(endpoint).current_user(GRANT) == HumanIdentity(
            USER, True, True, False
        )
    with provider(scenario({**CURRENT, "is_admin": False})) as endpoint:
        assert not HomeAssistantWebSocket(endpoint).current_user(GRANT).is_administrator


@pytest.mark.parametrize(
    "result",
    [
        {**CURRENT, "id": "person.someone"},
        {**CURRENT, "is_admin": 1},
        {**CURRENT, "credentials": []},
        {**CURRENT, "credentials": "wrong"},
        {**CURRENT, "credentials": [None]},
        {**CURRENT, "credentials": [{"auth_provider_type": "other"}]},
        [],
        {},
    ],
)
def test_malformed_or_nonhuman_current_user_cannot_become_identity(result: object) -> None:
    with provider(scenario(result)) as endpoint:
        with pytest.raises(IdentityRejected, match="invalid_ha_protocol"):
            HomeAssistantWebSocket(endpoint).current_user(GRANT)


@pytest.mark.parametrize("response_id,success", [(2, True), (True, True), (1, 1), (1, False)])
def test_response_correlation_and_success_are_exact(response_id: object, success: object) -> None:
    with provider(scenario(CURRENT, response_id=response_id, success=success)) as endpoint:
        with pytest.raises(IdentityRejected):
            HomeAssistantWebSocket(endpoint).current_user(GRANT)


def test_directory_uses_group_source_and_explicit_system_active_flags() -> None:
    records = [
        {
            "id": USER,
            "is_owner": False,
            "is_active": True,
            "system_generated": False,
            "group_ids": ["system-admin"],
        }
    ]
    with provider(scenario(records, operation="config/auth/list")) as endpoint:
        assert (
            HomeAssistantWebSocket(endpoint).directory_user("fixture-access", USER).is_administrator
        )
    records[0]["group_ids"] = ["system-users"]
    with provider(scenario(records, operation="config/auth/list")) as endpoint:
        assert (
            not HomeAssistantWebSocket(endpoint)
            .directory_user("fixture-access", USER)
            .is_administrator
        )


@pytest.mark.parametrize(
    "records",
    [
        [],
        [
            {
                "id": USER,
                "is_owner": False,
                "is_active": False,
                "system_generated": False,
                "group_ids": [],
            }
        ],
        [
            {
                "id": USER,
                "is_owner": True,
                "is_active": True,
                "system_generated": True,
                "group_ids": [],
            }
        ],
        [
            {
                "id": USER,
                "is_owner": False,
                "is_active": 1,
                "system_generated": False,
                "group_ids": [],
            }
        ],
        [
            {
                "id": USER,
                "is_owner": False,
                "is_active": True,
                "system_generated": False,
                "group_ids": "system-admin",
            }
        ],
        [
            {
                "id": USER,
                "is_owner": False,
                "is_active": True,
                "system_generated": False,
                "group_ids": [1],
            }
        ],
        [
            {
                "id": USER,
                "is_owner": 1,
                "is_active": True,
                "system_generated": False,
                "group_ids": [],
            }
        ],
        [None],
        {},
        [{"id": "bad"}],
        [{"id": USER}, {"id": USER}],
    ],
)
def test_directory_rejects_missing_inactive_technical_malformed_or_duplicate_subject(
    records: object,
) -> None:
    with provider(scenario(records, operation="config/auth/list")) as endpoint:
        with pytest.raises(IdentityRejected):
            HomeAssistantWebSocket(endpoint).directory_user("fixture-access", USER)


def test_directory_permission_denial_is_distinct_from_own_identity_rejection() -> None:
    with provider(scenario(None, operation="config/auth/list", success=False)) as endpoint:
        with pytest.raises(Forbidden, match="ha_directory_forbidden"):
            HomeAssistantWebSocket(endpoint).directory_user("fixture-access", USER)


@pytest.mark.parametrize(
    "message",
    [b"binary", "not-json", '{"type":"a","type":"b"}', '{"type":"unexpected"}', "x" * 70_000],
)
def test_invalid_or_oversized_handshake_is_not_outage_grace(message: str | bytes) -> None:
    def handle(connection: ServerConnection) -> None:
        connection.send(message)

    with provider(handle) as endpoint:
        with pytest.raises(IdentityRejected):
            HomeAssistantWebSocket(endpoint).current_user(GRANT)


def test_explicit_auth_rejection_does_not_grant_outage_access() -> None:
    def handle(connection: ServerConnection) -> None:
        connection.send('{"type":"auth_required"}')
        connection.recv()
        connection.send('{"type":"auth_invalid","message":"private-provider-detail"}')

    with provider(handle) as endpoint:
        with pytest.raises(IdentityRejected, match="ha_rejected") as failure:
            HomeAssistantWebSocket(endpoint).current_user(GRANT)
        assert "private" not in str(failure.value)


def test_early_disconnect_is_unavailable_and_pinned_redirect_hook_never_contacts_other_origin() -> (
    None
):
    with provider(lambda connection: connection.close()) as endpoint:
        with pytest.raises(IdentityUnavailable):
            HomeAssistantWebSocket(endpoint).current_user(GRANT)
    visited = []
    with provider(lambda connection: visited.append(True)) as other:

        def redirect(connection: ServerConnection, request: object) -> Response:
            response = connection.respond(302, "Moved")
            response.headers["Location"] = other.websocket_url
            return response

        with provider(
            lambda _: pytest.fail("Redirect must not open a protocol"), process_request=redirect
        ) as endpoint:
            with pytest.raises(IdentityRejected):
                HomeAssistantWebSocket(endpoint).current_user(GRANT)
    assert visited == []


def test_invalid_directory_subject_is_rejected_before_connect() -> None:
    with pytest.raises(InvalidInput):
        HomeAssistantWebSocket(HAEndpoint("http://ha.invalid")).directory_user(
            "fixture-access", "bad-id"
        )


def test_wrong_auth_acknowledgement_is_a_protocol_rejection() -> None:
    def handle(connection: ServerConnection) -> None:
        connection.send('{"type":"auth_required"}')
        connection.recv()
        connection.send('{"type":"unexpected"}')

    with provider(handle) as endpoint:
        with pytest.raises(IdentityRejected, match="invalid_ha_protocol"):
            HomeAssistantWebSocket(endpoint).current_user(GRANT)


@pytest.mark.parametrize("status", [429, 503])
def test_temporary_handshake_failure_is_availability(status: int) -> None:
    def unavailable(connection: ServerConnection, request: object) -> Response:
        return connection.respond(status, "private failure detail")

    with provider(lambda _: None, process_request=unavailable) as endpoint:
        with pytest.raises(IdentityUnavailable, match="ha_unavailable"):
            HomeAssistantWebSocket(endpoint).current_user(GRANT)


def test_connection_refusal_is_safe_unavailability() -> None:
    with socket.socket() as unlistening:
        unlistening.bind(("127.0.0.1", 0))
        endpoint = HAEndpoint(f"http://127.0.0.1:{unlistening.getsockname()[1]}")
        with pytest.raises(IdentityUnavailable, match="ha_unavailable"):
            HomeAssistantWebSocket(endpoint).current_user(GRANT)


def test_directory_ignores_another_users_admin_flag_and_wire_logging_is_private(
    caplog: pytest.LogCaptureFixture,
) -> None:
    records = [
        {
            "id": "b" * 32,
            "is_owner": False,
            "is_active": True,
            "system_generated": False,
            "group_ids": ["system-admin"],
        },
        {
            "id": USER,
            "is_owner": False,
            "is_active": True,
            "system_generated": False,
            "group_ids": [],
        },
    ]
    with caplog.at_level(logging.DEBUG, logger="websockets.client"):
        with provider(scenario(records, operation="config/auth/list")) as endpoint:
            assert (
                not HomeAssistantWebSocket(endpoint)
                .directory_user("fixture-access", USER)
                .is_administrator
            )
    assert "fixture-access" not in caplog.text


def test_ha_owner_remains_administrator_without_administrator_group() -> None:
    records = [
        {
            "id": USER,
            "is_owner": True,
            "is_active": True,
            "system_generated": False,
            "group_ids": [],
        }
    ]
    with provider(scenario(records, operation="config/auth/list")) as endpoint:
        assert (
            HomeAssistantWebSocket(endpoint).directory_user("fixture-access", USER).is_administrator
        )


def test_websocket_absolute_deadline_is_enforced_without_business_sleeps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from domus.infrastructure import ha_websocket

    real_timeout = asyncio.timeout

    def immediate_deadline(seconds: float) -> asyncio.Timeout:
        assert seconds == 5
        return real_timeout(0)

    monkeypatch.setattr(ha_websocket, "timeout", immediate_deadline)
    with provider(lambda _: None) as endpoint:
        with pytest.raises(IdentityUnavailable, match="ha_unavailable"):
            HomeAssistantWebSocket(endpoint).current_user(GRANT)
