"""Durable source admission and generation with real independent SQLite transactions."""

from dataclasses import replace

import pytest
from test_relative_materialization import configured
from test_task_commands import counts

from domus.application.recurrence_sources import RecurrenceSourceObservations
from domus.application.relative_lifecycle import RelativeLifecycle
from domus.application.relative_recurrence import RelativeRecurrencePlanner
from domus.application.task_requests import CompleteTask
from domus.domain.relative_lifecycle import RelativeClosure, RelativeClosureKind
from domus.infrastructure.sqlite import SQLiteDatabase


@pytest.mark.parametrize("timed", [False, True])
def test_actual_completion_advances_one_successor_and_replays_original_after_restart(
    tmp_path, timed
):
    initial, store, _, identifiers, schedule_id, tasks = configured(tmp_path, timed=timed)
    bootstrap = initial.initial(schedule_id)
    with store.read() as unit:
        member = unit.members.list("home")[0]
    done = tasks.complete(
        "actual", CompleteTask(bootstrap.occurrence_id, 1, (member.member_id,), 90)
    )
    source = RecurrenceSourceObservations(store, initial.scope)
    page = source.ingest(limit=1)
    assert page.source_rows_examined == 1 and not page.complete
    (record,) = page.items
    assert record.event.event_id == done.operation_id
    assert source.ingest(limit=1).items == ()
    lifecycle = RelativeLifecycle(
        store, initial.scope, RelativeRecurrencePlanner(initial.times), initial.clock, identifiers
    )
    step = lifecycle.consume(schedule_id, record.event.event_key)
    assert step.status == "generated"
    with store.read() as unit:
        rule = unit.recurrence.relative_schedule("home", schedule_id)
        key = RelativeClosure.cycle_key(rule, record.event.cycle, store.installation)
        closure = unit.recurrence.relative_closure("home", key)
        assert closure.kind is RelativeClosureKind.GENERATED and closure.matches_receipt(
            step.receipt
        )
        assert closure.successor.occurrence_id == step.occurrence_id
        successor = unit.tasks.occurrence("home", step.occurrence_id)
        assert successor.due_at == (
            closure.successor.planned.resolved.instant_ms if timed else None
        )
        saved = unit.recurrence.relative_progress("home", schedule_id)
        assert saved.current_occurrence_id == step.occurrence_id and saved.matches_receipt(
            step.receipt
        )
        assert unit.tasks.cycle("home", record.event.cycle.cycle_id) == record.event.cycle
        assert unit.recurrence.pending_relative_sources("home") == ()
    before, allocated = counts(store), identifiers.count
    restarted = replace(lifecycle, transactions=SQLiteDatabase(store.path, store.installation))
    replay = restarted.consume(schedule_id, record.event.event_key)
    assert replay == step
    assert counts(store) == before and identifiers.count == allocated


def completed(tmp_path, *, child=False, visibility=None):
    from test_relative_recurrence_creation import request, setup

    if visibility is None:
        initial, store, _, ids, schedule_id, tasks = configured(tmp_path)
    else:
        from domus.application.fixed_materialization import MaintenanceScope
        from domus.application.relative_materialization import RelativeMaintenance

        creation, tasks, store, _, ids = setup(tmp_path)
        schedule_id = creation.create("relative", request(visibility=visibility)).result.decode()[
            "schedule_id"
        ]
        initial = RelativeMaintenance(
            store, MaintenanceScope(store.installation, "home"), creation.times, creation.clock, ids
        )
    bootstrap = initial.initial(schedule_id)
    with store.read() as unit:
        member = unit.members.list("home")[0]
    tasks.complete("actual", CompleteTask(bootstrap.occurrence_id, 1, (member.member_id,), 90))
    source = RecurrenceSourceObservations(store, initial.scope)
    lifecycle = RelativeLifecycle(
        store, initial.scope, RelativeRecurrencePlanner(initial.times), initial.clock, ids
    )
    (item,) = source.ingest().items
    return store, schedule_id, bootstrap.occurrence_id, source, lifecycle, item.event, tasks, member


