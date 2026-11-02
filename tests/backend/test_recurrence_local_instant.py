"""An actual performed instant keeps its real fold, independently of future fold preference."""

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from domus.domain.errors import InvalidInput
from domus.domain.recurrence_time import MAX_INSTANT_MS, FoldPolicy, TimePolicy
from domus.infrastructure.recurrence_time import PinnedRecurrenceTime


def instant(value):
    delta = value - datetime(1970, 1, 1, tzinfo=UTC)
    return delta.days * 86_400_000 + delta.seconds * 1000 + delta.microseconds // 1000


@pytest.mark.parametrize("fold", list(FoldPolicy))
def test_actual_fold_is_preserved_even_when_household_prefers_the_other_appearance(fold):
    times = PinnedRecurrenceTime()
    policy = TimePolicy("Europe/Madrid", times.data_identity, fold)
    first = times.local_at(instant(datetime(2026, 10, 25, 0, 30, tzinfo=UTC)), policy)
    second = times.local_at(instant(datetime(2026, 10, 25, 1, 30, tzinfo=UTC)), policy)
    assert first.local == second.local == datetime(2026, 10, 25, 2, 30)
    assert first.offset_seconds == 7200 and second.offset_seconds == 3600
    assert first.policy == second.policy == policy
    assert first.instant_ms + 3_600_000 == second.instant_ms
    assert first.local.fold == second.local.fold == 0
    assert first.zone_digest == second.zone_digest


@pytest.mark.parametrize("value", [True, -1, MAX_INSTANT_MS + 1, None])
def test_local_at_rejects_noninstant_or_out_of_range_input(value):
    times = PinnedRecurrenceTime()
    with pytest.raises(InvalidInput, match="recurrence_time_out_of_range"):
        times.local_at(value, TimePolicy("UTC", times.data_identity))


def test_actual_local_overflow_is_not_clamped_or_wrapped():
    times = PinnedRecurrenceTime()
    with pytest.raises(InvalidInput, match="recurrence_time_out_of_range"):
        times.local_at(MAX_INSTANT_MS, TimePolicy("Europe/Madrid", times.data_identity))


@pytest.mark.parametrize(
    "change",
    [
        {"instant_ms": True},
        {"instant_ms": -1},
        {"instant_ms": MAX_INSTANT_MS + 1},
        {"local": None},
        {"local": datetime(2026, 1, 1, tzinfo=UTC)},
        {"local": datetime(2026, 1, 1, microsecond=1)},
        {"local": datetime(2026, 1, 1, fold=1)},
        {"offset_seconds": True},
        {"offset_seconds": 86400},
        {"policy": None},
        {"zone_digest": "not-a-hash"},
        {"instant_ms": 0},
    ],
)
def test_local_facts_require_exact_integer_utc_arithmetic_and_closed_types(change):
    times = PinnedRecurrenceTime()
    value = times.local_at(
        instant(datetime(2026, 1, 1, tzinfo=UTC)), TimePolicy("UTC", times.data_identity)
    )
    with pytest.raises(InvalidInput):
        replace(value, **change)
