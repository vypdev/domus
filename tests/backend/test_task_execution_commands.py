"""Execution facts, current grants and cycle transitions commit on actual SQLite files."""

from dataclasses import replace

import pytest
from test_task_commands import child_commands, fixture, resource

from domus.application.task_commands import (
    AssignTask,
    CompleteTask,
    CreateTask,
    ReopenTask,
    TransitionTask,
    VerifyTask,
)
from domus.domain.errors import Conflict, Forbidden, InvalidInput, StorageFailure
from domus.domain.identity import MemberStatus, Permission, PermissionRule, Role
from domus.domain.task_values import (
    DependencyGate,
    OccurrenceState,
    TaskContent,
    TaskOverrides,
    VerificationMode,
    VerificationState,
)
from domus.infrastructure.sqlite_tasks import SQLiteTasks


def work_at(store, occurrence_id):
    with store.read() as unit:
        work = unit.tasks.occurrence("home", occurrence_id)
        cycle = (
            None
            if work.current_cycle_id is None
            else unit.tasks.cycle("home", work.current_cycle_id)
        )
        return work, cycle


def state(store, occurrence_id):
    with store.read() as unit:
        return (
            unit.tasks.occurrence("home", occurrence_id),
            unit.tasks.cycles("home", occurrence_id),
            unit.audit.entries("home"),
            unit.outbox.pending(),
        )


def prepared(tmp_path, overrides=None, assign=True):
    commands, store, actor, identifiers = fixture(tmp_path)
    created = commands.create(
        "create",
        CreateTask(
            TaskContent("Work"), overrides=TaskOverrides() if overrides is None else overrides
        ),
    )
    occurrence_id = resource(created)[1]
    with store.read() as unit:
        administrator = unit.members.by_user("home", actor.human.ha_user_id).member_id
    if assign:
        commands.assign("assign", AssignTask(occurrence_id, 1, ("child",)))
    child, _ = child_commands(store, identifiers=identifiers)
    return commands, child, store, occurrence_id, administrator, identifiers


def perform(service, store, occurrence_id, performers, key="complete"):
    work, _ = work_at(store, occurrence_id)
    return service.complete(key, CompleteTask(occurrence_id, work.revision, performers, 90))


def test_adult_performance_needs_no_approval_and_replay_does_not_create_another_cycle(tmp_path):
    commands, _, store, occurrence_id, admin, identifiers = prepared(tmp_path, assign=False)
    request = CompleteTask(occurrence_id, 1, (admin,), 90)
    result = commands.complete("complete", request)
    count = identifiers.count
    assert commands.complete("complete", request) == result and identifiers.count == count
    work, cycle = work_at(store, occurrence_id)
    assert work.state is OccurrenceState.COMPLETED and cycle.verification is VerificationState.NONE
    assert cycle.recorded_by == admin and cycle.performers[0].role is Role.ADMINISTRATOR
    assert cycle.performed_at == 90 and cycle.recorded_at == 100 and cycle.closed_at is None
    assert (
        cycle.definition_revision,
        cycle.task_policy_revision,
        cycle.identity_policy_revision,
    ) == (1, 1, 1)
    assert result.result.decode()["consumer_delivery"] == "unconfirmed"
    with store.read() as unit:
        event = unit.outbox.pending()[-1]
        assert (
            event.event_id == result.operation_id
            and event.payload.decode()["kind"] == "task.completed"
        )
        assert event.payload.decode()["cycle"]["cycle_id"] == cycle.cycle_id
        assert len(unit.tasks.cycles("home", occurrence_id)) == 1
    with pytest.raises(Conflict):
        commands.complete("duplicate", CompleteTask(occurrence_id, work.revision, (admin,), 90))


def test_actual_restricted_performer_stays_pending_when_an_adult_records_on_behalf(tmp_path):
    commands, _, store, occurrence_id, admin, _ = prepared(tmp_path)
    result = perform(commands, store, occurrence_id, ("child",))
    _, cycle = work_at(store, occurrence_id)
    assert cycle.verification is VerificationState.PENDING
    assert cycle.recorded_by == admin and cycle.performers[0].member_id == "child"
    assert cycle.performers[0].role is Role.RESTRICTED
    with store.write() as unit:
        person = unit.members.get("home", "child")
        unit.members.save(replace(person, status=MemberStatus.ARCHIVED, revision=2), 1)
    # Participant eligibility is a new-performance precondition, not a reason to replay an effect.
    assert commands.complete("complete", CompleteTask(occurrence_id, 2, ("child",), 90)) == result
    with store.write() as unit:
        person = unit.members.get("home", admin)
        unit.members.save(
            replace(
                person,
                exceptions=(PermissionRule(Permission.TASKS_RECORD_FOR_OTHERS, False),),
                revision=2,
            ),
            1,
        )
    with pytest.raises(Forbidden):
        commands.complete("complete", CompleteTask(occurrence_id, 2, ("child",), 90))


