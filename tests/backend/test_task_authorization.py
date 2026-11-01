"""Real local task authority is current and distinct from eligibility and past snapshots."""

from dataclasses import replace

import pytest
from test_membership_authorization import store_at
from test_tasks import definition, restricted_cycle

from domus.application.task_authorization import TaskAccess
from domus.domain.errors import Forbidden, InvalidInput, StorageFailure
from domus.domain.identity import (
    AdministratorMapping,
    HouseholdPolicy,
    HumanIdentity,
    MappingMode,
    Member,
    MemberStatus,
    Permission,
    PermissionRule,
    ProfileRule,
    Role,
)
from domus.domain.task_values import OccurrenceState, TaskOverrides, TaskPerformer, TaskRules
from domus.domain.tasks import HouseholdTaskPolicy


def fixture(tmp_path, role=Role.RESTRICTED, *, exceptions=(), overrides=None):
    store = store_at(tmp_path / "database")
    with store.write() as unit:
        unit.members.save(
            replace(
                unit.members.get("home", "member_1"), role=role, exceptions=exceptions, revision=2
            ),
            1,
        )
        unit.members.save(
            Member("other", "home", "ha_other", Role.ADULT, MemberStatus.ACTIVE, 1), 0
        )
        unit.tasks.save_policy(HouseholdTaskPolicy("home", TaskRules()), 0)
        item = definition(overrides=TaskOverrides() if overrides is None else overrides)
        work = item.new_occurrence("occurrence", item.created_at, assignees=("member_1",))
        unit.tasks.save_definition(item, 0)
        unit.tasks.save_occurrence(work, 0)
    return store, TaskAccess(HumanIdentity("ha_1", False, True, False)), work


@pytest.mark.parametrize("role", list(Role))
def test_task_read_defaults_are_current_and_task_scope_cannot_cross_households(tmp_path, role):
    store, access, work = fixture(tmp_path, role)
    with store.read() as unit:
        actor = access.require(unit, "home", Permission.TASKS_READ, work)
        assert actor.member.member_id == "member_1" and actor.role is role
        assert actor.identity_policy_revision == 1
        assert actor.performer == TaskPerformer("member_1", role)
        with pytest.raises(Forbidden):
            access.require(unit, "other", Permission.TASKS_READ, work)
        with pytest.raises(Forbidden):
            access.require(unit, "home", Permission.INVENTORY_MANAGE)
        with pytest.raises(Forbidden):
            access.require(unit, "home", "tasks.read")


@pytest.mark.parametrize(
    "state", [MemberStatus.PENDING, MemberStatus.SUSPENDED, MemberStatus.ARCHIVED]
)
def test_inactive_members_and_current_explicit_denials_block_reused_access(tmp_path, state):
    store, access, work = fixture(tmp_path)
    with store.read() as unit:
        access.require(unit, "home", Permission.TASKS_READ)
    with store.write() as unit:
        person = unit.members.get("home", "member_1")
        unit.members.save(replace(person, status=state, revision=3), 2)
    with store.read() as unit:
        with pytest.raises(Forbidden):
            access.require(unit, "home", Permission.TASKS_READ, work)


def test_missing_members_policy_and_fresh_ha_mapping_are_not_cached(tmp_path):
    store, access, _ = fixture(tmp_path, Role.VIEWER)
    admin = TaskAccess(HumanIdentity("ha_1", True, True, False))
    with store.read() as unit:
        assert admin.require(unit, "home", Permission.TASKS_CONFIGURE).role is Role.ADMINISTRATOR
        with pytest.raises(Forbidden):
            access.require(unit, "home", Permission.TASKS_CONFIGURE)
        with pytest.raises(Forbidden):
            TaskAccess(HumanIdentity("missing", True, True, False)).require(
                unit, "home", Permission.TASKS_READ
            )
    with store.write() as unit:
        unit.policies.save(
            HouseholdPolicy("home", AdministratorMapping(MappingMode.SELECTED, "ha_other"), 2), 1
        )
    with store.read() as unit:
        with pytest.raises(Forbidden):
            admin.require(unit, "home", Permission.TASKS_CONFIGURE)
    with store._connection() as connection:
        connection.execute("DELETE FROM household_policy")
    with store.read() as unit:
        with pytest.raises(Forbidden):
            admin.require(unit, "home", Permission.TASKS_READ)


