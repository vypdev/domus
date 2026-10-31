"""Policy edits retain mapping provenance, current authority and an eligible administrator."""

from dataclasses import replace
from pathlib import Path

import pytest
from test_member_commands import configured

from domus.application.member_commands import UpdateMember
from domus.application.policy_commands import PolicyCommands, UpdatePolicy
from domus.domain.errors import Conflict, Forbidden, IdentityUnavailable, InvalidInput
from domus.domain.identity import (
    AdministratorMapping,
    HumanIdentity,
    MappingMode,
    MemberStatus,
    Permission,
    ProfileRule,
    Role,
    allows,
)


def policies(tmp_path: Path) -> tuple:
    members, store, actor, directory, member_id = configured(tmp_path)
    commands = PolicyCommands(store, actor, directory, members.clock, members.identifiers)
    return commands, members, store, actor, directory, member_id


def test_profile_adjustments_persist_with_revision_and_one_atomic_command(tmp_path: Path) -> None:
    commands, members, store, _, directory, member_id = policies(tmp_path)
    members.update("activate", UpdateMember(member_id, 1, Role.ADULT, MemberStatus.ACTIVE))
    adjustment = ProfileRule(Role.ADULT, Permission.SHOPPING_MANAGE, False)
    request = UpdatePolicy(1, AdministratorMapping(MappingMode.ALL), (adjustment,))
    receipt = commands.update("policy", request)
    with store.read() as unit:
        policy = unit.policies.get("home")
        member = unit.members.get("home", member_id)
        assert policy.revision == 2 and policy.adjustments == (adjustment,)
        assert not allows(
            directory.people["ha_joiner"], member, policy, Permission.SHOPPING_MANAGE, "home"
        )
        assert member.revision == 2  # Policy changes do not rewrite member records.
        assert unit.receipts.get(receipt.command) == receipt
        assert len(unit.audit.entries("home")) == len(unit.outbox.pending()) == 4
    assert receipt.result.decode() == {
        "household_id": "home",
        "revision": 2,
        "mapping_mode": "all_ha_administrators",
    }


def test_selected_mapping_grants_an_ordinary_active_human_and_revokes_only_inheritance(
    tmp_path: Path,
) -> None:
    commands, members, store, actor, directory, member_id = policies(tmp_path)
    members.update("activate", UpdateMember(member_id, 1, Role.VIEWER, MemberStatus.ACTIVE))
    request = UpdatePolicy(1, AdministratorMapping(MappingMode.SELECTED, "ha_joiner"))
    commands.update("select", request)
    with store.read() as unit:
        policy = unit.policies.get("home")
        original = unit.members.by_user("home", "ha_admin")
        selected = unit.members.get("home", member_id)
        assert not allows(actor.human, original, policy, Permission.POLICY_MANAGE, "home")
        assert allows(
            directory.people["ha_joiner"], selected, policy, Permission.POLICY_MANAGE, "home"
        )
        assert original.role is selected.role is Role.VIEWER
    with pytest.raises(Forbidden):
        commands.update("select", request)
    actor.human = directory.people["ha_joiner"]
    commands.update("all", UpdatePolicy(2, AdministratorMapping(MappingMode.ALL)))
    with store.read() as unit:
        assert not allows(
            actor.human,
            unit.members.get("home", member_id),
            unit.policies.get("home"),
            Permission.POLICY_MANAGE,
            "home",
        )
    assert directory.batch_calls == [("ha_admin",)]


def test_mapping_change_preserves_independently_granted_administrator_profile(
    tmp_path: Path,
) -> None:
    commands, members, store, actor, directory, member_id = policies(tmp_path)
    members.update("explicit", UpdateMember(member_id, 1, Role.ADMINISTRATOR, MemberStatus.ACTIVE))
    commands.update(
        "select", UpdatePolicy(1, AdministratorMapping(MappingMode.SELECTED, "ha_joiner"))
    )
    actor.human = directory.people["ha_joiner"]
    directory.error = IdentityUnavailable("ha_unavailable")
    commands.update("all", UpdatePolicy(2, AdministratorMapping(MappingMode.ALL)))
    with store.read() as unit:
        assert allows(
            actor.human,
            unit.members.get("home", member_id),
            unit.policies.get("home"),
            Permission.POLICY_MANAGE,
            "home",
        )


