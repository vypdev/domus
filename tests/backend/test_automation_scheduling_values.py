"""Daily authority belongs to the rule and logical triggers survive binding changes."""

from dataclasses import replace
from datetime import date, datetime

import pytest

from domus.domain.automation import AutomationControl, AutomationDraft, AutomationRule, DailyTrigger
from domus.domain.automation_scheduling import (
    DailyAutomationSchedule,
    DailySuppression,
    RuleExecutionGrant,
    ScheduledAutomationRun,
    ScheduledOutcome,
)
from domus.domain.errors import Conflict, InvalidInput
from domus.domain.fold_policy import FoldPolicy
from domus.domain.recurrence_time import MAX_INSTANT_MS, NominalTime, TimePolicy
from domus.domain.storage import Installation
from domus.domain.task_values import TaskContent
from domus.infrastructure.recurrence_time import PinnedRecurrenceTime

INSTALLATION = Installation("25a2ec31-0190-42f2-815e-f784b8661b14", "edge")


def grant():
    rule = AutomationRule(2, DailyTrigger("02:30"), None, TaskContent("Daily rule task"))
    return RuleExecutionGrant(INSTALLATION, "home", "grant-1", AutomationDraft("daily", 1, rule))


def planned(zone="Europe/Madrid", fold=FoldPolicy.FIRST):
    times = PinnedRecurrenceTime()
    return times.resolve(
        NominalTime(datetime(2026, 10, 25, 2, 30)), TimePolicy(zone, times.data_identity, fold)
    )


def schedule():
    value = planned()
    return DailyAutomationSchedule(grant(), 1, value.policy, value, value.instant_ms - 1000)


def run():
    value = planned()
    return ScheduledAutomationRun(grant(), 1, value, value.instant_ms)


def test_principal_is_owned_by_rule_across_regrants_and_immutable_revisions():
    original = grant()
    newer = replace(original, grant_id="grant-2", draft=replace(original.draft, revision=2))
    assert original.principal == newer.principal
    assert original.principal.startswith("system:automation:")
    assert len(original.principal) <= 128
    for changed in (
        replace(original, household_id="other"),
        replace(original, installation=replace(INSTALLATION, channel="stable")),
        replace(original, draft=replace(original.draft, rule_id="another")),
    ):
        assert changed.principal != original.principal


def test_current_binding_and_control_are_required_without_member_identity():
    value = grant()
    control = AutomationControl("daily", 1, 1, True)
    assert value.permits(INSTALLATION, "home", control, value.grant_id)
    assert value.permits(INSTALLATION, "home", replace(control, control_revision=2), value.grant_id)
    for installation, home, current, binding in (
        (replace(INSTALLATION, channel="stable"), "home", control, "grant-1"),
        (INSTALLATION, "other", control, "grant-1"),
        (INSTALLATION, "home", control, "grant-2"),
        (INSTALLATION, "home", None, "grant-1"),
        (INSTALLATION, "home", replace(control, enabled=False), "grant-1"),
        (INSTALLATION, "home", replace(control, rule_id="another"), "grant-1"),
        (INSTALLATION, "home", replace(control, rule_revision=2), "grant-1"),
    ):
        assert not value.permits(installation, home, current, binding)


def test_one_trigger_identity_is_independent_of_policy_fold_and_regrant():
    original = grant()
    first = original.trigger_key(planned())
    assert original.trigger_key(planned(fold=FoldPolicy.SECOND)) == first
    assert original.trigger_key(planned("UTC")) == first
    assert replace(original, grant_id="grant-2").trigger_key(planned()) == first
    assert (
        replace(original, draft=replace(original.draft, revision=2)).trigger_key(planned()) != first
    )
    assert run().key == first


@pytest.mark.parametrize(
    "changes",
    [
        {"installation": None},
        {"draft": None},
        {"draft": AutomationDraft("daily", 1, None)},
        {
            "draft": AutomationDraft(
                "manual", 1, AutomationRule(1, "manual", None, TaskContent("A"))
            )
        },
        {"household_id": "foreign/home"},
        {"grant_id": ""},
        {
            "draft": AutomationDraft(
                "daily",
                1,
                AutomationRule(
                    2, DailyTrigger("02:30"), None, TaskContent("A", description="undelegated")
                ),
            )
        },
    ],
)
def test_grant_is_closed_and_does_not_accept_broader_task_capability(changes):
    with pytest.raises(InvalidInput):
        replace(grant(), **changes)


