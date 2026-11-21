"""Resolve the next five proposed daily times with the current household policy."""

from dataclasses import dataclass

from domus.application.automation_preview import require_manual_automation
from domus.application.automation_scheduled_planning import DailyAutomationPlanner
from domus.application.fixed_materialization import MaintenanceScope
from domus.application.ports import Clock, Transactions
from domus.application.recurrence_ports import RecurrenceTimes
from domus.domain.identity import HumanIdentity
from domus.domain.recurrence_time import TimePolicy, TimeResolution


@dataclass(frozen=True, slots=True)
class DailyAutomationTime:
    requested_date: str
    resolved_local: str
    instant_ms: int
    offset_seconds: int
    resolution: TimeResolution


@dataclass(frozen=True, slots=True)
class DailyAutomationTimes:
    time_zone: str
    requested_time: str
    items: tuple[DailyAutomationTime, ...]


@dataclass(frozen=True, slots=True)
class AutomationSchedulePreview:
    transactions: Transactions
    scope: MaintenanceScope
    human: HumanIdentity
    clock: Clock
    times: RecurrenceTimes

    def daily(self, requested: str) -> DailyAutomationTimes:
        with self.transactions.read() as unit:
            home = self.scope.require(unit)
            require_manual_automation(unit, home.household_id, self.human)
            policy = TimePolicy(
                home.time_zone, self.times.data_identity, home.repeated_time, home.revision
            )
            upcoming = DailyAutomationPlanner(self.times).upcoming(
                requested, policy, self.clock.now()
            )
            return DailyAutomationTimes(
                home.time_zone,
                requested,
                tuple(
                    DailyAutomationTime(
                        resolved.nominal.local.date().isoformat(),
                        resolved.resolved_local.isoformat(timespec="milliseconds"),
                        resolved.instant_ms,
                        resolved.offset_seconds,
                        resolved.resolution,
                    )
                    for resolved in upcoming
                ),
            )
