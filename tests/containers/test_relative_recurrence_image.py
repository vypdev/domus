"""Verify an actual relative successor from both lifetimes in each packaged CPU image."""

import pytest
from test_app_image import docker
from test_app_image import image as image


@pytest.mark.parametrize("mode", ["native", "standalone"])
def test_packaged_owned_worker_restarts_and_materializes_a_relative_successor(image, mode):
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
import sys
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event

from domus.application.household_commands import HouseholdCommands, SetupHousehold
from domus.application.relative_recurrence_commands import (
    CreateRelativeTask, RelativeRecurrenceCommands,
)
from domus.application.task_commands import TaskCommands
from domus.application.task_requests import CompleteTask, CreateTask
from domus.composition import ingress, server
from domus.domain.identity import HumanIdentity
from domus.domain.recurrence_rules import NominalDate
from domus.domain.recurrence_time import RelativeInterval, TimePolicy
from domus.domain.task_values import TaskContent
from domus.infrastructure.application_runtime import SecureIdentifiers, SystemClock, TimeZoneCatalog
from domus.infrastructure.recurrence_time import PinnedRecurrenceTime
from domus.infrastructure.sqlite import SCHEMA_VERSION

MODE = sys.argv[1]
ORIGIN = 'https://domus.fixture'
assert SCHEMA_VERSION == 10

class FixtureHuman:
    def current(self):
        return HumanIdentity('a' * 32, True, True, False)

    def get(self, user_id):
        raise AssertionError('No directory request expected')

def owned(root):
    if MODE == 'native':
        return ingress.create_owned_runtime('fixture', 'edge', root, (ORIGIN,))
    return server.create_owned_runtime('http://ha.fixture', ORIGIN, 'edge', root)

async def one_lifetime(runtime):
    worker = runtime.recurrence
    finished = Event()
    tick = worker._tick

    def completed(should_continue):
        try:
            return tick(should_continue)
        finally:
            finished.set()

    worker._tick = completed
    async with runtime.app.router.lifespan_context(runtime.app):
        assert await asyncio.to_thread(finished.wait, 10)
    assert worker.last_failure is None
    return worker.last_run

with TemporaryDirectory(prefix='relative-worker-image-') as directory:
    root = Path(directory)
    actor, clock, ids = FixtureHuman(), SystemClock(), SecureIdentifiers()
    times = PinnedRecurrenceTime()
    runtime = owned(root)
    try:
        store = runtime.storage.database
        HouseholdCommands(store, actor, actor, TimeZoneCatalog(), clock, ids).setup(
            'setup', SetupHousehold('Fictional image fixture', 'UTC'))
        rule = RelativeRecurrenceCommands(store, actor, clock, ids, times).create(
            'relative', CreateRelativeTask(CreateTask(TaskContent('Replace filter')),
                NominalDate(date(2026, 1, 1)), RelativeInterval(30),
                TimePolicy('UTC', times.data_identity))
        ).result.decode()['schedule_id']
        assert asyncio.run(one_lifetime(runtime)).created == 1
        with store.read() as unit:
            parent = unit.recurrence.relative_progress('home', rule).current_occurrence_id
            member = unit.members.by_user('home', actor.current().ha_user_id).member_id
        original = TaskCommands(store, actor, clock, ids).complete(
            'complete', CompleteTask(parent, 1, (member,), clock.now()))
    finally:
        runtime.close()

    runtime = owned(root)
    try:
        observed = asyncio.run(one_lifetime(runtime))
        assert observed.relative_slots_observed == 1 and observed.source_scan_complete
        with runtime.storage.database.read() as unit:
            slots = unit.recurrence.relative_slots('home', rule)
            assert len(slots) == 2
            derived = next(slot for slot in slots if slot.source is not None)
            assert derived.source.cycle.cycle_id == original.result.decode()['cycle']['cycle_id']
            assert derived.matches_receipt(unit.receipts.get(derived.command))
            assert not unit.recurrence.relative_sources_pending('home')
    finally:
        runtime.close()

print('relative-owned-worker-ok')
""",
        mode,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "relative-owned-worker-ok"
