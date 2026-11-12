"""Present both native deadline sensors from one coordinated snapshot."""

from typing import Literal

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DeadlineEntry

DeadlineGroup = Literal["due_today", "overdue"]


async def async_setup_entry(
    _hass: HomeAssistant, entry: DeadlineEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities(
        [DomusDeadlineSensor(entry, "due_today"), DomusDeadlineSensor(entry, "overdue")]
    )


class DomusDeadlineSensor(CoordinatorEntity, SensorEntity):
    """One count from the latest available Domus deadline snapshot."""

    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, entry: DeadlineEntry, group: DeadlineGroup) -> None:
        super().__init__(entry.runtime_data)
        self._group = group
        self._attr_translation_key = f"tasks_{group}"
        self._attr_unique_id = f"{entry.unique_id}.{group}"

    @property
    def native_value(self) -> int:
        return getattr(self.coordinator.data, self._group)
