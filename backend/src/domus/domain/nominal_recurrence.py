"""The supported rule subset inspects at most 366 dates of one original frequency period."""

from calendar import isleap, monthrange
from datetime import date, datetime, timedelta

from domus.domain.recurrence_periods import period_bounds
from domus.domain.recurrence_rules import (
    ByDay,
    FixedPattern,
    Frequency,
    NominalDate,
    NominalSlot,
    PeriodCandidates,
    Weekday,
    slot_datetime,
)
from domus.domain.recurrence_time import NominalTime


def _defaults(pattern: FixedPattern) -> tuple[tuple[int, ...], tuple[int, ...], tuple[ByDay, ...]]:
    months, month_days, weekdays = pattern.by_month, pattern.by_month_day, pattern.by_day
    start = slot_datetime(pattern.start)
    if not month_days and not weekdays:
        if pattern.frequency is Frequency.YEARLY:
            months = months or (start.month,)
            month_days = (start.day,)
        elif pattern.frequency is Frequency.MONTHLY:
            month_days = (start.day,)
        elif pattern.frequency is Frequency.WEEKLY:
            weekdays = (ByDay(tuple(Weekday)[start.weekday()]),)
    return months, month_days, weekdays


def _weekday(day: date, selector: ByDay, pattern: FixedPattern) -> bool:
    if day.weekday() != selector.weekday.number:
        return False
    if selector.ordinal is None:
        return True
    if pattern.frequency is Frequency.YEARLY and not pattern.by_month:
        position = (day - date(day.year, 1, 1)).days + 1
        length = 366 if isleap(day.year) else 365
    else:
        position, length = day.day, monthrange(day.year, day.month)[1]
    ordinal = (position - 1) // 7 + 1 if selector.ordinal > 0 else -((length - position) // 7 + 1)
    return selector.ordinal == ordinal


def _matches(
    day: date,
    pattern: FixedPattern,
    months: tuple[int, ...],
    month_days: tuple[int, ...],
    weekdays: tuple[ByDay, ...],
) -> bool:
    if months and day.month not in months:
        return False
    if month_days and not (
        day.day in month_days or day.day - monthrange(day.year, day.month)[1] - 1 in month_days
    ):
        return False
    return not weekdays or any(_weekday(day, selector, pattern) for selector in weekdays)


class CalendarNominalExpansion:
    def period(self, pattern: FixedPattern, index: int) -> PeriodCandidates:
        bounds = period_bounds(pattern, index)
        if bounds is None:
            return PeriodCandidates((), terminal=True)
        lower, upper = bounds
        start = slot_datetime(pattern.start)
        selectors = _defaults(pattern)
        ordered = []
        for offset in range((upper.date() - lower.date()).days + 1):
            day = lower.date() + timedelta(days=offset)
            if _matches(day, pattern, *selectors):
                ordered.append(datetime.combine(day, start.time()))
        if pattern.by_set_position:
            ordered = sorted(
                {
                    ordered[p - 1 if p > 0 else p]
                    for p in pattern.by_set_position
                    if abs(p) <= len(ordered)
                }
            )
        slots: tuple[NominalSlot, ...] = tuple(
            NominalDate(value.date())
            if isinstance(pattern.start, NominalDate)
            else NominalTime(value)
            for value in ordered
            if value >= start
        )
        return PeriodCandidates(slots)
