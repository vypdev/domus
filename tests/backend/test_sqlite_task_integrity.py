"""Owned schema-5 files retain actual task snapshots and reject nonlocal corruption."""

from dataclasses import dataclass, replace
from pathlib import Path

import pytest
from test_household_commands import fixture
from test_sqlite_snapshots import Clock
from test_tasks import definition

from domus.application.authorization import HouseholdAccess, MembershipAuthorization
from domus.application.commands import AtomicCommands, Change
from domus.application.household_commands import SetupHousehold
from domus.domain.errors import DatabaseRejected, DomusError
from domus.domain.identity import Member, MemberStatus, Permission, Role
from domus.domain.storage import CommandKey, JsonDocument
from domus.domain.task_values import (
    OccurrenceState,
    TaskContent,
    TaskPerformer,
    TaskRequirement,
    TaskRules,
    VerificationState,
)
from domus.domain.tasks import HouseholdTaskPolicy, TaskCycle
from domus.infrastructure.sqlite import SQLiteDatabase
from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots
from domus.infrastructure.sqlite_task_integrity import verify_task_records
from domus.infrastructure.sqlite_task_records import cycle_document, occurrence_document


@dataclass
class FixedClock:
    value: int

    def now(self) -> int:
        return self.value


def task_command(store, actor, identifiers, action, permission, key, payload, apply, now):
    # HA proof is a labeled fixture; real authorization and atomic storage still execute.
    authority = MembershipAuthorization(HouseholdAccess(actor.human), action, permission)
    commands = AtomicCommands(store, authority, FixedClock(now), identifiers)
    return commands.execute(CommandKey("home", actor.human.ha_user_id, action, key), payload, apply)


def populated(tmp_path: Path, *, materials=()):
    tmp_path.mkdir(mode=0o700, exist_ok=True)
    commands, store, actor, _, identifiers = fixture(tmp_path / "domus.sqlite3")
    commands.setup("setup", SetupHousehold("Home", "UTC"))
    with store.write() as unit:
        for name, role in [("child", Role.RESTRICTED), ("other", Role.ADULT)]:
            unit.members.save(Member(name, "home", "ha_" + name, role, MemberStatus.ACTIVE, 1), 0)
    item = definition(created_at=110, materials=materials)
    work = item.new_occurrence("occurrence", 120)
    payload = JsonDocument.from_value({"title": item.content.title, "expected_revision": 0})

    def apply(unit):
        unit.tasks.save_policy(HouseholdTaskPolicy("home", TaskRules()), 0)
        unit.tasks.save_definition(item, 0)
        unit.tasks.save_occurrence(work, 0)
        facts = JsonDocument.from_value(
            {
                "definition_id": item.definition_id,
                "occurrence_id": work.occurrence_id,
                "revision": 1,
            }
        )
        return Change(facts, facts, facts)

    task_command(
        store,
        actor,
        identifiers,
        "task.create",
        Permission.TASKS_CREATE,
        "create",
        payload,
        apply,
        120,
    )
    return store, actor, identifiers, work


def perform(store, actor, identifiers, work):
    payload = JsonDocument.from_value(
        {
            "occurrence_id": work.occurrence_id,
            "expected_revision": work.revision,
            "performer_ids": ["child"],
            "performed_at": 130,
        }
    )

    def apply(unit):
        member = unit.members.by_user("home", actor.human.ha_user_id)
        current = unit.tasks.occurrence("home", work.occurrence_id)
        rules = current.definition_snapshot.overrides.resolve(unit.tasks.policy("home").rules)
        saved = TaskCycle.record(
            "cycle",
            "home",
            work.occurrence_id,
            recorded_by=member.member_id,
            performers=(TaskPerformer("child", Role.RESTRICTED),),
            rules=rules,
            definition_revision=current.definition_snapshot.revision,
            task_policy_revision=1,
            identity_policy_revision=unit.policies.get("home").revision,
            performed_at=130,
            recorded_at=140,
        )
        done = current.complete(saved, requirements=())
        unit.tasks.save_cycle(saved, 0)
        unit.tasks.save_occurrence(done, current.revision)
        facts = JsonDocument.from_value(
            {
                "occurrence_id": done.occurrence_id,
                "cycle_id": saved.cycle_id,
                "revision": done.revision,
                "verification": saved.verification.value,
            }
        )
        return Change(facts, facts, facts)

    receipt = task_command(
        store,
        actor,
        identifiers,
        "task.complete",
        Permission.TASKS_COMPLETE,
        "complete",
        payload,
        apply,
        140,
    )
    with store.read() as unit:
        return (
            unit.tasks.occurrence("home", work.occurrence_id),
            unit.tasks.cycle("home", "cycle"),
            receipt,
            payload,
        )


