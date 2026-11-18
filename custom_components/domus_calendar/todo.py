"""Present the last complete authorized shopping snapshot as a read-only list."""

from homeassistant.components.todo import TodoItem, TodoItemStatus, TodoListEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import ShoppingEntry
from .shopping_client import ShoppingItem

_SYMBOLS = {"gram": "g", "millilitre": "mL"}


async def async_setup_entry(
    hass: HomeAssistant, entry: ShoppingEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([DomusShoppingList(entry, hass.config.language)])


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
