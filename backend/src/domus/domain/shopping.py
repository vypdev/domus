"""Purchased, received and posted quantities are separate household facts."""

from dataclasses import dataclass, replace

from domus.domain.errors import Conflict, InvalidInput
from domus.domain.inventory import BaseUnit
from domus.domain.storage import JsonDocument
from domus.domain.task_material_values import MaterialQuantity
from domus.domain.task_values import validate_task_text

MIN_SESSION_ITEMS = 2
MAX_SESSION_ITEMS = 16
MAX_PURCHASE_STORE_NAME = 160


@dataclass(frozen=True, slots=True)
class SessionSelection:
    product_id: str | None
    extra_id: str | None
    quantity: MaterialQuantity


@dataclass(frozen=True, slots=True)
class PurchaseSession:
    session_id: str
    member_id: str
    created_at: int
    store_name: str | None = None

    def __post_init__(self) -> None:
        if self.store_name is not None:
            try:
                validate_task_text(self.store_name, MAX_PURCHASE_STORE_NAME, required=True)
            except InvalidInput:
                raise InvalidInput("invalid_shopping_store_name") from None


@dataclass(frozen=True, slots=True)
class Purchase:
    purchase_id: str
    product_id: str | None
    name: str
    base_unit: BaseUnit
    purchased: int
    received: int
    settled: int
    revision: int
    member_id: str
    created_at: int
    cancelled: int = 0

    @property
    def remaining(self) -> int:
        return self.purchased - self.received - self.cancelled

    @property
    def pending(self) -> int:
        return self.received - self.settled

    def receive(self, quantity: int, expected_revision: int) -> Purchase:
        if self.revision != expected_revision:
            raise Conflict("revision_conflict")
        if quantity > self.remaining:
            raise Conflict("shopping_receipt_exceeds_purchase")
        return replace(
            self,
            received=self.received + quantity,
            settled=self.settled + quantity if self.product_id is None else self.settled,
            revision=self.revision + 1,
        )

    def cancel_balance(self, expected_revision: int) -> Purchase:
        if self.revision != expected_revision:
            raise Conflict("revision_conflict")
        if not self.remaining:
            raise Conflict("shopping_balance_closed")
        return replace(self, cancelled=self.remaining, revision=self.revision + 1)

    def void_receipt(self, quantity: int, expected_revision: int) -> Purchase:
        if self.revision != expected_revision:
            raise Conflict("revision_conflict")
        if self.cancelled:
            raise Conflict("shopping_receipt_balance_cancelled")
        return replace(self, received=self.received - quantity, revision=self.revision + 1)

    def correct_posted_receipt(self, quantity: int, expected_revision: int) -> Purchase:
        reopened = self.void_receipt(quantity, expected_revision)
        return replace(reopened, settled=self.settled - quantity)

    def return_receipt(self, expected_revision: int) -> Purchase:
        if self.revision != expected_revision:
            raise Conflict("revision_conflict")
        if self.cancelled or self.settled != self.purchased:
            raise Conflict("shopping_purchase_not_settled")
        return replace(self, revision=self.revision + 1)

    def post(self, quantity: int) -> Purchase:
        return replace(self, settled=self.settled + quantity, revision=self.revision + 1)


@dataclass(frozen=True, slots=True)
class PurchaseCancellation:
    purchase_id: str
    quantity: int
    reason: str
    member_id: str
    created_at: int


@dataclass(frozen=True, slots=True)
class PurchaseReceiptVoid:
    receipt_id: str
    reason: str
    member_id: str
    created_at: int


@dataclass(frozen=True, slots=True)
class PurchaseReceipt:
    receipt_id: str
    purchase_id: str
    quantity: int
    member_id: str
    created_at: int
    movement_id: str | None

    @property
    def stock_source(self) -> str:
        return JsonDocument.from_value({"shopping_receipt": self.receipt_id}).fingerprint

    @property
    def return_source(self) -> str:
        return JsonDocument.from_value({"shopping_return": self.receipt_id}).fingerprint
