"""One task service factory binds production session adapters to shared application use cases."""

from collections.abc import Callable
from typing import Protocol

from domus.application.calendar_commands import CalendarCommands
from domus.application.calendar_queries import CalendarQueries
from domus.application.family_queries import FamilyQueries
from domus.application.fixed_materialization import MaintenanceScope
from domus.application.fixed_recurrence import FixedRecurrencePlanner
from domus.application.inventory import InventorySettlement
from domus.application.point_allocations import AllocationCommands, AllocationQueries
from domus.application.ports import Transactions, UnitOfWork
from domus.application.recurrence_commands import RecurrenceCommands
from domus.application.recurrence_review import RecurrenceReview
from domus.application.relative_recurrence import RelativeRecurrencePlanner
from domus.application.relative_recurrence_commands import RelativeRecurrenceCommands
from domus.application.task_category_commands import TaskCategoryCommands
from domus.application.task_commands import TaskCommands
from domus.application.task_events import TaskEventFeed, TaskEventSource
from domus.application.task_queries import TaskQueries
from domus.domain.identity import HumanIdentity
from domus.domain.nominal_recurrence import CalendarNominalExpansion
from domus.domain.storage import Installation
from domus.entrypoints.task_http import TaskHTTPContext
from domus.infrastructure.application_runtime import SecureIdentifiers, SystemClock
from domus.infrastructure.auth_runtime import SecureEntropy
from domus.infrastructure.recurrence_time import PinnedRecurrenceTime
from domus.infrastructure.task_cursor import TaskCursor


class TaskSession(Protocol):
    def read(self) -> HumanIdentity: ...
    def current(self) -> HumanIdentity: ...


def task_event_source(store: Transactions, installation: Installation) -> TaskEventSource:
    return TaskEventFeed(store, installation)


def task_contexts(
    store: Transactions, installation: Installation
) -> Callable[[TaskSession], TaskHTTPContext]:
    clock, identifiers = SystemClock(), SecureIdentifiers()
    planner = RelativeRecurrencePlanner(PinnedRecurrenceTime())
    cursors = TaskCursor(clock, SecureEntropy().new().encode("ascii"))

    def inventory(unit: UnitOfWork) -> InventorySettlement:
        return InventorySettlement(unit.inventory, clock, identifiers)

    scope = MaintenanceScope(installation, "home")

    def context(actor: TaskSession) -> TaskHTTPContext:
        return TaskHTTPContext(
            lambda: TaskQueries(
                store,
                actor.read(),
                cursors,
                installation,
                schedule_data_identity=planner.times.data_identity,
            ),
            TaskCommands(store, actor, clock, identifiers, inventory_factory=inventory),
            RecurrenceReview(store, installation, actor, actor.read, clock, identifiers, planner),
            lambda: CalendarQueries(store, scope, actor.read(), cursors, planner.times),
            CalendarCommands(store, actor, actor.read, clock, identifiers),
            RecurrenceCommands(
                store,
                actor,
                clock,
                identifiers,
                FixedRecurrencePlanner(CalendarNominalExpansion(), planner.times),
                inventory_factory=inventory,
                bind_household_policy=True,
            ),
            RelativeRecurrenceCommands(
                store,
                actor,
                clock,
                identifiers,
                planner.times,
                inventory_factory=inventory,
                bind_household_policy=True,
            ),
            TaskCategoryCommands(store, actor, actor.read, clock, identifiers),
            lambda: FamilyQueries(store, scope, actor.read(), cursors, planner.times),
            lambda: AllocationQueries(store, actor.read()),
            AllocationCommands(store, actor, clock, identifiers),
        )

    return context
