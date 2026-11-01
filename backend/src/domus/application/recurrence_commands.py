"""Current-authorized schedule creation shares task validation and the durable command boundary."""

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass

from domus.application.commands import AtomicCommands, Change
from domus.application.fixed_recurrence import FixedRecurrencePlanner
from domus.application.identity_ports import CurrentHuman
from domus.application.ports import Clock, Identifiers, Transactions, UnitOfWork
from domus.application.task_authorization import TaskAccess, TaskCommandAuthorization
from domus.application.task_creation import TaskCreation
from domus.application.task_material_ports import TaskInventory
from domus.application.task_requests import CreateTask
from domus.domain.errors import IntegrationUnavailable, InvalidInput
from domus.domain.recurrence_planning import FixedCursor, cursor_binding
from domus.domain.recurrence_records import FixedProgress, FixedSchedule
from domus.domain.recurrence_rules import FixedPattern
from domus.domain.recurrence_time import TimePolicy
from domus.domain.storage import CommandKey, JsonDocument, Receipt, validate_identifier
from domus.domain.task_values import DefinitionState, TaskOverrides


@dataclass(frozen=True, slots=True)
class CreateFixedTask:
    task: CreateTask
    pattern: FixedPattern
    policy: TimePolicy

    def __post_init__(self) -> None:
        if (
            not isinstance(self.task, CreateTask)
            or self.task.state is not DefinitionState.ACTIVE
            or not isinstance(self.pattern, FixedPattern)
            or not isinstance(self.policy, TimePolicy)
        ):
            raise InvalidInput("invalid_recurrence_create")

    def document(self) -> JsonDocument:
        return JsonDocument(
            json.dumps(
                {
                    "version": 1,
                    "task": self.task.document().decode(),
                    "pattern": self.pattern.document().decode(),
                    "policy": asdict(self.policy),
                }
            )
        )


@dataclass
class RecurrenceCommands:
    transactions: Transactions
    actor: CurrentHuman
    clock: Clock
    identifiers: Identifiers
    planner: FixedRecurrencePlanner
    household_id: str = "home"
    inventory_factory: Callable[[UnitOfWork], TaskInventory] | None = None

    def __post_init__(self) -> None:
        validate_identifier(self.household_id)

    def create_fixed(self, key: str, request: CreateFixedTask) -> Receipt:
        payload = request.document()
        access = TaskAccess(self.actor.current())
        command = CommandKey(
            self.household_id, access.human.ha_user_id, "recurrence.fixed.create", key
        )
        authority = TaskCommandAuthorization(
            access,
            self.household_id,
            command.action,
            needs_configuration=request.task.overrides != TaskOverrides(),
            needs_material_link=request.task.materials is not None,
        )
        commands = AtomicCommands(self.transactions, authority, self.clock, self.identifiers)
        previous = commands.replay(command, payload)
        if previous is not None:
            return previous
        # Provider work cannot hold the writer lock; execute checks fresh local grants again.
        self.planner.times.require_policy(request.policy)
        check = self.planner.check_start(request.pattern, request.policy)
        if not check.matches:
            if not check.search_complete:
                raise IntegrationUnavailable("recurrence_start_unresolved")
            raise InvalidInput("recurrence_start_mismatch")

        def apply(unit: UnitOfWork) -> Change:
            item = TaskCreation(self.clock, self.identifiers, self.inventory_factory).definition(
                unit, access, self.household_id, request.task
            )
            schedule = FixedSchedule(
                self.identifiers.new(),
                self.household_id,
                item.definition_id,
                request.pattern,
                request.policy,
                item.created_at,
            )
            # Validation's lookahead never consumes the first real obligation.
            progress = FixedProgress(
                schedule.schedule_id,
                self.household_id,
                1,
                FixedCursor(cursor_binding(schedule.pattern, schedule.policy)),
            )
            unit.recurrence.save_schedule(schedule, 0)
            unit.recurrence.save_progress(progress, 0)
            result = JsonDocument.from_value(
                {
                    "schedule_id": schedule.schedule_id,
                    "definition_id": item.definition_id,
                    "revision": 1,
                    "pattern_revision": 1,
                    "state": schedule.state.value,
                    "processing": "pending",
                    "first_occurrence_id": None,
                }
            )
            detail = JsonDocument.from_value(
                {
                    "transition": "recurrence.fixed.created",
                    "request": payload.decode(),
                    "result": result.decode(),
                }
            )
            event = JsonDocument.from_value(
                {
                    "version": 1,
                    "kind": "recurrence.fixed.created",
                    **result.decode(),
                }
            )
            return Change(result, detail, event)

        return commands.execute(command, payload, apply)