def test_setup_mapping_is_bound_to_recorded_setup_actor(tmp_path: Path) -> None:
    commands, members, store, _, _, member_id = policies(tmp_path)
    members.update("activate", UpdateMember(member_id, 1, Role.ADULT, MemberStatus.ACTIVE))
    with pytest.raises(InvalidInput, match="setup_administrator_mismatch"):
        commands.update(
            "retarget", UpdatePolicy(1, AdministratorMapping(MappingMode.SETUP, "ha_joiner"))
        )
    commands.update(
        "setup-only", UpdatePolicy(1, AdministratorMapping(MappingMode.SETUP, "ha_admin"))
    )
    with store.read() as unit:
        assert unit.policies.get("home").mapping == AdministratorMapping(
            MappingMode.SETUP, "ha_admin"
        )
        assert unit.audit.setup_actor("home") == "ha_admin"
        assert unit.audit.setup_actor("another-home") is None


@pytest.mark.parametrize("target", ["ha_joiner", "missing"])
def test_selected_mapping_requires_existing_active_linkage_before_directory_lookup(
    tmp_path: Path, target: str
) -> None:
    commands, _, store, _, directory, _ = policies(tmp_path)
    with pytest.raises(Conflict, match="mapping_target_inactive"):
        commands.update(
            "select", UpdatePolicy(1, AdministratorMapping(MappingMode.SELECTED, target))
        )
    assert directory.calls == directory.batch_calls == []
    with store.read() as unit:
        assert unit.policies.get("home").revision == 1
        assert len(unit.audit.entries("home")) == 2


def test_current_source_changes_during_target_proof_block_policy_edit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    commands, members, store, actor, directory, member_id = policies(tmp_path)
    members.update("activate", UpdateMember(member_id, 1, Role.ADULT, MemberStatus.ACTIVE))
    original = directory.get

    def lookup(user_id: str) -> HumanIdentity:
        with store.write() as unit:
            assert unit.policies.get("home").revision == 1
        actor.human = replace(actor.human, is_administrator=False)
        return original(user_id)

    monkeypatch.setattr(directory, "get", lookup)
    with pytest.raises(Forbidden):
        commands.update(
            "select", UpdatePolicy(1, AdministratorMapping(MappingMode.SELECTED, "ha_joiner"))
        )
    with store.read() as unit:
        assert unit.policies.get("home").revision == 1
        assert len(unit.audit.entries("home")) == 3


def test_local_inventory_changed_during_target_proof_is_a_conflict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    commands, members, store, _, directory, member_id = policies(tmp_path)
    members.update("activate", UpdateMember(member_id, 1, Role.ADULT, MemberStatus.ACTIVE))
    original = directory.get

    def lookup(user_id: str) -> HumanIdentity:
        with store.write() as unit:
            member = unit.members.get("home", member_id)
            unit.members.save(replace(member, status=MemberStatus.SUSPENDED, revision=3), 2)
        return original(user_id)

    monkeypatch.setattr(directory, "get", lookup)
    with pytest.raises(Conflict, match="identity_state_changed"):
        commands.update(
            "select", UpdatePolicy(1, AdministratorMapping(MappingMode.SELECTED, "ha_joiner"))
        )
    with store.read() as unit:
        assert unit.policies.get("home").revision == 1


