"""Task reads use current local authority, bounded pages and side-effect-free planning."""

from dataclasses import replace

import pytest
from test_task_commands import fixture, resource
from test_task_cursor import KEY, Clock
from test_task_execution_commands import perform, prepared, state, work_at

from domus.application.task_commands import (
    AssignTask,
    ClaimTask,
    CompleteTask,
    CreateTask,
    CreateTaskOccurrence,
    ReopenTask,
    TransitionTask,
    UpdateTaskDefinition,
    UpdateTaskDependencies,
    UpdateTaskPolicy,
    VerifyTask,
)
from domus.application.task_queries import TaskQueries
from domus.domain.errors import Forbidden, InvalidInput, NotFound, StorageFailure
from domus.domain.identity import HumanIdentity, MemberStatus, Permission, PermissionRule, Role
from domus.domain.storage import Installation
from domus.domain.task_values import (
    DefinitionState,
    DependencyGate,
    OccurrenceState,
    TaskContent,
    TaskOverrides,
    TaskRules,
    VerificationState,
)
from domus.infrastructure.task_cursor import TaskCursor


def queries(store, human):
    return TaskQueries(store, human, TaskCursor(Clock(), KEY), store.installation)


def test_reading_empty_defaults_does_not_initialize_policy_or_allocate_a_receipt(tmp_path):
    commands, store, actor, ids = fixture(tmp_path)
    service = queries(store, actor.current())
    allocated = ids.count
    policy = service.policy()
    assert policy.rules == TaskRules() and policy.revision == 0 and policy.can_configure
    assert service.definitions().items == service.occurrences().items == ()
    assert service.definitions().next_cursor is None and ids.count == allocated
    with store.read() as unit:
        assert unit.tasks.policy("home") is None and len(unit.audit.entries("home")) == 1
    commands.update_policy("defaults", UpdateTaskPolicy(0, TaskRules(claim_allowed=False)))
    policy = service.policy()
    assert not policy.rules.claim_allowed and policy.revision == 1


def test_definition_and_occurrence_pages_use_exact_filters_and_no_duplicate_keys(tmp_path):
    commands, store, actor, _ = fixture(tmp_path)
    created = [
        commands.create(f"create-{i}", CreateTask(TaskContent(f"Work {i}"))) for i in range(7)
    ]
    service = queries(store, actor.current())
    for name in ("definitions", "occurrences"):
        read = getattr(service, name)
        seen, cursor = [], None
        while True:
            page = read(limit=2, cursor=cursor)
            assert len(page.items) <= 2
            seen.extend(
                item.definition_id if name == "definitions" else item.occurrence_id
                for item in page.items
            )
            cursor = page.next_cursor
            if cursor is None:
                break
        assert len(seen) == len(set(seen)) == 7 and seen == sorted(seen)
    did, oid = resource(created[0])
    assert service.definition(did).content.title == "Work 0"
    assert [item.occurrence_id for item in service.occurrences(definition_id=did).items] == [oid]
    assert not service.occurrences(assignee_id="child").items
    assert not service.definitions(state=DefinitionState.DRAFT).items
    assert not service.occurrences(state=OccurrenceState.COMPLETED).items
    assert len(service.definitions(state=DefinitionState.ACTIVE).items) == 7


@pytest.mark.parametrize("name", ["definitions", "occurrences"])
@pytest.mark.parametrize("limit", [True, 0, -1, 101, 1.5, "25"])
def test_query_limits_are_strict_before_storage(name, limit, tmp_path):
    _, store, actor, _ = fixture(tmp_path)
    with pytest.raises(InvalidInput):
        getattr(queries(store, actor.current()), name)(limit=limit)


