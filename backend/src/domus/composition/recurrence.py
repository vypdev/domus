"""Bind local maintenance to the actual persistent installation and ASGI-owned lifetime."""

from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.concurrency import run_in_threadpool

from domus.application.fair_recurrence import (
    FairFixedRunner,
    FixedRun,
    RelativeRunServices,
    RunLimits,
)
from domus.application.fixed_materialization import FixedMaintenance, MaintenanceScope
from domus.application.fixed_recurrence import FixedRecurrencePlanner
from domus.application.ports import Transactions
from domus.application.recurrence_sources import RecurrenceSourceObservations
from domus.application.relative_lifecycle import RelativeLifecycle
from domus.application.relative_materialization import RelativeMaintenance
from domus.application.relative_recurrence import RelativeRecurrencePlanner
from domus.domain.errors import Forbidden
from domus.domain.nominal_recurrence import CalendarNominalExpansion
from domus.domain.storage import Installation
from domus.infrastructure.application_runtime import SecureIdentifiers, SystemClock
from domus.infrastructure.recurrence_time import PinnedRecurrenceTime
from domus.infrastructure.recurrence_worker import RecurrenceWorker


def recurrence_worker(store: Transactions, installation: Installation) -> RecurrenceWorker:
    times, clock, identifiers = PinnedRecurrenceTime(), SystemClock(), SecureIdentifiers()
    planner = FixedRecurrencePlanner(CalendarNominalExpansion(), times)

    def tick(should_continue: Callable[[], bool]) -> FixedRun:
        if not should_continue():
            return FixedRun("stopped")
        with store.read() as unit:
            if unit.recurrence.installation != installation:
                raise Forbidden("maintenance_scope_denied")
            household = unit.households.current()
        if household is None:
            return FixedRun("unconfigured")
        scope = MaintenanceScope(installation, household.household_id)
        return FairFixedRunner(
            store,
            scope,
            FixedMaintenance(store, scope, planner, clock, identifiers),
            times,
            clock,
            limits=RunLimits(horizon_days=household.materialization_horizon_days),
            relative=RelativeRunServices(
                RelativeMaintenance(store, scope, times, clock, identifiers),
                RecurrenceSourceObservations(store, scope),
                RelativeLifecycle(
                    store, scope, RelativeRecurrencePlanner(times), clock, identifiers
                ),
            ),
        ).tick(should_continue=should_continue)

    return RecurrenceWorker(tick)


def bind_lifespan(app: FastAPI, worker: RecurrenceWorker) -> None:
    previous = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[Mapping[str, object]]:
        async with previous(app) as state:
            try:
                worker.start()
                yield {} if state is None else state
            finally:
                await run_in_threadpool(worker.close)

    app.router.lifespan_context = lifespan