def test_adjustment_order_is_canonical_and_authorized_replay_ignores_old_revision(
    tmp_path: Path,
) -> None:
    commands, _, _, _, directory, _ = policies(tmp_path)
    rules = (
        ProfileRule(Role.VIEWER, Permission.SHOPPING_REQUEST, True),
        ProfileRule(Role.ADULT, Permission.INVENTORY_MANAGE, False),
    )
    request = UpdatePolicy(1, AdministratorMapping(MappingMode.ALL), rules)
    original = commands.update("edit", request)
    directory.error = IdentityUnavailable("ha_unavailable")
    assert commands.update("edit", replace(request, adjustments=tuple(reversed(rules)))) == original
    with pytest.raises(Conflict, match="idempotency_conflict"):
        commands.update("edit", replace(request, adjustments=()))
    with pytest.raises(Conflict, match="revision_conflict"):
        commands.update("another", request)


@pytest.mark.parametrize(
    "values",
    [
        {"expected_revision": 0},
        {"expected_revision": True},
        {"mapping": "all_ha_administrators"},
        {"adjustments": []},
        {"adjustments": (ProfileRule(Role.ADULT, Permission.HOUSEHOLD_READ, False),) * 2},
    ],
)
def test_policy_contract_rejects_ambiguous_revision_mapping_and_rules(values: dict) -> None:
    with pytest.raises(InvalidInput):
        UpdatePolicy(
            **{"expected_revision": 1, "mapping": AdministratorMapping(MappingMode.ALL), **values}
        )


def test_setup_mapping_rejects_a_founder_who_is_no_longer_ha_administrator(tmp_path: Path) -> None:
    commands, members, store, actor, directory, member_id = policies(tmp_path)
    members.update("promote", UpdateMember(member_id, 1, Role.ADMINISTRATOR, MemberStatus.ACTIVE))
    actor.human = directory.people["ha_joiner"]
    directory.people["ha_admin"] = HumanIdentity("ha_admin", False, True, False)
    with pytest.raises(Forbidden, match="ha_administrator_required"):
        commands.update(
            "setup-only", UpdatePolicy(1, AdministratorMapping(MappingMode.SETUP, "ha_admin"))
        )
    with store.read() as unit:
        assert unit.policies.get("home").revision == 1
        assert len(unit.audit.entries("home")) == 3


def test_switching_away_from_selected_mapping_cannot_remove_the_last_administrator(
    tmp_path: Path,
) -> None:
    commands, members, store, actor, directory, member_id = policies(tmp_path)
    members.update("activate", UpdateMember(member_id, 1, Role.VIEWER, MemberStatus.ACTIVE))
    commands.update(
        "select", UpdatePolicy(1, AdministratorMapping(MappingMode.SELECTED, "ha_joiner"))
    )
    actor.human = directory.people["ha_joiner"]
    del directory.people["ha_admin"]
    with pytest.raises(Conflict, match="last_administrator"):
        commands.update("all", UpdatePolicy(2, AdministratorMapping(MappingMode.ALL)))
    with store.read() as unit:
        assert unit.policies.get("home").mapping.mode is MappingMode.SELECTED
        assert unit.policies.get("home").revision == 2
        assert len(unit.audit.entries("home")) == len(unit.outbox.pending()) == 4


def test_policy_write_blocks_on_source_outage_without_changing_current_mapping(
    tmp_path: Path,
) -> None:
    commands, members, store, _, directory, member_id = policies(tmp_path)
    members.update("activate", UpdateMember(member_id, 1, Role.VIEWER, MemberStatus.ACTIVE))
    directory.error = IdentityUnavailable("ha_unavailable")
    with pytest.raises(IdentityUnavailable):
        commands.update(
            "select", UpdatePolicy(1, AdministratorMapping(MappingMode.SELECTED, "ha_joiner"))
        )
    with store.read() as unit:
        assert unit.policies.get("home").mapping.mode is MappingMode.ALL
        assert unit.policies.get("home").revision == 1


