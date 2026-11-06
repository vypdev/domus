"""Both production lifetimes bind local technical authority and perform real SQLite work."""

from contextlib import asynccontextmanager
from dataclasses import replace
from threading import Event, Thread

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_fixed_materialization import configured
from test_recurrence_creation import request
from test_task_runtime import api as api

from domus.application.fixed_recurrence import FixedRecurrencePlanner
from domus.application.recurrence_commands import RecurrenceCommands
from domus.composition.recurrence import bind_lifespan, recurrence_worker
from domus.domain.errors import Forbidden, StorageBusy
from domus.domain.nominal_recurrence import CalendarNominalExpansion
from domus.domain.recurrence_records import ScheduleState
from domus.domain.storage import Installation
from domus.infrastructure.application_runtime import SecureIdentifiers, SystemClock
from domus.infrastructure.owned_storage import open_storage
from domus.infrastructure.recurrence_time import PinnedRecurrenceTime
from domus.infrastructure.sqlite import SQLiteDatabase


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch):
    monkeypatch.setattr(SystemClock, "now", lambda _: 1_780_272_000_000)


def observed(worker, monkeypatch):
    """Signal only after the real production tick has completed, without polling SQLite."""
    completed = Event()
    original = worker._tick

    def tick(should_continue):
        result = original(should_continue)
        completed.set()
        return result

    monkeypatch.setattr(worker, "_tick", tick)
    return completed


def test_composed_worker_uses_owned_installation_and_actual_household_without_an_ha_request(
    tmp_path, monkeypatch
):
    _, store, actor, _, rule_id, _ = configured(tmp_path)
    calls = actor.calls
    worker = recurrence_worker(store, store.installation)
    done = observed(worker, monkeypatch)
    try:
        worker.start()
        assert done.wait(5)
    finally:
        worker.close()
    assert worker.last_run.created == 1 and worker.last_failure is None
    assert actor.calls == calls
    with store.read() as unit:
        assert len(unit.recurrence.slots("home", rule_id)) == 1
        assert unit.tasks.occurrences("home")[0].current_cycle_id is None


def test_composition_refuses_a_different_installation_before_admitting_any_rule(tmp_path):
    _, store, _, _, rule_id, _ = configured(tmp_path)
    worker = recurrence_worker(store, replace(store.installation, channel="stable"))
    with pytest.raises(Forbidden):
        worker._tick(lambda: True)
    worker.close()
    with store.read() as unit:
        assert unit.recurrence.frontier("home") is None
        assert unit.recurrence.slots("home", rule_id) == ()


def test_stop_before_composition_read_has_no_database_effect(tmp_path):
    _, store, _, _, _, _ = configured(tmp_path)
    worker = recurrence_worker(store, store.installation)
    assert worker._tick(lambda: False).status == "stopped"
    worker.close()
    with store.read() as unit:
        assert unit.recurrence.frontier("home") is None


def test_unconfigured_installation_stays_unconfigured_and_no_empty_frontier_is_created(tmp_path):
    store = SQLiteDatabase(
        tmp_path / "domus.sqlite3", Installation("047cc6fb-dfb0-4fa4-b3c3-e0fe54d116b6", "edge")
    )
    store.initialize()
    worker = recurrence_worker(store, store.installation)
    try:
        assert worker._tick(lambda: True).status == "unconfigured"
    finally:
        worker.close()
    with store.read() as unit:
        assert unit.households.current() is None and unit.outbox.pending() == ()
        assert unit.recurrence.frontier("home") is None


def test_configured_home_without_active_rules_does_not_churn_frontier_or_business_records(tmp_path):
    _, store, _, _, rule_id, _ = configured(tmp_path)
    with store.write() as unit:
        rule = unit.recurrence.schedule("home", rule_id)
        unit.recurrence.save_schedule(replace(rule, state=ScheduleState.PAUSED, revision=2), 1)
    worker = recurrence_worker(store, store.installation)
    try:
        assert worker._tick(lambda: True).status == "complete"
        assert worker._tick(lambda: True).selected_schedule_ids == ()
    finally:
        worker.close()
    with store.read() as unit:
        assert unit.recurrence.frontier("home") is None and unit.tasks.occurrences("home") == ()


