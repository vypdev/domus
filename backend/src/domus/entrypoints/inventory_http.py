"""Protected product catalog and original intake receipts."""

from collections.abc import Callable
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request
from fastapi.params import Depends
from pydantic import Field

from domus.application.inventory import CatalogAction
from domus.application.inventory_queries import InventoryView
from domus.domain.inventory import BaseUnit
from domus.domain.task_material_values import MaterialQuantity
from domus.entrypoints.household_http import (
    ReceiptResponse,
    _EmptyQuery,
    _JSONRoute,
    _key,
    _receipt,
)
from domus.entrypoints.http_contract import StrictModel
from domus.entrypoints.recurrence_http import _require_context
from domus.entrypoints.task_dto import Identifier, PageQuery, Quantity
from domus.entrypoints.task_http import TaskHTTPContext


class ProductBody(StrictModel):
    action: Literal["inventory.register-product"]
    name: str = Field(min_length=1, max_length=160)
    base_unit: Annotated[BaseUnit, Field(strict=False)]


class IntakeBody(StrictModel):
    action: Literal["inventory.intake"]
    product_id: Identifier
    quantity: Quantity


CatalogBody = Annotated[ProductBody | IntakeBody, Field(discriminator="action")]


def create_inventory_router(
    context: Callable[[Request], TaskHTTPContext], *, security: Depends
) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/inventory",
        dependencies=[security, Depends(_require_context)],
        route_class=_JSONRoute,
    )

    @router.get("", response_model=InventoryView)
    def catalog(request: Request, query: Annotated[PageQuery, Query()]) -> InventoryView:
        return context(request).inventory().report(limit=query.limit, cursor=query.cursor)

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
        request: Request, body: CatalogBody, query: Annotated[_EmptyQuery, Query()]
    ) -> ReceiptResponse:
        inventory, key = context(request).inventory_commands, _key(request)
        if isinstance(body, ProductBody):
            receipt = inventory.register(key, body.name, body.base_unit)
        else:
            receipt = inventory.intake(key, body.product_id, MaterialQuantity(body.quantity))
        return _receipt(receipt)

    @router.get("/requests/{action}/{key}", response_model=ReceiptResponse)
    def original(
        action: CatalogAction,
        key: Identifier,
        request: Request,
        query: Annotated[_EmptyQuery, Query()],
    ) -> ReceiptResponse:
        return _receipt(context(request).inventory_original(action, key))

    return router