def test_restricted_performance_approval_records_decision_without_closing_and_replays(tmp_path):
    commands, child, store, occurrence_id, _, _ = prepared(tmp_path)
    perform(child, store, occurrence_id, ("child",))
    work, cycle = work_at(store, occurrence_id)
    request = VerifyTask(occurrence_id, work.revision, cycle.cycle_id, VerificationState.APPROVED)
    result = commands.verify("approve", request)
    assert commands.verify("approve", request) == result
    approved, verified = work_at(store, occurrence_id)
    assert approved.revision == work.revision + 1 and approved.current_cycle_revision == 2
    assert verified.verification is VerificationState.APPROVED and verified.closed_at is None
    assert verified.verified_at == 100 and verified.verified_by.role is Role.ADMINISTRATOR
    with pytest.raises(Conflict):
        commands.verify(
            "again",
            VerifyTask(
                occurrence_id, approved.revision, cycle.cycle_id, VerificationState.APPROVED
            ),
        )
    with pytest.raises(Forbidden):
        child.verify("approve", request)


@pytest.mark.parametrize("independent", [False, True])
def test_adult_participant_approval_uses_saved_rule_and_another_adult_can_approve(
    tmp_path, independent
):
    commands, _, store, occurrence_id, admin, ids = prepared(
        tmp_path,
        TaskOverrides(
            verification=VerificationMode.ADULT, adult_performer_may_approve=not independent
        ),
        assign=False,
    )
    perform(commands, store, occurrence_id, (admin,))
    work, cycle = work_at(store, occurrence_id)
    request = VerifyTask(occurrence_id, work.revision, cycle.cycle_id, VerificationState.APPROVED)
    if independent:
        with pytest.raises(Forbidden, match="task_approval_denied"):
            commands.verify("self", request)
        with store.write() as unit:
            person = unit.members.get("home", "other")
            unit.members.save(replace(person, role=Role.ADULT, revision=2), 1)
        other, _ = child_commands(store, "other", ids)
        other.verify("adult", request)
    else:
        commands.verify("self", request)
    assert work_at(store, occurrence_id)[1].verification is VerificationState.APPROVED


def test_rejection_retains_performed_facts_and_reopen_compensates_once_before_new_cycle(tmp_path):
    commands, child, store, occurrence_id, _, _ = prepared(tmp_path)
    perform(child, store, occurrence_id, ("child",))
    work, first = work_at(store, occurrence_id)
    commands.verify(
        "reject",
        VerifyTask(
            occurrence_id,
            work.revision,
            first.cycle_id,
            VerificationState.REJECTED,
            "Needs another pass",
        ),
    )
    work, rejected = work_at(store, occurrence_id)
    assert (
        work.state is OccurrenceState.COMPLETED
        and rejected.verification_reason == "Needs another pass"
    )
    request = ReopenTask(occurrence_id, work.revision, first.cycle_id, "Do the work again")
    receipt = commands.reopen("reopen", request)
    assert commands.reopen("reopen", request) == receipt
    reopened, _ = work_at(store, occurrence_id)
    assert reopened.state is OccurrenceState.ASSIGNED and reopened.current_cycle_id is None
    with store.read() as unit:
        closed = unit.tasks.cycle("home", first.cycle_id)
        assert closed.closed_at == 100 and closed.performed_at == first.performed_at
        assert closed.verification is VerificationState.REJECTED
        event = unit.outbox.pending()[-1].payload.decode()
        assert event["kind"] == "task.reopened" and event["compensates_cycle_id"] == first.cycle_id
    perform(child, store, occurrence_id, ("child",), "genuine-new-work")
    current, second = work_at(store, occurrence_id)
    assert second.cycle_id != first.cycle_id and second.verification is VerificationState.PENDING
    before = state(store, occurrence_id)
    for operation in ("verify", "reopen"):
        request = (
            VerifyTask(occurrence_id, current.revision, first.cycle_id, VerificationState.APPROVED)
            if operation == "verify"
            else ReopenTask(occurrence_id, current.revision, first.cycle_id, "Old cycle")
        )
        with pytest.raises(Conflict, match="task_cycle_conflict"):
            getattr(commands, operation)("stale-" + operation, request)
    assert state(store, occurrence_id) == before


