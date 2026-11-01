"""A composition-only read port exports live source facts, never consumer success or authority."""

from dataclasses import dataclass
from typing import Protocol, cast

from domus.application.ports import Transactions
from domus.application.task_authorization import recorded_request
from domus.domain.errors import InvalidInput, NotFound, StorageFailure
from domus.domain.storage import Installation, validate_identifier
from domus.domain.task_events import TaskLifecycleEvent, lifecycle_event


@dataclass(frozen=True, slots=True)
class TaskEventPage:
    items: tuple[TaskLifecycleEvent, ...]
    next_position: int | None


class TaskEventSource(Protocol):
    """Trusted local consumers keep their own durable inbox/closure; no human HTTP surface."""

    def read(self, *, limit: int = 25, after: int = 0) -> TaskEventPage: ...


@dataclass(frozen=True, slots=True)
class TaskEventFeed:
    transactions: Transactions
    installation: Installation
    household_id: str = "home"

    def __post_init__(self) -> None:
        validate_identifier(self.household_id)
        if not isinstance(self.installation, Installation):
            raise InvalidInput("invalid_task_event_source")

    def read(self, *, limit: int = 25, after: int = 0) -> TaskEventPage:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise InvalidInput("invalid_page_size")
        if type(after) is not int or not 0 <= after <= 2**63 - 1:
            raise InvalidInput("invalid_task_position")
        with self.transactions.read() as unit:
            if unit.households.get(self.household_id) is None:
                raise NotFound("household_missing")
            rows = unit.tasks.lifecycle_events(self.household_id, limit=limit + 1, after=after)
            items = []
            for row in rows:
                recorded_request(row)
                try:
                    raw = row.receipt.result.decode().get("cycle")
                    if not isinstance(raw, dict):
                        raise InvalidInput("invalid_task_event")
                    cycle_id = cast(str, raw.get("cycle_id"))
                    validate_identifier(cycle_id)
                    cycle = unit.tasks.cycle(self.household_id, cycle_id)
                    if cycle is None:
                        raise InvalidInput("invalid_task_event")
                    work = unit.tasks.occurrence(self.household_id, cycle.occurrence_id)
                    if work is None:
                        raise InvalidInput("invalid_task_event")
                    items.append(lifecycle_event(row, work, cycle, self.installation))
                except InvalidInput, TypeError, ValueError:
                    raise StorageFailure("invalid_task_event") from None
            return TaskEventPage(
                tuple(items[:limit]), items[limit - 1].position if len(items) > limit else None
            )
