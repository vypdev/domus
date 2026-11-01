"""Expansion visits one bounded original frequency period, preserving phase and all selectors."""

from datetime import date, datetime

import pytest

from domus.application.recurrence_ports import NominalExpansion
from domus.domain.errors import InvalidInput
from domus.domain.nominal_recurrence import CalendarNominalExpansion
from domus.domain.recurrence_rule_text import parse_fixed_pattern
from domus.domain.recurrence_rules import NominalDate
from domus.domain.recurrence_time import NominalTime


def dates(raw, start, index):
    pattern = parse_fixed_pattern(raw, NominalDate(start))
    result = CalendarNominalExpansion().period(pattern, index)
    return [s.local for s in result.slots]


def test_monthly_31_omits_invalid_month_without_losing_original_day_anchor():
    assert dates("FREQ=MONTHLY", date(2026, 1, 31), 0) == [date(2026, 1, 31)]
    assert dates("FREQ=MONTHLY", date(2026, 1, 31), 1) == []
    assert dates("FREQ=MONTHLY", date(2026, 1, 31), 2) == [date(2026, 3, 31)]


def test_interval_and_week_start_keep_phase_across_december_and_empty_periods():
    assert dates("FREQ=MONTHLY;INTERVAL=2", date(2025, 12, 31), 1) == []
    assert dates("FREQ=MONTHLY;INTERVAL=2", date(2025, 12, 31), 2) == []
    assert dates("FREQ=MONTHLY;INTERVAL=2", date(2025, 12, 31), 3) == []
    assert dates("FREQ=MONTHLY;INTERVAL=2", date(2025, 12, 31), 4) == [date(2026, 8, 31)]
    assert dates("FREQ=WEEKLY;INTERVAL=2;WKST=SU;BYDAY=SU,MO", date(2026, 1, 4), 1) == [
        date(2026, 1, 18),
        date(2026, 1, 19),
    ]


@pytest.mark.parametrize(
    "raw,start,index,expected",
    [
        ("FREQ=YEARLY", date(2024, 2, 29), 1, []),
        ("FREQ=YEARLY", date(2024, 2, 29), 4, [date(2028, 2, 29)]),
        ("FREQ=YEARLY;BYMONTH=9;BYMONTHDAY=1", date(2026, 9, 1), 1, [date(2027, 9, 1)]),
        ("FREQ=MONTHLY;BYDAY=-1FR", date(2026, 1, 30), 1, [date(2026, 2, 27)]),
        (
            "FREQ=MONTHLY;BYDAY=MO,TU,WE,TH,FR;BYSETPOS=-1",
            date(2026, 1, 30),
            1,
            [date(2026, 2, 27)],
        ),
        ("FREQ=MONTHLY;BYDAY=MO,1TU;BYSETPOS=-1", date(2026, 1, 26), 1, [date(2026, 2, 23)]),
        (
            "FREQ=MONTHLY;BYMONTHDAY=1,-1",
            date(2026, 1, 1),
            1,
            [date(2026, 2, 1), date(2026, 2, 28)],
        ),
        ("FREQ=DAILY;INTERVAL=366", date(2026, 1, 1), 1, [date(2027, 1, 2)]),
        ("FREQ=YEARLY;BYDAY=1MO", date(2026, 1, 5), 1, [date(2027, 1, 4)]),
    ],
)
def test_supported_seasonal_ordinal_negative_and_set_position_forms(raw, start, index, expected):
    assert dates(raw, start, index) == expected


def test_naive_generation_retains_nominal_gap_time_for_explicit_domus_resolution():
    pattern = parse_fixed_pattern("FREQ=DAILY", NominalTime(datetime(2026, 3, 28, 2, 30)))
    result = CalendarNominalExpansion().period(pattern, 1)
    assert result.slots == (NominalTime(datetime(2026, 3, 29, 2, 30)),)


def test_period_rebasing_does_not_apply_count_or_until_as_a_new_per_period_limit():
    assert dates("FREQ=MONTHLY;BYMONTHDAY=1,2;COUNT=1", date(2026, 1, 1), 1) == [
        date(2026, 2, 1),
        date(2026, 2, 2),
    ]


