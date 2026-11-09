"""The versioned allocation settings and immutable completion evidence share a transaction."""

from typing import Protocol

from domus.domain.point_allocation import AllocationSetting, CompletionAllocation


class PointAllocations(Protocol):
    def setting(self, household_id: str, definition_id: str | None) -> AllocationSetting | None: ...
    def put_setting(
        self, household_id: str, definition_id: str | None, setting: AllocationSetting
    ) -> None: ...
    def snapshot(self, household_id: str, cycle_id: str) -> CompletionAllocation | None: ...
    def last_conserved(
        self, household_id: str, definition_id: str
    ) -> CompletionAllocation | None: ...
    def freeze(
        self, household_id: str, cycle_id: str, definition_id: str, snapshot: CompletionAllocation
    ) -> None: ...
