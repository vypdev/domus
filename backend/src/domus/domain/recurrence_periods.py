"""Frequency periods preserve the original interval phase without traversing prior candidates."""

from calendar import monthrange
from datetime import date, datetime, time, timedelta

from domus.domain.errors import InvalidInput
from domus.domain.recurrence_rules import FixedPattern, Frequency, slot_datetime


def period_bounds(pattern: FixedPattern, index: int) -> tuple[datetime, datetime] | None:
    if type(index) is not int or not 0 <= index <= 2**63 - 1:
        raise InvalidInput("invalid_recurrence_period_index")
    start = slot_datetime(pattern.start).date()
    step = index * pattern.interval
    try:
        if pattern.frequency is Frequency.DAILY:
            lower = upper = start + timedelta(days=step)
        elif pattern.frequency is Frequency.WEEKLY:
            origin = start - timedelta(days=(start.weekday() - pattern.week_start.number) % 7)
            lower = origin + timedelta(days=step * 7)
            upper = min(date.max, lower + timedelta(days=min(6, (date.max - lower).days)))
        elif pattern.frequency is Frequency.MONTHLY:
            month_index = start.year * 12 + start.month - 1 + step
            year, month = month_index // 12, month_index % 12 + 1
            lower = date(year, month, 1)
            upper = date(year, month, monthrange(year, month)[1])
        else:
            lower = date(start.year + step, 1, 1)
            upper = date(lower.year, 12, 31)
        return datetime.combine(lower, time.min), datetime.combine(upper, time.max)
    except OverflowError, ValueError:
        return None
