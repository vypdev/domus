"""Read the bounded Domus installation projection over an explicitly configured origin."""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, tzinfo
from uuid import UUID

from aiohttp import ClientError, ClientSession, ClientTimeout
from homeassistant.components.calendar import CalendarEvent
from yarl import URL

PATH = "/api/v1/ha/calendar"
PAGE_SIZE = 100
MAX_EVENTS = 1_000
MAX_PAGE_BYTES = 128 * 1024
MAX_PAGES_PER_KIND = 10
MAX_DAYS = 90
_MIN_DATE = date(1970, 1, 1)
_KINDS = ("planned", "due")
_TOKEN = re.compile(r"([0-9a-f-]{36})\.(stable|edge)\.[0-9a-f]{64}")
_PRIVATE_HOST = re.compile(r"(?:local|[0-9a-f]{8})-domus(?:-edge)?")
_DAY = timedelta(days=1)


class CalendarUnavailable(Exception):
    """No complete, trustworthy calendar read is available."""


class InvalidCredential(CalendarUnavailable):
    """The installation rejected its calendar bearer."""


class InvalidEndpoint(CalendarUnavailable):
    """The endpoint is outside the permitted transport boundary."""


@dataclass(frozen=True, slots=True)
class Projection:
    events: tuple[CalendarEvent, ...]
    pending: bool


@dataclass(frozen=True, slots=True)
class Page:
    events: tuple[CalendarEvent, ...]
    count: int
    cursor: str | None
    pending: bool


def _instant(value: date | datetime, zone: tzinfo) -> datetime:
    if not isinstance(value, datetime):
        value = datetime.combine(value, time.min, zone)
    return value.astimezone(UTC)


def overlaps(event: CalendarEvent, start: datetime, end: datetime, zone: tzinfo) -> bool:
    return _instant(event.start, zone) < end.astimezone(UTC) and start.astimezone(UTC) < _instant(
        event.end, zone
    )


def _event(raw: object, kind: str) -> CalendarEvent:
    if not isinstance(raw, dict):
        raise CalendarUnavailable
    uid, summary, start, all_day = (
        raw.get("uid"),
        raw.get("summary"),
        raw.get("start"),
        raw.get("all_day"),
    )
    if (
        raw.get("kind") != kind
        or not isinstance(uid, str)
        or not uid.startswith(f"{kind}:")
        or not len(kind) + 1 < len(uid) <= 160
        or not isinstance(summary, str)
        or not 1 <= len(summary) <= 512
        or not isinstance(start, str)
        or len(start) > 40
        or type(all_day) is not bool
    ):
        raise CalendarUnavailable
    try:
        if all_day:
            day = date.fromisoformat(start)
            if day.isoformat() != start:
                raise ValueError
            return CalendarEvent(day, day + _DAY, summary, uid=uid)
        point = datetime.fromisoformat(start)
        if point.utcoffset() is None or "T" not in start:
            raise ValueError
        return CalendarEvent(point, point + timedelta(minutes=1), summary, uid=uid)
    except ValueError, OverflowError:
        raise CalendarUnavailable from None


def _origin(value: str, channel: str) -> URL:
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


