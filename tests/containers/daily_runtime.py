"""Observe a real packaged daily worker with a controlled, test-only clock and identity."""

import asyncio
import json
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from domus.application.automation_execution import (
    AutomationExecution,
    ConfigureAutomation,
    RunAutomation,
)
from domus.application.automation_scheduled_control import (
    DailyAutomationControl,
    DailyControlRequest,
    ReviewedDailyRequest,
)
from domus.application.automation_scheduled_execution import ScheduledAutomationExecution
from domus.application.automation_scheduled_planning import DailyAutomationPlanner
from domus.application.fixed_materialization import MaintenanceScope
from domus.application.household_commands import HouseholdCommands, SetupHousehold
from domus.application.task_commands import TaskCommands
from domus.composition import automation, ingress, server
from domus.domain.automation import AutomationDraft, AutomationRule, DailyTrigger
from domus.domain.automation_scheduling import ScheduledOutcome
from domus.domain.identity import HumanIdentity
from domus.domain.task_values import TaskContent
from domus.infrastructure.application_runtime import SecureIdentifiers, TimeZoneCatalog
from domus.infrastructure.recurrence_time import PinnedRecurrenceTime
from domus.infrastructure.sqlite import SCHEMA_VERSION
from domus.infrastructure.sqlite_activation import SQLiteActivation
from domus.infrastructure.sqlite_restoration import SQLiteRestorations
from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots


class Clock:
    value = 1_795_219_200_000  # 2026-11-21T00:00:00Z

    def now(self):
        return self.value


class Actor:
    available = True

    def current(self):
        assert self.available, "The scheduled worker must not request interactive human authority"
        return HumanIdentity("daily-image-fixture", True, True, False)

    def get(self, _identifier):
        raise AssertionError("No external directory access is part of this fixture")


async def wait_for(predicate):
    deadline = time.monotonic() + 18
    while not predicate():
        assert time.monotonic() < deadline, "Owned daily worker did not reach the expected state"
        await asyncio.sleep(0.05)


