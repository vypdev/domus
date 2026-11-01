"""Real-file repository contracts; this isolated schema fixture is not migration/adoption proof."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

import pytest
from test_tasks import cycle, definition, occurrence, restricted_cycle

from domus.domain.errors import Conflict, InvalidInput, StorageFailure
from domus.domain.identity import Member, MemberStatus, Role
from domus.domain.task_values import (
    DefinitionState,
    OccurrenceState,
    TaskContent,
    TaskPerformer,
    TaskRules,
    VerificationState,
)
from domus.domain.tasks import HouseholdTaskPolicy
from domus.infrastructure.sqlite import BASE_STATEMENTS, IDENTITY_STATEMENTS
from domus.infrastructure.sqlite_identity import SQLiteMembers
from domus.infrastructure.sqlite_task_schema import TASK_STATEMENTS
from domus.infrastructure.sqlite_tasks import SQLiteTasks

type Store = tuple[sqlite3.Connection, SQLiteTasks, Path]


@contextmanager
def transaction(connection: sqlite3.Connection) -> Iterator[SQLiteTasks]:
    connection.execute("BEGIN IMMEDIATE")
    try:
        yield SQLiteTasks(connection)
        connection.execute("COMMIT")
    except BaseException:
        connection.execute("ROLLBACK")
        raise


@pytest.fixture
def store(tmp_path: Path) -> Iterator[Store]:
    path = tmp_path / "tasks.sqlite3"
    connection = sqlite3.connect(path, autocommit=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA trusted_schema=OFF")
    for statement in (*BASE_STATEMENTS, *IDENTITY_STATEMENTS, *TASK_STATEMENTS):
        connection.execute(statement)
    connection.execute(
        "INSERT INTO households(household_id,name,time_zone,revision) "
        "VALUES ('home','Home','UTC',1)"
    )
    members = SQLiteMembers(connection)
    for name, role in [("adult", Role.ADULT), ("child", Role.RESTRICTED), ("other", Role.ADULT)]:
        members.save(Member(name, "home", "ha_" + name, role, MemberStatus.ACTIVE, 1), 0)
    try:
        yield connection, SQLiteTasks(connection), path
    finally:
        connection.close()


@pytest.fixture
def prepared(store: Store) -> Store:
    connection, repository, _ = store
    with transaction(connection):
        repository.save_policy(HouseholdTaskPolicy("home", TaskRules()), 0)
        repository.save_definition(definition(), 0)
        repository.save_occurrence(occurrence(), 0)
    return store


def test_missing_and_wrong_household_records_are_absent_without_cross_scope_fallback(
    store: Store,
) -> None:
    _, repository, _ = store
    for household in ("home", "other"):
        assert repository.policy(household) is None
        assert repository.definition(household, "definition") is None
        assert repository.occurrence(household, "occurrence") is None
        assert repository.cycle(household, "cycle") is None
        assert repository.definitions(household) == repository.occurrences(household) == ()
        assert repository.cycles(household, "occurrence") == ()


def test_committed_policy_definition_and_occurrence_survive_reopening_the_file(
    prepared: Store,
) -> None:
    _, _, path = prepared
    connection = sqlite3.connect(path, autocommit=True)
    connection.row_factory = sqlite3.Row
    try:
        repository = SQLiteTasks(connection)
        assert repository.policy("home") == HouseholdTaskPolicy("home", TaskRules())
        assert repository.definition("home", "definition") == definition()
        assert repository.occurrence("home", "occurrence") == occurrence()
        assert repository.definition("other", "definition") is None
    finally:
        connection.close()


def test_all_command_parts_roll_back_together_without_repository_owned_commits(
    store: Store,
) -> None:
    connection, repository, _ = store
    with pytest.raises(RuntimeError, match="injected"):
        with transaction(connection):
            repository.save_policy(HouseholdTaskPolicy("home", TaskRules()), 0)
            repository.save_definition(definition(), 0)
            repository.save_occurrence(occurrence(), 0)
            raise RuntimeError("injected")
    assert repository.policy("home") is None and repository.definitions("home") == ()
    assert repository.occurrences("home") == ()


def test_expected_revisions_and_creation_identity_prevent_stale_or_silent_overwrite(
    prepared: Store,
) -> None:
    connection, repository, _ = prepared
    policy = HouseholdTaskPolicy("home", TaskRules()).revise(
        replace(TaskRules(), claim_allowed=False)
    )
    renamed = definition().revise(
        TaskContent("Renamed"), definition().overrides, DefinitionState.ACTIVE
    )
    assigned = occurrence().assign(("child",))
    with transaction(connection):
        repository.save_policy(policy, 1)
        repository.save_definition(renamed, 1)
        repository.save_occurrence(assigned, 1)
    assert repository.definition("home", "definition") == renamed
    assert repository.occurrence("home", "occurrence") == assigned
    for save, value in [
        (repository.save_policy, policy),
        (repository.save_definition, renamed),
        (repository.save_occurrence, assigned),
    ]:
        with pytest.raises(Conflict):
            save(value, 1)
        with pytest.raises(Conflict):
            save(value, 0)
        with pytest.raises(InvalidInput):
            save(value, True)
    with pytest.raises(Conflict, match="task_identity_conflict"):
        repository.save_definition(replace(renamed, created_at=11, revision=3), 2)
    with pytest.raises(Conflict, match="task_identity_conflict"):
        repository.save_occurrence(replace(assigned, definition_snapshot=renamed, revision=3), 2)
    with pytest.raises(Conflict):
        repository.save_definition(replace(renamed, definition_id="missing", revision=3), 2)


def test_duplicate_initial_records_and_revision_skips_are_conflicts(prepared: Store) -> None:
    _, repository, _ = prepared
    for save, value in [
        (repository.save_policy, HouseholdTaskPolicy("home", TaskRules())),
        (repository.save_definition, definition()),
        (repository.save_occurrence, occurrence()),
    ]:
        with pytest.raises(Conflict, match="task_record_conflict"):
            save(value, 0)
        with pytest.raises(Conflict, match="revision_conflict"):
            save(value, 3)
        for expected in [-1, 2**63, 0.0]:
            with pytest.raises(InvalidInput):
                save(value, expected)


def test_definition_occurrence_and_cycle_lists_use_bounded_exact_keysets(prepared: Store) -> None:
    connection, repository, _ = prepared
    with transaction(connection):
        repository.save_definition(
            replace(definition(), definition_id="definition_z", state=DefinitionState.DRAFT), 0
        )
        repository.save_occurrence(
            definition().new_occurrence("occurrence_z", 20, assignees=("child",)), 0
        )
    assert [d.definition_id for d in repository.definitions("home", limit=1)] == ["definition"]
    assert [
        d.definition_id
        for d in repository.definitions("home", after="definition", state=DefinitionState.DRAFT)
    ] == ["definition_z"]
    assert repository.definitions("home", after="definition_z") == ()
    assert [
        o.occurrence_id
        for o in repository.occurrences(
            "home", state=OccurrenceState.ASSIGNED, definition_id="definition", assignee_id="child"
        )
    ] == ["occurrence_z"]
    assert [o.occurrence_id for o in repository.occurrences("home", limit=1)] == ["occurrence"]
    assert [o.occurrence_id for o in repository.occurrences("home", after="occurrence")] == [
        "occurrence_z"
    ]
    assert repository.occurrences("home", assignee_id="other") == ()
    for query in (repository.definitions, repository.occurrences):
        assert query("home", limit=101)
        for bad in [0, 102, True, 1.5]:
            with pytest.raises(InvalidInput):
                query("home", limit=bad)
        with pytest.raises(InvalidInput):
            query("home", state="available")
        with pytest.raises(InvalidInput):
            query("home", after="bad/id")
    with pytest.raises(InvalidInput):
        repository.occurrences("home", assignee_id="member' OR 1=1")


def test_cycle_and_current_pointer_commit_atomically_through_approval_reopen_and_new_work(
    prepared: Store,
) -> None:
    connection, repository, _ = prepared
    original = restricted_cycle()
    completed = occurrence().complete(original, requirements=())
    with transaction(connection):
        repository.save_cycle(original, 0)
        repository.save_occurrence(completed, 1)
    approved_work, approved = completed.verify(
        original, VerificationState.APPROVED, TaskPerformer("adult", Role.ADULT), 50
    )
    with transaction(connection):
        repository.save_cycle(approved, 1)
        repository.save_occurrence(approved_work, 2)
    reopened, closed = approved_work.reopen(approved, 60, "Repeat")
    second = replace(original, cycle_id="cycle_z", performed_at=70, recorded_at=80)
    again = reopened.complete(second, requirements=())
    with transaction(connection):
        repository.save_cycle(closed, 2)
        repository.save_occurrence(reopened, 3)
        repository.save_cycle(second, 0)
        repository.save_occurrence(again, 4)
    assert repository.cycle("home", "cycle") == closed
    assert repository.cycle("home", "cycle_z") == second
    assert repository.occurrence("home", "occurrence") == again
    assert repository.cycles("home", "occurrence") == (closed, second)
    assert repository.cycles("home", "occurrence", after="cycle", limit=1) == (second,)
    assert repository.cycles("other", "occurrence") == ()
    with pytest.raises(Conflict):
        repository.save_cycle(replace(closed, closed_at=None, revision=4), 3)
    with pytest.raises(Conflict):
        repository.save_cycle(replace(closed, verified_at=51, revision=4), 3)
    with pytest.raises(Conflict):
        repository.save_cycle(replace(second, performed_at=71, revision=2), 1)


def test_deferred_foreign_keys_reject_an_orphan_cycle_or_one_sided_revision_update(
    prepared: Store,
) -> None:
    connection, repository, _ = prepared
    original = restricted_cycle()
    with pytest.raises(sqlite3.IntegrityError):
        with transaction(connection):
            repository.save_cycle(original, 0)
    assert repository.cycle("home", "cycle") is None
    completed = occurrence().complete(original, requirements=())
    with transaction(connection):
        repository.save_cycle(original, 0)
        repository.save_occurrence(completed, 1)
    _, approved = completed.verify(
        original, VerificationState.APPROVED, TaskPerformer("adult", Role.ADULT), 50
    )
    with pytest.raises(sqlite3.IntegrityError):
        with transaction(connection):
            repository.save_cycle(approved, 1)
    assert repository.cycle("home", "cycle") == original


def test_foreign_policy_and_member_references_cannot_be_inserted(prepared: Store) -> None:
    _, repository, _ = prepared
    with pytest.raises(Conflict):
        repository.save_policy(HouseholdTaskPolicy("other", TaskRules()), 0)
    with pytest.raises(Conflict):
        repository.save_definition(definition(household_id="other"), 0)
    with pytest.raises(Conflict):
        repository.save_cycle(replace(cycle(), recorded_by="missing"), 0)


def test_stored_body_and_index_headers_must_describe_the_same_record(prepared: Store) -> None:
    connection, repository, _ = prepared
    connection.execute("UPDATE task_definitions SET state='paused'")
    with pytest.raises(StorageFailure, match="invalid_task_record"):
        repository.definition("home", "definition")
    connection.execute("UPDATE task_occurrences SET document='{}'")
    with pytest.raises(StorageFailure):
        repository.occurrence("home", "occurrence")


def test_closed_cycle_cannot_remain_the_current_completed_pointer(prepared: Store) -> None:
    connection, repository, _ = prepared
    original = restricted_cycle()
    done = occurrence().complete(original, requirements=())
    with transaction(connection):
        repository.save_cycle(original, 0)
        repository.save_occurrence(done, 1)
    closed = original.close(50)
    with pytest.raises(sqlite3.IntegrityError):
        with transaction(connection):
            repository.save_cycle(closed, 1)
            repository.save_occurrence(replace(done, current_cycle_revision=2, revision=3), 2)
    assert repository.cycle("home", "cycle") == original
    assert repository.occurrence("home", "occurrence") == done
    with pytest.raises(Conflict):
        with transaction(connection):
            repository.save_cycle(replace(original, cycle_id="another"), 0)


@pytest.mark.parametrize(
    "update",
    [
        "revision=0",
        "revision=1.5",
        "state='future'",
        "occurrence_id=NULL",
        "current_cycle_id='missing'",
    ],
)
def test_database_constraints_reject_invalid_structural_headers(
    prepared: Store, update: str
) -> None:
    connection, repository, _ = prepared
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute("UPDATE task_occurrences SET " + update)
    assert repository.occurrence("home", "occurrence") == occurrence()


def test_index_header_type_corruption_is_not_equal_to_a_valid_integer(prepared: Store) -> None:
    connection, repository, _ = prepared
    connection.execute("PRAGMA ignore_check_constraints=ON")
    connection.execute("UPDATE task_occurrences SET revision=1.5")
    with pytest.raises(StorageFailure):
        repository.occurrence("home", "occurrence")
