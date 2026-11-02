"""Actual relative creation keeps current authority, explicit timing and one atomic intention."""

from dataclasses import replace
from datetime import date, datetime, timedelta

import pytest
from test_household_commands import Clock
from test_task_commands import counts, fixture

from domus.application.relative_recurrence_commands import (
    CreateRelativeTask,
    RelativeRecurrenceCommands,
)
from domus.application.task_requests import CreateTask
from domus.domain.errors import (
    Conflict,
    Forbidden,
    IdentityUnavailable,
    IntegrationUnavailable,
    InvalidInput,
    StorageFailure,
)
from domus.domain.identity import HumanIdentity, MemberStatus, Permission, PermissionRule, Role
from domus.domain.recurrence_rules import NominalDate
from domus.domain.recurrence_time import FoldPolicy, NominalTime, RelativeInterval, TimePolicy
from domus.domain.relative_recurrence import SuccessorVisibility
from domus.domain.task_values import DefinitionState, TaskContent, TaskOverrides
from domus.infrastructure.recurrence_time import PinnedRecurrenceTime
from domus.infrastructure.sqlite import SQLiteAudit, SQLiteDatabase, SQLiteOutbox, SQLiteReceipts
from domus.infrastructure.sqlite_relative_recurrence import SQLiteRelativeRecurrences
from domus.infrastructure.sqlite_tasks import SQLiteTasks


def setup(tmp_path):
    tasks, store, actor, identifiers = fixture(tmp_path)
    commands = RelativeRecurrenceCommands(
        store, actor, Clock(), identifiers, PinnedRecurrenceTime()
    )
    return commands, tasks, store, actor, identifiers


def request(*, timed=False, visibility=SuccessorVisibility.AT_COMPLETION):
    initial = (
        NominalTime(datetime(2026, 3, 29, 2, 30, 0, 123000))
        if timed
        else NominalDate(date(2026, 3, 29))
    )
    return CreateRelativeTask(
        CreateTask(TaskContent("Clean the filter")),
        initial,
        RelativeInterval(30),
        TimePolicy("Europe/Madrid", PinnedRecurrenceTime().data_identity),
        visibility,
    )


@pytest.mark.parametrize("timed", [False, True])
@pytest.mark.parametrize("visibility", list(SuccessorVisibility))
def test_relative_creation_commits_one_unconsumed_intention_without_manual_work(
    tmp_path, timed, visibility
):
    commands, tasks, store, _, _ = setup(tmp_path)
    value = request(timed=timed, visibility=visibility)
    before = counts(store)
    receipt = commands.create("relative", value)
    result = receipt.result.decode()
    assert receipt.command.action == "recurrence.relative.create"
    assert result["processing"] == "pending" and result["first_occurrence_id"] is None
    with store.read() as unit:
        rule = unit.recurrence.relative_schedule("home", result["schedule_id"])
        progress = unit.recurrence.relative_progress("home", rule.schedule_id)
        item = unit.tasks.definition("home", result["definition_id"])
        assert rule.definition_id == item.definition_id
        assert rule.initial.nominal == value.initial
        assert rule.interval == value.interval and rule.policy == value.policy
        assert rule.visibility == visibility and rule.created_at == item.created_at == 100
        assert progress.pristine and progress.matches_schedule(rule)
        assert progress.source_after == 0 and progress.last_run_at is None
        assert progress.current_occurrence_id is progress.current_slot_key is None
        assert unit.recurrence.relative_slots("home", rule.schedule_id) == ()
        assert unit.recurrence.schedules("home") == ()
        assert unit.tasks.occurrences("home") == ()
        assert unit.tasks.policy("home").revision == 1
        if timed:
            assert rule.initial.resolved.resolved_local == datetime(2026, 3, 29, 3)
        else:
            assert rule.initial.resolved is None
        assert unit.receipts.get(receipt.command) == receipt
        assert (
            unit.audit.entries("home")[-1].detail.decode()["request"] == value.document().decode()
        )
        event = unit.outbox.pending()[-1]
        assert event.event_id == receipt.operation_id
        assert event.payload.decode() == {
            "version": 1,
            "kind": "recurrence.relative.created",
            **result,
        }
    assert counts(store) == (1, 0, before[2] + 1, before[3] + 1)
    tasks.create("ordinary", CreateTask(TaskContent("Manual")))
    assert counts(store)[:2] == (2, 1)


