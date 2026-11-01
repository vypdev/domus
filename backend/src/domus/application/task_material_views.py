"""Safe typed material outcomes separate live state from immutable command evidence."""

import json
from dataclasses import asdict, dataclass

from domus.domain.storage import JsonDocument, JsonObject
from domus.domain.task_material_values import MaterialPendingReason, MaterialState
from domus.domain.task_materials import MaterialIntent


@dataclass(frozen=True, slots=True)
class MaterialOutcome:
    intent_id: str
    cycle_id: str
    line_id: str
    submitted_quantity: str | None
    quantity: str | None
    state: MaterialState
    pending_reason: MaterialPendingReason | None
    movement_id: str | None
    effect_revision: int
    revision: int
    message: str
    action_required: str | None
    confirmed_quantity: str | None
    confirmed_effect_revision: int | None
    posted_at: int | None


_MESSAGES: dict[MaterialState, tuple[str, str | None]] = {
    MaterialState.PENDING_RECORDING: (
        "Work is saved; actual material quantity has not been recorded.",
        "Record the actual quantity, including zero if unused.",
    ),
    MaterialState.PENDING_AUTHORIZATION: (
        "Work is saved; material consumption is not authorized.",
        "Ask an authorized member to review and explicitly settle this usage.",
    ),
    MaterialState.PENDING_REGULARIZATION: (
        "Work is saved; material consumption needs Inventory review.",
        "Review stock or binding details, then explicitly retry settlement.",
    ),
    MaterialState.PENDING_PROCESSING: (
        "Work is saved; material consumption is awaiting explicit processing.",
        "Review the pending reason and explicitly settle this usage.",
    ),
    MaterialState.NOT_USED: ("Material was not used; no stock movement was requested.", None),
    MaterialState.POSTED: ("Inventory confirmed this material consumption.", None),
    MaterialState.CORRECTED: ("Inventory confirmed the corrected total.", None),
    MaterialState.DISMISSED: (
        "Material intent was dismissed; its original submission is retained.",
        None,
    ),
}


def material_outcome(value: MaterialIntent) -> MaterialOutcome:
    message, action = _MESSAGES[value.state]
    return MaterialOutcome(
        value.intent_id,
        value.cycle_id,
        value.line.line_id,
        None if value.submitted_quantity is None else value.submitted_quantity.value,
        None if value.quantity is None else value.quantity.value,
        value.state,
        value.pending_reason,
        None if value.posting is None else value.posting.movement_id,
        value.effect_revision,
        value.revision,
        message,
        action,
        None if value.posting is None else value.posting.quantity.value,
        None if value.posting is None else value.posting.effect_revision,
        None if value.posting is None else value.posting.posted_at,
    )


def material_result(value: MaterialIntent) -> JsonObject:
    # Existing receipts retain their original compact shape; live reads add proof facts.
    result = asdict(material_outcome(value))
    for field in ("confirmed_quantity", "confirmed_effect_revision", "posted_at"):
        del result[field]
    return JsonDocument(json.dumps(result)).decode()
