"""Exact stock movements and stable task-linked Inventory effects."""

from dataclasses import dataclass
from enum import StrEnum

from domus.domain.task_material_values import MaterialQuantity
from domus.domain.task_materials import MaterialPosting

MAX_STOCK_UNITS = 10**18 - 1


def stock_units(quantity: MaterialQuantity) -> int:
    whole, _, fraction = quantity.value.partition(".")
    return int(whole) * 1_000_000 + int(fraction.ljust(6, "0"))


class EffectKind(StrEnum):
    RESERVATION = "reservation"
    DEMAND = "demand"


@dataclass(frozen=True, slots=True)
class InventoryEffect:
    household_id: str
    effect_id: str
    kind: EffectKind
    reference_id: str
    origin_id: str | None
    occurrence_id: str | None
    line_id: str | None
    remaining: int
    revision: int = 1


@dataclass(frozen=True, slots=True)
class StockMovement:
    household_id: str
    reference_id: str
    movement_id: str
    source_key: str
    member_id: str
    delta: int
    created_at: int
    reason: str
    posting: MaterialPosting | None = None
    corrects: str | None = None
