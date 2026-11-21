"""Durable daily facts join the caller's ordinary unit of work."""

from typing import Protocol

from domus.domain.automation_scheduling import DailyAutomationSchedule, ScheduledAutomationRun


class ScheduledAutomationRecords(Protocol):
    def pending_count(
        self, household_id: str, *, rule_id: str | None = None, limit: int = 1000
    ) -> int: ...

    def schedule(self, household_id: str, rule_id: str) -> DailyAutomationSchedule | None: ...
    def save_schedule(self, value: DailyAutomationSchedule, expected_revision: int) -> None: ...
    def schedules(
        self, household_id: str, *, after: str | None = None, limit: int = 100
    ) -> tuple[DailyAutomationSchedule, ...]: ...
    def run(self, household_id: str, trigger_key: str) -> ScheduledAutomationRun | None: ...
    def admit(self, value: ScheduledAutomationRun) -> None: ...
    def finish(self, value: ScheduledAutomationRun) -> None: ...
    def pending(
        self,
        household_id: str,
        *,
        rule_id: str | None = None,
        limit: int = 100,
        after: tuple[int, str] | None = None,
    ) -> tuple[ScheduledAutomationRun, ...]: ...
    def cancel_pending(self, household_id: str, rule_id: str, at: int) -> int: ...
    def history(
        self,
        household_id: str,
        rule_id: str,
        *,
        before: tuple[int, str] | None = None,
        limit: int = 25,
    ) -> tuple[ScheduledAutomationRun, ...]: ...