@pytest.mark.parametrize("paused", [False, True])
def test_both_business_runtimes_start_only_during_lifespan_and_resume_after_restart(
    api, monkeypatch, paused
):
    from domus.composition import ingress, server

    original = api.runtime.recurrence
    assert original is not None and not original.is_running
    # This setup uses the same fixture-confirmed HA subject; it does not claim owner-HA access.
    human = (
        api.source.people[api.client.headers["X-Remote-User-Id"]]
        if api.mode == "native"
        else api.source.human
    )

    class Actor:
        def current(self):
            return human

    creator = RecurrenceCommands(
        api.store,
        Actor(),
        SystemClock(),
        SecureIdentifiers(),
        FixedRecurrencePlanner(CalendarNominalExpansion(), PinnedRecurrenceTime()),
    )
    value = request()
    receipt = creator.create_fixed(
        "runtime-fixed", replace(value, pattern=replace(value.pattern, count=1))
    )
    rule_id = receipt.result.decode()["schedule_id"]
    if paused:
        with api.store.write() as unit:
            rule = unit.recurrence.schedule("home", rule_id)
            unit.recurrence.save_schedule(replace(rule, state=ScheduleState.PAUSED, revision=2), 1)
    done = observed(original, monkeypatch)
    try:
        with TestClient(api.runtime.app, base_url=api.origin):
            assert done.wait(5) and original.is_running
        assert not original.is_running
        with api.store.read() as unit:
            assert len(unit.recurrence.slots("home", rule_id)) == (0 if paused else 1)
    finally:
        api.runtime.close()
    # Reopening production composition over the same schema reads durable cursor/slot facts.
    if api.mode == "native":
        runtime = ingress.create_business_runtime(
            "private-supervisor-token",
            "edge",
            api.store.path,
            api.store.installation.instance_id,
            (api.origin,),
        )
    else:
        runtime = server.create_runtime(
            "http://ha.local",
            api.origin,
            api.store.installation.instance_id,
            "edge",
            database=api.store.path,
        )
    done = observed(runtime.recurrence, monkeypatch)
    try:
        with TestClient(runtime.app, base_url=api.origin):
            assert done.wait(5)
    finally:
        runtime.close()
    with api.store.read() as unit:
        assert len(unit.recurrence.slots("home", rule_id)) == (0 if paused else 1)


def test_lifespan_preserves_prior_state_and_closes_worker_on_failure(monkeypatch):
    events = []
    app = FastAPI()

    @asynccontextmanager
    async def previous(_):
        events.append("entered")
        try:
            yield {"retained": "state"}
        finally:
            events.append("exited")

    class Worker:
        def start(self):
            events.append("started")

        def close(self):
            events.append("closed")

    app.router.lifespan_context = previous
    bind_lifespan(app, Worker())
    with pytest.raises(RuntimeError, match="fixture-application"):
        with TestClient(app) as client:
            assert client.app_state == {"retained": "state"}
            raise RuntimeError("fixture-application")
    assert events == ["entered", "started", "closed", "exited"]


def test_startup_failure_disposes_worker_and_exits_the_previous_lifespan():
    events = []
    app = FastAPI()

    @asynccontextmanager
    async def previous(_):
        try:
            yield
        finally:
            events.append("previous-closed")

    class Worker:
        def start(self):
            raise RuntimeError("fixture-startup")

        def close(self):
            events.append("worker-closed")

    app.router.lifespan_context = previous
    bind_lifespan(app, Worker())
    with pytest.raises(RuntimeError, match="fixture-startup"):
        with TestClient(app):
            pytest.fail("Startup was rejected")
    assert events == ["worker-closed", "previous-closed"]


