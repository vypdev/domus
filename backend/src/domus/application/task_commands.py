"""Task mutations commit local facts and retry evidence through the shared durable boundary."""

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import cast

from domus.application.commands import AtomicCommands, Change
from domus.application.identity_ports import CurrentHuman
from domus.application.ports import Clock, Identifiers, Transactions, UnitOfWork
from domus.application.task_authorization import (
    TaskAccess,
    TaskCommandAuthorization,
)
from domus.application.task_creation import TaskCreation
from domus.application.task_facts import (
    current_cycle,
    definition_result,
    required_work,
    resolved_rules,
)
from domus.application.task_material_commands import TaskMaterialCommands, material_result
from domus.application.task_material_ports import TaskInventory
from domus.application.task_material_scope import MaterialScope
from domus.application.task_material_views import material_outcome
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
    ReviewTaskDependency,
    TaskRequest,
)
from domus.application.task_requests import (
    ReopenTask as ReopenTask,
)
from domus.application.task_requests import (
    SettleTaskMaterial as SettleTaskMaterial,
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
from domus.application.task_reviews import review_cycle, review_items
from domus.domain.errors import Conflict, Forbidden, NotFound
from domus.domain.identity import MemberStatus, Permission
from domus.domain.storage import CommandKey, JsonDocument, Receipt, validate_identifier
from domus.domain.task_material_values import validate_material_usages
from domus.domain.task_materials import MaterialIntent
from domus.domain.task_policy import validate_dependency_graph
from domus.domain.task_reviews import DependencyReviewDecision, DependencyReviewState
from domus.domain.task_values import (
    OccurrenceState,
    TaskOverrides,
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
    inventory_factory: Callable[[UnitOfWork], TaskInventory] | None = None

    def __post_init__(self) -> None:
        validate_identifier(self.household_id)

    def _materials(self, unit: UnitOfWork, access: TaskAccess) -> TaskMaterialCommands:
        return TaskCreation(self.clock, self.identifiers, self.inventory_factory).materials(
            unit, access, self.household_id
        )

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
        needs_material_link: bool = False,
        material_cycle_id: str | None = None,
        material_intent_id: str | None = None,
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
            needs_material_link=needs_material_link,
            material_cycle_id=material_cycle_id,
            material_intent_id=material_intent_id,
        )
        return AtomicCommands(self.transactions, authority, self.clock, self.identifiers).execute(
            command, request.document(), lambda unit: apply(unit, access)
        )

    def settle_material(self, key: str, request: SettleTaskMaterial) -> Receipt:
        def apply(unit: UnitOfWork, access: TaskAccess) -> Change:
            # Current source authority was checked before original receipt lookup.
            work = cast(
                TaskOccurrence, unit.tasks.occurrence(self.household_id, request.occurrence_id)
            )
            cycle = cast(TaskCycle, unit.tasks.cycle(self.household_id, request.cycle_id))
            original = cast(
                MaterialIntent, unit.task_materials.get(self.household_id, request.intent_id)
            )
            if original.revision != request.expected_revision:
                raise Conflict("revision_conflict")
            updated = self._materials(unit, access).settle(original, request)
            result = _cycle_result(work, cycle).decode()
            result["material"] = JsonDocument(
                json.dumps(asdict(material_outcome(updated)))
            ).decode()
            result["material_source"] = MaterialScope.source(work, cycle, original).document()
            result["material_action"] = request.action.value
            return _change("task.material.settled", request, JsonDocument.from_value(result))

        return self._execute(
            key,
            "task.material.settle",
            request,
            apply,
            occurrence_id=request.occurrence_id,
            material_cycle_id=request.cycle_id,
            material_intent_id=request.intent_id,
        )

    def review_dependency(self, key: str, request: ReviewTaskDependency) -> Receipt:
        def apply(unit: UnitOfWork, access: TaskAccess) -> Change:
            work = cast(
                TaskOccurrence, unit.tasks.occurrence(self.household_id, request.occurrence_id)
            )
            cycle = review_cycle(unit, work, request.cycle_id)
            evidence = unit.tasks.review_evidence(
                self.household_id,
                work.occurrence_id,
                cycle.cycle_id,
                limit=2,
                source_operation_id=request.source_operation_id,
            )
            items = review_items(unit, work, cycle, evidence)
            if not items:
                raise NotFound("task_dependency_review_missing")
            item = items[0]
            if request.expected_revision != item.revision:
                raise Conflict("revision_conflict")
            if item.state is DependencyReviewState.REVIEWED:
                raise Conflict("task_dependency_already_reviewed")
            actor = access.require(unit, self.household_id, Permission.TASKS_MANAGE, work)
            decision = DependencyReviewDecision(
                item.cause, actor.member.member_id, self.clock.now(), request.reason
            )
            result = _cycle_result(work, cycle).decode()
            result["review"] = decision.document().decode()
            return _change("task.dependency.reviewed", request, JsonDocument.from_value(result))

        return self._execute(
            key, "task.dependency.review", request, apply, occurrence_id=request.occurrence_id
        )

    def create(self, key: str, request: CreateTask) -> Receipt:
        def apply(unit: UnitOfWork, access: TaskAccess) -> Change:
            item = TaskCreation(self.clock, self.identifiers, self.inventory_factory).definition(
                unit, access, self.household_id, request
            )
            work = item.new_occurrence(self.identifiers.new(), item.created_at)
            unit.tasks.save_occurrence(work, 0)
            return _change("task.created", request, _result(work))

        return self._execute(
            key,
            "task.create",
            request,
            apply,
            needs_configuration=request.overrides != TaskOverrides(),
            needs_material_link=request.materials is not None,
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
            validate_material_usages(
                request.material_usages or (), work.definition_snapshot.materials
            )
            actor = access.performance_actor(unit, work, request.performer_ids)
            performers = access.performers(unit, work, request.performer_ids)
            rules, task_policy_revision = resolved_rules(unit, work)
            requirements = required_work(unit, work)
            saved = TaskCycle.record(
                self.identifiers.new(),
                self.household_id,
                work.occurrence_id,
                recorded_by=actor.member.member_id,
                performers=performers,
                rules=rules,
                definition_revision=work.definition_snapshot.revision,
                task_policy_revision=task_policy_revision,
                identity_policy_revision=actor.identity_policy_revision,
                performed_at=request.performed_at,
                recorded_at=self.clock.now(),
            )
            updated = work.complete(saved, requirements=requirements)
            unit.tasks.save_cycle(saved, 0)
            unit.tasks.save_occurrence(updated, request.expected_revision)
            result = _cycle_result(updated, saved)
            if work.definition_snapshot.materials:
                materials = self._materials(unit, access).complete(
                    work, saved, request.material_usages or ()
                )
                value = result.decode()
                value["materials"] = [material_result(material) for material in materials]
                result = JsonDocument.from_value(value)
            return _change("task.completed", request, result)

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
            current = current_cycle(unit, work, request.cycle_id)
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
            current = current_cycle(unit, work, request.cycle_id)
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
            materials = (
                None
                if request.materials is None
                else self._materials(unit, access).link(request.materials, previous.materials)
            )
            updated = previous.revise(
                request.content, overrides, request.state, materials=materials
            )
            unit.tasks.save_definition(updated, request.expected_revision)
            result = definition_result(updated)
            return _change("task.definition.updated", request, result)

        return self._execute(
            key,
            "task.definition.update",
            request,
            apply,
            definition_id=request.definition_id,
            needs_configuration=request.overrides is not None,
            needs_material_link=request.materials is not None,
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
