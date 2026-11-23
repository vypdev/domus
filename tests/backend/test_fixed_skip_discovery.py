"""Read-only skip discovery shares current write eligibility and preserves original proof."""

from dataclasses import replace
from datetime import datetime, time, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from test_recurrence_review import fixed_move, fixed_skip_fixture, reviewed
from test_task_commands import counts

from domus.application.recurrence_review import ReviewAction
from domus.application.task_commands import TaskCommands
from domus.application.task_requests import AssignTask, CompleteTask, ReopenTask, TransitionTask
from domus.domain.errors import Conflict, Forbidden, IntegrationUnavailable, StorageFailure
from domus.domain.identity import HumanIdentity
from domus.domain.recurrence_time import NominalTime
from domus.domain.task_values import OccurrenceState
from domus.infrastructure.sqlite import SQLiteDatabase
from domus.infrastructure.sqlite_tasks import SQLiteTasks


@pytest.mark.parametrize("timed", [False, True])
def test_settled_skip_is_not_offered_again_and_original_remains_read_only(tmp_path, timed):
    service, selection, _, _ = fixed_skip_fixture(tmp_path, timed=timed)
    before = service.target(selection.occurrence_id)
    assert "fixed-skip" in before.actions
    _, request = reviewed(service, selection)
    receipt = service.apply("skip", request)
    restarted = replace(
        service,
        transactions=SQLiteDatabase(service.transactions.path, service.installation),
    )
    settled_counts = counts(service.transactions)
    target = restarted.target(selection.occurrence_id)
    assert target.actions == tuple(action for action in before.actions if action != "fixed-skip")
    assert target.occurrence_revision == receipt.result.decode()["work"]["revision"]
    assert target.slot_key == before.slot_key
    assert restarted.original(ReviewAction.APPLY, "skip") == receipt
    assert counts(service.transactions) == settled_counts


@pytest.mark.parametrize("timed", [False, True])
@pytest.mark.parametrize("assigned", [False, True])
def test_overdue_unstarted_work_remains_eligible_with_or_without_an_assignee(
    tmp_path, timed, assigned
):
    service, selection, _, _ = fixed_skip_fixture(tmp_path, timed=timed)
    if assigned:
        tasks = TaskCommands(
            service.transactions, service.actor, service.clock, service.identifiers
        )
        tasks.assign("assign", AssignTask(selection.occurrence_id, 1, ("child",)))
    before = counts(service.transactions)
    target = service.target(selection.occurrence_id)
    assert "fixed-skip" in target.actions
    assert target.occurrence_revision == (2 if assigned else 1)
    assert counts(service.transactions) == before


@pytest.mark.parametrize("timed", [False, True])
@pytest.mark.parametrize("offset", [-1, 0, 1])
def test_skip_discovery_uses_strict_instant_and_whole_local_date_boundaries(
    tmp_path, timed, offset
):
    service, selection, _, _ = fixed_skip_fixture(tmp_path, timed=timed)
    with service.transactions.read() as unit:
        slot = unit.recurrence.slot("home", selection.slot_key)
    if timed:
        boundary = slot.planned.resolved.instant_ms
    else:
        midnight = NominalTime(
            datetime.combine(slot.planned.nominal.local + timedelta(days=1), time.min)
        )
        boundary = service.planner.times.resolve(midnight, slot.schedule.policy).instant_ms
    clock = SimpleNamespace(now=lambda: boundary + offset)
    before = counts(service.transactions)
    target = replace(service, clock=clock).target(selection.occurrence_id)
    expected = offset > 0 if timed else offset >= 0
    assert ("fixed-skip" in target.actions) is expected
    assert counts(service.transactions) == before


@pytest.mark.parametrize("state", ["started", "blocked", "cancelled", "completed", "reopened"])
def test_performed_or_settled_work_cannot_reacquire_skip_eligibility(tmp_path, state):
    service, selection, _, _ = fixed_skip_fixture(tmp_path)
    tasks = TaskCommands(service.transactions, service.actor, service.clock, service.identifiers)
    oid = selection.occurrence_id
    if state == "cancelled":
        tasks.transition("cancel", TransitionTask(oid, 1, OccurrenceState.CANCELLED, "Not needed"))
    elif state in ("started", "blocked"):
        tasks.assign("assign", AssignTask(oid, 1, ("child",)))
        tasks.transition("start", TransitionTask(oid, 2, OccurrenceState.IN_PROGRESS))
        if state == "blocked":
            tasks.transition("block", TransitionTask(oid, 3, OccurrenceState.BLOCKED, "Waiting"))
    else:
        tasks.complete("complete", CompleteTask(oid, 1, ("child",), 90))
        if state == "reopened":
            with service.transactions.read() as unit:
                work = unit.tasks.occurrence("home", oid)
            tasks.reopen("reopen", ReopenTask(oid, work.revision, work.current_cycle_id, "Redo"))
            with service.transactions.read() as unit:
                assert unit.tasks.occurrence("home", oid).state is OccurrenceState.AVAILABLE
    before = counts(service.transactions)
    target = service.target(oid)
    assert "fixed-skip" not in target.actions
    with pytest.raises(Conflict, match="recurrence_skip_incompatible"):
        service.preview(
            "fresh-skip", replace(selection, occurrence_revision=target.occurrence_revision)
        )
    assert counts(service.transactions) == before