def test_cursor_cannot_be_used_for_another_query_filter_actor_channel_or_installation(tmp_path):
    commands, store, actor, _ = fixture(tmp_path)
    for i in range(3):
        commands.create(str(i), CreateTask(TaskContent("Work")))
    service = queries(store, actor.current())
    cursor = service.occurrences(limit=1).next_cursor
    for changes in (
        {"limit": 2},
        {"state": OccurrenceState.AVAILABLE},
        {"definition_id": "def"},
        {"assignee_id": "child"},
    ):
        with pytest.raises(InvalidInput):
            service.occurrences(cursor=cursor, **({"limit": 1} | changes))
    with pytest.raises(InvalidInput):
        service.definitions(limit=1, cursor=cursor)
    contexts = [
        replace(service, human=HumanIdentity("ha_child", False, True, False)),
        replace(service, installation=Installation(store.installation.instance_id, "stable")),
        replace(service, installation=Installation("00000000-0000-4000-8000-000000000001", "edge")),
    ]
    for context in contexts:
        with pytest.raises(InvalidInput):
            context.occurrences(limit=1, cursor=cursor)


@pytest.mark.parametrize(
    "name,args",
    [
        ("policy", ()),
        ("definition", ("missing",)),
        ("occurrence", ("missing",)),
        ("definitions", ()),
        ("occurrences", ()),
        ("history", ("missing",)),
        ("operation", ("missing",)),
    ],
)
def test_current_revocation_prevents_every_read_and_resource_discovery(tmp_path, name, args):
    _, store, actor, _ = fixture(tmp_path)
    service = queries(store, actor.current())
    with store.write() as unit:
        person = unit.members.by_user("home", actor.human.ha_user_id)
        unit.members.save(
            replace(person, exceptions=(PermissionRule(Permission.TASKS_READ, False),), revision=2),
            1,
        )
    with pytest.raises(Forbidden):
        getattr(service, name)(*args)


def test_cursor_is_not_authority_after_a_member_is_suspended(tmp_path):
    commands, store, actor, _ = fixture(tmp_path)
    for i in range(2):
        commands.create(str(i), CreateTask(TaskContent("Work")))
    service = queries(store, actor.current())
    cursor = service.definitions(limit=1).next_cursor
    with store.write() as unit:
        person = unit.members.by_user("home", actor.human.ha_user_id)
        unit.members.save(replace(person, status=MemberStatus.SUSPENDED, revision=2), 1)
    with pytest.raises(Forbidden):
        service.definitions(limit=1, cursor=cursor)


def test_missing_and_foreign_household_tasks_are_not_disclosed(tmp_path):
    commands, _, store, oid, _, _ = prepared(tmp_path)
    service = queries(store, commands.actor.current())
    for name in ("definition", "occurrence"):
        with pytest.raises(NotFound):
            getattr(service, name)("missing")
        with pytest.raises(Forbidden):
            getattr(replace(service, household_id="other"), name)(oid)


def test_allowed_actions_follow_assignment_profile_and_terminal_state_without_effects(tmp_path):
    commands, child, store, oid, admin, ids = prepared(tmp_path)
    service = queries(store, child.actor.current())
    before, allocated = state(store, oid), ids.count
    detail = service.occurrence(oid)
    assert detail.work.assignee_ids == ("child",) and detail.rules == TaskRules()
    assert (
        "complete" in detail.allowed_actions and "transition:in_progress" in detail.allowed_actions
    )
    assert "assign" not in detail.allowed_actions and "claim" not in detail.allowed_actions
    assert state(store, oid) == before and ids.count == allocated
    perform(child, store, oid, ("child",))
    detail = service.occurrence(oid)
    assert detail.cycle.verification is VerificationState.PENDING and not detail.allowed_actions
    adult = queries(store, commands.actor.current()).occurrence(oid)
    assert set(adult.allowed_actions) == {"approve", "reject", "reopen"}
    with store.write() as unit:
        person = unit.members.get("home", admin)
        unit.members.save(replace(person, role=Role.VIEWER, revision=2), 1)
    # The fixture HA administrator remains administrator under follow_ha policy.
    observer = replace(service, human=HumanIdentity("ha_admin", False, True, False))
    assert not observer.occurrence(oid).allowed_actions