def test_claim_is_a_separate_current_permission_without_pretending_assignment(tmp_path):
    store, access, work = fixture(tmp_path)
    available = work.assign(())
    assert available.state is OccurrenceState.AVAILABLE
    with store.write() as unit:
        unit.tasks.save_occurrence(available, work.revision)
    with store.read() as unit:
        assert access.claim(unit, available).member.member_id == "member_1"
        with pytest.raises(Forbidden):
            access.require(unit, "home", Permission.TASKS_COMPLETE, available)
    with store.write() as unit:
        person = unit.members.get("home", "member_1")
        unit.members.save(
            replace(
                person, exceptions=(PermissionRule(Permission.TASKS_CLAIM, False),), revision=3
            ),
            2,
        )
    with store.read() as unit:
        with pytest.raises(Forbidden):
            access.claim(unit, available)


@pytest.mark.parametrize(
    "rules", [TaskRules(claim_allowed=False), TaskRules(eligible_roles=(Role.ADULT,))]
)
def test_current_household_eligibility_changes_deny_claim(tmp_path, rules):
    store, access, work = fixture(tmp_path)
    with store.write() as unit:
        unit.tasks.save_policy(HouseholdTaskPolicy("home", rules, 2), 1)
    with store.read() as unit:
        with pytest.raises(Forbidden, match="task_claim_denied"):
            access.claim(unit, work)


def test_explicit_task_override_and_profile_rules_are_reread(tmp_path):
    store, access, work = fixture(tmp_path, overrides=TaskOverrides(claim_allowed=False))
    with store.read() as unit:
        with pytest.raises(Forbidden, match="task_claim_denied"):
            access.claim(unit, work)
    with store.write() as unit:
        unit.policies.save(
            HouseholdPolicy(
                "home",
                AdministratorMapping(MappingMode.ALL),
                2,
                (ProfileRule(Role.RESTRICTED, Permission.TASKS_READ, False),),
            ),
            1,
        )
    with store.read() as unit:
        with pytest.raises(Forbidden):
            access.require(unit, "home", Permission.TASKS_READ)


def test_missing_task_policy_fails_closed_instead_of_creating_read_side_defaults(tmp_path):
    store, access, work = fixture(tmp_path)
    with store._connection() as connection:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute("DELETE FROM task_policy")
    with store.read() as unit:
        with pytest.raises(StorageFailure, match="invalid_task_references"):
            access.claim(unit, work)


def test_restricted_performers_need_real_assignment_self_attribution_and_on_behalf_grant(tmp_path):
    store, access, work = fixture(tmp_path)
    with store.read() as unit:
        assert access.performers(unit, work, ("member_1",)) == (
            TaskPerformer("member_1", Role.RESTRICTED),
        )
        with pytest.raises(Forbidden):
            access.performers(unit, work, ("other",))
        with pytest.raises(Forbidden):
            access.performers(unit, work, ("member_1", "other"))
        for invalid in [(), ("member_1", "member_1"), ["member_1"]]:
            with pytest.raises(InvalidInput):
                access.performers(unit, work, invalid)
    with store.write() as unit:
        person = unit.members.get("home", "member_1")
        unit.members.save(
            replace(
                person,
                exceptions=(PermissionRule(Permission.TASKS_RECORD_FOR_OTHERS, True),),
                revision=3,
            ),
            2,
        )
    with store.read() as unit:
        assert access.performers(unit, work, ("other", "member_1")) == (
            TaskPerformer("other", Role.ADULT),
            TaskPerformer("member_1", Role.RESTRICTED),
        )
        with pytest.raises(Forbidden):
            access.performers(unit, work, ("other",))


