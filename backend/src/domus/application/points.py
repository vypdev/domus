"""Process a bounded live source page and its Points ledger effects atomically."""

from collections.abc import Callable
from dataclasses import dataclass

from domus.application.ports import Clock, Transactions, UnitOfWork
from domus.application.task_events import lifecycle_page
from domus.domain.errors import Forbidden, StorageFailure
from domus.domain.points import PointsPosting, conserve_points, points_source_fingerprint
from domus.domain.storage import Installation, validate_identifier
from domus.domain.task_events import TaskLifecycleEvent


@dataclass(frozen=True, slots=True)
class PointsConsumer:
    store: Transactions
    installation: Installation
    clock: Clock

    def tick(self, should_continue: Callable[[], bool]) -> int:
        with self.store.write() as unit:
            if unit.recurrence.installation != self.installation:
                raise Forbidden("maintenance_scope_denied")
            household = unit.households.current()
            if household is None:
                return 0
            scope = household.household_id
            page = lifecycle_page(unit, self.installation, scope, 25, unit.points.position(scope))
            consumed = 0
            for event in page.items:
                if not should_continue():
                    break
                self._record(unit, event)
                consumed += 1
            return consumed

    def ledger(self, household_id: str, cycle_id: str) -> tuple[PointsPosting, ...]:
        validate_identifier(household_id)
        validate_identifier(cycle_id)
        with self.store.read() as unit:
            if unit.recurrence.installation != self.installation:
                raise Forbidden("maintenance_scope_denied")
            return unit.points.ledger(household_id, cycle_id)

    def _record(self, unit: UnitOfWork, event: TaskLifecycleEvent) -> None:
        scope, cycle = event.cycle.household_id, event.cycle.cycle_id
        fingerprint = points_source_fingerprint(event)
        prior = unit.points.processed(scope, event.event_id)
        if prior is not None:
            if prior != fingerprint:
                raise StorageFailure("invalid_points_source")
            return
        entries = unit.points.ledger(scope, cycle)
        posting = None
        if event.closes_awards and len(entries) == 1:
            posting = entries[0].reverse(event.event_id, self.clock.now())
        elif event.points_eligible and not entries:
            # Fence a completion that became closed or rejected before its first delivery.
            current = unit.tasks.cycle(scope, cycle)
            if current == event.cycle and unit.tasks.restored_cycle_closure(scope, cycle) is None:
                posting = conserve_points(
                    event, self.clock.now(), unit.points.next_recipient(scope, event.definition_id)
                )
        unit.points.add(event, fingerprint, posting)
