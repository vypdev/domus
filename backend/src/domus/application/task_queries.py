"""Bounded local task reads and current action hints never mutate or establish write authority."""

from collections.abc import Callable
from dataclasses import dataclass, replace
from functools import partial
from typing import cast

from domus.application.authorization import HouseholdAccess
from domus.application.household_queries import OperationView
from domus.application.ports import Transactions, UnitOfWork
from domus.application.task_authorization import (
    TaskAccess,
    TaskActor,
    TaskCommandAuthorization,
    recorded_authorization,
    recorded_request,
)
from domus.application.task_facts import current_cycle, required_work, resolved_rules
from domus.application.task_ports import TaskCursors
from domus.domain.errors import Conflict, Forbidden, InvalidInput, NotFound, StorageFailure
from domus.domain.identity import HumanIdentity, Permission, validate_revision
from domus.domain.restoration import RetainedOperation
from domus.domain.storage import (
    CommandKey,
    Installation,
    JsonDocument,
    RestorationProvenance,
    validate_identifier,
)
from domus.domain.task_policy import require_completion_state, requirements_satisfied
from domus.domain.task_values import (
    DefinitionState,
    OccurrenceState,
    Priority,
    TaskRequirement,
    TaskRules,
    VerificationState,
    validate_task_text,
    validate_task_time,
)
from domus.domain.tasks import TaskCycle, TaskDefinition, TaskOccurrence


