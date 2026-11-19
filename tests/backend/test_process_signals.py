"""Requested process termination must pass through owned-runtime cleanup."""

import signal
from contextlib import closing

import pytest
from test_household_commands import Actor, Clock, Directory, Identifiers, Zones
from test_owned_storage import directory

from domus.application.household_commands import HouseholdCommands, SetupHousehold
from domus.application.task_commands import TaskCommands
from domus.application.task_requests import CreateTask
from domus.composition import ingress, server
from domus.domain.task_values import TaskContent
from domus.infrastructure.owned_storage import open_storage


def request_termination():
    handler = signal.getsignal(signal.SIGTERM)
    assert getattr(handler, "__module__", "") == "domus.composition.signals"
    handler(signal.SIGTERM, None)


@pytest.mark.parametrize("native", [False, True])
@pytest.mark.parametrize("projection", [False, True])
def test_sigterm_closes_runtime_defers_repeated_stop_and_retains_receipts(
    tmp_path, monkeypatch, native, projection
):
    root = directory(tmp_path)
    actor, clock, identifiers = Actor(), Clock(), Identifiers()
    with closing(open_storage(root, "edge")) as storage:
        HouseholdCommands(storage.database, actor, Directory(), Zones(), clock, identifiers).setup(
            "setup", SetupHousehold("Shutdown fixture", "UTC")
        )
        receipt = TaskCommands(storage.database, actor, clock, identifiers).create(
            "create", CreateTask(TaskContent("Retained after stop"))
        )
    before = signal.getsignal(signal.SIGTERM)
    events = []
    runtime_type = ingress.NativeRuntime if native else server.AuthenticationRuntime
    original_close = runtime_type.close

    def close(runtime):
        events.append("closing")
        try:
            request_termination()
            events.append("repeated stop deferred")
        finally:
            result = original_close(runtime)
        events.append("closed")
        return result

    def serve(*args, **kwargs):
        events.append("serving")
        request_termination()
        raise AssertionError("A requested stop must unwind the listener")

    monkeypatch.setattr(runtime_type, "close", close)
    monkeypatch.setattr(ingress.uvicorn, "run", serve)
    monkeypatch.setattr(ingress, "_serve_ha_projections", serve)
    if projection:
        monkeypatch.setenv("DOMUS_HA_TASKS_DIGEST", "a" * 64)
    monkeypatch.setenv("SUPERVISOR_TOKEN", "fixture-supervisor-token")
    arguments = ["--channel", "edge", "--data-directory", str(root)]
    if native:
        arguments += ["--public-origin", "http://homeassistant.local:8123"]
        assert ingress.main(arguments) == 0
    else:
        arguments += ["--ha-url", "https://ha.example", "--public-origin", "https://domus.example"]
        assert server.main(arguments) == 0
    assert events == ["serving", "closing", "repeated stop deferred", "closed"]
    assert signal.getsignal(signal.SIGTERM) is before
    with closing(open_storage(root, "edge")) as restarted:
        with restarted.database.read() as unit:
            assert unit.households.current().name == "Shutdown fixture"
            assert unit.receipts.get(receipt.command) == receipt


def test_first_sigterm_during_cleanup_is_deferred_and_original_handler_is_restored():
    from domus.composition.signals import graceful_termination

    before = signal.getsignal(signal.SIGTERM)
    events = []
    with graceful_termination() as begin_cleanup:
        begin_cleanup()
        request_termination()
        request_termination()
        events.append("cleanup finished")
    assert events == ["cleanup finished"]
    assert signal.getsignal(signal.SIGTERM) is before


@pytest.mark.parametrize("native", [False, True])
def test_sigterm_during_composition_releases_the_partially_opened_storage(
    tmp_path, monkeypatch, native
):
    root = directory(tmp_path)
    with closing(open_storage(root, "edge")) as storage:
        installation = storage.installation
    before = signal.getsignal(signal.SIGTERM)

    def interrupted(*args, **kwargs):
        request_termination()

    module = ingress if native else server
    factory = "_compose_business" if native else "_compose"
    monkeypatch.setattr(module, factory, interrupted)
    monkeypatch.setenv("SUPERVISOR_TOKEN", "fixture-supervisor-token")
    arguments = ["--channel", "edge", "--data-directory", str(root)]
    if native:
        arguments += ["--public-origin", "http://homeassistant.local:8123"]
    else:
        arguments += ["--ha-url", "https://ha.example", "--public-origin", "https://domus.example"]
    assert module.main(arguments) == 0
    assert signal.getsignal(signal.SIGTERM) is before
    with closing(open_storage(root, "edge")) as reopened:
        assert reopened.installation == installation


@pytest.mark.parametrize("failure", [RuntimeError("listener failed"), KeyboardInterrupt()])
def test_unexpected_errors_propagate_and_restore_the_original_handler(failure):
    from domus.composition.signals import graceful_termination

    before = signal.getsignal(signal.SIGTERM)
    with pytest.raises(type(failure)) as raised:
        with graceful_termination():
            raise failure
    assert raised.value is failure
    assert signal.getsignal(signal.SIGTERM) is before


@pytest.mark.parametrize("native", [False, True])
def test_sigterm_after_runtime_creation_closes_it_before_the_listener_starts(
    tmp_path, monkeypatch, native
):
    before = signal.getsignal(signal.SIGTERM)
    closed = []

    class Runtime:
        @property
        def app(self):
            request_termination()

        def close(self):
            closed.append(True)
            return 0, 0

    module = ingress if native else server
    monkeypatch.setattr(module, "create_owned_runtime", lambda *args, **kwargs: Runtime())
    monkeypatch.setenv("SUPERVISOR_TOKEN", "fixture-supervisor-token")
    arguments = ["--channel", "edge", "--data-directory", str(tmp_path)]
    if native:
        arguments += ["--public-origin", "http://homeassistant.local:8123"]
    else:
        arguments += ["--ha-url", "https://ha.example", "--public-origin", "https://domus.example"]
    assert module.main(arguments) == 0
    assert closed == [True]
    assert signal.getsignal(signal.SIGTERM) is before


def test_cleanup_error_remains_visible_after_a_requested_stop():
    from domus.composition.signals import graceful_termination

    before = signal.getsignal(signal.SIGTERM)
    with pytest.raises(RuntimeError, match="cleanup failed"):
        with graceful_termination() as begin_cleanup:
            try:
                request_termination()
            finally:
                begin_cleanup()
                raise RuntimeError("cleanup failed")
    assert signal.getsignal(signal.SIGTERM) is before
