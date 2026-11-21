"""Plan bounded daily times under an explicitly selected, immutable time policy."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from domus.application.recurrence_ports import RecurrenceTimes
from domus.domain.automation import require_daily_time
from domus.domain.errors import IntegrationUnavailable, InvalidInput
from domus.domain.recurrence_time import NominalTime, ResolvedTime, TimePolicy


@dataclass(frozen=True, slots=True)
class DailyAutomationPlanner:
    times: RecurrenceTimes

    def require_approved(self, value: ResolvedTime) -> None:
        if self.times.resolve(value.nominal, value.policy) != value:
            raise IntegrationUnavailable("daily_automation_approved_time_changed")

    def next(
        self, requested: str, policy: TimePolicy, after: int, *, after_date: date | None = None
    ) -> ResolvedTime:
        return self._plan(requested, policy, after, after_date, 1)[0]

    def upcoming(
        self, requested: str, policy: TimePolicy, after: int, *, after_date: date | None = None
    ) -> tuple[ResolvedTime, ...]:
        return self._plan(requested, policy, after, after_date, 5)

    def _plan(
        self, requested: str, policy: TimePolicy, after: int, after_date: date | None, count: int
    ) -> tuple[ResolvedTime, ...]:
        require_daily_time(requested)
        minute = time.fromisoformat(requested)
        today = self.times.local_at(after, policy).local.date()
        items: list[ResolvedTime] = []
        try:
            # A persisted nominal frontier prevents clock rollback or explicit
            # policy adoption from admitting the same logical date again.
            first = today if after_date is None else max(today, after_date + timedelta(days=1))
            # Allow an elapsed time today and a skipped date resolving to the
            # following day's instant. Never backfill an unbounded date range.
            for offset in range(7):
                day = first + timedelta(days=offset)
                resolved = self.times.resolve(NominalTime(datetime.combine(day, minute)), policy)
                if resolved.instant_ms <= after:
                    continue
                items.append(resolved)
                if len(items) == count:
                    return tuple(items)
                after = resolved.instant_ms
        except OverflowError:
            raise InvalidInput("recurrence_time_out_of_range") from None
        raise IntegrationUnavailable("daily_automation_times_unavailable")