@pytest.mark.parametrize("timed", [False, True])
def test_a_rescheduled_deadline_controls_discovery_instead_of_the_original_slot(tmp_path, timed):
    service, move, _, _ = fixed_move(tmp_path, timed=timed)
    assert "fixed-skip" in service.target(move.occurrence_id).actions
    _, request = reviewed(service, move)
    original = service.apply("move", request)
    before = counts(service.transactions)
    assert "fixed-skip" not in service.target(move.occurrence_id).actions
    with service.transactions.read() as unit:
        slot = unit.recurrence.slot("home", move.slot_key)
    if timed:
        boundary = (
            service.planner.times.resolve(move.destination, slot.schedule.policy).instant_ms + 1
        )
    else:
        midnight = NominalTime(
            datetime.combine(move.destination.local + timedelta(days=1), time.min)
        )
        boundary = service.planner.times.resolve(midnight, slot.schedule.policy).instant_ms
    later = replace(service, clock=SimpleNamespace(now=lambda: boundary))
    assert "fixed-skip" in later.target(move.occurrence_id).actions
    assert later.original(ReviewAction.APPLY, "move") == original
    assert counts(service.transactions) == before


@pytest.mark.parametrize("opt_in", [False, True])
def test_opt_in_and_current_authority_are_checked_before_reading_time(tmp_path, opt_in):
    service, selection, _, _ = fixed_skip_fixture(tmp_path, opt_in=opt_in)
    clock = Mock()
    clock.now.side_effect = IntegrationUnavailable("clock_unavailable")
    service = replace(service, clock=clock)
    before = counts(service.transactions)
    if not opt_in:
        assert "fixed-skip" not in service.target(selection.occurrence_id).actions
        clock.now.assert_not_called()
    service.actor.human = HumanIdentity("ha_child", False, True, False)
    with pytest.raises(Forbidden):
        service.target(selection.occurrence_id)
    clock.now.assert_not_called()
    assert counts(service.transactions) == before


@pytest.mark.parametrize("timed", [False, True])
def test_an_unproven_effective_deadline_is_not_offered(tmp_path, timed):
    service, selection, _, _ = fixed_skip_fixture(tmp_path, timed=timed)
    with service.transactions.write() as unit:
        work = unit.tasks.occurrence("home", selection.occurrence_id)
        unit.tasks.save_occurrence(replace(work, due_at=1, revision=2), 1)
    before = counts(service.transactions)
    assert "fixed-skip" not in service.target(selection.occurrence_id).actions
    assert counts(service.transactions) == before


@pytest.mark.parametrize("failure", ["time", "storage", "unexpected_conflict"])
def test_discovery_propagates_unavailable_or_unexpected_facts(tmp_path, monkeypatch, failure):
    from domus.application import fixed_skip_review

    service, selection, _, _ = fixed_skip_fixture(tmp_path)
    before = counts(service.transactions)
    if failure == "time":
        monkeypatch.setattr(type(service.planner.times), "local_at", lambda *_: None)
        error, code = IntegrationUnavailable, "recurrence_time_source_invalid"
    elif failure == "storage":

        def unavailable(*_):
            raise StorageFailure("storage_unavailable")

        monkeypatch.setattr(SQLiteTasks, "latest_reschedule", unavailable)
        error, code = StorageFailure, "storage_unavailable"
    else:

        def unexpected(*_):
            raise Conflict("unexpected_recurrence_failure")

        monkeypatch.setattr(fixed_skip_review, "fixed_skip_plan", unexpected)
        error, code = Conflict, "unexpected_recurrence_failure"
    with pytest.raises(error, match=code):
        service.target(selection.occurrence_id)
    assert counts(service.transactions) == before
