"""Actual authorized scheduled creation retains one atomic rule and no accidental manual work."""

from dataclasses import replace
from datetime import date, datetime

import pytest
from test_household_commands import Clock
from test_task_commands import counts, fixture

from domus.application.fixed_recurrence import FixedRecurrencePlanner
from domus.application.recurrence_commands import CreateFixedTask, RecurrenceCommands
from domus.application.task_requests import CreateTask
from domus.domain.errors import (
    Conflict,
    Forbidden,
    IdentityUnavailable,
    InvalidInput,
    StorageFailure,
)
from domus.domain.identity import HumanIdentity, MemberStatus, Permission, PermissionRule, Role
from domus.domain.recurrence_planning import cursor_binding
from domus.domain.recurrence_records import ScheduleState
from domus.domain.recurrence_rules import ByDay, FixedPattern, Frequency, NominalDate, Weekday
from domus.domain.recurrence_time import NominalTime, TimePolicy
from domus.domain.task_values import DefinitionState, TaskContent, TaskOverrides
from domus.infrastructure.recurrence_time import PinnedRecurrenceTime
from domus.infrastructure.sqlite import SQLiteAudit, SQLiteDatabase
from domus.infrastructure.sqlite_recurrence import SQLiteRecurrences


def setup(tmp_path):
    from domus.domain.nominal_recurrence import CalendarNominalExpansion

    tasks, store, actor, identifiers = fixture(tmp_path)
    planner = FixedRecurrencePlanner(CalendarNominalExpansion(), PinnedRecurrenceTime())
    commands = RecurrenceCommands(store, actor, Clock(), identifiers, planner)
    return commands, tasks, store, actor, identifiers


def request(*, timed=False):
    policy = TimePolicy("Europe/Madrid", PinnedRecurrenceTime().data_identity)
    start = NominalTime(datetime(2026, 3, 29, 2, 30)) if timed else NominalDate(date(2026, 3, 29))
    return CreateFixedTask(
        CreateTask(TaskContent("Clean the filter")), FixedPattern(start, Frequency.DAILY), policy
    )


@pytest.mark.parametrize("timed", [False, True])
def test_atomic_scheduled_creation_starts_unconsumed_and_never_creates_manual_work(tmp_path, timed):
    commands, tasks, store, actor, identifiers = setup(tmp_path)
    before = counts(store)
    value = request(timed=timed)
    result = commands.create_fixed("scheduled", value)
    body = result.result.decode()
    assert body["processing"] == "pending" and body["state"] == "active"
    assert body["first_occurrence_id"] is None
    with store.read() as unit:
        schedule = unit.recurrence.schedule("home", body["schedule_id"])
        item = unit.tasks.definition("home", body["definition_id"])
        progress = unit.recurrence.progress("home", schedule.schedule_id)
        assert schedule.pattern == value.pattern and schedule.policy == value.policy
        assert item.content == value.task.content and item.created_at == schedule.created_at == 100
        assert (
            schedule.definition_id == item.definition_id and schedule.state is ScheduleState.ACTIVE
        )
        assert progress.cursor.binding == cursor_binding(value.pattern, value.policy)
        assert (
            progress.cursor.nominal_count
            == progress.cursor.offset
            == progress.cursor.period_index
            == 0
        )
        assert not progress.range_complete and progress.last_run_at is None
        assert unit.recurrence.slots("home", schedule.schedule_id) == ()
        assert unit.tasks.occurrences("home") == ()
        assert unit.tasks.policy("home").revision == 1
        assert unit.receipts.get(result.command) == result
        assert (
            unit.audit.entries("home")[-1].detail.decode()["request"] == value.document().decode()
        )
        assert unit.outbox.pending()[-1].event_id == result.operation_id
    assert counts(store) == (1, 0, before[2] + 1, before[3] + 1)
    ordinary = tasks.create("ordinary", CreateTask(TaskContent("Manual")))
    assert ordinary.result.decode()["occurrence_id"] is not None
    assert counts(store)[:2] == (2, 1)
    assert actor.calls >= 2 and identifiers.count >= 4


