"""Protected product catalog and original intake receipts."""

from collections.abc import Callable
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request
from fastapi.params import Depends
from pydantic import Field

from domus.application.inventory import CatalogAction
from domus.application.inventory_queries import (
    InventoryView,
    MovementHistory,
    PhysicalReceiptsView,
    PurchaseSessionDetail,
    PurchaseSessionsView,
    PurchasesView,
)
from domus.application.shopping_list import ShoppingListView, ShoppingSourcesView
from domus.domain.inventory import MAX_STOCK_REASON, BaseUnit
from domus.domain.shopping import MAX_SESSION_ITEMS, MIN_SESSION_ITEMS, SessionSelection
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


StockReason = Annotated[str, Field(min_length=1, max_length=MAX_STOCK_REASON)]
SignedQuantity = Annotated[
    str,
    Field(min_length=1, max_length=20, pattern=r"^-?(?:0|[1-9][0-9]{0,11})(?:\.[0-9]{0,5}[1-9])?$"),
]


class AdjustmentBody(StrictModel):
    action: Literal["inventory.adjust"]
    product_id: Identifier
    quantity: SignedQuantity
    reason: StockReason


class IntakeCorrectionBody(StrictModel):
    action: Literal["inventory.correct-intake"]
    product_id: Identifier
    movement_id: Identifier
    reason: StockReason


class ReplenishmentBody(StrictModel):
    action: Literal["inventory.configure-replenishment"]
    product_id: Identifier
    minimum: Quantity
    target: Quantity
    expected_revision: str = Field(pattern=r"^(?:0|[1-9][0-9]{0,18})$")


class PurchaseBody(StrictModel):
    action: Literal["shopping.purchase"]
    product_id: Identifier | None
    name: Annotated[str, Field(min_length=1, max_length=160)] | None
    quantity: Quantity


class ReceivePurchaseBody(StrictModel):
    action: Literal["shopping.receive"]
    purchase_id: Identifier
    quantity: Quantity
    expected_revision: str = Field(pattern=r"^[1-9][0-9]{0,18}$")


class PostReceiptBody(StrictModel):
    action: Literal["shopping.post-receipt"]
    purchase_id: Identifier
    receipt_id: Identifier


class AddExtraBody(StrictModel):
    action: Literal["shopping.add-extra"]
    product_id: Identifier | None
    name: Annotated[str, Field(min_length=1, max_length=160)] | None
    quantity: Quantity


class ClearExtraBody(StrictModel):
    action: Literal["shopping.clear-extra"]
    extra_id: Identifier


class SessionSelectionBody(StrictModel):
    product_id: Identifier | None
    extra_id: Identifier | None
    quantity: Quantity


class PurchaseSessionBody(StrictModel):
    action: Literal["shopping.record-session"]
    items: Annotated[
        list[SessionSelectionBody],
        Field(min_length=MIN_SESSION_ITEMS, max_length=MAX_SESSION_ITEMS),
    ]


class CancelPurchaseBalanceBody(StrictModel):
    action: Literal["shopping.cancel-balance"]
    purchase_id: Identifier
    reason: StockReason
    expected_revision: str = Field(pattern=r"^[1-9][0-9]{0,18}$")


class ReceiptCorrectionBody(StrictModel):
    purchase_id: Identifier
    receipt_id: Identifier
    reason: StockReason
    expected_revision: str = Field(pattern=r"^[1-9][0-9]{0,18}$")


class VoidReceiptBody(ReceiptCorrectionBody):
    action: Literal["shopping.void-receipt"]


class CorrectPostedReceiptBody(ReceiptCorrectionBody):
    action: Literal["shopping.correct-posted-receipt"]


