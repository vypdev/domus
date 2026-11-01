"""Bounded planning resumes exact nominal progress; it never authenticates or persists work."""

from dataclasses import replace
from datetime import date, datetime

import pytest

from domus.application.fixed_recurrence import FixedRecurrencePlanner
from domus.domain.errors import Conflict, IntegrationUnavailable, InvalidInput
from domus.domain.nominal_recurrence import CalendarNominalExpansion
from domus.domain.recurrence_planning import FixedCursor, PlannedFixedSlot
from domus.domain.recurrence_rule_text import parse_fixed_pattern
from domus.domain.recurrence_rules import NominalDate, PeriodCandidates
from domus.domain.recurrence_time import FoldPolicy, NominalTime, TimePolicy
from domus.infrastructure.recurrence_time import TIMEZONE_DATA_IDENTITY, PinnedRecurrenceTime


def planner():
    return FixedRecurrencePlanner(CalendarNominalExpansion(), PinnedRecurrenceTime())


def policy(zone="Europe/Madrid"):
    return TimePolicy(zone, TIMEZONE_DATA_IDENTITY)


def pattern(raw="FREQ=DAILY", start=None):
    return parse_fixed_pattern(raw, start or NominalDate(date(2026, 1, 1)))


def test_batch_continues_inside_the_original_period_without_losing_count_or_dates():
    value = pattern("FREQ=MONTHLY;BYMONTHDAY=1,2;COUNT=3")
    first = planner().expand(value, policy(), slot_limit=1)
    assert [s.nominal.local for s in first.slots] == [date(2026, 1, 1)]
    assert (first.cursor.period_index, first.cursor.offset, first.cursor.nominal_count) == (0, 1, 1)
    assert not first.range_complete
    second = planner().expand(value, policy(), cursor=first.cursor, slot_limit=2)
    assert [s.nominal.local for s in second.slots] == [date(2026, 1, 2), date(2026, 2, 1)]
    assert second.cursor.closed and second.range_complete
    assert second.cursor.nominal_count == 3
    assert planner().expand(value, policy(), cursor=second.cursor).slots == ()


def test_date_only_horizon_and_until_never_invent_utc_midnight_or_shift_the_date():
    value = pattern("FREQ=DAILY;UNTIL=20260103")
    first = planner().expand(value, policy("Pacific/Apia"), before=NominalDate(date(2026, 1, 3)))
    assert [s.nominal.local for s in first.slots] == [date(2026, 1, 1), date(2026, 1, 2)]
    assert all(s.resolved is None for s in first.slots)
    assert first.range_complete and not first.cursor.closed
    last = planner().expand(value, policy("Pacific/Apia"), cursor=first.cursor, before=None)
    assert [s.nominal.local for s in last.slots] == [date(2026, 1, 3)]
    assert last.cursor.closed


def test_instant_until_is_inclusive_after_explicit_gap_resolution():
    value = pattern("FREQ=DAILY;UNTIL=20260329T010000Z", NominalTime(datetime(2026, 3, 28, 2, 30)))
    batch = planner().expand(value, policy())
    assert len(batch.slots) == 2
    assert batch.slots[-1].nominal.local == datetime(2026, 3, 29, 2, 30)
    assert batch.slots[-1].resolved.resolved_local == datetime(2026, 3, 29, 3)
    assert batch.cursor.closed


def test_empty_impossible_periods_exhaust_scan_budget_without_claiming_no_future_work():
    batch = planner().expand(
        pattern("FREQ=YEARLY;BYMONTH=2;BYMONTHDAY=30"), policy(), period_limit=3
    )
    assert batch.slots == ()
    assert batch.periods_scanned == 3
    assert batch.cursor.period_index == 3
    assert not batch.range_complete and not batch.cursor.closed


def test_empty_periods_after_the_horizon_do_not_force_traversal_to_year9999():
    batch = planner().expand(
        pattern("FREQ=YEARLY;BYMONTH=2;BYMONTHDAY=30"),
        policy(),
        before=NominalDate(date(2027, 1, 1)),
    )
    assert batch.slots == () and batch.range_complete
    assert batch.periods_scanned == 1
    assert batch.cursor.period_index == 1