@pytest.mark.parametrize("fold", list(FoldPolicy))
def test_explicit_initial_fold_keeps_one_configured_instant_and_milliseconds(tmp_path, fold):
    commands, _, store, _, _ = setup(tmp_path)
    value = request(timed=True)
    value = replace(
        value,
        initial=NominalTime(datetime(2026, 10, 25, 2, 30, 0, 321000)),
        policy=replace(value.policy, repeated_time=fold),
    )
    receipt = commands.create("fold", value)
    with store.read() as unit:
        rule = unit.recurrence.relative_schedule("home", receipt.result.decode()["schedule_id"])
        assert rule.initial.resolved == PinnedRecurrenceTime().resolve(value.initial, value.policy)
        assert rule.initial.resolved.instant_ms % 1000 == 321
        assert rule.initial.resolved.offset_seconds == (7200 if fold is FoldPolicy.FIRST else 3600)
        assert unit.tasks.occurrences("home") == ()


def test_authorized_original_replay_precedes_provider_work_or_new_identity_allocation(
    tmp_path, monkeypatch
):
    commands, _, store, actor, identifiers = setup(tmp_path)
    value = request(timed=True)
    original = commands.create("original", value)
    before, allocated, calls = counts(store), identifiers.count, actor.calls

    def unavailable(*args):
        raise AssertionError("An authorized original is returned before provider work")

    monkeypatch.setattr(PinnedRecurrenceTime, "require_policy", unavailable)
    monkeypatch.setattr(PinnedRecurrenceTime, "resolve", unavailable)
    again = replace(commands, transactions=SQLiteDatabase(store.path, store.installation))
    assert again.create("original", value) == original
    assert counts(store) == before and identifiers.count == allocated and actor.calls == calls + 1


@pytest.mark.parametrize("change", ["initial", "interval", "policy", "visibility", "task"])
def test_original_command_cannot_be_reused_for_a_different_relative_intention(tmp_path, change):
    commands, _, store, _, _ = setup(tmp_path)
    value = request()
    commands.create("original", value)
    changes = {
        "initial": {"initial": NominalDate(value.initial.local + timedelta(days=1))},
        "interval": {"interval": RelativeInterval(31)},
        "policy": {"policy": replace(value.policy, zone="Unknown/Zone")},
        "visibility": {"visibility": SuccessorVisibility.AT_VERIFICATION},
        "task": {"task": CreateTask(TaskContent("Different"))},
    }
    before = counts(store)
    with pytest.raises(Conflict, match="idempotency_conflict"):
        commands.create("original", replace(value, **changes[change]))
    assert counts(store) == before


@pytest.mark.parametrize(
    "stage", ["policy", "definition", "schedule", "progress", "receipt", "audit", "outbox"]
)
def test_every_relative_creation_write_rolls_back_policy_rule_and_original_evidence(
    tmp_path, monkeypatch, stage
):
    commands, _, store, _, _ = setup(tmp_path)
    target, name = {
        "policy": (SQLiteTasks, "save_policy"),
        "definition": (SQLiteTasks, "save_definition"),
        "schedule": (SQLiteRelativeRecurrences, "save_relative_schedule"),
        "progress": (SQLiteRelativeRecurrences, "save_relative_progress"),
        "receipt": (SQLiteReceipts, "add"),
        "audit": (SQLiteAudit, "append"),
        "outbox": (SQLiteOutbox, "append"),
    }[stage]
    original = getattr(target, name)
    before = counts(store)

    def fail_after(self, *args):
        original(self, *args)
        raise StorageFailure("fixture_after_write")

    with monkeypatch.context() as patch:
        patch.setattr(target, name, fail_after)
        with pytest.raises(StorageFailure, match="fixture_after_write"):
            commands.create("relative", request())
    assert counts(store) == before
    with store.read() as unit:
        assert unit.tasks.policy("home") is None
        assert unit.recurrence.relative_schedules("home") == ()
    assert commands.create("relative", request()).result.decode()["processing"] == "pending"


