"""Background task creation uses a current rule grant rather than a human identity."""

from dataclasses import replace
from unittest.mock import Mock

import pytest
from test_household_commands import Clock, Identifiers
from test_scheduled_automation_storage import source

from domus.application.automation_scheduled_authority import (
    ADMIT_SCHEDULED_AUTOMATION,
    RUN_SCHEDULED_AUTOMATION,
    ScheduledRuleAuthority,
)
from domus.application.fixed_materialization import MaintenanceScope
from domus.application.task_creation import TaskCreation
from domus.application.task_creation_command import TaskCreationCommand
from domus.application.task_requests import CreateTask
from domus.domain.automation_scheduling import ScheduledOutcome
from domus.domain.errors import Forbidden, StorageFailure
from domus.domain.storage import CommandKey, Installation
from domus.domain.task_values import TaskContent, TaskOverrides
from domus.infrastructure.sqlite import SQLiteOutbox


def authority(store, run, action="task.create", request=None):
    command = CommandKey("home", run.grant.principal, action, run.key)
    return ScheduledRuleAuthority(
        MaintenanceScope(store.installation, "home"), run, command, request
    )


def command(store, run, request):
    access = authority(store, run, request=request)
    return TaskCreationCommand(store, access, Clock(), Identifiers()), access.command


def test_exact_delegated_task_uses_the_ordinary_policy_occurrence_and_outbox(tmp_path):
    store, _, run = source(tmp_path)
    request = CreateTask(run.grant.draft.rule.task)
    with store.write() as unit:
        unit.scheduled_automations.admit(run)
    commands, key = command(store, run, request)
    first = commands.execute(key, request)
    assert first.command.actor_id == run.grant.principal
    assert first.result.decode()["state"] == "available"
    assert commands.execute(key, request) == first
    with store.read() as unit:
        work = unit.tasks.occurrence("home", first.result.decode()["occurrence_id"])
        assert work.definition_snapshot.content == run.grant.draft.rule.task
        assert work.definition_snapshot.overrides == TaskOverrides()
        assert unit.tasks.policy("home").revision == 1
        assert unit.receipts.get(key) == first
        assert unit.audit.entries("home")[-1].operation_id == first.operation_id
        assert unit.outbox.pending()[-1].event_id == first.operation_id


def test_the_callers_transaction_rolls_back_task_and_receipt_before_identical_retry(
    tmp_path, monkeypatch
):
    store, _, run = source(tmp_path)
    request = CreateTask(run.grant.draft.rule.task)
    with store.write() as unit:
        unit.scheduled_automations.admit(run)
    commands, key = command(store, run, request)
    with monkeypatch.context() as patch:
        patch.setattr(
            SQLiteOutbox, "append", Mock(side_effect=StorageFailure("injected_outbox_failure"))
        )
        with pytest.raises(StorageFailure, match="injected_outbox_failure"):
            with store.write() as unit:
                commands.execute(key, request, unit)
    with store.read() as unit:
        assert unit.tasks.definitions("home") == ()
        assert unit.receipts.get(key) is None
        assert unit.scheduled_automations.run("home", run.key) == run
    with store.write() as unit:
        first = commands.execute(key, request, unit)
    with store.read() as unit:
        assert len(unit.tasks.definitions("home")) == 1
        assert unit.receipts.get(key) == first


@pytest.mark.parametrize("change", ["disable", "regrant", "revision", "missing", "installation"])
def test_grant_is_rechecked_before_a_new_effect_or_an_original_receipt_lookup(tmp_path, change):
    store, schedule, run = source(tmp_path)
    request = CreateTask(run.grant.draft.rule.task)
    with store.write() as unit:
        unit.scheduled_automations.admit(run)
    commands, key = command(store, run, request)
    first = commands.execute(key, request)
    with store.write() as unit:
        previous = unit.automation_controls.get("home", "daily")
        if change == "disable":
            unit.automation_controls.save(
                "home", replace(previous, control_revision=2, enabled=False), 1
            )
        elif change == "revision":
            draft = replace(run.grant.draft, revision=2)
            unit.automation_drafts.append("home", draft)
            unit.automation_controls.save(
                "home", replace(previous, control_revision=2, rule_revision=2), 1
            )
        elif change == "regrant":
            unit.scheduled_automations.save_schedule(
                replace(
                    schedule, revision=2, grant=replace(schedule.grant, grant_id="replacement")
                ),
                1,
            )
        elif change == "missing":
            unit.scheduled_automations.finish(
                run.finish(
                    ScheduledOutcome.NO_TASK,
                    run.admitted_at,
                )
            )
        else:
            commands = replace(
                commands,
                authorization=replace(
                    commands.authorization,
                    scope=MaintenanceScope(
                        Installation(store.installation.instance_id, "stable"), "home"
                    ),
                ),
            )
    with pytest.raises(Forbidden):
        commands.execute(key, request)
    with store.read() as unit:
        assert unit.receipts.get(key) == first and len(unit.tasks.definitions("home")) == 1


@pytest.mark.parametrize(
    "payload",
    [
        CreateTask(TaskContent("Other title")),
        CreateTask(TaskContent("Daily rule task"), overrides=TaskOverrides(point_value_minor=100)),
        CreateTask(TaskContent("Daily rule task", description="undelegated")),
        CreateTask(TaskContent("Daily rule task"), materials=()),
    ],
)
def test_grant_cannot_expand_its_approved_task_payload(tmp_path, payload):
    store, _, run = source(tmp_path)
    with store.write() as unit:
        unit.scheduled_automations.admit(run)
    commands, key = command(store, run, payload)
    with pytest.raises(Forbidden, match="daily_automation_capability_denied"):
        commands.execute(key, payload)
    with store.read() as unit:
        assert unit.tasks.definitions("home") == () and unit.receipts.get(key) is None


def test_foreign_commands_and_non_task_actions_never_reach_task_creation(tmp_path):
    store, _, run = source(tmp_path)
    request = CreateTask(run.grant.draft.rule.task)
    access = authority(store, run, request=request)
    with store.write() as unit:
        unit.scheduled_automations.admit(run)
        for key in (
            replace(access.command, household_id="other"),
            replace(access.command, actor_id="ha_admin"),
            replace(access.command, action="task.complete"),
            replace(access.command, key="another-trigger"),
        ):
            with pytest.raises(Forbidden):
                replace(access, command=key).require(key, unit)
        with pytest.raises(Forbidden):
            access.require(replace(access.command, key="other"), unit)
    commands = TaskCreationCommand(store, access, Clock(), Identifiers())
    with pytest.raises(Forbidden, match="permission_denied"):
        commands.execute(replace(access.command, action="task.complete"), request)
    with store.write() as unit:
        with pytest.raises(Forbidden, match="permission_denied"):
            TaskCreation(Clock(), Identifiers()).materials(unit, None, "home")


def test_admission_and_execution_are_distinct_narrow_authorities(tmp_path):
    store, schedule, run = source(tmp_path)
    admission = authority(store, run, ADMIT_SCHEDULED_AUTOMATION)
    execution = authority(store, run, RUN_SCHEDULED_AUTOMATION)
    with store.write() as unit:
        admission.require(admission.command, unit)
        with pytest.raises(Forbidden):
            execution.require(execution.command, unit)
        unit.scheduled_automations.admit(run)
        execution.require(execution.command, unit)
        with pytest.raises(Forbidden):
            replace(execution, task=CreateTask(run.grant.draft.rule.task)).require(
                execution.command, unit
            )
        with pytest.raises(Forbidden):
            replace(admission, run=replace(run, control_revision=2)).require(
                admission.command, unit
            )
