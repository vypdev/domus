"""Literal annotations belong to an individual manual Shopping request."""

from dataclasses import dataclass
from enum import StrEnum

from domus.domain.errors import InvalidInput
from domus.domain.task_values import validate_task_text

MAX_SHOPPING_NOTE = 1000


class ShoppingPriority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


def shopping_note(value: object) -> str:
    if not isinstance(value, str):
        raise InvalidInput("invalid_shopping_note")
    try:
        validate_task_text(value, MAX_SHOPPING_NOTE, required=False, multiline=True)
    except InvalidInput:
        raise InvalidInput("invalid_shopping_note") from None
    return value


def shopping_priority(value: object) -> ShoppingPriority:
    if not isinstance(value, str):
        raise InvalidInput("invalid_shopping_priority")
    try:
        return ShoppingPriority(value)
    except ValueError:
        raise InvalidInput("invalid_shopping_priority") from None


@dataclass(frozen=True, slots=True)
class ShoppingAnnotation:
    note: str = ""
    priority: ShoppingPriority = ShoppingPriority.NORMAL

    def __post_init__(self) -> None:
        shopping_note(self.note)
        if not isinstance(self.priority, ShoppingPriority):
            raise InvalidInput("invalid_shopping_priority")
