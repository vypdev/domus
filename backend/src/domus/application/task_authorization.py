"""Current task authority reads local facts; performer snapshots never confer grants."""

from dataclasses import dataclass

from domus.application.ports import UnitOfWork
from domus.domain.errors import Forbidden, InvalidInput, StorageFailure
from domus.domain.identity import (
    HumanIdentity,
    Member,
    MemberStatus,
    Permission,
    Role,
    allows,
    effective_role,
)
from domus.domain.storage import CommandKey, validate_identifier
from domus.domain.task_policy import can_approve, claim_matches_task
from domus.domain.task_values import OccurrenceState, TaskPerformer, validate_task_ids
from domus.domain.tasks import TaskCycle, TaskOccurrence

_TASK_PERMISSIONS = frozenset(
    {
        Permission.TASKS_READ,
        Permission.TASKS_CREATE,
        Permission.TASKS_CLAIM,
        Permission.TASKS_MANAGE,
        Permission.TASKS_COMPLETE,
        Permission.TASKS_RECORD_FOR_OTHERS,
        Permission.TASKS_APPROVE,
        Permission.TASKS_CONFIGURE,
        Permission.TASKS_MATERIAL_USE,
    }
)


@dataclass(frozen=True, slots=True)
class TaskActor:
    member: Member
    role: Role
    identity_policy_revision: int

    @property
    def performer(self) -> TaskPerformer:
        return TaskPerformer(self.member.member_id, self.role)


@dataclass(frozen=True, slots=True)
class TaskAccess:
    """Compositions supply current human proof; commands invoke this inside the transaction.

    These checks confer authority only. State, capacity, revision and cycle checks
    remain command preconditions, after an authorized original-receipt lookup.
    """

    human: HumanIdentity

    def _current(self, unit: UnitOfWork, occurrence: TaskOccurrence) -> TaskOccurrence:
        current = unit.tasks.occurrence(occurrence.household_id, occurrence.occurrence_id)
        if current is None:
            raise Forbidden("permission_denied")
        return current

    def require(
        self,
        unit: UnitOfWork,
        household_id: str,
        permission: Permission,
        occurrence: TaskOccurrence | None = None,
    ) -> TaskActor:
        validate_identifier(household_id)
        if (
            not isinstance(permission, Permission)
            or permission not in _TASK_PERMISSIONS
            or (occurrence is not None and occurrence.household_id != household_id)
        ):
            raise Forbidden("permission_denied")
        member = unit.members.by_user(household_id, self.human.ha_user_id)
        policy = unit.policies.get(household_id)
        if member is None or policy is None:
            raise Forbidden("permission_denied")
        assignees = () if occurrence is None else self._current(unit, occurrence).assignee_ids
        role = effective_role(self.human, member, policy)
        if role is None or not allows(
            self.human,
            member,
            policy,
            permission,
            household_id,
            assigned_to=assignees,
        ):
            raise Forbidden("permission_denied")
        return TaskActor(member, role, policy.revision)

    def claim(self, unit: UnitOfWork, occurrence: TaskOccurrence) -> TaskActor:
        actor = self.require(unit, occurrence.household_id, Permission.TASKS_CLAIM, occurrence)
        policy = unit.tasks.policy(occurrence.household_id)
        if policy is None:
            raise StorageFailure("invalid_task_references")
        current = self._current(unit, occurrence)
        rules = current.definition_snapshot.overrides.resolve(policy.rules)
        if not claim_matches_task(actor.role, rules):
            raise Forbidden("task_claim_denied")
        return actor

    def performance_actor(
        self, unit: UnitOfWork, occurrence: TaskOccurrence, member_ids: tuple[str, ...]
    ) -> TaskActor:
        """Current attribution grants only; participant eligibility follows receipt lookup."""
        actor = self.require(unit, occurrence.household_id, Permission.TASKS_COMPLETE, occurrence)
        validate_task_ids(member_ids)
        if not member_ids:
            raise InvalidInput("invalid_task_performer")
        if actor.role is Role.RESTRICTED and actor.member.member_id not in member_ids:
            raise Forbidden("task_performer_denied")
        if any(member_id != actor.member.member_id for member_id in member_ids):
            self.require(unit, occurrence.household_id, Permission.TASKS_RECORD_FOR_OTHERS)
        return actor

    def performers(
        self, unit: UnitOfWork, occurrence: TaskOccurrence, member_ids: tuple[str, ...]
    ) -> tuple[TaskPerformer, ...]:
        actor = self.performance_actor(unit, occurrence, member_ids)
        performers = []
        for member_id in member_ids:
            person = unit.members.get(occurrence.household_id, member_id)
            if person is None or person.status is not MemberStatus.ACTIVE:
                raise Forbidden("task_performer_denied")
            # Only the actor has current HA proof. Other performers retain their
            # local profile; an assumed external administrator grant is unsafe.
            role = actor.role if member_id == actor.member.member_id else person.role
            performers.append(TaskPerformer(member_id, role))
        return tuple(performers)

    def approver(
        self, unit: UnitOfWork, occurrence: TaskOccurrence, cycle: TaskCycle
    ) -> TaskPerformer:
        actor = self.require(unit, occurrence.household_id, Permission.TASKS_APPROVE, occurrence)
        if (
            cycle.household_id != occurrence.household_id
            or cycle.occurrence_id != occurrence.occurrence_id
        ):
            raise InvalidInput("invalid_task_cycle")
        if not can_approve(
            actor.performer,
            cycle.performers,
            independent=not cycle.rules.adult_performer_may_approve,
        ):
            raise Forbidden("task_approval_denied")
        return actor.performer


_SCOPED_PERMISSIONS = {
    "task.assign": Permission.TASKS_MANAGE,
    "task.claim": Permission.TASKS_CLAIM,
    "task.transition": Permission.TASKS_MANAGE,
    "task.complete": Permission.TASKS_COMPLETE,
    "task.verify": Permission.TASKS_APPROVE,
    "task.reopen": Permission.TASKS_MANAGE,
    "task.dependencies.update": Permission.TASKS_MANAGE,
}
_GLOBAL_PERMISSIONS = {
    "task.create": Permission.TASKS_CREATE,
    "task.policy.update": Permission.TASKS_CONFIGURE,
}
_DEFINITION_ACTIONS = frozenset({"task.definition.update", "task.occurrence.create"})


@dataclass(frozen=True, slots=True)
class TaskCommandAuthorization:
    access: TaskAccess
    household_id: str
    action: str
    occurrence_id: str | None = None
    needs_configuration: bool = False
    performer_ids: tuple[str, ...] = ()
    transition_target: OccurrenceState | None = None
    definition_id: str | None = None

    def require(self, command: CommandKey, unit: UnitOfWork) -> None:
        if (
            command.household_id != self.household_id
            or command.actor_id != self.access.human.ha_user_id
            or command.action != self.action
        ):
            raise Forbidden("permission_denied")
        if (
            self.action in _GLOBAL_PERMISSIONS
            and self.occurrence_id is None
            and self.definition_id is None
        ):
            self.access.require(unit, self.household_id, _GLOBAL_PERMISSIONS[self.action])
        elif (
            self.action in _DEFINITION_ACTIONS
            and self.definition_id is not None
            and self.occurrence_id is None
        ):
            self.access.require(unit, self.household_id, Permission.TASKS_MANAGE)
            if unit.tasks.definition(self.household_id, self.definition_id) is None:
                raise Forbidden("permission_denied")
        elif (
            self.action in _SCOPED_PERMISSIONS
            and self.occurrence_id is not None
            and self.definition_id is None
        ):
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
