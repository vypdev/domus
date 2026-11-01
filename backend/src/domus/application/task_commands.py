"""Task mutations commit local facts and retry evidence through the shared durable boundary."""

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import cast

from domus.application.commands import AtomicCommands, Change
from domus.application.identity_ports import CurrentHuman
from domus.application.ports import Clock, Identifiers, Transactions, UnitOfWork
from domus.application.task_authorization import TaskAccess
from domus.domain.errors import Conflict, Forbidden, InvalidInput
from domus.domain.identity import MemberStatus, Permission, validate_revision
from domus.domain.storage import CommandKey, JsonDocument, Receipt, validate_identifier
from domus.domain.task_values import (
    DefinitionState,
    OccurrenceState,
    TaskContent,
    TaskOverrides,
    TaskRules,
    validate_task_ids,
)
from domus.domain.tasks import HouseholdTaskPolicy, TaskDefinition, TaskOccurrence


@dataclass(frozen=True, slots=True)
class _Request:
    def document(self) -> JsonDocument:
        # Tuples and string enums become JSON arrays and exact enum values.
        return JsonDocument(json.dumps(asdict(self), ensure_ascii=False))


@dataclass(frozen=True, slots=True)
class CreateTask(_Request):
    content: TaskContent
    overrides: TaskOverrides = TaskOverrides()
    state: DefinitionState = DefinitionState.ACTIVE
    expected_revision: int = 0

    def __post_init__(self) -> None:
        if (
            type(self.expected_revision) is not int
            or self.expected_revision != 0
            or not isinstance(self.content, TaskContent)
            or not isinstance(self.overrides, TaskOverrides)
            or not isinstance(self.state, DefinitionState)
            or self.state not in (DefinitionState.DRAFT, DefinitionState.ACTIVE)
        ):
            raise InvalidInput("invalid_task_create")


@dataclass(frozen=True, slots=True)
class AssignTask(_Request):
    occurrence_id: str
    expected_revision: int
    assignee_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        validate_identifier(self.occurrence_id)
        validate_revision(self.expected_revision)
        validate_task_ids(self.assignee_ids)


@dataclass(frozen=True, slots=True)
class ClaimTask(_Request):
    occurrence_id: str
    expected_revision: int

    def __post_init__(self) -> None:
        validate_identifier(self.occurrence_id)
        validate_revision(self.expected_revision)


@dataclass(frozen=True, slots=True)
class _TaskAuthority:
    access: TaskAccess
    household_id: str
    action: str
    occurrence_id: str | None = None
    needs_configuration: bool = False

    def require(self, command: CommandKey, unit: UnitOfWork) -> None:
        if (
            command.household_id != self.household_id
            or command.actor_id != self.access.human.ha_user_id
            or command.action != self.action
        ):
            raise Forbidden("permission_denied")
        if self.action == "task.create" and self.occurrence_id is None:
            self.access.require(unit, self.household_id, Permission.TASKS_CREATE)
        elif self.action in ("task.assign", "task.claim") and self.occurrence_id is not None:
            work = unit.tasks.occurrence(self.household_id, self.occurrence_id)
            if work is None:
                raise Forbidden("permission_denied")
            if self.action == "task.claim":
                self.access.claim(unit, work)
            else:
                self.access.require(unit, self.household_id, Permission.TASKS_MANAGE, work)
        else:
            raise Forbidden("permission_denied")
        if self.needs_configuration:
            self.access.require(unit, self.household_id, Permission.TASKS_CONFIGURE)


def _occurrence(
    unit: UnitOfWork, household_id: str, request: AssignTask | ClaimTask
) -> TaskOccurrence:
    # Authority resolved this resource in the same transaction before receipt lookup.
    work = cast(TaskOccurrence, unit.tasks.occurrence(household_id, request.occurrence_id))
    if work.revision != request.expected_revision:
        raise Conflict("revision_conflict")
    return work


def _result(work: TaskOccurrence) -> JsonDocument:
    return JsonDocument.from_value(
        {
            "definition_id": work.definition_snapshot.definition_id,
            "definition_revision": work.definition_snapshot.revision,
            "occurrence_id": work.occurrence_id,
            "revision": work.revision,
            "state": work.state.value,
            "assignee_ids": list(work.assignee_ids),
        }
    )


def _change(transition: str, request: _Request, result: JsonDocument) -> Change:
    detail = JsonDocument.from_value(
        {
            "transition": transition,
            "request": request.document().decode(),
            "result": result.decode(),
        }
    )
    event = JsonDocument.from_value({"version": 1, "kind": transition, **result.decode()})
    return Change(result, detail, event)


@dataclass
class TaskCommands:
    transactions: Transactions
    actor: CurrentHuman
    clock: Clock
    identifiers: Identifiers
    household_id: str = "home"

    def __post_init__(self) -> None:
        validate_identifier(self.household_id)

    def _execute(
        self,
        key: str,
        action: str,
        request: _Request,
        apply: Callable[[UnitOfWork, TaskAccess], Change],
        *,
        occurrence_id: str | None = None,
        needs_configuration: bool = False,
    ) -> Receipt:
        human = self.actor.current()
        access = TaskAccess(human)
        command = CommandKey(self.household_id, human.ha_user_id, action, key)
        authority = _TaskAuthority(
            access, self.household_id, action, occurrence_id, needs_configuration
        )
        return AtomicCommands(self.transactions, authority, self.clock, self.identifiers).execute(
            command, request.document(), lambda unit: apply(unit, access)
        )

    def create(self, key: str, request: CreateTask) -> Receipt:
        def apply(unit: UnitOfWork, access: TaskAccess) -> Change:
            if unit.tasks.policy(self.household_id) is None:
                unit.tasks.save_policy(HouseholdTaskPolicy(self.household_id, TaskRules()), 0)
            now = self.clock.now()
            item = TaskDefinition(
                self.identifiers.new(),
                self.household_id,
                request.content,
                now,
                request.overrides,
                request.state,
            )
            work = item.new_occurrence(self.identifiers.new(), now)
            unit.tasks.save_definition(item, 0)
            unit.tasks.save_occurrence(work, 0)
            return _change("task.created", request, _result(work))

        return self._execute(
            key,
            "task.create",
            request,
            apply,
            needs_configuration=request.overrides != TaskOverrides(),
        )

    def assign(self, key: str, request: AssignTask) -> Receipt:
        def apply(unit: UnitOfWork, access: TaskAccess) -> Change:
            work = _occurrence(unit, self.household_id, request)
            for member_id in request.assignee_ids:
                member = unit.members.get(self.household_id, member_id)
                if member is None or member.status is not MemberStatus.ACTIVE:
                    raise Forbidden("task_assignee_denied")
            updated = work.assign(request.assignee_ids)
            unit.tasks.save_occurrence(updated, request.expected_revision)
            return _change("task.assigned", request, _result(updated))

        return self._execute(
            key, "task.assign", request, apply, occurrence_id=request.occurrence_id
        )

    def claim(self, key: str, request: ClaimTask) -> Receipt:
        def apply(unit: UnitOfWork, access: TaskAccess) -> Change:
            work = _occurrence(unit, self.household_id, request)
            if work.state is not OccurrenceState.AVAILABLE:
                raise Conflict("task_not_available")
            actor = access.claim(unit, work)
            updated = work.assign((actor.member.member_id,))
            unit.tasks.save_occurrence(updated, request.expected_revision)
            return _change("task.claimed", request, _result(updated))

        return self._execute(key, "task.claim", request, apply, occurrence_id=request.occurrence_id)