@pytest.mark.parametrize("surface", ["read", "replay", "snapshot"])
@pytest.mark.parametrize(
    "damage",
    [
        "close_status",
        "generated_status",
        "schedule",
        "invalidation_status",
        "invalidation_disposition",
        "invalidation_schedule",
        "different_cycle",
        "receipt_proof",
        "missing_closure",
        "invalidation_receipt",
    ],
)
def test_c38_mismatched_persisted_outcome_fails_without_effects_or_repair(
    tmp_path, surface, damage
):
    from test_sqlite_snapshots import Clock

    from domus.application.task_requests import ReopenTask
    from domus.domain.errors import DatabaseRejected, StorageFailure
    from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots

    store, rule, oid, source, service, event, tasks, member = completed(tmp_path)
    if damage == "close_status":
        tasks.reopen("reopen", ReopenTask(oid, 2, event.cycle.cycle_id, "Repeat"))
    original = service.consume(rule, event.event_key)
    target = event
    change, values = "outcome_status=?", ("generated" if damage == "close_status" else "reopened",)
    if damage.startswith("invalidation"):
        tasks.reopen("reopen", ReopenTask(oid, 2, event.cycle.cycle_id, "Repeat"))
        (observed,) = source.ingest().items
        target = observed.event
        original = service.consume(rule, target.event_key)
        assert original.status == "cancel"
        values = ("generated" if damage == "invalidation_status" else "retained",)
    if damage in ("schedule", "invalidation_schedule"):
        change, values = "outcome_schedule_id=?", ("other",)
    if damage == "different_cycle":
        from domus.domain.errors import Conflict
        from domus.domain.relative_lifecycle import RelativeEventOutcome

        tasks.complete("next", CompleteTask(original.occurrence_id, 1, (member.member_id,), 91))
        (observed,) = source.ingest().items
        other = service.consume(rule, observed.event.event_key)
        with store._connection() as connection:
            connection.execute(
                "UPDATE recurrence_relative_inbox SET outcome_status=NULL,"
                "outcome_schedule_id=NULL,outcome_operation_id=NULL,outcome_occurrence_id=NULL "
                "WHERE event_key=?",
                (target.event_key,),
            )
        with store.write() as unit:
            with pytest.raises(Conflict, match="relative_source_conflict"):
                unit.recurrence.finish_relative_source(
                    "home",
                    target.event_key,
                    RelativeEventOutcome("generated", rule, other.receipt, other.occurrence_id),
                )
            assert unit.recurrence.relative_source_outcome("home", target.event_key) is None
        change, values = (
            "outcome_status=?,outcome_schedule_id=?,outcome_operation_id=?,outcome_occurrence_id=?",
            ("generated", rule, other.receipt.operation_id, other.occurrence_id),
        )
    with store._connection() as connection:
        if damage == "receipt_proof":
            body = original.receipt.result.decode()
            body["relative_closure"]["recorded_at"] += 1
            from domus.domain.storage import JsonDocument

            connection.execute(
                "UPDATE receipts SET result=? WHERE operation_id=?",
                (JsonDocument.from_value(body).encoded, original.receipt.operation_id),
            )
            change, values = "outcome_status=?", (original.status,)
        if damage == "missing_closure":
            connection.execute("DELETE FROM recurrence_relative_closures")
            change, values = "outcome_status=?", (original.status,)
        if damage == "invalidation_receipt":
            from domus.domain.storage import JsonDocument

            body = original.receipt.result.decode()
            body["occurrence_id"] = "foreign-successor"
            connection.execute(
                "UPDATE receipts SET result=? WHERE operation_id=?",
                (JsonDocument.from_value(body).encoded, original.receipt.operation_id),
            )
            change, values = "outcome_occurrence_id=?", ("foreign-successor",)
        connection.execute(
            "UPDATE recurrence_relative_inbox SET " + change + " WHERE event_key=?",
            (*values, target.event_key),
        )
    before, bytes_before = counts(store), store.path.read_bytes()
    if surface == "snapshot":
        with pytest.raises(DatabaseRejected, match="invalid_snapshot_records"):
            SQLiteSnapshots(store, tmp_path / "invalid", store.installation, Clock()).create(
                "invalid"
            )
    else:
        reason = (
            "invalid_relative_closure_record"
            if damage == "receipt_proof"
            else "invalid_relative_outcome"
        )
        with pytest.raises(StorageFailure, match=reason):
            if surface == "read":
                with store.read() as unit:
                    unit.recurrence.relative_source_outcome("home", target.event_key)
            else:
                service.consume(rule, target.event_key)
    assert counts(store) == before and store.path.read_bytes() == bytes_before


