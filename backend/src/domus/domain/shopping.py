"""Purchased, received and posted quantities are separate household facts."""

from dataclasses import dataclass, replace

from domus.domain.errors import Conflict
from domus.domain.inventory import BaseUnit
from domus.domain.storage import JsonDocument


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

    @property
    def remaining(self) -> int:
        return self.purchased - self.received

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

    def post(self, quantity: int) -> Purchase:
        return replace(self, settled=self.settled + quantity, revision=self.revision + 1)


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