@pytest.mark.parametrize("action", ["complete", "verify", "reopen"])
@pytest.mark.parametrize("stage", ["cycle", "occurrence"])
def test_failure_between_real_cycle_and_occurrence_writes_rolls_back_every_fact(
    tmp_path, monkeypatch, action, stage
):
    commands, child, store, occurrence_id, _, _ = prepared(tmp_path)
    if action != "complete":
        perform(child, store, occurrence_id, ("child",))
    work, cycle = work_at(store, occurrence_id)
    request = (
        CompleteTask(occurrence_id, work.revision, ("child",), 90)
        if action == "complete"
        else VerifyTask(occurrence_id, work.revision, cycle.cycle_id, VerificationState.APPROVED)
        if action == "verify"
        else ReopenTask(occurrence_id, work.revision, cycle.cycle_id, "Retry work")
    )
    before = state(store, occurrence_id)
    original = getattr(SQLiteTasks, "save_" + stage)

    def fail(self, value, expected_revision):
        original(self, value, expected_revision)
        raise StorageFailure("injected_failure")

    monkeypatch.setattr(SQLiteTasks, "save_" + stage, fail)
    service = child if action == "complete" else commands
    with pytest.raises(StorageFailure):
        getattr(service, action)("failed", request)
    assert state(store, occurrence_id) == before


def link(store, occurrence_id, required, subtasks=()):
    # Seed pre-existing references; the public dependency editor remains separate work.
    with store.write() as unit:
        work = unit.tasks.occurrence("home", occurrence_id)
        updated = replace(
            work,
            prerequisite_ids=required,
            required_subtask_ids=subtasks,
            revision=work.revision + 1,
        )
        unit.tasks.save_occurrence(updated, work.revision)


@pytest.mark.parametrize("gate", list(DependencyGate))
def test_pending_prerequisite_obeys_configured_gate_without_releasing_points(tmp_path, gate):
    commands, child, store, prior_id, admin, _ = prepared(tmp_path)
    perform(child, store, prior_id, ("child",))
    later_id = resource(
        commands.create(
            "later", CreateTask(TaskContent("Later"), overrides=TaskOverrides(dependency_gate=gate))
        )
    )[1]
    link(store, later_id, (prior_id,))
    if gate is DependencyGate.APPROVED:
        with pytest.raises(Conflict, match="task_dependencies_incomplete"):
            perform(commands, store, later_id, (admin,), "later-completion")
        work, cycle = work_at(store, prior_id)
        commands.verify(
            "approve-prior",
            VerifyTask(prior_id, work.revision, cycle.cycle_id, VerificationState.APPROVED),
        )
    else:
        assert work_at(store, prior_id)[1].verification is VerificationState.PENDING
    perform(commands, store, later_id, (admin,), "later-completion")
    assert work_at(store, later_id)[0].state is OccurrenceState.COMPLETED


def test_rejected_required_work_and_unfinished_required_subtasks_block_completion(tmp_path):
    commands, child, store, prior_id, admin, _ = prepared(tmp_path)
    perform(child, store, prior_id, ("child",))
    prior, cycle = work_at(store, prior_id)
    commands.verify(
        "reject",
        VerifyTask(
            prior_id, prior.revision, cycle.cycle_id, VerificationState.REJECTED, "Not ready"
        ),
    )
    later_id = resource(commands.create("later", CreateTask(TaskContent("Later"))))[1]
    link(store, later_id, (), (prior_id,))
    with pytest.raises(Conflict, match="task_dependencies_incomplete"):
        perform(commands, store, later_id, (admin,), "later-work")
    commands.reopen(
        "redo", ReopenTask(prior_id, work_at(store, prior_id)[0].revision, cycle.cycle_id, "Repeat")
    )
    with pytest.raises(Conflict, match="task_dependencies_incomplete"):
        perform(commands, store, later_id, (admin,), "later-work")


