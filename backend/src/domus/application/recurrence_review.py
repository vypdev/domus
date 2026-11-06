"""Review an exact manual occurrence before binding it to a relative initial slot."""

import re
from collections.abc import Callable
from dataclasses import asdict, dataclass
from enum import StrEnum

from domus.application.commands import AtomicCommands, Change
from domus.application.fixed_materialization import MaintenanceScope
from domus.application.identity_ports import CurrentHuman
from domus.application.ports import Clock, Identifiers, Transactions, UnitOfWork
from domus.application.relative_lifecycle import occurrence_work_history
from domus.application.relative_materialization import RelativeSource, adopt_initial, initial_source
from domus.application.task_authorization import TaskAccess, TaskActor
from domus.domain.errors import Conflict, Forbidden, InvalidInput, NotFound
from domus.domain.identity import HumanIdentity, Permission, validate_revision
from domus.domain.recurrence_records import ScheduleState
from domus.domain.relative_lifecycle import WorkHistory
from domus.domain.relative_recurrence import RelativeSlot
from domus.domain.storage import (
    CommandKey,
    Installation,
    JsonDocument,
    Receipt,
    validate_identifier,
)
from domus.domain.task_values import DefinitionState, OccurrenceState
from domus.domain.tasks import TaskOccurrence

_REVIEW_TTL_MS = 300_000


class ReviewAction(StrEnum):
    PREVIEW = "recurrence.review.preview"
    APPLY = "recurrence.review.apply"


@dataclass(frozen=True, slots=True)
class ManualAdoption:
    schedule_id: str
    schedule_revision: int
    occurrence_id: str
    occurrence_revision: int

    def __post_init__(self) -> None:
        validate_identifier(self.schedule_id)
        validate_identifier(self.occurrence_id)
        validate_revision(self.schedule_revision)
        validate_revision(self.occurrence_revision)

    def document(self) -> JsonDocument:
        return JsonDocument.from_value({"version": 1, "kind": "adopt_manual", **asdict(self)})


@dataclass(frozen=True, slots=True)
class ReviewedAdoption:
    selection: ManualAdoption
    preview_key: str
    plan_fingerprint: str

    def __post_init__(self) -> None:
        validate_identifier(self.preview_key)
        if not isinstance(self.plan_fingerprint, str) or not re.fullmatch(
            r"[0-9a-f]{64}", self.plan_fingerprint
        ):
            raise InvalidInput("invalid_recurrence_review")

    def document(self) -> JsonDocument:
        return JsonDocument.from_value(
            {
                **self.selection.document().decode(),
                "preview_key": self.preview_key,
                "plan_fingerprint": self.plan_fingerprint,
            }
        )


@dataclass(frozen=True, slots=True)
class _ReviewAuthority:
    scope: MaintenanceScope
    access: TaskAccess
    command: CommandKey

    def current(self, unit: UnitOfWork) -> TaskActor:
        self.scope.require(unit)
        return self.access.require(unit, self.scope.household_id, Permission.TASKS_MANAGE)

    def require(self, command: CommandKey, unit: UnitOfWork) -> None:
        if command != self.command:
            raise Forbidden("permission_denied")
        self.current(unit)


@dataclass(frozen=True, slots=True)
class _AdoptionPlan:
    source: RelativeSource
    work: TaskOccurrence
    slot: RelativeSlot
    document: JsonDocument


