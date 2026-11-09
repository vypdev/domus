"""Exact conserved allocation and immutable task-derived Points postings."""

import json
from dataclasses import asdict, dataclass

from domus.domain.errors import InvalidInput
from domus.domain.point_allocation import AllocationPolicy, allocate_points
from domus.domain.storage import JsonDocument, validate_identifier
from domus.domain.task_events import TaskLifecycleEvent
from domus.domain.task_values import validate_task_ids, validate_task_time
from domus.domain.tasks import TaskCycle


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
    policy_version: str = "conserve_total.v1"

    def __post_init__(self) -> None:
        for value in (self.event_id, self.cycle_id, self.definition_id):
            validate_identifier(value)
        validate_task_time(self.performed_at)
        validate_task_time(self.posted_at)
        if (
            type(self.precision) is not int
            or self.precision not in (0, 2)
            or self.policy_version != "conserve_total.v1"
            or not self.shares
        ):
            raise InvalidInput("invalid_points_posting")
        validate_task_ids(tuple(member for member, _ in self.shares))
        if self.next_recipient is not None:
            validate_identifier(self.next_recipient)
        if self.reverses is not None:
            validate_identifier(self.reverses)
        quantum = 100 if self.precision == 0 else 1
        if (
            any(
                type(amount) is not int
                or abs(amount) > 1_000_000
                or amount % quantum
                or (amount < 0 if self.reverses is None else amount > 0)
                for _, amount in self.shares
            )
            or abs(sum(amount for _, amount in self.shares)) > 1_000_000
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


def points_source_fingerprint(event: TaskLifecycleEvent) -> str:
    return JsonDocument(json.dumps(asdict(event))).fingerprint
