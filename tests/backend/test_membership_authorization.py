"""Concrete local authority is reread before an old receipt or a new mutation."""

import sqlite3
from contextlib import closing
from dataclasses import replace
from pathlib import Path

import pytest

from domus.application.authorization import HouseholdAccess, MembershipAuthorization
from domus.application.commands import AtomicCommands, Change
from domus.application.ports import UnitOfWork
from domus.domain.errors import Forbidden
from domus.domain.identity import (
    AdministratorMapping,
    HouseholdPolicy,
    HumanIdentity,
    MappingMode,
    Member,
    MemberStatus,
    Permission,
    Role,
)
from domus.domain.storage import CommandKey, Household, Installation, JsonDocument
from domus.infrastructure.sqlite import SQLiteDatabase


class Clock:
    def now(self) -> int:
        return 100


class Identifiers:
    def new(self) -> str:
        return "rename-operation"


def store_at(path: Path, *, explicit_admin: bool = False) -> SQLiteDatabase:
    store = SQLiteDatabase(path, Installation("047cc6fb-dfb0-4fa4-b3c3-e0fe54d116b6", "edge"))
    store.initialize()
    with store.write() as unit:
        unit.households.save(Household("home", "Before", "UTC", 1), 0)
        unit.policies.save(HouseholdPolicy("home", AdministratorMapping(MappingMode.ALL), 1), 0)
        unit.members.save(
            Member(
                "member_1",
                "home",
                "ha_1",
                Role.ADMINISTRATOR if explicit_admin else Role.VIEWER,
                MemberStatus.ACTIVE,
                1,
            ),
            0,
        )
    return store


def authority(*, ha_admin: bool = True) -> MembershipAuthorization:
    return MembershipAuthorization(
        HouseholdAccess(HumanIdentity("ha_1", ha_admin, True, False)),
        "household.rename",
        Permission.HOUSEHOLD_MANAGE,
    )


def rename(unit: UnitOfWork) -> Change:
    unit.households.save(Household("home", "After", "UTC", 2), 1)
    result = JsonDocument.from_value({"revision": 2})
    return Change(result, result, result)


def test_fresh_source_revocation_denies_original_receipt_before_result_disclosure(
    tmp_path: Path,
) -> None:
    store = store_at(tmp_path / "database")
    key = CommandKey("home", "ha_1", "household.rename", "request")
    payload = JsonDocument.from_value({"name": "After"})
    original = AtomicCommands(store, authority(), Clock(), Identifiers()).execute(
        key, payload, rename
    )
    revoked = AtomicCommands(store, authority(ha_admin=False), Clock(), Identifiers())
    with pytest.raises(Forbidden, match="permission_denied"):
        revoked.execute(key, payload, rename)
    with store.read() as unit:
        assert unit.receipts.get(key) == original
        assert unit.households.current().revision == 2
        assert len(unit.audit.entries("home")) == 1
        assert len(unit.outbox.pending()) == 1


def test_independent_explicit_administrator_survives_ha_admin_source_revocation(
    tmp_path: Path,
) -> None:
    store = store_at(tmp_path / "database", explicit_admin=True)
    key = CommandKey("home", "ha_1", "household.rename", "request")
    payload = JsonDocument.from_value({})
    commands = AtomicCommands(store, authority(), Clock(), Identifiers())
    first = commands.execute(key, payload, rename)
    assert (
        AtomicCommands(store, authority(ha_admin=False), Clock(), Identifiers()).execute(
            key, payload, rename
        )
        == first
    )


@pytest.mark.parametrize(
    "status", [MemberStatus.PENDING, MemberStatus.SUSPENDED, MemberStatus.ARCHIVED]
)
def test_current_member_state_overrides_existing_authority_and_receipt(
    tmp_path: Path,
    status: MemberStatus,
) -> None:
    store = store_at(tmp_path / "database")
    key = CommandKey("home", "ha_1", "household.rename", "request")
    commands = AtomicCommands(store, authority(), Clock(), Identifiers())
    commands.execute(key, JsonDocument.from_value({}), rename)
    with store.write() as unit:
        unit.members.save(
            replace(unit.members.get("home", "member_1"), status=status, revision=2), 1
        )
    with pytest.raises(Forbidden):
        commands.execute(key, JsonDocument.from_value({}), rename)
    with store.read() as unit:
        with pytest.raises(Forbidden):
            authority().access.require(unit, "home", Permission.HOUSEHOLD_READ)


def test_mapping_revision_is_not_cached_across_commands(tmp_path: Path) -> None:
    store = store_at(tmp_path / "database")
    auth = authority()
    with store.write() as unit:
        auth.require(CommandKey("home", "ha_1", "household.rename", "before"), unit)
        unit.policies.save(
            HouseholdPolicy("home", AdministratorMapping(MappingMode.SELECTED, "ha_2"), 2), 1
        )
    with store.write() as unit:
        with pytest.raises(Forbidden):
            auth.require(CommandKey("home", "ha_1", "household.rename", "after"), unit)


@pytest.mark.parametrize("actor,action", [("ha_2", "household.rename"), ("ha_1", "members.read")])
def test_command_identity_and_action_are_bound_by_server_authority(
    tmp_path: Path,
    actor: str,
    action: str,
) -> None:
    store = store_at(tmp_path / "database")
    with store.write() as unit:
        with pytest.raises(Forbidden):
            authority().require(CommandKey("home", actor, action, "request"), unit)
    with store.read() as unit:
        assert unit.households.current().revision == 1


def test_unlinked_user_missing_policy_and_cross_scope_fail_closed(tmp_path: Path) -> None:
    store = store_at(tmp_path / "database")
    unlinked = HouseholdAccess(HumanIdentity("ha_2", True, True, False))
    with store.read() as unit:
        with pytest.raises(Forbidden):
            unlinked.require(unit, "home", Permission.HOUSEHOLD_READ)
        with pytest.raises(Forbidden):
            authority().access.require(unit, "other", Permission.HOUSEHOLD_READ)
    with closing(sqlite3.connect(store.path, autocommit=True)) as connection:
        connection.execute("DELETE FROM household_policy")
    with store.read() as unit:
        with pytest.raises(Forbidden):
            authority().access.require(unit, "home", Permission.HOUSEHOLD_READ)


def test_authorized_reads_return_resolved_member_and_enforce_private_self_scope(
    tmp_path: Path,
) -> None:
    store = store_at(tmp_path / "database")
    access = authority().access
    with store.read() as unit:
        assert access.require(unit, "home", Permission.HOUSEHOLD_READ).member_id == "member_1"
        assert (
            access.require(
                unit, "home", Permission.PREFERENCES_READ, subject_member_id="member_1"
            ).ha_user_id
            == "ha_1"
        )
        with pytest.raises(Forbidden):
            access.require(unit, "home", Permission.PREFERENCES_READ, subject_member_id="member_2")