@dataclass(frozen=True, slots=True)
class RecurrenceReview:
    transactions: Transactions
    installation: Installation
    actor: CurrentHuman
    read_actor: Callable[[], HumanIdentity]
    clock: Clock
    identifiers: Identifiers
    household_id: str = "home"

    def _authority(self, human: HumanIdentity, action: ReviewAction, key: str) -> _ReviewAuthority:
        scope = MaintenanceScope(self.installation, self.household_id)
        command = CommandKey(self.household_id, human.ha_user_id, action.value, key)
        return _ReviewAuthority(scope, TaskAccess(human), command)

    def _plan(
        self,
        unit: UnitOfWork,
        scope: MaintenanceScope,
        actor: TaskActor,
        selection: ManualAdoption,
    ) -> _AdoptionPlan:
        source = initial_source(unit, scope, selection.schedule_id)
        rule, progress, definition = source.schedule, source.progress, source.definition
        work = unit.tasks.occurrence(rule.household_id, selection.occurrence_id)
        if (
            rule.revision != selection.schedule_revision
            or work is None
            or work.revision != selection.occurrence_revision
        ):
            raise Conflict("recurrence_review_stale")
        due_at = None if rule.initial.resolved is None else rule.initial.resolved.instant_ms
        if (
            rule.state is not ScheduleState.ACTIVE
            or definition.state is not DefinitionState.ACTIVE
            or not progress.pristine
            or work.definition_snapshot != definition
            or work.due_at != due_at
            or work.created_at < rule.created_at
            or work.state not in (OccurrenceState.AVAILABLE, OccurrenceState.ASSIGNED)
            or unit.recurrence.relative_slot_for_occurrence(rule.household_id, work.occurrence_id)
            is not None
            or occurrence_work_history(unit, work) is not WorkHistory.UNSTARTED
        ):
            raise Conflict("recurrence_adoption_incompatible")
        slot = RelativeSlot(
            scope.installation, rule, rule.initial, work.occurrence_id, work.created_at
        )
        if unit.receipts.get(slot.command) is not None:
            raise Conflict("recurrence_initial_already_consumed")
        return _AdoptionPlan(
            source,
            work,
            slot,
            JsonDocument.from_value(
                {
                    "request": selection.document().decode(),
                    "installation": asdict(scope.installation),
                    "household_id": scope.household_id,
                    "member_id": actor.member.member_id,
                    "member_revision": actor.member.revision,
                    "policy_revision": actor.identity_policy_revision,
                    "role": actor.role.value,
                    "definition_id": definition.definition_id,
                    "definition_revision": definition.revision,
                    "progress_revision": progress.revision,
                    "generation": rule.binding,
                    "initial": rule.initial.value(),
                    "retained_occurrence_id": work.occurrence_id,
                    "due_at": work.due_at,
                }
            ),
        )

    @staticmethod
    def _change(action: ReviewAction, payload: JsonDocument, result: JsonDocument) -> Change:
        return Change(
            result,
            JsonDocument.from_value({"request": payload.decode(), "result": result.decode()}),
            JsonDocument.from_value({"version": 1, "kind": action.value}),
        )

    def preview(self, key: str, selection: ManualAdoption) -> Receipt:
        action = ReviewAction.PREVIEW
        authority = self._authority(self.actor.current(), action, key)
        commands = AtomicCommands(self.transactions, authority, self.clock, self.identifiers)
        payload = selection.document()

        def apply(unit: UnitOfWork) -> Change:
            plan = self._plan(unit, authority.scope, authority.current(unit), selection)
            result = JsonDocument.from_value(
                {
                    "plan": plan.document.decode(),
                    "plan_fingerprint": plan.document.fingerprint,
                    "expires_at": self.clock.now() + _REVIEW_TTL_MS,
                }
            )
            return self._change(action, payload, result)

        return commands.execute(authority.command, payload, apply)

    def apply(self, key: str, request: ReviewedAdoption) -> Receipt:
        action = ReviewAction.APPLY
        authority = self._authority(self.actor.current(), action, key)
        commands = AtomicCommands(self.transactions, authority, self.clock, self.identifiers)
        payload = request.document()

        def apply(unit: UnitOfWork) -> Change:
            preview_key = CommandKey(
                self.household_id,
                authority.command.actor_id,
                ReviewAction.PREVIEW.value,
                request.preview_key,
            )
            preview = unit.receipts.get(preview_key)
            if (
                preview is None
                or preview.historical
                or preview.payload_fingerprint != request.selection.document().fingerprint
            ):
                raise Conflict("recurrence_review_stale")
            saved = preview.result.decode()
            expires = saved.get("expires_at")
            if (
                saved.get("plan_fingerprint") != request.plan_fingerprint
                or type(expires) is not int
                or not preview.created_at <= self.clock.now() < expires
            ):
                raise Conflict("recurrence_review_stale")
            plan = self._plan(unit, authority.scope, authority.current(unit), request.selection)
            if (
                plan.document.fingerprint != request.plan_fingerprint
                or plan.document.decode() != saved.get("plan")
            ):
                raise Conflict("recurrence_review_stale")
            effect = adopt_initial(unit, commands, authority.scope, plan.source, plan.slot)
            result = JsonDocument.from_value(
                {
                    "version": 1,
                    "kind": "adopt_manual",
                    "schedule_id": plan.source.schedule.schedule_id,
                    "occurrence_id": plan.work.occurrence_id,
                    "occurrence_revision": plan.work.revision,
                    "materialization_operation_id": effect.operation_id,
                    "plan_fingerprint": request.plan_fingerprint,
                }
            )
            return self._change(action, payload, result)

        return commands.execute(authority.command, payload, apply)

    def original(self, action: ReviewAction, key: str) -> Receipt:
        if not isinstance(action, ReviewAction):
            raise InvalidInput("invalid_recurrence_review_action")
        authority = self._authority(self.read_actor(), action, key)
        with self.transactions.read() as unit:
            authority.require(authority.command, unit)
            receipt = unit.receipts.get(authority.command)
            if receipt is None:
                raise NotFound("operation_missing")
            return receipt
