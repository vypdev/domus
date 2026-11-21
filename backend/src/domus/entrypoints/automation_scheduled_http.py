"""Strict protected review, control and history for household-owned daily rules."""

from collections.abc import Callable
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Query, Request
from fastapi.params import Depends
from pydantic import Field

from domus.application.automation_scheduled_control import (
    ADOPT_DAILY_POLICY,
    DISABLE_DAILY_AUTOMATION,
    ENABLE_DAILY_AUTOMATION,
    DailyAutomationReview,
    DailyControlRequest,
    ReviewedDailyRequest,
)
from domus.application.automation_scheduled_documents import planned_document, read_planned
from domus.application.automation_scheduled_history import ScheduledRunPage
from domus.domain.automation import DailyTrigger
from domus.domain.fold_policy import FoldPolicy
from domus.domain.recurrence_time import MAX_INSTANT_MS, ResolvedTime, TimePolicy, TimeResolution
from domus.domain.storage import JsonDocument, JsonObject
from domus.entrypoints.automation_http import (
    _WRITE_HEADERS,
    ConditionBody,
    ControlRevisionText,
    DailyProposalBody,
    RevisionText,
)
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


class DailyPolicyBody(StrictModel):
    zone: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_+\-/]+$")
    data_identity: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9:/_.\-]+$")
    repeated_time: Annotated[FoldPolicy, Field(strict=False)]
    revision: RevisionText

    @classmethod
    def of(cls, policy: TimePolicy) -> DailyPolicyBody:
        return cls(
            zone=policy.zone,
            data_identity=policy.data_identity,
            repeated_time=policy.repeated_time,
            revision=str(policy.revision),
        )


class DailyTimeBody(StrictModel):
    nominal: str = Field(min_length=19, max_length=26)
    policy: DailyPolicyBody
    resolved_local: str = Field(min_length=19, max_length=26)
    offset_seconds: int = Field(gt=-86400, lt=86400)
    resolution: Annotated[TimeResolution, Field(strict=False)]
    zone_digest: str = Field(pattern=r"^[a-f0-9]{64}$")

    def domain(self) -> ResolvedTime:
        data = self.model_dump(mode="json")
        data["policy"]["revision"] = int(self.policy.revision)
        return read_planned(JsonDocument.from_value(data))

    @classmethod
    def of(cls, value: ResolvedTime) -> DailyTimeBody:
        data = planned_document(value).decode()
        policy = cast(JsonObject, data["policy"])
        policy["revision"] = str(policy["revision"])
        return cls.model_validate(data)


class DailyRevisionQuery(StrictModel):
    revision: RevisionText


class DailyControlBody(StrictModel):
    rule_revision: RevisionText
    expected_control_revision: ControlRevisionText
    expected_schedule_revision: ControlRevisionText

    def domain(self, rule_id: str) -> DailyControlRequest:
        return DailyControlRequest(
            rule_id,
            int(self.rule_revision),
            int(self.expected_control_revision),
            int(self.expected_schedule_revision),
        )


class DailyReviewedBody(DailyControlBody):
    reviewed: DailyTimeBody

    def reviewed_request(self, rule_id: str) -> ReviewedDailyRequest:
        value = self.domain(rule_id)
        return ReviewedDailyRequest(
            value.rule_id,
            value.rule_revision,
            value.expected_control_revision,
            value.expected_schedule_revision,
            self.reviewed.domain(),
        )


class DailySuppressionDetail(StrictModel):
    first: DailyTimeBody
    through_ms: int = Field(ge=0, le=MAX_INSTANT_MS)


