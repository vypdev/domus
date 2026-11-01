"""Both real CPU images must execute the newly packaged recurrence and pinned timezone code."""

from test_app_image import docker
from test_app_image import image as image


def test_current_image_executes_recurrence_creation_planning_and_closed_record_codecs(image):
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
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from domus.application.fixed_recurrence import FixedRecurrencePlanner
from domus.application.household_commands import HouseholdCommands, SetupHousehold
from domus.application.recurrence_commands import CreateFixedTask, RecurrenceCommands
from domus.application.task_requests import CreateTask
from domus.domain.errors import InvalidInput
from domus.domain.identity import HumanIdentity
from domus.domain.nominal_recurrence import CalendarNominalExpansion
from domus.domain.recurrence_records import FixedProgress, FixedSchedule, ScheduledSlot
from domus.domain.recurrence_rule_text import parse_fixed_pattern
from domus.domain.recurrence_time import NominalTime, TimePolicy, TimeResolution
from domus.domain.storage import Installation
from domus.domain.task_values import TaskContent
from domus.infrastructure.application_runtime import SecureIdentifiers, SystemClock, TimeZoneCatalog
from domus.infrastructure.recurrence_time import PinnedRecurrenceTime, TIMEZONE_DATA_IDENTITY
from domus.infrastructure.sqlite import SCHEMA_VERSION, SQLiteDatabase
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
try:
    ScheduledSlot(installation, replace(rule, pattern=replace(pattern, count=1)),
        planned.slots[1], 'outside-count', 100)
except InvalidInput:
    pass
else:
    raise AssertionError('A real second nominal cannot fit COUNT1')

class FictionalHuman:
    def current(self):
        return HumanIdentity('fixture_ha_admin', True, True, False)

class UnusedDirectory:
    def get(self, user_id):
        raise AssertionError('Default mapping selects no external directory subject')

with TemporaryDirectory(prefix='domus-current-image-') as directory:
    store = SQLiteDatabase(Path(directory) / 'domus.sqlite3', installation)
    store.initialize()
    clock, identifiers, human = SystemClock(), SecureIdentifiers(), FictionalHuman()
    HouseholdCommands(store, human, UnusedDirectory(), TimeZoneCatalog(), clock, identifiers).setup(
        'setup', SetupHousehold('Fictional image fixture', 'UTC'))
    creation = RecurrenceCommands(store, human, clock, identifiers,
        FixedRecurrencePlanner(CalendarNominalExpansion(), times))
    request = CreateFixedTask(CreateTask(TaskContent('Scheduled image fixture')), pattern, policy)
    receipt = creation.create_fixed('create', request)
    assert creation.create_fixed('create', request) == receipt
    facts = receipt.result.decode()
    with store.read() as unit:
        assert unit.tasks.occurrences('home') == ()
        assert len(unit.tasks.definitions('home')) == 1
        assert unit.recurrence.progress('home', facts['schedule_id']).cursor.nominal_count == 0
        assert unit.receipts.get(receipt.command) == receipt
print('Current-source recurrence creation, codecs and pinned timezone planning passed.')
""",
    )
    assert result.returncode == 0, result.stderr
    assert (
        "Current-source recurrence creation, codecs and pinned timezone planning passed."
        in result.stdout
    )
