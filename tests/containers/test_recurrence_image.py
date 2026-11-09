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
import asyncio
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from domus.application.fixed_recurrence import FixedRecurrencePlanner
from domus.application.fixed_materialization import FixedMaintenance, MaintenanceScope
from domus.application.fair_recurrence import FairFixedRunner, RunLimits
from domus.application.household_commands import HouseholdCommands, SetupHousehold
from domus.application.recurrence_commands import CreateFixedTask, RecurrenceCommands
from domus.application.task_requests import CreateTask
from domus.application.task_commands import TaskCommands, CompleteTask
from domus.application.task_events import TaskEventFeed
from domus.application.relative_recurrence import RelativeRecurrencePlanner
from domus.application.relative_recurrence_commands import (
    CreateRelativeTask, RelativeRecurrenceCommands,
)
from domus.composition import ingress, server
from domus.domain.errors import DatabaseRejected, InvalidInput, StorageBusy, StorageFailure
from domus.domain.recurrence_frontier import RecurrenceFrontier
from domus.domain.relative_recurrence import (
    RelativeSchedule, RelativeProgress, RelativeSlot, RelativeOperation,
)
from domus.domain.identity import HumanIdentity
from domus.domain.nominal_recurrence import CalendarNominalExpansion
from domus.domain.recurrence_planning import FixedCursor, cursor_binding
from domus.domain.recurrence_records import FixedProgress, FixedSchedule, ScheduledSlot
from domus.domain.recurrence_rule_text import parse_fixed_pattern
from domus.domain.recurrence_time import NominalTime, TimePolicy, TimeResolution, RelativeInterval
from domus.domain.storage import Installation, Receipt, AuditEntry, OutboxEvent, JsonDocument
from domus.domain.task_values import TaskContent
from domus.infrastructure.application_runtime import SecureIdentifiers, SystemClock, TimeZoneCatalog
from domus.infrastructure.recurrence_time import PinnedRecurrenceTime, TIMEZONE_DATA_IDENTITY
from domus.infrastructure.sqlite import SCHEMA_VERSION, SQLiteDatabase
from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots
from domus.infrastructure.sqlite_recurrence_records import (
    schedule_document, read_schedule, progress_document, read_progress, slot_document, read_slot,
    frontier_document, read_frontier,
)
assert SCHEMA_VERSION == 14
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
for value, encode, decode in (
    (rule, schedule_document, read_schedule),
    (progress, progress_document, read_progress),
    (slot, slot_document, read_slot),
    (RecurrenceFrontier('home', None, 100), frontier_document, read_frontier),
):
    try:
        decode(' ' + encode(value).encoded)
    except StorageFailure:
        pass
    else:
        raise AssertionError('Noncanonical stored text was accepted')
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
    maintenance = FixedMaintenance(store, MaintenanceScope(installation, 'home'),
        creation.planner, clock, identifiers)
    horizon = NominalTime(datetime(2026, 3, 31, 2, 30))
    first_step = maintenance.step(facts['schedule_id'], horizon)
    assert first_step.status == 'created' and not first_step.cursor.closed
    with store.read() as unit:
        work = unit.tasks.occurrence('home', first_step.occurrence_id)
        assert work.due_at == first.resolved.instant_ms
    assert maintenance.step(facts['schedule_id'], horizon).cursor.closed
    assert maintenance.step(facts['schedule_id'], horizon).status == 'current'
    with store.read() as unit:
        assert len(unit.tasks.occurrences('home')) == 2
        assert len(unit.recurrence.slots('home', facts['schedule_id'])) == 2
    other = creation.create_fixed('fair-create', request).result.decode()
    fair = FairFixedRunner(store, maintenance.scope, maintenance, times, clock,
        RunLimits(max_slots=1))
    assert fair.tick().created == 1
    assert fair.tick().created == 1
    with store.read() as unit:
        member = unit.members.by_user('home', human.current().ha_user_id)
        work = unit.tasks.occurrence('home', first_step.occurrence_id)
    performed = clock.now()
    TaskCommands(store, human, clock, identifiers).complete('perform-planning-control',
        CompleteTask(work.occurrence_id, work.revision, (member.member_id,), performed))
    source = TaskEventFeed(store, installation).read().items[0]
    relative = RelativeSchedule('relative-plan-control', 'home', source.definition_id,
        planned.slots[0], RelativeInterval(30), policy, 100)
    relative_plan = RelativeRecurrencePlanner(times).plan(relative, source.cycle)
    assert relative_plan.status == 'ready'
    assert relative_plan.source.cycle == source.cycle
    assert relative_plan.source.performed_local.instant_ms == performed
    # This is a packaged read-only plan, not relative persistence or materialization.
    with store.read() as unit:
        assert len(unit.tasks.occurrences('home')) == 4
        assert unit.recurrence.frontier('home') is not None
        assert unit.recurrence.progress('home', other['schedule_id']).cursor.closed

    async def serve_once(runtime):
        async with runtime.app.router.lifespan_context(runtime.app):
            deadline = asyncio.get_running_loop().time() + 10
            while runtime.recurrence.last_run is None:
                assert asyncio.get_running_loop().time() < deadline, 'Owned worker did not run'
                await asyncio.sleep(0.01)
            assert runtime.recurrence.is_running
            assert runtime.recurrence.last_run.created == 2
        assert not runtime.recurrence.is_running

    for mode in ('standalone', 'native'):
        scheduled = creation.create_fixed(mode + '-create', request).result.decode()
        runtime = (
            server.create_runtime('http://ha.local', 'https://domus.example',
                installation.instance_id, installation.channel, database=store.path)
            if mode == 'standalone' else
            ingress.create_business_runtime('fictional-supervisor-token', installation.channel,
                store.path, installation.instance_id, ('http://ha.local',))
        )
        try:
            assert not runtime.recurrence.is_running
            asyncio.run(serve_once(runtime))
        finally:
            runtime.close()
        with store.read() as unit:
            assert len(unit.recurrence.slots('home', scheduled['schedule_id'])) == 2
            assert unit.recurrence.progress('home', scheduled['schedule_id']).cursor.closed
    with store.read() as unit:
        assert len(unit.tasks.occurrences('home')) == 8
    contended = SQLiteDatabase(store.path, installation, busy_timeout=0.01)
    with store._connection() as holder:
        holder.execute('BEGIN EXCLUSIVE')
        try:
            with contended.read():
                raise AssertionError('An exclusive writer was bypassed')
        except StorageBusy:
            pass
        holder.execute('ROLLBACK')
    with store.read() as unit:
        original_progress = unit.recurrence.progress('home', facts['schedule_id'])
    altered = replace(original_progress,
        cursor=replace(original_progress.cursor,
            period_index=original_progress.cursor.period_index+100))
    with store._connection() as connection:
        connection.execute('UPDATE recurrence_progress SET document=? WHERE schedule_id=?',
            (progress_document(altered).encoded, facts['schedule_id']))
    source_bytes = store.path.read_bytes()
    try:
        with store.read() as unit:
            unit.recurrence.progress('home', facts['schedule_id'])
    except StorageFailure:
        pass
    else:
        raise AssertionError('A bound cursor skipped its actual nominal rank')
    try:
        SQLiteSnapshots(store, Path(directory)/'bad-checkpoint', installation, clock).create('bad')
    except DatabaseRejected as error:
        assert error.code == 'invalid_snapshot_records'
    else:
        raise AssertionError('Checkpoint accepted inconsistent progress')
    assert store.path.read_bytes() == source_bytes
