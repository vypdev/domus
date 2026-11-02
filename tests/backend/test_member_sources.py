"""Presentation source facts cannot supply an identity or household permission grant."""

from dataclasses import FrozenInstanceError

import pytest

from domus.domain.errors import InvalidInput
from domus.domain.member_sources import (
    HAProfile,
    MemberSourceSnapshot,
    ProfileDirectory,
    ProfileResult,
    SourceState,
)

USER, OTHER = "a" * 32, "b" * 32


@pytest.mark.parametrize("name", [None, "Name", "<b>Literal</b>", "😀" * 256, "  Exact  "])
def test_source_names_remain_bounded_literal_facts_without_role_or_avatar(name):
    value = HAProfile(USER, name, True)
    assert value.name == name and value.eligible is True
    assert not hasattr(value, "role") and not hasattr(value, "avatar")
    with pytest.raises(FrozenInstanceError):
        value.name = "Changed"


@pytest.mark.parametrize("name", [1, False, "", " ", "A" * 257, "\tName", "Name\x7f", "\ud800"])
def test_invalid_source_text_cannot_become_a_verified_label(name):
    with pytest.raises(InvalidInput):
        HAProfile(USER, name, True)


@pytest.mark.parametrize("eligible", [None, 0, "true"])
def test_source_eligibility_is_an_exact_boolean(eligible):
    with pytest.raises(InvalidInput):
        HAProfile(USER, "Name", eligible)


def test_available_empty_directory_is_distinct_from_unavailable_and_confirmed_absence():
    empty = ProfileDirectory(SourceState.AVAILABLE)
    missing = MemberSourceSnapshot(USER, empty, ProfileResult(SourceState.ABSENT))
    assert missing.profile(USER).state is SourceState.ABSENT
    assert missing.profile(OTHER).state is SourceState.ABSENT
    for state in (SourceState.DENIED, SourceState.UNAVAILABLE):
        snapshot = MemberSourceSnapshot(USER, ProfileDirectory(state), ProfileResult(state))
        assert snapshot.profile(OTHER).state is state


def test_denied_directory_can_retain_only_the_exact_own_verified_profile():
    own = HAProfile(USER, "Same name", True)
    snapshot = MemberSourceSnapshot(
        USER, ProfileDirectory(SourceState.DENIED), ProfileResult(SourceState.AVAILABLE, own)
    )
    assert snapshot.profile(USER).profile is own
    assert snapshot.profile(OTHER).state is SourceState.DENIED


def test_available_directory_keeps_distinct_accounts_and_ineligible_source_facts():
    first, second = HAProfile(USER, "Same", True), HAProfile(OTHER, "Same", False)
    snapshot = MemberSourceSnapshot(
        USER,
        ProfileDirectory(SourceState.AVAILABLE, (first, second)),
        ProfileResult(SourceState.AVAILABLE, first),
    )
    assert snapshot.profile(USER).profile == first
    assert snapshot.profile(OTHER).profile == second
    assert snapshot.profile("missing").state is SourceState.ABSENT


@pytest.mark.parametrize(
    "state,profile",
    [
        (SourceState.AVAILABLE, None),
        (SourceState.AVAILABLE, "forged"),
        (SourceState.DENIED, HAProfile(USER, "Name", True)),
        ("available", None),
    ],
)
def test_profile_result_rejects_unproven_partial_or_unknown_states(state, profile):
    with pytest.raises(InvalidInput):
        ProfileResult(state, profile)


@pytest.mark.parametrize(
    "state,profiles",
    [
        (SourceState.ABSENT, ()),
        ("available", ()),
        (SourceState.AVAILABLE, []),
        (SourceState.AVAILABLE, (None,)),
        (SourceState.AVAILABLE, (HAProfile(USER, None, True),) * 2),
        (SourceState.AVAILABLE, tuple(HAProfile(f"user-{n}", None, True) for n in range(257))),
        (SourceState.UNAVAILABLE, (HAProfile(USER, None, True),)),
    ],
)
def test_directory_facts_are_closed_unique_complete_and_bounded(state, profiles):
    with pytest.raises(InvalidInput):
        ProfileDirectory(state, profiles)


@pytest.mark.parametrize(
    "directory,own",
    [
        ("forged", ProfileResult(SourceState.ABSENT)),
        (ProfileDirectory(SourceState.UNAVAILABLE), None),
        (
            ProfileDirectory(SourceState.DENIED),
            ProfileResult(SourceState.AVAILABLE, HAProfile(OTHER, None, True)),
        ),
        (ProfileDirectory(SourceState.AVAILABLE), ProfileResult(SourceState.UNAVAILABLE)),
        (
            ProfileDirectory(SourceState.AVAILABLE, (HAProfile(USER, "Name", True),)),
            ProfileResult(SourceState.ABSENT),
        ),
    ],
)
def test_snapshot_cannot_substitute_a_subject_or_contradict_its_complete_directory(directory, own):
    with pytest.raises(InvalidInput):
        MemberSourceSnapshot(USER, directory, own)