def exercise(mode, restart_admitted):
    assert SCHEMA_VERSION == 38
    clock, actor, identifiers = Clock(), Actor(), SecureIdentifiers()
    planner = DailyAutomationPlanner(PinnedRecurrenceTime())

    def owned(root):
        with patch.object(automation, "SystemClock", lambda: clock):
            if mode == "native":
                return ingress.create_owned_runtime(
                    "fixture", "edge", root, ("https://domus.fixture",)
                )
            return server.create_owned_runtime(
                "http://ha.fixture", "https://domus.fixture", "edge", root
            )

    def service(runtime):
        store = runtime.storage.database
        return DailyAutomationControl(
            store,
            MaintenanceScope(store.installation, "home"),
            actor,
            actor.current,
            clock,
            identifiers,
            planner,
        )

    def tasks(runtime):
        with runtime.storage.database.read() as unit:
            return unit.tasks.definitions("home")

    with TemporaryDirectory(prefix="daily-worker-image-") as directory:
        root = Path(directory)
        runtime = owned(root)
        try:
            store = runtime.storage.database
            HouseholdCommands(store, actor, actor, TimeZoneCatalog(), clock, identifiers).setup(
                "setup", SetupHousehold("Fictional daily image household", "UTC")
            )
            with store.write() as unit:
                unit.automation_drafts.append(
                    "home",
                    AutomationDraft(
                        "daily",
                        1,
                        AutomationRule(
                            2, DailyTrigger("00:01"), None, TaskContent("Daily image task")
                        ),
                    ),
                )
                unit.automation_drafts.append(
                    "home",
                    AutomationDraft(
                        "manual",
                        1,
                        AutomationRule(1, "manual", None, TaskContent("Manual image task")),
                    ),
                )
            control = service(runtime)
            review = control.review("daily", 1)
            control.enable(
                "enable", ReviewedDailyRequest("daily", 1, 0, 0, review.proposed_times[0])
            )
            approved = control.review("daily", 1).schedule
            manual = AutomationExecution(
                store,
                control.scope,
                actor,
                actor.current,
                clock,
                identifiers,
                TaskCommands(store, actor, clock, identifiers),
            )
            manual.configure("manual-enable", ConfigureAutomation("manual", 1, 0, True))
            clock.value = approved.next_time.instant_ms + 1
            if restart_admitted:
                engine = ScheduledAutomationExecution(
                    store, control.scope, clock, identifiers, planner, clock.value - 60_001
                )
                assert engine.admit("daily").status == "admitted"
                assert tasks(runtime) == ()
                runtime.close()
                clock.value += 3 * 86_400_000
                runtime = owned(root)
            actor.available = False

            async def lifetime():
                worker = runtime.automation_worker
                assert worker is not None and not worker.is_running
                async with runtime.app.router.lifespan_context(runtime.app):
                    await wait_for(lambda: len(tasks(runtime)) == 1)
                    assert worker.is_running and worker.last_failure is None
                    with runtime.storage.database.read() as unit:
                        runs = unit.scheduled_automations.history("home", "daily", limit=10)
                        assert len(runs) == 1 and runs[0].outcome is ScheduledOutcome.CREATED
                        assert runs[0].grant == approved.grant
                        assert runs[0].planned == approved.next_time
                        assert unit.tasks.occurrence("home", runs[0].task_occurrence_id) is not None
                        assert not unit.scheduled_automations.pending("home")
                        assert unit.automation_controls.get("home", "manual").enabled
                    actor.available = True
                    current = service(runtime).review("daily", 1)
                    service(runtime).disable(
                        "disable",
                        DailyControlRequest(
                            "daily", 1, current.control.control_revision, current.schedule.revision
                        ),
                    )
                    previous = worker.last_run
                    clock.value += 2 * 86_400_000
                    await wait_for(lambda: worker.last_run is not previous)
                    assert len(tasks(runtime)) == 1 and worker.last_failure is None
                assert not worker.is_running
                assert not runtime.recurrence.is_running and not runtime.points_worker.is_running

            asyncio.run(lifetime())
            # The existing manual path remains usable after daily revocation and restart.
            store = runtime.storage.database
            control = service(runtime)
            manual = AutomationExecution(
                store,
                control.scope,
                actor,
                actor.current,
                clock,
                identifiers,
                TaskCommands(store, actor, clock, identifiers),
            )
            receipt = manual.run("manual-run", RunAutomation("manual", 1, 1))
            assert receipt.result.decode()["condition_matched"]
            assert len(tasks(runtime)) == 2
        finally:
            runtime.close()
        runtime = owned(root)
        try:
            assert len(tasks(runtime)) == 2
            current = service(runtime).review("daily", 1)
            assert (
                not current.control.enabled
                and current.schedule.grant.principal == approved.grant.principal
            )
            assert current.schedule.next_time.instant_ms > approved.next_time.instant_ms
            # Capture an actual admitted queue, cancel it afterwards, then let the
            # ordinary owned worker encounter the restored enabled checkpoint.
            with TemporaryDirectory(prefix="daily-cancelled-restore-image-") as recovery:
                manager = service(runtime)
                manager.enable(
                    "restore-enable",
                    ReviewedDailyRequest(
                        "daily",
                        1,
                        current.control.control_revision,
                        current.schedule.revision,
                        current.proposed_times[0],
                    ),
                )
                selected = manager.review("daily", 1).schedule
                clock.value = selected.next_time.instant_ms + 1
                store = runtime.storage.database
                engine = ScheduledAutomationExecution(
                    store, manager.scope, clock, identifiers, planner, clock.value - 60_001
                )
                admitted = engine.admit("daily")
                assert admitted.status == "admitted"
                archive, target = Path(recovery) / "checkpoint", Path(recovery) / "prepared"
                checkpoint = SQLiteSnapshots(store, archive, store.installation, clock).create(
                    "queued"
                )
                current = manager.review("daily", 1)
                manager.disable(
                    "restore-disable",
                    DailyControlRequest(
                        "daily", 1, current.control.control_revision, current.schedule.revision
                    ),
                )
                with store.read() as unit:
                    cancelled = unit.scheduled_automations.run("home", admitted.trigger_key)
                    assert cancelled.outcome is ScheduledOutcome.CANCELLED
                SQLiteRestorations(
                    store, archive, target, store.installation, clock, checkpoint
                ).prepare("restore-cancelled")
                runtime.close()
                assert (
                    SQLiteActivation(root, store.installation, clock, target).activate().state
                    == "active"
                )
                actor.available = False
                runtime = owned(root)
                with runtime.storage.database.read() as unit:
                    assert (
                        unit.scheduled_automations.run("home", admitted.trigger_key).outcome
                        is ScheduledOutcome.QUEUED
                    )

                def reconciled():
                    with runtime.storage.database.read() as unit:
                        return not unit.scheduled_automations.pending("home")

                async def restored_lifetime():
                    async with runtime.app.router.lifespan_context(runtime.app):
                        await wait_for(reconciled)
                        assert runtime.automation_worker.is_running
                        assert runtime.automation_worker.last_failure is None
                        with runtime.storage.database.read() as unit:
                            assert (
                                unit.scheduled_automations.run("home", admitted.trigger_key)
                                == cancelled
                            )
                            assert len(unit.tasks.definitions("home")) == 2
                    assert not runtime.automation_worker.is_running

                asyncio.run(restored_lifetime())
        finally:
            runtime.close()
    print(
        json.dumps(
            {
                "mode": mode,
                "restart_admitted": restart_admitted,
                "daily_tasks": 1,
                "manual_tasks": 1,
                "worker_joined": True,
                "revoked_without_redelivery": True,
                "cancelled_checkpoint_restored_without_a_task": True,
            }
        )
    )


if __name__ == "__main__":
    exercise(sys.argv[1], sys.argv[2] == "True")
