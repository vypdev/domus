"""Closed inputs for authorized fixed and completion-relative task creation."""

from collections.abc import Callable
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import Field

from domus.application.recurrence_commands import CreateFixedTask, RecurrenceCommands
from domus.application.relative_recurrence_commands import (
    CreateRelativeTask,
    RelativeRecurrenceCommands,
)
from domus.application.task_queries import TaskQueries
from domus.application.task_requests import CreateTask
from domus.domain.recurrence_rule_text import parse_fixed_pattern
from domus.domain.recurrence_time import FoldPolicy, RelativeInterval, TimePolicy
from domus.domain.relative_recurrence import SuccessorVisibility
from domus.domain.task_values import TaskOverrides
from domus.entrypoints.household_http import (
    OperationResponse,
    ReceiptResponse,
    _EmptyQuery,
    _JSONRoute,
    _key,
    _receipt,
)
from domus.entrypoints.http_contract import StrictModel
from domus.entrypoints.recurrence_dto import NominalBody, nominal
from domus.entrypoints.recurrence_http import _require_context
from domus.entrypoints.task_dto import Identifier, PointValueMinor, Revision, TaskTextBody

ScheduleCreationAction = Literal["recurrence.fixed.create", "recurrence.relative.create"]


class ScheduleCreationPolicyBody(StrictModel):
    zone: Annotated[str, Field(min_length=1, max_length=128)]
    data_identity: Annotated[str, Field(min_length=1, max_length=128)]
    repeated_time: Literal["first_instant", "second_instant"]
    revision: Revision

    def domain(self) -> TimePolicy:
        return TimePolicy(
            self.zone, self.data_identity, FoldPolicy(self.repeated_time), self.revision
        )


class ScheduledTaskOverridesBody(StrictModel):
    point_value_minor: PointValueMinor


class ScheduledTaskTextBody(TaskTextBody):
    overrides: ScheduledTaskOverridesBody | None = None

    def domain(self) -> CreateTask:
        amount = None if self.overrides is None else self.overrides.point_value_minor
        return CreateTask(self.content(), overrides=TaskOverrides(point_value_minor=amount))


class ScheduledTaskBody(StrictModel):
    task: ScheduledTaskTextBody
    start: NominalBody
    policy: ScheduleCreationPolicyBody


class FixedTaskBody(ScheduledTaskBody):
    rrule: Annotated[str, Field(min_length=1, max_length=2048)]


class RelativeTaskBody(ScheduledTaskBody):
    interval_days: Annotated[int, Field(ge=1, le=36600)]
    visibility: Literal["at_completion", "at_verification"] = "at_completion"


class ScheduledTaskOriginalResponse(OperationResponse):
    action: ScheduleCreationAction
    command_key: str


def create_schedule_creation_router(
    fixed: Callable[[Request], RecurrenceCommands],
    relative: Callable[[Request], RelativeRecurrenceCommands],
    queries: Callable[[Request], TaskQueries],
) -> APIRouter:
    router = APIRouter(
        prefix="/recurrence/creation",
        dependencies=[Depends(_require_context)],
        route_class=_JSONRoute,
    )
    write_contract = {
        "parameters": [
            {"name": name, "in": "header", "required": True, "schema": {"type": "string"}}
            for name in ("Idempotency-Key", "Origin", "X-CSRF-Token")
        ]
    }

    @router.post("/fixed", response_model=ReceiptResponse, openapi_extra=write_contract)
    def create_fixed(
        request: Request, body: FixedTaskBody, query: Annotated[_EmptyQuery, Query()]
    ) -> ReceiptResponse:
        return _receipt(
            fixed(request).create_fixed(
                _key(request),
                CreateFixedTask(
                    body.task.domain(),
                    parse_fixed_pattern(body.rrule, nominal(body.start)),
                    body.policy.domain(),
                ),
            )
        )

    @router.post("/relative", response_model=ReceiptResponse, openapi_extra=write_contract)
    def create_relative(
        request: Request, body: RelativeTaskBody, query: Annotated[_EmptyQuery, Query()]
    ) -> ReceiptResponse:
        return _receipt(
            relative(request).create(
                _key(request),
                CreateRelativeTask(
                    body.task.domain(),
                    nominal(body.start),
                    RelativeInterval(body.interval_days),
                    body.policy.domain(),
                    SuccessorVisibility(body.visibility),
                ),
            )
        )

    @router.get("/requests/{action}/{key}", response_model=ScheduledTaskOriginalResponse)
    def original(
        action: ScheduleCreationAction,
        key: Identifier,
        request: Request,
        query: Annotated[_EmptyQuery, Query()],
    ) -> ScheduledTaskOriginalResponse:
        view = queries(request).original_schedule(action, key)
        return ScheduledTaskOriginalResponse(
            **_receipt(view.receipt).model_dump(),
            action=action,
            command_key=key,
            delivery="suppressed"
            if view.receipt.historical
            else "delivered"
            if view.delivered
            else "pending",
        )

    return router
