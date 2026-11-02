"""Pattern membership and nominal COUNT rank are independent of stored headers or receipts."""

from datetime import datetime, timedelta
from functools import lru_cache
from math import gcd

from domus.domain.nominal_recurrence import CalendarNominalExpansion
from domus.domain.recurrence_periods import period_bounds
from domus.domain.recurrence_planning import CursorTimeEvidence, FixedCursor, PlannedFixedSlot
from domus.domain.recurrence_rules import FixedPattern, Frequency, NominalDate, slot_datetime


def _period_index(pattern: FixedPattern, planned: PlannedFixedSlot) -> int | None:
    start, target = slot_datetime(pattern.start).date(), slot_datetime(planned.nominal).date()
    if pattern.frequency is Frequency.DAILY:
        distance = (target - start).days
    elif pattern.frequency is Frequency.WEEKLY:
        origin = start - timedelta(days=(start.weekday() - pattern.week_start.number) % 7)
        distance = (target - origin).days // 7
    elif pattern.frequency is Frequency.MONTHLY:
        distance = (target.year - start.year) * 12 + target.month - start.month
    else:
        distance = target.year - start.year
    index, remainder = divmod(distance, pattern.interval)
    return None if remainder else index


@lru_cache(maxsize=4096)
def _block_count(pattern: FixedPattern, first: int, length: int) -> int:
    # Pure bounded memoization changes no proof or result. Each block inspects <=64 periods;
    # eviction merely recomputes the same facts, including when independent readers race.
    expansion = CalendarNominalExpansion()
    return sum(
        len(expansion.period(pattern, index).slots) for index in range(first, first + length)
    )


def _full_periods(pattern: FixedPattern, length: int) -> int:
    blocks, remaining = divmod(length, 64)
    total = sum(_block_count(pattern, 1 + block * 64, 64) for block in range(blocks))
    return total + (_block_count(pattern, 1 + blocks * 64, remaining) if remaining else 0)


def _rank(pattern: FixedPattern, index: int, position: int) -> int:
    if pattern.frequency is Frequency.DAILY and not (
        pattern.by_month or pattern.by_month_day or pattern.by_day or pattern.by_set_position
    ):
        return index + 1
    if index == 0:
        return position + 1
    # Gregorian selectors repeat every400 years. Account for the interval phase explicitly:
    # at most146097 daily dates,20871 weeks,4800 months or400 years are examined, regardless
    # of the target's distance. Period zero alone is truncated by DTSTART and is separate.
    calendar_cycle = {
        Frequency.DAILY: 146097,
        Frequency.WEEKLY: 20871,
        Frequency.MONTHLY: 4800,
        Frequency.YEARLY: 400,
    }[pattern.frequency]
    cycle = calendar_cycle // gcd(calendar_cycle, pattern.interval)
    repeats, remainder = divmod(index - 1, cycle)
    first = len(CalendarNominalExpansion().period(pattern, 0).slots)
    return (
        first
        + (repeats * _full_periods(pattern, cycle) if repeats else 0)
        + _full_periods(pattern, remainder)
        + position
        + 1
    )


def accepts_fixed_slot(pattern: FixedPattern, planned: PlannedFixedSlot) -> bool:
    nominal = planned.nominal
    if type(nominal) is not type(pattern.start) or slot_datetime(nominal) < slot_datetime(
        pattern.start
    ):
        return False
    if isinstance(pattern.until, NominalDate):
        if nominal.local > pattern.until.local:
            return False
    elif pattern.until is not None and (
        planned.resolved is None or planned.resolved.instant_ms > pattern.until
    ):
        return False
    index = _period_index(pattern, planned)
    if index is None:
        return False
    candidates = CalendarNominalExpansion().period(pattern, index).slots
    if nominal not in candidates:
        return False
    return (
        pattern.count is None or _rank(pattern, index, candidates.index(nominal)) <= pattern.count
    )


def accepts_fixed_cursor(
    pattern: FixedPattern, cursor: FixedCursor, evidence: CursorTimeEvidence | None = None
) -> bool:
    """Consumed nominal rank includes truncated DTSTART and empty original periods."""
    bounds = period_bounds(pattern, cursor.period_index)
    if bounds is None and period_bounds(pattern, max(0, cursor.period_index - 1)) is None:
        return False
    candidates = CalendarNominalExpansion().period(pattern, cursor.period_index).slots
    if cursor.offset > len(candidates):
        return False
    if isinstance(pattern.until, NominalDate):
        if cursor.offset:
            if slot_datetime(candidates[cursor.offset - 1]).date() > pattern.until.local:
                return False
        elif cursor.period_index:
            previous_bounds = period_bounds(pattern, cursor.period_index - 1)
            assert previous_bounds is not None  # Valid periods form one contiguous prefix.
            previous = CalendarNominalExpansion().period(pattern, cursor.period_index - 1).slots
            if previous_bounds[0].date() > pattern.until.local or (
                previous and slot_datetime(previous[-1]).date() > pattern.until.local
            ):
                return False
    consumed = _rank(pattern, cursor.period_index, 0) - 1 + cursor.offset
    if consumed != cursor.nominal_count:
        return False
    if type(pattern.until) is int:
        if evidence is None:
            return (
                cursor.period_index == cursor.offset == cursor.nominal_count == 0
                and not cursor.closed
            )
        if evidence.cursor != cursor:
            return False
        last = evidence.last
        if consumed:
            if last is None or last.resolved is None or not accepts_fixed_slot(pattern, last):
                return False
            index = _period_index(pattern, last)
            assert index is not None  # Actual membership was checked above.
            slots = CalendarNominalExpansion().period(pattern, index).slots
            if _rank(pattern, index, slots.index(last.nominal)) != consumed:
                return False
        elif last is not None:
            return False
        if not cursor.closed or bounds is None:
            return evidence.terminal is None
        if evidence.terminal is not None:
            terminal = evidence.terminal
            return (
                cursor.offset < len(candidates)
                and terminal.nominal == candidates[cursor.offset]
                and terminal.resolved is not None
                and terminal.resolved.instant_ms > pattern.until
            )
        delta = bounds[0] - datetime(1970, 1, 1)
        lower_ms = delta.days * 86_400_000 + delta.seconds * 1000
        return cursor.offset == 0 and lower_ms - 86_400_000 > pattern.until
    if not cursor.closed or bounds is None:
        return True
    if pattern.count is not None:
        return consumed == pattern.count
    if isinstance(pattern.until, NominalDate):
        return bounds[0].date() > pattern.until.local or (
            cursor.offset < len(candidates)
            and slot_datetime(candidates[cursor.offset]).date() > pattern.until.local
        )
    return False
