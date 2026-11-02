"""Persistable recurrence facts retain scope and nominal identity independently of authority."""

from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime

import pytest

from domus.domain.errors import InvalidInput
from domus.domain.recurrence_planning import FixedCursor, PlannedFixedSlot, cursor_binding
from domus.domain.recurrence_records import (
    FixedProgress,
    FixedSchedule,
    ScheduledSlot,
    ScheduleState,
)
from domus.domain.recurrence_rules import FixedPattern, Frequency, NominalDate
from domus.domain.recurrence_time import NominalTime, ResolvedTime, TimePolicy, TimeResolution
from domus.domain.storage import Installation


def values(timed=False):
    start = NominalTime(datetime(2026, 1, 1, 12)) if timed else NominalDate(date(2026, 1, 1))
    rule = FixedSchedule(
        "rule",
        "home",
        "definition",
        FixedPattern(start, Frequency.DAILY),
        TimePolicy("UTC", "fixture:1"),
        100,
    )
    resolved = (
        ResolvedTime(start, rule.policy, start.local, 0, TimeResolution.EXACT, "a" * 64)
        if timed
        else None
    )
    slot = ScheduledSlot(
        Installation("00000000-0000-0000-0000-000000000001", "edge"),
        rule,
        PlannedFixedSlot(start, resolved),
        "work",
        100,
    )
    progress = FixedProgress(
        "rule", "home", 1, FixedCursor(cursor_binding(rule.pattern, rule.policy))
    )
    return rule, progress, slot


@pytest.mark.parametrize("timed", [False, True])
def test_nominal_identity_survives_pause_but_not_pattern_or_ownership_change(timed):
    rule, progress, slot = values(timed)
    assert slot.command.actor_id == "system:recurrence"
    assert slot.command.action == "recurrence.materialize"
    assert slot.command.key == slot.key and slot.command.household_id == "home"
    assert slot.key == replace(slot, occurrence_id="other", created_at=101).key
    assert (
        slot.key
        == replace(slot, schedule=replace(rule, revision=2, state=ScheduleState.PAUSED)).key
    )
    assert slot.key != replace(slot, schedule=replace(rule, revision=2, pattern_revision=2)).key
    assert slot.key != replace(slot, installation=replace(slot.installation, channel="stable")).key
    assert slot.key != replace(slot, schedule=replace(rule, household_id="other")).key
    assert slot.key != replace(slot, schedule=replace(rule, schedule_id="other")).key
    assert replace(progress, cursor=replace(progress.cursor, closed=True), range_complete=True)
    with pytest.raises(FrozenInstanceError):
        rule.revision = 2


@pytest.mark.parametrize(
    "field,value",
    [
        ("schedule_id", ""),
        ("household_id", ""),
        ("definition_id", ""),
        ("pattern", None),
        ("policy", None),
        ("state", "active"),
        ("revision", True),
        ("pattern_revision", 2),
        ("created_at", -1),
    ],
)
def test_invalid_rule_facts_are_rejected(field, value):
    with pytest.raises(InvalidInput):
        replace(values()[0], **{field: value})


@pytest.mark.parametrize(
    "field,value",
    [
        ("schedule_id", ""),
        ("household_id", ""),
        ("pattern_revision", True),
        ("revision", 0),
        ("cursor", None),
        ("last_run_at", -1),
        ("range_complete", 1),
    ],
)
def test_invalid_progress_facts_are_rejected(field, value):
    with pytest.raises(InvalidInput):
        replace(values()[1], **{field: value})


def test_closed_progress_requires_explicit_range_completion():
    progress = values()[1]
    with pytest.raises(InvalidInput):
        replace(progress, cursor=replace(progress.cursor, closed=True))
    assert replace(progress, last_run_at=101)


@pytest.mark.parametrize(
    "field,value",
    [
        ("occurrence_id", ""),
        ("created_at", -1),
        ("created_at", 99),
        ("installation", None),
        ("schedule", None),
        ("planned", None),
    ],
)
def test_invalid_slot_facts_are_rejected(field, value):
    with pytest.raises(InvalidInput):
        replace(values()[2], **{field: value})


def test_slot_cannot_retag_its_rule_or_replace_the_resolved_policy():
    dated = values()[2]
    timed = values(True)[2]
    with pytest.raises(InvalidInput):
        replace(dated, planned=timed.planned)
    with pytest.raises(InvalidInput):
        replace(
            timed, schedule=replace(timed.schedule, policy=TimePolicy("Europe/Madrid", "fixture:1"))
        )


def test_record_relationships_bind_scope_count_and_current_or_historical_generations():
    rule, progress, slot = values()
    assert progress.matches_schedule(rule) and slot.consistent_with(rule)
    for different in [
        replace(rule, schedule_id="other"),
        replace(rule, household_id="other"),
        replace(rule, pattern_revision=2, revision=2),
        replace(rule, policy=TimePolicy("Europe/Madrid", "fixture:1")),
    ]:
        assert not progress.matches_schedule(different)
    limited = replace(rule, pattern=replace(rule.pattern, count=1))
    end = replace(
        progress,
        cursor=replace(
            progress.cursor,
            binding=cursor_binding(limited.pattern, limited.policy),
            nominal_count=1,
        ),
    )
    assert end.matches_schedule(limited)
    assert not replace(end, cursor=replace(end.cursor, nominal_count=2)).matches_schedule(limited)
    assert slot.consistent_with(replace(rule, revision=2, state=ScheduleState.PAUSED))
    assert slot.consistent_with(
        replace(rule, revision=2, pattern_revision=2, pattern=replace(rule.pattern, interval=2))
    )
    for different in [
        replace(rule, schedule_id="other"),
        replace(rule, household_id="other"),
        replace(rule, definition_id="other"),
        replace(rule, created_at=101),
        replace(rule, pattern=replace(rule.pattern, interval=2)),
        replace(rule, policy=TimePolicy("Europe/Madrid", "fixture:1")),
    ]:
        assert not slot.consistent_with(different)
    assert not replace(slot, schedule=replace(rule, revision=2)).consistent_with(rule)
    assert not replace(
        slot, schedule=replace(rule, revision=2, pattern_revision=2)
    ).consistent_with(rule)
    assert not replace(
        slot, schedule=replace(rule, revision=2, pattern_revision=2)
    ).consistent_with(replace(rule, revision=2))
