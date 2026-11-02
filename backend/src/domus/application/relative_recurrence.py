"""Plan one completion-relative successor from actual work; no storage or execution claim."""

from dataclasses import dataclass
from datetime import timedelta

from domus.application.recurrence_ports import RecurrenceTimes
from domus.domain.errors import IntegrationUnavailable, InvalidInput
from domus.domain.recurrence_planning import PlannedSlot
from domus.domain.recurrence_records import ScheduleState
from domus.domain.recurrence_rules import NominalDate
from domus.domain.recurrence_time import LocalInstant, NominalTime, ResolvedTime
from domus.domain.relative_recurrence import RelativeSchedule, RelativeSource
from domus.domain.task_values import VerificationState
from domus.domain.tasks import TaskCycle


@dataclass(frozen=True, slots=True)
class RelativePlan:
    status: str
    planned: PlannedSlot | None = None
    source: RelativeSource | None = None


@dataclass(frozen=True, slots=True)
class RelativeRecurrencePlanner:
    times: RecurrenceTimes

    def plan(self, schedule: RelativeSchedule, cycle: TaskCycle) -> RelativePlan:
        if not schedule.allows_successor(cycle):
            status = (
                schedule.state.value
                if schedule.state is not ScheduleState.ACTIVE
                else "source_closed"
                if cycle.closed_at is not None or cycle.verification is VerificationState.REJECTED
                else "waiting_verification"
            )
            return RelativePlan(status)
        local = self.times.local_at(cycle.performed_at, schedule.policy)
        if (
            not isinstance(local, LocalInstant)
            or local.instant_ms != cycle.performed_at
            or local.policy != schedule.policy
        ):
            raise IntegrationUnavailable("recurrence_time_source_invalid")
        source = RelativeSource.from_cycle(cycle, local)
        try:
            expected = local.local + timedelta(days=schedule.interval.days)
        except OverflowError:
            raise InvalidInput("recurrence_time_out_of_range") from None
        if isinstance(schedule.initial.nominal, NominalDate):
            return RelativePlan("ready", PlannedSlot(NominalDate(expected.date()), None), source)
        resolved = self.times.after_local_days(
            cycle.performed_at, schedule.interval, schedule.policy
        )
        if (
            not isinstance(resolved, ResolvedTime)
            or resolved.nominal != NominalTime(expected)
            or resolved.policy != schedule.policy
            or resolved.zone_digest != local.zone_digest
        ):
            raise IntegrationUnavailable("recurrence_time_source_invalid")
        return RelativePlan("ready", PlannedSlot(resolved.nominal, resolved), source)