class DailyExecutionDetail(StrictModel):
    rule_id: Identifier
    rule_revision: RevisionText
    title: str
    requested_time: str
    control_revision: ControlRevisionText
    schedule_revision: ControlRevisionText
    enabled: bool
    active_trigger: Literal["manual", "daily"] | None
    active_rule_revision: RevisionText | None
    active_title: str | None
    grant_owner: Literal["household_rule"] = "household_rule"
    capability: Literal["task.create"] = "task.create"
    condition_product_ids: tuple[str, ...]
    condition: ConditionBody | None
    may_enable: bool
    approved_policy: DailyPolicyBody | None
    proposed_policy: DailyPolicyBody
    approved_times: tuple[DailyTimeBody, ...] | None
    proposed_times: tuple[DailyTimeBody, ...]
    proposed_unavailable: bool
    approved_unavailable: bool
    policy_changed: bool
    next_time: DailyTimeBody | None
    suppression: DailySuppressionDetail | None

    @classmethod
    def of(cls, value: DailyAutomationReview) -> DailyExecutionDetail:
        schedule, control, active = value.schedule, value.control, value.active_draft
        active_enabled = control is not None and control.enabled and active is not None
        enabled = schedule is not None and schedule.grant.permits(
            schedule.grant.installation,
            schedule.grant.household_id,
            control,
            schedule.grant.grant_id,
        )
        return cls(
            rule_id=value.draft.rule_id,
            rule_revision=str(value.draft.revision),
            title=value.draft.rule.task.title,
            requested_time=cast(DailyTrigger, value.draft.rule.trigger).time,
            control_revision="0" if control is None else str(control.control_revision),
            schedule_revision="0" if schedule is None else str(schedule.revision),
            enabled=enabled,
            active_trigger=None
            if not active_enabled or active is None
            else ("manual" if active.rule.trigger == "manual" else "daily"),
            active_rule_revision=None
            if not active_enabled or active is None
            else str(active.revision),
            active_title=None if not active_enabled or active is None else active.rule.task.title,
            condition_product_ids=value.draft.rule.stock_products(),
            condition=DailyProposalBody.model_validate(
                value.draft.rule.document().decode()
            ).condition,
            may_enable=value.may_grant_tasks,
            approved_policy=None if schedule is None else DailyPolicyBody.of(schedule.policy),
            proposed_policy=DailyPolicyBody.of(value.proposed_policy),
            approved_times=None
            if value.approved_times is None
            else tuple(DailyTimeBody.of(item) for item in value.approved_times),
            proposed_times=tuple(DailyTimeBody.of(item) for item in value.proposed_times),
            proposed_unavailable=value.proposed_error is not None,
            approved_unavailable=value.approved_error is not None,
            policy_changed=value.policy_changed,
            next_time=None if schedule is None else DailyTimeBody.of(schedule.next_time),
            suppression=None
            if schedule is None or schedule.suppression is None
            else DailySuppressionDetail(
                first=DailyTimeBody.of(schedule.suppression.first),
                through_ms=schedule.suppression.through_ms,
            ),
        )


def create_daily_automation_router(
    context: Callable[[Request], TaskHTTPContext], *, security: Depends
) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/automation",
        dependencies=[security, Depends(_require_context)],
        route_class=_JSONRoute,
    )

    @router.get("/drafts/{rule_id}/daily", response_model=DailyExecutionDetail)
    def review(
        request: Request, rule_id: Identifier, query: Annotated[DailyRevisionQuery, Query()]
    ) -> DailyExecutionDetail:
        return DailyExecutionDetail.of(
            context(request).daily_automation.review(rule_id, int(query.revision))
        )

    @router.get("/drafts/{rule_id}/daily/active", response_model=DailyExecutionDetail | None)
    def active(
        request: Request, rule_id: Identifier, query: Annotated[_EmptyQuery, Query()]
    ) -> DailyExecutionDetail | None:
        value = context(request).daily_automation.active_review(rule_id)
        return None if value is None else DailyExecutionDetail.of(value)

    @router.post(
        "/drafts/{rule_id}/daily/enable",
        response_model=ReceiptResponse,
        openapi_extra=_WRITE_HEADERS,
    )
    def enable(
        request: Request,
        rule_id: Identifier,
        body: DailyReviewedBody,
        query: Annotated[_EmptyQuery, Query()],
    ) -> ReceiptResponse:
        return _receipt(
            context(request).daily_automation.enable(_key(request), body.reviewed_request(rule_id))
        )

    @router.post(
        "/drafts/{rule_id}/daily/disable",
        response_model=ReceiptResponse,
        openapi_extra=_WRITE_HEADERS,
    )
    def disable(
        request: Request,
        rule_id: Identifier,
        body: DailyControlBody,
        query: Annotated[_EmptyQuery, Query()],
    ) -> ReceiptResponse:
        return _receipt(
            context(request).daily_automation.disable(_key(request), body.domain(rule_id))
        )

    @router.post(
        "/drafts/{rule_id}/daily/adopt",
        response_model=ReceiptResponse,
        openapi_extra=_WRITE_HEADERS,
    )
    def adopt(
        request: Request,
        rule_id: Identifier,
        body: DailyReviewedBody,
        query: Annotated[_EmptyQuery, Query()],
    ) -> ReceiptResponse:
        return _receipt(
            context(request).daily_automation.adopt(_key(request), body.reviewed_request(rule_id))
        )

    @router.get("/daily/requests/{action}/{key}", response_model=ReceiptResponse)
    def original(
        request: Request,
        action: Literal["enable", "disable", "adopt"],
        key: Identifier,
        query: Annotated[_EmptyQuery, Query()],
    ) -> ReceiptResponse:
        selected = {
            "enable": ENABLE_DAILY_AUTOMATION,
            "disable": DISABLE_DAILY_AUTOMATION,
            "adopt": ADOPT_DAILY_POLICY,
        }[action]
        return _receipt(context(request).daily_automation.original(selected, key))

    @router.get("/drafts/{rule_id}/daily/runs", response_model=ScheduledRunPage)
    def runs(
        request: Request, rule_id: Identifier, query: Annotated[PageQuery, Query()]
    ) -> ScheduledRunPage:
        return context(request).daily_automation_history.page(
            rule_id, limit=query.limit, cursor=query.cursor
        )

    return router
