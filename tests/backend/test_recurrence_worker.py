"""Owned recurrence polling starts explicitly, waits between attempts and joins before disposal."""

from threading import Event, Thread

import pytest

from domus.application.fair_recurrence import FixedRun
from domus.domain.errors import Forbidden, StorageBusy
from domus.infrastructure.recurrence_worker import RecurrenceWorker


@pytest.mark.parametrize("interval", [True, None, "5", 0, -1, 61, float("inf"), float("nan")])
def test_invalid_poll_interval_never_creates_a_worker(interval):
    with pytest.raises(ValueError, match="invalid_recurrence_poll_interval"):
        RecurrenceWorker(lambda _: pytest.fail("No tick"), interval=interval)


def test_construction_is_inert_and_close_without_start_prevents_late_work():
    worker = RecurrenceWorker(lambda _: pytest.fail("No tick"))
    assert not worker.is_running and worker.last_run is None and worker.last_failure is None
    worker.close()
    worker.close()
    with pytest.raises(RuntimeError, match="recurrence_worker_closed"):
        worker.start()


def test_close_waits_for_admitted_step_and_prevents_another_tick():
    entered, release, stopping, closed = Event(), Event(), Event(), Event()
    calls = []

    def tick(should_continue):
        calls.append(True)
        entered.set()
        while not release.wait(0.005):
            if not should_continue():
                stopping.set()
        return FixedRun("stopped")

    worker = RecurrenceWorker(tick)
    worker.start()
    worker.start()
    assert entered.wait(5) and worker.is_running

    def close():
        worker.close()
        closed.set()

    closer = Thread(target=close)
    closer.start()
    try:
        assert stopping.wait(5) and not closed.is_set()
    finally:
        release.set()
        closer.join(5)
        worker.close()
    assert closed.is_set() and not worker.is_running and len(calls) == 1
    assert worker.last_run == FixedRun("stopped") and worker.last_failure is None


@pytest.mark.parametrize("error", [StorageBusy("private-fixture-detail"), RuntimeError("secret")])
def test_unconfirmed_tick_is_reported_safely_and_a_later_poll_can_recover(error, caplog):
    recovered = Event()
    calls = []

    def tick(_):
        calls.append(True)
        if len(calls) == 1:
            raise error
        recovered.set()
        return FixedRun("unconfigured")

    worker = RecurrenceWorker(tick, interval=0.01)
    try:
        worker.start()
        assert recovered.wait(5)
    finally:
        worker.close()
    assert len(calls) >= 2 and worker.last_run == FixedRun("unconfigured")
    assert worker.last_failure is None
    assert "recurrence_run_unconfirmed" in caplog.text
    assert "private-fixture-detail" not in caplog.text and "secret" not in caplog.text


def test_scope_denial_stops_polling_without_disclosing_its_diagnostic(caplog):
    entered = Event()
    calls = []

    def tick(_):
        calls.append(True)
        entered.set()
        raise Forbidden("private-wrong-installation")

    worker = RecurrenceWorker(tick, interval=0.01)
    worker.start()
    assert entered.wait(5)
    worker.close()
    assert len(calls) == 1 and worker.last_run is None and worker.last_failure == "scope_denied"
    assert "private-wrong-installation" not in caplog.text


def test_thread_start_failure_leaves_no_claim_of_a_running_worker(monkeypatch):
    worker = RecurrenceWorker(lambda _: FixedRun("complete"))

    def fail(_):
        raise RuntimeError("fixture-thread-start")

    with monkeypatch.context() as patch:
        patch.setattr(Thread, "start", fail)
        with pytest.raises(RuntimeError, match="fixture-thread-start"):
            worker.start()
    assert not worker.is_running and worker.last_run is None
    worker.close()


def test_stop_before_scheduled_thread_entry_prevents_its_first_tick(monkeypatch):
    worker = RecurrenceWorker(lambda _: pytest.fail("A cancelled entry cannot start a tick"))
    entered, release = Event(), Event()
    original = worker._run

    def delayed():
        entered.set()
        assert release.wait(5)
        original()

    monkeypatch.setattr(worker, "_run", delayed)
    worker.start()
    assert entered.wait(5)
    closer = Thread(target=worker.close)
    closer.start()
    try:
        assert worker._stop.wait(5)
    finally:
        release.set()
        closer.join(5)
        worker.close()
    assert not worker.is_running and worker.last_run is None
