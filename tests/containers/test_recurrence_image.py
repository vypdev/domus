"""Both real CPU images must execute the newly packaged recurrence and pinned timezone code."""

from test_app_image import docker
from test_app_image import image as image


def test_current_image_executes_recurrence_planning_and_closed_record_codecs(image):
    result = docker(
        "run",
        "--rm",
        "--network",
        "none",
        "--user",
        "65532:65532",
        "--entrypoint",
        "/app/.venv/bin/python",
        image,
        "-c",
        """
from datetime import datetime
from domus.application.fixed_recurrence import FixedRecurrencePlanner
from domus.domain.nominal_recurrence import CalendarNominalExpansion
from domus.domain.recurrence_records import FixedProgress, FixedSchedule, ScheduledSlot
from domus.domain.recurrence_rule_text import parse_fixed_pattern
from domus.domain.recurrence_time import NominalTime, TimePolicy, TimeResolution
from domus.domain.storage import Installation
from domus.infrastructure.recurrence_time import PinnedRecurrenceTime, TIMEZONE_DATA_IDENTITY
from domus.infrastructure.sqlite import SCHEMA_VERSION
from domus.infrastructure.sqlite_recurrence_records import (
    schedule_document, read_schedule, progress_document, read_progress, slot_document, read_slot,
)
assert SCHEMA_VERSION == 8
policy = TimePolicy('Europe/Madrid', TIMEZONE_DATA_IDENTITY)
pattern = parse_fixed_pattern('FREQ=DAILY;COUNT=2', NominalTime(datetime(2026, 3, 29, 2, 30)))
times = PinnedRecurrenceTime()
planned = FixedRecurrencePlanner(CalendarNominalExpansion(), times).expand(pattern, policy)
assert len(planned.slots) == 2 and planned.range_complete and planned.cursor.closed
first = planned.slots[0]
assert first.resolved.resolved_local == datetime(2026, 3, 29, 3)
assert first.resolved.resolution is TimeResolution.GAP_FIRST_VALID
rule = FixedSchedule('rule', 'home', 'definition', pattern, policy, 100)
progress = FixedProgress('rule', 'home', 1, planned.cursor, range_complete=True)
installation = Installation('00000000-0000-0000-0000-000000000001', 'edge')
slot = ScheduledSlot(installation, rule, first, 'work', 100)
assert read_schedule(schedule_document(rule).encoded) == rule
assert read_progress(progress_document(progress).encoded) == progress
assert read_slot(slot_document(slot).encoded) == slot
assert progress.matches_schedule(rule) and slot.consistent_with(rule)
print('Current-source recurrence codecs and pinned timezone planning passed.')
""",
    )
    assert result.returncode == 0, result.stderr
    assert "Current-source recurrence codecs and pinned timezone planning passed." in result.stdout