def test_reopened_prerequisite_keeps_completed_dependent_facts_unchanged(tmp_path):
    commands, _, store, prior_id, admin, _ = prepared(tmp_path, assign=False)
    perform(commands, store, prior_id, (admin,))
    later_id = resource(commands.create("later", CreateTask(TaskContent("Later"))))[1]
    link(store, later_id, (prior_id,))
    perform(commands, store, later_id, (admin,), "later-work")
    later = work_at(store, later_id)
    prior, cycle = work_at(store, prior_id)
    commands.reopen("reopen", ReopenTask(prior_id, prior.revision, cycle.cycle_id, "Check again"))
    assert work_at(store, later_id) == later
    # The source cause is retained; no completed review projection is claimed here.
    with store.read() as unit:
        assert unit.outbox.pending()[-1].payload.decode()["dependency_review_required"] is True


def test_assigned_performer_can_start_block_and_unblock_but_not_cancel_or_complete_by_transition(
    tmp_path,
):
    commands, child, store, occurrence_id, _, _ = prepared(tmp_path)
    for target, reason in [
        (OccurrenceState.IN_PROGRESS, ""),
        (OccurrenceState.BLOCKED, "Waiting"),
        (OccurrenceState.ASSIGNED, "Ready"),
    ]:
        work, _ = work_at(store, occurrence_id)
        request = TransitionTask(occurrence_id, work.revision, target, reason)
        receipt = child.transition(target.value, request)
        assert child.transition(target.value, request) == receipt
        assert work_at(store, occurrence_id)[0].state is target
    work, _ = work_at(store, occurrence_id)
    with pytest.raises(Forbidden):
        child.transition(
            "cancel",
            TransitionTask(
                occurrence_id, work.revision, OccurrenceState.CANCELLED, "No longer needed"
            ),
        )
    with pytest.raises(InvalidInput):
        TransitionTask(occurrence_id, work.revision, OccurrenceState.COMPLETED)
    commands.transition(
        "skip",
        TransitionTask(occurrence_id, work.revision, OccurrenceState.SKIPPED, "Explicit omission"),
    )
    assert work_at(store, occurrence_id)[0].state is OccurrenceState.SKIPPED


@pytest.mark.parametrize(
    "build_request",
    [
        lambda: CompleteTask("occ", 1, (), 90),
        lambda: CompleteTask("occ", 1, ("child", "child"), 90),
        lambda: CompleteTask("occ", 1, ["child"], 90),
        lambda: CompleteTask("occ", 1, ("child",), True),
        lambda: CompleteTask("occ", 1, ("child",), -1),
        lambda: CompleteTask("occ", 1, ("child",), 2**63),
        lambda: VerifyTask("occ", 1, "cycle", "approved"),
        lambda: VerifyTask("occ", 1, "cycle", VerificationState.NONE),
        lambda: VerifyTask("occ", 1, "cycle", VerificationState.PENDING),
        lambda: VerifyTask("occ", 1, "cycle", VerificationState.REJECTED, " "),
        lambda: ReopenTask("occ", 1, "cycle", " "),
        lambda: ReopenTask("occ", 1, "bad id", "Repeat"),
        lambda: TransitionTask("occ", 1, "in_progress"),
        lambda: TransitionTask("occ", 1, OccurrenceState.DRAFT),
        lambda: TransitionTask("occ", 1, OccurrenceState.BLOCKED, " "),
        lambda: TransitionTask("occ", 1, OccurrenceState.CANCELLED, "x" * 1001),
        lambda: TransitionTask("occ", 1, OccurrenceState.SKIPPED, "bad\x00reason"),
    ],
)
def test_execution_requests_reject_malformed_values_before_any_effect(build_request):
    with pytest.raises(InvalidInput):
        build_request()


def test_transition_authority_fails_closed_when_server_target_context_is_missing(tmp_path):
    from domus.application.task_authorization import TaskAccess, TaskCommandAuthorization
    from domus.domain.storage import CommandKey

    commands, _, store, occurrence_id, _, _ = prepared(tmp_path)
    authority = TaskCommandAuthorization(
        TaskAccess(commands.actor.current()), "home", "task.transition", occurrence_id
    )
    with store.read() as unit:
        with pytest.raises(Forbidden):
            authority.require(
                CommandKey("home", "ha_admin", "task.transition", "missing-context"), unit
            )


