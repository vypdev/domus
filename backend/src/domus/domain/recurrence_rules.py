"""Closed calendar patterns and nominal period facts; no provider or scheduling authority."""

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum

from domus.domain.errors import InvalidInput
from domus.domain.recurrence_time import MAX_INSTANT_MS, NominalTime


class Frequency(StrEnum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    YEARLY = "YEARLY"


class Weekday(StrEnum):
    MO = "MO"
    TU = "TU"
    WE = "WE"
    TH = "TH"
    FR = "FR"
    SA = "SA"
    SU = "SU"

    @property
    def number(self) -> int:
        return tuple(Weekday).index(self)


@dataclass(frozen=True, slots=True)
class NominalDate:
    local: date

    def __post_init__(self) -> None:
        if type(self.local) is not date or self.local.year < 1970:
            raise InvalidInput("invalid_recurrence_date")


type NominalSlot = NominalDate | NominalTime


@dataclass(frozen=True, slots=True)
class ByDay:
    weekday: Weekday
    ordinal: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.weekday, Weekday) or (
            self.ordinal is not None
            and (type(self.ordinal) is not int or self.ordinal == 0 or not -5 <= self.ordinal <= 5)
        ):
            raise InvalidInput("invalid_recurrence_weekday")


def _integers(values: tuple[int, ...], maximum: int, lower: int, upper: int) -> None:
    if (
        type(values) is not tuple
        or len(values) > maximum
        or any(type(v) is not int or v == 0 or not lower <= v <= upper for v in values)
        or len(set(values)) != len(values)
    ):
        raise InvalidInput("invalid_recurrence_selector")


@dataclass(frozen=True, slots=True)
class FixedPattern:
    start: NominalSlot
    frequency: Frequency
    interval: int = 1
    week_start: Weekday = Weekday.MO
    by_day: tuple[ByDay, ...] = ()
    by_month: tuple[int, ...] = ()
    by_month_day: tuple[int, ...] = ()
    by_set_position: tuple[int, ...] = ()
    count: int | None = None
    until: NominalDate | int | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.start, NominalDate | NominalTime)
            or not isinstance(self.frequency, Frequency)
            or type(self.interval) is not int
            or not 1 <= self.interval <= 366
            or not isinstance(self.week_start, Weekday)
            or (
                isinstance(self.start, NominalTime)
                and (self.start.local.second != 0 or self.start.local.microsecond != 0)
            )
        ):
            raise InvalidInput("invalid_recurrence_pattern")
        if (
            type(self.by_day) is not tuple
            or len(self.by_day) > 35
            or any(not isinstance(v, ByDay) for v in self.by_day)
            or len(set(self.by_day)) != len(self.by_day)
        ):
            raise InvalidInput("invalid_recurrence_selector")
        _integers(self.by_month, 12, 1, 12)
        _integers(self.by_month_day, 62, -31, 31)
        _integers(self.by_set_position, 32, -366, 366)
        if (
            (self.frequency is Frequency.WEEKLY and self.by_month_day)
            or (
                self.frequency in (Frequency.DAILY, Frequency.WEEKLY)
                and any(v.ordinal is not None for v in self.by_day)
            )
            or (self.by_set_position and not (self.by_month or self.by_month_day or self.by_day))
        ):
            raise InvalidInput("invalid_recurrence_combination")
        if self.count is not None and (
            type(self.count) is not int or not 1 <= self.count <= 100000 or self.until is not None
        ):
            raise InvalidInput("invalid_recurrence_end")
        if self.until is not None:
            if isinstance(self.start, NominalDate):
                if not isinstance(self.until, NominalDate) or self.until.local < self.start.local:
                    raise InvalidInput("invalid_recurrence_end")
            elif type(self.until) is not int or not 0 <= self.until <= MAX_INSTANT_MS:
                raise InvalidInput("invalid_recurrence_end")
        object.__setattr__(
            self,
            "by_day",
            tuple(sorted(self.by_day, key=lambda v: (v.weekday.number, v.ordinal or 0))),
        )
        for name in ("by_month", "by_month_day", "by_set_position"):
            object.__setattr__(self, name, tuple(sorted(getattr(self, name))))

    @property
    def fingerprint(self) -> str:
        value = {
            "version": 1,
            "start_kind": "date" if isinstance(self.start, NominalDate) else "time",
            "start": self.start.local.isoformat(),
            "frequency": self.frequency.value,
            "interval": self.interval,
            "week_start": self.week_start.value,
            "by_day": [(v.weekday.value, v.ordinal) for v in self.by_day],
            "by_month": self.by_month,
            "by_month_day": self.by_month_day,
            "by_set_position": self.by_set_position,
            "count": self.count,
            "until": {"date": self.until.local.isoformat()}
            if isinstance(self.until, NominalDate)
            else self.until,
        }
        return hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


def slot_datetime(slot: NominalSlot) -> datetime:
    """Internal nominal comparison value; a date-only result never becomes a UTC instant."""
    if isinstance(slot, NominalDate):
        return datetime(slot.local.year, slot.local.month, slot.local.day)
    return slot.local


@dataclass(frozen=True, slots=True)
class PeriodCandidates:
    slots: tuple[NominalSlot, ...]
    terminal: bool = False

    def __post_init__(self) -> None:
        if (
            type(self.slots) is not tuple
            or len(self.slots) > 366
            or any(not isinstance(v, NominalDate | NominalTime) for v in self.slots)
            or type(self.terminal) is not bool
            or (self.terminal and self.slots)
            or (self.slots and any(type(v) is not type(self.slots[0]) for v in self.slots))
            or any(
                slot_datetime(a) >= slot_datetime(b)
                for a, b in zip(self.slots, self.slots[1:], strict=False)
            )
        ):
            raise InvalidInput("invalid_recurrence_period")
