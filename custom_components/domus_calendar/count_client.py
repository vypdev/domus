"""Fetch small aggregate counts over a purpose-bound installation grant."""

import json
import re
from typing import Literal

from aiohttp import ClientSession

from .connection import ProjectionUnavailable, bearer_source, connection_origin, read_projection

DEADLINES = "deadlines"
STOCK = "stock"
type CountPurpose = Literal["deadlines", "stock"]

_PATHS = {DEADLINES: "/api/v1/ha/task-deadlines", STOCK: "/api/v1/ha/low-stock-products"}
_FIELDS = {DEADLINES: {"due_today", "overdue"}, STOCK: {"low_stock_products"}}
_MAX_BODY_BYTES = 128
_MAX_COUNT = (1 << 63) - 1


def _counts(body: bytearray, expected: set[str]) -> dict[str, int]:
    if not body.lstrip().startswith(b"{"):
        raise ProjectionUnavailable
    fields = json.loads(body, object_pairs_hook=tuple)
    if not isinstance(fields, tuple) or len(fields) != len(expected):
        raise ProjectionUnavailable
    values = dict(fields)
    if set(values) != expected:
        raise ProjectionUnavailable
    if any(type(value) is not int or not 0 <= value <= _MAX_COUNT for value in values.values()):
        raise ProjectionUnavailable
    return values


class CountClient:
    def __init__(self, session: ClientSession, url: str, token: str, purpose: CountPurpose) -> None:
        pattern = re.compile(rf"([0-9a-f-]{{36}})\.(stable|edge)\.{purpose}\.[0-9a-f]{{64}}")
        instance_id, self.channel = bearer_source(token, pattern)
        self.identity = f"{instance_id}.{self.channel}.{purpose}"
        self.url = connection_origin(url, self.channel)
        self._endpoint = self.url.with_path(_PATHS[purpose])
        self._fields = _FIELDS[purpose]
        self._authorization = f"Bearer {token}"
        self._session = session

    async def read(self) -> dict[str, int]:
        body = await read_projection(
            self._session, self._endpoint, self._authorization, byte_limit=_MAX_BODY_BYTES
        )
        try:
            return _counts(body, self._fields)
        except ValueError, RecursionError:
            raise ProjectionUnavailable from None