@pytest.mark.parametrize(
    "value",
    [
        None,
        "02:30",
        replace(
            planned(),
            nominal=NominalTime(datetime(2026, 10, 25, 2, 31)),
            resolved_local=datetime(2026, 10, 25, 2, 31),
        ),
    ],
)
def test_trigger_requires_the_exact_approved_minute(value):
    with pytest.raises(InvalidInput, match="invalid_daily_automation_trigger"):
        grant().require_planned(value)


def test_schedule_retains_an_inspectable_bounded_suppression_and_monotone_frontier():
    value = schedule()
    evidence = DailySuppression(value.next_time, value.next_time.instant_ms + 1000)
    assert evidence.first.nominal.local == datetime(2026, 10, 25, 2, 30)
    assert replace(
        value, last_nominal=date(2026, 10, 24), suppression=evidence
    ).last_nominal == date(2026, 10, 24)


@pytest.mark.parametrize(
    "changes",
    [
        {"grant": None},
        {"policy": None},
        {"next_time": None},
        {"policy": replace(planned().policy, revision=2)},
        {"startup_cutoff_ms": planned().instant_ms},
        {"startup_cutoff_ms": True},
        {"startup_cutoff_ms": -1},
        {"startup_cutoff_ms": MAX_INSTANT_MS + 1},
        {"last_nominal": "2026-10-24"},
        {"last_nominal": date(2026, 10, 25)},
        {"suppression": "untrusted"},
        {"revision": 0},
        {"control_revision": 0},
    ],
)
def test_inconsistent_schedule_facts_are_rejected(changes):
    with pytest.raises(InvalidInput):
        replace(schedule(), **changes)


@pytest.mark.parametrize("first, through", [(None, 0), (planned(), 0)])
def test_suppression_cannot_claim_a_range_before_its_first_trigger(first, through):
    with pytest.raises(InvalidInput, match="invalid_daily_automation_suppression"):
        DailySuppression(first, through)


@pytest.mark.parametrize("outcome", list(ScheduledOutcome)[1:])
def test_run_has_one_terminal_outcome_and_keeps_original_timing(outcome):
    value = run()
    ids = (
        {"task_operation_id": "task-op", "task_occurrence_id": "task"}
        if outcome is ScheduledOutcome.CREATED
        else {}
    )
    finished = value.finish(outcome, value.admitted_at + 1000, **ids)
    assert finished.planned == value.planned and finished.key == value.key
    assert finished.outcome is outcome and finished.finished_at == value.admitted_at + 1000
    with pytest.raises(Conflict, match="daily_automation_run_finished"):
        finished.finish(ScheduledOutcome.NO_TASK, finished.finished_at)
    with pytest.raises(Conflict, match="daily_automation_run_finished"):
        value.finish(ScheduledOutcome.QUEUED, value.admitted_at)


@pytest.mark.parametrize(
    "changes",
    [
        {"grant": None},
        {"control_revision": 0},
        {"admitted_at": planned().instant_ms - 1},
        {"outcome": "created"},
        {"finished_at": planned().instant_ms},
        {"outcome": ScheduledOutcome.CANCELLED},
        {"outcome": ScheduledOutcome.NO_TASK, "finished_at": -1},
        {"task_operation_id": "op"},
        {"task_occurrence_id": "task"},
        {"outcome": ScheduledOutcome.CREATED, "finished_at": planned().instant_ms},
        {
            "outcome": ScheduledOutcome.CREATED,
            "finished_at": planned().instant_ms,
            "task_operation_id": "op",
            "task_occurrence_id": "bad/id",
        },
    ],
)
def test_run_cannot_claim_uncommitted_or_inconsistent_task_results(changes):
    with pytest.raises(InvalidInput):
        replace(run(), **changes)
