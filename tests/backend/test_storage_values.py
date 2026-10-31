"""Pure persistence contracts reject ambiguous identifiers and mutable replay payloads."""

from dataclasses import FrozenInstanceError

import pytest

from domus.domain.errors import InvalidInput
from domus.domain.storage import CommandKey, Household, Installation, JsonDocument


def test_installation_has_explicit_persistent_identity_and_channel() -> None:
    identity = Installation("047cc6fb-dfb0-4fa4-b3c3-e0fe54d116b6", "edge")
    assert identity.channel == "edge"
    with pytest.raises(FrozenInstanceError):
        identity.channel = "stable"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("instance_id", "channel"),
    [
        ("not-a-uuid", "stable"),
        ("047CC6FB-DFB0-4FA4-B3C3-E0FE54D116B6", "stable"),
        ("047cc6fb-dfb0-4fa4-b3c3-e0fe54d116b6", "production"),
        ("00000000-0000-0000-0000-000000000000", "stable"),
    ],
)
def test_installation_rejects_noncanonical_identity_or_unknown_channel(
    instance_id: str, channel: str
) -> None:
    with pytest.raises(InvalidInput, match="invalid_installation"):
        Installation(instance_id, channel)


def test_command_key_scopes_receipts_by_household_actor_action_and_key() -> None:
    key = CommandKey("household_1", "ha_1", "household.rename", "request-1")
    assert key != CommandKey("household_2", "ha_1", "household.rename", "request-1")
    assert key != CommandKey("household_1", "ha_2", "household.rename", "request-1")
    assert key != CommandKey("household_1", "ha_1", "household.create", "request-1")


@pytest.mark.parametrize("field", ["household_id", "actor_id", "action", "key"])
@pytest.mark.parametrize("value", ["", "with space", "line\nfeed", "x" * 129])
def test_command_key_rejects_ambiguous_or_unbounded_scope(field: str, value: str) -> None:
    values = dict(household_id="home", actor_id="actor", action="rename", key="request")
    values[field] = value
    with pytest.raises(InvalidInput, match="invalid_identifier"):
        CommandKey(**values)


def test_canonical_payload_is_detached_from_callers_and_ignores_object_key_order() -> None:
    value = {"b": [2, {"ok": True}], "a": None}
    document = JsonDocument.from_value(value)
    value["b"] = []
    assert document.decode() == {"a": None, "b": [2, {"ok": True}]}
    assert document == JsonDocument('{"b":[2,{"ok":true}],"a":null}')
    assert document.fingerprint == JsonDocument.from_value(document.decode()).fingerprint
    decoded = document.decode()
    decoded["a"] = "changed"
    assert document.decode()["a"] is None


def test_json_preserves_scalar_types_and_array_order() -> None:
    value = {"items": ["é", 1, 1.25, False, None]}
    assert JsonDocument.from_value(value).decode() == value
    assert (
        JsonDocument.from_value({"items": [1, 2]}).fingerprint
        != JsonDocument.from_value({"items": [2, 1]}).fingerprint
    )


@pytest.mark.parametrize(
    "encoded",
    [None, 123, "not json", "[]", "1", '{"a":NaN}', '{"a":Infinity}', '{"a":1,"a":2}'],
)
def test_invalid_or_ambiguous_json_does_not_establish_a_payload(encoded: str) -> None:
    with pytest.raises(InvalidInput, match="invalid_document"):
        JsonDocument(encoded)


@pytest.mark.parametrize("value", [{1: "not a string key"}, {"value": object()}, {"bad": "\ud800"}])
def test_unsupported_objects_and_invalid_unicode_are_rejected_without_echo(value: object) -> None:
    with pytest.raises(InvalidInput) as caught:
        JsonDocument.from_value(value)
    assert str(caught.value) == "invalid_document"


def test_document_size_and_depth_are_bounded() -> None:
    with pytest.raises(InvalidInput):
        JsonDocument.from_value({"value": "x" * 65_536})
    nested: object = None
    for _ in range(20):
        nested = [nested]
    with pytest.raises(InvalidInput):
        JsonDocument.from_value({"nested": nested})


def test_integer_conversion_limits_are_safe_document_validation_failures() -> None:
    with pytest.raises(InvalidInput, match="invalid_document"):
        JsonDocument.from_value({"unbounded_integer": 10**5000})


def test_encoded_size_and_parser_depth_are_bounded_before_interpretation() -> None:
    with pytest.raises(InvalidInput, match="invalid_document"):
        JsonDocument(" " * 65_537 + "{}")
    with pytest.raises(InvalidInput, match="invalid_document"):
        JsonDocument('{"nested":' + "[" * 2000 + "0" + "]" * 2000 + "}")


def test_unicode_payloads_use_the_utf8_budget_without_ascii_escape_inflation() -> None:
    value = {"name": "🏠" * 10_000}
    assert JsonDocument.from_value(value).decode() == value


def test_canonical_numeric_expansion_cannot_escape_the_document_budget() -> None:
    encoded = '{"values":[' + ",".join(["1e6"] * 10_000) + "]}"
    assert len(encoded) < 65_536
    with pytest.raises(InvalidInput, match="invalid_document"):
        JsonDocument(encoded)


def test_household_record_preserves_revision_and_unicode_display_name() -> None:
    record = Household("home", "  Family home 🏠  ", "Europe/Madrid", 1)
    assert record.name == "Family home 🏠"
    assert record.revision == 1


@pytest.mark.parametrize(
    ("name", "time_zone", "revision"),
    [
        (" ", "UTC", 1),
        ("x" * 161, "UTC", 1),
        ("bad\nname", "UTC", 1),
        ("Home", "", 1),
        ("Home", "UTC", 0),
        ("Home", "UTC", True),
        ("Home", "UTC", 2**63),
        (None, "UTC", 1),
        ("Home", None, 1),
        ("\ud800", "UTC", 1),
        ("Home", "\ud800", 1),
    ],
)
def test_invalid_household_does_not_become_persistent_state(
    name: str, time_zone: str, revision: int
) -> None:
    with pytest.raises(InvalidInput, match="invalid_household"):
        Household("home", name, time_zone, revision)
