"""Completion material children share the caller's unit, source receipt and every CAS step."""

from dataclasses import dataclass
from typing import cast

from domus.application.ports import Clock, Identifiers, UnitOfWork
from domus.application.task_authorization import TaskMaterialAccess
from domus.application.task_material_ports import TaskInventory
from domus.application.task_material_views import material_result as material_result
from domus.application.task_materials import TaskMaterials
from domus.application.task_requests import SettleTaskMaterial
from domus.domain.errors import Forbidden
from domus.domain.task_material_values import (
    MaterialAction,
    MaterialLine,
    MaterialQuantity,
    MaterialSelection,
    MaterialUsage,
    validate_material_usages,
)
from domus.domain.task_materials import MaterialIntent
from domus.domain.tasks import TaskCycle, TaskOccurrence


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

    def settle(self, value: MaterialIntent, request: SettleTaskMaterial) -> MaterialIntent:
        previous = value

        def stage(updated: MaterialIntent) -> None:
            nonlocal previous
            self.unit.task_materials.save(updated, previous.revision)
            previous = updated

        if request.action is MaterialAction.CORRECT:
            updated = self.processor.correct(
                value, cast(MaterialQuantity, request.quantity), request.reason, stage=stage
            )
        elif request.action is MaterialAction.POST:
            updated = self.processor.post(value)
        else:
            updated = self.processor.dismiss(value, request.reason)
        if updated != previous:
            stage(updated)
        return updated

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
