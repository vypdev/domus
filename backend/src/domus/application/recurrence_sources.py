"""A composition-scoped source reads original current/history facts without granting effects."""

from dataclasses import dataclass

from domus.application.fixed_materialization import MaintenanceScope
from domus.application.ports import Transactions, UnitOfWork
from domus.application.task_authorization import recorded_request
from domus.domain.errors import InvalidInput, StorageFailure
from domus.domain.restoration import RetainedOperation
from domus.domain.task_events import TaskLifecycleEvent, TaskSourceRecord


@dataclass(frozen=True, slots=True)
class RecurrenceObservation:
    original: RetainedOperation
    event: TaskLifecycleEvent


@dataclass(frozen=True, slots=True)
class RecurrenceSourcePage:
    items: tuple[RecurrenceObservation, ...]
    after_position: int
    complete: bool
    source_rows_examined: int


@dataclass(frozen=True, slots=True)
class RecurrenceSourceObservations:
    transactions: Transactions
    scope: MaintenanceScope

    @staticmethod
    def _limit(limit: int) -> None:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise InvalidInput("invalid_page_size")

    def read(self, *, limit: int = 100, after: int = 0) -> RecurrenceSourcePage:
        self._limit(limit)
        if type(after) is not int or not 0 <= after <= 2**63 - 1:
            raise InvalidInput("invalid_task_position")
        with self.transactions.read() as unit:
            self.scope.require(unit)
            return self._read(unit, limit, after, persist=False)

    def ingest(self, *, limit: int = 100) -> RecurrenceSourcePage:
        """Persist the page and its continuation in the same bounded writer."""
        self._limit(limit)
        with self.transactions.write() as unit:
            self.scope.require(unit)
            after = unit.recurrence.relative_inbox_after(self.scope.household_id)
            return self._read(unit, limit, after, persist=True)

    def _read(
        self, unit: UnitOfWork, limit: int, after: int, *, persist: bool
    ) -> RecurrenceSourcePage:
        records = unit.tasks.lifecycle_sources(self.scope.household_id, limit=limit, after=after)
        if type(records) is not tuple or len(records) > limit:
            raise StorageFailure("invalid_recurrence_source")
        items = []
        previous = after
        for record in records:
            if not isinstance(record, TaskSourceRecord):
                raise StorageFailure("invalid_recurrence_source")
            recorded_request(record.original.evidence)
            try:
                event = record.event(self.scope.installation)
            except InvalidInput, TypeError, ValueError:
                raise StorageFailure("invalid_recurrence_source") from None
            if event.cycle.household_id != self.scope.household_id or event.position <= previous:
                raise StorageFailure("invalid_recurrence_source")
            if persist:
                unit.recurrence.add_relative_source(record)
            items.append(RecurrenceObservation(record.original, event))
            previous = event.position
        # An exact full page is conservatively incomplete; an empty scan spends one unit.
        return RecurrenceSourcePage(
            tuple(items), previous, len(records) < limit, max(1, len(records))
        )