with TemporaryDirectory(prefix='domus-current-until-') as directory:
    store = SQLiteDatabase(Path(directory)/'domus.sqlite3', installation)
    store.initialize()
    HouseholdCommands(store, human, UnusedDirectory(), TimeZoneCatalog(), clock, identifiers).setup(
        'setup', SetupHousehold('Fictional UTC boundary fixture', 'UTC'))
    creation = RecurrenceCommands(store, human, clock, identifiers,
        FixedRecurrencePlanner(CalendarNominalExpansion(), times))
    utc_policy = TimePolicy('UTC', TIMEZONE_DATA_IDENTITY)
    utc_pattern = parse_fixed_pattern('FREQ=DAILY;UNTIL=20260102T120000Z',
        NominalTime(datetime(2026, 1, 1, 12)))
    request = CreateFixedTask(CreateTask(TaskContent('UTC inclusive boundary')),
        utc_pattern, utc_policy)
    rid = creation.create_fixed('utc-create', request).result.decode()['schedule_id']
    maintenance = FixedMaintenance(store, MaintenanceScope(installation, 'home'),
        creation.planner, clock, identifiers)
    horizon = NominalTime(datetime(2026, 1, 5, 12))
    assert maintenance.step(rid, horizon).status == 'created'
    included = maintenance.step(rid, horizon)
    assert not included.cursor.closed and included.cursor.nominal_count == 2
    terminal = maintenance.step(rid, horizon)
    assert terminal.cursor.closed and terminal.status == 'scan'
    with store.read() as unit:
        progress = unit.recurrence.progress('home', rid)
        evidence = progress.evidence
        assert evidence.time.last.resolved.instant_ms == utc_pattern.until
        assert evidence.time.terminal.resolved.instant_ms > utc_pattern.until
        assert unit.receipts.get(evidence.command).operation_id == evidence.operation_id
        assert len(unit.tasks.occurrences('home')) == 2
    assert maintenance.step(rid, horizon).status == 'current'
    assert SQLiteSnapshots(store, Path(directory)/'good', installation, clock).create('good')
    with store._connection() as connection:
        connection.execute('DELETE FROM recurrence_progress_evidence')
    source_bytes = store.path.read_bytes()
    try:
        with store.read() as unit:
            unit.recurrence.progress('home', rid)
    except StorageFailure:
        pass
    else:
        raise AssertionError('UTC progress lost its original evidence header')
    try:
        SQLiteSnapshots(store, Path(directory)/'bad', installation, clock).create('bad')
    except DatabaseRejected as error:
        assert error.code == 'invalid_snapshot_records'
    else:
        raise AssertionError('Checkpoint accepted unproved UTC continuation')
    assert store.path.read_bytes() == source_bytes
