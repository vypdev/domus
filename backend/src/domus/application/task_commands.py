"""Task mutations commit local facts and retry evidence through the shared durable boundary."""

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import cast

from domus.application.commands import AtomicCommands, Change
from domus.application.identity_ports import CurrentHuman
from domus.application.ports import Clock, Identifiers, Transactions, UnitOfWork
from domus.application.task_authorization import TaskAccess
from domus.domain.errors import Conflict, Forbidden, InvalidInput, StorageFailure
from domus.domain.identity import MemberStatus, Permission, validate_revision
from domus.domain.storage import CommandKey, JsonDocument, Receipt, validate_identifier
from domus.domain.task_values import (
    DefinitionState,
    OccurrenceState,
    TaskContent,
    TaskOverrides,
    TaskRequirement,
    TaskRules,
    VerificationState,
    validate_task_ids,
    validate_task_text,
    validate_task_time,
)
from domus.domain.tasks import HouseholdTaskPolicy, TaskCycle, TaskDefinition, TaskOccurrence


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
class _ExistingTask(_Request):
    occurrence_id: str
    expected_revision: int

    def __post_init__(self) -> None:
        validate_identifier(self.occurrence_id)
        validate_revision(self.expected_revision)


@dataclass(frozen=True, slots=True)
class AssignTask(_ExistingTask):
    assignee_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _ExistingTask.__post_init__(self)
        validate_task_ids(self.assignee_ids)


@dataclass(frozen=True, slots=True)
class ClaimTask(_ExistingTask):
    pass


@dataclass(frozen=True, slots=True)
class TransitionTask(_ExistingTask):
    target: OccurrenceState
    reason: str = ""

    def __post_init__(self) -> None:
        _ExistingTask.__post_init__(self)
        if not isinstance(self.target, OccurrenceState) or self.target in (
            OccurrenceState.DRAFT,
            OccurrenceState.COMPLETED,
        ):
            raise InvalidInput("invalid_task_transition")
        validate_task_text(
            self.reason,
            1000,
            required=self.target
            in (OccurrenceState.BLOCKED, OccurrenceState.CANCELLED, OccurrenceState.SKIPPED),
            multiline=True,
        )


@dataclass(frozen=True, slots=True)
class CompleteTask(_ExistingTask):
    performer_ids: tuple[str, ...]
    performed_at: int

    def __post_init__(self) -> None:
        _ExistingTask.__post_init__(self)
        validate_task_ids(self.performer_ids)
        if not self.performer_ids:
            raise InvalidInput("invalid_task_performer")
        validate_task_time(self.performed_at)


@dataclass(frozen=True, slots=True)
class VerifyTask(_ExistingTask):
    cycle_id: str
    decision: VerificationState
    reason: str = ""

    def __post_init__(self) -> None:
        _ExistingTask.__post_init__(self)
        validate_identifier(self.cycle_id)
        if not isinstance(self.decision, VerificationState) or self.decision not in (
            VerificationState.APPROVED,
            VerificationState.REJECTED,
        ):
            raise InvalidInput("invalid_task_verification")
        validate_task_text(
            self.reason, 1000, required=self.decision is VerificationState.REJECTED, multiline=True
        )


@dataclass(frozen=True, slots=True)
class ReopenTask(_ExistingTask):
    cycle_id: str
    reason: str

    def __post_init__(self) -> None:
        _ExistingTask.__post_init__(self)
        validate_identifier(self.cycle_id)
        validate_task_text(self.reason, 1000, required=True, multiline=True)


_SCOPED_PERMISSIONS = {
    "task.assign": Permission.TASKS_MANAGE,
    "task.claim": Permission.TASKS_CLAIM,
    "task.transition": Permission.TASKS_MANAGE,
    "task.complete": Permission.TASKS_COMPLETE,
    "task.verify": Permission.TASKS_APPROVE,
    "task.reopen": Permission.TASKS_MANAGE,
}


@dataclass(frozen=True, slots=True)
class _TaskAuthority:
    access: TaskAccess
    household_id: str
    action: str
    occurrence_id: str | None = None
    needs_configuration: bool = False
    performer_ids: tuple[str, ...] = ()
    transition_target: OccurrenceState | None = None

    def require(self, command: CommandKey, unit: UnitOfWork) -> None:
        if (
            command.household_id != self.household_id
            or command.actor_id != self.access.human.ha_user_id
            or command.action != self.action
        ):
            raise Forbidden("permission_denied")
        if self.action == "task.create" and self.occurrence_id is None:
            self.access.require(unit, self.household_id, Permission.TASKS_CREATE)
        elif self.action in _SCOPED_PERMISSIONS and self.occurrence_id is not None:
            work = unit.tasks.occurrence(self.household_id, self.occurrence_id)
            if work is None:
                raise Forbidden("permission_denied")
            if self.action == "task.claim":
                self.access.claim(unit, work)
            elif self.action == "task.complete":
                self.access.performance_actor(unit, work, self.performer_ids)
            else:
                permission = _SCOPED_PERMISSIONS[self.action]
                if self.action == "task.transition":
                    if not isinstance(self.transition_target, OccurrenceState):
                        raise Forbidden("permission_denied")
                    if self.transition_target in (
                        OccurrenceState.IN_PROGRESS,
                        OccurrenceState.BLOCKED,
                        OccurrenceState.ASSIGNED,
                    ):
                        permission = Permission.TASKS_COMPLETE
                self.access.require(unit, self.household_id, permission, work)
        else:
            raise Forbidden("permission_denied")
        if self.needs_configuration:
            self.access.require(unit, self.household_id, Permission.TASKS_CONFIGURE)


