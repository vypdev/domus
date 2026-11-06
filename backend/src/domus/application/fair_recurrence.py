"""Durable bounded rule admission and fair round-robin steps; no thread or calendar claim."""

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from domus.application.fixed_materialization import FixedMaintenance, MaintenanceScope
from domus.application.ports import Clock, Transactions, UnitOfWork
from domus.application.recurrence_ports import RecurrenceTimes
from domus.application.recurrence_sources import RecurrenceSourceObservations
from domus.application.relative_lifecycle import RelativeLifecycle
from domus.application.relative_materialization import RelativeMaintenance, RelativeStep
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
from domus.domain.relative_recurrence import RelativeSchedule


@dataclass(frozen=True, slots=True)
class RunLimits:
    max_definitions: int = 50
    max_slots: int = 1000
    max_periods: int = 4096
    horizon_days: int = 60
    max_sources: int = 4096

    def __post_init__(self) -> None:
        for value, lower, upper in (
            (self.max_definitions, 1, 50),
            (self.max_slots, 1, 1000),
            (self.max_periods, 1, 64000),
            (self.horizon_days, 7, 366),
            (self.max_sources, 1, 64000),
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
    source_rows_examined: int = 0
    source_scan_complete: bool = True
    relative_slots_observed: int = 0

    @property
    def attention_count(self) -> int:
        return len(self.attention_items)


@dataclass(frozen=True, slots=True)
class RelativeRunServices:
    initial: RelativeMaintenance
    sources: RecurrenceSourceObservations
    lifecycle: RelativeLifecycle

    def step(
        self, rule: RelativeSchedule, should_continue: Callable[[], bool]
    ) -> tuple[RelativeStep, bool]:
        initial = self.initial.initial(
            rule.schedule_id, expected_schedule=rule, should_continue=should_continue
        )
        if initial.status not in ("current", "paused", "retired", "definition_inactive"):
            return initial, False
        with self.initial.transactions.read() as unit:
            self.initial.scope.require(unit)
            event_key = unit.recurrence.next_relative_source(rule.household_id, rule.schedule_id)
        if event_key is None:
            return initial, False
        return self.lifecycle.consume(
            rule.schedule_id, event_key, should_continue=should_continue
        ), True


@dataclass
class FairFixedRunner:
    transactions: Transactions
    scope: MaintenanceScope
    stepper: FixedMaintenance
    times: RecurrenceTimes
    clock: Clock
    limits: RunLimits = RunLimits()
    relative: RelativeRunServices | None = None

    def _rules(
        self, unit: UnitOfWork, limit: int, after: str | None = None
    ) -> tuple[FixedSchedule | RelativeSchedule, ...]:
        home = self.scope.household_id
        if self.relative is None:
            return unit.recurrence.schedules(
                home, limit=limit, after=after, state=ScheduleState.ACTIVE
            )
        return unit.recurrence.maintenance_schedules(home, limit=limit, after=after)

    def _scan_sources(self, should_continue: Callable[[], bool]) -> tuple[int, bool]:
        if self.relative is None:
            return 0, True
        examined = 0
        while examined < self.limits.max_sources and should_continue():
            try:
                page = self.relative.sources.ingest(
                    limit=min(100, self.limits.max_sources - examined)
                )
            except Forbidden:
                raise
            except DomusError:
                return examined, False
            examined += page.source_rows_examined
            if page.complete:
                return examined, True
        return examined, False

    def _select(self) -> tuple[tuple[FixedSchedule | RelativeSchedule, ...], int] | None:
        with self.transactions.read() as unit:
            if self.scope.household(unit) is None:
                return None
            home = self.scope.household_id
            frontier = unit.recurrence.frontier(home)
            after = None if frontier is None else frontier.after_schedule_id
            selected = self._rules(unit, self.limits.max_definitions, after)
            if after is not None and len(selected) < self.limits.max_definitions:
                head = self._rules(unit, self.limits.max_definitions - len(selected))
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
        if self.relative is not None:
            with self.transactions.read() as unit:
                if self.scope.household(unit) is None:
                    return FixedRun("unconfigured")
        source_rows, source_complete = self._scan_sources(should_continue)
        if self.relative is not None and not should_continue():
            return FixedRun(
                "stopped", source_rows_examined=source_rows, source_scan_complete=source_complete
            )
        claim = self._select()
        if claim is None:
            return FixedRun("unconfigured")
        selected, started_at = claim
        pending = deque(selected)
        horizons: dict[str, NominalSlot] = {}
        admitted: set[str] = set()
        created = replayed = historical = scanned = 0
        attention: list[RuleAttention] = []
        stopped = deferred_periods = False
        relative_slots = 0
        while pending and created + replayed + historical + relative_slots < self.limits.max_slots:
            if not should_continue():
                stopped = True
                break
            rule = pending.popleft()
            if isinstance(rule, FixedSchedule) and scanned >= self.limits.max_periods:
                deferred_periods = True
                continue
            try:
                # Reserve each actually attempted rule before provider I/O. Reserving an entire
                # unvisited window could starve its later rules after repeated interrupted runs.
                if rule.schedule_id not in admitted:
                    self._admit(rule.schedule_id)
                    admitted.add(rule.schedule_id)
                if isinstance(rule, RelativeSchedule):
                    assert self.relative is not None
                    step, observed = self.relative.step(rule, should_continue)
                    if step.status == "stopped":
                        stopped = True
                        break
                    if observed:
                        relative_slots += int(step.occurrence_id is not None)
                    elif step.status == "created":
                        created += 1
                    elif step.status == "replayed":
                        replayed += 1
                    elif step.status == "historical_absent":
                        historical += 1
                    if step.status in ("review", "initial_review_required"):
                        attention.append(RuleAttention(rule.schedule_id, step.status))
                    continue
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
        relative_pending = False
        if self.relative is not None and not stopped:
            with self.transactions.read() as unit:
                self.scope.require(unit)
                relative_pending = unit.recurrence.relative_sources_pending(self.scope.household_id)
        status = (
            "stopped"
            if stopped
            else "budget_exhausted"
            if pending or deferred_periods
            else "attention"
            if attention
            else "source_pending"
            if relative_pending or not source_complete
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
            source_rows,
            source_complete,
            relative_slots,
        )
