"""Explicit household setup and own enrollment preserve authorization and durable replay."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from threading import Barrier

import pytest

from domus.application.commands import AtomicCommands
from domus.application.household_commands import (
    HouseholdCommands,
    SetupHousehold,
    _InitialAuthority,
)
from domus.domain.errors import Conflict, Forbidden, IdentityUnavailable, InvalidInput, StorageBusy
from domus.domain.identity import HumanIdentity, MappingMode, Member, MemberStatus, Role
from domus.domain.storage import CommandKey, Installation, JsonDocument
from domus.infrastructure.sqlite import SQLiteDatabase


class Actor:
    human = HumanIdentity("ha_admin", True, True, False)
    error = None
    calls = 0

    def current(self) -> HumanIdentity:
        self.calls += 1
        if self.error:
            raise self.error
        return self.human


class Directory:
    def __init__(self) -> None:
        self.people = {"ha_selected": HumanIdentity("ha_selected", False, True, False)}
        self.calls = []
        self.error = None

    def get(self, user_id: str) -> HumanIdentity:
        self.calls.append(user_id)
        if self.error:
            raise self.error
        return self.people[user_id]


class Zones:
    def require(self, time_zone: str) -> None:
        if time_zone not in ("UTC", "Europe/Madrid"):
            raise InvalidInput("invalid_time_zone")


class Clock:
    def now(self) -> int:
        return 100


class Identifiers:
    def __init__(self) -> None:
        self.count = 0

    def new(self) -> str:
        self.count += 1
        return f"identity-{self.count}"


def fixture(path: Path) -> tuple:
    store = SQLiteDatabase(path, Installation("047cc6fb-dfb0-4fa4-b3c3-e0fe54d116b6", "edge"))
    store.initialize()
    actor, directory, identifiers = Actor(), Directory(), Identifiers()
    return (
        HouseholdCommands(store, actor, directory, Zones(), Clock(), identifiers),
        store,
        actor,
        directory,
        identifiers,
    )


def test_setup_is_explicit_and_commits_household_mapping_member_and_evidence(
    tmp_path: Path,
) -> None:
    commands, store, actor, directory, _ = fixture(tmp_path / "database")
    with store.read() as unit:
        assert unit.households.current() is None
    result = commands.setup("create", SetupHousehold("  Our home  ", "Europe/Madrid"))
    assert actor.calls == 1 and directory.calls == []
    assert result.command.actor_id == "ha_admin" and result.created_at == 100
    with store.read() as unit:
        assert unit.households.current().name == "Our home"
        assert unit.households.current().time_zone == "Europe/Madrid"
        assert unit.policies.get("home").mapping.mode is MappingMode.ALL
        member = unit.members.by_user("home", "ha_admin")
        assert member.status is MemberStatus.ACTIVE
        assert member.role is Role.VIEWER  # Administration is inherited, not an independent grant.
        assert result.result.decode()["member_id"] == member.member_id
        assert len(unit.audit.entries("home")) == len(unit.outbox.pending()) == 1
        assert unit.receipts.get(result.command) == result


@pytest.mark.parametrize("mode", [MappingMode.ALL, MappingMode.SETUP, MappingMode.SELECTED])
def test_each_mapping_is_explicit_and_selected_ordinary_human_is_verified(
    tmp_path: Path,
    mode: MappingMode,
) -> None:
    commands, store, _, directory, _ = fixture(tmp_path / "database")
    selected = "ha_selected" if mode is MappingMode.SELECTED else None
    result = commands.setup("create", SetupHousehold("Home", "UTC", mode, selected))
    with store.read() as unit:
        policy = unit.policies.get("home")
        assert policy.mapping.mode is mode
        expected = None if mode is MappingMode.ALL else (selected or "ha_admin")
        assert policy.mapping.target_ha_user_id == expected
        if selected:
            member = unit.members.by_user("home", selected)
            assert member.status is MemberStatus.ACTIVE and member.role is Role.VIEWER
            assert result.result.decode()["administrator_member_id"] == member.member_id
    assert directory.calls == ([selected] if selected else [])


def test_selected_self_uses_fresh_actor_proof_without_an_unrelated_directory_read(
    tmp_path: Path,
) -> None:
    commands, _, _, directory, _ = fixture(tmp_path / "database")
    commands.setup("create", SetupHousehold("Home", "UTC", MappingMode.SELECTED, "ha_admin"))
    assert directory.calls == []


def test_first_arriving_ordinary_user_never_initializes_the_household(tmp_path: Path) -> None:
    commands, store, actor, _, _ = fixture(tmp_path / "database")
    actor.human = HumanIdentity("ha_ordinary", False, True, False)
    with pytest.raises(Forbidden):
        commands.setup("create", SetupHousehold("Home", "UTC"))
    with store.read() as unit:
        assert unit.households.current() is None
        assert unit.outbox.pending() == ()


@pytest.mark.parametrize("failure", ["unavailable", "mismatched"])
def test_unverified_selected_user_cannot_leave_partial_setup(tmp_path: Path, failure: str) -> None:
    commands, store, _, directory, _ = fixture(tmp_path / "database")
    if failure == "unavailable":
        directory.error = IdentityUnavailable("ha_unavailable")
    else:
        directory.people["ha_selected"] = HumanIdentity("other", True, True, False)
    with pytest.raises((IdentityUnavailable, Forbidden)):
        commands.setup("create", SetupHousehold("Home", "UTC", MappingMode.SELECTED, "ha_selected"))
    with store.read() as unit:
        assert unit.households.current() is None and unit.outbox.pending() == ()


def test_authorized_setup_retry_reuses_receipt_after_restart_and_payload_conflicts(
    tmp_path: Path,
) -> None:
    path = tmp_path / "database"
    commands, _, _, _, ids = fixture(path)
    request = SetupHousehold("Home", "UTC")
    original = commands.setup("create", request)
    assert commands.setup("create", request) == original
    assert ids.count == 2
    restarted, _, _, _, fresh_ids = fixture(path)
    assert restarted.setup("create", request) == original and fresh_ids.count == 0
    with pytest.raises(Conflict, match="idempotency_conflict"):
        restarted.setup("create", SetupHousehold("Changed", "UTC"))
    with pytest.raises(Conflict, match="household_exists"):
        restarted.setup("another-key", request)


def test_selected_setup_retry_does_not_require_fresh_target_proof_when_actor_remains_admin(
    tmp_path: Path,
) -> None:
    commands, _, _, directory, _ = fixture(tmp_path / "database")
    request = SetupHousehold("Home", "UTC", MappingMode.SELECTED, "ha_admin")
    first = commands.setup("create", request)
    directory.error = IdentityUnavailable("ha_unavailable")
    assert commands.setup("create", request) == first


def test_setup_retry_after_actor_loses_administration_cannot_disclose_the_old_receipt(
    tmp_path: Path,
) -> None:
    commands, _, actor, _, _ = fixture(tmp_path / "database")
    request = SetupHousehold("Home", "UTC")
    commands.setup("create", request)
    actor.human = replace(actor.human, is_administrator=False)
    with pytest.raises(Forbidden):
        commands.setup("create", request)


def test_own_enrollment_is_pending_and_a_retry_has_one_stable_member(tmp_path: Path) -> None:
    commands, store, actor, _, ids = fixture(tmp_path / "database")
    commands.setup("create", SetupHousehold("Home", "UTC"))
    actor.human = HumanIdentity("ha_ordinary", False, True, False)
    first = commands.enroll("join")
    count = ids.count
    assert commands.enroll("join") == first and ids.count == count
    assert first.command.actor_id == "ha_ordinary"
    assert first.result.decode()["status"] == "pending"
    with store.read() as unit:
        member = unit.members.by_user("home", "ha_ordinary")
        assert member.role is Role.VIEWER and member.status is MemberStatus.PENDING
        assert len(unit.members.list("home")) == 2
        assert len(unit.audit.entries("home")) == len(unit.outbox.pending()) == 2
    with pytest.raises(Conflict, match="member_exists"):
        commands.enroll("different-key")


@pytest.mark.parametrize(
    "mode,expected", [(MappingMode.ALL, "active"), (MappingMode.SETUP, "pending")]
)
def test_ha_admin_activation_exception_applies_only_to_explicit_enrollment_in_default_mapping(
    tmp_path: Path,
    mode: MappingMode,
    expected: str,
) -> None:
    commands, store, actor, _, _ = fixture(tmp_path / "database")
    commands.setup("create", SetupHousehold("Home", "UTC", mode))
    actor.human = HumanIdentity("ha_other_admin", True, True, False)
    with store.read() as unit:
        assert unit.members.by_user("home", "ha_other_admin") is None
    assert commands.enroll("join").result.decode()["status"] == expected


@pytest.mark.parametrize("status", [MemberStatus.SUSPENDED, MemberStatus.ARCHIVED])
def test_inactive_members_cannot_reenroll_or_replay_an_earlier_request(
    tmp_path: Path, status: MemberStatus
) -> None:
    commands, store, actor, _, _ = fixture(tmp_path / "database")
    commands.setup("create", SetupHousehold("Home", "UTC"))
    actor.human = HumanIdentity("ha_ordinary", False, True, False)
    commands.enroll("join")
    with store.write() as unit:
        member = unit.members.by_user("home", "ha_ordinary")
        unit.members.save(replace(member, status=status, revision=2), 1)
    for key in ("join", "new-join"):
        with pytest.raises(Forbidden):
            commands.enroll(key)
    with store.read() as unit:
        assert len(unit.members.list("home")) == 2


def test_enrollment_without_a_configured_household_fails_closed(tmp_path: Path) -> None:
    commands, store, _, _, _ = fixture(tmp_path / "database")
    with pytest.raises(Forbidden):
        commands.enroll("join")
    with store.read() as unit:
        assert unit.households.current() is None


def test_rename_checks_current_authority_and_replays_before_stale_revision(tmp_path: Path) -> None:
    commands, store, actor, _, _ = fixture(tmp_path / "database")
    commands.setup("create", SetupHousehold("Home", "UTC"))
    changed = commands.update("rename", "New name", "Europe/Madrid", 1)
    assert commands.update("rename", "New name", "Europe/Madrid", 1) == changed
    with pytest.raises(Conflict, match="revision_conflict"):
        commands.update("other", "Different", "UTC", 1)
    actor.human = replace(actor.human, is_administrator=False)
    with pytest.raises(Forbidden):
        commands.update("rename", "New name", "Europe/Madrid", 1)
    with store.read() as unit:
        assert unit.households.current().revision == 2
        assert unit.households.current().name == "New name"


def test_fresh_actor_outage_and_invalid_timezone_do_not_mutate_records(tmp_path: Path) -> None:
    commands, store, actor, _, _ = fixture(tmp_path / "database")
    with pytest.raises(InvalidInput, match="invalid_time_zone"):
        commands.setup("create", SetupHousehold("Home", "Not/AZone"))
    actor.error = IdentityUnavailable("ha_unavailable")
    with pytest.raises(IdentityUnavailable):
        commands.setup("create", SetupHousehold("Home", "UTC"))
    with store.read() as unit:
        assert unit.households.current() is None


@pytest.mark.parametrize(
    "values",
    [
        {"mapping_mode": "all_ha_administrators"},
        {"mapping_mode": MappingMode.ALL, "selected_ha_user_id": "ha_selected"},
        {"mapping_mode": MappingMode.SELECTED},
        {"mapping_mode": MappingMode.SELECTED, "selected_ha_user_id": "invalid/id"},
        {"mapping_mode": MappingMode.SETUP, "selected_ha_user_id": "ha_selected"},
        {"expected_revision": True},
        {"expected_revision": -1},
        {"expected_revision": 1},
    ],
)
def test_initial_configuration_rejects_ambiguous_mappings_and_nonzero_revisions(
    values: dict,
) -> None:
    with pytest.raises(InvalidInput):
        SetupHousehold("Home", "UTC", **values)


@pytest.mark.parametrize("value", [True, -1, 1])
def test_enrollment_requires_a_deliberate_initial_revision(tmp_path: Path, value: int) -> None:
    commands, _, _, _, _ = fixture(tmp_path / "database")
    with pytest.raises(InvalidInput, match="invalid_revision"):
        commands.enroll("join", value)


@pytest.mark.parametrize(
    "actor_id,action,authority_action",
    [
        ("outsider", "household.setup", "household.setup"),
        ("ha_admin", "member.enroll", "household.setup"),
        ("ha_admin", "unknown", "unknown"),
    ],
)
def test_setup_authority_cannot_be_reused_for_a_forged_actor_or_action(
    tmp_path: Path,
    actor_id: str,
    action: str,
    authority_action: str,
) -> None:
    _, store, actor, _, identifiers = fixture(tmp_path / "database")
    commands = AtomicCommands(
        store, _InitialAuthority(actor.human, authority_action), Clock(), identifiers
    )

    def forbidden_effect(unit: object) -> None:
        pytest.fail("Forged command context must not reach any effect")

    with pytest.raises(Forbidden):
        commands.execute(
            CommandKey("home", actor_id, action, "forged"),
            JsonDocument.from_value({}),
            forbidden_effect,
        )
    with store.read() as unit:
        assert unit.households.current() is None and unit.outbox.pending() == ()


def test_other_household_scope_and_missing_policy_cannot_admit_enrollment(tmp_path: Path) -> None:
    commands, store, actor, directory, identifiers = fixture(tmp_path / "database")
    commands.setup("create", SetupHousehold("Home", "UTC"))
    cross_scope = HouseholdCommands(store, actor, directory, Zones(), Clock(), identifiers, "other")
    with pytest.raises(Forbidden):
        cross_scope.enroll("join")
    import sqlite3

    with closing(sqlite3.connect(store.path, autocommit=True)) as connection:
        connection.execute("DELETE FROM household_policy")
    with pytest.raises(Forbidden):
        commands.enroll("join")


def test_preparing_a_selected_human_never_holds_the_sqlite_writer_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands, store, _, directory, _ = fixture(tmp_path / "database")
    original = directory.get

    def prove(user_id: str) -> HumanIdentity:
        with store.write() as unit:
            assert unit.households.current() is None
        return original(user_id)

    monkeypatch.setattr(directory, "get", prove)
    commands.setup("create", SetupHousehold("Home", "UTC", MappingMode.SELECTED, "ha_selected"))


def test_authorized_selected_setup_replay_does_not_depend_on_target_directory_availability(
    tmp_path: Path,
) -> None:
    commands, store, _, directory, _ = fixture(tmp_path / "database")
    request = SetupHousehold("Home", "UTC", MappingMode.SELECTED, "ha_selected")
    first = commands.setup("create", request)
    # Fixture an independent explicit grant, separate from the selected-user mapping.
    with store.write() as unit:
        member = unit.members.by_user("home", "ha_admin")
        unit.members.save(replace(member, role=Role.ADMINISTRATOR, revision=2), 1)
    directory.error = IdentityUnavailable("ha_unavailable")
    assert commands.setup("create", request) == first
    assert directory.calls == ["ha_selected"]


def test_selected_member_storage_conflict_rolls_back_every_setup_record(tmp_path: Path) -> None:
    commands, store, _, _, _ = fixture(tmp_path / "database")

    class CollidingIdentifiers:
        def new(self) -> str:
            return "collision"

    commands.identifiers = CollidingIdentifiers()
    request = SetupHousehold("Home", "UTC", MappingMode.SELECTED, "ha_selected")
    with pytest.raises(Conflict, match="member_exists"):
        commands.setup("create", request)
    with store.read() as unit:
        assert unit.households.current() is None
        assert unit.members.list("home") == () and unit.policies.get("home") is None
        assert unit.audit.entries("home") == () and unit.outbox.pending() == ()
    commands.identifiers = Identifiers()
    assert commands.setup("create", request).result.decode()["state"] == "configured"


def test_concurrent_explicit_setup_has_one_complete_winner(tmp_path: Path) -> None:
    _, store, _, _, _ = fixture(tmp_path / "database")
    gate = Barrier(2)

    class ConcurrentZones(Zones):
        def require(self, time_zone: str) -> None:
            super().require(time_zone)
            gate.wait(timeout=3)

    def create(key: str) -> str:
        command = HouseholdCommands(
            store, Actor(), Directory(), ConcurrentZones(), Clock(), Identifiers()
        )
        try:
            command.setup(key, SetupHousehold("Home", "UTC"))
        except Conflict, StorageBusy:
            return "conflict"
        return "configured"

    with ThreadPoolExecutor(max_workers=2) as workers:
        assert sorted(workers.map(create, ("first", "second"))) == ["configured", "conflict"]
    with store.read() as unit:
        assert unit.households.current().revision == 1
        assert len(unit.members.list("home")) == 1
        assert len(unit.audit.entries("home")) == len(unit.outbox.pending()) == 1


def test_enrollment_capacity_preserves_all_existing_actors_without_partial_evidence(
    tmp_path: Path,
) -> None:
    commands, store, actor, _, _ = fixture(tmp_path / "database")
    commands.setup("create", SetupHousehold("Home", "UTC"))
    with store.write() as unit:
        for number in range(255):
            unit.members.save(
                Member(f"m{number}", "home", f"ha_{number}", Role.VIEWER, MemberStatus.PENDING, 1),
                0,
            )
    actor.human = HumanIdentity("ha_new", False, True, False)
    with pytest.raises(Conflict, match="member_capacity"):
        commands.enroll("join")
    with store.read() as unit:
        assert len(unit.members.list("home")) == 256
        assert len(unit.audit.entries("home")) == len(unit.outbox.pending()) == 1


def test_existing_active_member_enrollment_replay_and_invalid_updated_zone_are_safe(
    tmp_path: Path,
) -> None:
    commands, store, actor, _, _ = fixture(tmp_path / "database")
    commands.setup("create", SetupHousehold("Home", "UTC"))
    with pytest.raises(InvalidInput):
        commands.update("invalid", "Home", "Not/AZone", 1)
    actor.human = HumanIdentity("ha_ordinary", False, True, False)
    enrolled = commands.enroll("join")
    with store.write() as unit:
        member = unit.members.by_user("home", "ha_ordinary")
        unit.members.save(replace(member, status=MemberStatus.ACTIVE, revision=2), 1)
    assert commands.enroll("join") == enrolled
