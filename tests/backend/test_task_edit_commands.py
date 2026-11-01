"""Task editors preserve prior snapshots and validate the complete scoped graph in SQLite."""

from dataclasses import replace

import pytest
from test_task_commands import child_commands, fixture, resource
from test_task_execution_commands import perform, work_at

from domus.application.task_commands import CreateTask
from domus.application.task_requests import (
    ClaimTask,
    CreateTaskOccurrence,
    UpdateTaskDefinition,
    UpdateTaskDependencies,
    UpdateTaskPolicy,
)
from domus.domain.errors import Conflict, Forbidden, InvalidInput, StorageFailure
from domus.domain.identity import Role
from domus.domain.task_values import (
    DefinitionState,
    DependencyGate,
    OccurrenceState,
    TaskContent,
    TaskOverrides,
    TaskRules,
)
from domus.infrastructure.sqlite_tasks import SQLiteTasks


def created(commands, key="create", title="Original", overrides=None):
    return resource(
        commands.create(
            key,
            CreateTask(
                TaskContent(title), overrides=TaskOverrides() if overrides is None else overrides
            ),
        )
    )


def snapshot(store):
    with store.read() as unit:
        return (
            unit.tasks.policy("home"),
            unit.tasks.definitions("home", limit=101),
            unit.tasks.occurrences("home", limit=101),
            unit.audit.entries("home"),
            unit.outbox.pending(),
        )


def test_explicit_policy_initialization_and_revisioned_update_do_not_rewrite_cycles(tmp_path):
    commands, store, _, ids = fixture(tmp_path)
    request = UpdateTaskPolicy(0, TaskRules(claim_allowed=False))
    receipt = commands.update_policy("policy", request)
    assert commands.update_policy("policy", request) == receipt
    definition_id, occurrence_id = created(commands)
    child, _ = child_commands(store, identifiers=ids)
    with pytest.raises(Forbidden):
        child.claim("blocked", ClaimTask(occurrence_id, 1))
    commands.update_policy(
        "enable", UpdateTaskPolicy(1, TaskRules(dependency_gate=DependencyGate.APPROVED))
    )
    with store.read() as unit:
        admin = unit.members.by_user("home", "ha_admin").member_id
    perform(commands, store, occurrence_id, (admin,))
    old = work_at(store, occurrence_id)
    commands.update_policy("change-default", UpdateTaskPolicy(2, TaskRules(point_value_minor=100)))
    assert work_at(store, occurrence_id) == old
    assert (
        old[1].task_policy_revision == 2 and old[1].rules.dependency_gate is DependencyGate.APPROVED
    )
    with pytest.raises(Conflict, match="revision_conflict"):
        commands.update_policy("stale", UpdateTaskPolicy(1, TaskRules()))
    with pytest.raises(Conflict, match="task_unchanged"):
        commands.update_policy("unchanged", UpdateTaskPolicy(3, TaskRules(point_value_minor=100)))


def test_definition_edits_affect_only_later_occurrences_and_override_reset_is_explicit(tmp_path):
    commands, store, actor, _ = fixture(tmp_path)
    definition_id, first_id = created(commands, overrides=TaskOverrides(point_value_minor=500))
    request = UpdateTaskDefinition(definition_id, 1, TaskContent("Revised"), DefinitionState.ACTIVE)
    receipt = commands.update_definition("edit", request)
    assert commands.update_definition("edit", request) == receipt
    second = commands.create_occurrence(
        "next", CreateTaskOccurrence(definition_id, assignee_ids=("child",), due_at=150)
    )
    second_id = second.result.decode()["occurrence_id"]
    with store.read() as unit:
        first, second = (
            unit.tasks.occurrence("home", first_id),
            unit.tasks.occurrence("home", second_id),
        )
        assert (
            first.definition_snapshot.content.title == "Original"
            and first.definition_snapshot.revision == 1
        )
        assert (
            second.definition_snapshot.content.title == "Revised"
            and second.definition_snapshot.revision == 2
        )
        assert (
            second.due_at == 150
            and second.assignee_ids == ("child",)
            and second.state is OccurrenceState.ASSIGNED
        )
        assert second.definition_snapshot.overrides.point_value_minor == 500
        person = unit.members.by_user("home", actor.human.ha_user_id)
    with store.write() as unit:
        unit.members.save(replace(person, role=Role.ADULT, revision=2), 1)
    actor.human = replace(actor.human, is_administrator=False)
    commands.update_definition(
        "adult-content",
        UpdateTaskDefinition(definition_id, 2, TaskContent("Adult edit"), DefinitionState.ACTIVE),
    )
    explicit = UpdateTaskDefinition(
        definition_id, 3, TaskContent("Adult edit"), DefinitionState.ACTIVE, TaskOverrides()
    )
    with pytest.raises(Forbidden):
        commands.update_definition("reset", explicit)
    actor.human = replace(actor.human, is_administrator=True)
    result = commands.update_definition("reset", explicit)
    assert commands.update_definition("reset", explicit) == result
    actor.human = replace(actor.human, is_administrator=False)
    with pytest.raises(Forbidden):
        commands.update_definition("reset", explicit)
    with store.read() as unit:
        assert unit.tasks.definition("home", definition_id).overrides == TaskOverrides()
        assert (
            unit.tasks.occurrence("home", second_id).definition_snapshot.overrides.point_value_minor
            == 500
        )


