"""Protected profile routes use the same session/body boundaries as existing household actions."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, cast

from fastapi import APIRouter, Query, Request
from fastapi.params import Depends

from domus.application.household_administration_queries import HouseholdAdministrationQueries
from domus.application.household_queries import ADMINISTRATION_ACTIONS, HouseholdQueries
from domus.application.member_profile_commands import (
    AliasUpdate,
    MemberProfileCommands,
    PreferencesUpdate,
)
from domus.domain.storage import Receipt
from domus.entrypoints.administration_dto import (
    AdministrationAction,
    AdministrationCapabilities,
    AdministrationOperation,
    AdministrationReceipt,
    AliasRequest,
    PreferencesRequest,
    PreferencesResponse,
    PresentationResponse,
)
from domus.entrypoints.household_http import _EmptyQuery, _JSONRoute, _key, _receipt


@dataclass(frozen=True, slots=True)
class AdministrationHTTPContext:
    queries: Callable[[], HouseholdAdministrationQueries]
    commands: MemberProfileCommands
    operations: Callable[[], HouseholdQueries]


def _profile_receipt(receipt: Receipt) -> AdministrationReceipt:
    result = _receipt(receipt)
    if not receipt.historical:
        result.message = "The profile change was saved. Notification delivery is unavailable."
        result.action_required = (
            "Review current state. Keep the original request key and operation ID."
        )
    return AdministrationReceipt(**result.model_dump())


def create_administration_router(
    context: Callable[[Request], AdministrationHTTPContext], *, security: Depends
) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/administration", dependencies=[security], route_class=_JSONRoute
    )
    write_contract = {
        "parameters": [
            {"name": name, "in": "header", "required": True, "schema": {"type": "string"}}
            for name in ("Idempotency-Key", "Origin", "X-CSRF-Token")
        ]
    }

    @router.get("/capabilities", response_model=AdministrationCapabilities)
    def capabilities(
        request: Request, query: Annotated[_EmptyQuery, Query()]
    ) -> AdministrationCapabilities:
        # Available routes are not a caller grant or acceptance of the complete workspace.
        context(request).operations().access()
        return AdministrationCapabilities(
            actions=cast(tuple[AdministrationAction, ...], tuple(sorted(ADMINISTRATION_ACTIONS)))
        )

    @router.get("/preferences", response_model=PreferencesResponse)
    def preferences(
        request: Request, query: Annotated[_EmptyQuery, Query()]
    ) -> PreferencesResponse:
        return PreferencesResponse.model_validate(context(request).queries().preferences())

    @router.get("/members/{member_id}/presentation", response_model=PresentationResponse)
    def presentation(
        member_id: str, request: Request, query: Annotated[_EmptyQuery, Query()]
    ) -> PresentationResponse:
        return PresentationResponse.model_validate(
            context(request).queries().presentation(member_id)
        )

    @router.put("/preferences", response_model=AdministrationReceipt, openapi_extra=write_contract)
    def update_preferences(
        request: Request, body: PreferencesRequest, query: Annotated[_EmptyQuery, Query()]
    ) -> AdministrationReceipt:
        receipt = context(request).commands.update_preferences(
            _key(request),
            PreferencesUpdate(
                body.expected_revision, body.locale, body.routine_participation_summaries
            ),
        )
        return _profile_receipt(receipt)

    @router.put(
        "/members/{member_id}/presentation",
        response_model=AdministrationReceipt,
        openapi_extra=write_contract,
    )
    def update_presentation(
        member_id: str, request: Request, body: AliasRequest, query: Annotated[_EmptyQuery, Query()]
    ) -> AdministrationReceipt:
        return _profile_receipt(
            context(request).commands.update_alias(
                _key(request), AliasUpdate(member_id, body.expected_revision, body.alias)
            )
        )

    @router.get("/requests/{action}/{key}", response_model=AdministrationOperation)
    def original_request(
        action: AdministrationAction,
        key: str,
        request: Request,
        query: Annotated[_EmptyQuery, Query()],
    ) -> AdministrationOperation:
        result = context(request).operations().administration_request(action, key)
        return AdministrationOperation(
            **_profile_receipt(result.receipt).model_dump(),
            action=action,
            command_key=key,
            event_delivery=(
                "delivered"
                if result.delivered
                else "suppressed"
                if result.receipt.historical
                else "pending"
            ),
        )

    return router