def validate(store):
    with store.read() as unit:
        members, policy = unit.members.list("home"), unit.policies.get("home")
    with store._connection() as connection:
        verify_task_records(connection, "home", members, policy)


def test_actual_unit_snapshot_and_reopen_keep_task_cycles_and_one_atomic_receipt_set(
    tmp_path: Path,
) -> None:
    store, actor, identifiers, work = populated(tmp_path)
    completed, saved, receipt, _ = perform(store, actor, identifiers, work)
    validate(store)
    before = store.path.read_bytes()
    snapshots = SQLiteSnapshots(store, tmp_path / "snapshot", store.installation, Clock())
    checkpoint = snapshots.create("tasks")
    assert checkpoint.schema_version == 6 and snapshots.inspect() == checkpoint
    assert store.path.read_bytes() == before
    copy = SQLiteDatabase(tmp_path / "snapshot/domus.sqlite3", store.installation)
    with copy.read() as unit:
        assert unit.tasks.occurrence("home", work.occurrence_id) == completed
        assert unit.tasks.cycle("home", "cycle") == saved
        assert (
            unit.receipts.get_operation("home", actor.human.ha_user_id, receipt.operation_id)
            == receipt
        )
        assert len(unit.audit.entries("home")) == len(unit.outbox.pending()) == 3


def test_old_definition_and_pending_policy_snapshots_remain_valid_after_current_policy_edits(
    tmp_path: Path,
) -> None:
    store, actor, identifiers, work = populated(tmp_path)
    completed, saved, _, _ = perform(store, actor, identifiers, work)
    with store.write() as unit:
        original = unit.tasks.definition("home", "definition")
        unit.tasks.save_definition(
            original.revise(TaskContent("Future title"), original.overrides, original.state), 1
        )
        policy = unit.tasks.policy("home")
        unit.tasks.save_policy(
            policy.revise(replace(policy.rules, adult_performer_may_approve=False)), 1
        )
        child = unit.members.get("home", "child")
        unit.members.save(
            replace(child, role=Role.VIEWER, status=MemberStatus.ARCHIVED, revision=2), 1
        )
    validate(store)
    with store.read() as unit:
        assert unit.tasks.occurrence("home", work.occurrence_id) == completed
        assert unit.tasks.cycle("home", "cycle") == saved
    assert (
        saved.rules.adult_performer_may_approve and saved.verification is VerificationState.PENDING
    )


