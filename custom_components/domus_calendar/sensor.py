"""Present the aggregate sensors from their coordinated snapshots."""

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import CONF_PROJECTION, CountEntry
from .count_client import STOCK


async def async_setup_entry(
    _hass: HomeAssistant, entry: CountEntry, async_add_entities: AddEntitiesCallback
) -> None:
    if entry.data[CONF_PROJECTION] == STOCK:
        async_add_entities(
            [
                DomusCountSensor(
                    entry, "low_stock_products", "low_stock_products", "domus_low_stock_products"
                )
            ]
        )
    else:
        async_add_entities(
            [
                DomusCountSensor(entry, "due_today", "tasks_due_today"),
                DomusCountSensor(entry, "overdue", "tasks_overdue"),
            ]
        )


class DomusCountSensor(CoordinatorEntity, SensorEntity):
    """One count from the latest available Domus snapshot."""

    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self, entry: CountEntry, field: str, translation_key: str, suggested_id: str | None = None
    ) -> None:
        super().__init__(entry.runtime_data)
        self._field = field
        self._attr_translation_key = translation_key
        self._attr_unique_id = f"{entry.unique_id}.{field}"
        if suggested_id is not None:
            self._attr_suggested_object_id = suggested_id

    @property
    def native_value(self) -> int:
        return self.coordinator.data[self._field]
