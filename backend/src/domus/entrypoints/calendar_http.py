"""Protected calendar reads share the household session and context boundary."""

from collections.abc import Callable
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from pydantic import Field

from domus.application.calendar_queries import CalendarPage, CalendarQueries
from domus.domain.calendar_values import (
    CalendarFilters,
    CalendarKind,
    CalendarRange,
    CalendarTiming,
)
from domus.domain.errors import InvalidInput
from domus.domain.task_values import OccurrenceState, Priority
from domus.entrypoints.household_http import _JSONRoute
from domus.entrypoints.recurrence_http import _require_context
from domus.entrypoints.task_dto import Identifier, PageQuery

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


def create_calendar_router(context: Callable[[Request], CalendarQueries]) -> APIRouter:
    router = APIRouter(dependencies=[Depends(_require_context)], route_class=_JSONRoute)

    @router.get("/calendar", response_model=CalendarPage)
    def calendar(request: Request, query: Annotated[CalendarQuery, Query()]) -> CalendarPage:
        return context(request).page(
            query.period(),
            CalendarFilters(
                query.kind,
                query.timing,
                query.state,
                query.priority,
                query.member_id,
                query.category,
            ),
            limit=query.limit,
            cursor=query.cursor,
        )

    return router