class CalendarClient:
    """Keep the bearer private and publish a result only after all pages succeed."""

    def __init__(self, session: ClientSession, url: str, token: str) -> None:
        match = _TOKEN.fullmatch(token)
        if match is None:
            raise InvalidCredential
        self.instance_id, self.channel = match.groups()
        try:
            instance = UUID(self.instance_id)
            if str(instance) != self.instance_id or not instance.int:
                raise ValueError
        except ValueError:
            raise InvalidCredential from None
        self.identity = f"{self.instance_id}.{self.channel}"
        self.url = _origin(url, self.channel)
        self._endpoint = self.url.with_path(PATH)
        self._authorization = f"Bearer {token}"
        self._session = session
        self._lock = asyncio.Lock()

    async def _page(
        self, start: date, end: date, kind: str, limit: int, cursor: str | None
    ) -> Page:
        params = {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "kind": kind,
            "limit": str(limit),
        }
        if cursor is not None:
            params["cursor"] = cursor
        try:
            async with self._session.get(
                self._endpoint,
                params=params,
                headers={"Authorization": self._authorization, "Accept-Encoding": "identity"},
                allow_redirects=False,
                auto_decompress=False,
                timeout=ClientTimeout(total=4),
            ) as response:
                if response.status == 401:
                    raise InvalidCredential
                if response.status != 200 or response.content_type != "application/json":
                    raise CalendarUnavailable
                body = bytearray()
                async for chunk in response.content.iter_chunked(16_384):
                    body.extend(chunk)
                    if len(body) > MAX_PAGE_BYTES:
                        raise CalendarUnavailable
                value = json.loads(body)
        except ClientError, TimeoutError, ValueError, RecursionError:
            raise CalendarUnavailable from None
        if (
            not isinstance(value, dict)
            or value.get("instance_id") != self.instance_id
            or value.get("channel") != self.channel
            or not isinstance(projection := value.get("projection"), dict)
            or projection.get("period") != {"start": params["start"], "end": params["end"]}
            or projection.get("external_sync") != "disabled"
        ):
            raise CalendarUnavailable
        events, count, next_cursor, pending = (
            projection.get("events"),
            projection.get("count"),
            projection.get("next_cursor"),
            projection.get("pending"),
        )
        if (
            not isinstance(events, list)
            or len(events) > limit
            or type(count) is not int
            or not len(events) <= count <= MAX_EVENTS
            or "next_cursor" not in projection
            or (
                next_cursor is not None
                and (not isinstance(next_cursor, str) or not 1 <= len(next_cursor) <= 512)
            )
            or type(pending) is not bool
        ):
            raise CalendarUnavailable
        return Page(tuple(_event(item, kind) for item in events), count, next_cursor, pending)

    async def probe(self, now: datetime) -> None:
        today = now.astimezone(UTC).date()
        await self._page(today, today + _DAY, "planned", 1, None)

    async def read(self, start: datetime, end: datetime, zone: tzinfo) -> Projection:
        if (
            start.year < 1970
            or end.year >= 9999
            or start.utcoffset() is None
            or end.utcoffset() is None
            or start.astimezone(UTC) >= end.astimezone(UTC)
            or end.astimezone(zone) - start.astimezone(zone) > MAX_DAYS * _DAY
        ):
            raise CalendarUnavailable
        # The query uses household calendar dates. Pad for time-zone differences and for
        # point markers that start on the previous day, then apply actual HA overlap.
        first = max(
            _MIN_DATE, min(start.astimezone(UTC).date(), start.astimezone(zone).date()) - _DAY
        )
        last = max(end.astimezone(UTC).date(), end.astimezone(zone).date()) + 2 * _DAY
        events: dict[str | None, CalendarEvent] = {}
        pending = False
        try:
            async with asyncio.timeout(15), self._lock:
                while first < last:
                    boundary = min(first + MAX_DAYS * _DAY, last)
                    for kind in _KINDS:
                        cursor = None
                        cursors = set()
                        count = None
                        seen = 0
                        for _ in range(MAX_PAGES_PER_KIND):
                            page = await self._page(first, boundary, kind, PAGE_SIZE, cursor)
                            if count is None:
                                count = page.count
                                if len(events) + count > MAX_EVENTS:
                                    raise CalendarUnavailable
                            elif count != page.count:
                                raise CalendarUnavailable
                            pending |= page.pending
                            seen += len(page.events)
                            for event in page.events:
                                if event.uid in events:
                                    raise CalendarUnavailable
                                events[event.uid] = event
                            cursor = page.cursor
                            if cursor is None:
                                if seen != count:
                                    raise CalendarUnavailable
                                break
                            if cursor in cursors or not page.events or seen >= count:
                                raise CalendarUnavailable
                            cursors.add(cursor)
                        else:
                            raise CalendarUnavailable
                    first = boundary
        except TimeoutError:
            raise CalendarUnavailable from None
        matching = sorted(
            (event for event in events.values() if overlaps(event, start, end, zone)),
            key=lambda event: (_instant(event.start, zone), event.uid or ""),
        )
        if pending and not matching:
            raise CalendarUnavailable
        return Projection(tuple(matching), pending)
