"""Read-only facts for the member-scoped Family projection."""

from dataclasses import dataclass
from typing import Self

from domus.domain.point_allocation import AllocationMode, CompletionAllocation, ShareRounding
from domus.domain.tasks import TaskCycle


@dataclass(frozen=True, slots=True)
class FamilyAllocationEvidence:
    mode: AllocationMode
    precision: int
    rounding: ShareRounding | None
    policy_revision: int
    task_override: bool
    base_minor: int
    total_minor: int
    shares: tuple[tuple[str, int], ...]

    @classmethod
    def legacy(cls, precision: int, shares: tuple[tuple[str, int], ...]) -> Self:
        total = sum(amount for _, amount in shares)
        return cls(AllocationMode.CONSERVE_TOTAL, precision, None, 0, False, total, total, shares)

    @classmethod
    def from_snapshot(cls, snapshot: CompletionAllocation) -> Self:
        return cls(
            snapshot.policy.mode,
            snapshot.policy.precision,
            snapshot.policy.rounding,
            snapshot.policy_revision,
            snapshot.override_definition_id is not None,
            snapshot.base,
            snapshot.allocation.total,
            snapshot.allocation.shares,
        )


@dataclass(frozen=True, slots=True)
class FamilyLedgerEntry:
    event_id: str
    cycle_id: str
    occurrence_id: str
    title: str
    amount_minor: int
    performed_at: int
    verified_at: int | None
    posted_at: int
    reverses: str | None
    policy_version: str
    allocation: FamilyAllocationEvidence


@dataclass(frozen=True, slots=True)
class FamilyWork:
    cycle: TaskCycle
    definition_id: str
    title: str
    started_at: int | None
    awaiting_credit: bool
