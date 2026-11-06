"""Current-authorized relative creation preserves an explicit unconsumed first obligation."""

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass

from domus.application.commands import AtomicCommands, Change
from domus.application.identity_ports import CurrentHuman
from domus.application.ports import Clock, Identifiers, Transactions, UnitOfWork
from domus.application.recurrence_ports import RecurrenceTimes
from domus.application.task_authorization import TaskAccess, TaskCommandAuthorization
from domus.application.task_creation import TaskCreation
from domus.application.task_material_ports import TaskInventory
from domus.application.task_requests import CreateTask
from domus.domain.errors import IntegrationUnavailable, InvalidInput
from domus.domain.recurrence_planning import PlannedSlot
from domus.domain.recurrence_rules import NominalDate, NominalSlot
from domus.domain.recurrence_time import NominalTime, RelativeInterval, ResolvedTime, TimePolicy
from domus.domain.relative_recurrence import (
    RelativeProgress,
    RelativeSchedule,
    SuccessorVisibility,
)
from domus.domain.storage import CommandKey, JsonDocument, Receipt, validate_identifier
from domus.domain.task_values import DefinitionState, TaskOverrides


@dataclass(frozen=True, slots=True)
class CreateRelativeTask:
    task: CreateTask
    initial: NominalSlot
    interval: RelativeInterval
    policy: TimePolicy
    visibility: SuccessorVisibility = SuccessorVisibility.AT_COMPLETION

    def __post_init__(self) -> None:
        if (
            not isinstance(self.task, CreateTask)
            or self.task.state is not DefinitionState.ACTIVE
            or not isinstance(self.initial, NominalDate | NominalTime)
            or not isinstance(self.interval, RelativeInterval)
            or not isinstance(self.policy, TimePolicy)
            or not isinstance(self.visibility, SuccessorVisibility)
        ):
            raise InvalidInput("invalid_recurrence_create")

    def document(self) -> JsonDocument:
        return JsonDocument(
            json.dumps(
                {
                    "version": 1,
                    "task": self.task.document().decode(),
                    "initial": {
                        "kind": "date" if isinstance(self.initial, NominalDate) else "time",
                        "local": self.initial.local.isoformat(),
                    },
                    "interval_days": self.interval.days,
                    "policy": asdict(self.policy),
                    "visibility": self.visibility.value,
                }
            )
        )


def resolve_initial(
    times: RecurrenceTimes, initial: NominalSlot, policy: TimePolicy
) -> PlannedSlot:
    times.require_policy(policy)
    if isinstance(initial, NominalDate):
        return PlannedSlot(initial, None)
    resolved = times.resolve(initial, policy)
    if (
        not isinstance(resolved, ResolvedTime)
        or resolved.nominal != initial
        or resolved.policy != policy
    ):
        raise IntegrationUnavailable("recurrence_time_source_invalid")
    return PlannedSlot(initial, resolved)


@dataclass
class RelativeRecurrenceCommands:
    transactions: Transactions
    actor: CurrentHuman
    clock: Clock
    identifiers: Identifiers
    times: RecurrenceTimes
    household_id: str = "home"
    inventory_factory: Callable[[UnitOfWork], TaskInventory] | None = None

    def __post_init__(self) -> None:
        validate_identifier(self.household_id)

    def create(self, key: str, request: CreateRelativeTask) -> Receipt:
        payload = request.document()
        access = TaskAccess(self.actor.current())
        command = CommandKey(
            self.household_id, access.human.ha_user_id, "recurrence.relative.create", key
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
        # Actual timezone work precedes the writer; execute checks current local grants again.
        initial = resolve_initial(self.times, request.initial, request.policy)

        def apply(unit: UnitOfWork) -> Change:
            item = TaskCreation(self.clock, self.identifiers, self.inventory_factory).definition(
                unit, access, self.household_id, request.task
            )
            schedule = RelativeSchedule(
                self.identifiers.new(),
                self.household_id,
                item.definition_id,
                initial,
                request.interval,
                request.policy,
                item.created_at,
                request.visibility,
            )
            progress = RelativeProgress(
                schedule.schedule_id, self.household_id, 1, schedule.binding
            )
            unit.recurrence.save_relative_schedule(schedule, 0)
            unit.recurrence.save_relative_progress(progress, 0)
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
                    "transition": "recurrence.relative.created",
                    "request": payload.decode(),
                    "result": result.decode(),
                }
            )
            event = JsonDocument.from_value(
                {"version": 1, "kind": "recurrence.relative.created", **result.decode()}
            )
            return Change(result, detail, event)

        return commands.execute(command, payload, apply)
