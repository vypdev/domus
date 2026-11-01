"""Recurrence application code receives temporal facts, never provider timezone objects."""

from typing import Protocol

from domus.domain.recurrence_records import (
    FixedProgress,
    FixedSchedule,
    ScheduledSlot,
    ScheduleState,
)
from domus.domain.recurrence_rules import FixedPattern, PeriodCandidates
from domus.domain.recurrence_time import NominalTime, RelativeInterval, ResolvedTime, TimePolicy
from domus.domain.storage import Installation


class RecurrenceTimes(Protocol):
    @property
    def data_identity(self) -> str: ...

    def require_policy(self, policy: TimePolicy) -> None: ...

    def resolve(self, nominal: NominalTime, policy: TimePolicy) -> ResolvedTime: ...

    def after_local_days(
        self, performed_at: int, interval: RelativeInterval, policy: TimePolicy
    ) -> ResolvedTime: ...


class NominalExpansion(Protocol):
    def period(self, pattern: FixedPattern, index: int) -> PeriodCandidates: ...


class RecurrenceRepository(Protocol):
    @property
    def installation(self) -> Installation: ...

    def schedule(self, household_id: str, schedule_id: str) -> FixedSchedule | None: ...
    def progress(self, household_id: str, schedule_id: str) -> FixedProgress | None: ...
    def slot(self, household_id: str, slot_key: str) -> ScheduledSlot | None: ...
    def save_schedule(self, value: FixedSchedule, expected_revision: int) -> None: ...
    def save_progress(self, value: FixedProgress, expected_revision: int) -> None: ...
    def add_slot(self, value: ScheduledSlot) -> None: ...
    def schedules(
        self,
        household_id: str,
        *,
        limit: int = 25,
        after: str | None = None,
        state: ScheduleState | None = None,
    ) -> tuple[FixedSchedule, ...]: ...
    def slots(
        self,
        household_id: str,
        schedule_id: str,
        *,
        limit: int = 25,
        after: str | None = None,
    ) -> tuple[ScheduledSlot, ...]: ...
