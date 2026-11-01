"""Canonical material amounts and immutable Inventory binding facts, without stock arithmetic."""

import re
from dataclasses import dataclass
from enum import StrEnum

from domus.domain.errors import InvalidInput
from domus.domain.identity import validate_revision
from domus.domain.storage import validate_identifier
from domus.domain.task_values import validate_task_text


class MaterialState(StrEnum):
    PENDING_RECORDING = "pending_recording"
    PENDING_AUTHORIZATION = "pending_authorization"
    PENDING_REGULARIZATION = "pending_regularization"
    PENDING_PROCESSING = "pending_processing"
    NOT_USED = "not_used"
    POSTED = "posted"
    CORRECTED = "corrected"
    DISMISSED = "dismissed"


class MaterialPendingReason(StrEnum):
    ACTUAL_QUANTITY_REQUIRED = "actual_quantity_required"
    PERMISSION_REQUIRED = "material_permission_required"
    EXPLICIT_SETTLEMENT_REQUIRED = "explicit_settlement_required"
    AWAITING_INVENTORY = "awaiting_inventory_confirmation"
    INVENTORY_UNAVAILABLE = "inventory_unavailable"
    STOCK_SHORTAGE = "insufficient_stock"
    BINDING_CHANGED = "inventory_binding_changed"


class MaterialAction(StrEnum):
    POST = "post"
    CORRECT = "correct"
    DISMISS = "dismiss"


@dataclass(frozen=True, slots=True)
class MaterialQuantity:
    value: str

    def __post_init__(self) -> None:
        if type(self.value) is not str or not re.fullmatch(
            r"(?:0|[1-9][0-9]{0,11})(?:\.[0-9]{0,5}[1-9])?", self.value
        ):
            raise InvalidInput("invalid_material_quantity")

    @property
    def precision(self) -> int:
        return len(self.value.partition(".")[2])

    @property
    def is_zero(self) -> bool:
        return self.value == "0"


@dataclass(frozen=True, slots=True)
class MaterialBinding:
    """A semantic port must resolve existence and authority; construction proves neither."""

    household_id: str
    reference_id: str
    product_id: str
    unit_id: str
    location_id: str
    revision: int
    precision: int
    label: str = ""

    def __post_init__(self) -> None:
        for value in self.target:
            validate_identifier(value)
        validate_revision(self.revision)
        if type(self.precision) is not int or not 0 <= self.precision <= 6:
            raise InvalidInput("invalid_material_precision")
        validate_task_text(self.label, 160, required=False)

    @property
    def target(self) -> tuple[str, str, str, str, str]:
        return self.household_id, self.reference_id, self.product_id, self.unit_id, self.location_id

    def require_quantity(self, quantity: MaterialQuantity) -> None:
        if not isinstance(quantity, MaterialQuantity):
            raise InvalidInput("invalid_material_quantity")
        if quantity.precision > self.precision:
            raise InvalidInput("invalid_material_precision")


@dataclass(frozen=True, slots=True)
class MaterialLine:
    line_id: str
    binding: MaterialBinding
    planned_quantity: MaterialQuantity

    def __post_init__(self) -> None:
        validate_identifier(self.line_id)
        if not isinstance(self.binding, MaterialBinding):
            raise InvalidInput("invalid_material_binding")
        self.binding.require_quantity(self.planned_quantity)


@dataclass(frozen=True, slots=True)
class MaterialSelection:
    reference_id: str
    planned_quantity: MaterialQuantity

    def __post_init__(self) -> None:
        validate_identifier(self.reference_id)
        if not isinstance(self.planned_quantity, MaterialQuantity):
            raise InvalidInput("invalid_material_quantity")


@dataclass(frozen=True, slots=True)
class MaterialUsage:
    line_id: str
    quantity: MaterialQuantity

    def __post_init__(self) -> None:
        validate_identifier(self.line_id)
        if not isinstance(self.quantity, MaterialQuantity):
            raise InvalidInput("invalid_material_quantity")


def _bounded[T](values: tuple[T, ...], kind: type[T], identity: str) -> None:
    if (
        type(values) is not tuple
        or len(values) > 32
        or any(not isinstance(item, kind) for item in values)
    ):
        raise InvalidInput("invalid_material_list")
    if len({getattr(item, identity) for item in values}) != len(values):
        raise InvalidInput("invalid_material_list")


def validate_material_lines(values: tuple[MaterialLine, ...], household_id: str) -> None:
    validate_identifier(household_id)
    _bounded(values, MaterialLine, "line_id")
    if len({value.binding.reference_id for value in values}) != len(values):
        raise InvalidInput("invalid_material_list")
    if any(value.binding.household_id != household_id for value in values):
        raise InvalidInput("invalid_material_scope")


def validate_material_selections(values: tuple[MaterialSelection, ...]) -> None:
    _bounded(values, MaterialSelection, "reference_id")


def validate_material_usage_values(values: tuple[MaterialUsage, ...]) -> None:
    _bounded(values, MaterialUsage, "line_id")


def validate_material_usages(
    values: tuple[MaterialUsage, ...], lines: tuple[MaterialLine, ...]
) -> None:
    validate_material_usage_values(values)
    _bounded(lines, MaterialLine, "line_id")
    if len({line.binding.household_id for line in lines}) > 1:
        raise InvalidInput("invalid_material_scope")
    known = {line.line_id: line for line in lines}
    for value in values:
        line = known.get(value.line_id)
        if line is None:
            raise InvalidInput("invalid_material_reference")
        line.binding.require_quantity(value.quantity)
