"""Operator-owned endpoints cannot be selected by request hosts or forwarding headers."""

import ipaddress
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from domus.domain.errors import InvalidInput


def _origin(value: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) > 2048
        or any(character.isspace() or ord(character) < 32 for character in value)
        or any(character in value for character in ("?", "#", "\\", "%"))
    ):
        raise InvalidInput("invalid_origin")
    try:
        url = urlsplit(value)
        host, port = url.hostname, url.port
        if (
            url.scheme not in ("http", "https")
            or not host
            or url.username is not None
            or url.password is not None
            or url.path not in ("", "/")
            or (port is not None and not 1 <= port <= 65535)
        ):
            raise ValueError("invalid origin")
        try:
            ipaddress.ip_address(host)
        except ValueError:
            label = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
            if len(host) > 253 or not re.fullmatch(rf"{label}(?:\.{label})*", host):
                raise ValueError("invalid host") from None
        return f"{url.scheme}://{url.netloc.lower()}"
    except ValueError:
        raise InvalidInput("invalid_origin") from None


@dataclass(frozen=True, slots=True)
class HAEndpoint:
    origin: str
    supervised: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "origin", _origin(self.origin))
        if type(self.supervised) is not bool or (
            self.supervised and self.origin != "http://supervisor"
        ):
            raise InvalidInput("invalid_ha_endpoint")

    @classmethod
    def supervisor(cls) -> HAEndpoint:
        return cls("http://supervisor", supervised=True)

    @property
    def host(self) -> str:
        return str(urlsplit(self.origin).hostname)

    @property
    def port(self) -> int:
        return urlsplit(self.origin).port or (443 if self.origin.startswith("https:") else 80)

    @property
    def websocket_url(self) -> str:
        if self.supervised:
            return "ws://supervisor/core/websocket"
        scheme = "wss" if self.origin.startswith("https:") else "ws"
        return f"{scheme}://{urlsplit(self.origin).netloc}/api/websocket"


@dataclass(frozen=True, slots=True)
class PublicOrigins:
    values: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.values) is not tuple or not 1 <= len(self.values) <= 4:
            raise InvalidInput("invalid_public_origins")
        normalized = tuple(_origin(value) for value in self.values)
        if len(set(normalized)) != len(normalized):
            raise InvalidInput("invalid_public_origins")
        object.__setattr__(self, "values", normalized)


@dataclass(frozen=True, slots=True)
class OAuthConfiguration:
    ha: HAEndpoint
    public_origin: str
    development_http: bool = False

    def __post_init__(self) -> None:
        if self.ha.supervised:
            raise InvalidInput("supervisor_uses_ingress")
        origin = _origin(self.public_origin)
        host = str(urlsplit(origin).hostname)
        try:
            loopback = ipaddress.ip_address(host).is_loopback
        except ValueError:
            loopback = host == "localhost"
        if not origin.startswith("https:") and not (self.development_http is True and loopback):
            raise InvalidInput("insecure_public_origin")
        object.__setattr__(self, "public_origin", origin)

    @property
    def client_id(self) -> str:
        return self.public_origin + "/"

    @property
    def callback_url(self) -> str:
        return self.public_origin + "/api/v1/auth/callback"
