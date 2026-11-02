"""Cancellation around provider and writer admission preserves every original business fact."""

from contextlib import contextmanager
from dataclasses import replace
from threading import Event
from types import SimpleNamespace

from test_fixed_materialization import configured
from test_task_commands import counts

from domus.infrastructure.recurrence_time import PinnedRecurrenceTime


def test_stop_before_policy_lookup_does_no_external_or_business_work(tmp_path, monkeypatch):
    import pytest

    service, store, _, _, rule_id, before = configured(tmp_path)

    def denied(*args, **kwargs):
        pytest.fail("Stopped maintenance contacted the policy source")

    monkeypatch.setattr(PinnedRecurrenceTime, "require_policy", denied)
    initial = counts(store)
    assert service.step(rule_id, before, should_continue=lambda: False).status == "stopped"
    assert counts(store) == initial


def test_stop_while_entering_the_writer_leaves_no_effect_or_allocated_identity(tmp_path):
    service, store, _, identifiers, rule_id, before = configured(tmp_path)
    stopped = Event()
    initial = counts(store)
    allocated = identifiers.count

    @contextmanager
    def stopping_writer():
        with store.write() as unit:
            stopped.set()
            yield unit

    service = replace(service, transactions=SimpleNamespace(read=store.read, write=stopping_writer))
    result = service.step(rule_id, before, should_continue=lambda: not stopped.is_set())
    assert result.status == "stopped" and result.receipt is None
    assert counts(store) == initial and identifiers.count == allocated