@pytest.mark.parametrize("change", ["restricted", "suspended", "unlinked", "outage", "override"])
def test_fresh_identity_and_current_grants_precede_new_effect_and_original_replay(tmp_path, change):
    commands, _, store, actor, _ = setup(tmp_path)
    value = request()
    commands.create("original", value)
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
            commands.create(key, value)
    assert counts(store) == before


@pytest.mark.parametrize("timed", [False, True])
def test_grant_revocation_during_external_time_preparation_is_rechecked_in_writer(
    tmp_path, monkeypatch, timed
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
        commands.create("relative", request(timed=timed))
    assert counts(store) == before


@pytest.mark.parametrize(
    "change,code", [("zone", "unknown_time_zone"), ("data", "timezone_data_mismatch")]
)
def test_unavailable_initial_time_policy_leaves_no_partial_relative_intention(
    tmp_path, change, code
):
    commands, _, store, _, _ = setup(tmp_path)
    value = request()
    value = replace(
        value,
        policy=replace(
            value.policy,
            **(
                {"zone": "Unknown/Zone"} if change == "zone" else {"data_identity": "fixture:wrong"}
            ),
        ),
    )
    before = counts(store)
    with pytest.raises(InvalidInput if change == "zone" else IntegrationUnavailable, match=code):
        commands.create("relative", value)
    assert counts(store) == before


@pytest.mark.parametrize("change", ["none", "nominal", "policy"])
def test_contradictory_time_port_response_cannot_enter_saved_initial_slot(
    tmp_path, monkeypatch, change
):
    commands, _, store, _, _ = setup(tmp_path)
    value = request(timed=True)
    resolved = PinnedRecurrenceTime().resolve(value.initial, value.policy)
    altered = (
        None
        if change == "none"
        else replace(
            resolved,
            **(
                {"nominal": NominalTime(value.initial.local - timedelta(minutes=1))}
                if change == "nominal"
                else {"policy": replace(value.policy, revision=2)}
            ),
        )
    )
    monkeypatch.setattr(PinnedRecurrenceTime, "resolve", lambda *args: altered)
    before = counts(store)
    with pytest.raises(IntegrationUnavailable, match="recurrence_time_source_invalid"):
        commands.create("relative", value)
    assert counts(store) == before


@pytest.mark.parametrize("field", ["task", "initial", "interval", "policy", "visibility"])
def test_relative_request_requires_typed_explicit_timing_and_visibility(field):
    with pytest.raises(InvalidInput, match="invalid_recurrence_create"):
        replace(request(), **{field: None})


def test_nonactive_relative_task_requires_a_deliberate_later_configuration():
    with pytest.raises(InvalidInput, match="invalid_recurrence_create"):
        replace(request(), task=CreateTask(TaskContent("Draft"), state=DefinitionState.DRAFT))


def test_relative_creation_reuses_material_ownership_and_current_link_grants(tmp_path):
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
    receipt = commands.create("relative", value)
    with store.read() as unit:
        item = unit.tasks.definition("home", receipt.result.decode()["definition_id"])
        assert item.materials[0].binding == inventory.bindings["binding"]
        member = unit.members.by_user("home", actor.human.ha_user_id)
    with store.write() as unit:
        unit.members.save(
            replace(
                member, exceptions=(PermissionRule(Permission.INVENTORY_MANAGE, False),), revision=2
            ),
            1,
        )
    before = counts(store)
    for key in ("new", "relative"):
        with pytest.raises(Forbidden):
            commands.create(key, value)
    assert counts(store) == before


def test_relative_override_is_snapshotted_without_replacing_household_defaults(tmp_path):
    commands, _, store, _, _ = setup(tmp_path)
    value = request()
    value = replace(
        value, task=replace(value.task, overrides=TaskOverrides(adult_performer_may_approve=False))
    )
    receipt = commands.create("relative", value)
    with store.read() as unit:
        item = unit.tasks.definition("home", receipt.result.decode()["definition_id"])
        assert item.overrides == value.task.overrides
        assert unit.tasks.policy("home").rules.adult_performer_may_approve


@pytest.mark.parametrize("timed", [False, True])
@pytest.mark.parametrize("different", [False, True])
def test_independent_creation_writers_keep_one_atomic_original_and_explicit_retry(
    tmp_path, timed, different
):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from domus.domain.errors import StorageBusy
    from domus.infrastructure.application_runtime import SecureIdentifiers
    from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots

    commands, _, store, actor, _ = setup(tmp_path)
    gate = Barrier(2)

    class SimultaneousTimes(PinnedRecurrenceTime):
        def require_policy(self, policy):
            super().require_policy(policy)
            gate.wait(timeout=5)

    first = request(timed=timed)
    second = replace(first, interval=RelativeInterval(31)) if different else first

    def create(value):
        independent = SQLiteDatabase(store.path, store.installation)
        writer = RelativeRecurrenceCommands(
            independent, actor, Clock(), SecureIdentifiers(), SimultaneousTimes()
        )
        try:
            return writer.create("concurrent", value)
        except (Conflict, StorageBusy) as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(pool.map(create, (first, second)))
    winners = tuple(value for value in results if not isinstance(value, (Conflict, StorageBusy)))
    assert len(winners) in (1, 2) and len({value.operation_id for value in winners}) == 1
    winner = winners[0]
    for value in (first, second):
        if value.document().fingerprint == winner.payload_fingerprint:
            assert commands.create("concurrent", value) == winner
        else:
            with pytest.raises(Conflict, match="idempotency_conflict"):
                commands.create("concurrent", value)
    with store.read() as unit:
        assert len(unit.recurrence.relative_schedules("home")) == 1
        assert len(unit.tasks.definitions("home")) == 1
        assert unit.tasks.occurrences("home") == ()
        assert len(unit.audit.entries("home")) == len(unit.outbox.pending()) == 2
        assert unit.receipts.get(winner.command) == winner
    assert SQLiteSnapshots(store, tmp_path / "after", store.installation, Clock()).create("after")


def test_real_restore_keeps_missing_creation_historical_without_recreating_rule_or_work(
    tmp_path, monkeypatch
):
    from test_activation_compatibility import identity_at
    from test_sqlite_snapshots import Clock as SnapshotClock

    from domus.infrastructure.owned_storage import open_storage
    from domus.infrastructure.sqlite_activation import SQLiteActivation
    from domus.infrastructure.sqlite_restoration import SQLiteRestorations
    from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots

    root, archive, target = tmp_path / "source", tmp_path / "before", tmp_path / "prepared"
    root.mkdir(mode=0o700)
    commands, _, store, _, identifiers = setup(root)
    identity_at(root, store.installation)
    checkpoint = SQLiteSnapshots(store, archive, store.installation, SnapshotClock()).create(
        "before"
    )
    value = request(timed=True)
    original = commands.create("relative", value)
    allocated = identifiers.count
    SQLiteRestorations(
        store, archive, target, store.installation, SnapshotClock(), checkpoint
    ).prepare("relative-creation-restore")
    assert (
        SQLiteActivation(root, store.installation, SnapshotClock(), target).activate().state
        == "active"
    )

    def unavailable(*args):
        raise AssertionError("Historical creation must not replay provider work")

    monkeypatch.setattr(PinnedRecurrenceTime, "require_policy", unavailable)
    monkeypatch.setattr(PinnedRecurrenceTime, "resolve", unavailable)
    storage = open_storage(root, "edge")
    try:
        restored_commands = replace(commands, transactions=storage.database)
        restored = restored_commands.create("relative", value)
        assert restored.historical and restored.operation_id == original.operation_id
        assert restored.result == original.result and identifiers.count == allocated
        with storage.database.read() as unit:
            assert unit.tasks.definitions("home") == unit.tasks.occurrences("home") == ()
            assert unit.recurrence.relative_schedules("home") == ()
            assert unit.tasks.policy("home") is None
            assert len(unit.audit.entries("home")) == len(unit.outbox.pending()) == 1
            assert all(event.event_id != original.operation_id for event in unit.outbox.pending())
        with pytest.raises(Conflict, match="idempotency_conflict"):
            restored_commands.create("relative", replace(value, interval=RelativeInterval(31)))
        assert SQLiteSnapshots(
            storage.database, tmp_path / "after", store.installation, SnapshotClock()
        ).create("after")
    finally:
        storage.close()
