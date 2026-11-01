"""A composition-scoped step creates real work and advances only with durable original proof."""

from dataclasses import replace
from datetime import date

import pytest
from test_recurrence_creation import request, setup
from test_task_commands import counts

from domus.application.fixed_materialization import FixedMaintenance, MaintenanceScope
from domus.domain.errors import Conflict, Forbidden, StorageFailure
from domus.domain.recurrence_planning import FixedCursor
from domus.domain.recurrence_records import ScheduleState
from domus.domain.recurrence_rules import NominalDate
from domus.domain.recurrence_time import NominalTime
from domus.infrastructure.sqlite import SQLiteAudit, SQLiteDatabase
from domus.infrastructure.sqlite_recurrence import SQLiteRecurrences
from domus.infrastructure.sqlite_tasks import SQLiteTasks


def configured(tmp_path, *, timed=False, count=1):
    creation, _, store, actor, identifiers = setup(tmp_path)
    value = request(timed=timed)
    value = replace(value, pattern=replace(value.pattern, count=count))
    receipt = creation.create_fixed("scheduled", value)
    rule_id = receipt.result.decode()["schedule_id"]
    service = FixedMaintenance(
        store,
        MaintenanceScope(store.installation, "home"),
        creation.planner,
        creation.clock,
        identifiers,
    )
    before = (
        NominalTime(value.pattern.start.local.replace(day=31))
        if timed
        else NominalDate(date(2026, 3, 31))
    )
    return service, store, actor, identifiers, rule_id, before


@pytest.mark.parametrize("timed", [False, True])
def test_one_actual_step_commits_work_cursor_and_exact_original_evidence_without_human_performance(
    tmp_path, timed
):
    service, store, actor, _, rule_id, before = configured(tmp_path, timed=timed)
    actor_calls = actor.calls
    initial = counts(store)
    result = service.step(rule_id, before)
    assert result.status == "created" and result.range_complete and result.cursor.closed
    assert result.receipt.command.actor_id == "system:recurrence"
    assert result.receipt.command.action == "recurrence.materialize"
    with store.read() as unit:
        slot = unit.recurrence.slot("home", result.receipt.command.key)
        work = unit.tasks.occurrence("home", result.occurrence_id)
        progress = unit.recurrence.progress("home", rule_id)
        assert progress.cursor == result.cursor and progress.revision == 2
        assert progress.last_run_at == 100 and progress.range_complete
        assert work.current_cycle_id is None and work.assignee_ids == ()
        assert slot.occurrence_id == work.occurrence_id
        assert unit.receipts.get(slot.command) == result.receipt
        assert result.receipt.result.decode()["slot_key"] == slot.key
        assert unit.audit.entries("home")[-1].operation_id == result.receipt.operation_id
        assert unit.outbox.pending()[-1].event_id == result.receipt.operation_id
        if timed:
            assert slot.planned.resolved.resolved_local.hour == 3
            assert work.due_at == slot.planned.resolved.instant_ms
        else:
            assert slot.planned.nominal.local == date(2026, 3, 29) and work.due_at is None
    assert counts(store) == (initial[0], 1, initial[2] + 1, initial[3] + 1)
    assert actor.calls == actor_calls


def test_restart_at_terminal_cursor_creates_no_more_work_or_evidence(tmp_path):
    service, store, _, identifiers, rule_id, before = configured(tmp_path)
    first = service.step(rule_id, before)
    initial = counts(store)
    allocated = identifiers.count
    restarted = replace(service, transactions=SQLiteDatabase(store.path, store.installation))
    second = restarted.step(rule_id, before)
    assert second.status == "current" and second.receipt is None
    assert second.cursor == first.cursor and second.range_complete
    assert counts(store) == initial and identifiers.count == allocated


