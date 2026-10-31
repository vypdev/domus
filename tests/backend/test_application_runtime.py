"""System adapters preserve UTC units, safe identifiers and the configured zone boundary."""

import pytest

from domus.domain.errors import InvalidInput
from domus.domain.storage import validate_identifier
from domus.infrastructure import application_runtime


def test_wall_clock_is_utc_unix_milliseconds_without_float_rounding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(application_runtime.time, "time_ns", lambda: 123_456_789_123_456_789)
    assert application_runtime.SystemClock().now() == 123_456_789_123


def test_record_identifiers_use_192_bits_and_remain_valid_with_leading_underscore_entropy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def entropy(bytes_requested: int) -> str:
        assert bytes_requested == 24
        return "_fixture_material"

    monkeypatch.setattr(application_runtime.secrets, "token_urlsafe", entropy)
    value = application_runtime.SecureIdentifiers().new()
    validate_identifier(value)
    assert value == "domus__fixture_material"


@pytest.mark.parametrize("zone", ["UTC", "Europe/Madrid", "America/New_York"])
def test_supported_zones_are_validated_by_the_actual_system_catalog(zone: str) -> None:
    application_runtime.TimeZoneCatalog().require(zone)


@pytest.mark.parametrize("zone", ["Not/AZone", "../UTC", "/etc/passwd", "UTC\x00", None])
def test_unknown_or_path_malformed_zone_never_falls_back_to_a_different_zone(zone: str) -> None:
    with pytest.raises(InvalidInput, match="invalid_time_zone"):
        application_runtime.TimeZoneCatalog().require(zone)
