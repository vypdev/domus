"""Material orchestration preserves work and delegates every real stock effect to Inventory."""

from dataclasses import dataclass
from typing import cast

from domus.application.ports import Clock, Identifiers
from domus.application.task_material_ports import (
    InventoryMaterialResult,
    MaterialPostingRequest,
    TaskInventory,
    TaskMaterialAuthority,
)
from domus.domain.errors import (
    Conflict,
    Forbidden,
    IntegrationUnavailable,
    InvalidInput,
    StorageFailure,
)
from domus.domain.storage import validate_identifier
from domus.domain.task_material_values import (
    MaterialAction,
    MaterialBinding,
    MaterialLine,
    MaterialPendingReason,
    MaterialQuantity,
    MaterialSelection,
    validate_material_lines,
    validate_material_selections,
)
from domus.domain.task_materials import MaterialIntent, MaterialPosting
from domus.domain.task_values import MaterialRecording


def _actor(value: str) -> str:
    try:
        validate_identifier(value)
    except InvalidInput:
        raise StorageFailure("invalid_material_authority") from None
    return value


@dataclass
class TaskMaterials:
    """Caller owns transaction/receipt/CAS. These helpers neither commit nor confer authority."""

    inventory: TaskInventory
    authority: TaskMaterialAuthority
    clock: Clock
    identifiers: Identifiers

    def link(
        self,
        household_id: str,
        selections: tuple[MaterialSelection, ...],
        previous: tuple[MaterialLine, ...] = (),
    ) -> tuple[MaterialLine, ...]:
        validate_identifier(household_id)
        validate_material_selections(selections)
        validate_material_lines(previous, household_id)
        actor = _actor(self.authority.link_actor(household_id))
        resolved = []
        for selection in selections:
            binding = self.inventory.resolve(household_id, actor, selection.reference_id)
            if binding is None:
                raise InvalidInput("invalid_material_reference")
            if (
                not isinstance(binding, MaterialBinding)
                or binding.household_id != household_id
                or binding.reference_id != selection.reference_id
            ):
                raise StorageFailure("invalid_material_binding")
            binding.require_quantity(selection.planned_quantity)
            resolved.append((selection, binding))
        old = {value.binding.reference_id: value for value in previous}
        result = []
        try:
            for selection, binding in resolved:
                prior = old.get(binding.reference_id)
                identity = (
                    prior.line_id
                    if prior is not None and prior.binding.target == binding.target
                    else self.identifiers.new()
                )
                result.append(MaterialLine(identity, binding, selection.planned_quantity))
            values = tuple(result)
            validate_material_lines(values, household_id)
        except InvalidInput:
            raise StorageFailure("invalid_material_identity") from None
        return values

    def record_completion(self, intent: MaterialIntent) -> MaterialIntent:
        # Called only for the newly recorded cycle in its one explicit completion
        # submission, never by a grant/approval/stock/reopen event or a replay worker.
        if intent.recording_mode is MaterialRecording.SEPARATE or not intent.needs_posting:
            return intent
        try:
            actor = _actor(self.authority.require(intent, MaterialAction.POST))
        except Forbidden:
            return intent.defer(MaterialPendingReason.PERMISSION_REQUIRED, self.clock.now())
        return self._post(intent, actor)

    def post(self, intent: MaterialIntent) -> MaterialIntent:
        actor = _actor(self.authority.require(intent, MaterialAction.POST))
        return self._post(intent, actor)

    def correct(
        self, intent: MaterialIntent, quantity: MaterialQuantity, reason: str
    ) -> MaterialIntent:
        actor = _actor(self.authority.require(intent, MaterialAction.CORRECT))
        updated = intent.correct(quantity, reason, self.clock.now())
        return self._post(updated, actor) if updated.needs_posting else updated

    def dismiss(self, intent: MaterialIntent, reason: str) -> MaterialIntent:
        _actor(self.authority.require(intent, MaterialAction.DISMISS))
        return intent.dismiss(reason, self.clock.now())

    def _post(self, intent: MaterialIntent, actor: str) -> MaterialIntent:
        intent.require_posting(self.clock.now())
        try:
            result = self.inventory.settle(MaterialPostingRequest(intent, actor))
        except IntegrationUnavailable:
            return intent.defer(MaterialPendingReason.INVENTORY_UNAVAILABLE, self.clock.now())
        if not isinstance(result, InventoryMaterialResult):
            raise StorageFailure("invalid_material_consumer_result")
        if result.pending_reason is not None:
            return intent.defer(result.pending_reason, self.clock.now())
        try:
            return intent.confirm(cast(MaterialPosting, result.posting), self.clock.now())
        except InvalidInput, Conflict:
            raise StorageFailure("invalid_material_confirmation") from None
