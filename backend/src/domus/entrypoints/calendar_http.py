"""Protected calendar reads share the household session and context boundary."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from pydantic import Field

from domus.application.calendar_commands import CalendarCommands, CalendarPreferenceUpdate
from domus.application.calendar_queries import CalendarPage, CalendarQueries
from domus.application.ha_calendar_projection import HACalendarPage, ha_calendar_projection
from domus.domain.calendar_values import (
    CalendarFilters,
    CalendarKind,
    CalendarRange,
    CalendarTiming,
    WeekStart,
)
from domus.domain.errors import InvalidInput
from domus.domain.task_values import OccurrenceState, Priority
from domus.entrypoints.household_http import (
    ReceiptResponse,
    _EmptyQuery,
    _JSONRoute,
    _key,
    _receipt,
)
from domus.entrypoints.http_contract import StrictModel
from domus.entrypoints.recurrence_http import _require_context
from domus.entrypoints.task_dto import Identifier, PageQuery, Revision

LocalDate = Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")]


class CalendarQuery(PageQuery):
    start: LocalDate
    end: LocalDate
    kind: CalendarKind | None = Field(default=None, strict=False)
    timing: CalendarTiming | None = Field(default=None, strict=False)
    state: OccurrenceState | None = Field(default=None, strict=False)
    priority: Priority | None = Field(default=None, strict=False)
    member_id: Identifier | None = None
    category: str | None = Field(default=None, min_length=1, max_length=64)

    def period(self) -> CalendarRange:
        try:
            return CalendarRange(date.fromisoformat(self.start), date.fromisoformat(self.end))
        except ValueError:
            raise InvalidInput("invalid_calendar_range") from None

    def filters(self) -> CalendarFilters:
        return CalendarFilters(
            self.kind, self.timing, self.state, self.priority, self.member_id, self.category
        )


@dataclass(frozen=True, slots=True)
class CalendarPreferenceResponse:
    week_start: WeekStart
    revision: int


class CalendarPreferenceBody(StrictModel):
    expected_revision: Revision
    week_start: WeekStart = Field(strict=False)


def create_calendar_router(
    context: Callable[[Request], CalendarQueries],
    commands: Callable[[Request], CalendarCommands],
) -> APIRouter:
    router = APIRouter(dependencies=[Depends(_require_context)], route_class=_JSONRoute)

    @router.get("/calendar", response_model=CalendarPage)
    def calendar(request: Request, query: Annotated[CalendarQuery, Query()]) -> CalendarPage:
        return context(request).page(
            query.period(),
            query.filters(),
            limit=query.limit,
            cursor=query.cursor,
        )

    @router.get("/calendar/home-assistant", response_model=HACalendarPage)
    def home_assistant(
        request: Request, query: Annotated[CalendarQuery, Query()]
    ) -> HACalendarPage:
        return ha_calendar_projection(
            context(request).page(
                query.period(), query.filters(), limit=query.limit, cursor=query.cursor
            )
        )

    @router.get("/calendar/preferences", response_model=CalendarPreferenceResponse)
    def preference(
        request: Request, query: Annotated[_EmptyQuery, Query()]
    ) -> CalendarPreferenceResponse:
        current = commands(request).preference()
        return CalendarPreferenceResponse(current.week_start, current.revision)

    @router.put(
        "/calendar/preferences",
        response_model=ReceiptResponse,
        openapi_extra={
            "parameters": [
                {"name": name, "in": "header", "required": True, "schema": {"type": "string"}}
                for name in ("Idempotency-Key", "Origin", "X-CSRF-Token")
            ]
        },
    )
    def update(
        request: Request, body: CalendarPreferenceBody, query: Annotated[_EmptyQuery, Query()]
    ) -> ReceiptResponse:
        return _receipt(
            commands(request).update(
                _key(request), CalendarPreferenceUpdate(body.expected_revision, body.week_start)
            )
        )

    @router.get("/calendar/preferences/requests/{key}", response_model=ReceiptResponse)
    def original(
        key: Identifier, request: Request, query: Annotated[_EmptyQuery, Query()]
    ) -> ReceiptResponse:
        return _receipt(commands(request).original(key))

    return router