def test_restart_replay_keeps_original_receipt_without_provider_or_identity_allocation(
    tmp_path, monkeypatch
):
    commands, _, store, actor, identifiers = setup(tmp_path)
    original_calls = actor.calls
    value = request()
    result = commands.create_fixed("create", value)
    allocated = identifiers.count
    before = counts(store)

    def unavailable(*args, **kwargs):
        raise AssertionError("An authorized original receipt must precede provider work")

    monkeypatch.setattr(PinnedRecurrenceTime, "require_policy", unavailable)
    reopened = SQLiteDatabase(store.path, store.installation)
    replay = replace(commands, transactions=reopened).create_fixed("create", value)
    assert replay == result and identifiers.count == allocated and counts(store) == before
    assert actor.calls == original_calls + 2
    with pytest.raises(Conflict, match="idempotency_conflict"):
        commands.create_fixed("create", replace(value, pattern=replace(value.pattern, interval=2)))


@pytest.mark.parametrize("stage", ["definition", "schedule", "progress", "audit"])
def test_failure_after_each_creation_write_rolls_back_policy_rule_progress_and_all_evidence(
    tmp_path, monkeypatch, stage
):
    from domus.infrastructure.sqlite_tasks import SQLiteTasks

    commands, _, store, _, _ = setup(tmp_path)
    target, name = {
        "definition": (SQLiteTasks, "save_definition"),
        "schedule": (SQLiteRecurrences, "save_schedule"),
        "progress": (SQLiteRecurrences, "save_progress"),
        "audit": (SQLiteAudit, "append"),
    }[stage]
    original = getattr(target, name)
    before = counts(store)

    def failed(self, *args):
        original(self, *args)
        raise StorageFailure("fixture_after_write")

    with monkeypatch.context() as patch:
        patch.setattr(target, name, failed)
        with pytest.raises(StorageFailure, match="fixture_after_write"):
            commands.create_fixed("create", request())
    assert counts(store) == before
    with store.read() as unit:
        assert unit.tasks.policy("home") is None
        assert unit.recurrence.schedules("home") == ()
    assert commands.create_fixed("create", request()).result.decode()["processing"] == "pending"


@pytest.mark.parametrize("change", ["restricted", "unlinked", "suspended", "outage", "override"])
def test_current_identity_and_original_creation_permissions_apply_before_new_effect_or_replay(
    tmp_path, change
):
    commands, _, store, actor, _ = setup(tmp_path)
    value = request()
    original = commands.create_fixed("original", value)
    if change in ("restricted", "unlinked"):
        actor.human = HumanIdentity(
            "ha_child" if change == "restricted" else "ha_absent", False, True, False
        )
    elif change == "suspended":
        with store.write() as unit:
            member = unit.members.by_user("home", actor.human.ha_user_id)
            unit.members.save(replace(member, status=MemberStatus.SUSPENDED, revision=2), 1)
    elif change == "outage":
        actor.error = IdentityUnavailable("ha_unavailable")
    else:
        actor.human = HumanIdentity("ha_other", False, True, False)
        with store.write() as unit:
            member = unit.members.by_user("home", actor.human.ha_user_id)
            unit.members.save(replace(member, role=Role.ADULT, revision=2), 1)
        value = replace(
            value,
            task=replace(value.task, overrides=TaskOverrides(adult_performer_may_approve=False)),
        )
    before = counts(store)
    for key in ("new", "original"):
        with pytest.raises(IdentityUnavailable if change == "outage" else Forbidden):
            commands.create_fixed(key, value)
    assert counts(store) == before
    assert original.command.actor_id == "ha_admin"


def test_permission_loss_after_external_rule_validation_is_rechecked_inside_writer(
    tmp_path, monkeypatch
):
    commands, _, store, actor, _ = setup(tmp_path)
    original = PinnedRecurrenceTime.require_policy

    def revoke(self, policy):
        original(self, policy)
        with store.write() as unit:
            member = unit.members.by_user("home", actor.human.ha_user_id)
            unit.members.save(replace(member, status=MemberStatus.SUSPENDED, revision=2), 1)

    monkeypatch.setattr(PinnedRecurrenceTime, "require_policy", revoke)
    before = counts(store)
    with pytest.raises(Forbidden):
        commands.create_fixed("create", request())
    assert counts(store) == before


