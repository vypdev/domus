"""Strict versioned material facts; canonical quantities stay decimal strings in storage."""

from dataclasses import asdict
from typing import cast

from domus.domain.errors import DomusError, InvalidInput, StorageFailure
from domus.domain.storage import JsonDocument, JsonObject, JsonValue
from domus.domain.task_material_values import (
    MaterialBinding,
    MaterialLine,
    MaterialPendingReason,
    MaterialQuantity,
    MaterialState,
)
from domus.domain.task_materials import MaterialIntent, MaterialPosting
from domus.domain.task_values import MaterialRecording

_BINDING = (
    "household_id",
    "reference_id",
    "product_id",
    "unit_id",
    "location_id",
    "revision",
    "precision",
    "label",
)
_POSTING = (
    "intent_id",
    "household_id",
    "occurrence_id",
    "cycle_id",
    "line_id",
    "reference_id",
    "binding_revision",
    "intent_revision",
    "effect_revision",
    "quantity",
    "inventory_operation_id",
    "movement_id",
    "posted_at",
)
_INTENT = (
    "version",
    "intent_id",
    "household_id",
    "occurrence_id",
    "cycle_id",
    "line",
    "submitted_quantity",
    "quantity",
    "recorded_by",
    "performed_at",
    "created_at",
    "updated_at",
    "recording_mode",
    "authorized_at_recording",
    "state",
    "pending_reason",
    "reason",
    "posting",
    "effect_revision",
    "revision",
)


def _object(value: JsonValue, keys: tuple[str, ...]) -> JsonObject:
    if type(value) is not dict or set(value) != set(keys):
        raise InvalidInput("invalid_material_record")
    return value


def line_value(value: MaterialLine) -> JsonObject:
    return {
        "line_id": value.line_id,
        "binding": asdict(value.binding),
        "planned_quantity": value.planned_quantity.value,
    }


def read_line(value: JsonValue) -> MaterialLine:
    row = _object(value, ("line_id", "binding", "planned_quantity"))
    binding = _object(row["binding"], _BINDING)
    return MaterialLine(
        cast(str, row["line_id"]),
        MaterialBinding(
            cast(str, binding["household_id"]),
            cast(str, binding["reference_id"]),
            cast(str, binding["product_id"]),
            cast(str, binding["unit_id"]),
            cast(str, binding["location_id"]),
            cast(int, binding["revision"]),
            cast(int, binding["precision"]),
            cast(str, binding["label"]),
        ),
        MaterialQuantity(cast(str, row["planned_quantity"])),
    )


def _quantity(value: JsonValue) -> MaterialQuantity | None:
    return None if value is None else MaterialQuantity(cast(str, value))


def _posting(value: JsonValue) -> MaterialPosting | None:
    if value is None:
        return None
    row = _object(value, _POSTING)
    return MaterialPosting(
        cast(str, row["intent_id"]),
        cast(str, row["household_id"]),
        cast(str, row["occurrence_id"]),
        cast(str, row["cycle_id"]),
        cast(str, row["line_id"]),
        cast(str, row["reference_id"]),
        cast(int, row["binding_revision"]),
        cast(int, row["intent_revision"]),
        cast(int, row["effect_revision"]),
        MaterialQuantity(cast(str, row["quantity"])),
        cast(str, row["inventory_operation_id"]),
        cast(str, row["movement_id"]),
        cast(int, row["posted_at"]),
    )


def material_document(value: MaterialIntent) -> JsonDocument:
    row = asdict(value)
    row.update(
        version=1,
        recording_mode=value.recording_mode.value,
        state=value.state.value,
        pending_reason=None if value.pending_reason is None else value.pending_reason.value,
        line=line_value(value.line),
        submitted_quantity=None
        if value.submitted_quantity is None
        else value.submitted_quantity.value,
        quantity=None if value.quantity is None else value.quantity.value,
    )
    if value.posting is not None:
        row["posting"]["quantity"] = value.posting.quantity.value
    return JsonDocument.from_value(row)


def read_material(encoded: str) -> MaterialIntent:
    try:
        row = _object(JsonDocument(encoded).decode(), _INTENT)
        if type(row["version"]) is not int or row["version"] != 1:
            raise InvalidInput("unsupported_material_record")
        return MaterialIntent(
            cast(str, row["intent_id"]),
            cast(str, row["household_id"]),
            cast(str, row["occurrence_id"]),
            cast(str, row["cycle_id"]),
            read_line(row["line"]),
            _quantity(row["submitted_quantity"]),
            _quantity(row["quantity"]),
            cast(str, row["recorded_by"]),
            cast(int, row["performed_at"]),
            cast(int, row["created_at"]),
            cast(int, row["updated_at"]),
            MaterialRecording(cast(str, row["recording_mode"])),
            cast(bool, row["authorized_at_recording"]),
            MaterialState(cast(str, row["state"])),
            None
            if row["pending_reason"] is None
            else MaterialPendingReason(cast(str, row["pending_reason"])),
            cast(str, row["reason"]),
            _posting(row["posting"]),
            cast(int, row["effect_revision"]),
            cast(int, row["revision"]),
        )
    except DomusError, KeyError, TypeError, ValueError:
        raise StorageFailure("invalid_material_record") from None
