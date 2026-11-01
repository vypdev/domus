"""Closed rule values reject permissive provider behavior before expansion or storage."""

from dataclasses import replace
from datetime import UTC, date, datetime

import pytest

from domus.domain.errors import InvalidInput
from domus.domain.recurrence_rule_text import parse_fixed_pattern
from domus.domain.recurrence_rules import (
    ByDay,
    FixedPattern,
    Frequency,
    NominalDate,
    PeriodCandidates,
    Weekday,
)
from domus.domain.recurrence_time import NominalTime


def pattern(**changes):
    return replace(FixedPattern(NominalDate(date(2026, 1, 1)), Frequency.DAILY), **changes)


def test_explicit_defaults_and_canonical_selector_order_preserve_original_anchor():
    value = pattern(
        frequency=Frequency.MONTHLY,
        by_month=(12, 1),
        by_day=(ByDay(Weekday.FR, -1), ByDay(Weekday.MO)),
    )
    assert value.interval == 1
    assert value.week_start is Weekday.MO
    assert value.by_month == (1, 12)
    assert value.by_day == (ByDay(Weekday.MO), ByDay(Weekday.FR, -1))


@pytest.mark.parametrize("value", [None, "2026-01-01", date(1969, 12, 31), datetime(2026, 1, 1)])
def test_date_only_is_tagged_strict_and_never_an_implicit_midnight_instant(value):
    with pytest.raises(InvalidInput, match="invalid_recurrence_date"):
        NominalDate(value)


@pytest.mark.parametrize(
    "weekday,ordinal",
    [
        ("MO", None),
        (0, None),
        (None, None),
        (Weekday.MO, 0),
        (Weekday.MO, True),
        (Weekday.MO, 6),
        (Weekday.MO, -6),
    ],
)
def test_weekday_and_nonzero_bounded_ordinal_are_closed_values(weekday, ordinal):
    with pytest.raises(InvalidInput, match="invalid_recurrence_weekday"):
        ByDay(weekday, ordinal)


@pytest.mark.parametrize(
    "changes",
    [
        {"start": date(2026, 1, 1)},
        {"start": None},
        {"frequency": "DAILY"},
        {"interval": True},
        {"interval": 0},
        {"interval": 367},
        {"week_start": "MO"},
        {"by_day": []},
        {"by_day": ("MO",)},
        {"by_day": (ByDay(Weekday.MO),) * 2},
        {"by_day": tuple(ByDay(Weekday.MO, n) for n in (-5, -4, -3, -2, -1, 1, 2, 3, 4, 5)) * 4},
        {"by_month": (True,)},
        {"by_month": (0,)},
        {"by_month": (13,)},
        {"by_month": [1]},
        {"by_month": (1, 1)},
        {"by_month": tuple(range(1, 14))},
        {"by_month_day": (0,)},
        {"by_month_day": (32,)},
        {"by_month_day": (-32,)},
        {"by_month_day": (1, 1)},
        {"by_month_day": [1]},
        {"by_month_day": tuple(range(-31, 33))},
        {"by_set_position": (0,)},
        {"by_set_position": (367,)},
        {"by_set_position": (-367,)},
        {"by_set_position": tuple(range(1, 34))},
        {"by_set_position": (1,)},
        {"count": True},
        {"count": 0},
        {"count": 100001},
        {"count": 1.0},
        {"count": 1, "until": NominalDate(date(2026, 2, 1))},
        {"until": NominalDate(date(2025, 12, 31))},
        {"until": 1770000000000},
        {"frequency": Frequency.WEEKLY, "by_month_day": (1,)},
        {"frequency": Frequency.DAILY, "by_day": (ByDay(Weekday.MO, 1),)},
        {"frequency": Frequency.WEEKLY, "by_day": (ByDay(Weekday.MO, -1),)},
        {"start": NominalTime(datetime(2026, 1, 1, 0, 0, 1))},
        {"start": NominalTime(datetime(2026, 1, 1, microsecond=1000))},
    ],
)
def test_invalid_or_contradictory_pattern_never_reaches_provider(changes):
    with pytest.raises(InvalidInput):
        pattern(**changes)


@pytest.mark.parametrize(
    "until", [True, -1, 253402300800000, "20260101", NominalDate(date(2026, 2, 1))]
)
def test_timed_until_is_an_explicit_bounded_utc_instant(until):
    with pytest.raises(InvalidInput):
        pattern(start=NominalTime(datetime(2026, 1, 1)), until=until)


