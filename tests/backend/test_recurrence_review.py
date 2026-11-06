"""Review decisions preserve original work and survive transaction and runtime boundaries."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier

import pytest
from test_activation_compatibility import identity_at
from test_relative_lifecycle_consumer import completed
from test_relative_materialization import configured, progress, reset_progress
from test_sqlite_snapshots import Clock
from test_task_commands import counts

from domus.application.recurrence_review import (
    ManualAdoption,
    RecurrenceReview,
    ReviewAction,
    ReviewedChange,
    _ReviewAuthority,
)
from domus.application.relative_recurrence import RelativeRecurrencePlanner
from domus.application.relative_state_review import RelativeStateChange
from domus.application.task_authorization import TaskAccess
from domus.application.task_commands import TaskCommands
from domus.application.task_requests import (
    AssignTask,
    CreateTaskOccurrence,
    ReopenTask,
    TransitionTask,
    VerifyTask,
)
from domus.domain.errors import (
    Conflict,
    Forbidden,
    IntegrationUnavailable,
    InvalidInput,
    NotFound,
    StorageFailure,
)
from domus.domain.identity import HumanIdentity
from domus.domain.recurrence_records import ScheduleState
from domus.domain.relative_recurrence import RelativeSlot, SuccessorVisibility
from domus.domain.storage import CommandKey, JsonDocument
from domus.domain.task_values import DefinitionState, OccurrenceState, VerificationState
from domus.infrastructure.application_runtime import SecureIdentifiers
from domus.infrastructure.owned_storage import open_storage
from domus.infrastructure.sqlite import SQLiteDatabase, SQLiteOutbox, SQLiteReceipts
from domus.infrastructure.sqlite_activation import SQLiteActivation
from domus.infrastructure.sqlite_restoration import SQLiteRestorations
from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots
from domus.infrastructure.sqlite_tasks import SQLiteTasks


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
    service = review_service(initial, store, actor, ids)
    work = manual.result.decode()
    return service, initial, tasks, ManualAdoption(schedule_id, 1, work["occurrence_id"], 1)


def review_service(initial, store, actor, ids):
    return RecurrenceReview(
        store,
        store.installation,
        actor,
        actor.current,
        initial.clock,
        ids,
        RelativeRecurrencePlanner(initial.times),
    )


def reviewed(service, selection, key="preview"):
    preview = service.preview(key, selection)
    return preview, ReviewedChange(selection, key, preview.result.decode()["plan_fingerprint"])


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
        change_state(review, choice.schedule_id, 1, ScheduleState.PAUSED, "pause")
        resume, _ = change_state(review, choice.schedule_id, 2, ScheduleState.ACTIVE, "resume")
        assert resume.result.decode()["plan"]["backlog"]["status"] == "historical_absent"
        recovered = replace(initial, transactions=restored.database).initial(choice.schedule_id)
        assert recovered.status == "historical_absent"
        assert recovered.occurrence_id == choice.occurrence_id
        change_state(review, choice.schedule_id, 3, ScheduleState.PAUSED, "pause-again")
        resume = review.preview(
            "resume-again", RelativeStateChange(choice.schedule_id, 4, ScheduleState.ACTIVE)
        )
        assert resume.result.decode()["plan"]["backlog"]["status"] == "historical_absent"
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


def change_state(service, schedule_id, revision, target, prefix):
    preview, change = reviewed(
        service, RelativeStateChange(schedule_id, revision, target), f"{prefix}-preview"
    )
    return preview, service.apply(f"{prefix}-apply", change)


def test_paused_relative_rule_keeps_completion_and_resumes_with_reviewed_backlog(tmp_path):
    store, schedule_id, work_id, _, lifecycle, event, tasks, _ = completed(tmp_path)
    service = RecurrenceReview(
        store,
        store.installation,
        tasks.actor,
        tasks.actor.current,
        lifecycle.clock,
        lifecycle.identifiers,
        lifecycle.planner,
    )
    saved = progress(store, schedule_id)
    pause, paused = change_state(service, schedule_id, 1, ScheduleState.PAUSED, "pause")
    pause_plan = pause.result.decode()["plan"]
    assert pause_plan["snapshot"]["source"]["retained_occurrence"]["occurrence_id"] == work_id
    assert pause_plan["backlog"] == {"status": "paused", "next_slot": None}
    assert paused.result.decode()["schedule_revision"] == 2
    assert lifecycle.consume(schedule_id, event.event_key).status == "paused"
    assert progress(store, schedule_id) == saved

    resume, active = change_state(service, schedule_id, 2, ScheduleState.ACTIVE, "resume")
    backlog = resume.result.decode()["plan"]["backlog"]
    assert backlog["status"] == "ready"
    assert backlog["next_slot"]["nominal"]["local"] == "1970-01-31"
    assert active.result.decode()["backlog"] == backlog
    assert active.result.decode()["schedule_revision"] == 3
    assert progress(store, schedule_id) == saved
    assert service.original(ReviewAction.APPLY, "resume-apply") == active
    generated = lifecycle.consume(schedule_id, event.event_key)
    assert generated.status == "generated"
    with store.read() as unit:
        rule = unit.recurrence.relative_schedule("home", schedule_id)
        assert rule.pattern_revision == 1 and rule.state is ScheduleState.ACTIVE
        assert len(unit.tasks.occurrences("home")) == 2
        assert unit.tasks.occurrence("home", work_id).state is OccurrenceState.COMPLETED


@pytest.mark.parametrize(
    "fact,status",
    [
        ("empty", "initial"),
        ("manual", "initial_review_required"),
        ("work", "waiting_work"),
        ("original", "original_pending"),
    ],
)
def test_resume_describes_current_initial_obligation(tmp_path, fact, status):
    initial, store, actor, ids, schedule_id, tasks = configured(tmp_path)
    review = review_service(initial, store, actor, ids)
    if fact == "manual":
        with store.read() as unit:
            definition_id = unit.recurrence.relative_schedule("home", schedule_id).definition_id
        tasks.create_occurrence("manual", CreateTaskOccurrence(definition_id))
    if fact in ("work", "original"):
        initial.initial(schedule_id)
        if fact == "original":
            reset_progress(store, schedule_id)
    change_state(review, schedule_id, 1, ScheduleState.PAUSED, "pause")
    selection = RelativeStateChange(schedule_id, 2, ScheduleState.ACTIVE)
    preview = review.preview("resume", selection)
    backlog = preview.result.decode()["plan"]["backlog"]
    assert backlog["status"] == status
    assert (backlog["next_slot"] is not None) == (fact == "empty")
    assert review.preview("resume", selection) == preview


@pytest.mark.parametrize(
    "reason", ["wrong_revision", "same_state", "retired", "inactive_definition"]
)
def test_relative_state_review_rejects_invalid_transitions(tmp_path, reason):
    initial, store, actor, ids, schedule_id, _ = configured(tmp_path)
    review = review_service(initial, store, actor, ids)
    with pytest.raises(InvalidInput, match="invalid_recurrence_state_change"):
        RelativeStateChange(schedule_id, 1, ScheduleState.RETIRED)
    revision = 1
    target = ScheduleState.PAUSED
    if reason == "wrong_revision":
        revision = 2
    elif reason == "same_state":
        target = ScheduleState.ACTIVE
    else:
        with store.write() as unit:
            rule = unit.recurrence.relative_schedule("home", schedule_id)
            unit.recurrence.save_relative_schedule(
                replace(
                    rule,
                    state=ScheduleState.RETIRED if reason == "retired" else ScheduleState.PAUSED,
                    revision=2,
                ),
                1,
            )
            if reason == "inactive_definition":
                definition = unit.tasks.definition("home", rule.definition_id)
                unit.tasks.save_definition(
                    replace(definition, state=DefinitionState.ARCHIVED, revision=2), 1
                )
        revision, target = 2, ScheduleState.ACTIVE
    before = counts(store)
    with pytest.raises(Conflict, match="recurrence_(review_stale|state_change_unavailable)"):
        review.preview("state", RelativeStateChange(schedule_id, revision, target))
    assert counts(store) == before


def test_resume_is_stale_when_manual_work_appears_between_preview_and_apply(tmp_path):
    initial, store, actor, ids, schedule_id, tasks = configured(tmp_path)
    review = review_service(initial, store, actor, ids)
    change_state(review, schedule_id, 1, ScheduleState.PAUSED, "pause")
    _, request = reviewed(review, RelativeStateChange(schedule_id, 2, ScheduleState.ACTIVE))
    with store.read() as unit:
        definition_id = unit.recurrence.relative_schedule("home", schedule_id).definition_id
    tasks.create_occurrence("manual", CreateTaskOccurrence(definition_id))
    before = counts(store)
    with pytest.raises(Conflict, match="recurrence_review_stale"):
        review.apply("resume", request)
    assert counts(store) == before and initial.initial(schedule_id).status == "paused"


def test_state_review_revalidates_after_provider_preparation_and_before_preview_receipt(
    tmp_path, monkeypatch
):
    store, schedule_id, _, _, lifecycle, event, tasks, _ = completed(tmp_path)
    review = RecurrenceReview(
        store,
        store.installation,
        tasks.actor,
        tasks.actor.current,
        lifecycle.clock,
        lifecycle.identifiers,
        lifecycle.planner,
    )
    change_state(review, schedule_id, 1, ScheduleState.PAUSED, "pause")
    plan = RelativeRecurrencePlanner.plan

    def race(planner, rule, cycle):
        tasks.reopen(
            "reopen", ReopenTask(event.cycle.occurrence_id, 2, event.cycle.cycle_id, "Another pass")
        )
        return plan(planner, rule, cycle)

    with monkeypatch.context() as patch:
        patch.setattr(RelativeRecurrencePlanner, "plan", race)
        with pytest.raises(Conflict, match="recurrence_review_stale"):
            review.preview("resume", RelativeStateChange(schedule_id, 2, ScheduleState.ACTIVE))
    with pytest.raises(NotFound):
        review.original(ReviewAction.PREVIEW, "resume")


def test_resume_defers_pending_verification_and_refuses_missing_current_cycle(
    tmp_path, monkeypatch
):
    store, schedule_id, _, _, lifecycle, _, tasks, _ = completed(
        tmp_path, visibility=SuccessorVisibility.AT_VERIFICATION
    )
    review = RecurrenceReview(
        store,
        store.installation,
        tasks.actor,
        tasks.actor.current,
        lifecycle.clock,
        lifecycle.identifiers,
        lifecycle.planner,
    )
    change_state(review, schedule_id, 1, ScheduleState.PAUSED, "pause")
    selection = RelativeStateChange(schedule_id, 2, ScheduleState.ACTIVE)
    with monkeypatch.context() as patch:
        patch.setattr(SQLiteTasks, "cycle", lambda *_: None)
        with pytest.raises(StorageFailure, match="invalid_recurrence_source"):
            review.preview("resume", selection)
    preview = review.preview("resume", selection)
    assert preview.result.decode()["plan"]["backlog"] == {
        "status": "waiting_verification",
        "next_slot": None,
    }


def test_resume_reports_closed_source_without_projecting_another_successor(tmp_path):
    store, schedule_id, work_id, source, lifecycle, event, tasks, _ = completed(tmp_path)
    review = RecurrenceReview(
        store,
        store.installation,
        tasks.actor,
        tasks.actor.current,
        lifecycle.clock,
        lifecycle.identifiers,
        lifecycle.planner,
    )
    change_state(review, schedule_id, 1, ScheduleState.PAUSED, "pause")
    tasks.verify(
        "reject",
        VerifyTask(work_id, 2, event.cycle.cycle_id, VerificationState.REJECTED, "Incomplete"),
    )
    (terminal,) = source.ingest().items
    assert lifecycle.consume(schedule_id, terminal.event.event_key).status == "rejected"
    resume = review.preview("resume", RelativeStateChange(schedule_id, 2, ScheduleState.ACTIVE))
    assert resume.result.decode()["plan"]["backlog"] == {
        "status": "source_closed",
        "next_slot": None,
    }


@pytest.mark.parametrize("corrupt", [None, {"malformed": True}])
def test_apply_rejects_a_plan_that_disagrees_with_its_original_fingerprint(
    tmp_path, monkeypatch, corrupt
):
    review, _, _, choice = manual_fixture(tmp_path)
    _, request = reviewed(review, choice)
    get = SQLiteReceipts.get

    def tamper(self, command):
        receipt = get(self, command)
        if receipt is not None and command.action == ReviewAction.PREVIEW:
            result = JsonDocument.from_value(receipt.result.decode() | {"plan": corrupt})
            return replace(receipt, result=result)
        return receipt

    monkeypatch.setattr(SQLiteReceipts, "get", tamper)
    with pytest.raises(Conflict, match="recurrence_review_stale"):
        review.apply("apply", request)
    assert progress(review.transactions, choice.schedule_id).pristine


def fixed_skip_fixture(tmp_path, *, timed=False):
    from datetime import UTC, datetime

    from test_fixed_materialization import configured as fixed

    from domus.application.fixed_skip_review import FixedSkip

    service, store, actor, ids, rule_id, before = fixed(tmp_path, timed=timed, count=2)
    result = service.step(rule_id, before)
    planner = RelativeRecurrencePlanner(service.planner.times)
    now = int(datetime(2026, 3, 31, tzinfo=UTC).timestamp() * 1000)
    clock = type("Clock", (), {"now": lambda _: now})()
    review = RecurrenceReview(store, store.installation, actor, actor.current, clock, ids, planner)
    selection = FixedSkip(
        rule_id, 1, result.receipt.command.key, result.occurrence_id, 1, "Vacation"
    )
    return review, selection, service, before


@pytest.mark.parametrize("timed", [False, True])
def test_fixed_overdue_skip_keeps_slot_and_task_history_without_affecting_later_work(
    tmp_path, timed
):
    review, choice, service, before = fixed_skip_fixture(tmp_path, timed=timed)
    store = review.transactions
    with store.read() as unit:
        original = unit.recurrence.slot("home", choice.slot_key)
        progress = unit.recurrence.progress("home", choice.schedule_id)
    preview, command = reviewed(review, choice)
    plan = preview.result.decode()["plan"]
    assert plan["exception"] == "overdue_skip"
    assert plan["snapshot"]["source"]["nominal"] == original.planned.value()
    first = review.apply("skip", command)
    restarted = replace(review, transactions=SQLiteDatabase(store.path, store.installation))
    assert restarted.original(ReviewAction.APPLY, "skip") == first
    assert restarted.apply("skip", command) == first
    with store.read() as unit:
        (history,) = unit.tasks.history("home", choice.occurrence_id)
        assert (
            history.evidence.receipt.operation_id
            == first.result.decode()["transition_operation_id"]
        )
        assert history.evidence.receipt.command.actor_id == review.actor.human.ha_user_id
        assert unit.recurrence.slot("home", choice.slot_key) == original
        assert unit.recurrence.progress("home", choice.schedule_id) == progress
        assert unit.tasks.cycles("home") == ()
        work = unit.tasks.occurrence("home", choice.occurrence_id)
        assert work.state is OccurrenceState.SKIPPED and work.state_reason == choice.reason
    later = service.step(choice.schedule_id, before)
    assert later.status == "created" and later.occurrence_id != choice.occurrence_id
    assert review.preview("preview", choice) == preview


@pytest.mark.parametrize("timed", [False, True])
def test_due_slot_must_be_overdue_before_it_can_be_reviewed(tmp_path, timed):
    from test_household_commands import Clock

    review, choice, _, _ = fixed_skip_fixture(tmp_path, timed=timed)
    with pytest.raises(Conflict, match="recurrence_slot_not_overdue"):
        replace(review, clock=Clock()).preview("early", choice)
    with pytest.raises(InvalidInput):
        replace(choice, reason="")


@pytest.mark.parametrize(
    "change", ["missing", "rule_revision", "occurrence", "slot", "started", "retired"]
)
def test_fixed_skip_rechecks_exact_current_rule_slot_work_and_history(tmp_path, change):
    review, choice, service, _ = fixed_skip_fixture(tmp_path)
    store = review.transactions
    tasks = TaskCommands(store, review.actor, service.clock, service.identifiers)
    _, command = reviewed(review, choice)
    if change == "missing":
        with pytest.raises(NotFound):
            review.preview("missing", replace(choice, schedule_id="missing"))
        return
    if change == "occurrence":
        with pytest.raises(Conflict, match="recurrence_review_stale"):
            review.preview("missing", replace(choice, occurrence_id="missing"))
        return
    if change == "slot":
        with pytest.raises(Conflict, match="recurrence_review_stale"):
            review.preview("missing", replace(choice, slot_key="missing"))
        return
    if change == "started":
        tasks.assign("assign", AssignTask(choice.occurrence_id, 1, ("child",)))
        tasks.transition(
            "start", TransitionTask(choice.occurrence_id, 2, OccurrenceState.IN_PROGRESS)
        )
    else:
        with store.write() as unit:
            rule = unit.recurrence.schedule("home", choice.schedule_id)
            state = ScheduleState.RETIRED if change == "retired" else ScheduleState.PAUSED
            unit.recurrence.save_schedule(replace(rule, revision=2, state=state), 1)
    before = counts(store)
    with pytest.raises(Conflict, match="recurrence_review_stale"):
        review.apply("apply", command)
    if change == "retired":
        with pytest.raises(Conflict, match="recurrence_skip_incompatible"):
            review.preview("fresh", replace(choice, schedule_revision=2))
    if change == "started":
        with pytest.raises(Conflict, match="recurrence_skip_incompatible"):
            review.preview("fresh", replace(choice, occurrence_revision=3))
    assert counts(store) == before


def test_fixed_skip_refuses_contradictory_provider_fact(tmp_path, monkeypatch):
    review, choice, _, _ = fixed_skip_fixture(tmp_path)
    monkeypatch.setattr(type(review.planner.times), "local_at", lambda *_: None)
    with pytest.raises(IntegrationUnavailable, match="recurrence_time_source_invalid"):
        review.preview("skip", choice)


def test_fixed_skip_rolls_back_task_transition_if_review_receipt_fails(tmp_path, monkeypatch):
    review, choice, _, _ = fixed_skip_fixture(tmp_path)
    _, change = reviewed(review, choice)
    store = review.transactions
    before = counts(store)
    original = SQLiteReceipts.add

    def fail(self, receipt):
        original(self, receipt)
        if receipt.command.action == ReviewAction.APPLY:
            raise StorageFailure("review_receipt_failure")

    with monkeypatch.context() as patch:
        patch.setattr(SQLiteReceipts, "add", fail)
        with pytest.raises(StorageFailure, match="review_receipt_failure"):
            review.apply("skip", change)
    assert counts(store) == before
    with store.read() as unit:
        assert (
            unit.tasks.occurrence("home", choice.occurrence_id).state is OccurrenceState.AVAILABLE
        )
        assert unit.tasks.history("home", choice.occurrence_id) == ()
    assert review.apply("skip", change).result.decode()["work"]["state"] == "skipped"


def attachment_fixture(tmp_path, *, timed=False, retain=False):
    from test_relative_recurrence_creation import request as relative_request
    from test_task_commands import fixture

    from domus.application.relative_attachment_review import AttachmentChoice, AttachRelative
    from domus.application.task_requests import CreateTask
    from domus.domain.task_values import TaskContent
    from domus.infrastructure.recurrence_time import PinnedRecurrenceTime

    tasks, store, actor, ids = fixture(tmp_path)
    times = PinnedRecurrenceTime()
    original = relative_request(timed=timed)
    definition = tasks.create(
        "manual-definition", CreateTask(TaskContent("Existing task"))
    ).result.decode()
    due_at = times.resolve(original.initial, original.policy).instant_ms if timed else None
    if timed:
        if retain:
            due_at -= 86_400_000
        work = tasks.create_occurrence(
            "manual-due",
            CreateTaskOccurrence(
                definition["definition_id"], assignee_ids=("child",), due_at=due_at
            ),
        ).result.decode()["occurrence_id"]
        tasks.transition(
            "close-placeholder",
            TransitionTask(
                definition["occurrence_id"], 1, OccurrenceState.CANCELLED, "Use dated work"
            ),
        )
    else:
        work = definition["occurrence_id"]
    selection = AttachRelative(
        definition["definition_id"],
        1,
        work,
        1,
        original.initial,
        original.interval,
        original.policy.zone,
        original.policy.repeated_time,
        original.visibility,
        AttachmentChoice.RETAIN if retain else AttachmentChoice.ADOPT,
    )
    service = RecurrenceReview(
        store,
        store.installation,
        actor,
        actor.current,
        tasks.clock,
        ids,
        RelativeRecurrencePlanner(times),
    )
    return service, tasks, selection


@pytest.mark.parametrize("timed,retain", [(False, False), (True, False), (True, True)])
def test_attach_unconfigured_definition_preserves_manual_work_and_recovers_original(
    tmp_path, monkeypatch, timed, retain
):
    service, _, choice = attachment_fixture(tmp_path, timed=timed, retain=retain)
    store = service.transactions
    before = counts(store)
    with store.read() as unit:
        manual = unit.tasks.occurrence("home", choice.occurrence_id)
        assert not unit.recurrence.has_current_schedule("home", choice.definition_id)
        assert not unit.recurrence.occurrence_is_scheduled("home", choice.occurrence_id)
    preview, request = reviewed(service, choice)
    assert preview.result.decode()["plan"]["source"]["creates_first_occurrence"] is retain
    applied = service.apply("attach", request)
    facts = applied.result.decode()
    rule_id, first = facts["schedule_id"], facts["first_occurrence_id"]
    assert facts["manual_occurrence_id"] == choice.occurrence_id
    assert (first != choice.occurrence_id) is retain
    assert counts(store)[:2] == (before[0], before[1] + int(retain))
    with store.read() as unit:
        rule = unit.recurrence.relative_schedule("home", rule_id)
        (slot,) = unit.recurrence.relative_slots("home", rule_id)
        assert slot.occurrence_id == first and unit.recurrence.occurrence_is_scheduled(
            "home", first
        )
        assert unit.recurrence.relative_progress("home", rule_id).current_occurrence_id == first
        assert unit.tasks.occurrence("home", choice.occurrence_id) == manual
        assert rule.definition_id == choice.definition_id
        assert unit.receipts.get(slot.command).operation_id == facts["materialization_operation_id"]
    with pytest.raises(Conflict, match="recurrence_attachment_already_scheduled"):
        service.preview("another", choice)

    def unavailable(*_):
        raise AssertionError("Replaying the original must precede timezone lookup")

    monkeypatch.setattr(type(service.planner.times), "require_policy", unavailable)
    restarted = replace(service, transactions=SQLiteDatabase(store.path, store.installation))
    assert restarted.preview("preview", choice) == preview
    assert restarted.apply("attach", request) == applied
    assert restarted.original(ReviewAction.APPLY, "attach") == applied


def test_attachment_rejects_changed_work_and_rolls_back_new_rule_and_mapping(tmp_path, monkeypatch):
    service, tasks, choice = attachment_fixture(tmp_path)
    _, stale = reviewed(service, choice)
    tasks.assign("assign", AssignTask(choice.occurrence_id, 1, ("child",)))
    with pytest.raises(Conflict, match="recurrence_review_stale"):
        service.apply("stale", stale)
    _, request = reviewed(service, replace(choice, occurrence_revision=2), "fresh")
    before = counts(service.transactions)
    append = SQLiteOutbox.append

    def fail(self, event):
        append(self, event)
        if event.event_type == ReviewAction.APPLY:
            raise StorageFailure("attachment_rollback")

    with monkeypatch.context() as patch:
        patch.setattr(SQLiteOutbox, "append", fail)
        with pytest.raises(StorageFailure, match="attachment_rollback"):
            service.apply("attach", request)
    assert counts(service.transactions) == before
    with service.transactions.read() as unit:
        assert not unit.recurrence.has_current_schedule("home", choice.definition_id)
        assert not unit.recurrence.occurrence_is_scheduled("home", choice.occurrence_id)
    assert (
        service.apply("attach", request).result.decode()["first_occurrence_id"]
        == choice.occurrence_id
    )


def test_retain_manual_rejects_overlap_and_changes_to_other_reviewed_work(tmp_path):
    service, tasks, choice = attachment_fixture(tmp_path, timed=True, retain=True)
    _, request = reviewed(service, choice)
    work = tasks.create_occurrence(
        "added", CreateTaskOccurrence(choice.definition_id, due_at=1000)
    ).result.decode()
    assert work["occurrence_id"] != choice.occurrence_id
    with pytest.raises(Conflict, match="recurrence_review_stale"):
        service.apply("attach", request)
    tasks.create_occurrence("undated", CreateTaskOccurrence(choice.definition_id))
    with pytest.raises(Conflict, match="recurrence_attachment_overlap"):
        service.preview("refresh", choice)


def test_attachment_rejects_retired_owned_occurrence_and_oversized_manual_plan(
    tmp_path, monkeypatch
):
    from domus.application.relative_attachment_review import AttachmentChoice

    service, _, choice = attachment_fixture(tmp_path)
    _, request = reviewed(service, choice)
    facts = service.apply("attach", request).result.decode()
    store = service.transactions
    with store.write() as unit:
        rule = unit.recurrence.relative_schedule("home", facts["schedule_id"])
        unit.recurrence.save_relative_schedule(
            replace(rule, revision=2, state=ScheduleState.RETIRED), 1
        )
    with pytest.raises(Conflict, match="recurrence_attachment_incompatible"):
        service.preview("reattach", choice)

    (tmp_path / "other").mkdir()
    service, _, choice = attachment_fixture(tmp_path / "other")
    with service.transactions.read() as unit:
        work = unit.tasks.occurrence("home", choice.occurrence_id)
    monkeypatch.setattr(SQLiteTasks, "occurrences", lambda *a, **kw: (work,) * 101)
    with pytest.raises(Conflict, match="recurrence_review_too_large"):
        service.preview("oversized", replace(choice, choice=AttachmentChoice.RETAIN))


def test_original_attachment_after_restore_does_not_recreate_rule_or_work(tmp_path):
    root, archive, target = (tmp_path / part for part in ("root", "archive", "target"))
    root.mkdir(mode=0o700)
    service, _, choice = attachment_fixture(root)
    store = service.transactions
    identity_at(root, store.installation)
    checkpoint = SQLiteSnapshots(store, archive, store.installation, Clock()).create(
        "before-attachment"
    )
    _, request = reviewed(service, choice)
    applied = service.apply("attach", request)
    SQLiteRestorations(store, archive, target, store.installation, Clock(), checkpoint).prepare(
        "restore"
    )
    assert SQLiteActivation(root, store.installation, Clock(), target).activate().state == "active"
    restored = open_storage(root, "edge")
    try:
        reopened = replace(service, transactions=restored.database)
        original = reopened.original(ReviewAction.APPLY, "attach")
        assert original.historical and original.operation_id == applied.operation_id
        assert reopened.apply("attach", request) == original
        with restored.database.read() as unit:
            assert not unit.recurrence.has_current_schedule("home", choice.definition_id)
            assert not unit.recurrence.occurrence_is_scheduled("home", choice.occurrence_id)
            assert len(unit.tasks.occurrences("home")) == 1
    finally:
        restored.close()


def test_unconfigured_adoption_rejects_incompatible_choice(tmp_path):
    service, tasks, choice = attachment_fixture(tmp_path)
    with pytest.raises(InvalidInput, match="invalid_recurrence_attachment"):
        replace(choice, choice="adopt")
    tasks.assign("assign", AssignTask(choice.occurrence_id, 1, ("child",)))
    tasks.transition("start", TransitionTask(choice.occurrence_id, 2, OccurrenceState.IN_PROGRESS))
    with pytest.raises(Conflict, match="recurrence_adoption_incompatible"):
        service.preview("started", replace(choice, occurrence_revision=3))


def test_competing_new_attachments_share_exact_original_or_reject_second_rule(tmp_path):
    service, _, choice = attachment_fixture(tmp_path)
    _, request = reviewed(service, choice)
    store = service.transactions
    barrier = Barrier(3)

    def apply(key):
        client = replace(
            service,
            transactions=SQLiteDatabase(store.path, store.installation, busy_timeout=5),
            identifiers=SecureIdentifiers(),
        )
        barrier.wait(timeout=5)
        try:
            return client.apply(key, request)
        except Conflict as error:
            return error

    with ThreadPoolExecutor(max_workers=3) as pool:
        same, retry, another = tuple(pool.map(apply, ("same", "same", "another")))
    if isinstance(another, Conflict):
        assert str(another) == "recurrence_attachment_already_scheduled"
        assert not isinstance(same, Conflict) and same == retry
    else:
        assert all(
            str(error) == "recurrence_attachment_already_scheduled" for error in (same, retry)
        )
    with store.read() as unit:
        assert len(unit.recurrence.relative_schedules("home")) == 1
        assert len(unit.tasks.occurrences("home")) == 1


def test_reviewed_relative_settings_rebind_original_progress_and_generate_at_new_interval(tmp_path):
    from domus.application.recurrence_sources import RecurrenceSourceObservations
    from domus.application.relative_lifecycle import RelativeLifecycle
    from domus.application.relative_state_review import RelativeSettings
    from domus.application.task_requests import CompleteTask
    from domus.domain.recurrence_time import RelativeInterval

    initial, store, actor, ids, schedule_id, tasks = configured(tmp_path)
    bootstrap = initial.initial(schedule_id)
    service = review_service(initial, store, actor, ids)
    choice = RelativeSettings(
        schedule_id, 1, RelativeInterval(45), SuccessorVisibility.AT_COMPLETION
    )
    preview, request = reviewed(service, choice)
    old = progress(store, schedule_id)
    result = service.apply("settings", request)
    assert service.apply("settings", request) == result
    assert preview.result.decode()["plan"]["source"]["previous_interval_days"] == 30
    with store.read() as unit:
        rule = unit.recurrence.relative_schedule("home", schedule_id)
        assert rule.pattern_revision == rule.revision == 2
        assert rule.interval.days == 45
        saved = unit.recurrence.relative_progress("home", schedule_id)
        assert saved.current_occurrence_id == bootstrap.occurrence_id
        assert saved.current_slot_key == old.current_slot_key
        assert saved.matches_schedule(rule) and saved.matches_receipt(result)
        member = unit.members.by_user("home", actor.human.ha_user_id)
    tasks.complete("complete", CompleteTask(bootstrap.occurrence_id, 1, (member.member_id,), 90))
    observations = RecurrenceSourceObservations(store, initial.scope)
    (item,) = observations.ingest().items
    lifecycle = RelativeLifecycle(store, initial.scope, service.planner, initial.clock, ids)
    generated = lifecycle.consume(schedule_id, item.event.event_key)
    assert generated.status == "generated"
    with store.read() as unit:
        slot = unit.recurrence.relative_slot_for_occurrence("home", generated.occurrence_id)
        assert slot.planned.value()["nominal"]["local"] == "1970-02-15"
        assert (
            unit.tasks.occurrence("home", bootstrap.occurrence_id).state
            is OccurrenceState.COMPLETED
        )


def test_settings_changes_on_pristine_rule_rollback_with_receipt_and_remain_pristine(
    tmp_path, monkeypatch
):
    from domus.application.relative_state_review import RelativeSettings
    from domus.domain.recurrence_time import RelativeInterval
    from domus.infrastructure.sqlite_relative_recurrence import SQLiteRelativeRecurrences

    initial, store, actor, ids, schedule_id, _ = configured(tmp_path)
    service = review_service(initial, store, actor, ids)
    choice = RelativeSettings(
        schedule_id, 1, RelativeInterval(30), SuccessorVisibility.AT_VERIFICATION
    )
    with pytest.raises(InvalidInput):
        replace(choice, visibility="invalid")
    with pytest.raises(Conflict, match="recurrence_review_stale"):
        service.preview("stale", replace(choice, schedule_revision=2))
    with pytest.raises(Conflict, match="recurrence_state_change_unavailable"):
        service.preview("same", replace(choice, visibility=SuccessorVisibility.AT_COMPLETION))
    _, request = reviewed(service, choice)
    save = SQLiteRelativeRecurrences.save_relative_progress

    def fail(self, *args):
        save(self, *args)
        raise StorageFailure("settings_rollback")

    before = counts(store)
    with monkeypatch.context() as patch:
        patch.setattr(SQLiteRelativeRecurrences, "save_relative_progress", fail)
        with pytest.raises(StorageFailure, match="settings_rollback"):
            service.apply("settings", request)
    with store.read() as unit:
        assert unit.recurrence.relative_schedule("home", schedule_id).revision == 1
    assert counts(store) == before
    assert service.apply("settings", request)
    assert progress(store, schedule_id).pristine
    assert initial.initial(schedule_id).status == "created"


def test_settings_never_reinterpret_pending_completion_or_overwrite_changed_work(tmp_path):
    from domus.application.relative_state_review import RelativeSettings
    from domus.domain.recurrence_time import RelativeInterval

    pending = tmp_path / "pending"
    pending.mkdir()
    store, schedule_id, _, _, lifecycle, _, tasks, _ = completed(pending)
    service = RecurrenceReview(
        store,
        store.installation,
        tasks.actor,
        tasks.actor.current,
        lifecycle.clock,
        lifecycle.identifiers,
        lifecycle.planner,
    )
    choice = RelativeSettings(
        schedule_id, 1, RelativeInterval(45), SuccessorVisibility.AT_VERIFICATION
    )
    with pytest.raises(Conflict, match="recurrence_review_source_pending"):
        service.preview("pending", choice)

    initial, store, actor, ids, schedule_id, tasks = configured(tmp_path)
    first = initial.initial(schedule_id)
    service = review_service(initial, store, actor, ids)
    choice = replace(choice, schedule_id=schedule_id)
    _, request = reviewed(service, choice)
    tasks.assign("changed", AssignTask(first.occurrence_id, 1, ("child",)))
    with pytest.raises(Conflict, match="recurrence_review_stale"):
        service.apply("apply", request)
