"""Relative obligations preserve actual work, exact source scope and cycle-stable identity."""

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta

import pytest
from test_tasks import cycle, restricted_cycle

from domus.domain.errors import InvalidInput
from domus.domain.identity import Role
from domus.domain.recurrence_planning import PlannedSlot
from domus.domain.recurrence_records import ScheduleState
from domus.domain.recurrence_rules import NominalDate
from domus.domain.recurrence_time import LocalInstant, NominalTime, RelativeInterval, TimePolicy
from domus.domain.relative_recurrence import (
    RelativeProgress,
    RelativeSchedule,
    RelativeSlot,
    RelativeSource,
    SuccessorVisibility,
)
from domus.domain.storage import Installation
from domus.domain.task_values import TaskPerformer, VerificationState
from domus.infrastructure.recurrence_time import PinnedRecurrenceTime


def values(timed=True, *, restricted=False):
    times = PinnedRecurrenceTime()
    policy = TimePolicy("UTC", times.data_identity)
    initial_time = NominalTime(datetime(2026, 3, 1, 12))
    initial = PlannedSlot(
        initial_time if timed else NominalDate(initial_time.local.date()),
        times.resolve(initial_time, policy) if timed else None,
    )
    schedule = RelativeSchedule(
        "relative", "home", "definition", initial, RelativeInterval(30), policy, 100
    )
    local = times.local_at(1_774_872_000_123, policy)
    completed = (restricted_cycle if restricted else cycle)(
        performed_at=local.instant_ms, recorded_at=local.instant_ms + 1
    )
    source = RelativeSource.from_cycle(completed, local)
    due = times.after_local_days(completed.performed_at, schedule.interval, policy)
    planned = PlannedSlot(
        due.nominal if timed else NominalDate(due.nominal.local.date()), due if timed else None
    )
    slot = RelativeSlot(
        Installation("00000000-0000-0000-0000-000000000001", "edge"),
        schedule,
        planned,
        "next",
        local.instant_ms + 100,
        source,
    )
    return schedule, RelativeProgress("relative", "home", 1), slot, completed


@pytest.mark.parametrize("timed", [False, True])
def test_initial_obligation_and_successor_have_distinct_cycle_stable_scoped_keys(timed):
    schedule, progress, successor, _ = values(timed)
    initial = RelativeSlot(successor.installation, schedule, schedule.initial, "first", 101)
    assert initial.key != successor.key and len(initial.key) == len(successor.key) == 64
    assert initial.command.actor_id == successor.command.actor_id == "system:recurrence"
    assert initial.command.action == successor.command.action == "recurrence.materialize"
    assert progress.matches_schedule(schedule) and progress.current_occurrence_id is None
    paused = replace(schedule, state=ScheduleState.PAUSED, revision=2)
    assert replace(successor, schedule=paused).key == successor.key
    assert (
        replace(successor, occurrence_id="another", created_at=successor.created_at + 1).key
        == successor.key
    )
    assert (
        replace(
            successor,
            source=replace(
                successor.source, cycle=replace(successor.source.cycle, cycle_id="new-cycle")
            ),
        ).key
        != successor.key
    )
    assert (
        replace(successor, installation=replace(successor.installation, channel="stable")).key
        != successor.key
    )
    assert initial.consistent_with(paused) and successor.consistent_with(paused)
    with pytest.raises(FrozenInstanceError):
        schedule.revision = 2


@pytest.mark.parametrize("visibility", list(SuccessorVisibility))
def test_successor_eligibility_observes_verification_without_changing_actual_work(visibility):
    schedule, _, _, adult = values()
    schedule = replace(schedule, visibility=visibility)
    child = restricted_cycle(performed_at=adult.performed_at, recorded_at=adult.recorded_at)
    approved = child.verify(
        VerificationState.APPROVED, TaskPerformer("adult", Role.ADULT), child.recorded_at + 100
    )
    rejected = child.verify(
        VerificationState.REJECTED,
        TaskPerformer("adult", Role.ADULT),
        child.recorded_at + 100,
        "Repeat",
    )
    assert schedule.allows_successor(adult)
    assert schedule.allows_successor(child) == (visibility is SuccessorVisibility.AT_COMPLETION)
    assert schedule.allows_successor(approved)
    assert not schedule.allows_successor(rejected) and not schedule.allows_successor(
        adult.close(adult.recorded_at + 1)
    )
    assert not replace(schedule, state=ScheduleState.PAUSED).allows_successor(adult)


def test_approval_and_reopening_cannot_rewrite_the_original_completion_basis():
    schedule, _, slot, completed = values(restricted=True)
    approved = completed.verify(
        VerificationState.APPROVED, TaskPerformer("adult", Role.ADULT), completed.recorded_at + 100
    )
    assert RelativeSource.from_cycle(approved, slot.source.performed_local) == slot.source
    assert (
        RelativeSource.from_cycle(
            approved.close(approved.verified_at + 1), slot.source.performed_local
        )
        == slot.source
    )
    with pytest.raises(InvalidInput):
        replace(slot.source, cycle=approved)
    assert schedule.visibility is SuccessorVisibility.AT_COMPLETION


