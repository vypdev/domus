"""Exact collaborative allocation over a verified set of performer IDs."""

from bisect import bisect_left
from dataclasses import dataclass
from enum import StrEnum

from domus.domain.errors import InvalidInput
from domus.domain.storage import validate_identifier
from domus.domain.task_values import validate_task_ids

MAX_POINT_SHARE = 1_000_000


class AllocationMode(StrEnum):
    CONSERVE_TOTAL = "conserve_total"
    EQUAL_SHARE = "equal_share"
    FULL_PER_PARTICIPANT = "full_per_participant"
    MANUAL = "manual"


class ShareRounding(StrEnum):
    FLOOR = "floor"
    CEIL = "ceil"
    HALF_UP = "half_up"


@dataclass(frozen=True, slots=True)
class AllocationPolicy:
    mode: AllocationMode = AllocationMode.CONSERVE_TOTAL
    precision: int = 0
    rounding: ShareRounding | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.mode, AllocationMode)
            or type(self.precision) is not int
            or self.precision not in (0, 2)
            or (self.mode is AllocationMode.EQUAL_SHARE) != (self.rounding is not None)
            or (self.rounding is not None and not isinstance(self.rounding, ShareRounding))
        ):
            raise InvalidInput("invalid_points_policy")

    @property
    def quantum(self) -> int:
        return 100 if self.precision == 0 else 1


@dataclass(frozen=True, slots=True)
class PointAllocation:
    shares: tuple[tuple[str, int], ...]
    next_recipient: str | None

    @property
    def total(self) -> int:
        return sum(amount for _, amount in self.shares)


def _conserved(
    base: int, members: tuple[str, ...], quantum: int, next_recipient: str | None
) -> PointAllocation:
    share, remainder = divmod(base // quantum, len(members))
    start = bisect_left(members, next_recipient or "")
    shares = tuple(
        (member, (share + int((index - start) % len(members) < remainder)) * quantum)
        for index, member in enumerate(members)
    )
    following = members[(start + remainder) % len(members)] if remainder else next_recipient
    return PointAllocation(shares, following)


def _manual(
    members: tuple[str, ...], shares: tuple[tuple[str, int], ...], quantum: int
) -> PointAllocation:
    supplied = tuple(member for member, _ in shares)
    if tuple(sorted(supplied)) != members or any(
        type(amount) is not int or not 0 <= amount <= MAX_POINT_SHARE or amount % quantum
        for _, amount in shares
    ):
        raise InvalidInput("invalid_manual_shares")
    return PointAllocation(tuple(sorted(shares)), None)


def allocate_points(
    policy: AllocationPolicy,
    base: int,
    performer_ids: tuple[str, ...],
    *,
    next_recipient: str | None = None,
    manual_shares: tuple[tuple[str, int], ...] = (),
) -> PointAllocation:
    if type(base) is not int or not 0 <= base <= MAX_POINT_SHARE:
        raise InvalidInput("invalid_points_base")
    if not 1 <= len(performer_ids) <= 32:
        raise InvalidInput("invalid_task_performers")
    validate_task_ids(performer_ids)
    if next_recipient is not None:
        validate_identifier(next_recipient)
    members = tuple(sorted(performer_ids))
    quantum = policy.quantum
    if policy.mode is AllocationMode.MANUAL:
        return _manual(members, manual_shares, quantum)
    if manual_shares:
        raise InvalidInput("invalid_manual_shares")
    if policy.mode is AllocationMode.EQUAL_SHARE:
        denominator = len(members) * quantum
        units, remainder = divmod(base, denominator)
        if (policy.rounding is ShareRounding.CEIL and remainder != 0) or (
            policy.rounding is ShareRounding.HALF_UP and 2 * remainder >= denominator
        ):
            units += 1
        return PointAllocation(tuple((member, units * quantum) for member in members), None)
    if base % quantum:
        raise InvalidInput("points_precision_two_required")
    if policy.mode is AllocationMode.FULL_PER_PARTICIPANT:
        return PointAllocation(tuple((member, base) for member in members), None)
    return _conserved(base, members, quantum, next_recipient)
