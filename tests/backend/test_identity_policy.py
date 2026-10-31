"""Identity policy enforces current sources, explicit scope and permission precedence."""

from dataclasses import FrozenInstanceError, replace

import pytest

from domus.domain.errors import Conflict, InvalidInput
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
    allows,
    effective_role,
    ensure_administrator,
    recovery_allowed,
)


def human(user_id: str = "ha_1", *, administrator: bool = False) -> HumanIdentity:
    return HumanIdentity(user_id, administrator, True, False)


def member(role: Role = Role.VIEWER, **changes: object) -> Member:
    return replace(Member("member_1", "home", "ha_1", role, MemberStatus.ACTIVE, 1), **changes)


def policy(**changes: object) -> HouseholdPolicy:
    return replace(HouseholdPolicy("home", AdministratorMapping(MappingMode.ALL), 1), **changes)


@pytest.mark.parametrize(
    "flags",
    [
        (False, False, False),
        (False, True, True),
        (1, True, False),
        (False, "yes", False),
        (False, True, 0),
    ],
)
def test_only_exact_boolean_active_nonsystem_human_is_eligible(flags: tuple[object, ...]) -> None:
    with pytest.raises(InvalidInput, match="invalid_human_identity"):
        HumanIdentity("ha_1", *flags)


def test_identity_is_exact_stable_identifier_and_immutable() -> None:
    first = human()
    assert first.ha_user_id == "ha_1"
    with pytest.raises(FrozenInstanceError):
        first.is_administrator = True
    with pytest.raises(InvalidInput, match="invalid_identifier"):
        human("invalid user")


@pytest.mark.parametrize("mode", [MappingMode.SETUP, MappingMode.SELECTED])
def test_designated_modes_require_an_explicit_target(mode: MappingMode) -> None:
    with pytest.raises(InvalidInput, match="invalid_administrator_mapping"):
        AdministratorMapping(mode)
    assert AdministratorMapping(mode, "ha_1").target_ha_user_id == "ha_1"


@pytest.mark.parametrize(
    "mapping",
    [(MappingMode.ALL, "ha_1"), ("all_ha_administrators", None), (MappingMode.SELECTED, "")],
)
def test_invalid_mapping_cannot_silently_widen(mapping: tuple[object, object]) -> None:
    with pytest.raises(InvalidInput):
        AdministratorMapping(*mapping)


def test_all_administrators_mapping_uses_current_proof_and_retains_explicit_grants() -> None:
    assert effective_role(human(administrator=True), member(), policy()) == Role.ADMINISTRATOR
    assert effective_role(human(), member(), policy()) == Role.VIEWER
    assert effective_role(human(), member(Role.ADMINISTRATOR), policy()) == Role.ADMINISTRATOR
    selected_elsewhere = policy(mapping=AdministratorMapping(MappingMode.SELECTED, "ha_2"))
    assert effective_role(human(administrator=True), member(), selected_elsewhere) == Role.VIEWER
    assert (
        effective_role(human(), member(Role.ADMINISTRATOR), selected_elsewhere)
        == Role.ADMINISTRATOR
    )


def test_setup_mapping_requires_the_designated_current_ha_administrator() -> None:
    selected = policy(mapping=AdministratorMapping(MappingMode.SETUP, "ha_1"))
    assert effective_role(human(administrator=True), member(), selected) == Role.ADMINISTRATOR
    assert effective_role(human(), member(), selected) == Role.VIEWER
    other = member(ha_user_id="ha_2")
    assert effective_role(human("ha_2", administrator=True), other, selected) == Role.VIEWER


def test_selected_mapping_does_not_require_selected_human_to_be_ha_administrator() -> None:
    selected = policy(mapping=AdministratorMapping(MappingMode.SELECTED, "ha_1"))
    assert effective_role(human(), member(), selected) == Role.ADMINISTRATOR
    assert effective_role(human(), member(), policy()) == Role.VIEWER


