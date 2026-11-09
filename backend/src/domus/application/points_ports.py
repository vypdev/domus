"""Transaction-local Points persistence for the trusted task lifecycle consumer."""

from collections.abc import Iterable
from typing import Protocol

from domus.application.family_ports import FamilyLedgerEntry, FamilyWork
from domus.domain.points import PointsPosting
from domus.domain.task_events import TaskLifecycleEvent


class PointsRepository(Protocol):
    def position(self, household_id: str) -> int: ...
    def processed(self, household_id: str, event_id: str) -> str | None: ...
    def next_recipient(self, household_id: str, definition_id: str) -> str | None: ...
    def ledger(self, household_id: str, cycle_id: str) -> tuple[PointsPosting, ...]: ...
    def add(
        self, event: TaskLifecycleEvent, fingerprint: str, posting: PointsPosting | None
    ) -> None: ...

    def member_totals(
        self, household_id: str, member_id: str, start: int, end: int
    ) -> tuple[int, int]: ...
    def member_history(
        self, household_id: str, member_id: str, after: str | None, limit: int
    ) -> tuple[FamilyLedgerEntry, ...]: ...
    def member_work(
        self, household_id: str, member_id: str, start: int, end: int
    ) -> Iterable[FamilyWork]: ...