@pytest.mark.parametrize("stage", ["occurrence", "slot", "audit", "progress"])
def test_failure_after_any_new_effect_rolls_back_task_cursor_and_command_proofs(
    tmp_path, monkeypatch, stage
):
    service, store, _, _, rule_id, before = configured(tmp_path)
    target, name = {
        "occurrence": (SQLiteTasks, "save_occurrence"),
        "slot": (SQLiteRecurrences, "add_slot"),
        "audit": (SQLiteAudit, "append"),
        "progress": (SQLiteRecurrences, "save_progress"),
    }[stage]
    method = getattr(target, name)
    initial = counts(store)
    with store.read() as unit:
        original = unit.recurrence.progress("home", rule_id)

    def fail(self, *args):
        method(self, *args)
        raise StorageFailure("fixture_after_effect")

    with monkeypatch.context() as patch:
        patch.setattr(target, name, fail)
        with pytest.raises(StorageFailure, match="fixture_after_effect"):
            service.step(rule_id, before)
    assert counts(store) == initial
    with store.read() as unit:
        assert unit.recurrence.progress("home", rule_id) == original
        assert unit.recurrence.slots("home", rule_id) == ()
    assert service.step(rule_id, before).status == "created"


@pytest.mark.parametrize("change", ["channel", "installation", "household"])
def test_maintenance_scope_never_crosses_installation_channel_or_household(tmp_path, change):
    service, store, _, _, rule_id, before = configured(tmp_path)
    scope = service.scope
    if change == "household":
        scope = replace(scope, household_id="other")
    else:
        scope = replace(
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
    initial = counts(store)
    with pytest.raises(Forbidden):
        replace(service, scope=scope).step(rule_id, before)
    assert counts(store) == initial


def test_paused_rule_has_no_effect_and_pause_after_planning_invalidates_the_write(
    tmp_path, monkeypatch
):
    from domus.application.fixed_recurrence import FixedRecurrencePlanner

    service, store, _, _, rule_id, before = configured(tmp_path)
    original = FixedRecurrencePlanner.expand

    def pause(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        with store.write() as unit:
            rule = unit.recurrence.schedule("home", rule_id)
            unit.recurrence.save_schedule(replace(rule, state=ScheduleState.PAUSED, revision=2), 1)
        return result

    initial = counts(store)
    with monkeypatch.context() as patch:
        patch.setattr(FixedRecurrencePlanner, "expand", pause)
        with pytest.raises(Conflict, match="recurrence_source_changed"):
            service.step(rule_id, before)
    assert service.step(rule_id, before).status == "paused"
    assert counts(store) == initial


def test_replaying_a_proved_current_slot_advances_progress_without_duplicate_work(tmp_path):
    service, store, _, identifiers, rule_id, before = configured(tmp_path)
    first = service.step(rule_id, before)
    initial = counts(store)
    allocated = identifiers.count
    with store.write() as unit:
        progress = unit.recurrence.progress("home", rule_id)
        unit.recurrence.save_progress(
            replace(
                progress,
                revision=3,
                cursor=FixedCursor(progress.cursor.binding),
                range_complete=False,
            ),
            2,
        )
    second = service.step(rule_id, before)
    assert second.status == "replayed" and second.receipt == first.receipt
    assert counts(store) == initial and identifiers.count == allocated


def test_actual_restore_retains_absent_slot_proof_and_step_never_recreates_it(tmp_path):
    from test_activation_compatibility import identity_at
    from test_sqlite_snapshots import Clock

    from domus.infrastructure.owned_storage import open_storage
    from domus.infrastructure.sqlite_activation import SQLiteActivation
    from domus.infrastructure.sqlite_restoration import SQLiteRestorations
    from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots

    root = tmp_path / "source"
    root.mkdir(mode=0o700)
    service, store, _, identifiers, rule_id, before = configured(root)
    identity_at(root, store.installation)
    archive = tmp_path / "checkpoint"
    target = tmp_path / "prepared"
    checkpoint = SQLiteSnapshots(store, archive, store.installation, Clock()).create("before-slot")
    first = service.step(rule_id, before)
    SQLiteRestorations(store, archive, target, store.installation, Clock(), checkpoint).prepare(
        "restore-slot"
    )
    assert SQLiteActivation(root, store.installation, Clock(), target).activate().state == "active"
    storage = open_storage(root, "edge")
    try:
        allocated = identifiers.count
        second = replace(service, transactions=storage.database).step(rule_id, before)
        assert second.status == "historical_absent" and second.receipt.historical
        assert second.receipt.operation_id == first.receipt.operation_id
        assert second.receipt.archived_by == "restore-slot" and identifiers.count == allocated
        with storage.database.read() as unit:
            assert unit.tasks.occurrences("home") == ()
            assert unit.recurrence.slots("home", rule_id) == ()
            assert unit.recurrence.progress("home", rule_id).cursor.closed
            assert all(
                event.event_id != first.receipt.operation_id for event in unit.outbox.pending()
            )
        assert (
            replace(service, transactions=storage.database).step(rule_id, before).status
            == "current"
        )
    finally:
        storage.close()


def test_changed_source_is_rejected_before_protected_receipt_lookup(tmp_path, monkeypatch):
    from domus.application.fixed_recurrence import FixedRecurrencePlanner
    from domus.infrastructure.sqlite import SQLiteReceipts

    service, store, _, _, rule_id, before = configured(tmp_path)
    expand = FixedRecurrencePlanner.expand

    def change(self, *args, **kwargs):
        batch = expand(self, *args, **kwargs)
        with store.write() as unit:
            rule = unit.recurrence.schedule("home", rule_id)
            unit.recurrence.save_schedule(replace(rule, revision=2, state=ScheduleState.PAUSED), 1)
        return batch

    def denied_lookup(*args):
        pytest.fail("Current maintenance authority must precede any protected receipt lookup")

    monkeypatch.setattr(FixedRecurrencePlanner, "expand", change)
    monkeypatch.setattr(SQLiteReceipts, "get", denied_lookup)
    with pytest.raises(Conflict, match="recurrence_source_changed"):
        service.step(rule_id, before)


def rewind(store, rule_id):
    with store.write() as unit:
        progress = unit.recurrence.progress("home", rule_id)
        unit.recurrence.save_progress(
            replace(
                progress,
                revision=progress.revision + 1,
                cursor=FixedCursor(progress.cursor.binding),
                range_complete=False,
            ),
            progress.revision,
        )


@pytest.mark.parametrize("limit", [0, 65, True])
def test_invalid_step_budgets_fail_before_any_effect(tmp_path, limit):
    from domus.domain.errors import InvalidInput

    service, store, _, _, rule_id, before = configured(tmp_path)
    initial = counts(store)
    with pytest.raises(InvalidInput):
        service.step(rule_id, before, period_limit=limit)
    assert counts(store) == initial


def test_a_future_horizon_scan_has_its_own_bounded_proof_and_never_consumes_first_work(tmp_path):
    service, store, _, _, rule_id, before = configured(tmp_path)
    earlier = NominalDate(date(2026, 3, 28))
    result = service.step(rule_id, earlier)
    assert result.status == "scan" and result.range_complete and result.cursor.nominal_count == 0
    assert result.receipt.command.action == "recurrence.scan" and result.occurrence_id is None
    initial = counts(store)
    assert service.step(rule_id, earlier).status == "current" and counts(store) == initial
    assert service.step(rule_id, before).status == "created"


@pytest.mark.parametrize("change", ["missing-progress", "missing-definition", "wrong-binding"])
def test_inconsistent_durable_source_is_not_an_empty_or_successful_step(tmp_path, change):
    from domus.infrastructure.sqlite_recurrence_records import progress_document

    service, store, _, _, rule_id, before = configured(tmp_path)
    with store._connection() as connection:
        if change == "missing-progress":
            connection.execute("DELETE FROM recurrence_progress")
        elif change == "missing-definition":
            connection.execute("DELETE FROM task_definitions")
        else:
            with store.read() as unit:
                progress = unit.recurrence.progress("home", rule_id)
            connection.execute(
                "UPDATE recurrence_progress SET document=?",
                (progress_document(replace(progress, cursor=FixedCursor("a" * 64))).encoded,),
            )
    with pytest.raises(StorageFailure, match="invalid_recurrence_source"):
        service.step(rule_id, before)


def test_missing_rule_empty_installation_and_untyped_capability_have_distinct_safe_failures(
    tmp_path,
):
    from test_atomic_commands import store_at

    from domus.domain.errors import InvalidInput, NotFound

    service, _, _, _, _, before = configured(tmp_path)
    with pytest.raises(NotFound, match="recurrence_rule_missing"):
        service.step("absent", before)
    with pytest.raises(InvalidInput):
        MaintenanceScope(None, "home")
    empty = store_at(tmp_path / "empty.sqlite3")
    with pytest.raises(Forbidden):
        replace(service, transactions=empty).step("absent", before)


@pytest.mark.parametrize("change", ["retired", "definition-paused"])
def test_inactive_source_remains_unchanged(tmp_path, change):
    from domus.domain.task_values import DefinitionState

    service, store, _, _, rule_id, before = configured(tmp_path)
    with store.write() as unit:
        rule = unit.recurrence.schedule("home", rule_id)
        if change == "retired":
            unit.recurrence.save_schedule(replace(rule, state=ScheduleState.RETIRED, revision=2), 1)
        else:
            item = unit.tasks.definition("home", rule.definition_id)
            unit.tasks.save_definition(replace(item, state=DefinitionState.PAUSED, revision=2), 1)
    initial = counts(store)
    assert service.step(rule_id, before).status == (
        "retired" if change == "retired" else "definition_inactive"
    )
    assert counts(store) == initial


@pytest.mark.parametrize("change", ["occurrence-id", "slot-key", "missing-slot", "future-snapshot"])
def test_corrupt_current_original_effect_is_not_recreated_or_consumed_as_valid_progress(
    tmp_path, change
):
    import json

    service, store, _, _, rule_id, before = configured(tmp_path)
    original = service.step(rule_id, before)
    rewind(store, rule_id)
    with store._connection() as connection:
        if change in ("occurrence-id", "slot-key"):
            data = original.receipt.result.decode()
            data["occurrence_id" if change == "occurrence-id" else "slot_key"] = (
                "" if change == "occurrence-id" else "wrong"
            )
            connection.execute(
                "UPDATE receipts SET result=? WHERE command_key=?",
                (json.dumps(data), original.receipt.command.key),
            )
        elif change == "missing-slot":
            connection.execute("DELETE FROM recurrence_slots")
        else:
            row = connection.execute("SELECT document FROM recurrence_slots").fetchone()
            data = json.loads(row[0])
            data["schedule"]["revision"] = 2
            connection.execute("UPDATE recurrence_slots SET document=?", (json.dumps(data),))
    initial = counts(store)
    with pytest.raises(StorageFailure, match="invalid_recurrence_effect"):
        service.step(rule_id, before)
    assert counts(store) == initial
    with store.read() as unit:
        assert unit.recurrence.progress("home", rule_id).cursor.nominal_count == 0


def test_contradictory_historical_receipt_projection_cannot_hide_a_current_effect(
    tmp_path, monkeypatch
):
    from domus.domain.storage import RestorationProvenance
    from domus.infrastructure.sqlite import SQLiteReceipts

    service, store, _, _, rule_id, before = configured(tmp_path)
    first = service.step(rule_id, before)
    rewind(store, rule_id)
    original = SQLiteReceipts.get

    def inconsistent(self, command):
        result = original(self, command)
        return (
            replace(result, restoration=RestorationProvenance("fixture_restore", False))
            if result == first.receipt
            else result
        )

    monkeypatch.setattr(SQLiteReceipts, "get", inconsistent)
    with pytest.raises(StorageFailure, match="invalid_recurrence_effect"):
        service.step(rule_id, before)


@pytest.mark.parametrize(
    "change",
    ["input-key", "household", "human-actor", "human-action", "paused", "inactive-definition"],
)
def test_technical_authority_cannot_be_repurposed_for_another_command_or_inactive_record(
    tmp_path, change
):
    from domus.application.fixed_materialization import _FixedAuthority
    from domus.domain.storage import CommandKey
    from domus.domain.task_values import DefinitionState

    service, store, _, _, rule_id, _ = configured(tmp_path)
    command = CommandKey("home", "system:recurrence", "recurrence.materialize", "slot")
    with store.read() as unit:
        source = service._source(unit, rule_id)
        if change == "household":
            command = replace(command, household_id="other")
        elif change == "human-actor":
            command = replace(command, actor_id="ha_admin")
        elif change == "human-action":
            command = replace(command, action="task.complete")
        elif change == "paused":
            source = replace(source, schedule=replace(source.schedule, state=ScheduleState.PAUSED))
        elif change == "inactive-definition":
            source = replace(
                source, definition=replace(source.definition, state=DefinitionState.PAUSED)
            )
        authority = _FixedAuthority(service.scope, source, command)
        submitted = replace(command, key="other") if change == "input-key" else command
        with pytest.raises(Forbidden):
            authority.require(submitted, unit)


def test_empty_period_work_exhausts_its_budget_with_durable_incomplete_progress(tmp_path):
    from domus.domain.recurrence_planning import cursor_binding
    from domus.domain.recurrence_rules import Frequency

    service, store, _, _, rule_id, _ = configured(tmp_path)
    with store.write() as unit:
        rule = unit.recurrence.schedule("home", rule_id)
        pattern = replace(
            rule.pattern, frequency=Frequency.YEARLY, by_month=(2,), by_month_day=(30,), count=None
        )
        rule = replace(rule, revision=2, pattern_revision=2, pattern=pattern)
        progress = unit.recurrence.progress("home", rule_id)
        unit.recurrence.save_schedule(rule, 1)
        unit.recurrence.save_progress(
            replace(
                progress,
                revision=2,
                pattern_revision=2,
                cursor=FixedCursor(cursor_binding(pattern, rule.policy)),
            ),
            1,
        )
    initial = counts(store)
    first = service.step(rule_id, NominalDate(date(2036, 1, 1)), period_limit=3)
    assert first.status == "scan" and first.periods_scanned == 3 and not first.range_complete
    assert first.cursor.period_index == 3 and first.cursor.nominal_count == 0
    with store.read() as unit:
        assert unit.recurrence.progress("home", rule_id).cursor == first.cursor
    second = service.step(rule_id, NominalDate(date(2036, 1, 1)), period_limit=3)
    assert (
        second.cursor.period_index == 6 and second.receipt.command.key != first.receipt.command.key
    )
    assert counts(store) == (initial[0], 0, initial[2] + 2, initial[3] + 2)


def test_actual_independent_step_writers_have_one_complete_winner(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from domus.application.fixed_recurrence import FixedRecurrencePlanner
    from domus.domain.errors import StorageBusy
    from domus.infrastructure.application_runtime import SecureIdentifiers

    service, store, _, _, rule_id, before = configured(tmp_path)
    independent = replace(
        service,
        transactions=SQLiteDatabase(store.path, store.installation, busy_timeout=5),
        identifiers=SecureIdentifiers(),
    )
    gate = Barrier(2)
    expand = FixedRecurrencePlanner.expand

    def planned(self, *args, **kwargs):
        batch = expand(self, *args, **kwargs)
        gate.wait(timeout=5)
        return batch

    def run(candidate):
        try:
            return candidate.step(rule_id, before).status
        except Conflict:
            return "conflict"
        except StorageBusy:
            return "busy"

    with monkeypatch.context() as patch:
        patch.setattr(FixedRecurrencePlanner, "expand", planned)
        with ThreadPoolExecutor(max_workers=2) as workers:
            outcomes = list(workers.map(run, (service, independent)))
    assert outcomes.count("created") == 1 and len(set(outcomes) & {"conflict", "busy"}) == 1
    assert service.step(rule_id, before).status == "current"
    assert counts(store) == (1, 1, 3, 3)


def test_conflicting_original_payload_never_advances_or_replaces_a_slot(tmp_path):
    service, store, _, _, rule_id, before = configured(tmp_path)
    first = service.step(rule_id, before)
    rewind(store, rule_id)
    initial = counts(store)
    with store._connection() as connection:
        connection.execute(
            "UPDATE receipts SET payload_fingerprint=? WHERE command_key=?",
            ("f" * 64, first.receipt.command.key),
        )
    with pytest.raises(Conflict, match="idempotency_conflict"):
        service.step(rule_id, before)
    assert counts(store) == initial
    with store.read() as unit:
        assert unit.recurrence.progress("home", rule_id).cursor.nominal_count == 0


def test_date_only_maintenance_still_requires_the_actual_pinned_policy_without_writer_lock(
    tmp_path, monkeypatch
):
    from domus.domain.errors import IntegrationUnavailable
    from domus.infrastructure.recurrence_time import PinnedRecurrenceTime

    service, store, _, _, rule_id, before = configured(tmp_path)
    initial = counts(store)

    def unavailable(self, policy):
        # An independent writer can still enter while external policy data is consulted.
        with store.write():
            pass
        raise IntegrationUnavailable("timezone_source_unavailable")

    monkeypatch.setattr(PinnedRecurrenceTime, "require_policy", unavailable)
    with pytest.raises(IntegrationUnavailable, match="timezone_source_unavailable"):
        service.step(rule_id, before)
    assert counts(store) == initial
