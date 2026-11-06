"""Review decisions preserve original work and survive transaction and runtime boundaries."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier

import pytest
from test_activation_compatibility import identity_at
from test_relative_materialization import configured, progress, reset_progress
from test_sqlite_snapshots import Clock
from test_task_commands import counts

from domus.application.recurrence_review import (
    ManualAdoption,
    RecurrenceReview,
    ReviewAction,
    ReviewedAdoption,
    _ReviewAuthority,
)
from domus.application.task_authorization import TaskAccess
from domus.application.task_requests import CreateTaskOccurrence, TransitionTask
from domus.domain.errors import Conflict, Forbidden, InvalidInput, NotFound, StorageFailure
from domus.domain.identity import HumanIdentity
from domus.domain.recurrence_records import ScheduleState
from domus.domain.relative_recurrence import RelativeSlot
from domus.domain.storage import CommandKey
from domus.domain.task_values import OccurrenceState
from domus.infrastructure.application_runtime import SecureIdentifiers
from domus.infrastructure.owned_storage import open_storage
from domus.infrastructure.sqlite import SQLiteDatabase, SQLiteOutbox
from domus.infrastructure.sqlite_activation import SQLiteActivation
from domus.infrastructure.sqlite_restoration import SQLiteRestorations
from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots


def manual_fixture(tmp_path, *, timed=False, assigned=False):
    initial, store, actor, ids, schedule_id, tasks = configured(tmp_path, timed=timed)
    with store.read() as unit:
        rule = unit.recurrence.relative_schedule("home", schedule_id)
    due = rule.initial.resolved
    manual = tasks.create_occurrence(
        "manual",
        CreateTaskOccurrence(
            rule.definition_id,
            assignee_ids=("child",) if assigned else (),
            due_at=None if due is None else due.instant_ms,
        ),
    )
    service = RecurrenceReview(store, store.installation, actor, actor.current, initial.clock, ids)
    work = manual.result.decode()
    return service, initial, tasks, ManualAdoption(schedule_id, 1, work["occurrence_id"], 1)


def reviewed(service, selection, key="preview"):
    preview = service.preview(key, selection)
    return preview, ReviewedAdoption(selection, key, preview.result.decode()["plan_fingerprint"])


@pytest.mark.parametrize("timed,assigned", [(False, False), (True, True)])
def test_manual_adoption_binds_exact_existing_work_and_replays_after_restart(
    tmp_path, timed, assigned
):
    service, initial, _, choice = manual_fixture(tmp_path, timed=timed, assigned=assigned)
    store = service.transactions
    assert initial.initial(choice.schedule_id).status == "initial_review_required"
    with store.read() as unit:
        before = unit.tasks.occurrence("home", choice.occurrence_id)
    preview, change = reviewed(service, choice)
    plan = preview.result.decode()["plan"]
    assert plan["retained_occurrence_id"] == before.occurrence_id
    assert plan["due_at"] == before.due_at and plan["request"]["occurrence_revision"] == 1
    assert preview.result.decode()["expires_at"] == 300_100
    first = service.apply("apply", change)
    reopened = replace(service, transactions=SQLiteDatabase(store.path, store.installation))
    assert reopened.original(ReviewAction.APPLY, "apply") == first
    assert reopened.apply("apply", change) == first
    assert reopened.preview("preview", choice) == preview
    with pytest.raises(Conflict, match="idempotency_conflict"):
        reopened.apply("apply", replace(change, plan_fingerprint="a" * 64))
    with store.read() as unit:
        assert unit.tasks.occurrences("home") == (before,)
        assert unit.tasks.cycles("home") == ()
        (slot,) = unit.recurrence.relative_slots("home", choice.schedule_id)
        evidence = unit.receipts.get(slot.command)
        assert slot.occurrence_id == before.occurrence_id
        assert slot.matches_receipt(evidence)
        assert evidence.operation_id == first.result.decode()["materialization_operation_id"]
        assert unit.audit.entries("home")[-1].operation_id == first.operation_id
        assert unit.outbox.pending()[-1].event_id == first.operation_id
    assert progress(store, choice.schedule_id).matches_receipt(evidence)
    assert initial.initial(choice.schedule_id).status == "current"


def test_concurrent_start_requires_review_refresh_and_never_creates_a_second_initial(tmp_path):
    service, initial, tasks, choice = manual_fixture(tmp_path, assigned=True)
    _, change = reviewed(service, choice)
    tasks.transition("start", TransitionTask(choice.occurrence_id, 1, OccurrenceState.IN_PROGRESS))
    before = counts(service.transactions)
    with pytest.raises(Conflict, match="recurrence_review_stale"):
        service.apply("apply", change)
    with pytest.raises(Conflict, match="recurrence_adoption_incompatible"):
        service.preview("fresh", replace(choice, occurrence_revision=2))
    assert counts(service.transactions) == before
    assert progress(service.transactions, choice.schedule_id).pristine
    assert initial.initial(choice.schedule_id).status == "initial_review_required"


@pytest.mark.parametrize("change", ["scope", "rule", "progress", "definition", "due", "work"])
def test_manual_adoption_requires_current_exact_compatible_facts(tmp_path, change):
    service, _, _, choice = manual_fixture(tmp_path)
    store = service.transactions
    if change == "scope":
        service = replace(service, installation=replace(store.installation, channel="stable"))
        with pytest.raises(Forbidden):
            service.preview("preview", choice)
        return
    if change == "progress":
        _, request = reviewed(service, choice)
        service.apply("initial-apply", request)
    with store.write() as unit:
        rule = unit.recurrence.relative_schedule("home", choice.schedule_id)
        work = unit.tasks.occurrence("home", choice.occurrence_id)
        if change == "rule":
            unit.recurrence.save_relative_schedule(
                replace(rule, state=ScheduleState.PAUSED, revision=2), 1
            )
            choice = replace(choice, schedule_revision=2)
        elif change == "definition":
            definition = work.definition_snapshot
            unit.tasks.save_definition(replace(definition, revision=2), 1)
        elif change == "due":
            unit.tasks.save_occurrence(replace(work, due_at=1, revision=2), 1)
            choice = replace(choice, occurrence_revision=2)
        elif change == "work":
            choice = replace(choice, occurrence_id="missing")
    before = counts(store)
    with pytest.raises(Conflict, match="recurrence_(adoption_incompatible|review_stale)"):
        service.preview("fresh", choice)
    assert counts(store) == before


def test_preview_scope_payload_expiry_and_current_authority_are_required(tmp_path):
    service, _, _, choice = manual_fixture(tmp_path)
    _, change = reviewed(service, choice)
    store = service.transactions
    with pytest.raises(NotFound, match="operation_missing"):
        service.original(ReviewAction.APPLY, "apply")
    with pytest.raises(InvalidInput, match="invalid_recurrence_review_action"):
        service.original("task.create", "apply")
    with pytest.raises(InvalidInput, match="invalid_recurrence_review"):
        replace(change, plan_fingerprint="invalid")
    for mismatch in (
        replace(change, preview_key="missing"),
        replace(change, selection=replace(choice, schedule_revision=2)),
        replace(change, plan_fingerprint="0" * 64),
    ):
        with pytest.raises(Conflict, match="recurrence_review_stale"):
            service.apply("apply", mismatch)
    later = replace(service, clock=type("Clock", (), {"now": lambda _: 300_100})())
    with pytest.raises(Conflict, match="recurrence_review_stale"):
        later.apply("apply", change)
    first = service.apply("apply", change)
    assert later.apply("apply", change) == first
    service.actor.human = HumanIdentity("ha_child", False, True, False)
    before = counts(store)
    with pytest.raises(Forbidden):
        service.apply("apply", change)
    with pytest.raises(Forbidden):
        service.original(ReviewAction.APPLY, "apply")
    assert counts(store) == before


def test_preview_rejects_changed_member_context_even_with_current_manage_grant(tmp_path):
    service, _, _, choice = manual_fixture(tmp_path)
    _, change = reviewed(service, choice)
    with service.transactions.write() as unit:
        member = unit.members.by_user("home", service.actor.human.ha_user_id)
        unit.members.save(replace(member, revision=member.revision + 1), member.revision)
    with pytest.raises(Conflict, match="recurrence_review_stale"):
        service.apply("apply", change)


def test_failure_after_human_outbox_rolls_back_both_receipts_and_mapping(tmp_path, monkeypatch):
    service, initial, _, choice = manual_fixture(tmp_path)
    _, change = reviewed(service, choice)
    store = service.transactions
    before = counts(store)
    original = SQLiteOutbox.append

    def fail(self, event):
        original(self, event)
        if event.event_type == ReviewAction.APPLY:
            raise StorageFailure("review_rollback")

    with monkeypatch.context() as patch:
        patch.setattr(SQLiteOutbox, "append", fail)
        with pytest.raises(StorageFailure, match="review_rollback"):
            service.apply("apply", change)
    assert counts(store) == before and progress(store, choice.schedule_id).pristine
    with store.read() as unit:
        assert unit.recurrence.relative_slots("home", choice.schedule_id) == ()
        rule = unit.recurrence.relative_schedule("home", choice.schedule_id)
        probe = RelativeSlot(store.installation, rule, rule.initial, choice.occurrence_id, 100)
        assert unit.receipts.get(probe.command) is None
    with pytest.raises(NotFound):
        service.original(ReviewAction.APPLY, "apply")
    assert service.apply("apply", change)
    assert initial.initial(choice.schedule_id).status == "current"


@pytest.mark.parametrize("same_key", [False, True])
def test_independent_writers_bind_one_initial_slot(tmp_path, same_key):
    service, _, _, choice = manual_fixture(tmp_path)
    _, change = reviewed(service, choice)
    store = service.transactions
    before = counts(store)
    barrier = Barrier(2)

    def apply(index):
        fresh = replace(
            service,
            transactions=SQLiteDatabase(store.path, store.installation),
            identifiers=SecureIdentifiers(),
        )
        barrier.wait(timeout=5)
        try:
            return fresh.apply("apply" if same_key else f"apply-{index}", change)
        except Conflict as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = pool.map(apply, range(2))
    if same_key:
        assert first == second
    else:
        assert sum(isinstance(value, Conflict) for value in (first, second)) == 1
    assert counts(store) == (before[0], before[1], before[2] + 2, before[3] + 2)
    assert progress(store, choice.schedule_id).current_occurrence_id == choice.occurrence_id


def test_restore_preserves_manual_work_and_original_proof_without_recreating_mapping(tmp_path):
    root, archive, target = tmp_path / "root", tmp_path / "archive", tmp_path / "prepared"
    root.mkdir(mode=0o700)
    service, initial, _, choice = manual_fixture(root)
    store = service.transactions
    identity_at(root, store.installation)
    checkpoint = SQLiteSnapshots(store, archive, store.installation, Clock()).create(
        "before-review"
    )
    _, change = reviewed(service, choice)
    applied = service.apply("apply", change)
    SQLiteRestorations(store, archive, target, store.installation, Clock(), checkpoint).prepare(
        "review-restore"
    )
    assert SQLiteActivation(root, store.installation, Clock(), target).activate().state == "active"
    restored = open_storage(root, "edge")
    try:
        review = replace(service, transactions=restored.database)
        original = review.original(ReviewAction.APPLY, "apply")
        assert original.historical
        assert original.operation_id == applied.operation_id and original.result == applied.result
        assert review.apply("apply", change) == original
        with pytest.raises(Conflict, match="recurrence_review_stale"):
            review.apply("other", change)
        recovered = replace(initial, transactions=restored.database).initial(choice.schedule_id)
        assert recovered.status == "historical_absent"
        assert recovered.occurrence_id == choice.occurrence_id
        with restored.database.read() as unit:
            (work,) = unit.tasks.occurrences("home")
            assert work.occurrence_id == choice.occurrence_id and work.revision == 1
            assert unit.recurrence.relative_slots("home", choice.schedule_id) == ()
    finally:
        restored.close()


def test_original_technical_proof_blocks_a_fresh_manual_review(tmp_path):
    service, initial, tasks, choice = manual_fixture(tmp_path)
    _, request = reviewed(service, choice)
    service.apply("apply", request)
    reset_progress(service.transactions, choice.schedule_id)
    with service.transactions.read() as unit:
        rule = unit.recurrence.relative_schedule("home", choice.schedule_id)
    second = tasks.create_occurrence("another-manual", CreateTaskOccurrence(rule.definition_id))
    second_id = second.result.decode()["occurrence_id"]
    with pytest.raises(Conflict, match="recurrence_initial_already_consumed"):
        service.preview("second", replace(choice, occurrence_id=second_id))
    recovered = initial.initial(choice.schedule_id)
    assert recovered.status == "replayed"
    assert recovered.occurrence_id == choice.occurrence_id


def test_bound_review_authority_cannot_be_used_for_another_command(tmp_path):
    service, initial, _, _ = manual_fixture(tmp_path)
    command = CommandKey("home", "ha_admin", ReviewAction.PREVIEW.value, "preview")
    authority = _ReviewAuthority(initial.scope, TaskAccess(service.actor.human), command)
    with service.transactions.read() as unit, pytest.raises(Forbidden):
        authority.require(replace(command, action=ReviewAction.APPLY.value), unit)
