"""Durable bounded rule admission and fair round-robin steps; no thread or calendar claim."""

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from domus.application.fixed_materialization import FixedMaintenance, MaintenanceScope
from domus.application.ports import Clock, Transactions
from domus.application.recurrence_ports import RecurrenceTimes
from domus.domain.errors import (
    Conflict,
    DomusError,
    Forbidden,
    IntegrationUnavailable,
    InvalidInput,
    NotFound,
    StorageBusy,
    StorageFailure,
)
from domus.domain.recurrence_frontier import RecurrenceFrontier
from domus.domain.recurrence_records import FixedSchedule, ScheduleState
from domus.domain.recurrence_rules import NominalDate, NominalSlot
from domus.domain.recurrence_time import RelativeInterval


@dataclass(frozen=True, slots=True)
class RunLimits:
    max_definitions: int = 50
    max_slots: int = 1000
    max_periods: int = 4096
    horizon_days: int = 60

    def __post_init__(self) -> None:
        for value, lower, upper in (
            (self.max_definitions, 1, 50),
            (self.max_slots, 1, 1000),
            (self.max_periods, 1, 64000),
            (self.horizon_days, 7, 366),
        ):
            if type(value) is not int or not lower <= value <= upper:
                raise InvalidInput("invalid_recurrence_run_limits")


@dataclass(frozen=True, slots=True)
class RuleAttention:
    schedule_id: str
    code: str


def _attention_code(error: DomusError) -> str:
    if isinstance(error, Conflict):
        return (
            "original_proof_conflict" if error.code == "idempotency_conflict" else "source_changed"
        )
    for kind, code in (
        (StorageBusy, "storage_busy"),
        (StorageFailure, "result_unconfirmed"),
        (IntegrationUnavailable, "time_source_unavailable"),
        (InvalidInput, "invalid_rule"),
        (NotFound, "source_changed"),
    ):
        if isinstance(error, kind):
            return code
    return "recurrence_unavailable"


@dataclass(frozen=True, slots=True)
class FixedRun:
    """Counters are confirmed observations for the selected run, never calendar totals."""

    status: str
    selected_schedule_ids: tuple[str, ...] = ()
    created: int = 0
    replayed: int = 0
    historical_absent: int = 0
    periods_scanned: int = 0
    attention_items: tuple[RuleAttention, ...] = ()

    @property
    def attention_count(self) -> int:
        return len(self.attention_items)


@dataclass
class FairFixedRunner:
    transactions: Transactions
    scope: MaintenanceScope
    stepper: FixedMaintenance
    times: RecurrenceTimes
    clock: Clock
    limits: RunLimits = RunLimits()

    def _select(self) -> tuple[tuple[FixedSchedule, ...], int] | None:
        with self.transactions.read() as unit:
            if self.scope.household(unit) is None:
                return None
            home = self.scope.household_id
            frontier = unit.recurrence.frontier(home)
            after = None if frontier is None else frontier.after_schedule_id
            selected = unit.recurrence.schedules(
                home, limit=self.limits.max_definitions, after=after, state=ScheduleState.ACTIVE
            )
            if after is not None and len(selected) < self.limits.max_definitions:
                head = unit.recurrence.schedules(
                    home,
                    limit=self.limits.max_definitions - len(selected),
                    state=ScheduleState.ACTIVE,
                )
                seen = {rule.schedule_id for rule in selected}
                selected += tuple(rule for rule in head if rule.schedule_id not in seen)
            now = self.clock.now()
            return selected, now

    def _admit(self, schedule_id: str) -> None:
        with self.transactions.write() as unit:
            self.scope.require(unit)
            home = self.scope.household_id
            frontier = unit.recurrence.frontier(home)
            if frontier is not None and frontier.after_schedule_id == schedule_id:
                return
            expected = 0 if frontier is None else frontier.revision
            unit.recurrence.save_frontier(
                RecurrenceFrontier(home, schedule_id, self.clock.now(), expected + 1), expected
            )

    def tick(self, *, should_continue: Callable[[], bool] = lambda: True) -> FixedRun:
        if not should_continue():
            return FixedRun("stopped")
        claim = self._select()
        if claim is None:
            return FixedRun("unconfigured")
        selected, started_at = claim
        pending = deque(selected)
        horizons: dict[str, NominalSlot] = {}
        admitted: set[str] = set()
        created = replayed = historical = scanned = 0
        attention: list[RuleAttention] = []
        stopped = False
        while (
            pending
            and created + replayed + historical < self.limits.max_slots
            and scanned < self.limits.max_periods
        ):
            if not should_continue():
                stopped = True
                break
            rule = pending.popleft()
            try:
                # Reserve each actually attempted rule before provider I/O. Reserving an entire
                # unvisited window could starve its later rules after repeated interrupted runs.
                if rule.schedule_id not in admitted:
                    self._admit(rule.schedule_id)
                    admitted.add(rule.schedule_id)
                before = horizons.get(rule.schedule_id)
                if before is None:
                    horizon = self.times.after_local_days(
                        started_at, RelativeInterval(self.limits.horizon_days), rule.policy
                    ).nominal
                    before = (
                        NominalDate(horizon.local.date())
                        if isinstance(rule.pattern.start, NominalDate)
                        else horizon
                    )
                    horizons[rule.schedule_id] = before
                if not should_continue():
                    stopped = True
                    break
                result = self.stepper.step(
                    rule.schedule_id,
                    before,
                    period_limit=min(64, self.limits.max_periods - scanned),
                    expected_schedule=rule,
                    should_continue=should_continue,
                )
            except Forbidden:
                raise
            except DomusError as error:
                # An unavailable/unconfirmed rule keeps its durable facts and cannot starve peers.
                attention.append(RuleAttention(rule.schedule_id, _attention_code(error)))
                continue
            scanned += result.periods_scanned
            if result.status == "stopped":
                stopped = True
                break
            if result.status == "created":
                created += 1
            elif result.status == "replayed":
                replayed += 1
            elif result.status == "historical_absent":
                historical += 1
            elif result.status in ("current", "paused", "retired", "definition_inactive"):
                continue
            elif result.status != "scan" or (
                result.periods_scanned == 0 and not result.range_complete
            ):
                attention.append(RuleAttention(rule.schedule_id, "result_unconfirmed"))
                continue
            if not result.range_complete:
                pending.append(rule)
        status = (
            "stopped"
            if stopped
            else "budget_exhausted"
            if pending
            else "attention"
            if attention
            else "complete"
        )
        return FixedRun(
            status,
            tuple(rule.schedule_id for rule in selected),
            created,
            replayed,
            historical,
            scanned,
            tuple(attention),
        )
