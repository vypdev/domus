"""Real-file membership/policy contracts and upgrades preserve committed replay evidence."""

import sqlite3
from contextlib import closing
from dataclasses import replace
from pathlib import Path

import pytest

from domus.domain.errors import Conflict, DatabaseRejected, StorageFailure
from domus.domain.identity import (
    AdministratorMapping,
    HouseholdPolicy,
    MappingMode,
    Member,
    MemberStatus,
    Permission,
    PermissionRule,
    ProfileRule,
    Role,
)
from domus.domain.storage import CommandKey, Household, Installation
from domus.infrastructure.sqlite import SQLiteDatabase

IDENTITY = Installation("047cc6fb-dfb0-4fa4-b3c3-e0fe54d116b6", "edge")
V1 = Path(__file__).resolve().parents[1] / "fixtures/sqlite/v1.sql"


def old_database(path: Path) -> None:
    with closing(sqlite3.connect(path, autocommit=True)) as connection:
        connection.executescript(V1.read_text())


def store_at(path: Path) -> SQLiteDatabase:
    store = SQLiteDatabase(path, IDENTITY)
    store.initialize()
    with store.write() as unit:
        unit.households.save(Household("home", "Home", "UTC", 1), 0)
    return store


def member() -> Member:
    return Member(
        "member_1",
        "home",
        "ha_1",
        Role.ADULT,
        MemberStatus.ACTIVE,
        1,
        (PermissionRule(Permission.TASKS_CREATE, False),),
    )


def policy() -> HouseholdPolicy:
    return HouseholdPolicy(
        "home",
        AdministratorMapping(MappingMode.SELECTED, "ha_1"),
        1,
        (ProfileRule(Role.VIEWER, Permission.TASKS_CREATE, True),),
    )


def test_members_and_policy_round_trip_with_no_credential_fields(tmp_path: Path) -> None:
    path = tmp_path / "database"
    store = store_at(path)
    with store.read() as unit:
        assert unit.members.get("home", "missing") is None
        assert unit.members.by_user("home", "missing") is None
        assert unit.members.list("home") == ()
        assert unit.policies.get("home") is None
    with store.write() as unit:
        unit.members.save(member(), 0)
        unit.policies.save(policy(), 0)
    restarted = SQLiteDatabase(path, IDENTITY)
    restarted.initialize()
    with restarted.read() as unit:
        assert unit.members.get("home", "member_1") == member()
        assert unit.members.by_user("home", "ha_1") == member()
        assert unit.members.list("home") == (member(),)
        assert unit.policies.get("home") == policy()
        assert unit.members.get("other", "member_1") is None
        assert unit.members.by_user("other", "ha_1") is None
        assert unit.members.list("other") == ()
        assert unit.policies.get("other") is None


def test_unique_ha_link_is_retained_even_after_archival(tmp_path: Path) -> None:
    store = store_at(tmp_path / "database")
    with store.write() as unit:
        unit.members.save(replace(member(), status=MemberStatus.ARCHIVED), 0)
    for duplicate in (member(), replace(member(), member_id="member_2")):
        with pytest.raises(Conflict, match="member_exists"):
            with store.write() as unit:
                unit.members.save(duplicate, 0)
    with store.read() as unit:
        assert len(unit.members.list("home")) == 1


def test_member_updates_are_scoped_revisioned_and_cannot_relink_history(tmp_path: Path) -> None:
    store = store_at(tmp_path / "database")
    with store.write() as unit:
        unit.members.save(member(), 0)
    changed = replace(member(), role=Role.RESTRICTED, revision=2, exceptions=())
    with store.write() as unit:
        unit.members.save(changed, 1)
    invalid = [
        (member(), 1),
        (changed, 1),
        (replace(changed, revision=4), 2),
        (replace(changed, ha_user_id="different", revision=3), 2),
        (replace(changed, household_id="other", revision=3), 2),
    ]
    for record, revision in invalid:
        with pytest.raises(Conflict, match="revision_conflict"):
            with store.write() as unit:
                unit.members.save(record, revision)
    with store.read() as unit:
        assert unit.members.get("home", "member_1") == changed


