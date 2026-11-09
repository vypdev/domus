"""Exact conserved allocation and immutable task-derived Points postings."""

import json
from bisect import bisect_left
from dataclasses import asdict, dataclass

from domus.domain.errors import InvalidInput
from domus.domain.storage import JsonDocument, validate_identifier
from domus.domain.task_events import TaskLifecycleEvent
from domus.domain.task_values import validate_task_ids, validate_task_time


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


def conserve_points(
    event: TaskLifecycleEvent, posted_at: int, next_recipient: str | None
) -> PointsPosting:
    members = sorted(performer.member_id for performer in event.cycle.performers)
    value = event.cycle.rules.point_value_minor
    quantum = 1 if value % 100 else 100
    share, remainder = divmod(value // quantum, len(members))
    start = bisect_left(members, next_recipient or "")
    shares = tuple(
        (member, (share + int((index - start) % len(members) < remainder)) * quantum)
        for index, member in enumerate(members)
    )
    return PointsPosting(
        event.event_id,
        event.cycle.cycle_id,
        event.definition_id,
        shares,
        event.cycle.performed_at,
        posted_at,
        2 if quantum == 1 else 0,
        members[(start + remainder) % len(members)] if remainder else next_recipient,
    )


def points_source_fingerprint(event: TaskLifecycleEvent) -> str:
    return JsonDocument(json.dumps(asdict(event))).fingerprint
