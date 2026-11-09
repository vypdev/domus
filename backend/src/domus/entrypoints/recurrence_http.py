"""Protected recurrence review routes share the task session and request boundary."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request

from domus.application.recurrence_review import RecurrenceReview, ReviewAction
from domus.application.recurrence_review_target import ReviewTarget
from domus.entrypoints.entry_context import CONTEXT_HEADER
from domus.entrypoints.household_http import (
    ReceiptResponse,
    _EmptyQuery,
    _JSONRoute,
    _key,
    _receipt,
)
from domus.entrypoints.recurrence_dto import (
    FixedExceptionBody,
    FixedMissedPolicyBody,
    FixedPatternBody,
    FixedReplacementBody,
    FixedSkipBody,
    FixedStateBody,
    ManualAdoptionBody,
    RelativeAttachmentBody,
    RelativeSettingsBody,
    RelativeStateBody,
    RescheduleBody,
    ReviewedAdoptionBody,
    ReviewedFixedExceptionBody,
    ReviewedFixedMissedPolicyBody,
    ReviewedFixedPatternBody,
    ReviewedFixedReplacementBody,
    ReviewedFixedSkipBody,
    ReviewedFixedStateBody,
    ReviewedRelativeAttachmentBody,
    ReviewedRelativeSettingsBody,
    ReviewedRescheduleBody,
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

    @router.get("/targets/{occurrence_id}", response_model=ReviewTarget)
    def target(
        occurrence_id: Identifier, request: Request, query: Annotated[_EmptyQuery, Query()]
    ) -> ReviewTarget:
        return context(request).target(occurrence_id)

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

    @router.post(
        "/fixed-skip/preview", response_model=ReceiptResponse, openapi_extra=write_contract
    )
    def preview_fixed_skip(
        request: Request, body: FixedSkipBody, query: Annotated[_EmptyQuery, Query()]
    ) -> ReceiptResponse:
        return _receipt(context(request).preview(_key(request), body.selection()))

    @router.post("/fixed-skip/apply", response_model=ReceiptResponse, openapi_extra=write_contract)
    def apply_fixed_skip(
        request: Request, body: ReviewedFixedSkipBody, query: Annotated[_EmptyQuery, Query()]
    ) -> ReceiptResponse:
        return _receipt(context(request).apply(_key(request), body.reviewed()))

    @router.post(
        "/fixed-missed-policy/preview", response_model=ReceiptResponse, openapi_extra=write_contract
    )
    def preview_missed_policy(
        request: Request, body: FixedMissedPolicyBody, query: Annotated[_EmptyQuery, Query()]
    ) -> ReceiptResponse:
        return _receipt(context(request).preview(_key(request), body.selection()))

    @router.post(
        "/fixed-missed-policy/apply", response_model=ReceiptResponse, openapi_extra=write_contract
    )
    def apply_missed_policy(
        request: Request,
        body: ReviewedFixedMissedPolicyBody,
        query: Annotated[_EmptyQuery, Query()],
    ) -> ReceiptResponse:
        return _receipt(context(request).apply(_key(request), body.reviewed()))

    @router.post(
        "/attachment/preview", response_model=ReceiptResponse, openapi_extra=write_contract
    )
    def preview_attachment(
        request: Request, body: RelativeAttachmentBody, query: Annotated[_EmptyQuery, Query()]
    ) -> ReceiptResponse:
        return _receipt(context(request).preview(_key(request), body.selection()))

    @router.post("/attachment/apply", response_model=ReceiptResponse, openapi_extra=write_contract)
    def apply_attachment(
        request: Request,
        body: ReviewedRelativeAttachmentBody,
        query: Annotated[_EmptyQuery, Query()],
    ) -> ReceiptResponse:
        return _receipt(context(request).apply(_key(request), body.reviewed()))

    @router.post(
        "/relative-settings/preview", response_model=ReceiptResponse, openapi_extra=write_contract
    )
    def preview_relative_settings(
        request: Request, body: RelativeSettingsBody, query: Annotated[_EmptyQuery, Query()]
    ) -> ReceiptResponse:
        return _receipt(context(request).preview(_key(request), body.selection()))

    @router.post(
        "/relative-settings/apply", response_model=ReceiptResponse, openapi_extra=write_contract
    )
    def apply_relative_settings(
        request: Request, body: ReviewedRelativeSettingsBody, query: Annotated[_EmptyQuery, Query()]
    ) -> ReceiptResponse:
        return _receipt(context(request).apply(_key(request), body.reviewed()))

    @router.post(
        "/reschedule/preview", response_model=ReceiptResponse, openapi_extra=write_contract
    )
    def preview_reschedule(
        request: Request, body: RescheduleBody, query: Annotated[_EmptyQuery, Query()]
    ) -> ReceiptResponse:
        return _receipt(context(request).preview(_key(request), body.move()))

    @router.post("/reschedule/apply", response_model=ReceiptResponse, openapi_extra=write_contract)
    def apply_reschedule(
        request: Request, body: ReviewedRescheduleBody, query: Annotated[_EmptyQuery, Query()]
    ) -> ReceiptResponse:
        return _receipt(context(request).apply(_key(request), body.reviewed()))

    @router.post(
        "/fixed-state/preview", response_model=ReceiptResponse, openapi_extra=write_contract
    )
    def preview_fixed_state(
        request: Request, body: FixedStateBody, query: Annotated[_EmptyQuery, Query()]
    ) -> ReceiptResponse:
        return _receipt(context(request).preview(_key(request), body.selection()))

    @router.post("/fixed-state/apply", response_model=ReceiptResponse, openapi_extra=write_contract)
    def apply_fixed_state(
        request: Request, body: ReviewedFixedStateBody, query: Annotated[_EmptyQuery, Query()]
    ) -> ReceiptResponse:
        return _receipt(context(request).apply(_key(request), body.reviewed()))

    @router.post(
        "/fixed-pattern/preview", response_model=ReceiptResponse, openapi_extra=write_contract
    )
    def preview_fixed_pattern(
        request: Request, body: FixedPatternBody, query: Annotated[_EmptyQuery, Query()]
    ) -> ReceiptResponse:
        return _receipt(context(request).preview(_key(request), body.selection()))

    @router.post(
        "/fixed-pattern/apply", response_model=ReceiptResponse, openapi_extra=write_contract
    )
    def apply_fixed_pattern(
        request: Request, body: ReviewedFixedPatternBody, query: Annotated[_EmptyQuery, Query()]
    ) -> ReceiptResponse:
        return _receipt(context(request).apply(_key(request), body.reviewed()))

    @router.post(
        "/fixed-replacement/preview", response_model=ReceiptResponse, openapi_extra=write_contract
    )
    def preview_fixed_replacement(
        request: Request, body: FixedReplacementBody, query: Annotated[_EmptyQuery, Query()]
    ) -> ReceiptResponse:
        return _receipt(context(request).preview(_key(request), body.replacement()))

    @router.post(
        "/fixed-replacement/apply", response_model=ReceiptResponse, openapi_extra=write_contract
    )
    def apply_fixed_replacement(
        request: Request, body: ReviewedFixedReplacementBody, query: Annotated[_EmptyQuery, Query()]
    ) -> ReceiptResponse:
        return _receipt(context(request).apply(_key(request), body.reviewed()))

    @router.post(
        "/fixed-exception/preview", response_model=ReceiptResponse, openapi_extra=write_contract
    )
    def preview_fixed_exception(
        request: Request, body: FixedExceptionBody, query: Annotated[_EmptyQuery, Query()]
    ) -> ReceiptResponse:
        return _receipt(context(request).preview(_key(request), body.selection()))

    @router.post(
        "/fixed-exception/apply", response_model=ReceiptResponse, openapi_extra=write_contract
    )
    def apply_fixed_exception(
        request: Request, body: ReviewedFixedExceptionBody, query: Annotated[_EmptyQuery, Query()]
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