def test_missing_task_defaults_or_prerequisite_references_cannot_create_a_cycle(tmp_path):
    commands, _, store, occurrence_id, admin, _ = prepared(tmp_path, assign=False)
    link(store, occurrence_id, ("missing-prerequisite",))
    before = state(store, occurrence_id)
    with pytest.raises(StorageFailure, match="invalid_task_references"):
        perform(commands, store, occurrence_id, (admin,))
    assert state(store, occurrence_id) == before
    link(store, occurrence_id, ())
    with store._connection() as connection:
        # Deliberate isolated-file corruption, not a supported application mutation.
        connection.execute("DELETE FROM task_policy")
    before = state(store, occurrence_id)
    with pytest.raises(StorageFailure, match="invalid_task_references"):
        perform(commands, store, occurrence_id, (admin,))
    assert state(store, occurrence_id) == before


@pytest.mark.parametrize("corruption", ["missing", "revision"])
def test_current_cycle_missing_or_with_a_one_sided_revision_fails_before_writes(
    tmp_path, corruption
):
    from domus.infrastructure.sqlite_task_records import cycle_document

    commands, child, store, occurrence_id, _, _ = prepared(tmp_path)
    perform(child, store, occurrence_id, ("child",))
    work, cycle = work_at(store, occurrence_id)
    with store._connection() as connection:
        # Break the reference with foreign keys off to verify the read-time semantic fence.
        if corruption == "missing":
            connection.execute("DELETE FROM task_cycles")
        else:
            changed = replace(cycle, revision=cycle.revision + 1)
            connection.execute(
                "UPDATE task_cycles SET revision=?,document=?",
                (changed.revision, cycle_document(changed).encoded),
            )
    before = state(store, occurrence_id)
    with pytest.raises(StorageFailure, match="invalid_task_references"):
        commands.verify(
            "invalid",
            VerifyTask(occurrence_id, work.revision, cycle.cycle_id, VerificationState.APPROVED),
        )
    assert state(store, occurrence_id) == before


def test_a_foreign_semantic_cycle_response_cannot_become_approval(tmp_path, monkeypatch):
    commands, child, store, occurrence_id, _, _ = prepared(tmp_path)
    perform(child, store, occurrence_id, ("child",))
    work, cycle = work_at(store, occurrence_id)
    before = state(store, occurrence_id)
    # Explicit broken-port fixture; this does not establish SQLite foreign-key behavior.
    monkeypatch.setattr(SQLiteTasks, "cycle", lambda *_: replace(cycle, household_id="other"))
    with pytest.raises(StorageFailure, match="invalid_task_references"):
        commands.verify(
            "foreign",
            VerifyTask(occurrence_id, work.revision, cycle.cycle_id, VerificationState.APPROVED),
        )
    monkeypatch.undo()
    assert state(store, occurrence_id) == before


def test_a_future_performed_time_and_missing_on_behalf_grant_leave_no_performance(tmp_path):
    commands, child, store, occurrence_id, _, _ = prepared(tmp_path)
    before = state(store, occurrence_id)
    with pytest.raises(InvalidInput, match="invalid_task_cycle"):
        child.complete("future", CompleteTask(occurrence_id, 2, ("child",), 101))
    with pytest.raises(Forbidden):
        child.complete("on-behalf", CompleteTask(occurrence_id, 2, ("child", "other"), 90))
    with pytest.raises(Forbidden):
        child.complete("omit-self", CompleteTask(occurrence_id, 2, ("other",), 90))
    with pytest.raises(Forbidden):
        child.reopen("not-manager", ReopenTask(occurrence_id, 2, "cycle", "Reopen"))
    assert state(store, occurrence_id) == before


def test_two_concurrent_completions_create_one_cycle_and_preserve_actual_performers(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    commands, child, store, occurrence_id, admin, _ = prepared(tmp_path)
    gate = Barrier(2)

    def complete(service):
        gate.wait(timeout=5)
        try:
            return service.complete("race", CompleteTask(occurrence_id, 2, ("child",), 90))
        except Conflict:
            return None

    before = state(store, occurrence_id)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(complete, (commands, child)))
    assert sum(result is not None for result in results) == 1
    after = state(store, occurrence_id)
    assert (
        len(after[1]) == 1
        and len(after[2]) == len(before[2]) + 1
        and len(after[3]) == len(before[3]) + 1
    )
    assert after[1][0].recorded_by in (admin, "child")
    assert after[1][0].performers[0].member_id == "child"
    assert after[1][0].verification is VerificationState.PENDING