def test_final_supported_calendar_period_is_bounded_and_then_terminal():
    pattern = parse_fixed_pattern(
        "FREQ=YEARLY;BYDAY=MO,TU,WE,TH,FR,SA,SU", NominalDate(date(9999, 1, 1))
    )
    result = CalendarNominalExpansion().period(pattern, 0)
    assert len(result.slots) == 365
    assert result.slots[-1] == NominalDate(date(9999, 12, 31))
    assert CalendarNominalExpansion().period(pattern, 1).terminal is True


def test_a_far_sparse_period_does_not_search_from_the_ancient_start():
    pattern = parse_fixed_pattern(
        "FREQ=YEARLY;BYMONTH=2;BYMONTHDAY=29", NominalDate(date(1972, 2, 29))
    )
    result = CalendarNominalExpansion().period(pattern, 8027)
    assert result.slots == ()
    assert result.terminal is False


@pytest.mark.parametrize("index", [True, -1, 2**63, 1.0, "1", None])
def test_period_index_is_a_strict_bounded_continuation_value(index):
    with pytest.raises(InvalidInput, match="invalid_recurrence_period_index"):
        dates("FREQ=DAILY", date(2026, 1, 1), index)


def test_weekly_default_uses_original_weekday_instead_of_new_period_start():
    assert dates("FREQ=WEEKLY", date(2026, 1, 8), 1) == [date(2026, 1, 15)]
    assert dates("FREQ=WEEKLY;BYDAY=TH,FR", date(1970, 1, 1), 0) == [
        date(1970, 1, 1),
        date(1970, 1, 2),
    ]


@pytest.mark.parametrize("frequency", ["DAILY", "WEEKLY", "MONTHLY", "YEARLY"])
def test_each_frequency_reaches_its_final_date_without_overflow(frequency):
    service: NominalExpansion = CalendarNominalExpansion()
    value = parse_fixed_pattern(f"FREQ={frequency}", NominalDate(date(9999, 12, 31)))
    assert service.period(value, 0).slots == (NominalDate(date(9999, 12, 31)),)
    assert service.period(value, 1).terminal
    assert service.period(value, 2**63 - 1).terminal


def test_mixed_plain_and_ordinal_weekdays_are_unioned_before_global_set_position():
    expected = [date(2026, 2, d) for d in (2, 3, 9, 16, 23)]
    assert dates("FREQ=MONTHLY;BYDAY=MO,1TU", date(2026, 1, 5), 1) == expected
    assert dates("FREQ=MONTHLY;BYDAY=MO,1TU;BYSETPOS=2,-4,366", date(2026, 1, 6), 1) == [
        date(2026, 2, 3)
    ]


def test_set_position_applies_to_whole_period_before_dtstart_trimming():
    assert dates("FREQ=MONTHLY;BYDAY=MO;BYSETPOS=1", date(2026, 1, 6), 0) == []


@pytest.mark.parametrize(
    "raw,start,index,expected",
    [
        ("FREQ=YEARLY;BYDAY=-1MO", date(2026, 12, 28), 1, [date(2027, 12, 27)]),
        ("FREQ=YEARLY;BYDAY=1MO", date(2024, 1, 1), 0, [date(2024, 1, 1)]),
        (
            "FREQ=YEARLY;BYMONTH=1,2;BYDAY=1MO",
            date(2026, 1, 5),
            0,
            [date(2026, 1, 5), date(2026, 2, 2)],
        ),
    ],
)
def test_year_ordinal_scope_differs_from_explicit_month_scope(raw, start, index, expected):
    assert dates(raw, start, index) == expected


def test_impossible_selector_is_bounded_even_when_it_can_never_yield_a_date(monkeypatch):
    from domus.domain import nominal_recurrence as engine

    observed = []
    actual = engine._matches

    def match(*args):
        observed.append(args[0])
        return actual(*args)

    monkeypatch.setattr(engine, "_matches", match)
    assert dates("FREQ=YEARLY;BYMONTH=2;BYMONTHDAY=30", date(2024, 1, 1), 0) == []
    assert len(observed) == 366