@pytest.mark.parametrize(
    "field,value",
    [
        ("schedule_id", ""),
        ("household_id", ""),
        ("definition_id", ""),
        ("initial", None),
        ("interval", 30),
        ("policy", None),
        ("state", "active"),
        ("visibility", "at_completion"),
        ("revision", True),
        ("pattern_revision", 0),
        ("pattern_revision", 2),
        ("created_at", -1),
    ],
)
def test_relative_rules_reject_untyped_or_unscoped_configuration(field, value):
    with pytest.raises(InvalidInput):
        replace(values()[0], **{field: value})


@pytest.mark.parametrize(
    "field,value",
    [
        ("schedule_id", ""),
        ("household_id", ""),
        ("pattern_revision", True),
        ("source_after", -1),
        ("source_after", True),
        ("source_after", 2**63),
        ("revision", 0),
        ("last_run_at", -1),
        ("current_occurrence_id", "next"),
        ("current_slot_key", "slot"),
    ],
)
def test_progress_never_invents_half_a_current_obligation_or_a_source_position(field, value):
    with pytest.raises(InvalidInput):
        replace(values()[1], **{field: value})


@pytest.mark.parametrize(
    "field,value", [("schedule_id", "other"), ("household_id", "other"), ("pattern_revision", 2)]
)
def test_relative_progress_requires_the_exact_rule_generation(field, value):
    schedule, progress, _, _ = values()
    assert not replace(progress, **{field: value}).matches_schedule(schedule)


def test_successor_validates_actual_performed_instant_household_and_local_day_arithmetic():
    schedule, _, slot, _ = values()
    with pytest.raises(InvalidInput):
        replace(
            slot,
            source=replace(
                slot.source,
                performed_local=replace(
                    slot.source.performed_local, policy=replace(schedule.policy, revision=2)
                ),
            ),
        )
    with pytest.raises(InvalidInput):
        replace(
            slot.source,
            cycle=replace(slot.source.cycle, performed_at=slot.source.cycle.performed_at - 1),
        )
    with pytest.raises(InvalidInput):
        replace(
            slot,
            source=replace(slot.source, cycle=replace(slot.source.cycle, household_id="other")),
        )
    with pytest.raises(InvalidInput):
        replace(slot, occurrence_id=slot.source.cycle.occurrence_id)
    with pytest.raises(InvalidInput):
        replace(slot, created_at=100)
    wrong = NominalTime(slot.planned.nominal.local + timedelta(days=1))
    with pytest.raises(InvalidInput):
        replace(
            slot, planned=PlannedSlot(wrong, PinnedRecurrenceTime().resolve(wrong, schedule.policy))
        )


def test_relative_slot_rejects_wrong_initial_due_and_future_or_contradictory_generations():
    schedule, _, slot, _ = values()
    with pytest.raises(InvalidInput):
        replace(slot, source=None)
    assert slot.consistent_with(
        replace(schedule, interval=RelativeInterval(31), pattern_revision=2, revision=2)
    )
    assert not slot.consistent_with(replace(schedule, interval=RelativeInterval(31)))
    assert not slot.consistent_with(replace(schedule, definition_id="other"))
    assert not replace(slot, schedule=replace(schedule, revision=2)).consistent_with(schedule)


def test_epoch_local_fact_may_precede_1970_without_accepting_a_user_nominal_before_1970():
    policy = TimePolicy("America/New_York", PinnedRecurrenceTime().data_identity)
    local = LocalInstant(0, datetime(1969, 12, 31, 19), -18000, policy, "a" * 64)
    assert local.instant_ms == 0
    with pytest.raises(InvalidInput):
        NominalTime(local.local)


@pytest.mark.parametrize("source", [None, "cycle"])
def test_relative_source_and_eligibility_refuse_untyped_or_foreign_cycles(source):
    schedule, _, slot, _ = values()
    with pytest.raises(InvalidInput):
        RelativeSource.from_cycle(source, slot.source.performed_local)
    with pytest.raises(InvalidInput):
        schedule.allows_successor(source)
    with pytest.raises(InvalidInput):
        schedule.allows_successor(replace(slot.source.cycle, household_id="other"))


@pytest.mark.parametrize(
    "field,value",
    [("installation", None), ("schedule", None), ("planned", None), ("source", "cycle")],
)
def test_relative_slots_never_coerce_untyped_records(field, value):
    with pytest.raises(InvalidInput):
        replace(values()[2], **{field: value})


def test_relative_sources_fail_when_local_calendar_addition_overflows():
    from domus.domain.recurrence_time import MAX_INSTANT_MS

    schedule, _, slot, _ = values(False)
    local = PinnedRecurrenceTime().local_at(MAX_INSTANT_MS, schedule.policy)
    source = RelativeSource.from_cycle(
        cycle(performed_at=MAX_INSTANT_MS, recorded_at=MAX_INSTANT_MS), local
    )
    with pytest.raises(InvalidInput, match="recurrence_time_out_of_range"):
        replace(slot, source=source, created_at=MAX_INSTANT_MS)
