"""Bounded server-side HA OAuth form exchange with no redirects or environment proxies."""

import asyncio
import re
from asyncio import timeout
from dataclasses import dataclass, field
from typing import cast

import httpx

from domus.domain.errors import DomusError, IdentityRejected, IdentityUnavailable, InvalidInput
from domus.domain.storage import JsonDocument, JsonObject
from domus.infrastructure.ha_config import OAuthConfiguration


def _secret(value: str, *, minimum: int = 1, maximum: int = 8192) -> None:
    if (
        not isinstance(value, str)
        or not minimum <= len(value) <= maximum
        or not re.fullmatch(r"[A-Za-z0-9._~-]+", value)
    ):
        raise InvalidInput("invalid_auth_value")


@dataclass(frozen=True, slots=True)
class OAuthTokens:
    """Private, process-local transport state; never a DTO or business record."""

    access_token: str = field(repr=False)
    refresh_token: str = field(repr=False)
    expires_in: int
    provider: str

    def __post_init__(self) -> None:
        _secret(self.access_token)
        _secret(self.refresh_token)
        if (
            type(self.expires_in) is not int
            or not 1 <= self.expires_in <= 86_400
            or not isinstance(self.provider, str)
            or not re.fullmatch(r"[a-z0-9_-]{1,128}", self.provider)
        ):
            raise InvalidInput("invalid_auth_value")


@dataclass
class HomeAssistantOAuth:
    configuration: OAuthConfiguration
    transport: httpx.AsyncBaseTransport | None = field(default=None, repr=False)

    def _post(self, path: str, values: dict[str, str], *, document: bool = True) -> JsonObject:
        return asyncio.run(self._post_bounded(path, values, document=document))

    async def _post_bounded(
        self, path: str, values: dict[str, str], *, document: bool
    ) -> JsonObject:
        try:
            async with (
                timeout(5),
                httpx.AsyncClient(
                    trust_env=False,
                    follow_redirects=False,
                    timeout=httpx.Timeout(3, connect=2),
                    transport=self.transport,
                    headers={"Accept-Encoding": "identity"},
                ) as client,
            ):
                async with client.stream(
                    "POST", self.configuration.ha.origin + path, data=values
                ) as response:
                    if response.status_code == 429 or response.status_code >= 500:
                        raise IdentityUnavailable("ha_unavailable")
                    if response.status_code in (400, 401, 403):
                        raise IdentityRejected("ha_rejected")
                    if (
                        response.status_code != 200
                        or response.headers.get("content-encoding", "identity") != "identity"
                    ):
                        raise IdentityRejected("invalid_ha_protocol")
                    payload = bytearray()
                    async for chunk in response.aiter_bytes():
                        payload.extend(chunk)
                        if len(payload) > 65_536:
                            raise IdentityRejected("invalid_ha_protocol")
                    if not document:
                        if payload:
                            raise IdentityRejected("invalid_ha_protocol")
                        return {}
                    return JsonDocument(payload.decode("utf-8")).decode()
        except httpx.RequestError, TimeoutError:
            raise IdentityUnavailable("ha_unavailable") from None
        except InvalidInput, UnicodeError:
            raise IdentityRejected("invalid_ha_protocol") from None

    @staticmethod
    def _tokens(
        payload: JsonObject, *, refresh: str | None = None, provider: str | None = None
    ) -> OAuthTokens:
        try:
            if payload["token_type"] != "Bearer":
                raise InvalidInput("invalid_auth_value")
            return OAuthTokens(
                cast(str, payload["access_token"]),
                refresh if refresh is not None else cast(str, payload["refresh_token"]),
                cast(int, payload["expires_in"]),
                provider if provider is not None else cast(str, payload["ha_auth_provider"]),
            )
        except DomusError, KeyError:
            raise IdentityRejected("invalid_ha_protocol") from None

    def exchange(self, code: str, verifier: str) -> OAuthTokens:
        _secret(code, maximum=4096)
        _secret(verifier, minimum=43, maximum=128)
        return self._tokens(
            self._post(
                "/auth/token",
                {
                    "grant_type": "authorization_code",
                    "code": code,
                    "client_id": self.configuration.client_id,
                    "code_verifier": verifier,
                },
            )
        )

    def refresh(self, refresh_token: str, provider: str) -> OAuthTokens:
        _secret(refresh_token)
        return self._tokens(
            self._post(
                "/auth/token",
                {
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": self.configuration.client_id,
                },
            ),
            refresh=refresh_token,
            provider=provider,
        )

    def revoke(self, refresh_token: str) -> None:
        _secret(refresh_token)
        self._post("/auth/revoke", {"token": refresh_token}, document=False)
