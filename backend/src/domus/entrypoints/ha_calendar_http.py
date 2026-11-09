"""A calendar-only installation boundary, separate from human and Ingress routes."""

import hashlib
import hmac
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Annotated, Literal

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from domus.application.calendar_queries import CalendarQueries
from domus.application.ha_calendar_projection import HACalendarPage, ha_calendar_projection
from domus.domain.calendar_values import CalendarFilters, CalendarKind, CalendarRange
from domus.domain.errors import DomusError, InvalidInput
from domus.domain.storage import Installation
from domus.entrypoints.bounded_http import BoundedHTTP
from domus.entrypoints.calendar_http import LocalDate
from domus.entrypoints.task_dto import PageQuery

CALENDAR_PATH = "/api/v1/ha/calendar"
CALENDAR_PORT = 8100
CALENDAR_DIGEST_ENV = "DOMUS_HA_CALENDAR_DIGEST"
_DIGEST = re.compile(r"[0-9a-f]{64}")
_SECRET = re.compile(rb"[0-9a-f]{64}")
_NO_STORE = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}


def validate_digest(value: str) -> str:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise InvalidInput("invalid_ha_calendar_digest")
    return value


@dataclass(frozen=True, slots=True)
class CalendarCredential:
    installation: Installation
    digest: str = field(repr=False)

    def __post_init__(self) -> None:
        validate_digest(self.digest)

    def accepts(self, scope: Scope) -> bool:
        values = [value for key, value in scope["headers"] if key == b"authorization"]
        if len(values) != 1:
            return False
        prefix = f"Bearer {self.installation.instance_id}.{self.installation.channel}.".encode()
        value = values[0]
        if not value.startswith(prefix) or not _SECRET.fullmatch(value[len(prefix) :]):
            return False
        return hmac.compare_digest(hashlib.sha256(value[7:]).hexdigest(), self.digest)


class _CalendarQuery(PageQuery):
    start: LocalDate
    end: LocalDate
    kind: Literal["planned", "due"]

    def period(self) -> CalendarRange:
        start, end = date.fromisoformat(self.start), date.fromisoformat(self.end)
        if (end - start).days > 90:
            raise InvalidInput("invalid_calendar_range")
        return CalendarRange(start, end)


@dataclass(frozen=True, slots=True)
class _SourcePage:
    instance_id: str
    channel: str
    projection: HACalendarPage


def _error(status: int, code: str, _correlation: str = "") -> JSONResponse:
    return JSONResponse({"error": code}, status_code=status, headers=_NO_STORE)


def _validate(scope: Scope) -> None:
    if len(scope["query_string"]) > 2048 or len(scope["headers"]) > 32:
        raise InvalidInput("invalid_calendar_request")
    keys = [key for key, _ in Request(scope).query_params.multi_items()]
    if len(keys) != len(set(keys)):
        raise InvalidInput("invalid_calendar_request")


def calendar_api(query_service: CalendarQueries, installation: Installation) -> ASGIApp:
    api = FastAPI(openapi_url=None, docs_url=None, redoc_url=None, redirect_slashes=False)

    @api.exception_handler(RequestValidationError)
    async def invalid(_request: Request, _error_detail: RequestValidationError) -> JSONResponse:
        return _error(422, "invalid_request")

    @api.get(CALENDAR_PATH, response_model=_SourcePage)
    def read(query: Annotated[_CalendarQuery, Query()]) -> _SourcePage | JSONResponse:
        try:
            page = query_service.page(
                query.period(),
                CalendarFilters(CalendarKind(query.kind)),
                limit=query.limit,
                cursor=query.cursor,
            )
            return _SourcePage(
                installation.instance_id, installation.channel, ha_calendar_projection(page)
            )
        except ValueError, InvalidInput:
            return _error(422, "invalid_request")
        except DomusError:
            return _error(503, "calendar_unavailable")

    return BoundedHTTP(api, _validate, lambda: "", _error, _NO_STORE)


class CalendarBoundary:
    def __init__(
        self,
        app: ASGIApp,
        api: ASGIApp,
        credential: CalendarCredential,
        standalone_host: bytes | None,
    ) -> None:
        self.app, self.api = app, api
        self.credential, self.standalone_host = credential, standalone_host

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        standalone = self.standalone_host is not None
        server = scope.get("server")
        technical = (
            scope["path"] == CALENDAR_PATH
            if standalone
            else server is not None and server[1] == CALENDAR_PORT
        )
        if not technical:
            await self.app(scope, receive, send)
            return
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        if scope["path"] != CALENDAR_PATH:
            await _error(404, "not_found")(scope, receive, send)
            return
        if standalone and not self._standalone_transport(scope):
            await _error(403, "request_forbidden")(scope, receive, send)
            return
        if not self.credential.accepts(scope):
            await _error(401, "invalid_calendar_credential")(scope, receive, send)
            return
        await self.api(scope, receive, send)

    def _standalone_transport(self, scope: Scope) -> bool:
        hosts = [value for key, value in scope["headers"] if key == b"host"]
        peer = scope.get("client")
        return hosts == [self.standalone_host] and (
            scope["scheme"] == "https" or (peer is not None and peer[0] in ("127.0.0.1", "::1"))
        )
