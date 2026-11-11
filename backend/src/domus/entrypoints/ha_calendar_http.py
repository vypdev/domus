"""A calendar-only installation boundary, separate from human and Ingress routes."""

from dataclasses import dataclass
from datetime import date
from typing import Annotated, Literal

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Scope

from domus.application.calendar_queries import CalendarQueries
from domus.application.ha_calendar_projection import HACalendarPage, ha_calendar_projection
from domus.domain.calendar_values import CalendarFilters, CalendarKind, CalendarRange
from domus.domain.errors import DomusError, InvalidInput
from domus.domain.storage import Installation
from domus.entrypoints.bounded_http import BoundedHTTP
from domus.entrypoints.calendar_http import LocalDate
from domus.entrypoints.ha_projection_http import NO_STORE, PROJECTION_PORT, projection_error
from domus.entrypoints.task_dto import PageQuery

CALENDAR_PATH = "/api/v1/ha/calendar"
CALENDAR_PORT = PROJECTION_PORT
CALENDAR_DIGEST_ENV = "DOMUS_HA_CALENDAR_DIGEST"


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
        return projection_error(422, "invalid_request")

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
            return projection_error(422, "invalid_request")
        except DomusError:
            return projection_error(503, "calendar_unavailable")

    return BoundedHTTP(api, _validate, lambda: "", projection_error, NO_STORE)
