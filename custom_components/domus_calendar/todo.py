"""Present complete authorized shopping and open-task snapshots as read-only lists."""

from typing import cast

from homeassistant.components.todo import TodoItem, TodoItemStatus, TodoListEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import CONF_PROJECTION, ShoppingEntry, TasksEntry
from .shopping_client import ShoppingItem
from .task_client import TASKS

_SYMBOLS = {"gram": "g", "millilitre": "mL"}
_ENGLISH_STATES = {
    "draft": "Draft",
    "available": "Available",
    "assigned": "Assigned",
    "in_progress": "In progress",
    "blocked": "Blocked",
}
_SPANISH_STATES = {
    "draft": "Borrador",
    "available": "Disponible",
    "assigned": "Asignada",
    "in_progress": "En curso",
    "blocked": "Bloqueada",
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    if entry.data.get(CONF_PROJECTION) == TASKS:
        async_add_entities([DomusTaskList(cast(TasksEntry, entry), hass.config.language)])
    else:
        async_add_entities([DomusShoppingList(cast(ShoppingEntry, entry), hass.config.language)])


def _summary(item: ShoppingItem, spanish: bool) -> str:
    amount = item.quantity.replace(".", ",") if spanish else item.quantity
    if item.unit == "piece":
        quantity = f"×{amount}"
    else:
        quantity = f"{amount} {_SYMBOLS[item.unit]}"
    return f"{item.name} · {quantity}"


class DomusShoppingList(CoordinatorEntity, TodoListEntity):
    """The outstanding lines from the opted-in Domus shared list."""

    _attr_has_entity_name = True
    _attr_translation_key = "shopping_list"

    def __init__(self, entry: ShoppingEntry, language: str) -> None:
        super().__init__(entry.runtime_data)
        self._attr_unique_id = entry.unique_id
        self.entity_id = "todo.domus_shopping"
        self._spanish = language.split("-", 1)[0].lower() == "es"

    @property
    def todo_items(self) -> list[TodoItem] | None:
        if not self.available:
            return None
        return [
            TodoItem(
                uid=item.uid,
                summary=_summary(item, self._spanish),
                status=TodoItemStatus.NEEDS_ACTION,
            )
            for item in self.coordinator.data
        ]


class DomusTaskList(CoordinatorEntity, TodoListEntity):
    """The currently open occurrences from the opted-in Domus household."""

    _attr_has_entity_name = True
    _attr_translation_key = "open_tasks"

    def __init__(self, entry: TasksEntry, language: str) -> None:
        super().__init__(entry.runtime_data)
        self._attr_unique_id = entry.unique_id
        self.entity_id = "todo.domus_tasks"
        self._state_labels = (
            _SPANISH_STATES if language.split("-", 1)[0].lower() == "es" else _ENGLISH_STATES
        )

    @property
    def todo_items(self) -> list[TodoItem] | None:
        if not self.available:
            return None
        return [
            TodoItem(
                uid=item.uid,
                summary=f"{item.title} · {self._state_labels[item.state]}",
                status=TodoItemStatus.NEEDS_ACTION,
            )
            for item in self.coordinator.data
        ]