with TemporaryDirectory(prefix='domus-current-history-') as directory:
    store = SQLiteDatabase(Path(directory)/'domus.sqlite3', installation)
    store.initialize()
    HouseholdCommands(store, human, UnusedDirectory(), TimeZoneCatalog(), clock, identifiers).setup(
        'setup', SetupHousehold('Fictional original generation', 'UTC'))
    creation = RecurrenceCommands(store, human, clock, identifiers,
        FixedRecurrencePlanner(CalendarNominalExpansion(), times))
    rid = creation.create_fixed('history-create', request).result.decode()['schedule_id']
    maintenance = FixedMaintenance(store, MaintenanceScope(installation, 'home'),
        creation.planner, clock, identifiers)
    result = maintenance.step(rid, horizon)
    with store.write() as unit:
        original = unit.recurrence.slot('home', result.receipt.command.key)
        progress = unit.recurrence.progress('home', rid)
        current = replace(original.schedule, revision=2, pattern_revision=2,
            pattern=replace(original.schedule.pattern, interval=2))
        unit.recurrence.save_schedule(current, 1)
        unit.recurrence.save_progress(replace(progress, revision=3, pattern_revision=2,
            cursor=FixedCursor(cursor_binding(current.pattern, current.policy)),
            evidence=None, last_run_at=None, range_complete=False), 2)
    with store.read() as unit:
        assert unit.recurrence.slot('home', original.key) == original
    assert SQLiteSnapshots(store, Path(directory)/'good', installation, clock).create('good')
    altered = replace(original, schedule=replace(original.schedule,
        pattern=replace(original.schedule.pattern, interval=3)))
    assert altered.key == original.key
    with store._connection() as connection:
        connection.execute('UPDATE recurrence_slots SET document=?',
            (slot_document(altered).encoded,))
    source_bytes = store.path.read_bytes()
    try:
        with store.read() as unit:
            unit.recurrence.slot('home', original.key)
    except StorageFailure:
        pass
    else:
        raise AssertionError('Historical pattern contradicted its original generation binding')
    try:
        SQLiteSnapshots(store, Path(directory)/'bad', installation, clock).create('bad')
    except DatabaseRejected as error:
        assert error.code == 'invalid_snapshot_records'
    else:
        raise AssertionError('Checkpoint accepted altered original generation facts')
    assert store.path.read_bytes() == source_bytes