CatalogBody = Annotated[
    ProductBody
    | IntakeBody
    | AdjustmentBody
    | IntakeCorrectionBody
    | ReplenishmentBody
    | PurchaseBody
    | ReceivePurchaseBody
    | PostReceiptBody
    | AddExtraBody
    | ClearExtraBody
    | PurchaseSessionBody
    | CancelPurchaseBalanceBody
    | VoidReceiptBody
    | CorrectPostedReceiptBody,
    Field(discriminator="action"),
]


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

    @router.get("/products/{product_id}/movements", response_model=MovementHistory)
    def history(
        request: Request, product_id: Identifier, query: Annotated[PageQuery, Query()]
    ) -> MovementHistory:
        return (
            context(request).inventory().history(product_id, limit=query.limit, cursor=query.cursor)
        )

    @router.get("/purchases", response_model=PurchasesView)
    def purchases(request: Request, query: Annotated[PageQuery, Query()]) -> PurchasesView:
        return context(request).inventory().purchases(limit=query.limit, cursor=query.cursor)

    @router.get("/purchase-sessions", response_model=PurchaseSessionsView)
    def purchase_sessions(
        request: Request, query: Annotated[PageQuery, Query()]
    ) -> PurchaseSessionsView:
        return (
            context(request).inventory().purchase_sessions(limit=query.limit, cursor=query.cursor)
        )

    @router.get("/purchase-sessions/{session_id}", response_model=PurchaseSessionDetail)
    def purchase_session(
        request: Request, session_id: Identifier, query: Annotated[_EmptyQuery, Query()]
    ) -> PurchaseSessionDetail:
        return context(request).inventory().purchase_session(session_id)

    @router.get("/purchases/{purchase_id}/receipts", response_model=PhysicalReceiptsView)
    def physical_receipts(
        request: Request, purchase_id: Identifier, query: Annotated[PageQuery, Query()]
    ) -> PhysicalReceiptsView:
        return (
            context(request)
            .inventory()
            .physical_receipts(purchase_id, limit=query.limit, cursor=query.cursor)
        )

    @router.get("/shopping-list", response_model=ShoppingListView)
    def shopping_list(request: Request, query: Annotated[PageQuery, Query()]) -> ShoppingListView:
        return context(request).inventory().shopping_list(limit=query.limit, cursor=query.cursor)

    @router.get("/shopping-list/{product_id}/sources", response_model=ShoppingSourcesView)
    def shopping_sources(
        request: Request, product_id: Identifier, query: Annotated[PageQuery, Query()]
    ) -> ShoppingSourcesView:
        return (
            context(request)
            .inventory()
            .shopping_sources(product_id, limit=query.limit, cursor=query.cursor)
        )

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
        elif isinstance(body, IntakeBody):
            receipt = inventory.intake(key, body.product_id, MaterialQuantity(body.quantity))
        elif isinstance(body, AdjustmentBody):
            receipt = inventory.adjust(key, body.product_id, body.quantity, body.reason)
        elif isinstance(body, IntakeCorrectionBody):
            receipt = inventory.correct_intake(key, body.product_id, body.movement_id, body.reason)
        elif isinstance(body, ReplenishmentBody):
            receipt = inventory.configure_replenishment(
                key,
                body.product_id,
                MaterialQuantity(body.minimum),
                MaterialQuantity(body.target),
                int(body.expected_revision),
            )
        elif isinstance(body, PurchaseBody):
            receipt = inventory.purchase(
                key, body.product_id, body.name, MaterialQuantity(body.quantity)
            )
        elif isinstance(body, ReceivePurchaseBody):
            receipt = inventory.receive_purchase(
                key, body.purchase_id, MaterialQuantity(body.quantity), int(body.expected_revision)
            )
        elif isinstance(body, AddExtraBody):
            receipt = inventory.add_extra(
                key, body.product_id, body.name, MaterialQuantity(body.quantity)
            )
        elif isinstance(body, ClearExtraBody):
            receipt = inventory.clear_extra(key, body.extra_id)
        elif isinstance(body, PurchaseSessionBody):
            receipt = inventory.record_purchase_session(
                key,
                tuple(
                    SessionSelection(
                        item.product_id, item.extra_id, MaterialQuantity(item.quantity)
                    )
                    for item in body.items
                ),
            )
        elif isinstance(body, CancelPurchaseBalanceBody):
            receipt = inventory.cancel_purchase_balance(
                key, body.purchase_id, body.reason, int(body.expected_revision)
            )
        elif isinstance(body, CorrectPostedReceiptBody):
            receipt = inventory.correct_posted_receipt(
                key, body.purchase_id, body.receipt_id, body.reason, int(body.expected_revision)
            )
        elif isinstance(body, VoidReceiptBody):
            receipt = inventory.void_purchase_receipt(
                key, body.purchase_id, body.receipt_id, body.reason, int(body.expected_revision)
            )
        else:
            receipt = inventory.post_purchase_receipt(key, body.purchase_id, body.receipt_id)
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
