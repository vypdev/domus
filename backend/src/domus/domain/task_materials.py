"""Cycle-bound material facts retain desired amounts separately from confirmed Inventory effects."""

from dataclasses import dataclass, replace
from typing import Self

from domus.domain.errors import Conflict, InvalidInput
from domus.domain.identity import validate_revision
from domus.domain.storage import validate_identifier
from domus.domain.task_material_values import (
    MaterialLine,
    MaterialPendingReason,
    MaterialQuantity,
    MaterialState,
)
from domus.domain.task_values import (
    MaterialRecording,
    next_task_revision,
    validate_task_text,
    validate_task_time,
)

_PENDING = {
    MaterialPendingReason.ACTUAL_QUANTITY_REQUIRED: MaterialState.PENDING_RECORDING,
    MaterialPendingReason.PERMISSION_REQUIRED: MaterialState.PENDING_AUTHORIZATION,
    MaterialPendingReason.STOCK_SHORTAGE: MaterialState.PENDING_REGULARIZATION,
    MaterialPendingReason.BINDING_CHANGED: MaterialState.PENDING_REGULARIZATION,
    MaterialPendingReason.EXPLICIT_SETTLEMENT_REQUIRED: MaterialState.PENDING_PROCESSING,
    MaterialPendingReason.AWAITING_INVENTORY: MaterialState.PENDING_PROCESSING,
    MaterialPendingReason.INVENTORY_UNAVAILABLE: MaterialState.PENDING_PROCESSING,
}


@dataclass(frozen=True, slots=True)
class MaterialPosting:
    """An actual Inventory confirmation of total usage; Tasks never compute its stock delta."""

    intent_id: str
    household_id: str
    occurrence_id: str
    cycle_id: str
    line_id: str
    reference_id: str
    binding_revision: int
    intent_revision: int
    effect_revision: int
    quantity: MaterialQuantity
    inventory_operation_id: str
    movement_id: str
    posted_at: int

    def __post_init__(self) -> None:
        for value in (
            self.intent_id,
            self.household_id,
            self.occurrence_id,
            self.cycle_id,
            self.line_id,
            self.reference_id,
            self.inventory_operation_id,
            self.movement_id,
        ):
            validate_identifier(value)
        for revision in (self.binding_revision, self.intent_revision, self.effect_revision):
            validate_revision(revision)
        if not isinstance(self.quantity, MaterialQuantity):
            raise InvalidInput("invalid_material_quantity")
        validate_task_time(self.posted_at)