@pytest.mark.parametrize(
    "state", [MemberStatus.PENDING, MemberStatus.SUSPENDED, MemberStatus.ARCHIVED]
)
def test_inactive_local_state_denies_even_independent_and_inherited_administration(
    state: MemberStatus,
) -> None:
    actor = member(Role.ADMINISTRATOR, status=state)
    assert effective_role(human(administrator=True), actor, policy()) is None
    assert not allows(human(administrator=True), actor, policy(), Permission.HOUSEHOLD_READ, "home")


def test_wrong_identity_and_cross_household_never_resolve_a_role() -> None:
    assert effective_role(human("ha_2"), member(Role.ADMINISTRATOR), policy()) is None
    assert effective_role(human(), member(Role.ADMINISTRATOR), policy(household_id="other")) is None
    assert not allows(
        human(), member(Role.ADMINISTRATOR), policy(), Permission.MEMBERS_MANAGE, "other"
    )


@pytest.mark.parametrize(
    "role,permission,expected",
    [
        (Role.ADMINISTRATOR, Permission.MEMBERS_MANAGE, True),
        (Role.ADMINISTRATOR, Permission.AUTOMATIONS_CONFIGURE, True),
        (Role.ADULT, Permission.TASKS_CREATE, True),
        (Role.ADULT, Permission.SHOPPING_MANAGE, True),
        (Role.ADULT, Permission.TASKS_APPROVE, True),
        (Role.ADULT, Permission.POLICY_MANAGE, False),
        (Role.RESTRICTED, Permission.SHOPPING_REQUEST, True),
        (Role.RESTRICTED, Permission.TASKS_CREATE, False),
        (Role.RESTRICTED, Permission.TASKS_APPROVE, False),
        (Role.VIEWER, Permission.HOUSEHOLD_READ, True),
        (Role.VIEWER, Permission.TASKS_COMPLETE, False),
        (Role.VIEWER, Permission.INVENTORY_MANAGE, False),
    ],
)
def test_default_profile_matrix(role: Role, permission: Permission, expected: bool) -> None:
    assert allows(human(), member(role), policy(), permission, "home") is expected


def test_restricted_work_is_assigned_to_actual_member_and_cannot_skip_adult_approval() -> None:
    actor = member(Role.RESTRICTED, exceptions=(PermissionRule(Permission.TASKS_APPROVE, True),))
    assert not allows(human(), actor, policy(), Permission.TASKS_COMPLETE, "home")
    assert allows(
        human(), actor, policy(), Permission.TASKS_COMPLETE, "home", assigned_to=("member_1",)
    )
    assert not allows(human(), actor, policy(), Permission.TASKS_APPROVE, "home")
    viewer = member(exceptions=(PermissionRule(Permission.TASKS_APPROVE, True),))
    assert not allows(human(), viewer, policy(), Permission.TASKS_APPROVE, "home")


@pytest.mark.parametrize("role", list(Role))
@pytest.mark.parametrize(
    "permission",
    [Permission.PREFERENCES_READ, Permission.PREFERENCES_WRITE, Permission.OPERATIONS_READ],
)
def test_own_scoped_actions_require_explicit_self_even_for_administrator(
    role: Role,
    permission: Permission,
) -> None:
    actor = member(role)
    assert allows(human(), actor, policy(), permission, "home", subject_member_id="member_1")
    assert not allows(human(), actor, policy(), permission, "home", subject_member_id="member_2")
    assert not allows(human(), actor, policy(), permission, "home")


def test_member_then_profile_then_default_precedence_and_undefined_denial() -> None:
    denied_profile = policy(adjustments=(ProfileRule(Role.ADULT, Permission.TASKS_CREATE, False),))
    ordinary = member(Role.ADULT)
    assert not allows(human(), ordinary, denied_profile, Permission.TASKS_CREATE, "home")
    allowed_member = replace(ordinary, exceptions=(PermissionRule(Permission.TASKS_CREATE, True),))
    assert allows(human(), allowed_member, denied_profile, Permission.TASKS_CREATE, "home")
    allowed_profile = policy(adjustments=(ProfileRule(Role.VIEWER, Permission.TASKS_CREATE, True),))
    denied_member = member(exceptions=(PermissionRule(Permission.TASKS_CREATE, False),))
    assert allows(human(), member(), allowed_profile, Permission.TASKS_CREATE, "home")
    assert not allows(human(), denied_member, allowed_profile, Permission.TASKS_CREATE, "home")
    assert not allows(human(), member(Role.ADMINISTRATOR), policy(), "unknown.action", "home")
    unrelated = policy(
        adjustments=(
            ProfileRule(Role.VIEWER, Permission.TASKS_CREATE, True),
            ProfileRule(Role.ADULT, Permission.TASKS_APPROVE, False),
        )
    )
    assert allows(human(), member(Role.ADULT), unrelated, Permission.TASKS_CREATE, "home")