@pytest.mark.parametrize(
    "gate,allowed", [(DependencyGate.PERFORMED, True), (DependencyGate.APPROVED, False)]
)
def test_completion_hint_obeys_the_owner_selected_pending_dependency_gate(tmp_path, gate, allowed):
    commands, child, store, prerequisite, _, _ = prepared(tmp_path)
    perform(child, store, prerequisite, ("child",))
    dependent = resource(commands.create("dependent", CreateTask(TaskContent("Dependent"))))[1]
    commands.update_dependencies(
        "dependency", UpdateTaskDependencies(dependent, 1, (prerequisite,))
    )
    if gate is DependencyGate.APPROVED:
        commands.update_policy("gate", UpdateTaskPolicy(1, TaskRules(dependency_gate=gate)))
    detail = queries(store, commands.actor.current()).occurrence(dependent)
    assert ("complete" in detail.allowed_actions) is allowed
    assert detail.requirements[0].verification is VerificationState.PENDING


def test_detail_refuses_missing_defaults_and_corrupted_required_work(tmp_path):
    from test_task_execution_commands import link

    commands, _, store, oid, _, _ = prepared(tmp_path)
    service = queries(store, commands.actor.current())
    link(store, oid, ("missing",))
    with pytest.raises(StorageFailure):
        service.occurrence(oid)
    link(store, oid, ())
    with store._connection() as connection:
        connection.execute("DELETE FROM task_policy")
    with pytest.raises(StorageFailure):
        service.occurrence(oid)


def test_history_discloses_local_summaries_and_never_raw_identities_or_canonical_requests(tmp_path):
    import json
    from dataclasses import asdict

    commands, child, store, oid, _, _ = prepared(tmp_path)
    original = perform(child, store, oid, ("child",))
    service = queries(store, commands.actor.current())
    before = state(store, oid)
    first = service.history(oid, limit=2)
    second = service.history(oid, limit=2, cursor=first.next_cursor)
    assert len(first.items) == 2 and len(second.items) == 1 and second.next_cursor is None
    fact = second.items[0]
    assert fact.operation_id == original.operation_id and fact.actor_member_id == "child"
    assert fact.verification is VerificationState.PENDING and fact.performed_at == 90
    assert fact.outbox_delivery == "pending" and fact.consumer_delivery == "unconfirmed"
    assert not fact.historical and fact.archived_by is None
    serialized = json.dumps(asdict(second))
    assert (
        "ha_child" not in serialized
        and "request" not in serialized
        and "payload_fingerprint" not in serialized
    )
    assert state(store, oid) == before
    with pytest.raises(InvalidInput):
        service.history("other", limit=2, cursor=first.next_cursor)
    with pytest.raises(NotFound):
        service.history("other")


