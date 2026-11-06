"""Protected recurrence review routes share the task session and request boundary."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request

from domus.application.recurrence_review import RecurrenceReview, ReviewAction
from domus.entrypoints.entry_context import CONTEXT_HEADER
from domus.entrypoints.household_http import (
    ReceiptResponse,
    _EmptyQuery,
    _JSONRoute,
    _key,
    _receipt,
)
from domus.entrypoints.recurrence_dto import (
    ManualAdoptionBody,
    RelativeStateBody,
    ReviewedAdoptionBody,
    ReviewedStateBody,
)
from domus.entrypoints.task_dto import Identifier


def _require_context(_context: Annotated[str, Header(alias=CONTEXT_HEADER)]) -> None:
    """The inherited task security dependency verifies the asserted context."""


def create_recurrence_review_router(context: Callable[[Request], RecurrenceReview]) -> APIRouter:
    router = APIRouter(
        prefix="/recurrence/reviews",
        dependencies=[Depends(_require_context)],
        route_class=_JSONRoute,
    )
    write_contract = {
        "parameters": [
            {"name": name, "in": "header", "required": True, "schema": {"type": "string"}}
            for name in ("Idempotency-Key", "Origin", "X-CSRF-Token")
        ]
    }

    @router.post("/adoption/preview", response_model=ReceiptResponse, openapi_extra=write_contract)
    def preview_adoption(
        request: Request, body: ManualAdoptionBody, query: Annotated[_EmptyQuery, Query()]
    ) -> ReceiptResponse:
        return _receipt(context(request).preview(_key(request), body.selection()))

    @router.post("/adoption/apply", response_model=ReceiptResponse, openapi_extra=write_contract)
    def apply_adoption(
        request: Request, body: ReviewedAdoptionBody, query: Annotated[_EmptyQuery, Query()]
    ) -> ReceiptResponse:
        return _receipt(context(request).apply(_key(request), body.reviewed()))

    @router.post("/state/preview", response_model=ReceiptResponse, openapi_extra=write_contract)
    def preview_relative_state(
        request: Request, body: RelativeStateBody, query: Annotated[_EmptyQuery, Query()]
    ) -> ReceiptResponse:
        return _receipt(context(request).preview(_key(request), body.selection()))

    @router.post("/state/apply", response_model=ReceiptResponse, openapi_extra=write_contract)
    def apply_relative_state(
        request: Request, body: ReviewedStateBody, query: Annotated[_EmptyQuery, Query()]
    ) -> ReceiptResponse:
        return _receipt(context(request).apply(_key(request), body.reviewed()))

    @router.get("/requests/{action}/{key}", response_model=ReceiptResponse)
    def original_recurrence_request(
        action: ReviewAction,
        key: Identifier,
        request: Request,
        query: Annotated[_EmptyQuery, Query()],
    ) -> ReceiptResponse:
        return _receipt(context(request).original(action, key))

    return router
