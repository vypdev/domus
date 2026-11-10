"""Allocate exact Pantry supply to the household's automatic shopping needs."""

from dataclasses import dataclass, replace
from enum import StrEnum

from domus.domain.inventory import BaseUnit
from domus.domain.storage import JsonDocument


@dataclass(frozen=True, slots=True)
class ShoppingExtra:
    extra_id: str
    product_id: str | None
    name: str
    base_unit: BaseUnit
    quantity: int
    member_id: str
    created_at: int
    cleared_by: str | None = None
    cleared_at: int | None = None


class NeedKind(StrEnum):
    PANTRY = "pantry"
    TASK = "task"
    EXTRA = "extra"


@dataclass(frozen=True, slots=True)
class ShoppingNeed:
    kind: NeedKind
    origin_id: str
    name: str
    quantity: int
    line_id: str | None = None
    reserved: int = 0
    stock: int = 0
    incoming: int = 0

    @property
    def source_id(self) -> str:
        return JsonDocument.from_value(
            {"kind": self.kind.value, "origin": self.origin_id, "line": self.line_id}
        ).fingerprint

    @property
    def to_buy(self) -> int:
        return self.quantity - self.reserved - self.stock - self.incoming


def allocate_needs(
    automatic: tuple[ShoppingNeed, ...], available: int, incoming: int
) -> tuple[ShoppingNeed, ...]:
    """Pantry takes incoming first. Task lines take free stock in source order."""
    allocated = []
    for need in automatic:
        stock = min(available, need.to_buy) if need.kind is NeedKind.TASK else 0
        supplied = min(incoming, need.to_buy - stock)
        allocated.append(replace(need, stock=stock, incoming=supplied))
        available -= stock
        incoming -= supplied
    return tuple(allocated)
