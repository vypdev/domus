"""Nominal time and resolved facts preserve precision without implying a schedule or grant."""

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime

import pytest

from domus.domain.errors import InvalidInput
from domus.domain.recurrence_time import (
    FoldPolicy,
    NominalTime,
    RelativeInterval,
    ResolvedTime,
    TimePolicy,
    TimeResolution,
)


def policy() -> TimePolicy:
    return TimePolicy("Europe/Madrid", "tzdata:2026.6/iana:2026f")


def resolved() -> ResolvedTime:
    nominal = NominalTime(datetime(2026, 3, 29, 2, 30))
    return ResolvedTime(
        nominal,
        policy(),
        datetime(2026, 3, 29, 3),
        7200,
        TimeResolution.GAP_FIRST_VALID,
        "a" * 64,
    )


def test_nominal_and_resolved_values_keep_both_wall_times_and_integer_milliseconds():
    value = resolved()
    assert value.nominal.local == datetime(2026, 3, 29, 2, 30)
    assert value.resolved_local == datetime(2026, 3, 29, 3)
    assert value.instant_ms == 1_774_746_000_000
    assert value.policy.repeated_time is FoldPolicy.FIRST
    assert value.policy.revision == 1
    assert RelativeInterval(36600).days == 36600
    with pytest.raises(FrozenInstanceError):
        value.offset_seconds = 0


@pytest.mark.parametrize(
    "value",
    [
        None,
        "2026-01-01",
        date(2026, 1, 1),
        datetime(1969, 12, 31),
        datetime(2026, 1, 1, tzinfo=UTC),
        datetime(2026, 1, 1, fold=1),
        datetime(2026, 1, 1, microsecond=1),
    ],
)
def test_nominal_rejects_implicit_zone_precision_fold_and_unsupported_year(value):
    with pytest.raises(InvalidInput, match="invalid_recurrence_local_time"):
        NominalTime(value)


@pytest.mark.parametrize("value", [True, 0, -1, 36601, 1.0, "30", None])
def test_relative_interval_is_an_exact_bounded_integer(value):
    with pytest.raises(InvalidInput, match="invalid_relative_interval"):
        RelativeInterval(value)


@pytest.mark.parametrize(
    "zone",
    [
        None,
        "",
        "../UTC",
        "/UTC",
        "Europe//Madrid",
        "Europe/../UTC",
        "Europe/./Madrid",
        "UTC\x00",
        "é/UTC",
        "a" * 129,
        "UTC ",
        "UTC\\x",
    ],
)
def test_zone_key_is_bounded_inert_relative_ascii_without_path_traversal(zone):
    with pytest.raises(InvalidInput, match="invalid_recurrence_time_policy"):
        replace(policy(), zone=zone)


@pytest.mark.parametrize("zone", ["UTC", "Etc/GMT+1", "America/Port-au-Prince"])
def test_structural_zone_validation_does_not_pretend_to_check_provider_availability(zone):
    assert replace(policy(), zone=zone).zone == zone


@pytest.mark.parametrize(
    "changes",
    [
        {"data_identity": None},
        {"data_identity": ""},
        {"data_identity": "a" * 129},
        {"data_identity": "bad\nversion"},
        {"repeated_time": "first_instant"},
        {"revision": True},
        {"revision": 0},
        {"revision": 2**63},
    ],
)
def test_policy_requires_explicit_version_enum_and_positive_revision(changes):
    with pytest.raises(InvalidInput):
        replace(policy(), **changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"nominal": None},
        {"policy": None},
        {"resolved_local": None},
        {"offset_seconds": True},
        {"offset_seconds": -86400},
        {"offset_seconds": 86400},
        {"resolution": "gap_first_valid"},
        {"zone_digest": None},
        {"zone_digest": "a" * 63},
        {"zone_digest": "A" * 64},
        {"zone_digest": "g" * 64},
        {"resolution": TimeResolution.EXACT},
        {"resolved_local": datetime(2026, 3, 29, 2, 30)},
        {"resolved_local": datetime(2026, 3, 29, 2)},
        {"resolved_local": datetime(2026, 3, 29, 3, tzinfo=UTC)},
    ],
)
def test_resolved_facts_reject_inconsistent_or_untyped_snapshots(changes):
    with pytest.raises(InvalidInput):
        replace(resolved(), **changes)


def test_exact_and_fold_facts_preserve_nominal_wall_time_and_subsecond_precision():
    nominal = NominalTime(datetime(1970, 1, 1, 0, 1, 2, 123000))
    for reason in (TimeResolution.EXACT, TimeResolution.FOLD_FIRST, TimeResolution.FOLD_SECOND):
        appearance = FoldPolicy.SECOND if reason is TimeResolution.FOLD_SECOND else FoldPolicy.FIRST
        value = ResolvedTime(
            nominal,
            replace(policy(), repeated_time=appearance),
            nominal.local,
            60,
            reason,
            "f" * 64,
        )
        assert value.instant_ms == 2123


@pytest.mark.parametrize(
    "fold,reason",
    [
        (FoldPolicy.FIRST, TimeResolution.FOLD_SECOND),
        (FoldPolicy.SECOND, TimeResolution.FOLD_FIRST),
    ],
)
def test_fold_resolution_cannot_disagree_with_its_snapshotted_policy(fold, reason):
    nominal = NominalTime(datetime(2026, 10, 25, 2, 30))
    with pytest.raises(InvalidInput, match="invalid_recurrence_resolution"):
        ResolvedTime(
            nominal, replace(policy(), repeated_time=fold), nominal.local, 3600, reason, "f" * 64
        )


@pytest.mark.parametrize(
    "local,offset",
    [(datetime(1970, 1, 1), 1), (datetime(9999, 12, 31, 23, 59, 59, 999000), -1)],
)
def test_utc_conversion_never_wraps_before_epoch_or_beyond_supported_datetime(local, offset):
    with pytest.raises(InvalidInput, match="recurrence_time_out_of_range"):
        ResolvedTime(NominalTime(local), policy(), local, offset, TimeResolution.EXACT, "a" * 64)
