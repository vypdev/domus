"""The scheduler and preview share nominal dates and the approved time policy."""

from dataclasses import replace
from datetime import date, datetime
from unittest.mock import Mock

import pytest

from domus.application.automation_scheduled_planning import DailyAutomationPlanner
from domus.domain.errors import IntegrationUnavailable, InvalidInput
from domus.domain.fold_policy import FoldPolicy
from domus.domain.recurrence_time import MAX_INSTANT_MS, NominalTime, TimePolicy
from domus.infrastructure.recurrence_time import PinnedRecurrenceTime


def instant(value):
    return round(datetime.fromisoformat(value).timestamp() * 1000)


def policy(zone="UTC", fold=FoldPolicy.FIRST):
    return TimePolicy(zone, PinnedRecurrenceTime().data_identity, fold)


def test_strict_future_boundary_and_complete_nominal_facts():
    planner = DailyAutomationPlanner(PinnedRecurrenceTime())
    before = instant("2026-11-21T07:29:59.999Z")
    value = planner.next("07:30", policy(), before)
    assert value.nominal.local == datetime(2026, 11, 21, 7, 30)
    assert value.instant_ms == before + 1
    assert value.policy == policy()
    assert len(value.zone_digest) == 64
    following = planner.next("07:30", policy(), value.instant_ms)
    assert following.nominal.local == datetime(2026, 11, 22, 7, 30)
    assert following.instant_ms == value.instant_ms + 86_400_000


def test_gap_retains_the_requested_date_instead_of_relabelling_the_wall_time():
    value = DailyAutomationPlanner(PinnedRecurrenceTime()).next(
        "02:30", policy("Europe/Madrid"), instant("2026-03-28T13:00:00Z")
    )
    assert value.nominal.local == datetime(2026, 3, 29, 2, 30)
    assert value.resolved_local == datetime(2026, 3, 29, 3)
    assert value.instant_ms == instant("2026-03-29T01:00:00Z")
    assert value.resolution == "gap_first_valid"


@pytest.mark.parametrize(
    ("fold", "expected", "resolution"),
    [
        (FoldPolicy.FIRST, "2026-10-25T00:30:00Z", "fold_first"),
        (FoldPolicy.SECOND, "2026-10-25T01:30:00Z", "fold_second"),
    ],
)
def test_approved_fold_policy_selects_exactly_one_instant(fold, expected, resolution):
    values = DailyAutomationPlanner(PinnedRecurrenceTime()).upcoming(
        "02:30", policy("Europe/Madrid", fold), instant("2026-10-24T13:00:00Z")
    )
    assert values[0].instant_ms == instant(expected)
    assert values[0].resolution == resolution
    assert values[1].nominal.local.date() == date(2026, 10, 26)
    assert len({value.instant_ms for value in values}) == 5


def test_skipped_local_date_never_reuses_a_resolved_instant():
    values = DailyAutomationPlanner(PinnedRecurrenceTime()).upcoming(
        "00:00", policy("Pacific/Apia"), instant("2011-12-29T12:00:00Z")
    )
    assert [value.nominal.local.date() for value in values] == [
        date(2011, 12, 30),
        date(2012, 1, 1),
        date(2012, 1, 2),
        date(2012, 1, 3),
        date(2012, 1, 4),
    ]
    assert values[0].resolved_local == datetime(2011, 12, 31)


def test_persisted_nominal_frontier_survives_clock_rollback_and_policy_adoption():
    planner = DailyAutomationPlanner(PinnedRecurrenceTime())
    # The clock is now a day behind the last admitted nominal date. Changing
    # zone or fold must not re-admit that date with a different UTC instant.
    after = instant("2026-10-24T12:00:00Z")
    values = planner.upcoming(
        "02:30",
        policy("Europe/Madrid", FoldPolicy.SECOND),
        after,
        after_date=date(2026, 10, 25),
    )
    assert values[0].nominal.local.date() == date(2026, 10, 26)
    assert len(values) == 5
    assert (
        planner.next("02:30", policy("UTC"), after, after_date=date(2026, 10, 25))
        == (planner.upcoming("02:30", policy("UTC"), after, after_date=date(2026, 10, 25))[0])
    )


def test_an_old_frontier_does_not_request_missed_dates_on_startup():
    value = DailyAutomationPlanner(PinnedRecurrenceTime()).next(
        "07:30", policy(), instant("2026-11-21T08:00:00Z"), after_date=date(2026, 1, 1)
    )
    assert value.nominal.local == datetime(2026, 11, 22, 7, 30)


def test_unresolvable_policy_propagates_without_substitution():
    times = Mock(wraps=PinnedRecurrenceTime())
    times.local_at.side_effect = IntegrationUnavailable("approved_policy_unavailable")
    with pytest.raises(IntegrationUnavailable, match="approved_policy_unavailable"):
        DailyAutomationPlanner(times).next("07:30", policy(), 0)
    times.resolve.assert_not_called()


def test_stuck_provider_is_bounded_and_does_not_return_fewer_results():
    times = Mock(wraps=PinnedRecurrenceTime())
    times.resolve.return_value = PinnedRecurrenceTime().resolve(
        NominalTime(datetime(2026, 1, 1, 12)), policy()
    )
    with pytest.raises(IntegrationUnavailable, match="daily_automation_times_unavailable"):
        DailyAutomationPlanner(times).upcoming("12:00", policy(), instant("2026-01-02T00:00Z"))
    assert times.resolve.call_count == 7


@pytest.mark.parametrize("frontier", [None, date.max])
def test_date_overflow_is_a_typed_failure(frontier):
    with pytest.raises(InvalidInput, match="recurrence_time_out_of_range"):
        DailyAutomationPlanner(PinnedRecurrenceTime()).upcoming(
            "00:00", policy(), MAX_INSTANT_MS, after_date=frontier
        )


def test_invalid_wall_time_is_rejected_before_requesting_provider_data():
    times = Mock()
    with pytest.raises(InvalidInput, match="invalid_daily_automation_time"):
        DailyAutomationPlanner(times).next("7:30", policy(), 0)
    times.local_at.assert_not_called()


def test_approved_timing_rejects_changed_provider_bytes_under_the_same_data_label():
    times = PinnedRecurrenceTime()
    approved = DailyAutomationPlanner(times).next("07:30", policy(), 0)
    DailyAutomationPlanner(times).require_approved(approved)
    changed = Mock(wraps=times)
    changed.resolve.return_value = replace(approved, zone_digest="f" * 64)
    with pytest.raises(IntegrationUnavailable, match="daily_automation_approved_time_changed"):
        DailyAutomationPlanner(changed).require_approved(approved)
