"""Immutable bounded planning progress; these records are not persisted execution proof."""

import re
from dataclasses import dataclass

from domus.domain.errors import InvalidInput
from domus.domain.recurrence_rules import NominalDate, NominalSlot
from domus.domain.recurrence_time import NominalTime, ResolvedTime


@dataclass(frozen=True, slots=True)
class FixedCursor:
    binding: str
    period_index: int = 0
    offset: int = 0
    nominal_count: int = 0
    closed: bool = False

    def __post_init__(self) -> None:
        if (
            not isinstance(self.binding, str)
            or re.fullmatch(r"[a-f0-9]{64}", self.binding) is None
            or type(self.period_index) is not int
            or not 0 <= self.period_index <= 2**63 - 1
            or type(self.offset) is not int
            or not 0 <= self.offset <= 366
            or type(self.nominal_count) is not int
            or not 0 <= self.nominal_count <= 2**63 - 1
            or type(self.closed) is not bool
        ):
            raise InvalidInput("invalid_recurrence_cursor")


@dataclass(frozen=True, slots=True)
class PlannedFixedSlot:
    nominal: NominalSlot
    resolved: ResolvedTime | None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.nominal, NominalDate | NominalTime)
            or (isinstance(self.nominal, NominalDate) and self.resolved is not None)
            or (
                isinstance(self.nominal, NominalTime)
                and (
                    not isinstance(self.resolved, ResolvedTime)
                    or self.resolved.nominal != self.nominal
                )
            )
        ):
            raise InvalidInput("invalid_recurrence_slot")


@dataclass(frozen=True, slots=True)
class FixedBatch:
    slots: tuple[PlannedFixedSlot, ...]
    cursor: FixedCursor
    periods_scanned: int
    range_complete: bool


@dataclass(frozen=True, slots=True)
class StartCheck:
    matches: bool
    first_permitted: NominalSlot | None
    search_complete: bool
    continuation: FixedCursor
