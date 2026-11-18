"""The protected automation preview accepts declarative data and returns a simulation."""

from collections.abc import Callable
from typing import Annotated, Literal

from fastapi import APIRouter, Body, Query, Request
from fastapi.params import Depends
from pydantic import Field, model_validator

from domus.application.automation_drafts import DraftPage, SaveDraft
from domus.application.automation_execution import (
    RUN_AUTOMATION,
    SET_AUTOMATION_CONTROL,
    ConfigureAutomation,
    RunAutomation,
)
from domus.application.automation_preview import AutomationPreviewAccess
from domus.application.automation_run_history import AutomationRunPage
from domus.application.automation_schedule_preview import DailyAutomationTimes
from domus.domain.automation import (
    AUTOMATION_RULE_VERSION,
    DAILY_TIME_PATTERN,
    MAX_RULE_NODES,
    AutomationRule,
    AutomationSimulation,
    Condition,
    ConditionGroup,
    DailyTrigger,
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


class TaskProposalBody(StrictModel):
    condition: ConditionBody | None
    action: CreateTaskProposalBody

    def rule(self, version: int, trigger: Literal["manual"] | DailyTrigger) -> AutomationRule:
        return AutomationRule(
            version,
            trigger,
            None if self.condition is None else _condition(self.condition),
            TaskContent(self.action.title),
        )


class AutomationPreviewBody(TaskProposalBody):
    version: int = Field(ge=AUTOMATION_RULE_VERSION, le=AUTOMATION_RULE_VERSION)
    trigger: ManualTriggerBody

    def domain(self) -> AutomationRule:
        return self.rule(self.version, self.trigger.kind)


class DailyTriggerBody(StrictModel):
    kind: Literal["daily"]
    time: str = Field(pattern=DAILY_TIME_PATTERN, min_length=5, max_length=5)


class DailyProposalBody(TaskProposalBody):
    version: Literal[2]
    trigger: DailyTriggerBody

    def domain(self) -> AutomationRule:
        return self.rule(self.version, DailyTrigger(self.trigger.time))


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


class DailyAutomationQuery(StrictModel):
    time: str = Field(pattern=DAILY_TIME_PATTERN, min_length=5, max_length=5)


class DraftSaveBody(StrictModel):
    rule_id: Identifier | None
    expected_revision: str = Field(
        pattern=_revision_pattern(allow_zero=True),
        description="Use zero to create a draft and a positive signed 64-bit revision to edit.",
    )

    @model_validator(mode="before")
    @classmethod
    def _strict_version(cls, value: object) -> object:
        if not isinstance(value, dict) or type(value.get("version")) is not int:
            raise ValueError("automation version must be an integer")
        return value


class AutomationDraftBody(AutomationPreviewBody, DraftSaveBody):
    version: Literal[1]


class DailyAutomationDraftBody(DailyProposalBody, DraftSaveBody):
    pass


type AutomationDraftRequest = Annotated[
    AutomationDraftBody | DailyAutomationDraftBody, Body(discriminator="version")
]


class DraftIdentity(StrictModel):
    rule_id: Identifier
    revision: str
    state: Literal["draft"] = "draft"
    enabled: Literal[False] = False


class AutomationDraftDetail(AutomationPreviewBody, DraftIdentity):
    version: Literal[1]


class DailyAutomationDraftDetail(DailyProposalBody, DraftIdentity):
    pass


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
    latest_manual: bool = True


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

    @router.get("/schedule-preview", response_model=DailyAutomationTimes)
    def daily_preview(
        request: Request, query: Annotated[DailyAutomationQuery, Query()]
    ) -> DailyAutomationTimes:
        return context(request).automation_schedule().daily(query.time)

    @router.get("/drafts", response_model=DraftPage)
    def drafts(request: Request, query: Annotated[PageQuery, Query()]) -> DraftPage:
        return context(request).automation_drafts.list(limit=query.limit, cursor=query.cursor)

    @router.get(
        "/drafts/{rule_id}", response_model=AutomationDraftDetail | DailyAutomationDraftDetail
    )
    def reopen(
        request: Request, rule_id: Identifier, query: Annotated[_EmptyQuery, Query()]
    ) -> AutomationDraftDetail | DailyAutomationDraftDetail:
        draft = context(request).automation_drafts.reopen(rule_id)
        detail = (
            AutomationDraftDetail if draft.rule.trigger == "manual" else DailyAutomationDraftDetail
        )
        return detail.model_validate(
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
        request: Request, body: AutomationDraftRequest, query: Annotated[_EmptyQuery, Query()]
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

    @router.get(
        "/drafts/{rule_id}/execution",
        response_model=AutomationExecutionDetail,
        response_model_exclude_defaults=True,
    )
    def execution_state(
        request: Request, rule_id: Identifier, query: Annotated[_EmptyQuery, Query()]
    ) -> AutomationExecutionDetail:
        value = context(request).automation_execution.state(rule_id)
        control = value.control
        return AutomationExecutionDetail(
            rule_id=value.rule_id,
            latest_revision=str(value.latest_revision),
            latest_title=value.latest_title,
            latest_manual=value.latest_manual,
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

    @router.get("/drafts/{rule_id}/runs", response_model=AutomationRunPage)
    def run_history(
        request: Request, rule_id: Identifier, query: Annotated[PageQuery, Query()]
    ) -> AutomationRunPage:
        return context(request).automation_run_history.page(
            rule_id, limit=query.limit, cursor=query.cursor
        )

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
