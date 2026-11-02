"""Stored slots must belong to their actual rule, including nominal count and end bounds."""

from dataclasses import replace
from datetime import date, datetime

import pytest
from test_recurrence_records import values

from domus.domain.errors import InvalidInput
from domus.domain.recurrence_planning import PlannedFixedSlot
from domus.domain.recurrence_rules import ByDay, FixedPattern, Frequency, NominalDate, Weekday
from domus.domain.recurrence_time import NominalTime


def dated(pattern, day):
    original = values()[2]
    return replace(
        original,
        schedule=replace(original.schedule, pattern=pattern),
        planned=PlannedFixedSlot(NominalDate(day), None),
    )


@pytest.mark.parametrize(
    "pattern,day",
    [
        (FixedPattern(NominalDate(date(2026, 1, 1)), Frequency.DAILY, count=1), date(2026, 1, 2)),
        (FixedPattern(NominalDate(date(2026, 1, 1)), Frequency.DAILY), date(2025, 12, 31)),
        (
            FixedPattern(NominalDate(date(2026, 1, 1)), Frequency.DAILY, interval=2),
            date(2026, 1, 2),
        ),
        (
            FixedPattern(NominalDate(date(2026, 1, 5)), Frequency.WEEKLY, interval=2),
            date(2026, 1, 12),
        ),
        (FixedPattern(NominalDate(date(2026, 1, 5)), Frequency.WEEKLY), date(2026, 1, 6)),
        (FixedPattern(NominalDate(date(2026, 1, 31)), Frequency.MONTHLY), date(2026, 2, 28)),
        (
            FixedPattern(NominalDate(date(2026, 1, 31)), Frequency.MONTHLY, interval=2),
            date(2026, 2, 28),
        ),
        (FixedPattern(NominalDate(date(2024, 2, 29)), Frequency.YEARLY), date(2026, 2, 28)),
        (
            FixedPattern(NominalDate(date(2024, 2, 29)), Frequency.YEARLY, interval=4),
            date(2028, 3, 1),
        ),
        (
            FixedPattern(
                NominalDate(date(2026, 1, 1)), Frequency.DAILY, until=NominalDate(date(2026, 1, 2))
            ),
            date(2026, 1, 3),
        ),
        (
            FixedPattern(NominalDate(date(2026, 1, 31)), Frequency.MONTHLY, count=2),
            date(2026, 5, 31),
        ),
        (
            FixedPattern(
                NominalDate(date(2026, 1, 1)),
                Frequency.MONTHLY,
                by_day=(ByDay(Weekday.MO),),
                by_set_position=(-1,),
            ),
            date(2026, 1, 5),
        ),
    ],
)
def test_constructor_rejects_same_type_slots_outside_pattern_or_original_end(pattern, day):
    with pytest.raises(InvalidInput, match="invalid_recurrence_slot"):
        dated(pattern, day)


def test_monthly_invalid_dates_do_not_consume_count_and_until_remains_inclusive():
    pattern = FixedPattern(NominalDate(date(2026, 1, 31)), Frequency.MONTHLY, count=2)
    assert dated(pattern, date(2026, 1, 31))
    assert dated(pattern, date(2026, 3, 31))
    assert dated(
        replace(pattern, count=None, until=NominalDate(date(2026, 3, 31))), date(2026, 3, 31)
    )


def test_timed_slot_must_keep_actual_rule_wall_time_and_instant_until():
    original = values(True)[2]
    shifted = replace(
        original.planned.resolved,
        nominal=NominalTime(datetime(2026, 1, 1, 13)),
        resolved_local=datetime(2026, 1, 1, 13),
    )
    with pytest.raises(InvalidInput, match="invalid_recurrence_slot"):
        replace(original, planned=PlannedFixedSlot(shifted.nominal, shifted))
    until = original.planned.resolved.instant_ms
    assert replace(
        original,
        schedule=replace(
            original.schedule, pattern=replace(original.schedule.pattern, until=until)
        ),
    )
    with pytest.raises(InvalidInput, match="invalid_recurrence_slot"):
        replace(
            original,
            schedule=replace(
                original.schedule, pattern=replace(original.schedule.pattern, until=until - 1)
            ),
        )


@pytest.mark.parametrize(
    "frequency,start,target,ordinal",
    [
        (Frequency.DAILY, date(1970, 1, 1), date(2243, 10, 16), 100000),
        (Frequency.MONTHLY, date(2000, 1, 31), date(2800, 1, 31), 5601),
        (Frequency.YEARLY, date(2000, 2, 29), date(2800, 2, 29), 195),
    ],
)
def test_distant_count_uses_calendar_rank_not_elapsed_days(frequency, start, target, ordinal):
    pattern = FixedPattern(NominalDate(start), frequency, count=ordinal)
    assert dated(pattern, target)
    with pytest.raises(InvalidInput, match="invalid_recurrence_slot"):
        dated(replace(pattern, count=ordinal - 1), target)


def test_period_zero_truncation_and_week_start_preserve_count():
    # Friday DTSTART, weekdays in each Monday-based week: first week contributes only Friday.
    pattern = FixedPattern(
        NominalDate(date(2026, 1, 2)),
        Frequency.WEEKLY,
        by_day=(ByDay(Weekday.MO), ByDay(Weekday.FR)),
        count=2,
    )
    assert dated(pattern, date(2026, 1, 5))
    with pytest.raises(InvalidInput, match="invalid_recurrence_slot"):
        dated(pattern, date(2026, 1, 9))


def test_distant_weekly_count_includes_only_actual_selected_month_weekdays():
    from calendar import monthrange

    start = date(2000, 1, 3)
    target = next(date(2800, 2, day) for day in range(1, 8) if date(2800, 2, day).weekday() == 0)
    count = (
        sum(
            1
            for year in range(2000, 2800)
            for day in range(1, monthrange(year, 2)[1] + 1)
            if date(year, 2, day).weekday() == 0
        )
        + 1
    )
    pattern = FixedPattern(
        NominalDate(start),
        Frequency.WEEKLY,
        by_month=(2,),
        by_day=(ByDay(Weekday.MO),),
        count=count,
    )
    assert dated(pattern, target)
    with pytest.raises(InvalidInput, match="invalid_recurrence_slot"):
        dated(replace(pattern, count=count - 1), target)


@pytest.mark.parametrize(
    "frequency,start,target,ordinal",
    [
        (Frequency.MONTHLY, date(2000, 1, 31), date(2800, 1, 31), 2401),
        (Frequency.YEARLY, date(2000, 2, 29), date(4400, 2, 29), 195),
    ],
)
def test_gregorian_count_cycle_keeps_the_original_nonunit_interval_phase(
    frequency, start, target, ordinal
):
    pattern = FixedPattern(NominalDate(start), frequency, interval=3, count=ordinal)
    assert dated(pattern, target)
    with pytest.raises(InvalidInput, match="invalid_recurrence_slot"):
        dated(replace(pattern, count=ordinal - 1), target)
