"""The actual pinned TZif adapter resolves gaps, folds and local-day successors explicitly."""

import hashlib
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from domus.application.recurrence_ports import RecurrenceTimes
from domus.domain.errors import IntegrationUnavailable, InvalidInput
from domus.domain.recurrence_time import (
    FoldPolicy,
    NominalTime,
    RelativeInterval,
    TimePolicy,
    TimeResolution,
)
from domus.infrastructure import recurrence_time as adapter


def policy(zone="Europe/Madrid", fold=FoldPolicy.FIRST):
    return TimePolicy(zone, adapter.TIMEZONE_DATA_IDENTITY, fold)


def test_exact_time_uses_actual_pinned_bytes_and_preserves_milliseconds():
    local = datetime(2026, 1, 3, 12, 45, 6, 123000)
    service: RecurrenceTimes = adapter.PinnedRecurrenceTime()
    value = service.resolve(NominalTime(local), policy())
    assert value.resolved_local == local
    assert value.offset_seconds == 3600
    assert value.instant_ms == int(
        datetime(2026, 1, 3, 11, 45, 6, 123000, tzinfo=UTC).timestamp() * 1000
    )
    assert value.resolution is TimeResolution.EXACT
    assert (
        value.zone_digest
        == hashlib.sha256(adapter.PackagedTimeZones().read("Europe/Madrid")).hexdigest()
    )
    assert service.data_identity == adapter.TIMEZONE_DATA_IDENTITY


@pytest.mark.parametrize(
    "zone,nominal,expected,offset",
    [
        ("Europe/Madrid", datetime(2026, 3, 29, 2, 30), datetime(2026, 3, 29, 3), 7200),
        ("Australia/Lord_Howe", datetime(2026, 10, 4, 2, 15), datetime(2026, 10, 4, 2, 30), 39600),
        ("Pacific/Apia", datetime(2011, 12, 30, 12), datetime(2011, 12, 31), 50400),
        (
            "Africa/Monrovia",
            datetime(1972, 1, 7, 0, 1, 2, 123000),
            datetime(1972, 1, 7, 0, 44, 30),
            0,
        ),
    ],
)
def test_gap_selects_first_valid_boundary_instead_of_shifting_entire_gap(
    zone, nominal, expected, offset
):
    value = adapter.PinnedRecurrenceTime().resolve(NominalTime(nominal), policy(zone))
    assert value.nominal.local == nominal
    assert value.resolved_local == expected
    assert value.offset_seconds == offset
    assert value.resolution is TimeResolution.GAP_FIRST_VALID


@pytest.mark.parametrize(
    "fold,reason,hour",
    [
        (FoldPolicy.FIRST, TimeResolution.FOLD_FIRST, 0),
        (FoldPolicy.SECOND, TimeResolution.FOLD_SECOND, 1),
    ],
)
def test_fold_selects_exactly_one_requested_actual_utc_appearance(fold, reason, hour):
    value = adapter.PinnedRecurrenceTime().resolve(
        NominalTime(datetime(2026, 10, 25, 2, 30)), policy(fold=fold)
    )
    assert value.resolved_local == value.nominal.local
    assert value.instant_ms == int(datetime(2026, 10, 25, hour, 30, tzinfo=UTC).timestamp() * 1000)
    assert value.resolution is reason


def test_whole_date_adjustment_keeps_distinct_nominal_slots_when_instants_collide():
    service = adapter.PinnedRecurrenceTime()
    missing = service.resolve(NominalTime(datetime(2011, 12, 30)), policy("Pacific/Apia"))
    real = service.resolve(NominalTime(datetime(2011, 12, 31)), policy("Pacific/Apia"))
    assert missing.nominal != real.nominal
    assert missing.instant_ms == real.instant_ms


@pytest.mark.parametrize("year,month,day,elapsed", [(2026, 3, 28, 23), (2026, 10, 24, 25)])
def test_relative_successor_adds_local_days_to_actual_work_not_elapsed_utc_hours(
    year, month, day, elapsed
):
    service = adapter.PinnedRecurrenceTime()
    original = service.resolve(NominalTime(datetime(year, month, day, 12, 5, 6, 789000)), policy())
    successor = service.after_local_days(original.instant_ms, RelativeInterval(1), policy())
    assert successor.nominal.local == datetime(year, month, day + 1, 12, 5, 6, 789000)
    assert successor.instant_ms - original.instant_ms == elapsed * 3_600_000


def test_relative_successor_reuses_gap_policy_after_preserving_actual_work_wall_time():
    service = adapter.PinnedRecurrenceTime()
    original = service.resolve(NominalTime(datetime(2026, 3, 28, 2, 30, 6, 123000)), policy())
    value = service.after_local_days(original.instant_ms, RelativeInterval(1), policy())
    assert value.nominal.local == datetime(2026, 3, 29, 2, 30, 6, 123000)
    assert value.resolved_local == datetime(2026, 3, 29, 3)


@pytest.mark.parametrize("zone", ["Not/AZone", "Europe/Missing"])
def test_unknown_zone_is_input_failure_not_silent_utc_or_source_unavailability(zone):
    with pytest.raises(InvalidInput, match="unknown_time_zone"):
        adapter.PinnedRecurrenceTime().resolve(NominalTime(datetime(2026, 1, 1)), policy(zone))


def test_policy_source_version_mismatch_is_explicit_and_does_not_load_other_data():
    with pytest.raises(IntegrationUnavailable, match="timezone_data_mismatch"):
        adapter.PinnedRecurrenceTime().resolve(
            NominalTime(datetime(2026, 1, 1)), replace(policy(), data_identity="future")
        )