@pytest.mark.parametrize(
    "state", [None, MemberStatus.PENDING, MemberStatus.SUSPENDED, MemberStatus.ARCHIVED]
)
def test_on_behalf_authority_never_invents_active_performers(tmp_path, state):
    store, access, work = fixture(tmp_path, Role.ADULT)
    if state is not None:
        with store.write() as unit:
            person = unit.members.get("home", "other")
            unit.members.save(replace(person, status=state, revision=2), 1)
    with store.read() as unit:
        with pytest.raises(Forbidden, match="task_performer_denied"):
            access.performers(unit, work, ("missing" if state is None else "other",))


def test_other_performer_uses_local_role_without_fabricating_ha_administrator_proof(tmp_path):
    store, access, work = fixture(tmp_path, Role.ADULT)
    with store.write() as unit:
        person = unit.members.get("home", "other")
        unit.members.save(replace(person, role=Role.RESTRICTED, revision=2), 1)
    with store.read() as unit:
        assert access.performers(unit, work, ("other",)) == (
            TaskPerformer("other", Role.RESTRICTED),
        )


def test_approval_rereads_current_adult_permission_and_original_participation_rule(tmp_path):
    store, access, work = fixture(tmp_path, Role.ADULT)
    saved = restricted_cycle(
        occurrence_id=work.occurrence_id, performers=(TaskPerformer("member_1", Role.RESTRICTED),)
    )
    with store.read() as unit:
        assert access.approver(unit, work, saved) == TaskPerformer("member_1", Role.ADULT)
        with pytest.raises(Forbidden, match="task_approval_denied"):
            access.approver(
                unit, work, replace(saved, rules=TaskRules(adult_performer_may_approve=False))
            )
        with pytest.raises(InvalidInput):
            access.approver(unit, work, replace(saved, occurrence_id="other"))
    with store.write() as unit:
        person = unit.members.get("home", "member_1")
        unit.members.save(
            replace(
                person, exceptions=(PermissionRule(Permission.TASKS_APPROVE, False),), revision=3
            ),
            2,
        )
    with store.read() as unit:
        with pytest.raises(Forbidden):
            access.approver(unit, work, saved)


def test_member_exception_overrides_profile_and_effective_actor_role_has_current_proof(tmp_path):
    store, access, work = fixture(
        tmp_path, Role.VIEWER, exceptions=(PermissionRule(Permission.TASKS_CLAIM, True),)
    )
    with store.write() as unit:
        unit.tasks.save_policy(
            HouseholdTaskPolicy("home", TaskRules(eligible_roles=(Role.VIEWER,)), 2), 1
        )
        unit.policies.save(
            HouseholdPolicy(
                "home",
                AdministratorMapping(MappingMode.ALL),
                2,
                (ProfileRule(Role.VIEWER, Permission.TASKS_CLAIM, False),),
            ),
            1,
        )
    with store.read() as unit:
        assert access.claim(unit, work).role is Role.VIEWER
        proven_admin = TaskAccess(HumanIdentity("ha_1", True, True, False))
        assert proven_admin.performers(unit, work, ("member_1",)) == (
            TaskPerformer("member_1", Role.ADMINISTRATOR),
        )


def test_a_stale_assignment_cannot_authorize_completion_after_release(tmp_path):
    store, access, work = fixture(tmp_path)
    with store.read() as unit:
        assert access.performers(unit, work, ("member_1",))
    with store.write() as unit:
        unit.tasks.save_occurrence(work.assign(()), work.revision)
    with store.read() as unit:
        with pytest.raises(Forbidden):
            access.performers(unit, work, ("member_1",))


def test_claim_uses_the_stored_snapshot_not_a_supplied_weaker_override(tmp_path):
    store, access, work = fixture(tmp_path, overrides=TaskOverrides(claim_allowed=False))
    weakened = replace(
        work,
        definition_snapshot=replace(
            work.definition_snapshot, overrides=TaskOverrides(claim_allowed=True)
        ),
    )
    with store.read() as unit:
        with pytest.raises(Forbidden, match="task_claim_denied"):
            access.claim(unit, weakened)
        with pytest.raises(Forbidden):
            access.require(
                unit, "home", Permission.TASKS_READ, replace(work, occurrence_id="missing")
            )
