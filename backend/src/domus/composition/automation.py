"""One owned automation worker uses the actual installation and no human session."""

from collections.abc import Callable

from domus.application.automation_scheduled_execution import ScheduledAutomationExecution
from domus.application.automation_scheduled_planning import DailyAutomationPlanner
from domus.application.automation_scheduled_runner import DailyAutomationRunner, DailyAutomationTick
from domus.application.fixed_materialization import MaintenanceScope
from domus.application.ports import Transactions
from domus.domain.errors import Forbidden
from domus.domain.storage import Installation
from domus.infrastructure.application_runtime import SecureIdentifiers, SystemClock
from domus.infrastructure.recurrence_time import PinnedRecurrenceTime
from domus.infrastructure.recurrence_worker import MaintenanceWorker


def automation_worker(
    store: Transactions, installation: Installation
) -> MaintenanceWorker[DailyAutomationTick]:
    clock, identifiers = SystemClock(), SecureIdentifiers()
    planner = DailyAutomationPlanner(PinnedRecurrenceTime())
    startup_ms = clock.now()
    runner: DailyAutomationRunner | None = None

    def tick(should_continue: Callable[[], bool]) -> DailyAutomationTick:
        nonlocal runner
        if not should_continue():
            return DailyAutomationTick("stopped")
        with store.read() as unit:
            if unit.recurrence.installation != installation:
                raise Forbidden("maintenance_scope_denied")
            home = unit.households.current()
        if home is None:
            return DailyAutomationTick("unconfigured")
        if runner is None:
            runner = DailyAutomationRunner(
                ScheduledAutomationExecution(
                    store,
                    MaintenanceScope(installation, home.household_id),
                    clock,
                    identifiers,
                    planner,
                    startup_ms,
                )
            )
        return runner.tick(should_continue)

    return MaintenanceWorker(tick, "automation")