with TemporaryDirectory(prefix='domus-current-relative-store-') as directory:
    store = SQLiteDatabase(Path(directory)/'domus.sqlite3', installation)
    store.initialize()
    HouseholdCommands(store, human, UnusedDirectory(), TimeZoneCatalog(), clock, identifiers).setup(
        'setup', SetupHousehold('Fictional relative persistence', 'UTC'))
    # Explicit synthetic repository proof exercises packaging/storage, not a relative consumer.
    manual = TaskCommands(store, human, clock, identifiers).create('relative-base',
        CreateTask(TaskContent('Relative storage boundary'))).result.decode()
    with store.read() as unit:
        work = unit.tasks.occurrence('home', manual['occurrence_id'])
    rule = RelativeSchedule('relative-store', 'home', manual['definition_id'], first,
        RelativeInterval(30), policy, work.definition_snapshot.created_at)
    progress = RelativeProgress(rule.schedule_id, 'home', 1, rule.binding)
    slot = RelativeSlot(installation, rule, first, work.occurrence_id, work.created_at)
    opid = identifiers.new()
    advanced = replace(progress, current_occurrence_id=work.occurrence_id,
        current_slot_key=slot.key, revision=2, last_run_at=clock.now(),
        evidence=RelativeOperation(slot.command, opid))
    result = JsonDocument.from_value({'slot_key': slot.key, 'occurrence_id': work.occurrence_id,
        'schedule_id': rule.schedule_id, 'definition_id': rule.definition_id,
        'relative_slot_fingerprint': slot.evidence_fingerprint,
        'relative_progress': advanced.state_document().decode()})
    timestamp = clock.now()
    with store.write() as unit:
        unit.recurrence.save_relative_schedule(rule, 0)
        unit.recurrence.save_relative_progress(progress, 0)
        unit.recurrence.add_relative_slot(slot)
        unit.receipts.add(Receipt(slot.command, JsonDocument.from_value({}).fingerprint,
            opid, result, timestamp))
        unit.audit.append(AuditEntry(opid, slot.command, JsonDocument.from_value({}), timestamp))
        unit.outbox.append(OutboxEvent(opid, 'home', slot.command.action, result, timestamp))
        unit.recurrence.save_relative_progress(advanced, 1)
    with store.read() as unit:
        assert unit.recurrence.relative_progress('home', rule.schedule_id) == advanced
        assert unit.recurrence.relative_slots('home', rule.schedule_id) == (slot,)
        assert unit.recurrence.schedules('home') == ()
    assert SQLiteSnapshots(store, Path(directory)/'good', installation, clock).create('good')
with TemporaryDirectory(prefix='domus-current-relative-creation-') as directory:
    store = SQLiteDatabase(Path(directory)/'domus.sqlite3', installation)
    store.initialize()
    HouseholdCommands(store, human, UnusedDirectory(), TimeZoneCatalog(), clock, identifiers).setup(
        'setup', SetupHousehold('Fictional relative creation', 'UTC'))
    creation = RelativeRecurrenceCommands(store, human, clock, identifiers, times)
    request = CreateRelativeTask(CreateTask(TaskContent('Relative initial intention')),
        NominalTime(datetime(2026, 3, 29, 2, 30, 0, 123000)), RelativeInterval(30), policy)
    receipt = creation.create('relative-create', request)
    assert creation.create('relative-create', request) == receipt
    with store.read() as unit:
        facts = receipt.result.decode()
        rule = unit.recurrence.relative_schedule('home', facts['schedule_id'])
        assert rule.initial.nominal == request.initial
        assert rule.initial.resolved.resolved_local == datetime(2026, 3, 29, 3)
        assert unit.recurrence.relative_progress('home', rule.schedule_id).pristine
        assert len(unit.tasks.definitions('home')) == 1 and unit.tasks.occurrences('home') == ()
        assert unit.recurrence.relative_slots('home', rule.schedule_id) == ()
        assert unit.receipts.get(receipt.command) == receipt
    # Actual creation is verified; the relative materializer/source consumer is still required.
    assert SQLiteSnapshots(store, Path(directory)/'created', installation, clock).create('created')
print('Current-source recurrence, both owned runtimes and pinned-time codecs passed.')
""",
    )
    assert result.returncode == 0, result.stderr
    assert (
        "Current-source recurrence, both owned runtimes and pinned-time codecs passed."
        in result.stdout
    )