@pytest.mark.parametrize("state", [DefinitionState.PAUSED, DefinitionState.ARCHIVED])
def test_pausing_or_archiving_stops_new_work_but_not_replay_or_existing_work(tmp_path, state):
    commands, store, actor, _ = fixture(tmp_path)
    definition_id, first_id = created(commands)
    request = CreateTaskOccurrence(definition_id)
    original = commands.create_occurrence("next", request)
    commands.update_definition(
        "stop", UpdateTaskDefinition(definition_id, 1, TaskContent("Original"), state)
    )
    assert commands.create_occurrence("next", request) == original
    with pytest.raises(Conflict, match="task_definition_unavailable"):
        commands.create_occurrence("new", request)
    with store.read() as unit:
        admin = unit.members.by_user("home", actor.human.ha_user_id).member_id
    perform(commands, store, first_id, (admin,))
    assert work_at(store, first_id)[0].state is OccurrenceState.COMPLETED


def test_dependency_edits_are_scoped_acyclic_revisioned_and_replay_safe(tmp_path):
    commands, store, _, _ = fixture(tmp_path)
    _, first = created(commands, "first")
    _, second = created(commands, "second")
    _, third = created(commands, "third")
    request = UpdateTaskDependencies(second, 1, (first,), (third,))
    result = commands.update_dependencies("link", request)
    assert commands.update_dependencies("link", request) == result
    with store.read() as unit:
        work = unit.tasks.occurrence("home", second)
        assert (
            work.prerequisite_ids == (first,)
            and work.required_subtask_ids == (third,)
            and work.revision == 2
        )
    before = snapshot(store)
    for target, required in [(first, (second,)), (third, (second,))]:
        with pytest.raises(InvalidInput, match="task_dependency_cycle"):
            commands.update_dependencies(
                "cycle-" + target, UpdateTaskDependencies(target, 1, required)
            )
    for required in [("foreign-or-missing",), (first,)]:
        with pytest.raises(InvalidInput, match="invalid_task_dependency"):
            commands.update_dependencies(
                "invalid-" + required[0], UpdateTaskDependencies(first, 1, required)
            )
    with pytest.raises(Conflict, match="revision_conflict"):
        commands.update_dependencies("stale", UpdateTaskDependencies(second, 1, ()))
    with pytest.raises(Conflict, match="task_unchanged"):
        commands.update_dependencies(
            "unchanged", UpdateTaskDependencies(second, 2, (first,), (third,))
        )
    assert snapshot(store) == before


@pytest.mark.parametrize("back_edge", [False, True])
def test_graph_validation_includes_edges_beyond_first_repository_page(tmp_path, back_edge):
    commands, store, _, _ = fixture(tmp_path)
    definition_id, first = created(commands)
    with store.write() as unit:
        item = unit.tasks.definition("home", definition_id)
        for number in range(104):
            identity = f"z{number:03d}"
            required = (first,) if number == 103 and back_edge else ()
            unit.tasks.save_occurrence(
                item.new_occurrence(identity, 100, prerequisites=required), 0
            )
    if back_edge:
        with pytest.raises(InvalidInput, match="task_dependency_cycle"):
            commands.update_dependencies("tail", UpdateTaskDependencies(first, 1, ("z103",)))
    else:
        commands.update_dependencies("tail", UpdateTaskDependencies(first, 1, ("z103",)))
        with store.read() as unit:
            assert unit.tasks.occurrence("home", first).prerequisite_ids == ("z103",)