@pytest.mark.parametrize(
    "corruption",
    [
        "policy_missing",
        "identity_missing",
        "members_missing",
        "definition_missing",
        "snapshot_time",
        "snapshot_future",
        "snapshot_changed",
        "assignee_missing",
        "dependency_missing",
        "cycle_missing",
        "cycle_closed",
        "cycle_revision",
        "cycle_definition",
        "cycle_time",
        "task_policy_future",
        "identity_policy_future",
        "recorder_missing",
        "performer_missing",
        "verifier_missing",
        "occurrence_missing",
        "open_unreferenced",
    ],
)
def test_corrupt_task_files_fail_semantic_validation_and_snapshot_admission(
    tmp_path: Path, corruption: str
) -> None:
    store, actor, identifiers, work = populated(tmp_path)
    completed, saved, _, _ = perform(store, actor, identifiers, work)
    if corruption == "verifier_missing":
        with store.write() as unit:
            completed, saved = completed.verify(
                saved,
                VerificationState.APPROVED,
                TaskPerformer("identity-1", Role.ADMINISTRATOR),
                150,
            )
            unit.tasks.save_cycle(saved, 1)
            unit.tasks.save_occurrence(completed, 2)
    with store._connection() as connection:
        if corruption in (
            "policy_missing",
            "identity_missing",
            "members_missing",
            "definition_missing",
            "cycle_missing",
            "occurrence_missing",
        ):
            table = {
                "policy_missing": "task_policy",
                "identity_missing": "household_policy",
                "members_missing": "members",
                "definition_missing": "task_definitions",
                "cycle_missing": "task_cycles",
                "occurrence_missing": "task_occurrences",
            }[corruption]
            connection.execute("DELETE FROM " + table)
        elif corruption.startswith("snapshot_"):
            snapshot = completed.definition_snapshot
            if corruption == "snapshot_time":
                snapshot = replace(snapshot, created_at=111)
            elif corruption == "snapshot_future":
                snapshot = replace(snapshot, revision=2)
            else:
                snapshot = replace(snapshot, content=TaskContent("Forged same revision"))
            changed = replace(completed, definition_snapshot=snapshot)
            connection.execute(
                "UPDATE task_occurrences SET document=?", (occurrence_document(changed).encoded,)
            )
        elif corruption in ("assignee_missing", "dependency_missing", "open_unreferenced"):
            changed = (
                replace(completed, assignee_ids=("missing",))
                if corruption == "assignee_missing"
                else (
                    replace(completed, prerequisite_ids=("missing",))
                    if corruption == "dependency_missing"
                    else replace(
                        completed,
                        state=OccurrenceState.AVAILABLE,
                        current_cycle_id=None,
                        current_cycle_revision=None,
                    )
                )
            )
            connection.execute(
                "UPDATE task_occurrences SET state=?,current_cycle_id=?,"
                "current_cycle_revision=?,document=?",
                (
                    changed.state.value,
                    changed.current_cycle_id,
                    changed.current_cycle_revision,
                    occurrence_document(changed).encoded,
                ),
            )
        else:
            changes = {
                "cycle_closed": {"closed_at": 200},
                "cycle_revision": {"revision": 2},
                "cycle_definition": {"definition_revision": 2},
                "cycle_time": {"recorded_at": 115, "performed_at": 114},
                "task_policy_future": {"task_policy_revision": 2},
                "identity_policy_future": {"identity_policy_revision": 2},
                "recorder_missing": {"recorded_by": "missing"},
                "performer_missing": {"performers": (TaskPerformer("missing", Role.RESTRICTED),)},
                "verifier_missing": {"verified_by": TaskPerformer("missing", Role.ADULT)},
            }[corruption]
            changed = replace(saved, **changes)
            connection.execute(
                "UPDATE task_cycles SET revision=?,closed_at=?,active_occurrence_id=?,"
                "recorded_by=?,verified_by=?,document=?",
                (
                    changed.revision,
                    changed.closed_at,
                    changed.occurrence_id if changed.closed_at is None else None,
                    changed.recorded_by,
                    None if changed.verified_by is None else changed.verified_by.member_id,
                    cycle_document(changed).encoded,
                ),
            )
    before = store.path.read_bytes()
    with pytest.raises(DomusError):
        validate(store)
    with pytest.raises(DatabaseRejected):
        SQLiteSnapshots(store, tmp_path / "bad-snapshot", store.installation, Clock()).create("bad")
    assert not (tmp_path / "bad-snapshot/manifest.json").exists()
    assert store.path.read_bytes() == before