@pytest.mark.parametrize("action", ["complete", "verify", "reopen"])
def test_execution_commands_replay_historical_receipts_after_actual_offline_activation(
    tmp_path, action
):
    from test_activation_compatibility import identity_at
    from test_sqlite_snapshots import Clock

    from domus.application.task_commands import TaskCommands
    from domus.infrastructure.owned_storage import open_storage
    from domus.infrastructure.sqlite_activation import SQLiteActivation
    from domus.infrastructure.sqlite_restoration import SQLiteRestorations
    from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots

    root, archive, target = tmp_path / "source", tmp_path / "archive", tmp_path / "prepared"
    root.mkdir(mode=0o700)
    commands, child, store, occurrence_id, _, ids = prepared(root)
    identity_at(root, store.installation)
    if action != "complete":
        perform(child, store, occurrence_id, ("child",))
    if action == "reopen":
        work, cycle = work_at(store, occurrence_id)
        commands.verify(
            "approval",
            VerifyTask(occurrence_id, work.revision, cycle.cycle_id, VerificationState.APPROVED),
        )
    work, cycle = before = work_at(store, occurrence_id)
    if action == "complete":
        request, service = CompleteTask(occurrence_id, work.revision, ("child",), 90), child
    elif action == "verify":
        request, service = (
            VerifyTask(occurrence_id, work.revision, cycle.cycle_id, VerificationState.APPROVED),
            commands,
        )
    else:
        request, service = (
            ReopenTask(occurrence_id, work.revision, cycle.cycle_id, "Retry"),
            commands,
        )
    checkpoint = SQLiteSnapshots(store, archive, store.installation, Clock()).create(
        "before-execution"
    )
    original = getattr(service, action)(action, request)
    allocated = ids.count
    SQLiteRestorations(store, archive, target, store.installation, Clock(), checkpoint).prepare(
        "restore-execution"
    )
    assert SQLiteActivation(root, store.installation, Clock(), target).activate().state == "active"
    restored = open_storage(root, "edge")
    try:
        replay = TaskCommands(restored.database, service.actor, service.clock, ids)
        result = getattr(replay, action)(action, request)
        assert result.historical and result.operation_id == original.operation_id
        assert result.result == original.result and ids.count == allocated
        assert work_at(restored.database, occurrence_id) == before
    finally:
        restored.close()


def test_revoked_approval_permission_blocks_an_original_result_without_changing_cycle(tmp_path):
    commands, child, store, occurrence_id, admin, _ = prepared(tmp_path)
    perform(child, store, occurrence_id, ("child",))
    work, cycle = work_at(store, occurrence_id)
    request = VerifyTask(occurrence_id, work.revision, cycle.cycle_id, VerificationState.APPROVED)
    commands.verify("approve", request)
    with store.write() as unit:
        person = unit.members.get("home", admin)
        unit.members.save(
            replace(
                person, exceptions=(PermissionRule(Permission.TASKS_APPROVE, False),), revision=2
            ),
            1,
        )
    before = state(store, occurrence_id)
    with pytest.raises(Forbidden):
        commands.verify("approve", request)
    assert state(store, occurrence_id) == before


def test_approval_and_reopening_race_has_one_decision_and_consistent_cycle_pointer(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    commands, child, store, occurrence_id, _, _ = prepared(tmp_path)
    perform(child, store, occurrence_id, ("child",))
    work, cycle = work_at(store, occurrence_id)
    gate = Barrier(2)

    def change(action):
        request = (
            VerifyTask(occurrence_id, work.revision, cycle.cycle_id, VerificationState.APPROVED)
            if action == "verify"
            else ReopenTask(occurrence_id, work.revision, cycle.cycle_id, "Retry")
        )
        gate.wait(timeout=5)
        try:
            return action, getattr(commands, action)("race", request)
        except Conflict:
            return action, None

    before = state(store, occurrence_id)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(change, ("verify", "reopen")))
    winners = [action for action, result in results if result is not None]
    assert len(winners) == 1
    after = state(store, occurrence_id)
    assert len(after[2]) == len(before[2]) + 1 and len(after[3]) == len(before[3]) + 1
    current, saved = after[0], after[1][0]
    if winners == ["verify"]:
        assert (
            current.current_cycle_id == cycle.cycle_id
            and saved.verification is VerificationState.APPROVED
        )
        assert current.current_cycle_revision == saved.revision == 2 and saved.closed_at is None
    else:
        assert current.current_cycle_id is None and saved.closed_at == 100 and saved.revision == 2
