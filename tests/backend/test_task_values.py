"""Task input boundaries preserve real text and reject ambiguous or malformed values."""

from dataclasses import FrozenInstanceError, replace

import pytest

from domus.domain.errors import Conflict, InvalidInput
from domus.domain.identity import Role
from domus.domain.task_values import (
    DependencyGate,
    MaterialRecording,
    Priority,
    TaskContent,
    TaskOverrides,
    TaskPerformer,
    TaskRequirement,
    TaskRules,
    VerificationMode,
    VerificationState,
    next_task_revision,
    validate_performers,
    validate_task_ids,
    validate_task_time,
)
from domus.domain.task_values import OccurrenceState as O


def test_title_only_has_usable_defaults_without_normalizing_original_text() -> None:
    content = TaskContent("Wipe table")
    assert (content.description, content.priority, content.tags) == ("", Priority.NORMAL, ())
    rich = TaskContent(" Limpiar mesa ", "First line\nSecond\tline\r\n<script>plain text</script>")
    assert rich.title == " Limpiar mesa "
    assert "<script>plain text</script>" in rich.description
    with pytest.raises(FrozenInstanceError):
        content.title = "Changed"


@pytest.mark.parametrize("title", ["a", "a" * 160, "Preparar la habitación", "🧹"])
def test_valid_title_boundaries_and_unicode(title: str) -> None:
    assert TaskContent(title).title == title


@pytest.mark.parametrize(
    "title", [None, True, 1, "", "  ", "a" * 161, "a\n", "a\x00", "a\x7f", "\ud800"]
)
def test_invalid_titles_cannot_become_saved_tasks(title: object) -> None:
    with pytest.raises(InvalidInput, match="invalid_task_text"):
        TaskContent(title)


@pytest.mark.parametrize("description", ["x" * 4001, "bad\x01", "bad\x7f", "\ud800", None])
def test_description_bounds_and_encoding(description: object) -> None:
    with pytest.raises(InvalidInput):
        TaskContent("Task", description)


def test_all_priorities_and_full_description_are_preserved() -> None:
    for priority in Priority:
        assert TaskContent("Task", "x" * 4000, priority).priority is priority
    with pytest.raises(InvalidInput, match="invalid_task_priority"):
        TaskContent("Task", priority="normal")


@pytest.mark.parametrize(
    "tags",
    [
        ["one"],
        ("same", "same"),
        tuple(str(i) for i in range(17)),
        (None,),
        ("",),
        ("a" * 65,),
        ("bad\n",),
    ],
)
def test_tags_are_bounded_unique_valid_text(tags: object) -> None:
    with pytest.raises(InvalidInput):
        TaskContent("Task", tags=tags)


def test_tag_boundaries_remain_case_sensitive_and_immutable() -> None:
    tags = ("Kitchen", "kitchen", "x" * 64, *(str(i) for i in range(13)))
    assert TaskContent("Task", tags=tags).tags == tags


def test_rules_preserve_owner_defaults_and_explicit_alternatives() -> None:
    rules = TaskRules()
    assert rules.claim_allowed and rules.adult_performer_may_approve
    assert rules.task_scoped_material_consumption and rules.point_value_minor == 0
    assert rules.eligible_roles == (Role.ADMINISTRATOR, Role.ADULT, Role.RESTRICTED)
    assert rules.verification is VerificationMode.ROLE_DEFAULT
    assert rules.material_recording is MaterialRecording.REVIEW_ON_COMPLETION
    alternative = replace(
        rules,
        claim_allowed=False,
        eligible_roles=(),
        verification=VerificationMode.ADULT,
        adult_performer_may_approve=False,
        task_scoped_material_consumption=False,
        material_recording=MaterialRecording.SEPARATE,
        point_value_minor=1_000_000,
    )
    assert not alternative.claim_allowed and alternative.eligible_roles == ()
    assert alternative.point_value_minor == 1_000_000
    assert replace(rules, point_value_minor=1).point_value_minor == 1


@pytest.mark.parametrize(
    "field", ["claim_allowed", "adult_performer_may_approve", "task_scoped_material_consumption"]
)
@pytest.mark.parametrize("value", [0, 1, None, "true"])
def test_policy_flags_require_exact_booleans(field: str, value: object) -> None:
    with pytest.raises(InvalidInput, match="invalid_task_rules"):
        replace(TaskRules(), **{field: value})


@pytest.mark.parametrize(
    "changes",
    [
        {"eligible_roles": [Role.ADULT]},
        {"eligible_roles": (Role.ADULT, Role.ADULT)},
        {"eligible_roles": ("adult",)},
        {"eligible_roles": tuple(Role) + (Role.ADULT,)},
        {"verification": "role_default"},
        {"material_recording": "review_on_completion"},
        {"point_value_minor": True},
        {"point_value_minor": -1},
        {"point_value_minor": 1_000_001},
        {"point_value_minor": 3.33},
    ],
)
def test_invalid_policy_cannot_silently_grant_or_round(changes: dict[str, object]) -> None:
    with pytest.raises(InvalidInput):
        replace(TaskRules(), **changes)


@pytest.mark.parametrize("ids", [["a"], ("a", "a"), ("bad id",), tuple(str(i) for i in range(33))])
def test_identifier_lists_reject_mutability_duplicates_invalidity_and_overflow(ids: object) -> None:
    with pytest.raises(InvalidInput):
        validate_task_ids(ids)


