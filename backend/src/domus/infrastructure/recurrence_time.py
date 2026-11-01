"""Pinned package TZif bytes and explicit first-valid/fold policy, isolated from global TZPATH."""

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from importlib.metadata import PackageNotFoundError, version
from importlib.resources import files
from io import BytesIO
from struct import error as StructError
from zoneinfo import ZoneInfo

from domus.domain.errors import IntegrationUnavailable, InvalidInput
from domus.domain.recurrence_time import (
    MAX_INSTANT_MS,
    FoldPolicy,
    NominalTime,
    RelativeInterval,
    ResolvedTime,
    TimePolicy,
    TimeResolution,
)

TIMEZONE_DATA_IDENTITY = "tzdata:2026.6/iana:2026f"
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_MAX_SOURCE_BYTES = 1_048_576


class PackagedTimeZones:
    def read(self, zone: str) -> bytes:
        # The catalog distinguishes an unknown key from a missing known resource.
        # Read only bounded packaged data; never consult system files or mutate TZPATH.
        try:
            if version("tzdata") != "2026.6":
                raise IntegrationUnavailable("timezone_data_mismatch")
            root = files("tzdata")
            with root.joinpath("zones").open("rb") as stream:
                catalog = stream.read(65537)
            if len(catalog) > 65536:
                raise IntegrationUnavailable("timezone_source_corrupt")
            known = catalog.decode("ascii").splitlines()
            with root.joinpath("zoneinfo", "tzdata.zi").open("rb") as stream:
                if stream.readline(64) != b"# version 2026f\n":
                    raise IntegrationUnavailable("timezone_data_mismatch")
            if zone not in known:
                raise InvalidInput("unknown_time_zone")
            with root.joinpath("zoneinfo", *zone.split("/")).open("rb") as stream:
                data = stream.read(_MAX_SOURCE_BYTES + 1)
            if not data or len(data) > _MAX_SOURCE_BYTES:
                raise IntegrationUnavailable("timezone_source_corrupt")
            return data
        except PackageNotFoundError, ModuleNotFoundError, OSError:
            raise IntegrationUnavailable("timezone_source_unavailable") from None
        except UnicodeError:
            raise IntegrationUnavailable("timezone_source_corrupt") from None


def _candidates(local: datetime, zone: ZoneInfo) -> tuple[datetime, ...]:
    candidates = set()
    for fold in (0, 1):
        utc = local.replace(tzinfo=zone, fold=fold).astimezone(UTC)
        if utc.astimezone(zone).replace(tzinfo=None, fold=0) == local:
            candidates.add(utc)
    return tuple(sorted(candidates))


def _first_valid(local: datetime, zone: ZoneInfo) -> datetime:
    # Both fold interpretations of a TZif forward gap fail round-trip existence.
    # One round-trip lies beyond that same gap. Binary search its closed interval
    # in integer milliseconds instead of applying the provider's full-gap shift.
    upper = max(
        local.replace(tzinfo=zone, fold=fold)
        .astimezone(UTC)
        .astimezone(zone)
        .replace(tzinfo=None, fold=0)
        for fold in (0, 1)
    )
    delta = upper - local
    high = delta.days * 86_400_000 + delta.seconds * 1000 + delta.microseconds // 1000
    if not 0 < high <= 172_800_000:
        raise IntegrationUnavailable("timezone_resolution_unavailable")
    low = 0
    while low + 1 < high:
        middle = (low + high) // 2
        if _candidates(local + timedelta(milliseconds=middle), zone):
            high = middle
        else:
            low = middle
    return local + timedelta(milliseconds=high)


@dataclass(slots=True)
class PinnedRecurrenceTime:
    source: PackagedTimeZones = field(default_factory=PackagedTimeZones)

    @property
    def data_identity(self) -> str:
        return TIMEZONE_DATA_IDENTITY

    def require_policy(self, policy: TimePolicy) -> None:
        self._zone(policy)

    def _zone(self, policy: TimePolicy) -> tuple[ZoneInfo, str]:
        if policy.data_identity != self.data_identity:
            raise IntegrationUnavailable("timezone_data_mismatch")
        data = self.source.read(policy.zone)
        try:
            return ZoneInfo.from_file(BytesIO(data), key=policy.zone), hashlib.sha256(
                data
            ).hexdigest()
        except ValueError, EOFError, StructError:
            raise IntegrationUnavailable("timezone_source_corrupt") from None

    def resolve(self, nominal: NominalTime, policy: TimePolicy) -> ResolvedTime:
        zone, digest = self._zone(policy)
        return self._resolve(nominal, policy, zone, digest)

    def _resolve(
        self, nominal: NominalTime, policy: TimePolicy, zone: ZoneInfo, digest: str
    ) -> ResolvedTime:
        try:
            local = nominal.local
            candidates = _candidates(local, zone)
            reason = TimeResolution.EXACT
            if not candidates:
                local = _first_valid(local, zone)
                candidates = _candidates(local, zone)
                reason = TimeResolution.GAP_FIRST_VALID
            elif len(candidates) == 2:
                reason = (
                    TimeResolution.FOLD_FIRST
                    if policy.repeated_time is FoldPolicy.FIRST
                    else TimeResolution.FOLD_SECOND
                )
            utc = candidates[-1] if reason is TimeResolution.FOLD_SECOND else candidates[0]
            aware = utc.astimezone(zone)
            offset = aware.utcoffset()
            assert offset is not None  # ZoneInfo always supplies an actual offset.
            seconds = offset.days * 86400 + offset.seconds
            return ResolvedTime(nominal, policy, local, seconds, reason, digest)
        except OverflowError:
            raise InvalidInput("recurrence_time_out_of_range") from None

    def after_local_days(
        self, performed_at: int, interval: RelativeInterval, policy: TimePolicy
    ) -> ResolvedTime:
        if type(performed_at) is not int or not 0 <= performed_at <= MAX_INSTANT_MS:
            raise InvalidInput("recurrence_time_out_of_range")
        zone, digest = self._zone(policy)
        try:
            actual = (_EPOCH + timedelta(milliseconds=performed_at)).astimezone(zone)
            local = actual.replace(tzinfo=None, fold=0) + timedelta(days=interval.days)
        except OverflowError:
            raise InvalidInput("recurrence_time_out_of_range") from None
        return self._resolve(NominalTime(local), policy, zone, digest)
