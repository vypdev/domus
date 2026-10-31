"""Correlated HA proof over a fixed, bounded and nonredirecting WebSocket endpoint."""

import asyncio
import json
import logging
import re
from asyncio import timeout
from dataclasses import dataclass
from typing import cast

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed, InvalidStatus, WebSocketException

from domus.domain.errors import (
    DomusError,
    Forbidden,
    IdentityRejected,
    IdentityUnavailable,
    InvalidInput,
)
from domus.domain.identity import HumanIdentity
from domus.domain.storage import JsonDocument, JsonObject, JsonValue
from domus.infrastructure.ha_config import HAEndpoint
from domus.infrastructure.ha_http import OAuthTokens, _secret

# A private logger prevents library wire-debug settings from recording auth frames.
_WIRE_LOGGER = logging.Logger("domus.ha.private-wire")
_WIRE_LOGGER.disabled = True


class _FixedEndpoint(connect):
    """Pinned websockets 17.4 hook; real redirect fixtures guard upgrades."""

    def process_redirect(self, exc: Exception) -> Exception | str:
        return exc


def _user_id(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{32}", value):
        raise InvalidInput("invalid_ha_user_id")
    return value


async def _message(connection: ClientConnection) -> JsonObject:
    message = await connection.recv()
    if not isinstance(message, str):
        raise IdentityRejected("invalid_ha_protocol")
    return JsonDocument(message).decode()


@dataclass(frozen=True, slots=True)
class HomeAssistantWebSocket:
    endpoint: HAEndpoint

    async def _exchange(self, token: str, operation: str) -> JsonValue:
        try:
            async with (
                timeout(5),
                _FixedEndpoint(
                    self.endpoint.websocket_url,
                    proxy=None,
                    compression=None,
                    open_timeout=2,
                    close_timeout=0.25,
                    max_size=65_536,
                    max_queue=4,
                    ping_interval=None,
                    logger=_WIRE_LOGGER,
                ) as connection,
            ):
                if (await _message(connection)).get("type") != "auth_required":
                    raise IdentityRejected("invalid_ha_protocol")
                await connection.send(json.dumps({"type": "auth", "access_token": token}))
                authentication = await _message(connection)
                if authentication.get("type") == "auth_invalid":
                    raise IdentityRejected("ha_rejected")
                if authentication.get("type") != "auth_ok":
                    raise IdentityRejected("invalid_ha_protocol")
                await connection.send(json.dumps({"id": 1, "type": operation}))
                response = await _message(connection)
                if (
                    response.get("type") != "result"
                    or type(response.get("id")) is not int
                    or response["id"] != 1
                ):
                    raise IdentityRejected("invalid_ha_protocol")
                if response.get("success") is False:
                    if operation == "config/auth/list":
                        raise Forbidden("ha_directory_forbidden")
                    raise IdentityRejected("ha_rejected")
                if response.get("success") is not True or "result" not in response:
                    raise IdentityRejected("invalid_ha_protocol")
                return response["result"]
        except InvalidStatus as error:
            status = error.response.status_code
            if status == 429 or status >= 500:
                raise IdentityUnavailable("ha_unavailable") from None
            raise IdentityRejected("invalid_ha_protocol") from None
        except ConnectionClosed as error:
            if (error.sent is not None and error.sent.code == 1009) or (
                error.rcvd is not None and error.rcvd.code == 1009
            ):
                raise IdentityRejected("invalid_ha_protocol") from None
            raise IdentityUnavailable("ha_unavailable") from None
        except TimeoutError, OSError:
            raise IdentityUnavailable("ha_unavailable") from None
        except WebSocketException, InvalidInput, ValueError:
            raise IdentityRejected("invalid_ha_protocol") from None

    def _request(self, token: str, operation: str) -> JsonValue:
        _secret(token)
        return asyncio.run(self._exchange(token, operation))

    def current_user(self, grant: OAuthTokens) -> HumanIdentity:
        """Use only a server-exchanged client grant, never an incoming bearer token.

        HA 2026.10.4 rejects system users when creating a client-bound refresh
        token and enforces active users during authentication. current_user alone
        lacks system/active flags; that OAuth provenance is required here.
        """
        result = self._request(grant.access_token, "auth/current_user")
        try:
            if not isinstance(result, dict):
                raise InvalidInput("invalid_ha_identity")
            user_id = _user_id(result["id"])
            credentials = result["credentials"]
            if (
                not isinstance(credentials, list)
                or not 1 <= len(credentials) <= 32
                or any(not isinstance(item, dict) for item in credentials)
                or not any(
                    cast(JsonObject, item).get("auth_provider_type") == grant.provider
                    for item in credentials
                )
            ):
                raise InvalidInput("invalid_ha_identity")
            return HumanIdentity(user_id, cast(bool, result["is_admin"]), True, False)
        except DomusError, KeyError:
            raise IdentityRejected("invalid_ha_protocol") from None

    def directory_user(self, transport_token: str, ha_user_id: str) -> HumanIdentity:
        """Supervisor's credential only transports the exact subject lookup."""
        _user_id(ha_user_id)
        records = self._request(transport_token, "config/auth/list")
        try:
            if not isinstance(records, list) or len(records) > 256:
                raise InvalidInput("invalid_ha_directory")
            seen: set[str] = set()
            target: JsonObject | None = None
            for record in records:
                if not isinstance(record, dict):
                    raise InvalidInput("invalid_ha_directory")
                identity = _user_id(record["id"])
                if identity in seen:
                    raise InvalidInput("invalid_ha_directory")
                seen.add(identity)
                if identity == ha_user_id:
                    target = record
            if target is None:
                raise IdentityRejected("ha_subject_rejected")
            owner = target["is_owner"]
            if type(owner) is not bool:
                raise InvalidInput("invalid_ha_directory")
            groups = target["group_ids"]
            if (
                not isinstance(groups, list)
                or len(groups) > 32
                or any(not isinstance(group, str) for group in groups)
            ):
                raise InvalidInput("invalid_ha_directory")
            return HumanIdentity(
                ha_user_id,
                owner or "system-admin" in groups,
                cast(bool, target["is_active"]),
                cast(bool, target["system_generated"]),
            )
        except DomusError, KeyError:
            raise IdentityRejected("ha_subject_rejected") from None
