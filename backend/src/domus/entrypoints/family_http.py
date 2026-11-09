"""A protected member read of Points balances, history and participation."""

from collections.abc import Callable
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.params import Depends

from domus.application.family_queries import FamilyQueries, FamilyReport
from domus.domain.calendar_values import CalendarRange
from domus.domain.errors import InvalidInput
from domus.entrypoints.calendar_http import LocalDate
from domus.entrypoints.household_http import _JSONRoute
from domus.entrypoints.recurrence_http import _require_context
from domus.entrypoints.task_dto import PageQuery


class FamilyQuery(PageQuery):
    start: LocalDate
    end: LocalDate

    def period(self) -> CalendarRange:
        try:
            return CalendarRange(date.fromisoformat(self.start), date.fromisoformat(self.end))
        except ValueError:
            raise InvalidInput("invalid_calendar_range") from None


def create_family_router(
    context: Callable[[Request], FamilyQueries], *, security: Depends
) -> APIRouter:
    router = APIRouter(dependencies=[security, Depends(_require_context)], route_class=_JSONRoute)

    @router.get("/api/v1/family", response_model=FamilyReport)
    def family(request: Request, query: Annotated[FamilyQuery, Query()]) -> FamilyReport:
        return context(request).report(query.period(), limit=query.limit, cursor=query.cursor)

    return router