def test_start_check_reports_mismatch_and_first_permitted_candidate_without_rewriting():
    value = pattern("FREQ=MONTHLY;BYDAY=MO;BYSETPOS=1", NominalDate(date(2026, 1, 6)))
    check = planner().check_start(value, policy())
    assert not check.matches
    assert check.first_permitted == NominalDate(date(2026, 2, 2))
    assert value.start == NominalDate(date(2026, 1, 6))
    assert check.search_complete
    assert planner().check_start(pattern(), policy()).matches


def test_start_check_distinguishes_exhausted_rule_from_bounded_incomplete_search():
    impossible = pattern("FREQ=YEARLY;BYMONTH=2;BYMONTHDAY=30")
    check = planner().check_start(impossible, policy(), period_limit=2)
    assert not check.matches and check.first_permitted is None and not check.search_complete
    ended = planner().check_start(
        pattern("FREQ=DAILY;UNTIL=20260101T000000Z", NominalTime(datetime(2026, 1, 1, 2))),
        policy("UTC"),
    )
    assert ended.first_permitted is None and ended.search_complete


def test_cursor_binding_rejects_pattern_or_time_policy_reinterpretation():
    value = pattern()
    first = planner().expand(value, policy(), slot_limit=1)
    for changed, changed_policy in [
        (pattern("FREQ=DAILY;INTERVAL=2"), policy()),
        (value, replace(policy(), revision=2)),
        (value, replace(policy(), repeated_time=FoldPolicy.SECOND)),
    ]:
        with pytest.raises(Conflict, match="recurrence_cursor_mismatch"):
            planner().expand(changed, changed_policy, cursor=first.cursor)


@pytest.mark.parametrize(
    "field,value",
    [
        ("slot_limit", 0),
        ("slot_limit", True),
        ("slot_limit", 1001),
        ("period_limit", 0),
        ("period_limit", True),
        ("period_limit", 1001),
    ],
)
def test_limits_are_exact_bounded_work_controls(field, value):
    with pytest.raises(InvalidInput, match="invalid_recurrence_limits"):
        planner().expand(pattern(), policy(), **{field: value})


def test_horizon_kind_must_match_rule_without_coercing_date_or_instant():
    with pytest.raises(InvalidInput, match="invalid_recurrence_horizon"):
        planner().expand(pattern(), policy(), before=NominalTime(datetime(2026, 1, 3)))


@pytest.mark.parametrize(
    "field,value",
    [
        ("binding", "wrong"),
        ("period_index", -1),
        ("period_index", True),
        ("period_index", 2**63),
        ("offset", -1),
        ("offset", 367),
        ("offset", True),
        ("nominal_count", -1),
        ("nominal_count", True),
        ("nominal_count", 2**63),
        ("closed", 1),
    ],
)
def test_progress_record_is_strict_and_cannot_hide_invalid_bounds(field, value):
    base = FixedCursor("a" * 64)
    with pytest.raises(InvalidInput, match="invalid_recurrence_cursor"):
        replace(base, **{field: value})


def test_progress_cannot_claim_offsets_or_count_outside_the_original_pattern():
    value = pattern("FREQ=DAILY;COUNT=2")
    first = planner().expand(value, policy(), slot_limit=1)
    for cursor in (replace(first.cursor, offset=2), replace(first.cursor, nominal_count=3)):
        with pytest.raises(InvalidInput, match="invalid_recurrence_cursor"):
            planner().expand(value, policy(), cursor=cursor)


def test_equivalent_selector_order_has_same_binding_and_changed_start_has_another():
    first = planner().expand(pattern("FREQ=MONTHLY;BYMONTHDAY=1,2"), policy(), slot_limit=1)
    assert planner().expand(
        pattern("BYMONTHDAY=2,1;FREQ=MONTHLY"), policy(), cursor=first.cursor, slot_limit=1
    ).slots[0].nominal == NominalDate(date(2026, 1, 2))


def test_final_calendar_slot_is_retained_before_terminal_progress():
    value = pattern(start=NominalDate(date(9999, 12, 31)))
    batch = planner().expand(value, policy())
    assert len(batch.slots) == 1 and batch.cursor.closed and batch.range_complete