def test_identifier_lists_accept_empty_or_maximum_bounded_unique_ids() -> None:
    validate_task_ids(())
    validate_task_ids(tuple("member_" + str(i) for i in range(32)))


@pytest.mark.parametrize("value", [("bad id", Role.ADULT), ("m", "adult")])
def test_performer_requires_a_valid_member_identity_and_role(value: tuple[object, object]) -> None:
    with pytest.raises(InvalidInput):
        TaskPerformer(*value)


@pytest.mark.parametrize(
    "performers",
    [
        [],
        (),
        ("m",),
        (TaskPerformer("m", Role.ADULT),) * 2,
        tuple(TaskPerformer(str(i), Role.ADULT) for i in range(33)),
    ],
)
def test_performers_are_nonempty_unique_bounded_immutable_snapshots(performers: object) -> None:
    with pytest.raises(InvalidInput):
        validate_performers(performers)


def test_performer_snapshot_boundaries() -> None:
    validate_performers((TaskPerformer("m", Role.RESTRICTED),))
    validate_performers(tuple(TaskPerformer(str(i), Role.ADULT) for i in range(32)))


def test_overrides_inherit_new_defaults_and_retain_explicit_false_or_empty_values() -> None:
    inherited = TaskOverrides()
    assert inherited.resolve(TaskRules()) == TaskRules()
    changed = replace(TaskRules(), point_value_minor=333, claim_allowed=False)
    assert inherited.resolve(changed) == changed
    explicit = TaskOverrides(
        claim_allowed=False,
        eligible_roles=(),
        verification=VerificationMode.ADULT,
        adult_performer_may_approve=False,
        task_scoped_material_consumption=False,
        material_recording=MaterialRecording.SEPARATE,
        point_value_minor=0,
    )
    resolved = explicit.resolve(changed)
    assert resolved == TaskRules(
        False, (), VerificationMode.ADULT, False, False, MaterialRecording.SEPARATE, 0
    )
    assert replace(explicit, point_value_minor=None).resolve(changed).point_value_minor == 333
    with pytest.raises(FrozenInstanceError):
        explicit.claim_allowed = True


@pytest.mark.parametrize(
    "changes",
    [
        {"claim_allowed": 1},
        {"eligible_roles": ("restricted",)},
        {"verification": "authorized_adult"},
        {"adult_performer_may_approve": "false"},
        {"task_scoped_material_consumption": 0},
        {"material_recording": "separate_recording"},
        {"point_value_minor": 3.33},
    ],
)
def test_invalid_override_fails_before_it_can_replace_a_valid_household_default(
    changes: dict[str, object],
) -> None:
    with pytest.raises(InvalidInput):
        TaskOverrides(**changes)


@pytest.mark.parametrize("value", [0, 1, 2**63 - 1])
def test_task_timestamp_integer_boundaries(value: int) -> None:
    validate_task_time(value)


@pytest.mark.parametrize("value", [True, -1, 2**63, 1.0, "1", None])
def test_task_time_never_coerces_or_wraps_invalid_values(value: object) -> None:
    with pytest.raises(InvalidInput):
        validate_task_time(value)


def test_task_revision_increment_never_wraps_or_accepts_invalid_start() -> None:
    assert next_task_revision(1) == 2
    assert next_task_revision(2**63 - 2) == 2**63 - 1
    with pytest.raises(Conflict, match="task_revision_exhausted"):
        next_task_revision(2**63 - 1)
    for invalid in [0, -1, True, 2**63]:
        with pytest.raises(InvalidInput):
            next_task_revision(invalid)


def test_combined_dependency_ids_have_a_separate_explicit_64_edge_bound() -> None:
    validate_task_ids(tuple(str(i) for i in range(64)), maximum=64)
    with pytest.raises(InvalidInput):
        validate_task_ids(tuple(str(i) for i in range(65)), maximum=64)
    for invalid_limit in [True, 1, 33, 128]:
        with pytest.raises(InvalidInput):
            validate_task_ids((), maximum=invalid_limit)


@pytest.mark.parametrize("state", list(O))
@pytest.mark.parametrize("verification", [None, *VerificationState])
def test_required_work_cannot_keep_a_stale_verification_after_reopening(
    state: O, verification: VerificationState | None
) -> None:
    if (state is O.COMPLETED) == (verification is not None):
        assert TaskRequirement("required", state, verification).verification is verification
    else:
        with pytest.raises(InvalidInput):
            TaskRequirement("required", state, verification)
    with pytest.raises(InvalidInput):
        TaskRequirement("required", "completed", verification)


def test_requirement_does_not_accept_a_string_as_a_verified_decision() -> None:
    for state in O:
        with pytest.raises(InvalidInput):
            TaskRequirement("required", state, "approved")


def test_owner_dependency_default_and_household_task_override_precedence() -> None:
    assert TaskRules().dependency_gate is DependencyGate.PERFORMED
    household = replace(TaskRules(), dependency_gate=DependencyGate.APPROVED)
    assert TaskOverrides().resolve(household).dependency_gate is DependencyGate.APPROVED
    override = TaskOverrides(dependency_gate=DependencyGate.PERFORMED)
    assert override.resolve(household).dependency_gate is DependencyGate.PERFORMED
    assert (
        replace(override, dependency_gate=None).resolve(household).dependency_gate
        is DependencyGate.APPROVED
    )
    for invalid in ["performed", "approved", None, True]:
        with pytest.raises(InvalidInput):
            replace(TaskRules(), dependency_gate=invalid)
    with pytest.raises(InvalidInput):
        TaskOverrides(dependency_gate="approved")