def test_owned_runtime_keeps_actual_installation_lease_until_its_worker_has_joined(
    api, tmp_path, monkeypatch
):
    from domus.application.fair_recurrence import FixedRun
    from domus.composition import ingress, server

    directory = tmp_path / "owned-runtime"
    directory.mkdir(mode=0o700)
    runtime = (
        ingress.create_owned_runtime("private-supervisor-token", "edge", directory, (api.origin,))
        if api.mode == "native"
        else server.create_owned_runtime("http://ha.local", api.origin, "edge", directory)
    )
    entered, release, closed = Event(), Event(), Event()

    def tick(_):
        entered.set()
        assert release.wait(5)
        return FixedRun("unconfigured")

    monkeypatch.setattr(runtime.recurrence, "_tick", tick)
    runtime.recurrence.start()
    assert entered.wait(5)

    def close():
        runtime.close()
        closed.set()

    closer = Thread(target=close)
    closer.start()
    try:
        assert runtime.recurrence._stop.wait(5) and not closed.is_set()
        with pytest.raises(StorageBusy, match="installation_in_use"):
            open_storage(directory, "edge")
    finally:
        release.set()
        closer.join(5)
        runtime.close()
    assert closed.is_set() and not runtime.recurrence.is_running
    reopened = open_storage(directory, "edge")
    reopened.close()


def test_both_owned_lifetimes_resume_a_relative_cycle_after_bootstrap(api, monkeypatch):
    from test_relative_recurrence_creation import request as relative_request

    from domus.application.relative_recurrence_commands import RelativeRecurrenceCommands
    from domus.application.task_commands import TaskCommands
    from domus.application.task_requests import CompleteTask
    from domus.composition import ingress, server

    human = (
        api.source.people[api.client.headers["X-Remote-User-Id"]]
        if api.mode == "native"
        else api.source.human
    )

    class Actor:
        def current(self):
            return human

    actor, clock, ids = Actor(), SystemClock(), SecureIdentifiers()
    schedule = (
        RelativeRecurrenceCommands(api.store, actor, clock, ids, PinnedRecurrenceTime())
        .create("runtime-relative", relative_request())
        .result.decode()["schedule_id"]
    )
    ready = observed(api.runtime.recurrence, monkeypatch)
    try:
        with TestClient(api.runtime.app, base_url=api.origin):
            assert ready.wait(5)
        with api.store.read() as unit:
            bootstrap = unit.recurrence.relative_progress("home", schedule)
            assert bootstrap.current_occurrence_id is not None
            member = unit.members.by_user("home", human.ha_user_id).member_id
        original = TaskCommands(api.store, actor, clock, ids).complete(
            "runtime-complete",
            CompleteTask(bootstrap.current_occurrence_id, 1, (member,), clock.now()),
        )
    finally:
        api.runtime.close()

    if api.mode == "native":
        runtime = ingress.create_business_runtime(
            "private-supervisor-token",
            "edge",
            api.store.path,
            api.store.installation.instance_id,
            (api.origin,),
        )
    else:
        runtime = server.create_runtime(
            "http://ha.local",
            api.origin,
            api.store.installation.instance_id,
            "edge",
            database=api.store.path,
        )
    ready = observed(runtime.recurrence, monkeypatch)
    try:
        with TestClient(runtime.app, base_url=api.origin):
            assert ready.wait(5)
        assert runtime.recurrence.last_run.relative_slots_observed == 1
        with api.store.read() as unit:
            slots = unit.recurrence.relative_slots("home", schedule)
            assert len(slots) == 2
            successor = next(slot for slot in slots if slot.source is not None)
            assert successor.source.cycle.cycle_id == original.result.decode()["cycle"]["cycle_id"]
    finally:
        runtime.close()
