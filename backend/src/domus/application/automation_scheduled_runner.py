"""Bounded polling fairly visits active rules while preserving independently admitted work."""

from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial

from domus.application.automation_scheduled_execution import (
    ScheduledAutomationExecution,
    ScheduledAutomationStep,
)
from domus.domain.errors import DomusError, Forbidden, InvalidInput


@dataclass(frozen=True, slots=True)
class DailyAutomationTick:
    status: str
    steps: tuple[ScheduledAutomationStep, ...] = ()


@dataclass
class DailyAutomationRunner:
    engine: ScheduledAutomationExecution
    limit: int = 25
    _after: str | None = field(default=None, init=False, repr=False)
    _pending_after: tuple[int, str] | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if type(self.limit) is not int or not 1 <= self.limit <= 25:
            raise InvalidInput("invalid_daily_automation_limits")

    def _attempt(
        self, rule_id: str, action: Callable[[], ScheduledAutomationStep]
    ) -> ScheduledAutomationStep:
        try:
            return action()
        except DomusError as failure:
            if isinstance(failure, Forbidden) and failure.code == "maintenance_scope_denied":
                raise
            return ScheduledAutomationStep("unavailable", rule_id)

    def tick(self, should_continue: Callable[[], bool]) -> DailyAutomationTick:
        if not should_continue():
            return DailyAutomationTick("stopped")
        with self.engine.transactions.read() as unit:
            home = self.engine.scope.require(unit).household_id
            pending = unit.scheduled_automations.pending(
                home, limit=self.limit, after=self._pending_after
            )
            if not pending and self._pending_after is not None:
                self._pending_after = None
                pending = unit.scheduled_automations.pending(home, limit=self.limit)
            schedules = unit.scheduled_automations.schedules(
                home, after=self._after, limit=self.limit
            )
            if not schedules and self._after is not None:
                self._after = None
                schedules = unit.scheduled_automations.schedules(home, limit=self.limit)
        steps: list[ScheduledAutomationStep] = []
        for run in pending:
            if not should_continue():
                return DailyAutomationTick("stopped", tuple(steps))
            steps.append(
                self._attempt(
                    run.grant.draft.rule_id,
                    partial(self.engine.execute, run.key, should_continue=should_continue),
                )
            )
            self._pending_after = (run.admitted_at, run.key)
        for schedule in schedules:
            if not should_continue():
                return DailyAutomationTick("stopped", tuple(steps))
            rule_id = schedule.grant.draft.rule_id
            steps.append(
                self._attempt(
                    rule_id, partial(self.engine.admit, rule_id, should_continue=should_continue)
                )
            )
            self._after = rule_id
        return DailyAutomationTick("idle" if not steps else "processed", tuple(steps))