@pytest.mark.parametrize(
    "change,code",
    [
        ("zone", "unknown_time_zone"),
        ("data", "timezone_data_mismatch"),
        ("start", "recurrence_start_mismatch"),
    ],
)
def test_invalid_actual_policy_or_mismatched_start_is_rejected_without_silently_adjusting_rule(
    tmp_path, change, code
):
    from domus.domain.errors import IntegrationUnavailable

    commands, _, store, _, _ = setup(tmp_path)
    value = request()
    if change == "zone":
        value = replace(value, policy=replace(value.policy, zone="Unknown/Zone"))
    elif change == "data":
        value = replace(value, policy=replace(value.policy, data_identity="fixture:wrong"))
    else:
        value = replace(
            value,
            pattern=replace(value.pattern, frequency=Frequency.WEEKLY, by_day=(ByDay(Weekday.MO),)),
        )
    before = counts(store)
    with pytest.raises(InvalidInput if change != "data" else IntegrationUnavailable, match=code):
        commands.create_fixed("create", value)
    assert counts(store) == before


@pytest.mark.parametrize("field,value", [("task", None), ("pattern", None), ("policy", None)])
def test_untyped_scheduled_request_cannot_enter_application(field, value):
    with pytest.raises(InvalidInput, match="invalid_recurrence_create"):
        replace(request(), **{field: value})


def test_scheduled_creation_reuses_task_material_validation_and_privileged_link_permissions(
    tmp_path,
):
    from test_task_material_commands import Inventory

    from domus.domain.task_material_values import MaterialQuantity, MaterialSelection

    commands, _, store, actor, _ = setup(tmp_path)
    inventory = Inventory(tmp_path / "inventory.sqlite3")
    commands.inventory_factory = inventory.factory
    value = request()
    value = replace(
        value,
        task=replace(
            value.task, materials=(MaterialSelection("binding", MaterialQuantity("0.5")),)
        ),
    )
    receipt = commands.create_fixed("create", value)
    with store.read() as unit:
        item = unit.tasks.definition("home", receipt.result.decode()["definition_id"])
        assert item.materials[0].binding == inventory.bindings["binding"]
        assert item.materials[0].planned_quantity.value == "0.5"
        member = unit.members.by_user("home", actor.human.ha_user_id)
    before = counts(store)
    with store.write() as unit:
        unit.members.save(
            replace(
                member, exceptions=(PermissionRule(Permission.INVENTORY_MANAGE, False),), revision=2
            ),
            1,
        )
    for key in ("new", "create"):
        with pytest.raises(Forbidden):
            commands.create_fixed(key, value)
    assert counts(store) == before


def test_nonactive_task_requires_deliberate_later_configuration():
    with pytest.raises(InvalidInput, match="invalid_recurrence_create"):
        replace(request(), task=CreateTask(TaskContent("Draft"), state=DefinitionState.DRAFT))


def test_bounded_start_search_does_not_persist_an_unresolved_pattern(tmp_path):
    from domus.domain.errors import IntegrationUnavailable

    commands, _, store, _, _ = setup(tmp_path)
    value = request()
    value = replace(
        value,
        pattern=replace(
            value.pattern, frequency=Frequency.YEARLY, by_month=(2,), by_month_day=(30,)
        ),
    )
    before = counts(store)
    with pytest.raises(IntegrationUnavailable, match="recurrence_start_unresolved"):
        commands.create_fixed("create", value)
    assert counts(store) == before


def test_authorized_task_override_is_snapshotted_and_does_not_change_household_defaults(tmp_path):
    commands, _, store, _, _ = setup(tmp_path)
    value = request()
    value = replace(
        value, task=replace(value.task, overrides=TaskOverrides(adult_performer_may_approve=False))
    )
    receipt = commands.create_fixed("create", value)
    with store.read() as unit:
        item = unit.tasks.definition("home", receipt.result.decode()["definition_id"])
        assert item.overrides == value.task.overrides
        assert unit.tasks.policy("home").rules.adult_performer_may_approve
