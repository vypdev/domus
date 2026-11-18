"""Read a complete bounded open-task list for one Domus installation."""

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

TASKS = "tasks"
TASKS_TITLE = "Domus open tasks"
_PATH = "/api/v1/ha/tasks"
_TOKEN = re.compile(r"([0-9a-f-]{36})\.(stable|edge)\.tasks\.[0-9a-f]{64}")
_UID = re.compile(r"[0-9a-f]{64}")
_FIELDS = {"uid", "title", "state"}
_STATES = {"draft", "available", "assigned", "in_progress", "blocked"}
_MAX_ITEMS = 1000
_MAX_BODY_BYTES = 1_048_576


@dataclass(frozen=True, slots=True)
class TaskItem:
    uid: str
    title: str
    state: str


def _item(value: object) -> TaskItem:
    if type(value) is not dict or set(value) != _FIELDS:
        raise ProjectionUnavailable
    uid, title, state = (value[key] for key in ("uid", "title", "state"))
    if not all(type(field) is str for field in (uid, title, state)):
        raise ProjectionUnavailable
    if (
        _UID.fullmatch(uid) is None
        or not title.strip()
        or len(title) > 160
        or any(ord(char) < 32 or ord(char) == 127 for char in title)
        or state not in _STATES
    ):
        raise ProjectionUnavailable
    title.encode("utf-8")
    return TaskItem(uid, title, state)


def _items(body: bytearray) -> tuple[TaskItem, ...]:
    rows = projection_items(body, item_limit=_MAX_ITEMS)
    items = tuple(_item(row) for row in rows)
    if len({item.uid for item in items}) != len(items):
        raise ProjectionUnavailable
    return items


class TaskClient:
    def __init__(self, session: ClientSession, url: str, token: str) -> None:
        instance, self.channel = bearer_source(token, _TOKEN)
        self.identity = f"{instance}.{self.channel}.{TASKS}"
        self.url = connection_origin(url, self.channel)
        self._endpoint = self.url.with_path(_PATH)
        self._authorization = f"Bearer {token}"
        self._session = session

    async def read(self) -> tuple[TaskItem, ...]:
        body = await read_projection(
            self._session, self._endpoint, self._authorization, byte_limit=_MAX_BODY_BYTES
        )
        try:
            return _items(body)
        except ValueError, RecursionError:
            raise ProjectionUnavailable from None
