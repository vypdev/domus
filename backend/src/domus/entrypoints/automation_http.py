"""The protected automation preview accepts declarative data and returns a simulation."""

from collections.abc import Callable
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request
from fastapi.params import Depends
from pydantic import Field

from domus.application.automation_drafts import DraftPage, SaveDraft
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
from domus.entrypoints.household_http import (
    ReceiptResponse,
    _EmptyQuery,
    _JSONRoute,
    _key,
    _receipt,
)
from domus.entrypoints.http_contract import StrictModel
from domus.entrypoints.recurrence_http import _require_context
from domus.entrypoints.task_dto import Identifier, PageQuery
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


class AutomationDraftBody(AutomationPreviewBody):
    rule_id: Identifier | None
    expected_revision: str = Field(pattern=r"^(?:0|[1-9][0-9]{0,18})$")


class AutomationDraftDetail(AutomationPreviewBody):
    rule_id: Identifier
    revision: str
    state: Literal["draft"] = "draft"
    enabled: Literal[False] = False


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

    @router.get("/drafts", response_model=DraftPage)
    def drafts(request: Request, query: Annotated[PageQuery, Query()]) -> DraftPage:
        return context(request).automation_drafts.list(limit=query.limit, cursor=query.cursor)

    @router.get("/drafts/{rule_id}", response_model=AutomationDraftDetail)
    def reopen(
        request: Request, rule_id: Identifier, query: Annotated[_EmptyQuery, Query()]
    ) -> AutomationDraftDetail:
        draft = context(request).automation_drafts.reopen(rule_id)
        return AutomationDraftDetail.model_validate(
            {
                **draft.rule.document().decode(),
                "rule_id": draft.rule_id,
                "revision": str(draft.revision),
            }
        )

    @router.post(
        "/drafts",
        response_model=ReceiptResponse,
        openapi_extra={
            "parameters": [
                {"name": name, "in": "header", "required": True, "schema": {"type": "string"}}
                for name in ("Idempotency-Key", "Origin", "X-CSRF-Token")
            ]
        },
    )
    def save(
        request: Request, body: AutomationDraftBody, query: Annotated[_EmptyQuery, Query()]
    ) -> ReceiptResponse:
        receipt = context(request).automation_drafts.save(
            _key(request), SaveDraft(body.rule_id, int(body.expected_revision), body.domain())
        )
        return _receipt(receipt)

    @router.get("/drafts/requests/{key}", response_model=ReceiptResponse)
    def original(
        request: Request, key: Identifier, query: Annotated[_EmptyQuery, Query()]
    ) -> ReceiptResponse:
        return _receipt(context(request).automation_drafts.original(key))

    return router