@pytest.mark.parametrize(
    "action",
    [
        "create",
        "assign",
        "claim",
        "transition",
        "complete",
        "verify",
        "reopen",
        "update_policy",
        "update_definition",
        "create_occurrence",
        "update_dependencies",
    ],
)
def test_own_operation_lookup_rechecks_original_authority_without_rerunning_preconditions(
    tmp_path, action
):
    commands, child, store, oid, admin, _ = prepared(tmp_path, assign=False)
    with store.read() as unit:
        work = unit.tasks.occurrence("home", oid)
    did = work.definition_snapshot.definition_id
    service = commands
    if action == "create":
        request = CreateTask(
            TaskContent("Other work"), overrides=TaskOverrides(claim_allowed=False)
        )
    elif action == "assign":
        request = AssignTask(oid, 1, ("child",))
    elif action == "claim":
        service, request = child, ClaimTask(oid, 1)
    elif action == "transition":
        request = TransitionTask(oid, 1, OccurrenceState.BLOCKED, "Waiting")
    elif action == "complete":
        request = CompleteTask(oid, 1, (admin,), 90)
    elif action in ("verify", "reopen"):
        perform(commands, store, oid, ("child",))
        work, cycle = work_at(store, oid)
        request = (
            VerifyTask(oid, work.revision, cycle.cycle_id, VerificationState.APPROVED)
            if action == "verify"
            else ReopenTask(oid, work.revision, cycle.cycle_id, "Repeat")
        )
    elif action == "update_policy":
        request = UpdateTaskPolicy(1, TaskRules(claim_allowed=False))
    elif action == "update_definition":
        request = UpdateTaskDefinition(
            did, 1, TaskContent("Revised"), DefinitionState.ACTIVE, TaskOverrides()
        )
    elif action == "create_occurrence":
        request = CreateTaskOccurrence(did)
    else:
        prerequisite = resource(
            commands.create("prerequisite", CreateTask(TaskContent("Required")))
        )[1]
        request = UpdateTaskDependencies(oid, 1, (prerequisite,))
    receipt = getattr(service, action)("lookup", request)
    query = queries(store, service.actor.current())
    before = state(store, oid)
    assert query.operation(receipt.operation_id).receipt == receipt
    assert state(store, oid) == before
    other = commands if service is child else child
    with pytest.raises(NotFound):
        queries(store, other.actor.current()).operation(receipt.operation_id)
    with pytest.raises(NotFound):
        query.operation("unknown")


@pytest.mark.parametrize(
    "kind,permission",
    [("overrides", Permission.TASKS_CONFIGURE), ("on_behalf", Permission.TASKS_RECORD_FOR_OTHERS)],
)
def test_original_configuration_and_attribution_grants_are_required_again_for_operation_lookup(
    tmp_path, kind, permission
):
    commands, _, store, oid, admin, _ = prepared(tmp_path)
    receipt = (
        commands.create(
            "custom", CreateTask(TaskContent("Configured"), TaskOverrides(claim_allowed=False))
        )
        if kind == "overrides"
        else perform(commands, store, oid, ("child",))
    )
    query = queries(store, commands.actor.current())
    assert query.operation(receipt.operation_id).receipt == receipt
    with store.write() as unit:
        person = unit.members.get("home", admin)
        updated = (
            replace(person, role=Role.ADULT, revision=2)
            if permission is Permission.TASKS_CONFIGURE
            else replace(person, exceptions=(PermissionRule(permission, False),), revision=2)
        )
        unit.members.save(updated, 1)
    if permission is Permission.TASKS_CONFIGURE:
        query = replace(query, human=HumanIdentity("ha_admin", False, True, False))
    with pytest.raises(Forbidden):
        query.operation(receipt.operation_id)


@pytest.mark.parametrize("kind", ["definitions", "occurrences"])
def test_invalid_filter_types_are_safe_input_failures(tmp_path, kind):
    _, store, actor, _ = fixture(tmp_path)
    with pytest.raises(InvalidInput):
        getattr(queries(store, actor.current()), kind)(state="available")


@pytest.mark.parametrize("marker", ["abc", "0", "01", str(2**63)])
def test_history_rejects_an_inapplicable_signed_position(tmp_path, marker):
    from domus.domain.storage import JsonDocument

    commands, _, store, oid, _, _ = prepared(tmp_path)
    service = queries(store, commands.actor.current())
    binding, _ = service._context(
        "history", 25, JsonDocument.from_value({"occurrence_id": oid}), None
    )
    cursor = service.cursors.encode(binding, marker)
    with pytest.raises(InvalidInput):
        service.history(oid, cursor=cursor)