@pytest.mark.parametrize("frequency", [Frequency.MONTHLY, Frequency.YEARLY])
def test_permitted_ordinal_and_set_position_combinations_are_retained(frequency):
    value = pattern(frequency=frequency, by_day=(ByDay(Weekday.FR, -1),), by_set_position=(-1,))
    assert value.by_day[0].ordinal == -1


def test_strict_rule_parser_supports_all_declared_parts_without_provider_defaults():
    value = parse_fixed_pattern(
        "RRULE:FREQ=YEARLY;INTERVAL=2;WKST=SU;BYMONTH=12,1;BYDAY=-1FR,+1MO;BYMONTHDAY=-1,1;BYSETPOS=-1;COUNT=10",
        NominalDate(date(2026, 1, 1)),
    )
    assert value == pattern(
        frequency=Frequency.YEARLY,
        interval=2,
        week_start=Weekday.SU,
        by_month=(1, 12),
        by_day=(ByDay(Weekday.MO, 1), ByDay(Weekday.FR, -1)),
        by_month_day=(-1, 1),
        by_set_position=(-1,),
        count=10,
    )
    assert parse_fixed_pattern("FREQ=DAILY", value.start).interval == 1


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "",
        "x" * 2049,
        "FREQ=DAILY\n",
        "FREQ=daily",
        "freq=DAILY",
        "FREQ=DAILY;",
        "FREQ=DAILY;;COUNT=2",
        "FREQ=DAILY;FREQ=WEEKLY",
        "FREQ=DAILY;COUNT=2;COUNT=3",
        "COUNT=2",
        "FREQ=DAILY=EXTRA",
        "FREQ=HOURLY",
        "FREQ=DAILY;BYHOUR=2",
        "FREQ=DAILY;BYSECOND=1",
        "FREQ=YEARLY;BYWEEKNO=1",
        "FREQ=DAILY;X-EXTRA=1",
        "FREQ=DAILY;COUNT=2;UNTIL=20260103",
        "FREQ=DAILY;INTERVAL=1.0",
        "FREQ=DAILY;INTERVAL=1234567",
        "FREQ=DAILY;BYMONTH=01,1",
        "FREQ=DAILY;BYMONTH=",
        "FREQ=MONTHLY;BYDAY=0MO",
        "FREQ=MONTHLY;BYDAY=6MO",
        "FREQ=MONTHLY;BYDAY=MO,MO",
        "FREQ=DAILY;UNTIL=20260230",
        "FREQ=DAILY;UNTIL=20260101T000000",
        "FREQ=DAILY;UNTIL=20260101T000060Z",
        "FREQ=DAILY;UNTIL=00000101",
        "FREQ=DAILY;COUNT=١",
        "FREQ=DAILY;COUNT=+1",
        "FREQ=DAILY;COUNT=-1",
        "FREQ=DAILY;BYMONTHDAY=1,",
        "FREQ=DAILY;BYMONTH=１",
        "FREQ=DAILY\ud800",
    ],
)
def test_raw_rule_rejects_duplicates_unsupported_parts_malformed_dates_and_unbounded_numbers(raw):
    with pytest.raises(InvalidInput, match="invalid_recurrence"):
        parse_fixed_pattern(raw, NominalDate(date(2026, 1, 1)))


def test_utc_until_and_date_only_until_remain_different_tagged_values():
    date_value = parse_fixed_pattern("FREQ=DAILY;UNTIL=20260102", NominalDate(date(2026, 1, 1)))
    timed = parse_fixed_pattern(
        "FREQ=DAILY;UNTIL=20260102T000000Z", NominalTime(datetime(2026, 1, 1))
    )
    assert date_value.until == NominalDate(date(2026, 1, 2))
    assert timed.until == int(datetime(2026, 1, 2, tzinfo=UTC).timestamp() * 1000)


@pytest.mark.parametrize(
    "slots,terminal",
    [
        ([], False),
        ((None,), False),
        ((NominalDate(date(2026, 1, 1)),), True),
        ((), 1),
        ((NominalDate(date(2026, 1, 1)),) * 367, False),
        ((NominalDate(date(2026, 1, 1)), NominalDate(date(2026, 1, 1))), False),
        ((NominalDate(date(2026, 1, 2)), NominalDate(date(2026, 1, 1))), False),
        ((NominalDate(date(2026, 1, 1)), NominalTime(datetime(2026, 1, 2))), False),
    ],
)
def test_period_facts_are_typed_sorted_unique_bounded_and_cannot_claim_terminal_work(
    slots, terminal
):
    with pytest.raises(InvalidInput, match="invalid_recurrence_period"):
        PeriodCandidates(slots, terminal)