def _occurrence(unit: UnitOfWork, household_id: str, request: _ExistingTask) -> TaskOccurrence:
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
            "state_reason": work.state_reason,
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


def _cycle(unit: UnitOfWork, work: TaskOccurrence, cycle_id: str) -> TaskCycle:
    if work.current_cycle_id != cycle_id:
        raise Conflict("task_cycle_conflict")
    cycle = unit.tasks.cycle(work.household_id, cycle_id)
    if (
        cycle is None
        or cycle.household_id != work.household_id
        or cycle.occurrence_id != work.occurrence_id
        or cycle.revision != work.current_cycle_revision
        or cycle.closed_at is not None
    ):
        raise StorageFailure("invalid_task_references")
    return cycle


def _requirements(unit: UnitOfWork, work: TaskOccurrence) -> tuple[TaskRequirement, ...]:
    result = []
    for identity in sorted(set(work.prerequisite_ids) | set(work.required_subtask_ids)):
        required = unit.tasks.occurrence(work.household_id, identity)
        if required is None:
            raise StorageFailure("invalid_task_references")
        verification = None
        if required.state is OccurrenceState.COMPLETED:
            verification = _cycle(unit, required, cast(str, required.current_cycle_id)).verification
        result.append(TaskRequirement(identity, required.state, verification))
    return tuple(result)


def _cycle_result(
    work: TaskOccurrence, cycle: TaskCycle, *, reopened: bool = False
) -> JsonDocument:
    value = _result(work).decode()
    value["cycle"] = JsonDocument(json.dumps(asdict(cycle), ensure_ascii=False)).decode()
    value["consumer_delivery"] = "unconfirmed"
    if reopened:
        value["compensates_cycle_id"] = cycle.cycle_id
        value["dependency_review_required"] = True
    return JsonDocument.from_value(value)


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
        performer_ids: tuple[str, ...] = (),
        transition_target: OccurrenceState | None = None,
    ) -> Receipt:
        human = self.actor.current()
        access = TaskAccess(human)
        command = CommandKey(self.household_id, human.ha_user_id, action, key)
        authority = _TaskAuthority(
            access,
            self.household_id,
            action,
            occurrence_id,
            needs_configuration,
            performer_ids,
            transition_target,
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

    def transition(self, key: str, request: TransitionTask) -> Receipt:
        def apply(unit: UnitOfWork, access: TaskAccess) -> Change:
            work = _occurrence(unit, self.household_id, request)
            updated = work.transition(request.target, request.reason)
            unit.tasks.save_occurrence(updated, request.expected_revision)
            return _change("task.transitioned", request, _result(updated))

        return self._execute(
            key,
            "task.transition",
            request,
            apply,
            occurrence_id=request.occurrence_id,
            transition_target=request.target,
        )

    def complete(self, key: str, request: CompleteTask) -> Receipt:
        def apply(unit: UnitOfWork, access: TaskAccess) -> Change:
            work = _occurrence(unit, self.household_id, request)
            actor = access.performance_actor(unit, work, request.performer_ids)
            performers = access.performers(unit, work, request.performer_ids)
            policy = unit.tasks.policy(self.household_id)
            if policy is None:
                raise StorageFailure("invalid_task_references")
            rules = work.definition_snapshot.overrides.resolve(policy.rules)
            requirements = _requirements(unit, work)
            saved = TaskCycle.record(
                self.identifiers.new(),
                self.household_id,
                work.occurrence_id,
                recorded_by=actor.member.member_id,
                performers=performers,
                rules=rules,
                definition_revision=work.definition_snapshot.revision,
                task_policy_revision=policy.revision,
                identity_policy_revision=actor.identity_policy_revision,
                performed_at=request.performed_at,
                recorded_at=self.clock.now(),
            )
            updated = work.complete(saved, requirements=requirements)
            unit.tasks.save_cycle(saved, 0)
            unit.tasks.save_occurrence(updated, request.expected_revision)
            return _change("task.completed", request, _cycle_result(updated, saved))

        return self._execute(
            key,
            "task.complete",
            request,
            apply,
            occurrence_id=request.occurrence_id,
            performer_ids=request.performer_ids,
        )

    def verify(self, key: str, request: VerifyTask) -> Receipt:
        def apply(unit: UnitOfWork, access: TaskAccess) -> Change:
            work = _occurrence(unit, self.household_id, request)
            current = _cycle(unit, work, request.cycle_id)
            verifier = access.approver(unit, work, current)
            updated, saved = work.verify(
                current, request.decision, verifier, self.clock.now(), request.reason
            )
            unit.tasks.save_cycle(saved, current.revision)
            unit.tasks.save_occurrence(updated, request.expected_revision)
            return _change("task.verified", request, _cycle_result(updated, saved))

        return self._execute(
            key, "task.verify", request, apply, occurrence_id=request.occurrence_id
        )

    def reopen(self, key: str, request: ReopenTask) -> Receipt:
        def apply(unit: UnitOfWork, access: TaskAccess) -> Change:
            work = _occurrence(unit, self.household_id, request)
            current = _cycle(unit, work, request.cycle_id)
            updated, closed = work.reopen(current, self.clock.now(), request.reason)
            unit.tasks.save_cycle(closed, current.revision)
            unit.tasks.save_occurrence(updated, request.expected_revision)
            return _change("task.reopened", request, _cycle_result(updated, closed, reopened=True))

        return self._execute(
            key, "task.reopen", request, apply, occurrence_id=request.occurrence_id
        )
