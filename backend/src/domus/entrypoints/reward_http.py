"""Protected reward views and closed command shapes for both deployments."""

from collections.abc import Callable
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request
from fastapi.params import Depends
from pydantic import Field

from domus.application.reward_commands import RewardAction
from domus.application.reward_queries import RewardsView
from domus.domain.identity import Role
from domus.domain.point_allocation import MAX_POINT_SHARE
from domus.entrypoints.household_http import (
    ReceiptResponse,
    _EmptyQuery,
    _JSONRoute,
    _key,
    _receipt,
)
from domus.entrypoints.http_contract import NonnegativeRevision, StrictModel
from domus.entrypoints.recurrence_http import _require_context
from domus.entrypoints.task_dto import Identifier, PageQuery, Revision
from domus.entrypoints.task_http import TaskHTTPContext


class RewardsQuery(PageQuery):
    limit: Annotated[int, Field(ge=1, le=25, strict=False)] = 25


class RewardConfigureBody(StrictModel):
    action: Literal["reward.configure"]
    enabled: bool
    expected_revision: NonnegativeRevision


class RewardOfferBody(StrictModel):
    action: Literal["reward.offer"]
    offer_id: Identifier | None = None
    title: str = Field(min_length=1, max_length=160)
    cost_minor: int = Field(ge=1, le=MAX_POINT_SHARE)
    enabled: bool
    eligible_roles: list[Annotated[Role, Field(strict=False)]] = Field(min_length=1, max_length=4)
    expected_revision: NonnegativeRevision


class RewardRequestBody(StrictModel):
    action: Literal["reward.request"]
    offer_id: Identifier
    expected_revision: Revision


class RewardApproveBody(StrictModel):
    action: Literal["reward.approve"]
    redemption_id: Identifier


class RewardDeliverBody(StrictModel):
    action: Literal["reward.deliver"]
    redemption_id: Identifier


class RewardCancelBody(StrictModel):
    action: Literal["reward.cancel"]
    redemption_id: Identifier
    expected_revision: Revision
    reason: str = Field(min_length=1, max_length=1000)


RewardCommandBody = Annotated[
    RewardConfigureBody
    | RewardOfferBody
    | RewardRequestBody
    | RewardApproveBody
    | RewardDeliverBody
    | RewardCancelBody,
    Field(discriminator="action"),
]


def create_reward_router(
    context: Callable[[Request], TaskHTTPContext], *, security: Depends
) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/family/rewards",
        dependencies=[security, Depends(_require_context)],
        route_class=_JSONRoute,
    )

    @router.get("", response_model=RewardsView)
    def rewards(request: Request, query: Annotated[RewardsQuery, Query()]) -> RewardsView:
        return context(request).rewards().report(limit=query.limit, cursor=query.cursor)

    @router.post(
        "/commands",
        response_model=ReceiptResponse,
        openapi_extra={
            "parameters": [
                {"name": name, "in": "header", "required": True, "schema": {"type": "string"}}
                for name in ("Idempotency-Key", "Origin", "X-CSRF-Token")
            ]
        },
    )
    def command(
        request: Request, body: RewardCommandBody, query: Annotated[_EmptyQuery, Query()]
    ) -> ReceiptResponse:
        rewards = context(request).reward_commands
        key = _key(request)
        match body:
            case RewardConfigureBody():
                receipt = rewards.configure(key, body.enabled, body.expected_revision)
            case RewardOfferBody():
                receipt = rewards.offer(
                    key,
                    body.offer_id,
                    body.title,
                    body.cost_minor,
                    body.enabled,
                    tuple(body.eligible_roles),
                    body.expected_revision,
                )
            case RewardRequestBody():
                receipt = rewards.request(key, body.offer_id, body.expected_revision)
            case RewardApproveBody():
                receipt = rewards.approve(key, body.redemption_id)
            case RewardDeliverBody():
                receipt = rewards.deliver(key, body.redemption_id)
            case _:
                receipt = rewards.cancel(
                    key, body.redemption_id, body.expected_revision, body.reason
                )
        return _receipt(receipt)

    @router.get("/requests/{action}/{key}", response_model=ReceiptResponse)
    def original(
        action: RewardAction,
        key: Identifier,
        request: Request,
        query: Annotated[_EmptyQuery, Query()],
    ) -> ReceiptResponse:
        return _receipt(context(request).reward_original(action, key))

    return router
