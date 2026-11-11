"""The protected automation preview accepts declarative data and returns a simulation."""

from collections.abc import Callable
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request
from fastapi.params import Depends
from pydantic import Field

from domus.application.automation_preview import AutomationPreviewAccess
from domus.domain.automation import (
    AUTOMATION_RULE_VERSION,
    MAX_RULE_NODES,
    AutomationRule,
    AutomationSimulation,
    Condition,
    ConditionGroup,
    NegatedCondition,
    StockCondition,
)
from domus.domain.task_values import TaskContent
from domus.entrypoints.household_http import _EmptyQuery, _JSONRoute
from domus.entrypoints.http_contract import StrictModel
from domus.entrypoints.recurrence_http import _require_context
from domus.entrypoints.task_dto import Identifier
from domus.entrypoints.task_http import TaskHTTPContext


class ManualTriggerBody(StrictModel):
    kind: Literal["manual"]


class CreateTaskProposalBody(StrictModel):
    kind: Literal["task.create"]
    title: str = Field(min_length=1, max_length=160)


class StockConditionBody(StrictModel):
    kind: Literal["stock_below_minimum"]
    product_id: Identifier


class ConditionGroupBody(StrictModel):
    kind: Literal["all", "any"]
    children: Annotated[list[ConditionBody], Field(min_length=1, max_length=MAX_RULE_NODES)]


class NegatedConditionBody(StrictModel):
    kind: Literal["not"]
    child: ConditionBody


type ConditionBody = Annotated[
    StockConditionBody | ConditionGroupBody | NegatedConditionBody, Field(discriminator="kind")
]


def _condition(body: ConditionBody) -> Condition:
    if isinstance(body, StockConditionBody):
        return StockCondition(body.product_id)
    if isinstance(body, ConditionGroupBody):
        return ConditionGroup(body.kind, tuple(_condition(child) for child in body.children))
    return NegatedCondition(_condition(body.child))


class AutomationPreviewBody(StrictModel):
    version: int = Field(ge=AUTOMATION_RULE_VERSION, le=AUTOMATION_RULE_VERSION)
    trigger: ManualTriggerBody
    condition: ConditionBody | None
    action: CreateTaskProposalBody

    def domain(self) -> AutomationRule:
        return AutomationRule(
            self.version,
            self.trigger.kind,
            None if self.condition is None else _condition(self.condition),
            TaskContent(self.action.title),
        )


def create_automation_router(
    context: Callable[[Request], TaskHTTPContext], *, security: Depends
) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/automation",
        dependencies=[security, Depends(_require_context)],
        route_class=_JSONRoute,
    )

    @router.get("/preview-access", response_model=AutomationPreviewAccess)
    def access(request: Request, query: Annotated[_EmptyQuery, Query()]) -> AutomationPreviewAccess:
        return context(request).automation().access()

    @router.post(
        "/preview",
        response_model=AutomationSimulation,
        openapi_extra={
            "parameters": [
                {"name": name, "in": "header", "required": True, "schema": {"type": "string"}}
                for name in ("Origin", "X-CSRF-Token")
            ]
        },
    )
    def preview(
        request: Request, body: AutomationPreviewBody, query: Annotated[_EmptyQuery, Query()]
    ) -> AutomationSimulation:
        return context(request).automation().preview(body.domain())

    return router
