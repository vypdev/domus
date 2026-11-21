"""Create one task through the same authorized command for humans and rule grants."""

from collections.abc import Callable
from dataclasses import dataclass

from domus.application.commands import AtomicCommands, Change
from domus.application.ports import (
    Clock,
    CommandAuthorization,
    Identifiers,
    Transactions,
    UnitOfWork,
)
from domus.application.task_authorization import TaskAccess
from domus.application.task_changes import task_change
from domus.application.task_creation import TaskCreation, task_creation_result
from domus.application.task_facts import occurrence_result
from domus.application.task_material_ports import TaskInventory
from domus.application.task_requests import CreateTask
from domus.domain.errors import Forbidden
from domus.domain.storage import CommandKey, Receipt


@dataclass(frozen=True, slots=True)
class TaskCreationCommand:
    transactions: Transactions
    authorization: CommandAuthorization
    clock: Clock
    identifiers: Identifiers
    access: TaskAccess | None = None
    inventory_factory: Callable[[UnitOfWork], TaskInventory] | None = None

    def execute(
        self, command: CommandKey, request: CreateTask, unit: UnitOfWork | None = None
    ) -> Receipt:
        if command.action != "task.create":
            raise Forbidden("permission_denied")

        def apply(target: UnitOfWork) -> Change:
            item = TaskCreation(self.clock, self.identifiers, self.inventory_factory).definition(
                target, self.access, command.household_id, request
            )
            work = item.new_occurrence(self.identifiers.new(), item.created_at)
            target.tasks.save_occurrence(work, 0)
            return task_change(
                "task.created",
                request,
                task_creation_result(occurrence_result(work).decode(), item),
            )

        commands = AtomicCommands(
            self.transactions, self.authorization, self.clock, self.identifiers
        )
        payload = request.document()
        if unit is None:
            return commands.execute(command, payload, apply)
        return commands.in_unit(unit, command, payload, apply)
