"""Shared authorized task-definition creation; the caller owns its transaction and work mode."""

from collections.abc import Callable
from dataclasses import dataclass

from domus.application.point_allocations import household_allocation
from domus.application.ports import Clock, Identifiers, UnitOfWork
from domus.application.task_authorization import TaskAccess, TaskMaterialAccess
from domus.application.task_category_commands import require_active_category
from domus.application.task_material_commands import TaskMaterialCommands
from domus.application.task_material_ports import MissingTaskInventory, TaskInventory
from domus.application.task_requests import CreateTask
from domus.domain.errors import IntegrationUnavailable
from domus.domain.storage import JsonDocument, JsonObject
from domus.domain.task_values import TaskRules
from domus.domain.tasks import HouseholdTaskPolicy, TaskDefinition


def task_creation_result(result: JsonObject, definition: TaskDefinition) -> JsonDocument:
    """Preserve the explicit base amount in the original creation receipt."""
    amount = definition.overrides.point_value_minor
    return JsonDocument.from_value(
        result if amount is None else {**result, "point_value_minor": amount}
    )


@dataclass
class TaskCreation:
    clock: Clock
    identifiers: Identifiers
    inventory_factory: Callable[[UnitOfWork], TaskInventory] | None = None

    def materials(
        self, unit: UnitOfWork, access: TaskAccess, household_id: str
    ) -> TaskMaterialCommands:
        try:
            inventory = (
                MissingTaskInventory()
                if self.inventory_factory is None
                else self.inventory_factory(unit)
            )
        except IntegrationUnavailable:
            inventory = MissingTaskInventory()
        return TaskMaterialCommands(
            unit,
            TaskMaterialAccess(access, unit, household_id),
            inventory,
            self.clock,
            self.identifiers,
        )

    def definition(
        self, unit: UnitOfWork, access: TaskAccess, household_id: str, request: CreateTask
    ) -> TaskDefinition:
        amount = request.overrides.point_value_minor
        if amount is not None:
            allocation, _ = household_allocation(unit, household_id, amount)
            allocation.require_representable_base(amount)
        category = (
            None
            if request.content.category_id is None
            else require_active_category(unit, household_id, request.content.category_id)
        )
        if unit.tasks.policy(household_id) is None:
            unit.tasks.save_policy(HouseholdTaskPolicy(household_id, TaskRules()), 0)
        materials = (
            ()
            if request.materials is None
            else self.materials(unit, access, household_id).link(request.materials)
        )
        item = TaskDefinition(
            self.identifiers.new(),
            household_id,
            request.content,
            self.clock.now(),
            request.overrides,
            request.state,
            materials=materials,
            category_label=None if category is None else category.label,
        )
        unit.tasks.save_definition(item, 0)
        return item