def test_new_occurrence_validates_assignees_references_and_definition_scope(tmp_path):
    commands, store, _, _ = fixture(tmp_path)
    definition_id, first = created(commands)
    good = commands.create_occurrence(
        "good",
        CreateTaskOccurrence(
            definition_id, prerequisite_ids=(first,), required_subtask_ids=(first,), due_at=0
        ),
    )
    with store.read() as unit:
        work = unit.tasks.occurrence("home", good.result.decode()["occurrence_id"])
        assert work.prerequisite_ids == work.required_subtask_ids == (first,) and work.due_at == 0
    before = snapshot(store)
    with pytest.raises(InvalidInput, match="invalid_task_dependency"):
        commands.create_occurrence(
            "unknown", CreateTaskOccurrence(definition_id, prerequisite_ids=("missing",))
        )
    with pytest.raises(Forbidden, match="task_assignee_denied"):
        commands.create_occurrence(
            "missing-assignee", CreateTaskOccurrence(definition_id, assignee_ids=("missing",))
        )
    with pytest.raises(Forbidden):
        commands.create_occurrence("foreign", CreateTaskOccurrence("other-definition"))
    assert snapshot(store) == before


@pytest.mark.parametrize(
    "state", [OccurrenceState.COMPLETED, OccurrenceState.CANCELLED, OccurrenceState.SKIPPED]
)
def test_terminal_dependency_facts_are_not_rewritten(tmp_path, state):
    commands, store, actor, _ = fixture(tmp_path)
    _, first = created(commands, "first")
    _, second = created(commands, "second")
    if state is OccurrenceState.COMPLETED:
        with store.read() as unit:
            admin = unit.members.by_user("home", actor.human.ha_user_id).member_id
        perform(commands, store, first, (admin,))
    else:
        from domus.application.task_requests import TransitionTask

        commands.transition(
            "terminal", TransitionTask(first, 1, state, "Explicit terminal decision")
        )
    before = snapshot(store)
    with pytest.raises(Conflict, match="task_transition_conflict"):
        commands.update_dependencies("rewrite", UpdateTaskDependencies(first, 2, (second,)))
    assert snapshot(store) == before


@pytest.mark.parametrize("action", ["policy", "definition", "occurrence", "dependencies"])
def test_editor_failure_after_actual_write_rolls_back_resources_and_evidence(
    tmp_path, monkeypatch, action
):
    commands, store, _, _ = fixture(tmp_path)
    definition_id, first = created(commands, "first")
    _, second = created(commands, "second")
    operation, request, method = {
        "policy": (
            "update_policy",
            UpdateTaskPolicy(1, TaskRules(claim_allowed=False)),
            "save_policy",
        ),
        "definition": (
            "update_definition",
            UpdateTaskDefinition(definition_id, 1, TaskContent("New"), DefinitionState.ACTIVE),
            "save_definition",
        ),
        "occurrence": ("create_occurrence", CreateTaskOccurrence(definition_id), "save_occurrence"),
        "dependencies": (
            "update_dependencies",
            UpdateTaskDependencies(first, 1, (second,)),
            "save_occurrence",
        ),
    }[action]
    before = snapshot(store)
    original = getattr(SQLiteTasks, method)

    def fail(self, value, expected_revision):
        original(self, value, expected_revision)
        raise StorageFailure("injected_failure")

    monkeypatch.setattr(SQLiteTasks, method, fail)
    with pytest.raises(StorageFailure):
        getattr(commands, operation)("failed", request)
    assert snapshot(store) == before


