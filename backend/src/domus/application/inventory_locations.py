"""Read and check directly bound location effects inside the caller's transaction."""

from domus.application.inventory_ports import InventoryRecords
from domus.application.ports import UnitOfWork
from domus.domain.errors import Conflict
from domus.domain.inventory import LocationArchiveBlock, StorageLocation
from domus.domain.storage import JsonDocument


def location_is_archived(stock: InventoryRecords, home: str, location_id: str) -> bool:
    # Pantry and pre-catalog external bindings have no named location record.
    location = stock.location(home, location_id)
    return location is not None and location.archived


def require_active_location(stock: InventoryRecords, home: str, location_id: str) -> None:
    if location_is_archived(stock, home, location_id):
        raise Conflict("inventory_location_archived")


def location_archive_block(
    unit: UnitOfWork, home: str, location_id: str
) -> LocationArchiveBlock | None:
    usage = unit.inventory.location_usage(home, location_id)
    if usage.recorded_stock:
        return LocationArchiveBlock.RECORDED_STOCK
    if usage.pending_effects or unit.task_materials.has_pending_location(home, location_id):
        return LocationArchiveBlock.PENDING_EFFECTS
    return None


def location_result(value: StorageLocation) -> JsonDocument:
    return JsonDocument.from_value(
        {
            "location_id": value.location_id,
            "name": value.name,
            "revision": str(value.revision),
            "archived": value.archived,
        }
    )
