"""Protected category routes use the existing task session and request context."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from pydantic import Field

from domus.application.task_category_commands import (
    CategoryAction,
    CategoryCatalog,
    TaskCategoryCommands,
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
from domus.entrypoints.task_dto import Identifier, Revision

CategoryLabel = Annotated[str, Field(min_length=1, max_length=256)]


class CreateCategoryBody(StrictModel):
    label: CategoryLabel
    expected_revision: int = Field(default=0, ge=0, le=0)


class ArchiveCategoryBody(StrictModel):
    expected_revision: Revision


class RenameCategoryBody(ArchiveCategoryBody):
    label: CategoryLabel


class CategoryOriginalResponse(ReceiptResponse):
    action: CategoryAction
    command_key: str


def create_task_category_router(
    commands: Callable[[Request], TaskCategoryCommands],
) -> APIRouter:
    router = APIRouter(
        prefix="/categories", dependencies=[Depends(_require_context)], route_class=_JSONRoute
    )
    write_contract = {
        "parameters": [
            {"name": name, "in": "header", "required": True, "schema": {"type": "string"}}
            for name in ("Idempotency-Key", "Origin", "X-CSRF-Token")
        ]
    }

    @router.get("", response_model=CategoryCatalog)
    def catalog(request: Request, query: Annotated[_EmptyQuery, Query()]) -> CategoryCatalog:
        return commands(request).catalog()

    @router.post("", response_model=ReceiptResponse, openapi_extra=write_contract)
    def create(
        request: Request, body: CreateCategoryBody, query: Annotated[_EmptyQuery, Query()]
    ) -> ReceiptResponse:
        return _receipt(commands(request).create(_key(request), body.label))

    @router.put("/{category_id}", response_model=ReceiptResponse, openapi_extra=write_contract)
    def rename(
        category_id: Identifier,
        request: Request,
        body: RenameCategoryBody,
        query: Annotated[_EmptyQuery, Query()],
    ) -> ReceiptResponse:
        return _receipt(
            commands(request).rename(_key(request), category_id, body.expected_revision, body.label)
        )

    @router.post(
        "/{category_id}/archive", response_model=ReceiptResponse, openapi_extra=write_contract
    )
    def archive(
        category_id: Identifier,
        request: Request,
        body: ArchiveCategoryBody,
        query: Annotated[_EmptyQuery, Query()],
    ) -> ReceiptResponse:
        return _receipt(
            commands(request).archive(_key(request), category_id, body.expected_revision)
        )

    @router.get("/requests/{action}/{key}", response_model=CategoryOriginalResponse)
    def original(
        action: CategoryAction,
        key: Identifier,
        request: Request,
        query: Annotated[_EmptyQuery, Query()],
    ) -> CategoryOriginalResponse:
        receipt = commands(request).original(action, key)
        return CategoryOriginalResponse(
            **_receipt(receipt).model_dump(), action=action, command_key=key
        )

    return router
