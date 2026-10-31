"""Strict household wire contracts adapt only server-bound application use cases."""

import re
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, Request
from fastapi.params import Depends
from fastapi.routing import APIRoute
from pydantic import Field
from starlette.responses import Response

from domus.application.household_commands import HouseholdCommands, SetupHousehold
from domus.application.household_queries import AccessState, HouseholdQueries
from domus.application.member_commands import MemberCommands, UpdateMember
from domus.application.policy_commands import PolicyCommands, UpdatePolicy
from domus.domain.errors import DomusError, InvalidInput
from domus.domain.identity import (
    AdministratorMapping,
    MappingMode,
    MemberStatus,
    Permission,
    PermissionRule,
    ProfileRule,
    Role,
)
from domus.domain.storage import JsonDocument, JsonValue, Receipt
from domus.entrypoints.http_contract import StrictModel


@dataclass(frozen=True, slots=True)
class HouseholdHTTPContext:
    queries: Callable[[], HouseholdQueries]
    household: HouseholdCommands
    members: MemberCommands
    policy: PolicyCommands


class _JSONRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def strict_json(request: Request) -> Response:
            if request.method in ("POST", "PUT"):
                media = request.headers.getlist("content-type")
                if len(media) != 1 or not re.fullmatch(
                    r"application/json(?:\s*;\s*charset=utf-8)?", media[0], flags=re.IGNORECASE
                ):
                    raise InvalidInput("invalid_request")
                try:
                    JsonDocument((await request.body()).decode("utf-8"))
                except DomusError, UnicodeError:
                    raise InvalidInput("invalid_request") from None
            return await handler(request)

        return strict_json


class _EmptyQuery(StrictModel):
    pass


class PermissionDecision(StrictModel):
    permission: Permission = Field(strict=False)
    allow: bool


class ProfileDecision(PermissionDecision):
    role: Role = Field(strict=False)


class SetupRequest(StrictModel):
    expected_revision: int = Field(ge=0, le=0)
    name: str = Field(min_length=1, max_length=160)
    time_zone: str = Field(min_length=1, max_length=128)
    mapping_mode: MappingMode = Field(default=MappingMode.ALL, strict=False)
    selected_ha_user_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")


class HouseholdUpdateRequest(StrictModel):
    expected_revision: int = Field(ge=1, le=2**63 - 1)
    name: str = Field(min_length=1, max_length=160)
    time_zone: str = Field(min_length=1, max_length=128)


class EnrollmentRequest(StrictModel):
    expected_revision: int = Field(ge=0, le=0)


class MemberUpdateRequest(StrictModel):
    expected_revision: int = Field(ge=1, le=2**63 - 1)
    role: Role = Field(strict=False)
    status: MemberStatus = Field(strict=False)
    exceptions: list[PermissionDecision] = Field(default_factory=list, max_length=256)


class PolicyUpdateRequest(StrictModel):
    expected_revision: int = Field(ge=1, le=2**63 - 1)
    mapping_mode: MappingMode = Field(strict=False)
    target_ha_user_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    adjustments: list[ProfileDecision] = Field(default_factory=list, max_length=256)


class HouseholdResponse(StrictModel):
    household_id: str
    name: str
    time_zone: str
    revision: int


class MemberResponse(StrictModel):
    member_id: str
    role: Role
    status: MemberStatus
    revision: int
    ha_user_id: str | None = None
    exceptions: tuple[PermissionDecision, ...] | None = None


class MembersResponse(StrictModel):
    members: tuple[MemberResponse, ...]


class MappingResponse(StrictModel):
    mode: MappingMode
    target_ha_user_id: str | None


class PolicyResponse(StrictModel):
    household_id: str
    mapping: MappingResponse
    revision: int
    adjustments: tuple[ProfileDecision, ...]


class AccessResponse(StrictModel):
    state: AccessState
    setup_allowed: bool
    enrollment_allowed: bool
    member: MemberResponse | None
    policy_revision: int | None
    effective_role: Role | None
    permission_scope: Literal["household_administration"]
    permissions: tuple[Permission, ...]


class ReceiptResponse(StrictModel):
    state: Literal["committed"] = "committed"
    operation_id: str
    result: dict[str, JsonValue]
    created_at: int
    message: str = "The household change was saved. Event delivery is tracked separately."
    action_required: str = (
        "Keep the operation ID. If the response was lost, retry the same payload and key."
    )


class OperationResponse(ReceiptResponse):
    delivery: Literal["pending", "delivered"]