def test_draft_action_hints_and_revision_exhaustion_never_invite_an_impossible_write(tmp_path):
    from domus.infrastructure.sqlite_task_records import occurrence_document

    commands, store, actor, _ = fixture(tmp_path)
    receipt = commands.create(
        "draft", CreateTask(TaskContent("Draft"), state=DefinitionState.DRAFT)
    )
    _, oid = resource(receipt)
    service = queries(store, actor.current())
    detail = service.occurrence(oid)
    assert (
        "dependencies.update" in detail.allowed_actions and "assign" not in detail.allowed_actions
    )
    assert (
        "transition:available" in detail.allowed_actions
        and "complete" not in detail.allowed_actions
    )
    with store._connection() as connection:
        exhausted = replace(detail.work, revision=2**63 - 1)
        connection.execute(
            "UPDATE task_occurrences SET revision=?,document=? WHERE occurrence_id=?",
            (exhausted.revision, occurrence_document(exhausted).encoded, oid),
        )
    assert not service.occurrence(oid).allowed_actions


def rewrite_fact(
    row,
    *,
    request_changes=None,
    result_changes=None,
    detail_changes=None,
    event_changes=None,
    action=None,
    fingerprint=None,
):
    """Explicit broken-port evidence; no claim about a valid SQLite writer producing it."""
    from domus.domain.storage import JsonDocument

    evidence = row.evidence
    detail, result = evidence.audit.detail.decode(), evidence.receipt.result.decode()
    if request_changes is not None:
        detail["request"].update(request_changes)
    if result_changes is not None:
        result.update(result_changes)
    detail["result"] = result
    request = JsonDocument.from_value(detail["request"])
    command = (
        evidence.receipt.command
        if action is None
        else replace(evidence.receipt.command, action=action)
    )
    event = {"version": 1, "kind": detail["transition"], **result}
    if detail_changes:
        detail.update(detail_changes)
    if event_changes:
        event.update(event_changes)
    return replace(
        row,
        evidence=replace(
            evidence,
            receipt=replace(
                evidence.receipt,
                command=command,
                payload_fingerprint=request.fingerprint if fingerprint is None else fingerprint,
                result=JsonDocument.from_value(result),
            ),
            audit=replace(evidence.audit, command=command, detail=JsonDocument.from_value(detail)),
            event=replace(
                evidence.event, event_type=command.action, payload=JsonDocument.from_value(event)
            ),
        ),
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"action": "task.future"},
        {"detail_changes": {"extra": 1}},
        {"detail_changes": {"transition": "task.other"}},
        {"detail_changes": {"request": []}},
        {"request_changes": {"unexpected": True}},
        {"fingerprint": "0" * 64},
        {"detail_changes": {"result": {"revision": 1}}},
        {"event_changes": {"kind": "task.other"}},
        {"request_changes": {"occurrence_id": "bad id"}},
        {"request_changes": {"performer_ids": "child"}},
        {"request_changes": {"performer_ids": []}},
        {"request_changes": {"performer_ids": ["bad id"]}},
    ],
)
def test_operation_lookup_rejects_inconsistent_or_unknown_evidence(tmp_path, monkeypatch, changes):
    from domus.infrastructure.sqlite_tasks import SQLiteTasks

    commands, child, store, oid, _, _ = prepared(tmp_path)
    receipt = perform(child, store, oid, ("child",))
    with store.read() as unit:
        row = unit.tasks.operation("home", "ha_child", receipt.operation_id)
    corrupted = rewrite_fact(row, **changes)
    monkeypatch.setattr(SQLiteTasks, "operation", lambda *_: corrupted)
    with pytest.raises(StorageFailure):
        queries(store, child.actor.current()).operation(receipt.operation_id)


@pytest.mark.parametrize("overrides", [None, [], {"claim_allowed": False}])
def test_original_create_overrides_require_complete_known_authority_context(
    tmp_path, monkeypatch, overrides
):
    from domus.infrastructure.sqlite_tasks import SQLiteTasks

    commands, _, store, oid, _, _ = prepared(tmp_path)
    with store.read() as unit:
        row = unit.tasks.history("home", oid)[0]
    corrupted = rewrite_fact(row, request_changes={"overrides": overrides})
    monkeypatch.setattr(SQLiteTasks, "operation", lambda *_: corrupted)
    with pytest.raises(StorageFailure):
        queries(store, commands.actor.current()).operation(row.evidence.receipt.operation_id)


