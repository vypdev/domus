"""The protected automation preview accepts declarative data and returns a simulation."""

from collections.abc import Callable
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request
from fastapi.params import Depends
from pydantic import Field

from domus.application.automation_drafts import DraftPage, SaveDraft
from domus.application.automation_execution import (
    RUN_AUTOMATION,
    SET_AUTOMATION_CONTROL,
    ConfigureAutomation,
    RunAutomation,
)
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
from domus.domain.identity import MAX_REVISION
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


def _revision_pattern(*, allow_zero: bool) -> str:
    # JSON Schema applies a numeric maximum to numbers only. For a decimal
    # string, match shorter values and each prefix that first falls below the limit.
    maximum = str(MAX_REVISION)
    alternatives = ["0"] if allow_zero else []
    alternatives.extend((f"[1-9][0-9]{{0,{len(maximum) - 2}}}", maximum))
    for index, digit in enumerate(maximum):
        first_digit = 1 if index == 0 else 0
        last_digit = int(digit) - 1
        if first_digit <= last_digit:
            remaining = len(maximum) - index - 1
            alternatives.append(
                f"{maximum[:index]}[{first_digit}-{last_digit}][0-9]{{{remaining}}}"
            )
    return "^(?:" + "|".join(alternatives) + ")$"


class AutomationDraftBody(AutomationPreviewBody):
    rule_id: Identifier | None
    expected_revision: str = Field(
        pattern=_revision_pattern(allow_zero=True),
        description="Use zero to create a draft and a positive signed 64-bit revision to edit.",
    )


class AutomationDraftDetail(AutomationPreviewBody):
    rule_id: Identifier
    revision: str
    state: Literal["draft"] = "draft"
    enabled: Literal[False] = False


type RevisionText = Annotated[str, Field(pattern=_revision_pattern(allow_zero=False))]
type ControlRevisionText = Annotated[str, Field(pattern=_revision_pattern(allow_zero=True))]


class ConfigureAutomationBody(StrictModel):
    rule_revision: RevisionText
    expected_control_revision: ControlRevisionText
    enabled: bool


class RunAutomationBody(StrictModel):
    rule_revision: RevisionText
    control_revision: RevisionText


class AutomationControlDetail(StrictModel):
    rule_revision: RevisionText
    control_revision: RevisionText
    enabled: bool
    title: str = Field(min_length=1, max_length=160)


class AutomationExecutionDetail(StrictModel):
    rule_id: Identifier
    latest_revision: RevisionText
    latest_title: str = Field(min_length=1, max_length=160)
    control: AutomationControlDetail | None


_WRITE_HEADERS = {
    "parameters": [
        {"name": name, "in": "header", "required": True, "schema": {"type": "string"}}
        for name in ("Idempotency-Key", "Origin", "X-CSRF-Token")
    ]
}


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
        openapi_extra=_WRITE_HEADERS,
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

    @router.get("/drafts/{rule_id}/execution", response_model=AutomationExecutionDetail)
    def execution_state(
        request: Request, rule_id: Identifier, query: Annotated[_EmptyQuery, Query()]
    ) -> AutomationExecutionDetail:
        value = context(request).automation_execution.state(rule_id)
        control = value.control
        return AutomationExecutionDetail(
            rule_id=value.rule_id,
            latest_revision=str(value.latest_revision),
            latest_title=value.latest_title,
            control=None
            if control is None
            else AutomationControlDetail(
                rule_revision=str(control.rule_revision),
                control_revision=str(control.control_revision),
                enabled=control.enabled,
                title=control.title,
            ),
        )

    @router.post(
        "/drafts/{rule_id}/execution",
        response_model=ReceiptResponse,
        openapi_extra=_WRITE_HEADERS,
    )
    def configure(
        request: Request,
        rule_id: Identifier,
        body: ConfigureAutomationBody,
        query: Annotated[_EmptyQuery, Query()],
    ) -> ReceiptResponse:
        receipt = context(request).automation_execution.configure(
            _key(request),
            ConfigureAutomation(
                rule_id, int(body.rule_revision), int(body.expected_control_revision), body.enabled
            ),
        )
        return _receipt(receipt)

    @router.post(
        "/drafts/{rule_id}/runs",
        response_model=ReceiptResponse,
        openapi_extra=_WRITE_HEADERS,
    )
    def run(
        request: Request,
        rule_id: Identifier,
        body: RunAutomationBody,
        query: Annotated[_EmptyQuery, Query()],
    ) -> ReceiptResponse:
        receipt = context(request).automation_execution.run(
            _key(request),
            RunAutomation(rule_id, int(body.rule_revision), int(body.control_revision)),
        )
        return _receipt(receipt)

    @router.get("/execution/requests/{kind}/{key}", response_model=ReceiptResponse)
    def original_execution(
        request: Request,
        kind: Literal["configure", "run"],
        key: Identifier,
        query: Annotated[_EmptyQuery, Query()],
    ) -> ReceiptResponse:
        action = SET_AUTOMATION_CONTROL if kind == "configure" else RUN_AUTOMATION
        return _receipt(context(request).automation_execution.original(action, key))

    return router
