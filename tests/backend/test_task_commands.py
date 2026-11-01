"""Authorized commands exercise real SQLite transactions; current HA proof is a labeled fake."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier

import pytest
from test_household_commands import Actor, Clock, Identifiers
from test_household_commands import fixture as household_fixture

from domus.application.household_commands import SetupHousehold
from domus.application.task_authorization import TaskAccess, TaskCommandAuthorization
from domus.application.task_commands import (
    AssignTask,
    ClaimTask,
    CreateTask,
    TaskCommands,
)
from domus.domain.errors import (
    Conflict,
    Forbidden,
    IdentityUnavailable,
    InvalidInput,
    StorageFailure,
)
from domus.domain.identity import (
    HumanIdentity,
    Member,
    MemberStatus,
    Permission,
    PermissionRule,
    Role,
)
from domus.domain.storage import CommandKey
from domus.domain.task_values import DefinitionState, OccurrenceState, TaskContent, TaskOverrides
from domus.infrastructure.sqlite import SQLiteDatabase
from domus.infrastructure.sqlite_tasks import SQLiteTasks


def fixture(tmp_path):
    household, store, actor, _, identifiers = household_fixture(tmp_path / "domus.sqlite3")
    household.setup("setup", SetupHousehold("Home", "UTC"))
    with store.write() as unit:
        for member_id in ("child", "other"):
            unit.members.save(
                Member(
                    member_id, "home", "ha_" + member_id, Role.RESTRICTED, MemberStatus.ACTIVE, 1
                ),
                0,
            )
    return TaskCommands(store, actor, Clock(), identifiers), store, actor, identifiers


def resource(receipt):
    value = receipt.result.decode()
    return value["definition_id"], value["occurrence_id"]


def child_commands(store, member_id="child", identifiers=None):
    actor = Actor()
    actor.human = HumanIdentity("ha_" + member_id, False, True, False)
    return TaskCommands(
        store, actor, Clock(), Identifiers() if identifiers is None else identifiers
    ), actor


def counts(store):
    with store.read() as unit:
        return (
            len(unit.tasks.definitions("home")),
            len(unit.tasks.occurrences("home")),
            len(unit.audit.entries("home")),
            len(unit.outbox.pending()),
        )


def test_title_only_creation_commits_default_policy_definition_occurrence_and_one_receipt(tmp_path):
    commands, store, actor, _ = fixture(tmp_path)
    before = actor.calls
    with store.read() as unit:
        assert unit.tasks.policy("home") is None
    receipt = commands.create("create", CreateTask(TaskContent("Wipe table")))
    definition_id, occurrence_id = resource(receipt)
    assert len({definition_id, occurrence_id, receipt.operation_id}) == 3
    assert actor.calls == before + 1 and receipt.command.actor_id == "ha_admin"
    with store.read() as unit:
        item, work = (
            unit.tasks.definition("home", definition_id),
            unit.tasks.occurrence("home", occurrence_id),
        )
        assert item.content.title == "Wipe table" and item.state is DefinitionState.ACTIVE
        assert work.definition_snapshot == item and work.state is OccurrenceState.AVAILABLE
        assert item.created_at == work.created_at == receipt.created_at == 100
        assert unit.tasks.policy("home").revision == 1
        assert unit.receipts.get(receipt.command) == receipt
        assert unit.audit.entries("home")[-1].operation_id == receipt.operation_id
        assert unit.outbox.pending()[-1].event_id == receipt.operation_id
    assert counts(store) == (1, 1, 2, 2)


def test_creation_replay_survives_restart_and_does_not_allocate_more_ids(tmp_path):
    commands, store, actor, identifiers = fixture(tmp_path)
    request = CreateTask(TaskContent("A <script> & @mention", description="Untrusted\ntext"))
    first = commands.create("create", request)
    allocated = identifiers.count
    reopened = SQLiteDatabase(store.path, store.installation)
    again = TaskCommands(reopened, actor, Clock(), identifiers).create("create", request)
    assert again == first and identifiers.count == allocated
    with store.read() as unit:
        item = unit.tasks.definition("home", resource(first)[0])
        assert item.content == request.content
    assert counts(store) == (1, 1, 2, 2)
    with pytest.raises(Conflict, match="idempotency_conflict"):
        commands.create("create", CreateTask(TaskContent("Changed")))


@pytest.mark.parametrize("stage", ["definition", "occurrence"])
def test_failure_between_real_creation_writes_rolls_back_initial_policy_and_all_effects(
    tmp_path, monkeypatch, stage
):
    commands, store, _, _ = fixture(tmp_path)
    name = "save_" + stage
    original = getattr(SQLiteTasks, name)

    def fail(self, value, expected_revision):
        original(self, value, expected_revision)
        raise StorageFailure("injected_task_failure")

    monkeypatch.setattr(SQLiteTasks, name, fail)
    with pytest.raises(StorageFailure):
        commands.create("create", CreateTask(TaskContent("Wipe table")))
    assert counts(store) == (0, 0, 1, 1)
    with store.read() as unit:
        assert unit.tasks.policy("home") is None


def test_draft_creation_and_later_creation_retain_existing_default_revision(tmp_path):
    commands, store, _, _ = fixture(tmp_path)
    first = commands.create("draft", CreateTask(TaskContent("Plan"), state=DefinitionState.DRAFT))
    second = commands.create("active", CreateTask(TaskContent("Work")))
    with store.read() as unit:
        assert unit.tasks.occurrence("home", resource(first)[1]).state is OccurrenceState.DRAFT
        assert unit.tasks.occurrence("home", resource(second)[1]).state is OccurrenceState.AVAILABLE
        assert unit.tasks.policy("home").revision == 1
    assert counts(store) == (2, 2, 3, 3)


@pytest.mark.parametrize(
    "changes",
    [
        {"expected_revision": True},
        {"expected_revision": 1},
        {"expected_revision": -1},
        {"content": "title"},
        {"overrides": {}},
        {"state": "active"},
        {"state": DefinitionState.PAUSED},
        {"state": DefinitionState.ARCHIVED},
    ],
)
def test_create_request_rejects_invalid_typed_input(changes):
    values = {"content": TaskContent("Work"), **changes}
    with pytest.raises(InvalidInput):
        CreateTask(**values)


def test_create_requires_fresh_identity_and_denies_replay_after_source_revocation(tmp_path):
    commands, store, actor, _ = fixture(tmp_path)
    request = CreateTask(TaskContent("Work"))
    commands.create("create", request)
    actor.human = replace(actor.human, is_administrator=False)
    with pytest.raises(Forbidden):
        commands.create("create", request)
    actor.error = IdentityUnavailable("ha_unavailable")
    with pytest.raises(IdentityUnavailable):
        commands.create("other", request)
    assert counts(store) == (1, 1, 2, 2)


def test_rule_overrides_require_administrator_even_if_create_permission_remains(tmp_path):
    commands, store, actor, _ = fixture(tmp_path)
    request = CreateTask(TaskContent("Work"), overrides=TaskOverrides(claim_allowed=False))
    first = commands.create("custom", request)
    with store.write() as unit:
        member = unit.members.by_user("home", "ha_admin")
        unit.members.save(replace(member, role=Role.ADULT, revision=2), 1)
    actor.human = replace(actor.human, is_administrator=False)
    ordinary = commands.create("ordinary", CreateTask(TaskContent("Ordinary")))
    assert resource(ordinary) != resource(first)
    with pytest.raises(Forbidden):
        commands.create("custom", request)
    with pytest.raises(Forbidden):
        commands.create("new-custom", request)
    assert counts(store) == (2, 2, 3, 3)


def test_assignment_and_release_are_current_scoped_revisioned_commands(tmp_path):
    commands, store, _, _ = fixture(tmp_path)
    receipt = commands.create("create", CreateTask(TaskContent("Work")))
    occurrence_id = resource(receipt)[1]
    assignment = AssignTask(occurrence_id, 1, ("child", "other"))
    assigned = commands.assign("assign", assignment)
    assert commands.assign("assign", assignment) == assigned
    with store.read() as unit:
        work = unit.tasks.occurrence("home", occurrence_id)
        assert work.assignee_ids == ("child", "other") and work.revision == 2
    with pytest.raises(Conflict, match="revision_conflict"):
        commands.assign("stale", AssignTask(occurrence_id, 1, ()))
    commands.assign("release", AssignTask(occurrence_id, 2, ()))
    with store.read() as unit:
        work = unit.tasks.occurrence("home", occurrence_id)
        assert work.state is OccurrenceState.AVAILABLE and work.revision == 3
    assert counts(store) == (1, 1, 4, 4)


@pytest.mark.parametrize(
    "status", [None, MemberStatus.PENDING, MemberStatus.SUSPENDED, MemberStatus.ARCHIVED]
)
def test_assignment_never_invents_or_activates_assignees(tmp_path, status):
    commands, store, _, _ = fixture(tmp_path)
    occurrence_id = resource(commands.create("create", CreateTask(TaskContent("Work"))))[1]
    if status is not None:
        with store.write() as unit:
            member = unit.members.get("home", "child")
            unit.members.save(replace(member, status=status, revision=2), 1)
    target = "missing" if status is None else "child"
    with pytest.raises(Forbidden, match="task_assignee_denied"):
        commands.assign("assign", AssignTask(occurrence_id, 1, (target,)))
    assert counts(store) == (1, 1, 2, 2)


def test_restricted_claim_uses_actor_and_replays_after_its_assignment(tmp_path):
    commands, store, _, _ = fixture(tmp_path)
    occurrence_id = resource(commands.create("create", CreateTask(TaskContent("Work"))))[1]
    restricted, _ = child_commands(store)
    request = ClaimTask(occurrence_id, 1)
    result = restricted.claim("claim", request)
    assert restricted.claim("claim", request) == result
    with store.read() as unit:
        work = unit.tasks.occurrence("home", occurrence_id)
        assert work.assignee_ids == ("child",) and work.state is OccurrenceState.ASSIGNED
    with pytest.raises(Forbidden):
        restricted.assign("reassign", AssignTask(occurrence_id, 2, ("other",)))
    with pytest.raises(Conflict):
        restricted.claim("again", ClaimTask(occurrence_id, 2))
    assert counts(store) == (1, 1, 3, 3)


def test_two_real_concurrent_claims_have_one_winner_and_no_reassignment(tmp_path):
    commands, store, _, _ = fixture(tmp_path)
    occurrence_id = resource(commands.create("create", CreateTask(TaskContent("Work"))))[1]
    gate = Barrier(2)

    def claim(member_id):
        service, _ = child_commands(store, member_id)
        gate.wait(timeout=5)
        try:
            return member_id, service.claim("claim", ClaimTask(occurrence_id, 1))
        except Conflict:
            return member_id, None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(claim, ("child", "other")))
    winners = [member_id for member_id, result in results if result is not None]
    assert len(winners) == 1
    with store.read() as unit:
        assert unit.tasks.occurrence("home", occurrence_id).assignee_ids == tuple(winners)
    assert counts(store) == (1, 1, 3, 3)


def test_current_claim_exception_denies_an_original_receipt_and_retains_work(tmp_path):
    commands, store, _, _ = fixture(tmp_path)
    occurrence_id = resource(commands.create("create", CreateTask(TaskContent("Work"))))[1]
    restricted, _ = child_commands(store)
    request = ClaimTask(occurrence_id, 1)
    restricted.claim("claim", request)
    with store.write() as unit:
        person = unit.members.get("home", "child")
        unit.members.save(
            replace(
                person, exceptions=(PermissionRule(Permission.TASKS_CLAIM, False),), revision=2
            ),
            1,
        )
    with pytest.raises(Forbidden):
        restricted.claim("claim", request)
    assert counts(store) == (1, 1, 3, 3)


@pytest.mark.parametrize(
    "changes", [{"household_id": "other"}, {"actor_id": "ha_other"}, {"action": "task.claim"}]
)
def test_server_authority_binds_household_actor_and_action_before_any_receipt(tmp_path, changes):
    _, store, actor, _ = fixture(tmp_path)
    auth = TaskCommandAuthorization(TaskAccess(actor.human), "home", "task.create")
    key = CommandKey(
        **{
            "household_id": "home",
            "actor_id": "ha_admin",
            "action": "task.create",
            "key": "forged",
            **changes,
        }
    )
    with store.write() as unit:
        with pytest.raises(Forbidden):
            auth.require(key, unit)
    assert counts(store) == (0, 0, 1, 1)


@pytest.mark.parametrize(
    "action,occurrence_id",
    [
        ("task.delete", None),
        ("task.assign", None),
        ("task.create", "missing"),
        ("task.assign", "missing"),
        ("task.claim", "missing"),
    ],
)
def test_unknown_actions_missing_scope_and_missing_tasks_are_not_mutation_authority(
    tmp_path, action, occurrence_id
):
    _, store, actor, _ = fixture(tmp_path)
    auth = TaskCommandAuthorization(TaskAccess(actor.human), "home", action, occurrence_id)
    with store.write() as unit:
        with pytest.raises(Forbidden):
            auth.require(CommandKey("home", "ha_admin", action, "forged"), unit)
    assert counts(store) == (0, 0, 1, 1)


@pytest.mark.parametrize(
    "build_request",
    [
        lambda: AssignTask("bad id", 1, ()),
        lambda: AssignTask("occ", True, ()),
        lambda: AssignTask("occ", 0, ()),
        lambda: AssignTask("occ", 1, ["child"]),
        lambda: AssignTask("occ", 1, ("child", "child")),
        lambda: AssignTask("occ", 1, tuple("member-" + str(i) for i in range(33))),
        lambda: ClaimTask("bad id", 1),
        lambda: ClaimTask("occ", 0),
        lambda: ClaimTask("occ", True),
        lambda: ClaimTask("occ", 2**63),
    ],
)
def test_mutation_request_bounds_reject_invalid_ids_revisions_duplicates_and_capacity(
    build_request,
):
    with pytest.raises(InvalidInput):
        build_request()


def test_assignment_accepts_exactly_32_distinct_current_members(tmp_path):
    commands, store, _, _ = fixture(tmp_path)
    occurrence_id = resource(commands.create("create", CreateTask(TaskContent("Work"))))[1]
    names = tuple("person-" + str(i) for i in range(32))
    with store.write() as unit:
        for name in names:
            unit.members.save(
                Member(name, "home", "ha-" + name, Role.ADULT, MemberStatus.ACTIVE, 1), 0
            )
    commands.assign("assign", AssignTask(occurrence_id, 1, names))
    with store.read() as unit:
        assert unit.tasks.occurrence("home", occurrence_id).assignee_ids == names
    assert counts(store) == (1, 1, 3, 3)


def test_claim_replay_never_reassigns_work_released_and_claimed_by_someone_else(tmp_path):
    commands, store, _, identifiers = fixture(tmp_path)
    occurrence_id = resource(commands.create("create", CreateTask(TaskContent("Work"))))[1]
    child, _ = child_commands(store, identifiers=identifiers)
    other, _ = child_commands(store, "other", identifiers)
    first = child.claim("claim", ClaimTask(occurrence_id, 1))
    commands.assign("release", AssignTask(occurrence_id, 2, ()))
    other.claim("claim", ClaimTask(occurrence_id, 3))
    assert child.claim("claim", ClaimTask(occurrence_id, 1)) == first
    with store.read() as unit:
        work = unit.tasks.occurrence("home", occurrence_id)
        assert work.assignee_ids == ("other",) and work.revision == 4
    assert counts(store) == (1, 1, 5, 5)


def test_current_task_rule_denial_prevents_claim_without_erasing_definition(tmp_path):
    commands, store, _, _ = fixture(tmp_path)
    occurrence_id = resource(
        commands.create(
            "create", CreateTask(TaskContent("Work"), overrides=TaskOverrides(claim_allowed=False))
        )
    )[1]
    child, _ = child_commands(store)
    with pytest.raises(Forbidden, match="task_claim_denied"):
        child.claim("claim", ClaimTask(occurrence_id, 1))
    assert counts(store) == (1, 1, 2, 2)


def test_transaction_rechecks_a_member_denial_saved_during_fresh_proof(tmp_path):
    commands, store, actor, _ = fixture(tmp_path)

    class RevokingActor:
        def current(self):
            with store.write() as unit:
                person = unit.members.by_user("home", actor.human.ha_user_id)
                unit.members.save(
                    replace(
                        person,
                        exceptions=(PermissionRule(Permission.TASKS_CREATE, False),),
                        revision=2,
                    ),
                    1,
                )
            return actor.human

    commands.actor = RevokingActor()
    with pytest.raises(Forbidden):
        commands.create("create", CreateTask(TaskContent("Work")))
    assert counts(store) == (0, 0, 1, 1)
