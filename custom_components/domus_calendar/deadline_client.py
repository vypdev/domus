"""Fetch both task counts over the dedicated read-only grant."""

import json
import re
from dataclasses import dataclass

from aiohttp import ClientError, ClientSession, ClientTimeout

from .connection import InvalidCredential, ProjectionUnavailable, bearer_source, connection_origin

_PATH = "/api/v1/ha/task-deadlines"
_TOKEN = re.compile(r"([0-9a-f-]{36})\.(stable|edge)\.deadlines\.[0-9a-f]{64}")
_MAX_BODY_BYTES = 128
_MAX_COUNT = (1 << 63) - 1


@dataclass(frozen=True, slots=True)
class DeadlineCounts:
    due_today: int
    overdue: int


def _counts(body: bytearray) -> DeadlineCounts:
    fields = json.loads(body, object_pairs_hook=tuple)
    if not isinstance(fields, tuple) or len(fields) != 2:
        raise ProjectionUnavailable
    values = dict(fields)
    if set(values) != {"due_today", "overdue"}:
        raise ProjectionUnavailable
    today, overdue = values["due_today"], values["overdue"]
    if type(today) is not int or type(overdue) is not int:
        raise ProjectionUnavailable
    if not 0 <= today <= _MAX_COUNT or not 0 <= overdue <= _MAX_COUNT:
        raise ProjectionUnavailable
    return DeadlineCounts(today, overdue)


class DeadlineClient:
    def __init__(self, session: ClientSession, url: str, token: str) -> None:
        instance_id, self.channel = bearer_source(token, _TOKEN)
        self.identity = f"{instance_id}.{self.channel}.deadlines"
        self.url = connection_origin(url, self.channel)
        self._endpoint = self.url.with_path(_PATH)
        self._authorization = f"Bearer {token}"
        self._session = session

    async def read(self) -> DeadlineCounts:
        try:
            async with self._session.get(
                self._endpoint,
                headers={"Authorization": self._authorization, "Accept-Encoding": "identity"},
                allow_redirects=False,
                auto_decompress=False,
                timeout=ClientTimeout(total=4),
            ) as response:
                if response.status == 401:
                    raise InvalidCredential
                if response.status != 200 or response.content_type != "application/json":
                    raise ProjectionUnavailable
                body = bytearray()
                async for chunk in response.content.iter_chunked(_MAX_BODY_BYTES):
                    body.extend(chunk)
                    if len(body) > _MAX_BODY_BYTES:
                        raise ProjectionUnavailable
                return _counts(body)
        except ClientError, TimeoutError, ValueError, RecursionError:
            raise ProjectionUnavailable from None
