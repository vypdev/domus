"""Explicit nominal and resolved temporal facts; none establishes scheduling authority."""

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from domus.domain.errors import InvalidInput
from domus.domain.identity import validate_revision

MAX_INSTANT_MS = 253_402_300_799_999
_EPOCH = datetime(1970, 1, 1)


class FoldPolicy(StrEnum):
    FIRST = "first_instant"
    SECOND = "second_instant"


class TimeResolution(StrEnum):
    EXACT = "exact"
    FOLD_FIRST = "fold_first"
    FOLD_SECOND = "fold_second"
    GAP_FIRST_VALID = "gap_first_valid"


@dataclass(frozen=True, slots=True)
class NominalTime:
    local: datetime

    def __post_init__(self) -> None:
        if (
            type(self.local) is not datetime
            or self.local.tzinfo is not None
            or self.local.year < 1970
            or self.local.fold != 0
            or self.local.microsecond % 1000 != 0
        ):
            raise InvalidInput("invalid_recurrence_local_time")


@dataclass(frozen=True, slots=True)
class RelativeInterval:
    days: int

    def __post_init__(self) -> None:
        if type(self.days) is not int or not 1 <= self.days <= 36600:
            raise InvalidInput("invalid_relative_interval")


@dataclass(frozen=True, slots=True)
class TimePolicy:
    zone: str
    data_identity: str
    repeated_time: FoldPolicy = FoldPolicy.FIRST
    revision: int = 1

    def __post_init__(self) -> None:
        if (
            not isinstance(self.zone, str)
            or re.fullmatch(r"[A-Za-z0-9_+\-/]{1,128}", self.zone) is None
            or any(not part for part in self.zone.split("/"))
            or not isinstance(self.data_identity, str)
            or re.fullmatch(r"[A-Za-z0-9:/_.\-]{1,128}", self.data_identity) is None
            or not isinstance(self.repeated_time, FoldPolicy)
        ):
            raise InvalidInput("invalid_recurrence_time_policy")
        validate_revision(self.revision)


@dataclass(frozen=True, slots=True)
class ResolvedTime:
    nominal: NominalTime
    policy: TimePolicy
    resolved_local: datetime
    offset_seconds: int
    resolution: TimeResolution
    zone_digest: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.nominal, NominalTime)
            or not isinstance(self.policy, TimePolicy)
            or type(self.offset_seconds) is not int
            or not -86400 < self.offset_seconds < 86400
            or not isinstance(self.resolution, TimeResolution)
            or not isinstance(self.zone_digest, str)
            or re.fullmatch(r"[a-f0-9]{64}", self.zone_digest) is None
        ):
            raise InvalidInput("invalid_recurrence_resolution")
        NominalTime(self.resolved_local)
        if (
            self.resolution is TimeResolution.GAP_FIRST_VALID
            and self.resolved_local <= self.nominal.local
        ) or (
            self.resolution is not TimeResolution.GAP_FIRST_VALID
            and self.resolved_local != self.nominal.local
        ):
            raise InvalidInput("invalid_recurrence_resolution")
        if (
            self.resolution is TimeResolution.FOLD_FIRST
            and self.policy.repeated_time is not FoldPolicy.FIRST
        ) or (
            self.resolution is TimeResolution.FOLD_SECOND
            and self.policy.repeated_time is not FoldPolicy.SECOND
        ):
            raise InvalidInput("invalid_recurrence_resolution")
        if not 0 <= self.instant_ms <= MAX_INSTANT_MS:
            raise InvalidInput("recurrence_time_out_of_range")

    @property
    def instant_ms(self) -> int:
        delta = self.resolved_local - _EPOCH
        return (
            delta.days * 86_400_000
            + delta.seconds * 1000
            + delta.microseconds // 1000
            - self.offset_seconds * 1000
        )