@pytest.mark.parametrize(
    "build_request",
    [
        lambda: UpdateTaskPolicy(True, TaskRules()),
        lambda: UpdateTaskPolicy(-1, TaskRules()),
        lambda: UpdateTaskPolicy(2**63, TaskRules()),
        lambda: UpdateTaskPolicy(0, {}),
        lambda: UpdateTaskDefinition("def", 1, "title", DefinitionState.ACTIVE),
        lambda: UpdateTaskDefinition("def", 1, TaskContent("Title"), "active"),
        lambda: UpdateTaskDefinition("def", 1, TaskContent("Title"), DefinitionState.ACTIVE, {}),
        lambda: CreateTaskOccurrence("def", expected_revision=True),
        lambda: CreateTaskOccurrence("def", expected_revision=1),
        lambda: CreateTaskOccurrence("def", prerequisite_ids=["required"]),
        lambda: CreateTaskOccurrence("def", required_subtask_ids=("same", "same")),
        lambda: CreateTaskOccurrence("def", due_at=True),
        lambda: CreateTaskOccurrence("def", due_at=-1),
        lambda: UpdateTaskDependencies("occ", 0, ()),
        lambda: UpdateTaskDependencies("occ", 1, required_subtask_ids=("same", "same")),
        lambda: UpdateTaskDependencies("occ", 1, tuple("id-" + str(i) for i in range(33))),
    ],
)
def test_editor_request_bounds_reject_invalid_types_revisions_and_lists(build_request):
    with pytest.raises(InvalidInput):
        build_request()


def test_stale_definition_update_and_unchanged_fields_do_not_add_evidence(tmp_path):
    commands, store, _, _ = fixture(tmp_path)
    definition_id, _ = created(commands)
    before = snapshot(store)
    with pytest.raises(Conflict, match="revision_conflict"):
        commands.update_definition(
            "stale",
            UpdateTaskDefinition(definition_id, 2, TaskContent("New"), DefinitionState.ACTIVE),
        )
    with pytest.raises(Conflict, match="task_unchanged"):
        commands.update_definition(
            "same",
            UpdateTaskDefinition(definition_id, 1, TaskContent("Original"), DefinitionState.ACTIVE),
        )
    with pytest.raises(Forbidden):
        commands.update_definition(
            "foreign",
            UpdateTaskDefinition("foreign", 1, TaskContent("New"), DefinitionState.ACTIVE),
        )
    assert snapshot(store) == before


def test_ordinary_profiles_cannot_configure_policy_or_manage_other_work(tmp_path):
    commands, store, actor, ids = fixture(tmp_path)
    definition_id, first = created(commands)
    child, _ = child_commands(store, identifiers=ids)
    requests = [
        ("update_policy", UpdateTaskPolicy(1, TaskRules(claim_allowed=False))),
        (
            "update_definition",
            UpdateTaskDefinition(definition_id, 1, TaskContent("New"), DefinitionState.ACTIVE),
        ),
        ("create_occurrence", CreateTaskOccurrence(definition_id)),
        ("update_dependencies", UpdateTaskDependencies(first, 1, ("unknown",))),
    ]
    before = snapshot(store)
    for action, request in requests:
        with pytest.raises(Forbidden):
            getattr(child, action)(action, request)
    assert snapshot(store) == before
    request = UpdateTaskPolicy(1, TaskRules(claim_allowed=False))
    commands.update_policy("policy", request)
    actor.human = replace(actor.human, is_administrator=False)
    with pytest.raises(Forbidden):
        commands.update_policy("policy", request)


def test_dependency_receipt_cannot_restore_an_older_graph_after_an_explicit_change(tmp_path):
    commands, store, _, _ = fixture(tmp_path)
    _, first = created(commands, "first")
    _, second = created(commands, "second")
    _, third = created(commands, "third")
    request = UpdateTaskDependencies(first, 1, (second,))
    original = commands.update_dependencies("link", request)
    commands.update_dependencies("replace", UpdateTaskDependencies(first, 2, (third,)))
    before = snapshot(store)
    assert commands.update_dependencies("link", request) == original
    assert snapshot(store) == before
    with store.read() as unit:
        assert unit.tasks.occurrence("home", first).prerequisite_ids == (third,)