@dataclass(frozen=True, slots=True)
class MaterialIntent:
    intent_id: str
    household_id: str
    occurrence_id: str
    cycle_id: str
    line: MaterialLine
    submitted_quantity: MaterialQuantity | None
    quantity: MaterialQuantity | None
    recorded_by: str
    performed_at: int
    created_at: int
    updated_at: int
    recording_mode: MaterialRecording
    authorized_at_recording: bool
    state: MaterialState
    pending_reason: MaterialPendingReason | None = None
    reason: str = ""
    posting: MaterialPosting | None = None
    effect_revision: int = 1
    revision: int = 1

    def __post_init__(self) -> None:
        for value in (
            self.intent_id,
            self.household_id,
            self.occurrence_id,
            self.cycle_id,
            self.recorded_by,
        ):
            validate_identifier(value)
        for revision in (self.revision, self.effect_revision):
            validate_revision(revision)
        for timestamp in (self.performed_at, self.created_at, self.updated_at):
            validate_task_time(timestamp)
        if (
            not isinstance(self.line, MaterialLine)
            or self.line.binding.household_id != self.household_id
            or not isinstance(self.recording_mode, MaterialRecording)
            or type(self.authorized_at_recording) is not bool
            or not isinstance(self.state, MaterialState)
            or self.effect_revision > self.revision
            or not self.performed_at <= self.created_at <= self.updated_at
            or (self.effect_revision == 1 and self.quantity != self.submitted_quantity)
            or (self.effect_revision > 1 and self.quantity is None)
        ):
            raise InvalidInput("invalid_material_intent")
        for quantity in (self.submitted_quantity, self.quantity):
            if quantity is not None:
                self.line.binding.require_quantity(quantity)
        validate_task_text(
            self.reason,
            1000,
            required=self.effect_revision > 1 or self.state is MaterialState.DISMISSED,
            multiline=True,
        )
        if self.effect_revision == 1 and self.state is not MaterialState.DISMISSED and self.reason:
            raise InvalidInput("invalid_material_intent")
        if self.posting is not None:
            if (
                not isinstance(self.posting, MaterialPosting)
                or not self._scope(self.posting)
                or self.posting.effect_revision > self.effect_revision
                or self.posting.intent_revision >= self.revision
                or not self.created_at <= self.posting.posted_at <= self.updated_at
            ):
                raise InvalidInput("invalid_material_intent")
            self.line.binding.require_quantity(self.posting.quantity)
        self._state()

    def _scope(self, posting: MaterialPosting) -> bool:
        return (
            posting.intent_id,
            posting.household_id,
            posting.occurrence_id,
            posting.cycle_id,
            posting.line_id,
            posting.reference_id,
            posting.binding_revision,
        ) == (
            self.intent_id,
            self.household_id,
            self.occurrence_id,
            self.cycle_id,
            self.line.line_id,
            self.line.binding.reference_id,
            self.line.binding.revision,
        )

    def _state(self) -> None:
        if self.state in _PENDING.values():
            if (
                not isinstance(self.pending_reason, MaterialPendingReason)
                or _PENDING[self.pending_reason] is not self.state
            ):
                raise InvalidInput("invalid_material_intent")
            if self.state is MaterialState.PENDING_RECORDING:
                if self.quantity is not None or self.posting is not None:
                    raise InvalidInput("invalid_material_intent")
            elif (
                self.quantity is None
                or (self.quantity.is_zero and self.posting is None)
                or (self.posting is not None and self.posting.quantity == self.quantity)
            ):
                raise InvalidInput("invalid_material_intent")
        elif self.pending_reason is not None:
            raise InvalidInput("invalid_material_intent")
        elif self.state is MaterialState.NOT_USED:
            if self.quantity is None or not self.quantity.is_zero or self.posting is not None:
                raise InvalidInput("invalid_material_intent")
        elif self.state in (MaterialState.POSTED, MaterialState.CORRECTED):
            expected = (
                MaterialState.POSTED if self.effect_revision == 1 else MaterialState.CORRECTED
            )
            if (
                self.posting is None
                or self.posting.quantity != self.quantity
                or self.state is not expected
            ):
                raise InvalidInput("invalid_material_intent")
        elif self.posting is not None:
            # Dismissal never claims to erase an actual Inventory effect.
            raise InvalidInput("invalid_material_intent")

    @classmethod
    def record(
        cls,
        intent_id: str,
        household_id: str,
        occurrence_id: str,
        cycle_id: str,
        line: MaterialLine,
        quantity: MaterialQuantity | None,
        *,
        recorded_by: str,
        performed_at: int,
        recorded_at: int,
        recording_mode: MaterialRecording,
        authorized: bool,
    ) -> Self:
        if quantity is not None and not isinstance(quantity, MaterialQuantity):
            raise InvalidInput("invalid_material_quantity")
        if quantity is None:
            state, pending = (
                MaterialState.PENDING_RECORDING,
                MaterialPendingReason.ACTUAL_QUANTITY_REQUIRED,
            )
        elif quantity.is_zero:
            state, pending = MaterialState.NOT_USED, None
        elif not authorized:
            state, pending = (
                MaterialState.PENDING_AUTHORIZATION,
                MaterialPendingReason.PERMISSION_REQUIRED,
            )
        else:
            state = MaterialState.PENDING_PROCESSING
            pending = (
                MaterialPendingReason.EXPLICIT_SETTLEMENT_REQUIRED
                if recording_mode is MaterialRecording.SEPARATE
                else MaterialPendingReason.AWAITING_INVENTORY
            )
        return cls(
            intent_id,
            household_id,
            occurrence_id,
            cycle_id,
            line,
            quantity,
            quantity,
            recorded_by,
            performed_at,
            recorded_at,
            recorded_at,
            recording_mode,
            authorized,
            state,
            pending,
        )

    @property
    def needs_posting(self) -> bool:
        return self.state in (
            MaterialState.PENDING_AUTHORIZATION,
            MaterialState.PENDING_REGULARIZATION,
            MaterialState.PENDING_PROCESSING,
        )

    def _time(self, now: int) -> None:
        validate_task_time(now)
        if now < self.updated_at:
            raise InvalidInput("invalid_material_time")

    def require_posting(self, now: int) -> None:
        self._time(now)
        if not self.needs_posting:
            raise Conflict(
                "material_actual_quantity_required"
                if self.quantity is None
                else "material_already_settled"
            )
        next_task_revision(self.revision)

    def defer(self, reason: MaterialPendingReason, now: int) -> Self:
        self._time(now)
        if (
            not isinstance(reason, MaterialPendingReason)
            or reason is MaterialPendingReason.ACTUAL_QUANTITY_REQUIRED
        ):
            raise InvalidInput("invalid_material_pending_reason")
        if not self.needs_posting:
            raise Conflict("material_already_settled")
        if reason is self.pending_reason:
            return self
        return replace(
            self,
            state=_PENDING[reason],
            pending_reason=reason,
            revision=next_task_revision(self.revision),
            updated_at=now,
        )

    def correct(self, quantity: MaterialQuantity, reason: str, now: int) -> Self:
        self._time(now)
        self.line.binding.require_quantity(quantity)
        validate_task_text(reason, 1000, required=True, multiline=True)
        if self.state is MaterialState.DISMISSED:
            raise Conflict("material_already_settled")
        if quantity == self.quantity:
            raise Conflict("material_unchanged")
        state = MaterialState.PENDING_PROCESSING
        pending: MaterialPendingReason | None = MaterialPendingReason.AWAITING_INVENTORY
        if self.posting is None and quantity.is_zero:
            state, pending = MaterialState.NOT_USED, None
        elif self.posting is not None and self.posting.quantity == quantity:
            state, pending = MaterialState.CORRECTED, None
        return replace(
            self,
            quantity=quantity,
            reason=reason,
            state=state,
            pending_reason=pending,
            revision=next_task_revision(self.revision),
            effect_revision=next_task_revision(self.effect_revision),
            updated_at=now,
        )

    def dismiss(self, reason: str, now: int) -> Self:
        self._time(now)
        validate_task_text(reason, 1000, required=True, multiline=True)
        if self.posting is not None or self.state in (
            MaterialState.NOT_USED,
            MaterialState.DISMISSED,
        ):
            raise Conflict("material_already_settled")
        return replace(
            self,
            state=MaterialState.DISMISSED,
            pending_reason=None,
            reason=reason,
            revision=next_task_revision(self.revision),
            updated_at=now,
        )

    def confirm(self, posting: MaterialPosting, now: int) -> Self:
        self._time(now)
        if not isinstance(posting, MaterialPosting) or not self._scope(posting):
            raise InvalidInput("invalid_material_confirmation")
        if self.posting == posting and self.state in (
            MaterialState.POSTED,
            MaterialState.CORRECTED,
        ):
            return self
        if not self.needs_posting:
            raise Conflict("material_already_settled")
        if (
            posting.quantity != self.quantity
            or posting.effect_revision != self.effect_revision
            or posting.intent_revision > self.revision
        ):
            raise Conflict("material_effect_conflict")
        if not self.created_at <= posting.posted_at <= now:
            raise InvalidInput("invalid_material_time")
        if self.posting is not None and (
            posting.movement_id == self.posting.movement_id
            or posting.inventory_operation_id == self.posting.inventory_operation_id
        ):
            raise InvalidInput("invalid_material_confirmation")
        return replace(
            self,
            state=MaterialState.POSTED if self.effect_revision == 1 else MaterialState.CORRECTED,
            pending_reason=None,
            posting=posting,
            revision=next_task_revision(self.revision),
            updated_at=now,
        )
