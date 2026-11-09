"""Exact shares and durable rotation inputs are testable without persistence."""

import pytest

from domus.domain.errors import InvalidInput
from domus.domain.point_allocation import (
    AllocationMode,
    AllocationPolicy,
    ShareRounding,
    allocate_points,
)

MEMBERS = ("charlie", "alex", "blair")


@pytest.mark.parametrize(
    ("mode", "precision", "rounding", "base", "expected"),
    [
        (AllocationMode.CONSERVE_TOTAL, 0, None, 1000, (400, 300, 300)),
        (AllocationMode.CONSERVE_TOTAL, 2, None, 1000, (334, 333, 333)),
        (AllocationMode.EQUAL_SHARE, 0, ShareRounding.FLOOR, 1000, (300, 300, 300)),
        (AllocationMode.EQUAL_SHARE, 0, ShareRounding.CEIL, 1000, (400, 400, 400)),
        (AllocationMode.EQUAL_SHARE, 2, ShareRounding.FLOOR, 1000, (333, 333, 333)),
        (AllocationMode.EQUAL_SHARE, 0, ShareRounding.CEIL, 900, (300, 300, 300)),
        (AllocationMode.EQUAL_SHARE, 0, ShareRounding.HALF_UP, 1050, (400, 400, 400)),
        (AllocationMode.EQUAL_SHARE, 0, ShareRounding.HALF_UP, 1049, (300, 300, 300)),
        (AllocationMode.FULL_PER_PARTICIPANT, 0, None, 1000, (1000, 1000, 1000)),
    ],
)
def test_exact_allocation_policy_matrix(mode, precision, rounding, base, expected):
    result = allocate_points(AllocationPolicy(mode, precision, rounding), base, MEMBERS)
    assert result.shares == tuple(zip(sorted(MEMBERS), expected, strict=True))
    assert result.total == sum(expected)


def test_remainder_resumes_after_missing_member_wraps_and_stays_for_an_exact_split():
    policy = AllocationPolicy()
    later = allocate_points(policy, 1000, MEMBERS, next_recipient="bruce")
    assert later.shares == (("alex", 300), ("blair", 300), ("charlie", 400))
    assert later.next_recipient == "alex"
    wrapped = allocate_points(policy, 1000, MEMBERS, next_recipient="zoe")
    assert wrapped.shares[0] == ("alex", 400)
    assert wrapped.next_recipient == "blair"
    assert allocate_points(policy, 900, MEMBERS, next_recipient="bruce").next_recipient == "bruce"


def test_manual_amounts_include_an_explicit_zero_and_never_round():
    policy = AllocationPolicy(AllocationMode.MANUAL, 2)
    shares = (("charlie", 0), ("alex", 333), ("blair", 444))
    allocation = allocate_points(policy, 1000, MEMBERS, manual_shares=shares)
    assert allocation.shares == tuple(sorted(shares))
    assert allocation.total == 777
    assert allocation.next_recipient is None


@pytest.mark.parametrize(
    ("mode", "precision", "rounding"),
    [
        ("manual", 0, None),
        (AllocationMode.CONSERVE_TOTAL, False, None),
        (AllocationMode.CONSERVE_TOTAL, 1, None),
        (AllocationMode.EQUAL_SHARE, 0, None),
        (AllocationMode.CONSERVE_TOTAL, 0, ShareRounding.FLOOR),
        (AllocationMode.EQUAL_SHARE, 0, "ceil"),
    ],
)
def test_contradictory_settings_are_rejected_before_calculation(mode, precision, rounding):
    with pytest.raises(InvalidInput, match="invalid_points_policy"):
        AllocationPolicy(mode, precision, rounding)


@pytest.mark.parametrize("base", [True, -1, 1_000_001])
def test_invalid_base_is_rejected(base):
    with pytest.raises(InvalidInput, match="invalid_points_base"):
        allocate_points(AllocationPolicy(), base, MEMBERS)


@pytest.mark.parametrize("members", [(), ("alex", "alex"), tuple(f"member-{n}" for n in range(33))])
def test_performers_must_be_distinct_and_bounded(members):
    with pytest.raises(InvalidInput):
        allocate_points(AllocationPolicy(), 1000, members)


@pytest.mark.parametrize(
    "mode", [AllocationMode.CONSERVE_TOTAL, AllocationMode.FULL_PER_PARTICIPANT]
)
def test_unrepresentable_bases_require_precision_two(mode):
    with pytest.raises(InvalidInput, match="points_precision_two_required"):
        allocate_points(AllocationPolicy(mode), 1050, MEMBERS)
    assert allocate_points(AllocationPolicy(mode, 2), 1050, MEMBERS).shares


@pytest.mark.parametrize(
    "shares",
    [
        (),
        (("alex", 0), ("alex", 100), ("charlie", 200)),
        (("alex", True), ("blair", 100), ("charlie", 200)),
        (("alex", -100), ("blair", 100), ("charlie", 200)),
        (("alex", 1_000_100), ("blair", 100), ("charlie", 200)),
        (("alex", 50), ("blair", 100), ("charlie", 200)),
    ],
)
def test_manual_shares_require_one_representable_amount_per_performer(shares):
    with pytest.raises(InvalidInput, match="invalid_manual_shares"):
        allocate_points(
            AllocationPolicy(AllocationMode.MANUAL), 1000, MEMBERS, manual_shares=shares
        )


def test_manual_amounts_cannot_override_a_conserved_policy():
    with pytest.raises(InvalidInput, match="invalid_manual_shares"):
        allocate_points(AllocationPolicy(), 1000, MEMBERS, manual_shares=(("alex", 100),))


def test_frozen_allocation_rejects_inconsistent_evidence():
    from dataclasses import replace

    from domus.domain.point_allocation import (
        AllocationSetting,
        CompletionAllocation,
        PointAllocation,
    )

    conserved = AllocationPolicy()
    split = allocate_points(conserved, 1000, MEMBERS)
    stored = CompletionAllocation(conserved, 0, None, 1000, None, split)
    with pytest.raises(InvalidInput, match="invalid_points_policy"):
        AllocationSetting("not-a-policy", 1)
    for changes in (
        {"policy": "conserved"},
        {"override_definition_id": "definition"},
        {"allocation": PointAllocation(split.shares, "charlie")},
    ):
        with pytest.raises(InvalidInput, match="invalid_points_allocation"):
            replace(stored, **changes)
    with pytest.raises(InvalidInput, match="invalid_points_allocation"):
        CompletionAllocation(
            AllocationPolicy(AllocationMode.FULL_PER_PARTICIPANT), 1, None, 1000, "alex", split
        )


def test_completion_requires_a_valid_preview_token():
    from domus.application.task_requests import CompleteTask

    with pytest.raises(InvalidInput, match="invalid_allocation_preview"):
        CompleteTask("task", 1, MEMBERS, 100, allocation_fingerprint="G" * 64)


def test_exact_32_performer_upper_bound():
    members = tuple(f"member-{index:02}" for index in range(32))
    split = allocate_points(
        AllocationPolicy(AllocationMode.FULL_PER_PARTICIPANT), 1_000_000, members
    )
    assert split.total == 32_000_000 and len(split.shares) == 32
