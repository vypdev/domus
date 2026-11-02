"""A fair-selection cursor records admission only; it does not prove work or calendar freshness."""

from dataclasses import dataclass

from domus.domain.identity import validate_revision
from domus.domain.storage import validate_identifier
from domus.domain.task_values import validate_task_time


@dataclass(frozen=True, slots=True)
class RecurrenceFrontier:
    household_id: str
    after_schedule_id: str | None
    selected_at: int
    revision: int = 1

    def __post_init__(self) -> None:
        validate_identifier(self.household_id)
        if self.after_schedule_id is not None:
            validate_identifier(self.after_schedule_id)
        validate_task_time(self.selected_at)
        validate_revision(self.revision)
