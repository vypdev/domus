"""Validate the installation identity and permitted Home Assistant transports."""

import re
from uuid import UUID

from yarl import URL

_PRIVATE_HOST = re.compile(r"(?:local|[0-9a-f]{8})-domus(?:-edge)?")


class ProjectionUnavailable(Exception):
    """A complete, trustworthy installation projection is unavailable."""


class InvalidCredential(ProjectionUnavailable):
    """The installation credential is malformed or rejected."""


class InvalidEndpoint(ProjectionUnavailable):
    """The endpoint is outside the permitted transport boundary."""


def bearer_source(token: str, pattern: re.Pattern[str]) -> tuple[str, str]:
    match = pattern.fullmatch(token)
    if match is None:
        raise InvalidCredential
    instance_id, channel = match.groups()
    try:
        instance = UUID(instance_id)
        if str(instance) != instance_id or not instance.int:
            raise ValueError
    except ValueError:
        raise InvalidCredential from None
    return instance_id, channel


def connection_origin(value: str, channel: str) -> URL:
    if (
        not value
        or len(value) > 2048
        or any(char.isspace() or ord(char) < 32 or char in "?#\\%" for char in value)
    ):
        raise InvalidEndpoint
    try:
        url = URL(value)
        host = url.raw_host
        if (
            not host
            or url.user is not None
            or url.password is not None
            or url.path != "/"
            or url.port is None
            or not 1 <= url.port <= 65535
        ):
            raise InvalidEndpoint
        if url.scheme != "https" and (
            url.scheme != "http"
            or url.port != 8100
            or _PRIVATE_HOST.fullmatch(host) is None
            or host.endswith("-edge") != (channel == "edge")
        ):
            raise InvalidEndpoint
        return url.origin()
    except ValueError, UnicodeError:
        raise InvalidEndpoint from None
