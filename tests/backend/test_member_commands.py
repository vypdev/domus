"""Real-file administrator transitions cannot bypass eligibility, replay or last-admin safety."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace

import pytest
from test_household_commands import fixture

from domus.application.household_commands import SetupHousehold
from domus.application.member_commands import MemberCommands, UpdateMember
from domus.domain.errors import (
    Conflict,
    Forbidden,
    IdentityRejected,
    IdentityUnavailable,
    InvalidInput,
    StorageBusy,
    StorageFailure,
)
from domus.domain.identity import (
    HumanIdentity,
    MappingMode,
    MemberStatus,
    Permission,
    PermissionRule,
    Role,
    allows,
)
from domus.infrastructure.sqlite import SQLiteDatabase


def configured(tmp_path: Path, mode: MappingMode = MappingMode.ALL) -> tuple:
    household, store, actor, directory, identifiers = fixture(tmp_path / "database")
    household.setup("setup", SetupHousehold("Home", "UTC", mode))
    actor.human = HumanIdentity("ha_joiner", False, True, False)
    result = household.enroll("enroll")
    member_id = result.result.decode()["member_id"]
    actor.human = HumanIdentity("ha_admin", True, True, False)
    directory.people["ha_admin"] = actor.human
    directory.people["ha_joiner"] = HumanIdentity("ha_joiner", False, True, False)
    directory.batch_calls = []

    def eligible(user_ids: tuple[str, ...]) -> tuple[HumanIdentity, ...]:
        directory.batch_calls.append(user_ids)
        if directory.error:
            raise directory.error
        return tuple(
            directory.people[user_id] for user_id in user_ids if user_id in directory.people
        )

    directory.eligible = eligible
    commands = MemberCommands(store, actor, directory, household.clock, identifiers)
    return commands, store, actor, directory, member_id


def test_activation_commits_verified_linkage_role_exceptions_and_evidence(tmp_path: Path) -> None:
    commands, store, _, directory, member_id = configured(tmp_path)
    rule = PermissionRule(Permission.SHOPPING_REQUEST, False)
    request = UpdateMember(member_id, 1, Role.RESTRICTED, MemberStatus.ACTIVE, (rule,))
    receipt = commands.update("activate", request)
    with store.read() as unit:
        member = unit.members.get("home", member_id)
        assert member.ha_user_id == "ha_joiner"
        assert member.role is Role.RESTRICTED and member.status is MemberStatus.ACTIVE
        assert member.revision == 2 and member.exceptions == (rule,)
        policy = unit.policies.get("home")
        assert not allows(
            directory.people["ha_joiner"], member, policy, Permission.SHOPPING_REQUEST, "home"
        )
        assert unit.receipts.get(receipt.command) == receipt
        assert len(unit.audit.entries("home")) == len(unit.outbox.pending()) == 3
    assert receipt.command.actor_id == "ha_admin"
    assert receipt.result.decode() == {
        "member_id": member_id,
        "revision": 2,
        "status": "active",
        "role": "restricted",
    }


@pytest.mark.parametrize("failure", ["unavailable", "rejected", "mismatch"])
def test_activation_requires_exact_fresh_target_without_partial_effects(
    tmp_path: Path, failure: str
) -> None:
    commands, store, _, directory, member_id = configured(tmp_path)
    if failure == "mismatch":
        directory.people["ha_joiner"] = HumanIdentity("another", False, True, False)
    else:
        directory.error = (
            IdentityUnavailable("ha_unavailable")
            if failure == "unavailable"
            else IdentityRejected("ha_subject_rejected")
        )
    with pytest.raises((IdentityUnavailable, IdentityRejected, Forbidden)):
        commands.update("activate", UpdateMember(member_id, 1, Role.ADULT, MemberStatus.ACTIVE))
    with store.read() as unit:
        assert unit.members.get("home", member_id).status is MemberStatus.PENDING
        assert len(unit.audit.entries("home")) == len(unit.outbox.pending()) == 2


def test_current_administrator_may_archive_an_ineligible_other_user_without_contacting_them(
    tmp_path: Path,
) -> None:
    commands, store, _, directory, member_id = configured(tmp_path)
    directory.error = IdentityUnavailable("ha_unavailable")
    commands.update("archive", UpdateMember(member_id, 1, Role.VIEWER, MemberStatus.ARCHIVED))
    assert directory.calls == directory.batch_calls == []
    with store.read() as unit:
        member = unit.members.get("home", member_id)
        assert member.status is MemberStatus.ARCHIVED and member.ha_user_id == "ha_joiner"


@pytest.mark.parametrize(
    "status", [MemberStatus.PENDING, MemberStatus.SUSPENDED, MemberStatus.ARCHIVED]
)
def test_last_administrator_cannot_deactivate_itself(tmp_path: Path, status: MemberStatus) -> None:
    commands, store, _, _, _ = configured(tmp_path)
    with store.read() as unit:
        administrator = unit.members.by_user("home", "ha_admin")
    with pytest.raises(Conflict, match="last_administrator"):
        commands.update(
            "remove-self", UpdateMember(administrator.member_id, 1, Role.VIEWER, status)
        )
    with store.read() as unit:
        assert unit.members.by_user("home", "ha_admin").status is MemberStatus.ACTIVE
        assert len(unit.audit.entries("home")) == 2


def test_explicit_handover_preserves_ordinary_admin_and_then_allows_self_suspension(
    tmp_path: Path,
) -> None:
    commands, store, _, directory, member_id = configured(tmp_path, MappingMode.SETUP)
    commands.update("promote", UpdateMember(member_id, 1, Role.ADMINISTRATOR, MemberStatus.ACTIVE))
    with store.read() as unit:
        administrator = unit.members.by_user("home", "ha_admin")
    commands.update(
        "suspend-self",
        UpdateMember(administrator.member_id, 1, Role.VIEWER, MemberStatus.SUSPENDED),
    )
    assert directory.batch_calls == [("ha_joiner",)]
    with store.read() as unit:
        member = unit.members.get("home", member_id)
        assert allows(
            directory.people["ha_joiner"],
            member,
            unit.policies.get("home"),
            Permission.MEMBERS_MANAGE,
            "home",
        )
    with pytest.raises(Forbidden):
        commands.update(
            "suspend-self",
            UpdateMember(administrator.member_id, 1, Role.VIEWER, MemberStatus.SUSPENDED),
        )


def test_ha_revoked_remaining_administrator_cannot_satisfy_last_admin_check(tmp_path: Path) -> None:
    commands, store, _, directory, member_id = configured(tmp_path)
    commands.update("promote", UpdateMember(member_id, 1, Role.ADMINISTRATOR, MemberStatus.ACTIVE))
    del directory.people["ha_joiner"]
    with store.read() as unit:
        administrator = unit.members.by_user("home", "ha_admin")
    with pytest.raises(Conflict, match="last_administrator"):
        commands.update(
            "suspend", UpdateMember(administrator.member_id, 1, Role.VIEWER, MemberStatus.SUSPENDED)
        )


def test_current_authority_precedes_old_receipt_and_target_availability(tmp_path: Path) -> None:
    commands, store, actor, directory, member_id = configured(tmp_path)
    request = UpdateMember(member_id, 1, Role.ADULT, MemberStatus.ACTIVE)
    result = commands.update("activate", request)
    directory.error = IdentityUnavailable("ha_unavailable")
    assert commands.update("activate", request) == result
    with pytest.raises(Conflict, match="idempotency_conflict"):
        commands.update("activate", replace(request, role=Role.VIEWER))
    actor.human = replace(actor.human, is_administrator=False)
    with pytest.raises(Forbidden):
        commands.update("activate", request)
    with store.read() as unit:
        assert unit.members.get("home", member_id).revision == 2


def test_invalid_and_stale_member_changes_never_request_target_proof(tmp_path: Path) -> None:
    commands, _, _, directory, member_id = configured(tmp_path)
    for request, code in (
        (UpdateMember("missing", 1, Role.ADULT, MemberStatus.ACTIVE), "member_missing"),
        (UpdateMember(member_id, 2, Role.ADULT, MemberStatus.ACTIVE), "revision_conflict"),
    ):
        with pytest.raises(Conflict, match=code):
            commands.update("update", request)
    assert directory.calls == directory.batch_calls == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"expected_revision": True},
        {"expected_revision": 0},
        {"member_id": "bad/id"},
        {"role": "administrator"},
        {"status": "active"},
        {"exceptions": []},
        {"exceptions": (PermissionRule(Permission.HOUSEHOLD_READ, True),) * 2},
    ],
)
def test_change_contract_rejects_ambiguous_revisions_enums_and_rules(overrides: dict) -> None:
    values = {
        "member_id": "member",
        "expected_revision": 1,
        "role": Role.VIEWER,
        "status": MemberStatus.ACTIVE,
        **overrides,
    }
    with pytest.raises(InvalidInput):
        UpdateMember(**values)


def test_rule_order_does_not_change_the_canonical_retry_payload(tmp_path: Path) -> None:
    commands, _, _, _, member_id = configured(tmp_path)
    rules = (
        PermissionRule(Permission.TASKS_COMPLETE, True),
        PermissionRule(Permission.SHOPPING_REQUEST, False),
    )
    request = UpdateMember(member_id, 1, Role.ADULT, MemberStatus.ACTIVE, rules)
    result = commands.update("activate", request)
    assert (
        commands.update("activate", replace(request, exceptions=tuple(reversed(rules)))) == result
    )


@pytest.mark.parametrize("changed", ["policy", "member"])
def test_external_proof_cannot_commit_against_changed_local_authority_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, changed: str
) -> None:
    commands, store, _, directory, member_id = configured(tmp_path)
    original = directory.get

    def lookup(user_id: str) -> HumanIdentity:
        # This also proves external I/O never holds the writer lock.
        with store.write() as unit:
            if changed == "policy":
                policy = unit.policies.get("home")
                unit.policies.save(replace(policy, revision=2), 1)
            else:
                member = unit.members.get("home", member_id)
                unit.members.save(replace(member, role=Role.RESTRICTED, revision=2), 1)
        return original(user_id)

    monkeypatch.setattr(directory, "get", lookup)
    with pytest.raises(Conflict, match="identity_state_changed"):
        commands.update("activate", UpdateMember(member_id, 1, Role.ADULT, MemberStatus.ACTIVE))
    with store.read() as unit:
        assert unit.members.get("home", member_id).status is MemberStatus.PENDING
        assert len(unit.audit.entries("home")) == len(unit.outbox.pending()) == 2


@pytest.mark.parametrize("change", ["revoked", "mismatch", "unavailable"])
def test_actor_is_reproved_after_external_lookup_before_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    commands, store, actor, directory, member_id = configured(tmp_path)
    original = directory.get

    def lookup(user_id: str) -> HumanIdentity:
        if change == "unavailable":
            actor.error = IdentityUnavailable("ha_unavailable")
        else:
            actor.human = HumanIdentity(
                "someone_else" if change == "mismatch" else "ha_admin", False, True, False
            )
        return original(user_id)

    monkeypatch.setattr(directory, "get", lookup)
    with pytest.raises((Forbidden, IdentityUnavailable)):
        commands.update("activate", UpdateMember(member_id, 1, Role.ADULT, MemberStatus.ACTIVE))
    with store.read() as unit:
        assert unit.members.get("home", member_id).status is MemberStatus.PENDING
        assert len(unit.audit.entries("home")) == 2


@pytest.mark.parametrize("result", ["list", "too_many", "unknown", "duplicate", "invalid"])
def test_untrusted_batch_shape_or_identity_cannot_create_a_remaining_administrator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, result: str
) -> None:
    commands, store, _, directory, member_id = configured(tmp_path, MappingMode.SETUP)
    commands.update("promote", UpdateMember(member_id, 1, Role.ADMINISTRATOR, MemberStatus.ACTIVE))
    with store.read() as unit:
        administrator = unit.members.by_user("home", "ha_admin")
        extra = unit.members.get("home", member_id)
    # A second candidate makes the duplicate-identity guard independent of the size bound.
    with store.write() as unit:
        unit.members.save(replace(extra, member_id="extra", ha_user_id="ha_extra", revision=1), 0)
    human = directory.people["ha_joiner"]
    results = {
        "list": [human],
        "too_many": (human,) * 3,
        "unknown": (HumanIdentity("unknown", True, True, False),),
        "duplicate": (human, human),
        "invalid": (None,),
    }
    monkeypatch.setattr(directory, "eligible", lambda _: results[result])
    with pytest.raises(Forbidden, match="identity_mismatch"):
        commands.update(
            "suspend", UpdateMember(administrator.member_id, 1, Role.VIEWER, MemberStatus.SUSPENDED)
        )
    with store.read() as unit:
        assert unit.members.by_user("home", "ha_admin").status is MemberStatus.ACTIVE
        assert len(unit.audit.entries("home")) == 3


def test_directory_outage_never_becomes_confirmed_absence_or_a_partial_transition(
    tmp_path: Path,
) -> None:
    commands, store, _, directory, member_id = configured(tmp_path, MappingMode.SETUP)
    commands.update("promote", UpdateMember(member_id, 1, Role.ADMINISTRATOR, MemberStatus.ACTIVE))
    with store.read() as unit:
        administrator = unit.members.by_user("home", "ha_admin")
    directory.error = IdentityUnavailable("ha_unavailable")
    with pytest.raises(IdentityUnavailable):
        commands.update(
            "suspend", UpdateMember(administrator.member_id, 1, Role.VIEWER, MemberStatus.SUSPENDED)
        )
    with store.read() as unit:
        assert unit.members.by_user("home", "ha_admin").revision == 1
        assert len(unit.audit.entries("home")) == 3


def test_unbounded_corrupt_member_inventory_fails_before_lookup(tmp_path: Path) -> None:
    commands, store, _, directory, member_id = configured(tmp_path)
    with store.write() as unit:
        member = unit.members.get("home", member_id)
        for number in range(255):
            unit.members.save(
                replace(member, member_id=f"overflow{number}", ha_user_id=f"human{number}"), 0
            )
    with pytest.raises(StorageFailure, match="invalid_identity_record"):
        commands.update("activate", UpdateMember(member_id, 1, Role.ADULT, MemberStatus.ACTIVE))
    assert directory.calls == directory.batch_calls == []


def test_suspension_takes_effect_on_existing_authenticated_authority_immediately(
    tmp_path: Path,
) -> None:
    commands, store, actor, directory, member_id = configured(tmp_path)
    commands.update("promote", UpdateMember(member_id, 1, Role.ADMINISTRATOR, MemberStatus.ACTIVE))
    actor.human = directory.people["ha_joiner"]
    commands.update("edit-own", UpdateMember(member_id, 2, Role.ADMINISTRATOR, MemberStatus.ACTIVE))
    actor.human = directory.people["ha_admin"]
    commands.update(
        "suspend", UpdateMember(member_id, 3, Role.ADMINISTRATOR, MemberStatus.SUSPENDED)
    )
    actor.human = directory.people["ha_joiner"]
    with pytest.raises(Forbidden):
        commands.update(
            "edit-own", UpdateMember(member_id, 2, Role.ADMINISTRATOR, MemberStatus.ACTIVE)
        )
    with pytest.raises(Forbidden):
        commands.update(
            "self-reactivate", UpdateMember(member_id, 4, Role.ADMINISTRATOR, MemberStatus.ACTIVE)
        )


def test_restart_preserves_authorized_member_command_replay(tmp_path: Path) -> None:
    commands, store, actor, directory, member_id = configured(tmp_path)
    request = UpdateMember(member_id, 1, Role.ADULT, MemberStatus.ACTIVE)
    receipt = commands.update("activate", request)
    restarted = MemberCommands(
        SQLiteDatabase(store.path, store.installation),
        actor,
        directory,
        commands.clock,
        commands.identifiers,
    )
    directory.error = IdentityUnavailable("ha_unavailable")
    assert restarted.update("activate", request) == receipt


def test_concurrent_self_suspension_cannot_remove_both_remaining_administrators(
    tmp_path: Path,
) -> None:
    commands, store, _, directory, member_id = configured(tmp_path, MappingMode.SETUP)
    commands.update("promote", UpdateMember(member_id, 1, Role.ADMINISTRATOR, MemberStatus.ACTIVE))
    with store.read() as unit:
        administrator = unit.members.by_user("home", "ha_admin")
    gate = Barrier(2)

    class ConcurrentDirectory:
        def eligible(self, user_ids: tuple[str, ...]) -> tuple[HumanIdentity, ...]:
            result = tuple(directory.people[user_id] for user_id in user_ids)
            gate.wait(timeout=3)
            return result

    def suspend(user_id: str) -> str:
        actor = SimpleNamespace(current=lambda: directory.people[user_id])
        service = MemberCommands(
            store, actor, ConcurrentDirectory(), commands.clock, commands.identifiers
        )
        target, revision = (administrator.member_id, 1) if user_id == "ha_admin" else (member_id, 2)
        try:
            service.update(
                "suspend", UpdateMember(target, revision, Role.VIEWER, MemberStatus.SUSPENDED)
            )
        except Conflict, StorageBusy:
            return "conflict"
        return "committed"

    with ThreadPoolExecutor(max_workers=2) as workers:
        assert sorted(workers.map(suspend, ("ha_admin", "ha_joiner"))) == ["committed", "conflict"]
    with store.read() as unit:
        assert (
            sum(member.status is MemberStatus.ACTIVE for member in unit.members.list("home")) == 1
        )
        assert len(unit.audit.entries("home")) == len(unit.outbox.pending()) == 4


@pytest.mark.parametrize("role", [Role.ADULT, Role.RESTRICTED, Role.VIEWER])
def test_ordinary_member_cannot_assign_itself_privileges_or_change_another_member(
    tmp_path: Path, role: Role
) -> None:
    commands, store, actor, directory, member_id = configured(tmp_path)
    commands.update("activate", UpdateMember(member_id, 1, role, MemberStatus.ACTIVE))
    actor.human = directory.people["ha_joiner"]
    calls = tuple(directory.calls)
    with pytest.raises(Forbidden):
        commands.update(
            "promote-self", UpdateMember(member_id, 2, Role.ADMINISTRATOR, MemberStatus.ACTIVE)
        )
    assert tuple(directory.calls) == calls
    with store.read() as unit:
        assert unit.members.get("home", member_id).role is role
        assert len(unit.audit.entries("home")) == 3


def test_archived_member_reactivation_is_explicit_and_preserves_ha_linkage_and_history(
    tmp_path: Path,
) -> None:
    commands, store, _, directory, member_id = configured(tmp_path)
    commands.update("archive", UpdateMember(member_id, 1, Role.VIEWER, MemberStatus.ARCHIVED))
    commands.update("reactivate", UpdateMember(member_id, 2, Role.RESTRICTED, MemberStatus.ACTIVE))
    assert directory.calls == ["ha_joiner"]
    with store.read() as unit:
        member = unit.members.by_user("home", "ha_joiner")
        assert member.member_id == member_id and member.revision == 3
        assert member.status is MemberStatus.ACTIVE
        assert len(unit.members.list("home")) == 2
        assert len(unit.audit.entries("home")) == len(unit.outbox.pending()) == 4


def test_two_identical_concurrent_activations_have_one_effect_and_the_same_receipt(
    tmp_path: Path,
) -> None:
    commands, store, _, directory, member_id = configured(tmp_path)
    gate = Barrier(2)

    class ConcurrentDirectory:
        def get(self, user_id: str) -> HumanIdentity:
            human = directory.people[user_id]
            gate.wait(timeout=3)
            return human

    def activate(_: int) -> object:
        actor = SimpleNamespace(current=lambda: directory.people["ha_admin"])
        service = MemberCommands(
            store, actor, ConcurrentDirectory(), commands.clock, commands.identifiers
        )
        return service.update(
            "activate", UpdateMember(member_id, 1, Role.ADULT, MemberStatus.ACTIVE)
        )

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(activate, (1, 2)))
    assert results[0] == results[1]
    with store.read() as unit:
        assert unit.members.get("home", member_id).revision == 2
        assert len(unit.audit.entries("home")) == len(unit.outbox.pending()) == 3