def test_unknown_original_transition_target_is_not_authority(tmp_path, monkeypatch):
    from domus.infrastructure.sqlite_tasks import SQLiteTasks

    commands, _, store, oid, _, _ = prepared(tmp_path)
    receipt = commands.transition(
        "blocked", TransitionTask(oid, 2, OccurrenceState.BLOCKED, "Wait")
    )
    with store.read() as unit:
        row = unit.tasks.operation("home", "ha_admin", receipt.operation_id)
    corrupted = rewrite_fact(row, request_changes={"target": "future-state"})
    monkeypatch.setattr(SQLiteTasks, "operation", lambda *_: corrupted)
    with pytest.raises(StorageFailure):
        queries(store, commands.actor.current()).operation(receipt.operation_id)


@pytest.mark.parametrize(
    "changes",
    [
        {"occurrence_id": "other"},
        {"revision": True},
        {"state": "future"},
        {"cycle": []},
        {"cycle": None},
        {
            "cycle": {
                "cycle_id": "cycle",
                "verification": "pending",
                "performed_at": 90,
                "household_id": "other",
                "occurrence_id": "work",
            }
        },
    ],
)
def test_history_refuses_semantically_invalid_projection_facts(tmp_path, monkeypatch, changes):
    from domus.infrastructure.sqlite_tasks import SQLiteTasks

    commands, child, store, oid, _, _ = prepared(tmp_path)
    receipt = perform(child, store, oid, ("child",))
    with store.read() as unit:
        row = unit.tasks.operation("home", "ha_child", receipt.operation_id)
    corrupted = rewrite_fact(row, result_changes=changes)
    monkeypatch.setattr(SQLiteTasks, "history", lambda *_, **__: (corrupted,))
    with pytest.raises(StorageFailure):
        queries(store, commands.actor.current()).history(oid)


def test_actual_offline_restoration_exposes_history_without_reapplying_rolled_back_work(tmp_path):
    from test_activation_compatibility import identity_at
    from test_sqlite_snapshots import Clock as SnapshotClock

    from domus.application.task_commands import TaskCommands
    from domus.infrastructure.owned_storage import open_storage
    from domus.infrastructure.sqlite_activation import SQLiteActivation
    from domus.infrastructure.sqlite_restoration import SQLiteRestorations
    from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots

    root, archive, target = tmp_path / "source", tmp_path / "archive", tmp_path / "prepared"
    root.mkdir(mode=0o700)
    commands, child, store, oid, _, ids = prepared(root)
    identity_at(root, store.installation)
    checkpoint = SQLiteSnapshots(store, archive, store.installation, SnapshotClock()).create(
        "before-work"
    )
    receipt = perform(child, store, oid, ("child",))
    SQLiteRestorations(
        store, archive, target, store.installation, SnapshotClock(), checkpoint
    ).prepare("restore-work")
    assert (
        SQLiteActivation(root, store.installation, SnapshotClock(), target).activate().state
        == "active"
    )
    restored = open_storage(root, "edge")
    try:
        service = queries(restored.database, child.actor.current())
        before = state(restored.database, oid)
        history = service.history(oid).items
        assert len(history) == 3 and sum(item.historical for item in history) == 1
        assert (
            history[-1].outbox_delivery == "suppressed"
            and history[-1].archived_by == "restore-work"
        )
        assert service.operation(receipt.operation_id).receipt.historical
        assert service.occurrence(oid).cycle is None and state(restored.database, oid) == before
        cursor = service.history(oid, limit=2).next_cursor
        fresh = TaskCommands(restored.database, child.actor, child.clock, ids)
        new_receipt = fresh.complete("new-work", CompleteTask(oid, 2, ("child",), 90))
        tail = service.history(oid, limit=2, cursor=cursor).items
        assert [item.operation_id for item in tail] == [
            receipt.operation_id,
            new_receipt.operation_id,
        ]
        assert tail[0].historical and not tail[1].historical
    finally:
        restored.close()