def test_profile_overrides_do_not_create_administrator_authority() -> None:
    with pytest.raises(InvalidInput, match="protected_permission"):
        PermissionRule(Permission.MEMBERS_MANAGE, True)
    with pytest.raises(InvalidInput, match="protected_permission"):
        ProfileRule(Role.VIEWER, Permission.POLICY_MANAGE, True)
    denied_admin = member(
        Role.ADMINISTRATOR, exceptions=(PermissionRule(Permission.TASKS_CREATE, False),)
    )
    assert not allows(human(), denied_admin, policy(), Permission.TASKS_CREATE, "home")


@pytest.mark.parametrize("revision", [0, -1, True, 2**63])
def test_invalid_revisions_are_rejected(revision: object) -> None:
    with pytest.raises(InvalidInput, match="invalid_revision"):
        member(revision=revision)
    with pytest.raises(InvalidInput, match="invalid_revision"):
        policy(revision=revision)


def test_invalid_enums_rules_mutable_lists_and_same_level_duplicates_are_rejected() -> None:
    with pytest.raises(InvalidInput, match="invalid_member"):
        member(role="viewer")
    with pytest.raises(InvalidInput, match="invalid_member"):
        member(status="active")
    with pytest.raises(InvalidInput, match="invalid_permission_rule"):
        PermissionRule("tasks.create", True)
    with pytest.raises(InvalidInput, match="invalid_permission_rule"):
        PermissionRule(Permission.TASKS_CREATE, 1)
    with pytest.raises(InvalidInput, match="invalid_profile_rule"):
        ProfileRule("adult", Permission.TASKS_CREATE, True)
    with pytest.raises(InvalidInput, match="invalid_policy"):
        policy(mapping="all")
    allow, deny = (
        PermissionRule(Permission.TASKS_CREATE, True),
        PermissionRule(Permission.TASKS_CREATE, False),
    )
    for rules in ([allow], ("wrong",), (allow, deny), (allow, allow), (allow,) * 257):
        with pytest.raises(InvalidInput, match="invalid_permission_rules"):
            member(exceptions=rules)
    rule = ProfileRule(Role.ADULT, Permission.TASKS_CREATE, True)
    for rules in ([rule], ("wrong",), (rule, rule), (rule,) * 257):
        with pytest.raises(InvalidInput, match="invalid_profile_rules"):
            policy(adjustments=rules)


def test_last_administrator_requires_an_active_member_with_current_identity_evidence() -> None:
    admin = member(Role.ADMINISTRATOR)
    ensure_administrator(policy(), (admin,), (human(),))
    inherited = member()
    ensure_administrator(policy(), (inherited,), (human(administrator=True),))
    for records, identities in [
        ((inherited,), (human(),)),
        ((admin,), ()),
        ((replace(admin, status=MemberStatus.SUSPENDED),), (human(),)),
        ((), (human(administrator=True),)),
    ]:
        with pytest.raises(Conflict, match="last_administrator"):
            ensure_administrator(policy(), records, identities)


def test_recovery_is_narrowly_available_only_to_current_ha_administrator_in_alternate_modes() -> (
    None
):
    assert not recovery_allowed(human(administrator=True), policy())
    for mode in (MappingMode.SETUP, MappingMode.SELECTED):
        alternate = policy(mapping=AdministratorMapping(mode, "ha_2"))
        assert recovery_allowed(human(administrator=True), alternate)
        assert not recovery_allowed(human(), alternate)