def test_independent_writers_commit_one_original_and_one_successor(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    store, rule, _, _, service, event, _, _ = completed(tmp_path)
    independent = replace(
        service, transactions=SQLiteDatabase(store.path, store.installation, busy_timeout=5)
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(service.consume, rule, event.event_key)
        second = pool.submit(independent.consume, rule, event.event_key)
        assert first.result() == second.result()
    with store.read() as unit:
        assert len(unit.tasks.occurrences("home")) == 2
        assert unit.recurrence.pending_relative_sources("home") == ()


@pytest.mark.parametrize("stage", ["slot", "closure", "progress", "inbox"])
def test_fault_after_writing_effect_proof_or_acknowledgement_rolls_back(
    tmp_path, monkeypatch, stage
):
    from domus.domain.errors import StorageFailure
    from domus.infrastructure.sqlite_relative_lifecycle import SQLiteRelativeInbox
    from domus.infrastructure.sqlite_relative_recurrence import SQLiteRelativeRecurrences

    store, rule, _, _, service, event, _, _ = completed(tmp_path)
    before = counts(store)
    target, name = {
        "slot": (SQLiteRelativeRecurrences, "add_relative_slot"),
        "closure": (SQLiteRelativeRecurrences, "add_relative_closure"),
        "progress": (SQLiteRelativeRecurrences, "save_relative_progress"),
        "inbox": (SQLiteRelativeInbox, "finish_relative_source"),
    }[stage]
    original = getattr(target, name)

    def fail(self, *args):
        original(self, *args)
        raise StorageFailure("injected_after_write")

    with monkeypatch.context() as patch:
        patch.setattr(target, name, fail)
        with pytest.raises(StorageFailure, match="injected_after_write"):
            service.consume(rule, event.event_key)
    assert counts(store) == before
    with store.read() as unit:
        assert len(unit.recurrence.pending_relative_sources("home")) == 1
        assert len(unit.recurrence.relative_slots("home", rule)) == 1
    assert service.consume(rule, event.event_key).status == "generated"


@pytest.mark.parametrize("downstream", ["available", "assigned", "started", "completed", "unknown"])
def test_reopening_only_cancels_proven_unstarted_work(tmp_path, downstream):
    from domus.application.task_requests import AssignTask, ReopenTask, TransitionTask
    from domus.domain.task_values import OccurrenceState

    store, rule, parent, source, service, event, tasks, member = completed(tmp_path)
    generated = service.consume(rule, event.event_key)
    oid = generated.occurrence_id
    if downstream in ("assigned", "started"):
        tasks.assign("assigned", AssignTask(oid, 1, (member.member_id,)))
    if downstream == "started":
        tasks.transition("started", TransitionTask(oid, 2, OccurrenceState.IN_PROGRESS))
        tasks.transition("blocked", TransitionTask(oid, 3, OccurrenceState.BLOCKED, "Wait"))
    if downstream == "completed":
        tasks.complete("downstream", CompleteTask(oid, 1, (member.member_id,), 91))
    if downstream == "unknown":
        with store.write() as unit:
            work = unit.tasks.occurrence("home", oid)
            unit.tasks.save_occurrence(work.assign((member.member_id,)), 1)
    reopened = tasks.reopen("reopened", ReopenTask(parent, 2, event.cycle.cycle_id, "Repeat"))
    reopening = next(
        item.event for item in source.ingest().items if item.event.event_id == reopened.operation_id
    )
    with store.read() as unit:
        before = unit.tasks.occurrence("home", oid)
        cycles = unit.tasks.cycles("home")
    result = service.consume(rule, reopening.event_key)
    cancels = downstream in ("available", "assigned")
    assert result.status == ("cancel" if cancels else "review")
    assert service.consume(rule, reopening.event_key) == result
    assert service.consume(rule, event.event_key) == generated
    with store.read() as unit:
        current = unit.tasks.occurrence("home", oid)
        if cancels:
            assert current.state is OccurrenceState.CANCELLED
            assert current.state_reason == "relative_source_reopened"
            assert unit.recurrence.relative_progress("home", rule).current_occurrence_id == parent
        else:
            assert current == before
        assert unit.tasks.cycles("home") == cycles
        assert unit.receipts.get(result.receipt.command) == result.receipt


def test_compatible_restore_copies_later_cycle_proof_without_the_successor(tmp_path):
    from test_activation_compatibility import identity_at
    from test_sqlite_snapshots import Clock

    from domus.infrastructure.owned_storage import open_storage
    from domus.infrastructure.sqlite_activation import SQLiteActivation
    from domus.infrastructure.sqlite_restoration import SQLiteRestorations
    from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots

    root = tmp_path / "source"
    root.mkdir(mode=0o700)
    store, rule_id, parent, _, service, event, _, _ = completed(root)
    identity_at(root, store.installation)
    archive, prepared = tmp_path / "archive", tmp_path / "prepared"
    checkpoint = SQLiteSnapshots(store, archive, store.installation, Clock()).create("before")
    result = service.consume(rule_id, event.event_key)
    SQLiteRestorations(store, archive, prepared, store.installation, Clock(), checkpoint).prepare(
        "restore-cycle"
    )
    assert (
        SQLiteActivation(root, store.installation, Clock(), prepared).activate().state == "active"
    )
    restored = open_storage(root, "edge")
    try:
        with restored.database.read() as unit:
            rule = unit.recurrence.relative_schedule("home", rule_id)
            key = RelativeClosure.cycle_key(rule, event.cycle, store.installation)
            assert (
                unit.recurrence.relative_closure("home", key).successor.occurrence_id
                == result.occurrence_id
            )
            assert unit.tasks.occurrence("home", result.occurrence_id) is None
            assert (
                unit.recurrence.relative_progress("home", rule_id).current_occurrence_id == parent
            )
        before = counts(restored.database)
        step = replace(service, transactions=restored.database).consume(rule_id, event.event_key)
        assert step.status == "historical_absent"
        assert step.receipt.operation_id == result.receipt.operation_id and step.receipt.historical
        assert counts(restored.database) == before
    finally:
        restored.close()


def test_verification_visibility_binds_original_approval_without_moving_actual_work(tmp_path):
    from domus.application.task_requests import VerifyTask
    from domus.domain.relative_recurrence import SuccessorVisibility
    from domus.domain.task_values import VerificationState

    store, rule, oid, source, service, completed_event, tasks, _ = completed(
        tmp_path, child=True, visibility=SuccessorVisibility.AT_VERIFICATION
    )
    before = counts(store)
    waiting = service.consume(rule, completed_event.event_key)
    assert waiting.status == "waiting_verification"
    assert counts(store) == before
    tasks.verify(
        "approval", VerifyTask(oid, 2, completed_event.cycle.cycle_id, VerificationState.APPROVED)
    )
    (approval,) = source.ingest().items
    assert service.consume(rule, completed_event.event_key) == waiting
    result = service.consume(rule, approval.event.event_key)
    assert result.status == "generated"
    with store.read() as unit:
        slot = unit.recurrence.relative_slot("home", result.receipt.command.key)
        assert slot.source.cycle.performed_at == 90
        assert slot.source.cycle.verification is VerificationState.PENDING


@pytest.mark.parametrize("termination", ["reject", "reopen"])
@pytest.mark.parametrize("generated", [False, True])
def test_terminal_cycle_before_or_after_generation_never_grants_twice(
    tmp_path, termination, generated
):
    from domus.application.task_requests import ReopenTask, VerifyTask
    from domus.domain.task_values import VerificationState

    store, rule, oid, source, service, event, tasks, _ = completed(tmp_path, child=True)
    if generated:
        original = service.consume(rule, event.event_key)
        assert original.status == "generated"
    if termination == "reject":
        tasks.verify(
            "reject",
            VerifyTask(oid, 2, event.cycle.cycle_id, VerificationState.REJECTED, "Incomplete"),
        )
    else:
        tasks.reopen("reopen", ReopenTask(oid, 2, event.cycle.cycle_id, "Repeat"))
    (terminal,) = source.ingest().items
    outcome = service.consume(rule, terminal.event.event_key)
    if generated:
        assert outcome.status == "cancel"
        assert service.consume(rule, event.event_key) == original
    else:
        assert outcome.status == ("reopened" if termination == "reopen" else "rejected")
        assert service.consume(rule, event.event_key) == outcome
        with store.read() as unit:
            assert len(unit.tasks.occurrences("home")) == 1


@pytest.mark.parametrize("state", ["paused", "retired", "definition_inactive", "unrelated"])
def test_policy_outcomes_keep_distinct_inbox_dispositions(tmp_path, state):
    from test_relative_materialization import reset_progress

    from domus.domain.recurrence_records import ScheduleState
    from domus.domain.task_values import DefinitionState

    store, schedule, _, _, service, event, _, _ = completed(tmp_path)
    if state == "unrelated":
        reset_progress(store, schedule)
    else:
        with store.write() as unit:
            rule = unit.recurrence.relative_schedule("home", schedule)
            if state == "definition_inactive":
                definition = unit.tasks.definition("home", rule.definition_id)
                unit.tasks.save_definition(
                    replace(definition, state=DefinitionState.ARCHIVED, revision=2), 1
                )
            else:
                unit.recurrence.save_relative_schedule(
                    replace(rule, state=ScheduleState(state), revision=2), 1
                )
    outcome = service.consume(schedule, event.event_key)
    assert outcome.status == state and outcome.receipt is None
    with store.read() as unit:
        assert bool(unit.recurrence.pending_relative_sources("home")) == (state == "paused")


def test_source_and_schedule_lookup_fail_without_acknowledging_any_event(tmp_path):
    from domus.domain.errors import NotFound

    store, rule, _, _, service, event, _, _ = completed(tmp_path)
    with pytest.raises(NotFound, match="recurrence_source_missing"):
        service.consume(rule, "unknown")
    with pytest.raises(NotFound, match="recurrence_rule_missing"):
        service.consume("unknown", event.event_key)
    with store.read() as unit:
        assert len(unit.recurrence.pending_relative_sources("home")) == 1


@pytest.mark.parametrize("damage", ["outcome", "operation", "identity"])
def test_corrupt_inbox_is_rejected_without_a_new_effect(tmp_path, damage):
    from domus.domain.errors import StorageFailure

    store, rule, _, _, service, event, _, _ = completed(tmp_path)
    if damage == "outcome":
        service.consume(rule, event.event_key)
    with store._connection() as connection:
        change = {
            "outcome": "outcome_status='future'",
            "operation": "operation_id='missing'",
            "identity": "cycle_key='other'",
        }[damage]
        connection.execute("UPDATE recurrence_relative_inbox SET " + change)
    before = counts(store)
    with pytest.raises(StorageFailure):
        service.consume(rule, event.event_key)
    assert counts(store) == before


@pytest.mark.parametrize("damage", ["missing", "header", "proof", "slot"])
def test_independent_snapshot_rejects_orphaned_or_corrupt_cycle_proof(tmp_path, damage):
    from test_sqlite_snapshots import Clock

    from domus.domain.errors import DatabaseRejected
    from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots

    store, rule, _, _, service, event, _, _ = completed(tmp_path)
    generated = service.consume(rule, event.event_key)
    archive = tmp_path / "archive"
    snapshot = SQLiteSnapshots(store, archive, store.installation, Clock())
    with store._connection() as connection:
        if damage in ("missing", "header"):
            # A retained original can exist before any inbox acknowledgement. The independent
            # closure inventory must still detect the orphan/header mismatch in that state.
            connection.execute(
                "UPDATE recurrence_relative_inbox SET outcome_status=NULL,"
                "outcome_schedule_id=NULL,outcome_operation_id=NULL,outcome_occurrence_id=NULL"
            )
        statement = {
            "missing": "DELETE FROM recurrence_relative_closures",
            "header": "UPDATE recurrence_relative_closures SET closure_key='incorrect'",
            "proof": "UPDATE receipts SET result='{}' WHERE operation_id=?",
            "slot": "DELETE FROM recurrence_relative_slots WHERE slot_key=?",
        }[damage]
        arguments = {
            "proof": (generated.receipt.operation_id,),
            "slot": (generated.receipt.command.key,),
        }.get(damage, ())
        connection.execute(statement, arguments)
    with pytest.raises(DatabaseRejected, match="invalid_snapshot_records"):
        snapshot.create("corrupt")


@pytest.mark.parametrize("damage", ["position", "cycle", "original"])
def test_invalid_inbox_candidate_fails_before_storage(tmp_path, damage):
    from test_task_events import prepared

    from domus.domain.errors import Conflict, StorageFailure

    _, store, _, _, _, _ = prepared(tmp_path)
    with store.write() as unit:
        (original,) = unit.tasks.lifecycle_sources("home")
        if damage == "position":
            unit.recurrence.add_relative_source(original)
            observed = replace(
                original.original.evidence, position=original.original.evidence.position + 1
            )
            candidate = replace(original, original=replace(original.original, evidence=observed))
            expected = Conflict
        elif damage == "cycle":
            candidate = replace(original, cycle=replace(original.cycle, cycle_id="fake"))
            expected = StorageFailure
        else:
            candidate = replace(
                original, original=replace(original.original, archived_by="unrelated")
            )
            expected = Conflict
        with pytest.raises(expected, match="relative_source_conflict|invalid_recurrence_source"):
            unit.recurrence.add_relative_source(candidate)


@pytest.mark.parametrize("fields", [{"limit": 0}, {"after": -1}])
def test_pending_inbox_has_closed_page_limits(tmp_path, fields):
    from domus.domain.errors import InvalidInput

    store, _, _, _, _, _, _, _ = completed(tmp_path)
    with pytest.raises(InvalidInput), store.read() as unit:
        unit.recurrence.pending_relative_sources("home", **fields)


def test_snapshot_missing_outcome_operation_fails_closed(tmp_path):
    from test_sqlite_snapshots import Clock

    from domus.domain.errors import DatabaseRejected
    from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots

    store, rule, _, _, service, event, _, _ = completed(tmp_path)
    service.consume(rule, event.event_key)
    with store._connection() as connection:
        connection.execute("UPDATE recurrence_relative_inbox SET outcome_operation_id='missing'")
    with pytest.raises(DatabaseRejected, match="invalid_snapshot_records"):
        SQLiteSnapshots(store, tmp_path / "archive", store.installation, Clock()).create("bad")


def test_late_approval_reuses_generation_and_rejection_reopen_reuses_invalidation(tmp_path):
    from domus.application.task_requests import ReopenTask, VerifyTask
    from domus.domain.task_values import VerificationState

    (tmp_path / "approval").mkdir()

    store, rule, oid, source, service, event, tasks, _ = completed(
        tmp_path / "approval", child=True
    )
    before = service.consume(rule, event.event_key)
    tasks.verify("approved", VerifyTask(oid, 2, event.cycle.cycle_id, VerificationState.APPROVED))
    (approval,) = source.ingest().items
    assert service.consume(rule, approval.event.event_key) == before
    (tmp_path / "rejection").mkdir()
    store, rule, oid, source, service, event, tasks, _ = completed(
        tmp_path / "rejection", child=True
    )
    service.consume(rule, event.event_key)
    tasks.verify(
        "rejected", VerifyTask(oid, 2, event.cycle.cycle_id, VerificationState.REJECTED, "Repeat")
    )
    (rejection,) = source.ingest().items
    cancelled = service.consume(rule, rejection.event.event_key)
    tasks.reopen("opened", ReopenTask(oid, 3, event.cycle.cycle_id, "Perform again"))
    (reopening,) = source.ingest().items
    assert service.consume(rule, reopening.event.event_key) == cancelled


def test_restore_retains_a_downstream_start_even_if_current_work_looks_unstarted(tmp_path):
    from test_activation_compatibility import identity_at
    from test_sqlite_snapshots import Clock

    from domus.application.task_requests import AssignTask, ReopenTask, TransitionTask
    from domus.domain.task_values import OccurrenceState
    from domus.infrastructure.owned_storage import open_storage
    from domus.infrastructure.sqlite_activation import SQLiteActivation
    from domus.infrastructure.sqlite_restoration import SQLiteRestorations
    from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots

    root = tmp_path / "source"
    root.mkdir(mode=0o700)
    store, rule, oid, source, service, event, tasks, member = completed(root)
    generated = service.consume(rule, event.event_key)
    identity_at(root, store.installation)
    archive, target = tmp_path / "archive", tmp_path / "prepared"
    checkpoint = SQLiteSnapshots(store, archive, store.installation, Clock()).create("before-start")
    tasks.assign("assign", AssignTask(generated.occurrence_id, 1, (member.member_id,)))
    tasks.transition(
        "started", TransitionTask(generated.occurrence_id, 2, OccurrenceState.IN_PROGRESS)
    )
    SQLiteRestorations(store, archive, target, store.installation, Clock(), checkpoint).prepare(
        "restore-before-start"
    )
    SQLiteActivation(root, store.installation, Clock(), target).activate()
    restored = open_storage(root, "edge")
    try:
        reopened = replace(tasks, transactions=restored.database).reopen(
            "reopen", ReopenTask(oid, 2, event.cycle.cycle_id, "Again")
        )
        (observed,) = replace(source, transactions=restored.database).ingest().items
        assert observed.event.event_id == reopened.operation_id
        result = replace(service, transactions=restored.database).consume(
            rule, observed.event.event_key
        )
        assert result.status == "review"
        with restored.database.read() as unit:
            successor = unit.tasks.occurrence("home", generated.occurrence_id)
            assert successor.state is OccurrenceState.AVAILABLE and successor.revision == 1
    finally:
        restored.close()


@pytest.mark.parametrize("damage", ["progress", "definition", "cycle", "no_cycle", "work"])
def test_changed_or_missing_live_inputs_cannot_commit_the_observed_completion(
    tmp_path, monkeypatch, damage
):
    from domus.domain.errors import Conflict, StorageFailure
    from domus.infrastructure.sqlite_relative_recurrence import SQLiteRelativeRecurrences
    from domus.infrastructure.sqlite_tasks import SQLiteTasks

    store, rule, occurrence_id, _, service, event, _, _ = completed(tmp_path)
    with store.read() as unit:
        work = unit.tasks.occurrence("home", occurrence_id)
    if damage == "progress":
        monkeypatch.setattr(SQLiteRelativeRecurrences, "relative_progress", lambda *args: None)
    elif damage == "definition":
        monkeypatch.setattr(SQLiteTasks, "definition", lambda *args: None)
    elif damage == "cycle":
        monkeypatch.setattr(
            SQLiteTasks, "cycle", lambda *args: replace(event.cycle, performed_at=89)
        )
    elif damage == "no_cycle":
        monkeypatch.setattr(SQLiteTasks, "cycle", lambda *args: None)
    else:
        from domus.domain.task_values import OccurrenceState

        original = SQLiteTasks.occurrence

        def changed(self, household, occurrence):
            if occurrence == occurrence_id:
                return replace(
                    work,
                    state=OccurrenceState.AVAILABLE,
                    current_cycle_id=None,
                    current_cycle_revision=None,
                )
            return original(self, household, occurrence)

        monkeypatch.setattr(SQLiteTasks, "occurrence", changed)
    before = counts(store)
    with pytest.raises(
        (StorageFailure, Conflict), match="invalid_recurrence_source|recurrence_source_changed"
    ):
        service.consume(rule, event.event_key)
    assert counts(store) == before


def test_restore_of_later_completion_fences_an_absent_original_without_generating(tmp_path):
    from test_activation_compatibility import identity_at
    from test_sqlite_snapshots import Clock

    from domus.infrastructure.owned_storage import open_storage
    from domus.infrastructure.sqlite_activation import SQLiteActivation
    from domus.infrastructure.sqlite_restoration import SQLiteRestorations
    from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots

    root = tmp_path / "source"
    root.mkdir(mode=0o700)
    initial, store, _, identifiers, rule, tasks = configured(root)
    bootstrap = initial.initial(rule)
    identity_at(root, store.installation)
    archive, target = tmp_path / "archive", tmp_path / "prepared"
    checkpoint = SQLiteSnapshots(store, archive, store.installation, Clock()).create("no-cycle")
    with store.read() as unit:
        member = unit.members.list("home")[0]
    done = tasks.complete(
        "actual", CompleteTask(bootstrap.occurrence_id, 1, (member.member_id,), 90)
    )
    SQLiteRestorations(store, archive, target, store.installation, Clock(), checkpoint).prepare(
        "restore-before-completion"
    )
    SQLiteActivation(root, store.installation, Clock(), target).activate()
    restored = open_storage(root, "edge")
    try:
        source = RecurrenceSourceObservations(restored.database, initial.scope)
        (observed,) = source.ingest().items
        assert not observed.original.current and observed.event.event_id == done.operation_id
        lifecycle = RelativeLifecycle(
            restored.database,
            initial.scope,
            RelativeRecurrencePlanner(initial.times),
            initial.clock,
            identifiers,
        )
        step = lifecycle.consume(rule, observed.event.event_key)
        assert step.status == "historical_absent" and step.occurrence_id is None
        with restored.database.read() as unit:
            assert unit.tasks.cycles("home") == ()
            assert len(unit.tasks.occurrences("home")) == 1
        assert lifecycle.consume(rule, observed.event.event_key) == step
    finally:
        restored.close()


def test_inbox_rejects_outcome_from_a_different_event_or_scope(tmp_path):
    from domus.domain.errors import Conflict, StorageFailure
    from domus.domain.relative_lifecycle import RelativeEventOutcome

    store, rule, _, _, service, event, _, _ = completed(tmp_path)
    generated = service.consume(rule, event.event_key)
    with store.write() as unit:
        assert unit.recurrence.relative_source_outcome("home", "missing") is None
        with pytest.raises(Conflict, match="relative_source_conflict"):
            unit.recurrence.finish_relative_source(
                "other",
                event.event_key,
                RelativeEventOutcome("generated", rule, generated.receipt, generated.occurrence_id),
            )
        for key in ("missing", event.event_key):
            with pytest.raises(Conflict, match="relative_source_missing"):
                unit.recurrence.finish_relative_source(
                    "home",
                    key,
                    RelativeEventOutcome("unrelated", rule),
                )
    with store._connection() as connection:
        connection.execute("UPDATE recurrence_relative_inbox SET outcome_schedule_id='other'")
    with pytest.raises(StorageFailure, match="invalid_relative_outcome"):
        service.consume(rule, event.event_key)
    with store._connection() as connection:
        connection.execute(
            "UPDATE recurrence_relative_inbox SET outcome_status='unrelated',"
            "outcome_operation_id=NULL,outcome_occurrence_id=NULL"
        )
    with pytest.raises(Conflict, match="recurrence_source_changed"):
        service.consume(rule, event.event_key)


def test_relative_authority_rejects_a_different_command_even_inside_its_scope(tmp_path):
    from domus.application.relative_lifecycle import _CycleAuthority
    from domus.domain.errors import Forbidden
    from domus.domain.storage import CommandKey

    store, _, _, _, service, _, _, _ = completed(tmp_path)
    expected = CommandKey("home", "system:recurrence", "recurrence.relative.close", "original")
    with store.read() as unit, pytest.raises(Forbidden, match="maintenance_scope_denied"):
        _CycleAuthority(service.scope, expected).require(replace(expected, key="other"), unit)


def test_non_effect_outcome_rejects_effect_proof(tmp_path):
    from domus.domain.errors import InvalidInput
    from domus.domain.relative_lifecycle import RelativeEventOutcome

    _, rule, _, _, service, event, _, _ = completed(tmp_path)
    result = service.consume(rule, event.event_key)
    with pytest.raises(InvalidInput, match="invalid_relative_outcome"):
        RelativeEventOutcome("unrelated", rule, result.receipt, result.occurrence_id)


@pytest.mark.parametrize("damage", ["missing_parent", "reset_progress", "missing_receipt"])
def test_cancel_rechecks_original_proof_and_updates_only_its_own_progress(
    tmp_path, monkeypatch, damage
):
    from test_relative_materialization import reset_progress

    from domus.application.task_requests import ReopenTask
    from domus.domain.errors import StorageFailure
    from domus.infrastructure.sqlite_receipts import SQLiteReceipts
    from domus.infrastructure.sqlite_relative_recurrence import SQLiteRelativeRecurrences

    store, rule, oid, source, service, event, tasks, _ = completed(tmp_path)
    generated = service.consume(rule, event.event_key)
    if damage == "reset_progress":
        reset_progress(store, rule)
    tasks.reopen("opened", ReopenTask(oid, 2, event.cycle.cycle_id, "Again"))
    (reopening,) = source.ingest().items
    if damage == "reset_progress":
        assert service.consume(rule, reopening.event.event_key).status == "cancel"
        with store.read() as unit:
            assert unit.recurrence.relative_progress("home", rule).pristine
        return
    if damage == "missing_parent":
        monkeypatch.setattr(
            SQLiteRelativeRecurrences, "relative_slot_for_occurrence", lambda *a: None
        )
    else:
        with store.read() as unit:
            schedule = unit.recurrence.relative_schedule("home", rule)
            key = RelativeClosure.cycle_key(schedule, event.cycle, store.installation)
            closure = unit.recurrence.relative_closure("home", key)
            progress = unit.recurrence.relative_progress("home", rule)
        monkeypatch.setattr(SQLiteRelativeRecurrences, "relative_closure", lambda *a: closure)
        monkeypatch.setattr(SQLiteRelativeRecurrences, "relative_progress", lambda *a: progress)
        original = SQLiteReceipts.get

        def without_generated(self, command):
            return None if command == generated.receipt.command else original(self, command)

        monkeypatch.setattr(SQLiteReceipts, "get", without_generated)
    before = counts(store)
    with pytest.raises(StorageFailure, match="invalid_relative_closure_record"):
        service.consume(rule, reopening.event.event_key)
    assert counts(store) == before


def test_replayed_invalidation_must_still_match_its_cycle_and_successor(tmp_path):
    from test_relative_materialization import reset_progress

    from domus.application.task_requests import ReopenTask, VerifyTask
    from domus.domain.errors import StorageFailure
    from domus.domain.task_values import VerificationState

    store, rule, oid, source, service, event, tasks, _ = completed(tmp_path, child=True)
    service.consume(rule, event.event_key)
    tasks.verify(
        "rejected", VerifyTask(oid, 2, event.cycle.cycle_id, VerificationState.REJECTED, "Again")
    )
    (rejection,) = source.ingest().items
    cancelled = service.consume(rule, rejection.event.event_key)
    tasks.reopen("opened", ReopenTask(oid, 3, event.cycle.cycle_id, "Again"))
    (reopening,) = source.ingest().items
    reset_progress(store, rule)
    with store._connection() as connection:
        connection.execute(
            "UPDATE receipts SET result='{}' WHERE operation_id=?",
            (cancelled.receipt.operation_id,),
        )
    with pytest.raises(StorageFailure, match="invalid_relative_closure_record"):
        service.consume(rule, reopening.event.event_key)


def test_duplicate_and_missing_closure_proofs_are_rejected_on_direct_reads(tmp_path):
    from domus.domain.errors import Conflict, StorageFailure

    store, rule, _, _, service, event, _, _ = completed(tmp_path)
    result = service.consume(rule, event.event_key)
    with store.write() as unit:
        schedule = unit.recurrence.relative_schedule("home", rule)
        key = RelativeClosure.cycle_key(schedule, event.cycle, store.installation)
        saved = unit.recurrence.relative_closure("home", key)
        with pytest.raises(Conflict, match="relative_closure_conflict"):
            unit.recurrence.add_relative_closure(saved)
    with store._connection() as connection:
        connection.execute(
            "DELETE FROM recurrence_relative_slots WHERE slot_key=?", (result.receipt.command.key,)
        )
    with (
        store.read() as unit,
        pytest.raises(StorageFailure, match="invalid_relative_closure_record"),
    ):
        unit.recurrence.relative_closure("home", key)
    with store._connection() as connection:
        connection.execute(
            "UPDATE receipts SET result='{}' WHERE operation_id=?", (result.receipt.operation_id,)
        )
    with (
        store.read() as unit,
        pytest.raises(StorageFailure, match="invalid_relative_closure_record"),
    ):
        unit.recurrence.relative_closure("home", key)


def test_independent_closures_for_same_cycle_cannot_merge_during_restore(tmp_path):
    import shutil

    from domus.domain.errors import StorageFailure
    from domus.infrastructure.application_runtime import SecureIdentifiers
    from domus.infrastructure.sqlite_recurrence_integrity import restore_relative_closures

    store, rule, _, _, service, event, _, _ = completed(tmp_path)
    peer = SQLiteDatabase(tmp_path / "peer.sqlite3", store.installation)
    shutil.copyfile(store.path, peer.path)
    service.consume(rule, event.event_key)
    replace(service, transactions=peer, identifiers=SecureIdentifiers()).consume(
        rule, event.event_key
    )
    with store._connection() as source, peer._connection() as target:
        with pytest.raises(StorageFailure, match="invalid_relative_closure_record"):
            restore_relative_closures(target, source, store.installation)
