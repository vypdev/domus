"""Real pinned local-day planning uses the original performed instant, never approval time."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from test_recurrence_local_instant import instant
from test_relative_recurrence_records import values
from test_tasks import restricted_cycle

from domus.application.relative_recurrence import RelativeRecurrencePlanner
from domus.domain.errors import IntegrationUnavailable
from domus.domain.identity import Role
from domus.domain.recurrence_planning import PlannedSlot
from domus.domain.recurrence_records import ScheduleState
from domus.domain.recurrence_rules import NominalDate
from domus.domain.recurrence_time import NominalTime, RelativeInterval, TimePolicy
from domus.domain.relative_recurrence import SuccessorVisibility
from domus.domain.task_values import TaskPerformer, VerificationState
from domus.infrastructure.recurrence_time import PinnedRecurrenceTime


@pytest.mark.parametrize("timed", [False, True])
def test_approval_days_later_keeps_the_actual_performed_local_day_and_original_source(timed):
    schedule, _, _, _ = values(timed)
    times = PinnedRecurrenceTime()
    policy = TimePolicy("Europe/Madrid", times.data_identity)
    initial = NominalTime(datetime(2026, 3, 1, 13))
    schedule = replace(
        schedule,
        policy=policy,
        interval=RelativeInterval(1),
        initial=PlannedSlot(initial, times.resolve(initial, policy))
        if timed
        else PlannedSlot(NominalDate(initial.local.date()), None),
    )
    performed = instant(datetime(2026, 3, 28, 12, 0, 0, 123000, tzinfo=UTC))
    child = restricted_cycle(performed_at=performed, recorded_at=performed + 1)
    approved = child.verify(
        VerificationState.APPROVED, TaskPerformer("adult", Role.ADULT), performed + 5 * 86_400_000
    )
    planner = RelativeRecurrencePlanner(times)
    first = planner.plan(schedule, child)
    assert first.status == "ready"
    assert planner.plan(schedule, approved) == first
    verified = replace(schedule, visibility=SuccessorVisibility.AT_VERIFICATION)
    assert planner.plan(verified, child).status == "waiting_verification"
    later = planner.plan(verified, approved)
    assert (
        later.status == "ready" and later.source == first.source and later.planned == first.planned
    )
    assert first.source.cycle == child and first.source.performed_local.instant_ms == performed
    if timed:
        assert first.planned.nominal.local == datetime(2026, 3, 29, 13, 0, 0, 123000)
        assert first.planned.resolved.instant_ms - performed == 23 * 3_600_000
    else:
        assert first.planned.nominal.local == datetime(2026, 3, 29).date()
        assert first.planned.resolved is None


@pytest.mark.parametrize("change", ["paused", "retired", "pending", "rejected", "reopened"])
def test_ineligible_or_inactive_source_requires_no_provider_work(change):
    schedule, _, _, completed = values(restricted=True)
    if change in ("paused", "retired"):
        schedule = replace(schedule, state=ScheduleState(change))
    elif change == "pending":
        schedule = replace(schedule, visibility=SuccessorVisibility.AT_VERIFICATION)
    elif change == "rejected":
        completed = completed.verify(
            VerificationState.REJECTED,
            TaskPerformer("adult", Role.ADULT),
            completed.recorded_at + 1,
            "Repeat",
        )
    else:
        completed = completed.close(completed.recorded_at + 1)

    class Unavailable:
        def local_at(self, *_):
            pytest.fail("No provider should be needed for ineligible work")

    result = RelativeRecurrencePlanner(Unavailable()).plan(schedule, completed)
    assert result.status == (
        change
        if change in ("paused", "retired")
        else "waiting_verification"
        if change == "pending"
        else "source_closed"
    )
    assert result.planned is None and result.source is None


def test_date_only_successor_can_name_a_wholly_missing_local_date_without_inventing_an_instant():
    schedule, _, _, _ = values(False)
    times = PinnedRecurrenceTime()
    policy = TimePolicy("Pacific/Apia", times.data_identity)
    schedule = replace(schedule, policy=policy, interval=RelativeInterval(1))
    performed = instant(datetime(2011, 12, 29, 22, tzinfo=UTC))
    completed = restricted_cycle(performed_at=performed, recorded_at=performed + 1)
    result = RelativeRecurrencePlanner(times).plan(schedule, completed)
    assert result.planned.nominal.local == datetime(2011, 12, 30).date()
    assert result.planned.resolved is None


@pytest.mark.parametrize(
    "change", ["instant", "policy", "digest", "nominal", "type", "local-type", "due-policy"]
)
def test_provider_facts_must_match_original_work_and_the_exact_time_policy(change):
    schedule, _, _, completed = values()
    times = PinnedRecurrenceTime()

    class Changed:
        def local_at(self, value, policy):
            if change == "local-type":
                return None
            result = times.local_at(value + 1 if change == "instant" else value, policy)
            return (
                replace(result, policy=replace(policy, revision=2))
                if change == "policy"
                else result
            )

        def after_local_days(self, *args):
            result = times.after_local_days(*args)
            if change == "due-policy":
                return replace(result, policy=replace(result.policy, revision=2))
            if change == "digest":
                return replace(result, zone_digest="a" * 64)
            if change == "nominal":
                return times.resolve(
                    NominalTime(result.nominal.local + timedelta(days=1)), result.policy
                )
            return None if change == "type" else result

    with pytest.raises(IntegrationUnavailable, match="recurrence_time_source_invalid"):
        RelativeRecurrencePlanner(Changed()).plan(schedule, completed)


def test_relative_planner_keeps_out_of_range_future_work_explicit():
    from test_tasks import cycle

    from domus.domain.errors import InvalidInput
    from domus.domain.recurrence_time import MAX_INSTANT_MS

    schedule, _, _, _ = values(False)
    completed = cycle(performed_at=MAX_INSTANT_MS, recorded_at=MAX_INSTANT_MS)
    with pytest.raises(InvalidInput, match="recurrence_time_out_of_range"):
        RelativeRecurrencePlanner(PinnedRecurrenceTime()).plan(schedule, completed)


def test_real_task_lifecycle_facts_plan_the_same_work_after_approval_and_close_after_reopening(
    tmp_path,
):
    from test_task_commands import counts
    from test_task_events import prepared

    from domus.application.task_commands import ReopenTask, VerifyTask
    from domus.application.task_events import TaskEventFeed
    from domus.domain.relative_recurrence import RelativeSlot

    commands, store, _, _, oid, done = prepared(tmp_path, child=True)
    cid = done.result.decode()["cycle"]["cycle_id"]
    feed = TaskEventFeed(store, store.installation)
    first = feed.read().items[0]
    schedule, _, _, _ = values()
    schedule = replace(schedule, definition_id=first.definition_id)
    planner = RelativeRecurrencePlanner(PinnedRecurrenceTime())
    original = planner.plan(schedule, first.cycle)
    waiting = replace(schedule, visibility=SuccessorVisibility.AT_VERIFICATION)
    assert (
        original.status == "ready"
        and planner.plan(waiting, first.cycle).status == "waiting_verification"
    )
    commands.verify("verify", VerifyTask(oid, 2, cid, VerificationState.APPROVED))
    with store.read() as unit:
        actual = unit.tasks.cycle("home", cid)
    assert planner.plan(schedule, actual) == original
    verified = planner.plan(waiting, actual)
    assert verified.source == original.source and verified.planned == original.planned
    commands.reopen("reopen", ReopenTask(oid, 3, cid, "Repeat work"))
    before = counts(store)
    events = feed.read().items
    for event in events:
        with store.read() as unit:
            current = unit.tasks.cycle("home", event.cycle.cycle_id)
        assert planner.plan(schedule, current).status == "source_closed"
    assert len(events) == 3 and counts(store) == before
    # Planning is read-only; this value is not a persisted successor or consumer receipt.
    slot = RelativeSlot(
        store.installation, schedule, original.planned, "successor", 100, original.source
    )
    assert (
        slot.source.cycle == first.cycle
        and slot.planned.resolved.instant_ms == 90 + 30 * 86_400_000
    )
