"""Exact stock movements and stable task-linked Inventory effects."""

from dataclasses import dataclass
from enum import StrEnum

from domus.domain.errors import InvalidInput
from domus.domain.storage import validate_identifier
from domus.domain.task_material_values import MaterialBinding, MaterialQuantity
from domus.domain.task_materials import MaterialPosting
from domus.domain.task_values import validate_task_text

MAX_STOCK_UNITS = 10**18 - 1
PANTRY = "pantry"
MAX_STOCK_REASON = 240


class BaseUnit(StrEnum):
    PIECE = "piece"
    GRAM = "gram"
    MILLILITRE = "millilitre"

    @property
    def precision(self) -> int:
        return 0 if self is BaseUnit.PIECE else 6


@dataclass(frozen=True, slots=True)
class CatalogProduct:
    product_id: str
    reference_id: str
    name: str
    base_unit: BaseUnit

    def __post_init__(self) -> None:
        validate_identifier(self.product_id)
        validate_identifier(self.reference_id)
        validate_task_text(self.name, 160, required=True)
        if not isinstance(self.base_unit, BaseUnit):
            raise InvalidInput("invalid_inventory_unit")

    def binding(self, home: str) -> MaterialBinding:
        return MaterialBinding(
            home,
            self.reference_id,
            self.product_id,
            self.base_unit.value,
            PANTRY,
            1,
            self.base_unit.precision,
            self.name,
        )


def stock_quantity(units: int) -> str:
    sign = "-" if units < 0 else ""
    whole, fraction = divmod(abs(units), 1_000_000)
    magnitude = f"{whole}.{fraction:06}".rstrip("0") if fraction else str(whole)
    return sign + magnitude


def stock_units(quantity: MaterialQuantity) -> int:
    whole, _, fraction = quantity.value.partition(".")
    return int(whole) * 1_000_000 + int(fraction.ljust(6, "0"))


def validate_stock_reason(reason: str) -> None:
    try:
        validate_task_text(reason, MAX_STOCK_REASON, required=True)
    except InvalidInput:
        raise InvalidInput("invalid_inventory_reason") from None


class MovementKind(StrEnum):
    INTAKE = "intake"
    TASK_CONSUMPTION = "task_consumption"
    TASK_CORRECTION = "task_correction"
    ADJUSTMENT = "adjustment"
    INTAKE_CORRECTION = "intake_correction"


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
    kind: MovementKind
    posting: MaterialPosting | None = None
    corrects: str | None = None
