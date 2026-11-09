"""Exact conserved allocation and immutable task-derived Points postings."""

import json
from dataclasses import asdict, dataclass

from domus.domain.errors import InvalidInput, StorageFailure
from domus.domain.point_allocation import (
    MAX_POINT_SHARE,
    AllocationPolicy,
    CompletionAllocation,
    allocate_points,
)
from domus.domain.storage import JsonDocument, validate_identifier
from domus.domain.task_events import TaskLifecycleEvent
from domus.domain.task_values import validate_task_ids, validate_task_time
from domus.domain.tasks import TaskCycle

LEGACY_POLICY = "conserve_total.v1"
CONFIGURED_POLICY = "allocation.v2"


@dataclass(frozen=True, slots=True)
class PointsPosting:
    event_id: str
    cycle_id: str
    definition_id: str
    shares: tuple[tuple[str, int], ...]
    performed_at: int
    posted_at: int
    precision: int
    next_recipient: str | None
    reverses: str | None = None
    policy_version: str = LEGACY_POLICY

    def __post_init__(self) -> None:
        for value in (self.event_id, self.cycle_id, self.definition_id):
            validate_identifier(value)
        validate_task_time(self.performed_at)
        validate_task_time(self.posted_at)
        if (
            type(self.precision) is not int
            or self.precision not in (0, 2)
            or self.policy_version not in (LEGACY_POLICY, CONFIGURED_POLICY)
            or not 1 <= len(self.shares) <= 32
        ):
            raise InvalidInput("invalid_points_posting")
        validate_task_ids(tuple(member for member, _ in self.shares))
        if self.next_recipient is not None:
            validate_identifier(self.next_recipient)
        if self.reverses is not None:
            validate_identifier(self.reverses)
        quantum = 100 if self.precision == 0 else 1
        if any(
            type(amount) is not int
            or abs(amount) > MAX_POINT_SHARE
            or amount % quantum
            or (amount < 0 if self.reverses is None else amount > 0)
            for _, amount in self.shares
        ) or (
            self.policy_version == LEGACY_POLICY
            and abs(sum(amount for _, amount in self.shares)) > MAX_POINT_SHARE
        ):
            raise InvalidInput("invalid_points_posting")

    def reverse(self, event_id: str, posted_at: int) -> PointsPosting:
        if self.reverses is not None:
            raise InvalidInput("invalid_points_reversal")
        return PointsPosting(
            event_id,
            self.cycle_id,
            self.definition_id,
            tuple((member, -amount) for member, amount in self.shares),
            self.performed_at,
            posted_at,
            self.precision,
            None,
            self.event_id,
            self.policy_version,
        )


def conserved_shares(
    cycle: TaskCycle, next_recipient: str | None
) -> tuple[tuple[tuple[str, int], ...], int, str | None]:
    base = cycle.rules.point_value_minor
    precision = 2 if base % 100 else 0
    allocation = allocate_points(
        AllocationPolicy(precision=precision),
        base,
        tuple(performer.member_id for performer in cycle.performers),
        next_recipient=next_recipient,
    )
    return allocation.shares, precision, allocation.next_recipient


def conserve_points(
    event: TaskLifecycleEvent, posted_at: int, next_recipient: str | None
) -> PointsPosting:
    shares, precision, following = conserved_shares(event.cycle, next_recipient)
    return PointsPosting(
        event.event_id,
        event.cycle.cycle_id,
        event.definition_id,
        shares,
        event.cycle.performed_at,
        posted_at,
        precision,
        following,
    )


def require_allocation_cycle(
    snapshot: CompletionAllocation, cycle: TaskCycle, definition_id: str
) -> None:
    performers = tuple(sorted(person.member_id for person in cycle.performers))
    if (
        snapshot.base != cycle.rules.point_value_minor
        or snapshot.override_definition_id not in (None, definition_id)
        or tuple(member for member, _ in snapshot.allocation.shares) != performers
    ):
        raise StorageFailure("invalid_points_allocation")


def frozen_points(
    event: TaskLifecycleEvent, posted_at: int, snapshot: CompletionAllocation
) -> PointsPosting:
    require_allocation_cycle(snapshot, event.cycle, event.definition_id)
    return PointsPosting(
        event.event_id,
        event.cycle.cycle_id,
        event.definition_id,
        snapshot.allocation.shares,
        event.cycle.performed_at,
        posted_at,
        snapshot.policy.precision,
        snapshot.allocation.next_recipient,
        policy_version=CONFIGURED_POLICY if snapshot.policy_revision else LEGACY_POLICY,
    )


def points_source_fingerprint(event: TaskLifecycleEvent) -> str:
    return JsonDocument(json.dumps(asdict(event))).fingerprint