def test_dependency_cycles_are_rejected_but_completed_work_survives_a_reopened_prerequisite(
    tmp_path: Path,
) -> None:
    store, _, _, work = populated(tmp_path)
    prerequisite = work.definition_snapshot.new_occurrence("prerequisite", 120)
    prior = TaskCycle.record(
        "prior-cycle",
        "home",
        "prerequisite",
        recorded_by="identity-1",
        performers=(TaskPerformer("identity-1", Role.ADMINISTRATOR),),
        rules=TaskRules(),
        definition_revision=1,
        task_policy_revision=1,
        identity_policy_revision=1,
        performed_at=130,
        recorded_at=140,
    )
    prerequisite_done = prerequisite.complete(prior, requirements=())
    actual = TaskCycle.record(
        "dependent-cycle",
        "home",
        work.occurrence_id,
        recorded_by="identity-1",
        performers=(TaskPerformer("child", Role.RESTRICTED),),
        rules=TaskRules(),
        definition_revision=1,
        task_policy_revision=1,
        identity_policy_revision=1,
        performed_at=150,
        recorded_at=160,
    )
    with store.write() as unit:
        unit.tasks.save_occurrence(prerequisite, 0)
        unit.tasks.save_cycle(prior, 0)
        unit.tasks.save_occurrence(prerequisite_done, 1)
        dependent = replace(work, prerequisite_ids=("prerequisite",), revision=2)
        unit.tasks.save_occurrence(dependent, 1)
        performed = dependent.complete(
            actual,
            requirements=(
                TaskRequirement("prerequisite", OccurrenceState.COMPLETED, VerificationState.NONE),
            ),
        )
        unit.tasks.save_cycle(actual, 0)
        unit.tasks.save_occurrence(performed, 2)
        reopened, closed = prerequisite_done.reopen(prior, 170, "Review prerequisite")
        unit.tasks.save_cycle(closed, 1)
        unit.tasks.save_occurrence(reopened, 2)
    # Current prerequisite state cannot erase completed dependent work or its cycle snapshot.
    validate(store)
    with store.read() as unit:
        assert unit.tasks.occurrence("home", "occurrence") == performed
        assert unit.tasks.cycle("home", "dependent-cycle") == actual
    SQLiteSnapshots(store, tmp_path / "snapshot", store.installation, Clock()).create("reopened")
    with store.write() as unit:
        unit.tasks.save_occurrence(
            replace(reopened, prerequisite_ids=("occurrence",), revision=4), 3
        )
    with pytest.raises(DomusError):
        validate(store)


def test_integrity_checks_beyond_the_first_bounded_page(tmp_path: Path) -> None:
    store, _, _, _ = populated(tmp_path)
    with store.write() as unit:
        for index in range(103):
            unit.tasks.save_definition(definition(definition_id=f"z{index:03}", created_at=110), 0)
    validate(store)
    with store._connection() as connection:
        connection.execute("UPDATE task_definitions SET document='{}' WHERE definition_id='z102'")
    with pytest.raises(DomusError):
        validate(store)


def test_schema4_upgrade_failure_preserves_the_exact_old_database_and_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sqlite3
    from contextlib import closing

    from domus.domain.errors import DatabaseRejected, StorageFailure
    from domus.domain.storage import Installation
    from domus.infrastructure import sqlite as adapter

    frozen = Path(__file__).resolve().parents[1] / "fixtures/sqlite/v4.sql"
    path = tmp_path / "schema4.sqlite3"
    with closing(sqlite3.connect(path, autocommit=True)) as connection:
        connection.executescript(frozen.read_text())
    before = path.read_bytes()
    store = SQLiteDatabase(path, Installation("047cc6fb-dfb0-4fa4-b3c3-e0fe54d116b6", "edge"))
    with pytest.raises(DatabaseRejected):
        with store.read():
            pytest.fail("Schema 4 must require explicit migration")
    with monkeypatch.context() as patch:
        patch.setattr(adapter, "TASK_STATEMENTS", (*adapter.TASK_STATEMENTS, "INVALID SQL"))
        with pytest.raises(StorageFailure):
            store.initialize()
    assert path.read_bytes() == before
    store.initialize()
    store.initialize()
    with store.read() as unit:
        assert unit.tasks.policy("home") is None and unit.tasks.definitions("home") == ()
        assert unit.receipts.get_operation("home", "human", "operation-a").historical
    with store._connection() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 6
        assert connection.execute("SELECT count(*) FROM retained_operations").fetchone()[0] == 2