def test_policy_cas_duplicate_create_and_clearing_adjustments(tmp_path: Path) -> None:
    store = store_at(tmp_path / "database")
    with store.write() as unit:
        unit.policies.save(policy(), 0)
    with pytest.raises(Conflict, match="policy_exists"):
        with store.write() as unit:
            unit.policies.save(policy(), 0)
    changed = replace(
        policy(), mapping=AdministratorMapping(MappingMode.ALL), revision=2, adjustments=()
    )
    with store.write() as unit:
        unit.policies.save(changed, 1)
    for record, revision in [
        (policy(), 1),
        (changed, 1),
        (replace(changed, revision=4), 2),
        (replace(changed, household_id="other", revision=3), 2),
    ]:
        with pytest.raises(Conflict, match="revision_conflict"):
            with store.write() as unit:
                unit.policies.save(record, revision)
    with store.read() as unit:
        assert unit.policies.get("home") == changed


def test_membership_and_policy_failure_rolls_back_together(tmp_path: Path) -> None:
    store = store_at(tmp_path / "database")
    with pytest.raises(RuntimeError):
        with store.write() as unit:
            unit.members.save(member(), 0)
            unit.policies.save(policy(), 0)
            raise RuntimeError("cancel command")
    with store.read() as unit:
        assert unit.members.list("home") == ()
        assert unit.policies.get("home") is None


def test_v1_upgrade_preserves_household_receipts_audit_and_pending_outbox(tmp_path: Path) -> None:
    path = tmp_path / "database"
    old_database(path)
    store = SQLiteDatabase(path, IDENTITY)
    with pytest.raises(DatabaseRejected, match="unsupported_schema"):
        with store.read():
            pytest.fail("Old schema must be explicitly upgraded at initialization")
    store.initialize()
    store.initialize()
    with store.read() as unit:
        assert unit.households.current() == Household("home", "Existing household", "UTC", 3)
        receipt = unit.receipts.get(CommandKey("home", "ha_1", "household.rename", "old-key"))
        assert receipt.operation_id == "old-operation"
        assert receipt.result.decode() == {"revision": 3}
        assert unit.audit.entries("home")[0].detail.decode() == {"retained": True}
        assert unit.outbox.pending()[0].event_id == "old-operation"
        assert unit.members.list("home") == ()
        assert unit.policies.get("home") is None
    with store.write() as unit:
        unit.members.save(member(), 0)
        unit.policies.save(policy(), 0)
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_failed_v1_upgrade_rolls_back_new_tables_and_keeps_old_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from domus.infrastructure import sqlite as adapter

    path = tmp_path / "database"
    old_database(path)
    before = path.read_bytes()
    with monkeypatch.context() as patch:
        patch.setattr(adapter, "IDENTITY_STATEMENTS", (*adapter.IDENTITY_STATEMENTS, "INVALID SQL"))
        with pytest.raises(StorageFailure):
            SQLiteDatabase(path, IDENTITY).initialize()
    assert path.read_bytes() == before
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        assert (
            connection.execute("SELECT name FROM sqlite_master WHERE name='members'").fetchone()
            is None
        )
        assert (
            connection.execute("SELECT operation_id FROM receipts").fetchone()[0] == "old-operation"
        )
    SQLiteDatabase(path, IDENTITY).initialize()


def test_v1_ownership_is_checked_before_migration_writes(tmp_path: Path) -> None:
    path = tmp_path / "database"
    old_database(path)
    before = path.read_bytes()
    with pytest.raises(DatabaseRejected, match="installation_mismatch"):
        SQLiteDatabase(path, replace(IDENTITY, channel="stable")).initialize()
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "table,column,value",
    [
        ("members", "exceptions", '{"rules":[{"permission":"unknown","allow":true}]}'),
        ("members", "exceptions", '{"rules":[{"permission":"tasks.create","allow":1}]}'),
        ("members", "exceptions", '{"rules":"wrong"}'),
        ("members", "exceptions", '{"rules":[null]}'),
        ("household_policy", "adjustments", '{"rules":[{"role":"unknown"}]}'),
        ("household_policy", "adjustments", "{}"),
    ],
)
def test_invalid_persisted_permission_facts_fail_closed_without_raw_driver_details(
    tmp_path: Path,
    table: str,
    column: str,
    value: str,
) -> None:
    path = tmp_path / "database"
    store = store_at(path)
    with store.write() as unit:
        unit.members.save(member(), 0)
        unit.policies.save(policy(), 0)
    with closing(sqlite3.connect(path, autocommit=True)) as connection:
        connection.execute(f"UPDATE {table} SET {column}=?", (value,))
    with pytest.raises(StorageFailure, match="invalid_identity_record"):
        with store.read() as unit:
            unit.members.list("home") if table == "members" else unit.policies.get("home")