@pytest.mark.parametrize("damage", ["missing", "duplicate", "malformed"])
def test_missing_or_corrupt_setup_provenance_never_designates_a_new_founder(
    tmp_path: Path, damage: str
) -> None:
    import sqlite3
    from contextlib import closing

    from domus.domain.errors import StorageFailure

    commands, _, store, _, _, _ = policies(tmp_path)
    with closing(sqlite3.connect(store.path, autocommit=True)) as connection:
        if damage == "missing":
            connection.execute("DELETE FROM audit WHERE action='household.setup'")
        elif damage == "duplicate":
            connection.execute(
                "INSERT INTO audit SELECT 'duplicate-setup',household_id,actor_id,action,"
                "command_key,detail,created_at FROM audit WHERE action='household.setup'"
            )
        else:
            connection.execute(
                "UPDATE audit SET actor_id='invalid/actor' WHERE action='household.setup'"
            )
    error, code = (
        (Conflict, "setup_provenance_required")
        if damage == "missing"
        else (StorageFailure, "invalid_setup_provenance")
    )
    with pytest.raises(error, match=code):
        commands.update(
            "setup-only", UpdatePolicy(1, AdministratorMapping(MappingMode.SETUP, "ha_admin"))
        )
    with store.read() as unit:
        assert unit.policies.get("home").revision == 1
        assert len(unit.outbox.pending()) == 2


def test_unbounded_member_inventory_cannot_prepare_a_policy_change(tmp_path: Path) -> None:
    from domus.domain.errors import StorageFailure

    commands, _, store, _, directory, member_id = policies(tmp_path)
    with store.write() as unit:
        member = unit.members.get("home", member_id)
        for number in range(255):
            unit.members.save(
                replace(member, member_id=f"overflow{number}", ha_user_id=f"human{number}"), 0
            )
    with pytest.raises(StorageFailure, match="invalid_identity_record"):
        commands.update("edit", UpdatePolicy(1, AdministratorMapping(MappingMode.ALL)))
    assert directory.calls == directory.batch_calls == []


def test_policy_changed_while_resolving_target_is_not_overwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    commands, members, store, _, directory, member_id = policies(tmp_path)
    members.update("activate", UpdateMember(member_id, 1, Role.VIEWER, MemberStatus.ACTIVE))
    original = directory.get

    def lookup(user_id: str) -> HumanIdentity:
        commands.update(
            "concurrent",
            UpdatePolicy(
                1,
                AdministratorMapping(MappingMode.ALL),
                (ProfileRule(Role.VIEWER, Permission.SHOPPING_REQUEST, True),),
            ),
        )
        return original(user_id)

    monkeypatch.setattr(directory, "get", lookup)
    with pytest.raises(Conflict, match="identity_state_changed"):
        commands.update(
            "select", UpdatePolicy(1, AdministratorMapping(MappingMode.SELECTED, "ha_joiner"))
        )
    with store.read() as unit:
        assert unit.policies.get("home").revision == 2
        assert unit.policies.get("home").mapping.mode is MappingMode.ALL
        assert len(unit.audit.entries("home")) == len(unit.outbox.pending()) == 4


def test_restart_preserves_policy_revision_provenance_and_authorized_replay(tmp_path: Path) -> None:
    from domus.infrastructure.sqlite import SQLiteDatabase

    commands, _, store, actor, directory, _ = policies(tmp_path)
    request = UpdatePolicy(1, AdministratorMapping(MappingMode.SETUP, "ha_admin"))
    original = commands.update("setup-only", request)
    restarted = PolicyCommands(
        SQLiteDatabase(store.path, store.installation),
        actor,
        directory,
        commands.clock,
        commands.identifiers,
    )
    directory.error = IdentityUnavailable("ha_unavailable")
    assert restarted.update("setup-only", request) == original
    with restarted.transactions.read() as unit:
        assert unit.audit.setup_actor("home") == "ha_admin"
        assert unit.policies.get("home").revision == 2
