"""Task mutations commit local facts and retry evidence through the shared durable boundary."""

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import cast

from domus.application.commands import AtomicCommands, Change
from domus.application.identity_ports import CurrentHuman
from domus.application.ports import Clock, Identifiers, Transactions, UnitOfWork
from domus.application.task_authorization import TaskAccess, TaskCommandAuthorization
from domus.application.task_requests import (
    AssignTask as AssignTask,
)
from domus.application.task_requests import (
    ClaimTask as ClaimTask,
)
from domus.application.task_requests import (
    CompleteTask as CompleteTask,
)
from domus.application.task_requests import (
    CreateTask as CreateTask,
)
from domus.application.task_requests import (
    CreateTaskOccurrence as CreateTaskOccurrence,
)
from domus.application.task_requests import (
    OccurrenceRequest,
    TaskRequest,
)
from domus.application.task_requests import (
    ReopenTask as ReopenTask,
)
from domus.application.task_requests import (
    TransitionTask as TransitionTask,
)
from domus.application.task_requests import (
    UpdateTaskDefinition as UpdateTaskDefinition,
)
from domus.application.task_requests import (
    UpdateTaskDependencies as UpdateTaskDependencies,
)
from domus.application.task_requests import (
    UpdateTaskPolicy as UpdateTaskPolicy,
)
from domus.application.task_requests import (
    VerifyTask as VerifyTask,
)
from domus.domain.errors import Conflict, Forbidden, StorageFailure
from domus.domain.identity import MemberStatus
from domus.domain.storage import CommandKey, JsonDocument, Receipt, validate_identifier
from domus.domain.task_policy import validate_dependency_graph
from domus.domain.task_values import (
    OccurrenceState,
    TaskOverrides,
    TaskRequirement,
    TaskRules,
)
from domus.domain.tasks import HouseholdTaskPolicy, TaskCycle, TaskDefinition, TaskOccurrence


def _occurrence(unit: UnitOfWork, household_id: str, request: OccurrenceRequest) -> TaskOccurrence:
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
            "prerequisite_ids": list(work.prerequisite_ids),
            "required_subtask_ids": list(work.required_subtask_ids),
        }
    )


def _change(transition: str, request: TaskRequest, result: JsonDocument) -> Change:
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


def _assignees(unit: UnitOfWork, household_id: str, member_ids: tuple[str, ...]) -> None:
    for member_id in member_ids:
        member = unit.members.get(household_id, member_id)
        if member is None or member.status is not MemberStatus.ACTIVE:
            raise Forbidden("task_assignee_denied")


def _graph(unit: UnitOfWork, proposed: TaskOccurrence) -> None:
    graph: dict[str, tuple[str, ...]] = {}
    after: str | None = None
    while batch := unit.tasks.occurrences(proposed.household_id, limit=101, after=after):
        for work in batch:
            graph[work.occurrence_id] = tuple(
                set(work.prerequisite_ids) | set(work.required_subtask_ids)
            )
        after = batch[-1].occurrence_id
    graph[proposed.occurrence_id] = tuple(
        set(proposed.prerequisite_ids) | set(proposed.required_subtask_ids)
    )
    validate_dependency_graph(graph)


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
        request: TaskRequest,
        apply: Callable[[UnitOfWork, TaskAccess], Change],
        *,
        occurrence_id: str | None = None,
        needs_configuration: bool = False,
        performer_ids: tuple[str, ...] = (),
        transition_target: OccurrenceState | None = None,
        definition_id: str | None = None,
    ) -> Receipt:
        human = self.actor.current()
        access = TaskAccess(human)
        command = CommandKey(self.household_id, human.ha_user_id, action, key)
        authority = TaskCommandAuthorization(
            access=access,
            household_id=self.household_id,
            action=action,
            occurrence_id=occurrence_id,
            needs_configuration=needs_configuration,
            performer_ids=performer_ids,
            transition_target=transition_target,
            definition_id=definition_id,
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
            _assignees(unit, self.household_id, request.assignee_ids)
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

    def update_policy(self, key: str, request: UpdateTaskPolicy) -> Receipt:
        def apply(unit: UnitOfWork, access: TaskAccess) -> Change:
            previous = unit.tasks.policy(self.household_id)
            revision = 0 if previous is None else previous.revision
            if revision != request.expected_revision:
                raise Conflict("revision_conflict")
            updated = (
                HouseholdTaskPolicy(self.household_id, request.rules)
                if previous is None
                else previous.revise(request.rules)
            )
            unit.tasks.save_policy(updated, revision)
            result = JsonDocument(
                json.dumps(
                    {"revision": updated.revision, "rules": asdict(updated.rules)},
                    ensure_ascii=False,
                )
            )
            return _change("task.policy.updated", request, result)

        return self._execute(key, "task.policy.update", request, apply)

    def update_definition(self, key: str, request: UpdateTaskDefinition) -> Receipt:
        def apply(unit: UnitOfWork, access: TaskAccess) -> Change:
            previous = cast(
                TaskDefinition, unit.tasks.definition(self.household_id, request.definition_id)
            )
            if previous.revision != request.expected_revision:
                raise Conflict("revision_conflict")
            overrides = previous.overrides if request.overrides is None else request.overrides
            updated = previous.revise(request.content, overrides, request.state)
            unit.tasks.save_definition(updated, request.expected_revision)
            result = JsonDocument(json.dumps(asdict(updated), ensure_ascii=False))
            return _change("task.definition.updated", request, result)

        return self._execute(
            key,
            "task.definition.update",
            request,
            apply,
            definition_id=request.definition_id,
            needs_configuration=request.overrides is not None,
        )

    def create_occurrence(self, key: str, request: CreateTaskOccurrence) -> Receipt:
        def apply(unit: UnitOfWork, access: TaskAccess) -> Change:
            item = cast(
                TaskDefinition, unit.tasks.definition(self.household_id, request.definition_id)
            )
            _assignees(unit, self.household_id, request.assignee_ids)
            work = item.new_occurrence(
                self.identifiers.new(),
                self.clock.now(),
                assignees=request.assignee_ids,
                prerequisites=request.prerequisite_ids,
                required_subtasks=request.required_subtask_ids,
                due_at=request.due_at,
            )
            _graph(unit, work)
            unit.tasks.save_occurrence(work, 0)
            return _change("task.occurrence.created", request, _result(work))

        return self._execute(
            key, "task.occurrence.create", request, apply, definition_id=request.definition_id
        )

    def update_dependencies(self, key: str, request: UpdateTaskDependencies) -> Receipt:
        def apply(unit: UnitOfWork, access: TaskAccess) -> Change:
            previous = _occurrence(unit, self.household_id, request)
            updated = previous.dependencies(request.prerequisite_ids, request.required_subtask_ids)
            _graph(unit, updated)
            unit.tasks.save_occurrence(updated, request.expected_revision)
            return _change("task.dependencies.updated", request, _result(updated))

        return self._execute(
            key, "task.dependencies.update", request, apply, occurrence_id=request.occurrence_id
        )
