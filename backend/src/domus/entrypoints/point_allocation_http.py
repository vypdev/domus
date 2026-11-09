"""Protected allocation configuration and read-only completion preview."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.params import Depends
from pydantic import Field

from domus.application.point_allocations import AllocationPreview, AllocationSettingsView
from domus.domain.point_allocation import AllocationMode, AllocationPolicy, ShareRounding
from domus.entrypoints.household_http import (
    ReceiptResponse,
    _EmptyQuery,
    _JSONRoute,
    _key,
    _receipt,
)
from domus.entrypoints.http_contract import NonnegativeRevision, StrictModel
from domus.entrypoints.recurrence_http import _require_context
from domus.entrypoints.task_dto import (
    Identifier,
    ManualPointShares,
    Revision,
    manual_amounts,
)
from domus.entrypoints.task_http import TaskHTTPContext


class AllocationQuery(StrictModel):
    definition_id: Identifier | None = None


class AllocationPolicyBody(StrictModel):
    mode: AllocationMode = Field(strict=False)
    precision: int
    rounding: ShareRounding | None = Field(default=None, strict=False)

    def policy(self) -> AllocationPolicy:
        return AllocationPolicy(self.mode, self.precision, self.rounding)


class AllocationUpdateBody(StrictModel):
    definition_id: Identifier | None = None
    expected_revision: NonnegativeRevision
    policy: AllocationPolicyBody | None


class AllocationPreviewBody(StrictModel):
    occurrence_id: Identifier
    expected_revision: Revision
    performer_ids: list[Identifier] = Field(min_length=1, max_length=32)
    manual_shares: ManualPointShares | None = None


def create_point_allocation_router(
    context: Callable[[Request], TaskHTTPContext], *, security: Depends
) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/family/allocation",
        dependencies=[security, Depends(_require_context)],
        route_class=_JSONRoute,
    )

    @router.get("", response_model=AllocationSettingsView)
    def settings(
        request: Request, query: Annotated[AllocationQuery, Query()]
    ) -> AllocationSettingsView:
        return context(request).allocation().settings(query.definition_id)

    @router.put(
        "",
        response_model=ReceiptResponse,
        openapi_extra={
            "parameters": [
                {"name": name, "in": "header", "required": True, "schema": {"type": "string"}}
                for name in ("Idempotency-Key", "Origin", "X-CSRF-Token")
            ]
        },
    )
    def configure(
        request: Request, body: AllocationUpdateBody, query: Annotated[_EmptyQuery, Query()]
    ) -> ReceiptResponse:
        policy = None if body.policy is None else body.policy.policy()
        return _receipt(
            context(request).allocation_commands.configure(
                _key(request), body.definition_id, policy, body.expected_revision
            )
        )

    @router.get("/requests/{key}", response_model=ReceiptResponse)
    def original(
        key: Identifier, request: Request, query: Annotated[_EmptyQuery, Query()]
    ) -> ReceiptResponse:
        return _receipt(context(request).allocation().original(key))

    @router.post("/preview", response_model=AllocationPreview)
    def preview(
        request: Request, body: AllocationPreviewBody, query: Annotated[_EmptyQuery, Query()]
    ) -> AllocationPreview:
        return (
            context(request)
            .allocation()
            .preview(
                body.occurrence_id,
                body.expected_revision,
                tuple(body.performer_ids),
                manual_amounts(body.manual_shares),
            )
        )

    return router
