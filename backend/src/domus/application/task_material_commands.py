"""Completion material children share the caller's unit, source receipt and every CAS step."""

from dataclasses import dataclass

from domus.application.ports import Clock, Identifiers, UnitOfWork
from domus.application.task_authorization import TaskMaterialAccess
from domus.application.task_material_ports import TaskInventory
from domus.application.task_materials import TaskMaterials
from domus.domain.errors import Forbidden
from domus.domain.storage import JsonObject
from domus.domain.task_material_values import (
    MaterialAction,
    MaterialLine,
    MaterialSelection,
    MaterialState,
    MaterialUsage,
    validate_material_usages,
)
from domus.domain.task_materials import MaterialIntent
from domus.domain.tasks import TaskCycle, TaskOccurrence

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


def material_result(value: MaterialIntent) -> JsonObject:
    message, action = _MESSAGES[value.state]
    return {
        "intent_id": value.intent_id,
        "cycle_id": value.cycle_id,
        "line_id": value.line.line_id,
        "submitted_quantity": None
        if value.submitted_quantity is None
        else value.submitted_quantity.value,
        "quantity": None if value.quantity is None else value.quantity.value,
        "state": value.state.value,
        "pending_reason": None if value.pending_reason is None else value.pending_reason.value,
        "movement_id": None if value.posting is None else value.posting.movement_id,
        "effect_revision": value.effect_revision,
        "revision": value.revision,
        "message": message,
        "action_required": action,
    }


@dataclass
class TaskMaterialCommands:
    unit: UnitOfWork
    authority: TaskMaterialAccess
    inventory: TaskInventory
    clock: Clock
    identifiers: Identifiers

    @property
    def processor(self) -> TaskMaterials:
        return TaskMaterials(self.inventory, self.authority, self.clock, self.identifiers)

    def link(
        self, selections: tuple[MaterialSelection, ...], previous: tuple[MaterialLine, ...] = ()
    ) -> tuple[MaterialLine, ...]:
        return self.processor.link(self.authority.household_id, selections, previous)

    def complete(
        self, work: TaskOccurrence, cycle: TaskCycle, usages: tuple[MaterialUsage, ...]
    ) -> tuple[MaterialIntent, ...]:
        validate_material_usages(usages, work.definition_snapshot.materials)
        actuals = {value.line_id: value.quantity for value in usages}
        result = []
        for line in work.definition_snapshot.materials:
            value = MaterialIntent.record(
                self.identifiers.new(),
                work.household_id,
                work.occurrence_id,
                cycle.cycle_id,
                line,
                actuals.get(line.line_id),
                recorded_by=cycle.recorded_by,
                performed_at=cycle.performed_at,
                recorded_at=cycle.recorded_at,
                recording_mode=cycle.rules.material_recording,
                authorized=True,
            )
            try:
                self.authority.require(value, MaterialAction.POST)
            except Forbidden:
                value = MaterialIntent.record(
                    value.intent_id,
                    work.household_id,
                    work.occurrence_id,
                    cycle.cycle_id,
                    line,
                    actuals.get(line.line_id),
                    recorded_by=cycle.recorded_by,
                    performed_at=cycle.performed_at,
                    recorded_at=cycle.recorded_at,
                    recording_mode=cycle.rules.material_recording,
                    authorized=False,
                )
            self.unit.task_materials.save(value, 0)
            updated = self.processor.record_completion(value)
            if updated != value:
                self.unit.task_materials.save(updated, value.revision)
            result.append(updated)
        return tuple(result)
