"""Transaction-local material semantics; pending results certify no new Inventory movement."""

from dataclasses import dataclass
from typing import Protocol, cast

from domus.domain.errors import InvalidInput
from domus.domain.storage import JsonDocument, validate_identifier
from domus.domain.task_material_values import (
    MaterialAction,
    MaterialBinding,
    MaterialPendingReason,
    MaterialQuantity,
)
from domus.domain.task_materials import MaterialIntent, MaterialPosting


@dataclass(frozen=True, slots=True)
class MaterialPostingRequest:
    intent: MaterialIntent
    actor_member_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.intent, MaterialIntent) or not self.intent.needs_posting:
            raise InvalidInput("invalid_material_request")
        validate_identifier(self.actor_member_id)

    @property
    def source_key(self) -> str:
        """One requested effect survives operator, pending metadata and retry changes."""
        value = self.intent
        return (
            "task-material:"
            + JsonDocument.from_value(
                {
                    "version": 1,
                    "household": value.household_id,
                    "occurrence": value.occurrence_id,
                    "cycle": value.cycle_id,
                    "intent": value.intent_id,
                    "line": value.line.line_id,
                    "reference": value.line.binding.reference_id,
                    "product": value.line.binding.product_id,
                    "unit": value.line.binding.unit_id,
                    "location": value.line.binding.location_id,
                    "binding_revision": value.line.binding.revision,
                    "effect_revision": value.effect_revision,
                    "quantity": cast(MaterialQuantity, value.quantity).value,
                }
            ).fingerprint
        )


@dataclass(frozen=True, slots=True)
class InventoryMaterialResult:
    posting: MaterialPosting | None = None
    pending_reason: MaterialPendingReason | None = None

    def __post_init__(self) -> None:
        if (
            (self.posting is None) == (self.pending_reason is None)
            or (self.posting is not None and not isinstance(self.posting, MaterialPosting))
            or (
                self.pending_reason is not None
                and (
                    not isinstance(self.pending_reason, MaterialPendingReason)
                    or self.pending_reason
                    in (
                        MaterialPendingReason.ACTUAL_QUANTITY_REQUIRED,
                        MaterialPendingReason.EXPLICIT_SETTLEMENT_REQUIRED,
                    )
                )
            )
        ):
            raise InvalidInput("invalid_material_consumer_result")


class TaskInventory(Protocol):
    """Bind to the caller's local unit: no network I/O or independent commit under its writer.

    Pending is not completed movement deduplication. Explicit later retries may attempt
    the same source effect key; actual successful movements must remain duplicate-safe.
    """

    def resolve(
        self, household_id: str, actor_member_id: str, reference_id: str
    ) -> MaterialBinding | None: ...
    def settle(self, request: MaterialPostingRequest) -> InventoryMaterialResult: ...


class TaskMaterialAuthority(Protocol):
    """Reread current authority in the caller transaction; return a local member ID."""

    def link_actor(self, household_id: str) -> str: ...
    def require(self, intent: MaterialIntent, action: MaterialAction) -> str: ...


class TaskMaterialRepository(Protocol):
    def get(self, household_id: str, intent_id: str) -> MaterialIntent | None: ...
    def list(
        self, household_id: str, cycle_id: str, *, limit: int = 25, after: str | None = None
    ) -> tuple[MaterialIntent, ...]: ...
    def save(self, value: MaterialIntent, expected_revision: int) -> None: ...