def _receipt(receipt: Receipt) -> ReceiptResponse:
    return ReceiptResponse(
        operation_id=receipt.operation_id,
        result=receipt.result.decode(),
        created_at=receipt.created_at,
    )


def _key(request: Request) -> str:
    values = request.headers.getlist("idempotency-key")
    if len(values) != 1 or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", values[0]):
        raise InvalidInput("invalid_idempotency_key")
    return values[0]


def create_household_router(
    context: Callable[[Request], HouseholdHTTPContext], *, security: Depends
) -> APIRouter:
    router = APIRouter(prefix="/api/v1", dependencies=[security], route_class=_JSONRoute)
    write_contract = {
        "parameters": [
            {"name": name, "in": "header", "required": True, "schema": {"type": "string"}}
            for name in ("Idempotency-Key", "Origin", "X-CSRF-Token")
        ]
    }

    @router.get("/authorization", response_model=AccessResponse, response_model_exclude_none=True)
    def access(request: Request, query: Annotated[_EmptyQuery, Query()]) -> AccessResponse:
        return AccessResponse.model_validate(context(request).queries().access())

    @router.get("/household", response_model=HouseholdResponse)
    def household(request: Request, query: Annotated[_EmptyQuery, Query()]) -> HouseholdResponse:
        return HouseholdResponse.model_validate(context(request).queries().household())

    @router.get("/members", response_model=MembersResponse, response_model_exclude_none=True)
    def members(request: Request, query: Annotated[_EmptyQuery, Query()]) -> MembersResponse:
        return MembersResponse(
            members=tuple(
                MemberResponse.model_validate(member)
                for member in context(request).queries().members()
            )
        )

    @router.get("/policy", response_model=PolicyResponse)
    def policy(request: Request, query: Annotated[_EmptyQuery, Query()]) -> PolicyResponse:
        return PolicyResponse.model_validate(context(request).queries().policy())

    @router.get("/operations/{operation_id}", response_model=OperationResponse)
    def operation(
        operation_id: str, request: Request, query: Annotated[_EmptyQuery, Query()]
    ) -> OperationResponse:
        result = context(request).queries().operation(operation_id)
        return OperationResponse(
            **_receipt(result.receipt).model_dump(),
            delivery="delivered" if result.delivered else "pending",
        )

    @router.post("/household", response_model=ReceiptResponse, openapi_extra=write_contract)
    def setup(
        request: Request, body: SetupRequest, query: Annotated[_EmptyQuery, Query()]
    ) -> ReceiptResponse:
        result = context(request).household.setup(
            _key(request),
            SetupHousehold(
                body.name,
                body.time_zone,
                body.mapping_mode,
                body.selected_ha_user_id,
                body.expected_revision,
            ),
        )
        return _receipt(result)

    @router.put("/household", response_model=ReceiptResponse, openapi_extra=write_contract)
    def update_household(
        request: Request, body: HouseholdUpdateRequest, query: Annotated[_EmptyQuery, Query()]
    ) -> ReceiptResponse:
        result = context(request).household.update(
            _key(request), body.name, body.time_zone, body.expected_revision
        )
        return _receipt(result)

    @router.post(
        "/members/enrollment", response_model=ReceiptResponse, openapi_extra=write_contract
    )
    def enroll(
        request: Request, body: EnrollmentRequest, query: Annotated[_EmptyQuery, Query()]
    ) -> ReceiptResponse:
        return _receipt(context(request).household.enroll(_key(request), body.expected_revision))

    @router.put(
        "/members/{member_id}", response_model=ReceiptResponse, openapi_extra=write_contract
    )
    def update_member(
        member_id: str,
        request: Request,
        body: MemberUpdateRequest,
        query: Annotated[_EmptyQuery, Query()],
    ) -> ReceiptResponse:
        result = context(request).members.update(
            _key(request),
            UpdateMember(
                member_id,
                body.expected_revision,
                body.role,
                body.status,
                tuple(PermissionRule(rule.permission, rule.allow) for rule in body.exceptions),
            ),
        )
        return _receipt(result)

    @router.put("/policy", response_model=ReceiptResponse, openapi_extra=write_contract)
    def update_policy(
        request: Request, body: PolicyUpdateRequest, query: Annotated[_EmptyQuery, Query()]
    ) -> ReceiptResponse:
        result = context(request).policy.update(
            _key(request),
            UpdatePolicy(
                body.expected_revision,
                AdministratorMapping(body.mapping_mode, body.target_ha_user_id),
                tuple(
                    ProfileRule(rule.role, rule.permission, rule.allow) for rule in body.adjustments
                ),
            ),
        )
        return _receipt(result)

    return router
