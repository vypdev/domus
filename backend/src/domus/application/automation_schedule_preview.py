"""Resolve the next five proposed daily times with the current household policy."""

from dataclasses import dataclass
from datetime import datetime, time, timedelta

from domus.application.automation_preview import require_manual_automation
from domus.application.fixed_materialization import MaintenanceScope
from domus.application.ports import Clock, Transactions
from domus.application.recurrence_ports import RecurrenceTimes
from domus.domain.automation import require_daily_time
from domus.domain.errors import IntegrationUnavailable, InvalidInput
from domus.domain.identity import HumanIdentity
from domus.domain.recurrence_time import NominalTime, TimePolicy, TimeResolution


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
        require_daily_time(requested)
        minute = time.fromisoformat(requested)
        with self.transactions.read() as unit:
            home = self.scope.require(unit)
            require_manual_automation(unit, home.household_id, self.human)
            policy = TimePolicy(
                home.time_zone, self.times.data_identity, home.repeated_time, home.revision
            )
            return DailyAutomationTimes(home.time_zone, requested, self._upcoming(minute, policy))

    def _upcoming(self, minute: time, policy: TimePolicy) -> tuple[DailyAutomationTime, ...]:
        after = self.clock.now()
        today = self.times.local_at(after, policy).local.date()
        items: list[DailyAutomationTime] = []
        # Seven local dates allow for today to have passed and for a skipped date
        # to resolve to the same instant as the following day's nominal time.
        try:
            for offset in range(7):
                day = today + timedelta(days=offset)
                resolved = self.times.resolve(NominalTime(datetime.combine(day, minute)), policy)
                if resolved.instant_ms <= after:
                    continue
                items.append(
                    DailyAutomationTime(
                        day.isoformat(),
                        resolved.resolved_local.isoformat(timespec="milliseconds"),
                        resolved.instant_ms,
                        resolved.offset_seconds,
                        resolved.resolution,
                    )
                )
                if len(items) == 5:
                    return tuple(items)
                after = resolved.instant_ms
        except OverflowError:
            raise InvalidInput("recurrence_time_out_of_range") from None
        raise IntegrationUnavailable("daily_automation_times_unavailable")
