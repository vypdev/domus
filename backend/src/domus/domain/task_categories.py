"""Household category identities and bounded, inert display labels."""

from dataclasses import dataclass, replace
from typing import Self
from unicodedata import category, normalize

from domus.domain.errors import Conflict, InvalidInput
from domus.domain.identity import validate_revision
from domus.domain.storage import validate_identifier
from domus.domain.task_values import next_task_revision

MAX_ACTIVE_TASK_CATEGORIES = 100
MAX_TASK_CATEGORY_LABEL = 80
MAX_RAW_TASK_CATEGORY_LABEL = 256


def category_label(value: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) > MAX_RAW_TASK_CATEGORY_LABEL
        or any(category(character) in ("Cc", "Cs") for character in value)
    ):
        raise InvalidInput("invalid_task_category_label")
    label = normalize("NFC", value.strip())
    if not 1 <= len(label) <= MAX_TASK_CATEGORY_LABEL:
        raise InvalidInput("invalid_task_category_label")
    return label


@dataclass(frozen=True, slots=True)
class TaskCategory:
    category_id: str
    household_id: str
    label: str
    revision: int = 1
    archived: bool = False

    def __post_init__(self) -> None:
        validate_identifier(self.category_id)
        validate_identifier(self.household_id)
        validate_revision(self.revision)
        if type(self.archived) is not bool or category_label(self.label) != self.label:
            raise InvalidInput("invalid_task_category")

    @property
    def label_key(self) -> str:
        return normalize("NFC", self.label.casefold())

    def revise(self, label: str, *, archive: bool = False) -> Self:
        if self.archived or (not archive and label == self.label):
            raise Conflict("task_category_unchanged")
        return replace(
            self, label=label, archived=archive, revision=next_task_revision(self.revision)
        )
