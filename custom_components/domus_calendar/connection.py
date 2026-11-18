"""Validate the installation identity and permitted Home Assistant transports."""

import json
import re
from uuid import UUID

from aiohttp import ClientError, ClientSession, ClientTimeout
from yarl import URL

_PRIVATE_HOST = re.compile(r"(?:local|[0-9a-f]{8})-domus(?:-edge)?")


class ProjectionUnavailable(Exception):
    """A complete, trustworthy installation projection is unavailable."""


class InvalidCredential(ProjectionUnavailable):
    """The installation credential is malformed or rejected."""


class InvalidEndpoint(ProjectionUnavailable):
    """The endpoint is outside the permitted transport boundary."""


def _object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    values = dict(pairs)
    if len(values) != len(pairs):
        raise ProjectionUnavailable
    return values


def projection_items(body: bytearray, *, item_limit: int) -> list[object]:
    result = json.loads(body.decode("utf-8"), object_pairs_hook=_object)
    if type(result) is not dict or set(result) != {"items"}:
        raise ProjectionUnavailable
    rows = result["items"]
    if type(rows) is not list or len(rows) > item_limit:
        raise ProjectionUnavailable
    return rows


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


async def read_projection(
    session: ClientSession, endpoint: URL, authorization: str, *, byte_limit: int
) -> bytearray:
    try:
        async with session.get(
            endpoint,
            headers={"Authorization": authorization, "Accept-Encoding": "identity"},
            allow_redirects=False,
            auto_decompress=False,
            timeout=ClientTimeout(total=4),
        ) as response:
            if response.status == 401:
                raise InvalidCredential
            if response.status != 200 or response.content_type != "application/json":
                raise ProjectionUnavailable
            body = bytearray()
            async for chunk in response.content.iter_chunked(min(byte_limit, 65_536)):
                body.extend(chunk)
                if len(body) > byte_limit:
                    raise ProjectionUnavailable
            return body
    except ClientError, TimeoutError, ValueError, RecursionError:
        raise ProjectionUnavailable from None