@pytest.mark.parametrize(
    "period",
    [
        PeriodCandidates((), True),
        PeriodCandidates((NominalTime(datetime(2026, 1, 1)),)),
        PeriodCandidates((NominalDate(date(2025, 12, 31)),)),
        PeriodCandidates((NominalDate(date(2026, 1, 2)),)),
    ],
)
def test_inconsistent_nominal_adapter_facts_cannot_advance_planning(period):
    class WrongPeriod:
        def period(self, *_):
            return period

    service = FixedRecurrencePlanner(WrongPeriod(), PinnedRecurrenceTime())
    with pytest.raises(IntegrationUnavailable, match="recurrence_expansion_invalid"):
        service.expand(pattern(), policy())


def test_cursor_count_overflow_and_closed_count_are_explicit_without_wraparound():
    value = pattern()
    first = planner().expand(value, policy(), slot_limit=1)
    with pytest.raises(InvalidInput, match="invalid_recurrence_cursor"):
        planner().expand(
            value, policy(), cursor=replace(first.cursor, offset=0, nominal_count=2**63 - 1)
        )
    limited = pattern("FREQ=DAILY;COUNT=1")
    closed = planner().expand(limited, policy()).cursor
    assert planner().expand(limited, policy(), cursor=replace(closed, closed=False)).cursor.closed


@pytest.mark.parametrize(
    "nominal,resolved",
    [
        (None, None),
        (NominalTime(datetime(2026, 1, 1)), None),
        (NominalDate(date(2026, 1, 1)), object()),
    ],
)
def test_planned_slot_never_turns_a_date_into_an_instant_or_loses_timed_resolution(
    nominal, resolved
):
    with pytest.raises(InvalidInput, match="invalid_recurrence_slot"):
        PlannedFixedSlot(nominal, resolved)


def test_timed_slot_resolution_cannot_belong_to_a_different_nominal_time():
    resolved = PinnedRecurrenceTime().resolve(NominalTime(datetime(2026, 1, 1)), policy())
    with pytest.raises(InvalidInput, match="invalid_recurrence_slot"):
        PlannedFixedSlot(NominalTime(datetime(2026, 1, 2)), resolved)


def test_date_until_is_inclusive_inside_one_multi_slot_period():
    batch = planner().expand(pattern("FREQ=MONTHLY;BYMONTHDAY=1,2,3;UNTIL=20260102"), policy())
    assert [s.nominal.local for s in batch.slots] == [date(2026, 1, 1), date(2026, 1, 2)]
    assert batch.cursor.closed


@pytest.mark.parametrize("timed", [True, False])
def test_expired_end_closes_an_impossible_pattern_without_searching_future_years(timed):
    value = pattern(
        "FREQ=YEARLY;BYMONTH=2;BYMONTHDAY=30;UNTIL="
        + ("20260102T000000Z" if timed else "20260102"),
        NominalTime(datetime(2026, 1, 1)) if timed else None,
    )
    batch = planner().expand(value, policy())
    assert batch.slots == () and batch.cursor.closed and batch.periods_scanned == 1


def test_changed_original_start_rejects_the_old_continuation():
    first = planner().expand(pattern(), policy(), slot_limit=1)
    with pytest.raises(Conflict, match="recurrence_cursor_mismatch"):
        planner().expand(
            pattern(start=NominalDate(date(2026, 1, 2))), policy(), cursor=first.cursor
        )


def test_horizon_inside_a_multi_slot_period_preserves_the_unconsumed_slot():
    value = pattern("FREQ=MONTHLY;BYMONTHDAY=1,2,3")
    batch = planner().expand(value, policy(), before=NominalDate(date(2026, 1, 2)))
    assert [s.nominal.local for s in batch.slots] == [date(2026, 1, 1)]
    assert batch.range_complete and not batch.cursor.closed
    resumed = planner().expand(value, policy(), cursor=batch.cursor, slot_limit=1)
    assert resumed.slots[0].nominal == NominalDate(date(2026, 1, 2))
