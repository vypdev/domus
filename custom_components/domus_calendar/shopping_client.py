"""Read a complete bounded native shopping list for one Domus installation."""

import re
from dataclasses import dataclass

from aiohttp import ClientSession

from .connection import (
    ProjectionUnavailable,
    bearer_source,
    connection_origin,
    projection_items,
    read_projection,
)

SHOPPING = "shopping"
SHOPPING_TITLE = "Domus shopping list"
_PATH = "/api/v1/ha/shopping-list"
_TOKEN = re.compile(r"([0-9a-f-]{36})\.(stable|edge)\.shopping\.[0-9a-f]{64}")
_UID = re.compile(r"[0-9a-f]{64}")
_QUANTITY = re.compile(r"(?:0|[1-9][0-9]{0,39})(?:\.[0-9]{0,5}[1-9])?")
_FIELDS = {"uid", "name", "quantity", "unit"}
_UNITS = {"piece", "gram", "millilitre"}
_MAX_ITEMS = 1000
_MAX_BODY_BYTES = 1_048_576


@dataclass(frozen=True, slots=True)
class ShoppingItem:
    uid: str
    name: str
    quantity: str
    unit: str


def _item(value: object) -> ShoppingItem:
    if type(value) is not dict or set(value) != _FIELDS:
        raise ProjectionUnavailable
    uid, name, quantity, unit = (value[key] for key in ("uid", "name", "quantity", "unit"))
    if not all(type(field) is str for field in (uid, name, quantity, unit)):
        raise ProjectionUnavailable
    if (
        _UID.fullmatch(uid) is None
        or not name.strip()
        or len(name) > 160
        or any(ord(char) < 32 or ord(char) == 127 for char in name)
        or _QUANTITY.fullmatch(quantity) is None
        or quantity == "0"
        or unit not in _UNITS
        or (unit == "piece" and "." in quantity)
    ):
        raise ProjectionUnavailable
    name.encode("utf-8")
    return ShoppingItem(uid, name, quantity, unit)


def _items(body: bytearray) -> tuple[ShoppingItem, ...]:
    rows = projection_items(body, item_limit=_MAX_ITEMS)
    items = tuple(_item(row) for row in rows)
    if len({item.uid for item in items}) != len(items):
        raise ProjectionUnavailable
    return items


class ShoppingClient:
    def __init__(self, session: ClientSession, url: str, token: str) -> None:
        instance, self.channel = bearer_source(token, _TOKEN)
        self.identity = f"{instance}.{self.channel}.{SHOPPING}"
        self.url = connection_origin(url, self.channel)
        self._endpoint = self.url.with_path(_PATH)
        self._authorization = f"Bearer {token}"
        self._session = session

    async def read(self) -> tuple[ShoppingItem, ...]:
        body = await read_projection(
            self._session, self._endpoint, self._authorization, byte_limit=_MAX_BODY_BYTES
        )
        try:
            return _items(body)
        except ValueError, RecursionError:
            raise ProjectionUnavailable from None
