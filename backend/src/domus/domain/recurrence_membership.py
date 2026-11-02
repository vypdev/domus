"""Pattern membership and nominal COUNT rank are independent of stored headers or receipts."""

from datetime import timedelta
from functools import lru_cache
from math import gcd

from domus.domain.nominal_recurrence import CalendarNominalExpansion
from domus.domain.recurrence_planning import PlannedFixedSlot
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