@dataclass(frozen=True, slots=True)
class TaskPage[T]:
    items: tuple[T, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class TaskPolicyView:
    rules: TaskRules
    revision: int
    can_configure: bool


@dataclass(frozen=True, slots=True)
class DefinitionSummary:
    definition_id: str
    title: str
    state: DefinitionState
    priority: Priority
    tags: tuple[str, ...]
    revision: int


@dataclass(frozen=True, slots=True)
class OccurrenceSummary:
    occurrence_id: str
    definition_id: str
    definition_revision: int
    title: str
    state: OccurrenceState
    revision: int
    assignee_ids: tuple[str, ...]
    due_at: int | None
    current_cycle_id: str | None


@dataclass(frozen=True, slots=True)
class TaskDetail:
    work: TaskOccurrence
    rules: TaskRules
    task_policy_revision: int
    requirements: tuple[TaskRequirement, ...]
    cycle: TaskCycle | None
    allowed_actions: tuple[str, ...]
    consumer_delivery: str = "unconfirmed"


@dataclass(frozen=True, slots=True)
class TaskHistoryItem:
    operation_id: str
    action: str
    actor_member_id: str | None
    created_at: int
    revision: int
    state: OccurrenceState
    cycle_id: str | None
    verification: VerificationState | None
    performed_at: int | None
    reason: str
    historical: bool
    archived_by: str | None
    outbox_delivery: str
    consumer_delivery: str = "unconfirmed"


def _possible(check: Callable[[], object]) -> bool:
    try:
        check()
    except Forbidden, Conflict, InvalidInput:
        return False
    return True


@dataclass(frozen=True, slots=True)
class TaskQueries:
    """Composition supplies proven identity or a valid outage lease, never caller actor IDs."""

    transactions: Transactions
    human: HumanIdentity
    cursors: TaskCursors
    installation: Installation
    household_id: str = "home"

    def __post_init__(self) -> None:
        validate_identifier(self.household_id)

    def _read(self, unit: UnitOfWork) -> TaskActor:
        return TaskAccess(self.human).require(unit, self.household_id, Permission.TASKS_READ)

    def _context(
        self, kind: str, limit: int, filters: JsonDocument, cursor: str | None
    ) -> tuple[JsonDocument, str | None]:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise InvalidInput("invalid_page_size")
        binding = JsonDocument.from_value(
            {
                "version": 1,
                "instance": self.installation.instance_id,
                "channel": self.installation.channel,
                "household": self.household_id,
                "actor": self.human.ha_user_id,
                "query": kind,
                "limit": limit,
                "filters": filters.decode(),
            }
        )
        return binding, None if cursor is None else self.cursors.decode(binding, cursor)

    def _page[T](
        self, items: tuple[T, ...], limit: int, binding: JsonDocument, key: Callable[[T], str]
    ) -> TaskPage[T]:
        return TaskPage(
            items[:limit],
            self.cursors.encode(binding, key(items[limit - 1])) if len(items) > limit else None,
        )

    def policy(self) -> TaskPolicyView:
        with self.transactions.read() as unit:
            self._read(unit)
            policy = unit.tasks.policy(self.household_id)
            return TaskPolicyView(
                TaskRules() if policy is None else policy.rules,
                0 if policy is None else policy.revision,
                _possible(
                    lambda: TaskAccess(self.human).require(
                        unit, self.household_id, Permission.TASKS_CONFIGURE
                    )
                ),
            )

    def definition(self, definition_id: str) -> TaskDefinition:
        with self.transactions.read() as unit:
            self._read(unit)
            result = unit.tasks.definition(self.household_id, definition_id)
            if result is None:
                raise NotFound("task_definition_missing")
            return result

    def definitions(
        self, *, limit: int = 25, cursor: str | None = None, state: DefinitionState | None = None
    ) -> TaskPage[DefinitionSummary]:
        with self.transactions.read() as unit:
            self._read(unit)
            if state is not None and not isinstance(state, DefinitionState):
                raise InvalidInput("invalid_task_query")
            binding, after = self._context(
                "definitions",
                limit,
                JsonDocument.from_value({"state": None if state is None else state.value}),
                cursor,
            )
            rows = unit.tasks.definitions(
                self.household_id, limit=limit + 1, after=after, state=state
            )
            summaries = tuple(
                DefinitionSummary(
                    item.definition_id,
                    item.content.title,
                    item.state,
                    item.content.priority,
                    item.content.tags,
                    item.revision,
                )
                for item in rows
            )
            return self._page(summaries, limit, binding, lambda item: item.definition_id)

    def occurrences(
        self,
        *,
        limit: int = 25,
        cursor: str | None = None,
        state: OccurrenceState | None = None,
        definition_id: str | None = None,
        assignee_id: str | None = None,
    ) -> TaskPage[OccurrenceSummary]:
        with self.transactions.read() as unit:
            self._read(unit)
            if state is not None and not isinstance(state, OccurrenceState):
                raise InvalidInput("invalid_task_query")
            for identity in (definition_id, assignee_id):
                if identity is not None:
                    validate_identifier(identity)
            binding, after = self._context(
                "occurrences",
                limit,
                JsonDocument.from_value(
                    {
                        "state": None if state is None else state.value,
                        "definition_id": definition_id,
                        "assignee_id": assignee_id,
                    }
                ),
                cursor,
            )
            rows = unit.tasks.occurrences(
                self.household_id,
                limit=limit + 1,
                after=after,
                state=state,
                definition_id=definition_id,
                assignee_id=assignee_id,
            )
            summaries = tuple(
                OccurrenceSummary(
                    item.occurrence_id,
                    item.definition_snapshot.definition_id,
                    item.definition_snapshot.revision,
                    item.definition_snapshot.content.title,
                    item.state,
                    item.revision,
                    item.assignee_ids,
                    item.due_at,
                    item.current_cycle_id,
                )
                for item in rows
            )
            return self._page(summaries, limit, binding, lambda item: item.occurrence_id)

    def occurrence(self, occurrence_id: str) -> TaskDetail:
        with self.transactions.read() as unit:
            actor = self._read(unit)
            work = unit.tasks.occurrence(self.household_id, occurrence_id)
            if work is None:
                raise NotFound("task_occurrence_missing")
            rules, revision = resolved_rules(unit, work)
            requirements = required_work(unit, work)
            cycle = (
                None
                if work.current_cycle_id is None
                else current_cycle(unit, work, work.current_cycle_id)
            )
            return TaskDetail(
                work,
                rules,
                revision,
                requirements,
                cycle,
                self._actions(unit, actor, work, rules, requirements, cycle),
            )

    def history(
        self, occurrence_id: str, *, limit: int = 25, cursor: str | None = None
    ) -> TaskPage[TaskHistoryItem]:
        with self.transactions.read() as unit:
            self._read(unit)
            validate_identifier(occurrence_id)
            binding, marker = self._context(
                "history", limit, JsonDocument.from_value({"occurrence_id": occurrence_id}), cursor
            )
            after = 0
            if marker is not None:
                if (
                    not marker.isascii()
                    or not marker.isdecimal()
                    or not 1 <= int(marker) <= 2**63 - 1
                    or str(int(marker)) != marker
                ):
                    raise InvalidInput("invalid_task_cursor")
                after = int(marker)
            if unit.tasks.occurrence(self.household_id, occurrence_id) is None:
                raise NotFound("task_occurrence_missing")
            rows = unit.tasks.history(
                self.household_id, occurrence_id, limit=limit + 1, after=after
            )
            page = self._page(rows, limit, binding, lambda item: str(item.evidence.position))
            return TaskPage(
                tuple(self._history_item(unit, occurrence_id, row) for row in page.items),
                page.next_cursor,
            )

    def _history_item(
        self, unit: UnitOfWork, occurrence_id: str, row: RetainedOperation
    ) -> TaskHistoryItem:
        evidence = row.evidence
        recorded_request(evidence)
        value = evidence.receipt.result.decode()
        try:
            if value.get("occurrence_id") != occurrence_id:
                raise InvalidInput("invalid_task_operation")
            revision = cast(int, value.get("revision"))
            validate_revision(revision)
            state = OccurrenceState(cast(str, value.get("state")))
            reason = cast(str, value.get("state_reason", ""))
            validate_task_text(reason, 1000, required=False, multiline=True)
            cycle = value.get("cycle")
            cycle_id = verification = performed_at = None
            if cycle is not None:
                if not isinstance(cycle, dict):
                    raise InvalidInput("invalid_task_cycle")
                cycle_id = cast(str, cycle.get("cycle_id"))
                validate_identifier(cycle_id)
                verification = VerificationState(cast(str, cycle.get("verification")))
                performed_at = cast(int, cycle.get("performed_at"))
                validate_task_time(performed_at)
                if (
                    cycle.get("household_id") != self.household_id
                    or cycle.get("occurrence_id") != occurrence_id
                ):
                    raise InvalidInput("invalid_task_cycle")
            elif state is OccurrenceState.COMPLETED:
                raise InvalidInput("invalid_task_cycle")
        except InvalidInput, ValueError:
            raise StorageFailure("invalid_task_operation") from None
        member = unit.members.by_user(self.household_id, evidence.receipt.command.actor_id)
        return TaskHistoryItem(
            evidence.receipt.operation_id,
            evidence.receipt.command.action,
            None if member is None else member.member_id,
            evidence.receipt.created_at,
            revision,
            state,
            cycle_id,
            verification,
            performed_at,
            reason,
            not row.current,
            row.archived_by,
            "suppressed"
            if not row.current
            else "acknowledged"
            if evidence.delivered
            else "pending",
        )

    def operation(self, operation_id: str) -> OperationView:
        validate_identifier(operation_id)
        with self.transactions.read() as unit:
            actor = self._read(unit)
            HouseholdAccess(self.human).require(
                unit,
                self.household_id,
                Permission.OPERATIONS_READ,
                subject_member_id=actor.member.member_id,
            )
            row = unit.tasks.operation(self.household_id, self.human.ha_user_id, operation_id)
            if row is None:
                raise NotFound("operation_missing")
            authority = recorded_authorization(TaskAccess(self.human), row.evidence)
            authority.require(row.evidence.receipt.command, unit)
            receipt = replace(
                row.evidence.receipt,
                restoration=None
                if row.archived_by is None
                else RestorationProvenance(row.archived_by, row.current),
            )
            return OperationView(receipt, row.evidence.delivered)

    def _actions(
        self,
        unit: UnitOfWork,
        actor: TaskActor,
        work: TaskOccurrence,
        rules: TaskRules,
        requirements: tuple[TaskRequirement, ...],
        cycle: TaskCycle | None,
    ) -> tuple[str, ...]:
        if work.revision == 2**63 - 1:
            return ()
        access = TaskAccess(self.human)
        result = []
        manage = _possible(
            lambda: access.require(unit, self.household_id, Permission.TASKS_MANAGE, work)
        )
        if work.state not in (
            OccurrenceState.COMPLETED,
            OccurrenceState.CANCELLED,
            OccurrenceState.SKIPPED,
        ):
            if manage:
                result.append("dependencies.update")
                if work.state is not OccurrenceState.DRAFT:
                    result.append("assign")
            if work.state is OccurrenceState.AVAILABLE and _possible(
                lambda: access.claim(unit, work)
            ):
                result.append("claim")

        def transition(target: OccurrenceState) -> None:
            TaskCommandAuthorization(
                access,
                self.household_id,
                "task.transition",
                work.occurrence_id,
                transition_target=target,
            ).require(
                CommandKey(self.household_id, self.human.ha_user_id, "task.transition", "preview"),
                unit,
            )
            work.transition(target, "Preview")

        for target in OccurrenceState:
            if _possible(partial(transition, target)):
                result.append("transition:" + target.value)

        def complete() -> None:
            access.performance_actor(unit, work, (actor.member.member_id,))
            require_completion_state(work.state)
            if not requirements_satisfied(requirements, rules.dependency_gate):
                raise Conflict("task_dependencies_incomplete")

        if _possible(complete):
            result.append("complete")
        if cycle is not None and cycle.revision < 2**63 - 1:
            if cycle.verification is VerificationState.PENDING and _possible(
                lambda: access.approver(unit, work, cycle)
            ):
                result.extend(("approve", "reject"))
            if manage:
                result.append("reopen")
        return tuple(result)
