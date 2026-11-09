"""Calendar values reject open ranges and untyped filter choices."""

from datetime import date, datetime

import pytest

from domus.domain.calendar_values import (
    CalendarFilters,
    CalendarKind,
    CalendarRange,
    CalendarTiming,
)
from domus.domain.errors import InvalidInput
from domus.domain.task_values import OccurrenceState, Priority


@pytest.mark.parametrize(
    "start,end",
    [
        (datetime(2026, 1, 1), date(2026, 1, 2)),
        (date(2026, 1, 1), datetime(2026, 1, 2)),
        (date(1969, 12, 31), date(1970, 1, 2)),
        (date(2026, 1, 1), date(2026, 1, 1)),
        (date(2026, 1, 1), date(2028, 1, 1)),
    ],
)
def test_calendar_range_requires_bounded_half_open_local_dates(start, end):
    with pytest.raises(InvalidInput, match="invalid_calendar_range"):
        CalendarRange(start, end)


def test_calendar_filter_documents_bind_every_exact_selector():
    filters = CalendarFilters(
        CalendarKind.PERFORMED,
        CalendarTiming.RELATIVE,
        OccurrenceState.COMPLETED,
        Priority.HIGH,
        "person-1",
        "garden",
    )
    assert filters.document().decode() == {
        "kind": "performed",
        "timing": "completion_relative",
        "state": "completed",
        "priority": "high",
        "member_id": "person-1",
        "category": "garden",
    }
    with pytest.raises(InvalidInput, match="invalid_calendar_filter"):
        CalendarFilters(kind="approval")