def test_competing_opposite_edges_cannot_commit_a_cycle(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    commands, store, _, _ = fixture(tmp_path)
    _, first = created(commands, "first")
    _, second = created(commands, "second")
    gate = Barrier(2)

    def link(pair):
        target, required = pair
        gate.wait(timeout=5)
        try:
            return commands.update_dependencies(
                target, UpdateTaskDependencies(target, 1, (required,))
            )
        except InvalidInput as error:
            assert error.code == "task_dependency_cycle"
            return None

    before = snapshot(store)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(link, [(first, second), (second, first)]))
    assert sum(result is not None for result in results) == 1
    after = snapshot(store)
    assert len(after[3]) == len(before[3]) + 1 and len(after[4]) == len(before[4]) + 1
    with store.read() as unit:
        a, b = unit.tasks.occurrence("home", first), unit.tasks.occurrence("home", second)
        assert (a.prerequisite_ids, b.prerequisite_ids) in [((second,), ()), ((), (first,))]


def test_definition_edit_accepts_maximum_utf8_content_without_exceeding_atomic_document_bounds(
    tmp_path,
):
    commands, store, _, _ = fixture(tmp_path)
    definition_id, _ = created(commands)
    content = TaskContent(
        "🏡" * 160, "🧹" * 4000, tags=tuple((str(i) + "🔧" * 63)[:64] for i in range(16))
    )
    commands.update_definition(
        "unicode", UpdateTaskDefinition(definition_id, 1, content, DefinitionState.ACTIVE)
    )
    with store.read() as unit:
        assert unit.tasks.definition("home", definition_id).content == content
        assert len(unit.audit.entries("home")[-1].detail.encoded.encode("utf-8")) <= 65536


@pytest.mark.parametrize("action", ["policy", "definition", "occurrence", "dependencies"])
def test_editor_receipts_do_not_reapply_restored_away_changes_after_actual_activation(
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
    commands, store, actor, ids = fixture(root)
    definition_id, first = created(commands, "first")
    _, second = created(commands, "second")
    identity_at(root, store.installation)
    operation, request = {
        "policy": ("update_policy", UpdateTaskPolicy(1, TaskRules(claim_allowed=False))),
        "definition": (
            "update_definition",
            UpdateTaskDefinition(
                definition_id,
                1,
                TaskContent("New"),
                DefinitionState.ACTIVE,
                TaskOverrides(claim_allowed=False),
            ),
        ),
        "occurrence": (
            "create_occurrence",
            CreateTaskOccurrence(definition_id, assignee_ids=("child",)),
        ),
        "dependencies": ("update_dependencies", UpdateTaskDependencies(first, 1, (second,))),
    }[action]
    checkpoint = SQLiteSnapshots(store, archive, store.installation, Clock()).create(
        "before-editor"
    )
    before = snapshot(store)[:3]
    original = getattr(commands, operation)(action, request)
    count = ids.count
    SQLiteRestorations(store, archive, target, store.installation, Clock(), checkpoint).prepare(
        "restore-editor"
    )
    assert SQLiteActivation(root, store.installation, Clock(), target).activate().state == "active"
    selected = open_storage(root, "edge")
    try:
        replay = TaskCommands(selected.database, actor, commands.clock, ids)
        receipt = getattr(replay, operation)(action, request)
        assert receipt.historical and receipt.operation_id == original.operation_id
        assert receipt.result == original.result and ids.count == count
        assert snapshot(selected.database)[:3] == before
    finally:
        selected.close()


def test_first_policy_update_racing_creation_preserves_defaults_or_returns_revision_conflict(
    tmp_path,
):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    commands, store, _, _ = fixture(tmp_path)
    gate = Barrier(2)

    def change(action):
        gate.wait(timeout=5)
        try:
            if action == "policy":
                return action, commands.update_policy(
                    "policy", UpdateTaskPolicy(0, TaskRules(claim_allowed=False))
                )
            return action, commands.create("create", CreateTask(TaskContent("Work")))
        except Conflict as error:
            assert action == "policy" and error.code == "revision_conflict"
            return action, None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = dict(pool.map(change, ("policy", "create")))
    assert results["create"] is not None
    with store.read() as unit:
        policy = unit.tasks.policy("home")
        assert policy.revision == 1 and policy.rules.claim_allowed is (results["policy"] is None)
        assert len(unit.tasks.definitions("home")) == len(unit.tasks.occurrences("home")) == 1
        assert (
            len(unit.audit.entries("home"))
            == len(unit.outbox.pending())
            == (2 if results["policy"] is None else 3)
        )