@pytest.mark.parametrize("instant", [True, -1, 253402300800000, 2**63 - 1, "1"])
def test_relative_source_time_is_strict_and_cannot_overflow_datetime(instant):
    with pytest.raises(InvalidInput):
        adapter.PinnedRecurrenceTime().after_local_days(instant, RelativeInterval(1), policy("UTC"))


def test_relative_target_date_overflow_fails_instead_of_wrapping():
    with pytest.raises(InvalidInput, match="recurrence_time_out_of_range"):
        adapter.PinnedRecurrenceTime().after_local_days(
            253402214400000, RelativeInterval(1), policy("UTC")
        )


@pytest.mark.parametrize("failure", ["missing_metadata", "missing_package", "wrong_package"])
def test_missing_or_incompatible_package_never_uses_machine_timezone_fallback(monkeypatch, failure):
    def unavailable(_):
        raise adapter.PackageNotFoundError("private diagnostic")

    def missing_package(_):
        raise ModuleNotFoundError("private diagnostic")

    if failure == "missing_metadata":
        monkeypatch.setattr(adapter, "version", unavailable)
    elif failure == "missing_package":
        monkeypatch.setattr(adapter, "files", missing_package)
    else:
        monkeypatch.setattr(adapter, "version", lambda _: "future")
    code = "timezone_data_mismatch" if failure == "wrong_package" else "timezone_source_unavailable"
    with pytest.raises(IntegrationUnavailable) as error:
        adapter.PinnedRecurrenceTime().resolve(NominalTime(datetime(2026, 1, 1)), policy("UTC"))
    assert str(error.value) == code


@pytest.mark.parametrize(
    "failure,code",
    [
        ("large_catalog", "timezone_source_corrupt"),
        ("invalid_catalog", "timezone_source_corrupt"),
        ("missing_catalog", "timezone_source_unavailable"),
        ("wrong_iana", "timezone_data_mismatch"),
        ("missing_known_zone", "timezone_source_unavailable"),
        ("empty_zone", "timezone_source_corrupt"),
        ("large_zone", "timezone_source_corrupt"),
        ("invalid_zone", "timezone_source_corrupt"),
        ("truncated_zone", "timezone_source_corrupt"),
    ],
)
def test_actual_resource_failures_have_bounded_safe_distinct_results(
    tmp_path, monkeypatch, failure, code
):
    original = adapter.PackagedTimeZones().read("UTC")
    (tmp_path / "zones").write_bytes(b"UTC\n")
    zone_dir = tmp_path / "zoneinfo"
    zone_dir.mkdir()
    (zone_dir / "tzdata.zi").write_bytes(b"# version 2026f\n")
    (zone_dir / "UTC").write_bytes(original)
    match failure:
        case "large_catalog":
            (tmp_path / "zones").write_bytes(b"X" * 65537)
        case "invalid_catalog":
            (tmp_path / "zones").write_bytes(b"\xff")
        case "missing_catalog":
            (tmp_path / "zones").unlink()
        case "wrong_iana":
            (zone_dir / "tzdata.zi").write_bytes(b"# version future\n")
        case "missing_known_zone":
            (zone_dir / "UTC").unlink()
        case "empty_zone":
            (zone_dir / "UTC").write_bytes(b"")
        case "large_zone":
            (zone_dir / "UTC").write_bytes(b"X" * 1048577)
        case "invalid_zone":
            (zone_dir / "UTC").write_bytes(b"not TZif")
        case "truncated_zone":
            (zone_dir / "UTC").write_bytes(b"TZif2")
    monkeypatch.setattr(adapter, "files", lambda _: tmp_path)
    with pytest.raises(IntegrationUnavailable) as error:
        adapter.PinnedRecurrenceTime().resolve(NominalTime(datetime(2026, 1, 1)), policy("UTC"))
    assert str(error.value) == code


def test_actual_zone_can_overflow_utc_even_when_nominal_calendar_date_is_valid():
    with pytest.raises(InvalidInput, match="recurrence_time_out_of_range"):
        adapter.PinnedRecurrenceTime().resolve(
            NominalTime(datetime(9999, 12, 31, 23, 59, 59, 999000)), policy("Etc/GMT+1")
        )


def test_impossible_provider_existence_result_is_unavailable_instead_of_spinning(monkeypatch):
    monkeypatch.setattr(adapter, "_candidates", lambda *_: ())
    with pytest.raises(IntegrationUnavailable, match="timezone_resolution_unavailable"):
        adapter.PinnedRecurrenceTime().resolve(NominalTime(datetime(2026, 1, 1)), policy("UTC"))


def test_whole_date_resolution_has_logarithmically_bounded_probe_count(monkeypatch):
    calls = []
    actual = adapter._candidates

    def observe(*args):
        calls.append(1)
        return actual(*args)

    monkeypatch.setattr(adapter, "_candidates", observe)
    value = adapter.PinnedRecurrenceTime().resolve(
        NominalTime(datetime(2011, 12, 30, 0, 0, 0, 123000)), policy("Pacific/Apia")
    )
    assert value.resolved_local == datetime(2011, 12, 31)
    assert len(calls) <= 30


def test_adapter_does_not_consult_or_mutate_process_timezone_path(monkeypatch):
    import zoneinfo

    original = zoneinfo.TZPATH
    monkeypatch.setenv("PYTHONTZPATH", "/does/not/exist")
    monkeypatch.setattr(
        adapter,
        "ZoneInfo",
        type("OnlyExplicitBytes", (), {"from_file": zoneinfo.ZoneInfo.from_file}),
    )
    assert (
        adapter.PinnedRecurrenceTime()
        .resolve(NominalTime(datetime(2026, 1, 1)), policy("UTC"))
        .offset_seconds
        == 0
    )
    assert zoneinfo.TZPATH == original
