"""Side-effect-free bounded planning composes nominal/time ports without claiming persistence."""

from dataclasses import dataclass, replace
from datetime import datetime

from domus.application.recurrence_ports import NominalExpansion, RecurrenceTimes
from domus.domain.errors import Conflict, IntegrationUnavailable, InvalidInput
from domus.domain.recurrence_periods import period_bounds
from domus.domain.recurrence_planning import (
    FixedBatch,
    FixedCursor,
    PlannedFixedSlot,
    StartCheck,
    cursor_binding,
)
from domus.domain.recurrence_rules import FixedPattern, NominalDate, NominalSlot, slot_datetime
from domus.domain.recurrence_time import NominalTime, TimePolicy


def _beyond_end(pattern: FixedPattern, lower: datetime) -> bool:
    if isinstance(pattern.until, NominalDate):
        return lower.date() > pattern.until.local
    if pattern.until is None:
        return False
    # All accepted offsets are strictly within 24 hours. A forward gap never
    # moves a nominal time backwards, so this conservative bound also holds
    # when an entire local date is missing. Integer arithmetic cannot overflow.
    delta = lower - datetime(1970, 1, 1)
    wall_ms = delta.days * 86_400_000 + delta.seconds * 1000
    return wall_ms - 86_400_000 > pattern.until


@dataclass(frozen=True, slots=True)
class FixedRecurrencePlanner:
    nominal: NominalExpansion
    times: RecurrenceTimes

    def check_start(
        self, pattern: FixedPattern, policy: TimePolicy, *, period_limit: int = 64
    ) -> StartCheck:
        batch = self.expand(pattern, policy, slot_limit=1, period_limit=period_limit)
        first = batch.slots[0].nominal if batch.slots else None
        return StartCheck(
            first == pattern.start, first, bool(batch.slots) or batch.cursor.closed, batch.cursor
        )

    def expand(
        self,
        pattern: FixedPattern,
        policy: TimePolicy,
        *,
        cursor: FixedCursor | None = None,
        before: NominalSlot | None = None,
        slot_limit: int = 1000,
        period_limit: int = 64,
    ) -> FixedBatch:
        if (
            type(slot_limit) is not int
            or not 1 <= slot_limit <= 1000
            or type(period_limit) is not int
            or not 1 <= period_limit <= 1000
        ):
            raise InvalidInput("invalid_recurrence_limits")
        if before is not None and type(before) is not type(pattern.start):
            raise InvalidInput("invalid_recurrence_horizon")
        binding = cursor_binding(pattern, policy)
        current = cursor or FixedCursor(binding)
        if current.binding != binding:
            raise Conflict("recurrence_cursor_mismatch")
        if pattern.count is not None and current.nominal_count > pattern.count:
            raise InvalidInput("invalid_recurrence_cursor")
        slots: list[PlannedFixedSlot] = []
        scanned = 0

        def result(complete: bool = False, *, closed: bool = False) -> FixedBatch:
            return FixedBatch(
                tuple(slots),
                replace(current, closed=True) if closed else current,
                scanned,
                complete,
            )

        if current.closed or (pattern.count is not None and current.nominal_count == pattern.count):
            return result(True, closed=True)
        while scanned < period_limit:
            bounds = period_bounds(pattern, current.period_index)
            if bounds is None:
                return result(True, closed=True)
            if _beyond_end(pattern, bounds[0]):
                return result(True, closed=True)
            if before is not None and bounds[0] >= slot_datetime(before):
                return result(True)
            period = self.nominal.period(pattern, current.period_index)
            scanned += 1
            if period.terminal or any(
                type(v) is not type(pattern.start)
                or not bounds[0] <= slot_datetime(v) <= bounds[1]
                or slot_datetime(v) < slot_datetime(pattern.start)
                for v in period.slots
            ):
                raise IntegrationUnavailable("recurrence_expansion_invalid")
            if current.offset > len(period.slots):
                raise InvalidInput("invalid_recurrence_cursor")
            for index in range(current.offset, len(period.slots)):
                candidate = period.slots[index]
                if before is not None and slot_datetime(candidate) >= slot_datetime(before):
                    return result(True)
                resolved = (
                    self.times.resolve(candidate, policy)
                    if isinstance(candidate, NominalTime)
                    else None
                )
                if isinstance(pattern.until, NominalDate):
                    beyond = candidate.local > pattern.until.local
                else:
                    beyond = (
                        pattern.until is not None
                        and resolved is not None
                        and resolved.instant_ms > pattern.until
                    )
                if beyond:
                    return result(True, closed=True)
                if current.nominal_count == 2**63 - 1:
                    raise InvalidInput("invalid_recurrence_cursor")
                slots.append(PlannedFixedSlot(candidate, resolved))
                current = replace(
                    current, offset=index + 1, nominal_count=current.nominal_count + 1
                )
                if pattern.count is not None and current.nominal_count == pattern.count:
                    return result(True, closed=True)
                if len(slots) == slot_limit:
                    return result()
            current = replace(current, period_index=current.period_index + 1, offset=0)
        return result()
