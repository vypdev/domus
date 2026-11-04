"""Actual initial relative work, atomic proof, manual-work review and restored absence."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from threading import Barrier

import pytest
from test_relative_recurrence_creation import request, setup
from test_task_commands import counts

from domus.application.fixed_materialization import MaintenanceScope
from domus.application.relative_materialization import RelativeMaintenance
from domus.application.task_requests import CreateTask, CreateTaskOccurrence
from domus.domain.errors import (
    Conflict,
    Forbidden,
    IntegrationUnavailable,
    InvalidInput,
    NotFound,
    StorageBusy,
    StorageFailure,
)
from domus.domain.recurrence_records import ScheduleState
from domus.domain.relative_recurrence import RelativeOperation
from domus.domain.storage import JsonDocument, RestorationProvenance
from domus.domain.task_values import DefinitionState, OccurrenceState, TaskContent
from domus.infrastructure.application_runtime import SecureIdentifiers
from domus.infrastructure.recurrence_time import PinnedRecurrenceTime
from domus.infrastructure.sqlite import SQLiteAudit, SQLiteDatabase, SQLiteOutbox, SQLiteReceipts
from domus.infrastructure.sqlite_relative_recurrence import SQLiteRelativeRecurrences
from domus.infrastructure.sqlite_tasks import SQLiteTasks


def configured(tmp_path, *, timed=False):
    creation, tasks, store, actor, identifiers = setup(tmp_path)
    result = creation.create("relative", request(timed=timed)).result.decode()
    service = RelativeMaintenance(
        store,
        MaintenanceScope(store.installation, "home"),
        creation.times,
        creation.clock,
        identifiers,
    )
    return service, store, actor, identifiers, result["schedule_id"], tasks


def progress(store, schedule_id):
    with store.read() as unit:
        return unit.recurrence.relative_progress("home", schedule_id)


@pytest.mark.parametrize("timed", [False, True])
def test_initial_step_commits_real_work_slot_continuation_and_proof_in_one_transaction(
    tmp_path, timed
):
    service, store, actor, _, schedule_id, _ = configured(tmp_path, timed=timed)
    before, calls = counts(store), actor.calls
    result = service.initial(schedule_id)
    assert result.status == "created" and result.schedule_id == schedule_id
    with store.read() as unit:
        rule = unit.recurrence.relative_schedule("home", schedule_id)
        saved = unit.recurrence.relative_progress("home", schedule_id)
        slot = unit.recurrence.relative_slot("home", result.receipt.command.key)
        work = unit.tasks.occurrence("home", result.occurrence_id)
        assert work.state is OccurrenceState.AVAILABLE and work.assignee_ids == ()
        assert work.current_cycle_id is None and unit.tasks.cycles("home") == ()
        assert work.definition_snapshot == unit.tasks.definition("home", rule.definition_id)
        assert work.due_at == (rule.initial.resolved.instant_ms if timed else None)
        assert slot.source is None and slot.planned == rule.initial
        assert slot.occurrence_id == work.occurrence_id and slot.matches_receipt(result.receipt)
        assert saved.revision == 2 and saved.source_after == 0 and saved.last_run_at == 100
        assert saved.current_occurrence_id == work.occurrence_id
        assert saved.current_slot_key == slot.key and not saved.pristine
        assert saved.evidence == RelativeOperation(
            result.receipt.command, result.receipt.operation_id
        )
        assert saved.matches_receipt(result.receipt)
        assert result.receipt.command.actor_id == "system:recurrence"
        assert result.receipt.command.action == "recurrence.materialize"
        assert unit.audit.entries("home")[-1].operation_id == result.receipt.operation_id
        assert unit.outbox.pending()[-1].event_id == result.receipt.operation_id
    assert counts(store) == (before[0], 1, before[2] + 1, before[3] + 1)
    assert actor.calls == calls


def test_restart_at_saved_continuation_does_not_rearm_initial_work_or_require_provider(
    tmp_path, monkeypatch
):
    service, store, _, identifiers, schedule_id, _ = configured(tmp_path)
    first = service.initial(schedule_id)
    before, allocated = counts(store), identifiers.count

    def unavailable(*args):
        raise AssertionError("Saved progress requires no new time-provider work")

    monkeypatch.setattr(PinnedRecurrenceTime, "require_policy", unavailable)
    again = replace(service, transactions=SQLiteDatabase(store.path, store.installation))
    second = again.initial(schedule_id)
    assert second.status == "current" and second.receipt is None
    assert second.occurrence_id == first.occurrence_id
    assert counts(store) == before and identifiers.count == allocated


def reset_progress(store, schedule_id):
    with store.write() as unit:
        previous = unit.recurrence.relative_progress("home", schedule_id)
        unit.recurrence.save_relative_progress(
            replace(
                previous,
                current_occurrence_id=None,
                current_slot_key=None,
                last_run_at=None,
                evidence=None,
                revision=previous.revision + 1,
            ),
            previous.revision,
        )


def test_original_live_slot_reconciles_pristine_cursor_without_more_work_or_provider(
    tmp_path, monkeypatch
):
    service, store, _, identifiers, schedule_id, _ = configured(tmp_path, timed=True)
    first = service.initial(schedule_id)
    reset_progress(store, schedule_id)
    before, allocated = counts(store), identifiers.count

    def unavailable(*args):
        raise AssertionError("Original proof precedes any provider preparation")

    monkeypatch.setattr(PinnedRecurrenceTime, "require_policy", unavailable)
    second = service.initial(schedule_id)
    assert second.status == "replayed" and second.receipt == first.receipt
    assert second.occurrence_id == first.occurrence_id
    assert progress(store, schedule_id).matches_receipt(first.receipt)
    assert counts(store) == before and identifiers.count == allocated


@pytest.mark.parametrize("stage", ["work", "slot", "receipt", "audit", "outbox", "progress"])
def test_failure_after_each_write_rolls_back_work_mapping_proof_and_continuation(
    tmp_path, monkeypatch, stage
):
    service, store, _, _, schedule_id, _ = configured(tmp_path)
    target, name = {
        "work": (SQLiteTasks, "save_occurrence"),
        "slot": (SQLiteRelativeRecurrences, "add_relative_slot"),
        "receipt": (SQLiteReceipts, "add"),
        "audit": (SQLiteAudit, "append"),
        "outbox": (SQLiteOutbox, "append"),
        "progress": (SQLiteRelativeRecurrences, "save_relative_progress"),
    }[stage]
    original = getattr(target, name)
    before, saved = counts(store), progress(store, schedule_id)

    def fail(self, *args):
        original(self, *args)
        raise StorageFailure("fixture_after_initial_write")

    with monkeypatch.context() as patch:
        patch.setattr(target, name, fail)
        with pytest.raises(StorageFailure, match="fixture_after_initial_write"):
            service.initial(schedule_id)
    assert counts(store) == before and progress(store, schedule_id) == saved
    with store.read() as unit:
        assert unit.recurrence.relative_slots("home", schedule_id) == ()
    assert service.initial(schedule_id).status == "created"


@pytest.mark.parametrize("change", ["household", "instance", "channel"])
def test_initial_capability_is_bound_to_actual_installation_channel_and_household(tmp_path, change):
    service, store, _, _, schedule_id, _ = configured(tmp_path)
    scope = service.scope
    scope = (
        replace(scope, household_id="other")
        if change == "household"
        else replace(
            scope,
            installation=replace(
                scope.installation,
                **(
                    {"channel": "stable"}
                    if change == "channel"
                    else {"instance_id": "00000000-0000-0000-0000-000000000001"}
                ),
            ),
        )
    )
    before = counts(store)
    with pytest.raises(Forbidden):
        replace(service, scope=scope).initial(schedule_id)
    assert counts(store) == before


@pytest.mark.parametrize("state", [ScheduleState.PAUSED, ScheduleState.RETIRED])
def test_inactive_rule_does_not_generate_or_consume_its_initial_intention(tmp_path, state):
    service, store, _, _, schedule_id, _ = configured(tmp_path)
    with store.write() as unit:
        rule = unit.recurrence.relative_schedule("home", schedule_id)
        unit.recurrence.save_relative_schedule(replace(rule, state=state, revision=2), 1)
    before = counts(store)
    assert service.initial(schedule_id).status == state.value
    assert counts(store) == before and progress(store, schedule_id).pristine


@pytest.mark.parametrize("state", [v for v in DefinitionState if v is not DefinitionState.ACTIVE])
def test_inactive_definition_does_not_create_a_live_initial_obligation(tmp_path, state):
    service, store, _, _, schedule_id, _ = configured(tmp_path)
    with store.write() as unit:
        rule = unit.recurrence.relative_schedule("home", schedule_id)
        definition = unit.tasks.definition("home", rule.definition_id)
        unit.tasks.save_definition(replace(definition, state=state, revision=2), 1)
    before = counts(store)
    assert service.initial(schedule_id).status == "definition_inactive"
    assert counts(store) == before and progress(store, schedule_id).pristine


def test_existing_manual_work_requires_review_instead_of_another_initial_obligation(tmp_path):
    service, store, _, _, schedule_id, tasks = configured(tmp_path)
    with store.read() as unit:
        definition_id = unit.recurrence.relative_schedule("home", schedule_id).definition_id
    manual = tasks.create_occurrence("manual", CreateTaskOccurrence(definition_id))
    before = counts(store)
    result = service.initial(schedule_id)
    assert result.status == "initial_review_required" and result.receipt is None
    assert result.occurrence_id is None and progress(store, schedule_id).pristine
    assert counts(store) == before
    with store.read() as unit:
        assert (
            unit.tasks.occurrences("home")[0].occurrence_id
            == manual.result.decode()["occurrence_id"]
        )


def test_other_definition_work_does_not_block_this_rules_initial_work(tmp_path):
    service, store, _, _, schedule_id, tasks = configured(tmp_path)
    tasks.create("other", CreateTask(TaskContent("Other household responsibility")))
    assert service.initial(schedule_id).status == "created"
    assert counts(store)[:2] == (2, 2)


@pytest.mark.parametrize("change", ["rule", "definition", "progress", "manual"])
def test_writer_rechecks_current_sources_and_manual_work_after_provider_preparation(
    tmp_path, monkeypatch, change
):
    service, store, _, _, schedule_id, tasks = configured(tmp_path)
    original = PinnedRecurrenceTime.require_policy
    before = counts(store)

    def change_source(self, policy):
        original(self, policy)
        if change == "manual":
            with store.read() as unit:
                definition_id = unit.recurrence.relative_schedule("home", schedule_id).definition_id
            tasks.create_occurrence("racing-manual", CreateTaskOccurrence(definition_id))
            return
        with store.write() as unit:
            rule = unit.recurrence.relative_schedule("home", schedule_id)
            if change == "rule":
                unit.recurrence.save_relative_schedule(
                    replace(rule, state=ScheduleState.PAUSED, revision=2), 1
                )
            elif change == "definition":
                item = unit.tasks.definition("home", rule.definition_id)
                unit.tasks.save_definition(
                    replace(item, content=TaskContent("Updated"), revision=2), 1
                )
            else:
                saved = unit.recurrence.relative_progress("home", schedule_id)
                unit.recurrence.save_relative_progress(replace(saved, revision=2), 1)

    monkeypatch.setattr(PinnedRecurrenceTime, "require_policy", change_source)
    with pytest.raises(
        Conflict, match="relative_initial_review_required|recurrence_source_changed"
    ):
        service.initial(schedule_id)
    assert progress(store, schedule_id).pristine
    assert counts(store) == (
        (before[0], 1, before[2] + 1, before[3] + 1) if change == "manual" else before
    )


@pytest.mark.parametrize("boundary", ["before_provider", "after_provider", "inside_writer"])
def test_owned_lifetime_stop_never_publishes_part_of_an_initial_effect(
    tmp_path, monkeypatch, boundary
):
    service, store, _, _, schedule_id, _ = configured(tmp_path)
    stopped = boundary == "before_provider"
    original = PinnedRecurrenceTime.require_policy

    def prepare(self, policy):
        nonlocal stopped
        original(self, policy)
        if boundary == "after_provider":
            stopped = True

    monkeypatch.setattr(PinnedRecurrenceTime, "require_policy", prepare)
    writer = SQLiteDatabase.write

    @contextmanager
    def admitted(self):
        nonlocal stopped
        with writer(self) as unit:
            if boundary == "inside_writer":
                stopped = True
            yield unit

    monkeypatch.setattr(SQLiteDatabase, "write", admitted)
    before = counts(store)
    assert service.initial(schedule_id, should_continue=lambda: not stopped).status == "stopped"
    assert counts(store) == before and progress(store, schedule_id).pristine


def test_provider_failure_keeps_new_work_and_proof_absent(tmp_path, monkeypatch):
    service, store, _, _, schedule_id, _ = configured(tmp_path)

    def unavailable(*args):
        raise IntegrationUnavailable("fixture_time_source_down")

    monkeypatch.setattr(PinnedRecurrenceTime, "require_policy", unavailable)
    before = counts(store)
    with pytest.raises(IntegrationUnavailable, match="fixture_time_source_down"):
        service.initial(schedule_id)
    assert counts(store) == before and progress(store, schedule_id).pristine


def test_missing_rule_and_stale_expected_revision_have_no_effect(tmp_path):
    service, store, _, _, schedule_id, _ = configured(tmp_path)
    with store.read() as unit:
        rule = unit.recurrence.relative_schedule("home", schedule_id)
    before = counts(store)
    with pytest.raises(NotFound, match="recurrence_rule_missing"):
        service.initial("absent")
    with pytest.raises(Conflict, match="recurrence_source_changed"):
        service.initial(schedule_id, expected_schedule=replace(rule, revision=2))
    with pytest.raises(InvalidInput):
        service.initial("")
    assert counts(store) == before
    assert service.initial(schedule_id, expected_schedule=rule).status == "created"


def test_independent_initial_writers_leave_one_original_and_a_safe_retry(tmp_path):
    service, store, _, _, schedule_id, _ = configured(tmp_path)
    barrier = Barrier(2)

    class SimultaneousTimes(PinnedRecurrenceTime):
        def require_policy(self, policy):
            super().require_policy(policy)
            barrier.wait(timeout=5)

    def run(_):
        independent = replace(
            service,
            transactions=SQLiteDatabase(store.path, store.installation),
            identifiers=SecureIdentifiers(),
            times=SimultaneousTimes(),
        )
        try:
            return independent.initial(schedule_id)
        except (Conflict, StorageBusy) as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(pool.map(run, range(2)))
    winners = tuple(v for v in results if not isinstance(v, (Conflict, StorageBusy)))
    assert len(winners) == 1 and winners[0].status == "created"
    assert service.initial(schedule_id).status == "current"
    with store.read() as unit:
        assert len(unit.tasks.occurrences("home")) == 1
        assert len(unit.recurrence.relative_slots("home", schedule_id)) == 1
        assert len(unit.audit.entries("home")) == len(unit.outbox.pending()) == 3
        assert progress(store, schedule_id).matches_receipt(winners[0].receipt)


@pytest.mark.parametrize("timed", [False, True])
def test_actual_restore_retains_initial_proof_without_recreating_absent_work(
    tmp_path, monkeypatch, timed
):
    from test_activation_compatibility import identity_at
    from test_sqlite_snapshots import Clock

    from domus.infrastructure.owned_storage import open_storage
    from domus.infrastructure.sqlite_activation import SQLiteActivation
    from domus.infrastructure.sqlite_restoration import SQLiteRestorations
    from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots

    root, archive, target = tmp_path / "root", tmp_path / "archive", tmp_path / "prepared"
    root.mkdir(mode=0o700)
    service, store, _, identifiers, schedule_id, _ = configured(root, timed=timed)
    identity_at(root, store.installation)
    checkpoint = SQLiteSnapshots(store, archive, store.installation, Clock()).create(
        "before-initial"
    )
    first = service.initial(schedule_id)
    allocated = identifiers.count
    SQLiteRestorations(store, archive, target, store.installation, Clock(), checkpoint).prepare(
        "initial-restore"
    )
    assert SQLiteActivation(root, store.installation, Clock(), target).activate().state == "active"

    def unavailable(*args):
        raise AssertionError("Historical proof never repeats provider preparation")

    monkeypatch.setattr(PinnedRecurrenceTime, "require_policy", unavailable)
    storage = open_storage(root, "edge")
    try:
        recovered = replace(service, transactions=storage.database)
        result = recovered.initial(schedule_id)
        assert result.status == "historical_absent" and result.receipt.historical
        assert result.receipt.operation_id == first.receipt.operation_id
        assert result.receipt.result == first.receipt.result
        assert identifiers.count == allocated
        with storage.database.read() as unit:
            assert unit.tasks.occurrences("home") == ()
            assert unit.recurrence.relative_slots("home", schedule_id) == ()
            assert len(unit.audit.entries("home")) == len(unit.outbox.pending()) == 2
            assert unit.recurrence.relative_progress("home", schedule_id).matches_receipt(
                result.receipt
            )
        assert recovered.initial(schedule_id).status == "current"
        assert SQLiteSnapshots(
            storage.database, tmp_path / "after", store.installation, Clock()
        ).create("after")
    finally:
        storage.close()


@pytest.mark.parametrize("missing", ["progress", "definition", "binding"])
def test_incomplete_or_mismatched_source_cannot_authorize_initial_work(
    tmp_path, monkeypatch, missing
):
    service, store, _, _, schedule_id, _ = configured(tmp_path)
    saved = progress(store, schedule_id)
    before = counts(store)
    with monkeypatch.context() as patch:
        if missing == "definition":
            patch.setattr(SQLiteTasks, "definition", lambda *args: None)
        else:
            patch.setattr(
                SQLiteRelativeRecurrences,
                "relative_progress",
                lambda *args: None if missing == "progress" else replace(saved, binding="0" * 64),
            )
        with pytest.raises(StorageFailure, match="invalid_recurrence_source"):
            service.initial(schedule_id)
    assert counts(store) == before and progress(store, schedule_id) == saved


def test_local_maintenance_capability_cannot_be_repurposed_for_another_actor(tmp_path, monkeypatch):
    from domus.application.commands import AtomicCommands

    service, store, _, _, schedule_id, _ = configured(tmp_path)
    original = AtomicCommands.in_unit

    def altered(self, unit, command, payload, apply):
        return original(self, unit, replace(command, actor_id="other-actor"), payload, apply)

    monkeypatch.setattr(AtomicCommands, "in_unit", altered)
    before = counts(store)
    with pytest.raises(Forbidden, match="maintenance_scope_denied"):
        service.initial(schedule_id)
    assert counts(store) == before and progress(store, schedule_id).pristine


@pytest.mark.parametrize(
    "field,value",
    [
        ("occurrence_id", None),
        ("created_at", "100"),
        ("created_at", 99),
        ("created_at", 101),
        ("relative_slot_fingerprint", "0" * 64),
        ("relative_progress", {}),
        ("schedule_id", "other"),
        ("definition_id", "other"),
        ("slot_key", "0" * 64),
        ("version", True),
    ],
)
def test_altered_original_result_is_not_adopted_as_cursor_proof(
    tmp_path, monkeypatch, field, value
):
    service, store, _, _, schedule_id, _ = configured(tmp_path)
    first = service.initial(schedule_id)
    reset_progress(store, schedule_id)
    before, saved = counts(store), progress(store, schedule_id)
    original = SQLiteReceipts.get
    changed = replace(
        first.receipt,
        result=JsonDocument.from_value({**first.receipt.result.decode(), field: value}),
    )

    def altered(self, command):
        return changed if command == first.receipt.command else original(self, command)

    with monkeypatch.context() as patch:
        patch.setattr(SQLiteReceipts, "get", altered)
        with pytest.raises(StorageFailure, match="invalid_recurrence_effect"):
            service.initial(schedule_id)
    assert counts(store) == before and progress(store, schedule_id) == saved


@pytest.mark.parametrize("kind", ["command", "payload"])
def test_original_identity_and_payload_are_both_bound_to_the_initial_slot(
    tmp_path, monkeypatch, kind
):
    service, store, _, _, schedule_id, _ = configured(tmp_path)
    first = service.initial(schedule_id)
    reset_progress(store, schedule_id)
    before, saved = counts(store), progress(store, schedule_id)
    original = SQLiteReceipts.get
    changed = (
        replace(first.receipt, command=replace(first.receipt.command, actor_id="other-actor"))
        if kind == "command"
        else replace(first.receipt, payload_fingerprint="f" * 64)
    )

    def altered(self, command):
        return changed if command == first.receipt.command else original(self, command)

    with monkeypatch.context() as patch:
        patch.setattr(SQLiteReceipts, "get", altered)
        with pytest.raises(StorageFailure if kind == "command" else Conflict):
            service.initial(schedule_id)
    assert counts(store) == before and progress(store, schedule_id) == saved


@pytest.mark.parametrize("mapping", ["absent", "different"])
def test_missing_or_contradictory_live_mapping_cannot_advance_initial_progress(
    tmp_path, monkeypatch, mapping
):
    service, store, _, _, schedule_id, _ = configured(tmp_path)
    original = SQLiteRelativeRecurrences.relative_slot

    def contradictory(self, household_id, key):
        saved = original(self, household_id, key)
        return None if mapping == "absent" else replace(saved, occurrence_id="other-work")

    before = counts(store)
    with monkeypatch.context() as patch:
        patch.setattr(SQLiteRelativeRecurrences, "relative_slot", contradictory)
        with pytest.raises(StorageFailure, match="invalid_recurrence_effect"):
            service.initial(schedule_id)
    assert counts(store) == before and progress(store, schedule_id).pristine
    assert service.initial(schedule_id).status == "created"


def test_historical_proof_with_an_inconsistent_live_mapping_fails_closed(tmp_path, monkeypatch):
    service, store, _, _, schedule_id, _ = configured(tmp_path)
    first = service.initial(schedule_id)
    with store.read() as unit:
        slot = unit.recurrence.relative_slot("home", first.receipt.command.key)
    reset_progress(store, schedule_id)
    original = SQLiteReceipts.get
    historical = replace(first.receipt, restoration=RestorationProvenance("fixture-restore", False))

    def altered(self, command):
        return historical if command == first.receipt.command else original(self, command)

    before, saved = counts(store), progress(store, schedule_id)
    with monkeypatch.context() as patch:
        patch.setattr(SQLiteReceipts, "get", altered)
        patch.setattr(SQLiteRelativeRecurrences, "relative_slot", lambda *args: slot)
        with pytest.raises(StorageFailure, match="invalid_recurrence_effect"):
            service.initial(schedule_id)
    assert counts(store) == before and progress(store, schedule_id) == saved
