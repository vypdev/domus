"""Read-only facts for the member-scoped Family projection."""

from dataclasses import dataclass

from domus.domain.tasks import TaskCycle


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


@dataclass(frozen=True, slots=True)
class FamilyWork:
    cycle: TaskCycle
    definition_id: str
    started_at: int | None
    awaiting_credit: bool
