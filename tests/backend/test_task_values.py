"""Task input boundaries preserve real text and reject ambiguous or malformed values."""

from dataclasses import FrozenInstanceError, replace

import pytest

from domus.domain.errors import InvalidInput
from domus.domain.identity import Role
from domus.domain.task_values import (
    MaterialRecording,
    Priority,
    TaskContent,
    TaskPerformer,
    TaskRules,
    VerificationMode,
    validate_performers,
    validate_task_ids,
)


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
