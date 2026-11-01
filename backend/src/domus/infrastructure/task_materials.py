"""Explicit absence adapter: no catalog knowledge, stock writes or fabricated confirmations."""

from domus.application.task_material_ports import InventoryMaterialResult, MaterialPostingRequest
from domus.domain.errors import IntegrationUnavailable
from domus.domain.task_material_values import MaterialBinding, MaterialPendingReason


class UnavailableTaskInventory:
    def resolve(
        self, household_id: str, actor_member_id: str, reference_id: str
    ) -> MaterialBinding | None:
        raise IntegrationUnavailable("inventory_unavailable")

    def settle(self, request: MaterialPostingRequest) -> InventoryMaterialResult:
        return InventoryMaterialResult(pending_reason=MaterialPendingReason.INVENTORY_UNAVAILABLE)
