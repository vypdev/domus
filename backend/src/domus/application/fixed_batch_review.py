"""Prepare and atomically replace eligible future fixed obligations."""

from dataclasses import asdict, dataclass, replace
from datetime import timedelta
from functools import partial

from domus.application.commands import AtomicCommands
from domus.application.fixed_materialization import FixedMaintenance, MaintenanceScope
from domus.application.fixed_recurrence import FixedRecurrencePlanner
from domus.application.ports import UnitOfWork
from domus.application.relative_lifecycle import occurrence_work_history
from domus.application.reschedule_review import EffectiveDeadline, effective_deadline, future_until
from domus.application.task_authorization import TaskAccess, TaskCommandAuthorization
from domus.application.task_commands import transition_occurrence
from domus.application.task_requests import TransitionTask
from domus.domain.errors import (
    Conflict,
    IntegrationUnavailable,
    InvalidInput,
    NotFound,
    StorageFailure,
)
from domus.domain.identity import MemberStatus, validate_revision
from domus.domain.inventory import InventoryEffect
from domus.domain.recurrence_planning import FixedBatch, FixedCursor, cursor_binding
from domus.domain.recurrence_records import (
    FixedExceptionKind,
    FixedProgress,
    FixedSchedule,
    ScheduleState,
)
from domus.domain.recurrence_rules import FixedPattern, NominalDate, NominalSlot
from domus.domain.recurrence_time import LocalInstant, NominalTime
from domus.domain.relative_lifecycle import WorkHistory
from domus.domain.storage import (
    CommandKey,
    JsonDocument,
    JsonObject,
    JsonValue,
    validate_identifier,
)
from domus.domain.task_values import DefinitionState, OccurrenceState, validate_task_text
from domus.domain.tasks import TaskDefinition, TaskOccurrence

_SLOT_LIMIT = 100
_PERIOD_LIMIT = 1000


@dataclass(frozen=True, slots=True)
class FixedReplacement:
    schedule_id: str
    schedule_revision: int
    pattern: FixedPattern
    reason: str
    use_household_fold: bool = False

    def __post_init__(self) -> None:
        validate_identifier(self.schedule_id)
        validate_revision(self.schedule_revision)
        if not isinstance(self.pattern, FixedPattern) or type(self.use_household_fold) is not bool:
            raise InvalidInput("invalid_recurrence_pattern")
        validate_task_text(self.reason, 1000, required=True, multiline=True)

    def document(self) -> JsonDocument:
        return JsonDocument.from_value(
            {
                "version": 1,
                "kind": "fixed_replacement",
                **({"use_household_fold": True} if self.use_household_fold else {}),
                "schedule_id": self.schedule_id,
                "schedule_revision": self.schedule_revision,
                "pattern": self.pattern.document().decode(),
                "reason": self.reason,
            }
        )


@dataclass(frozen=True, slots=True)
class AffectedWork:
    work: TaskOccurrence
    key: str
    original: NominalSlot
    deadline: EffectiveDeadline
    previously_replaced: bool = False
    excluded: bool = False

    def value(self) -> JsonObject:
        return {
            "occurrence_id": self.work.occurrence_id,
            "slot_key": self.key,
            "revision": self.work.revision,
            "state": self.work.state.value,
            "assignee_ids": list(self.work.assignee_ids),
            "deadline": self.deadline.document.decode(),
            "previously_replaced": self.previously_replaced,
            "excluded": self.excluded,
        }


@dataclass(frozen=True, slots=True)
class ReplacementSource:
    current: FixedSchedule
    upcoming: FixedSchedule
    progress: FixedProgress
    definition: TaskDefinition
    replaceable: tuple[AffectedWork, ...]
    retained: tuple[AffectedWork, ...]
    effects: tuple[InventoryEffect, ...]

    def prepare(self, planner: FixedRecurrencePlanner, now: int) -> PreparedReplacement:
        rule = self.upcoming
        start = rule.pattern.start
        local = planner.times.local_at(now, rule.policy)
        if (
            not isinstance(local, LocalInstant)
            or local.policy != rule.policy
            or local.instant_ms != now
        ):
            raise IntegrationUnavailable("recurrence_time_source_invalid")
        today = local.local.date() if isinstance(start, NominalDate) else local.local
        if start.local < today:
            raise Conflict("recurrence_reschedule_in_past")
        try:
            before = (
                NominalDate(start.local + timedelta(days=60))
                if isinstance(start, NominalDate)
                else NominalTime(start.local + timedelta(days=60))
            )
        except OverflowError:
            raise Conflict("recurrence_review_too_large") from None
        cutoff_instant = (
            planner.times.resolve(before, rule.policy).instant_ms
            if isinstance(before, NominalTime)
            else None
        )
        blocking = tuple(
            item for item in self.retained if not (item.previously_replaced or item.excluded)
        )
        if any(item.original.local >= before.local for item in (*self.replaceable, *blocking)):
            raise Conflict("recurrence_review_too_large")
        for item in blocking:
            if isinstance(before, NominalDate):
                too_late = (
                    item.deadline.local_date is not None
                    and item.deadline.local_date >= before.local
                )
            else:
                assert cutoff_instant is not None
                too_late = (
                    item.deadline.due_at is not None and item.deadline.due_at >= cutoff_instant
                )
            if too_late:
                raise Conflict("recurrence_review_too_large")
        cursor = FixedCursor(cursor_binding(rule.pattern, rule.policy))
        steps = []
        budget = _PERIOD_LIMIT
        # A fixed rule has at most one nominal time per day, plus its final bounded scan.
        for _ in range(61):
            if budget == 0:
                break
            batch = planner.expand(
                rule.pattern,
                rule.policy,
                before=before,
                cursor=cursor,
                slot_limit=1,
                period_limit=budget,
            )
            steps.append(batch)
            budget -= batch.periods_scanned
            cursor = batch.cursor
            if batch.range_complete:
                break
        if not steps[-1].range_complete:
            raise Conflict("recurrence_review_too_large")
        nominal_slots = tuple(slot for step in steps for slot in step.slots)
        if not nominal_slots or nominal_slots[0].nominal != start:
            raise InvalidInput("recurrence_start_mismatch")
        planned = tuple(slot for slot in nominal_slots if rule.exception(slot.nominal) is None)
        instants = tuple(item.resolved.instant_ms for item in planned if item.resolved is not None)
        dates = {item.nominal for item in planned}
        if len(set(instants)) != len(instants) or any(
            item.original in dates
            or item.deadline.due_at is not None
            and item.deadline.due_at in instants
            or item.deadline.local_date is not None
            and NominalDate(item.deadline.local_date) in dates
            for item in blocking
        ):
            raise Conflict("recurrence_reschedule_collision")
        # Keep a matching date's assignees first, then pair remaining work chronologically.
        matched = {item.original: item for item in self.replaceable if item.original in dates}
        unmatched = iter(item for item in self.replaceable if item.original not in dates)
        pairing = tuple(
            matched[item.nominal] if item.nominal in matched else next(unmatched, None)
            for item in planned
        )
        if any(item.work.assignee_ids for item in unmatched):
            raise Conflict("recurrence_replacement_assignments_need_review")
        boundary = future_until(planner.times, nominal_slots[0], rule.policy)
        # The old first appearance can elapse while the proposed second is still ahead.
        # Fence the original deadlines as well as the proposed start at apply time.
        boundary = min(
            boundary,
            min(
                (
                    item.deadline.due_at
                    for item in self.replaceable
                    if item.deadline.due_at is not None
                ),
                default=boundary,
            ),
        )
        if now >= boundary:
            raise Conflict("recurrence_reschedule_in_past")
        return PreparedReplacement(self, before, tuple(steps), pairing, boundary)


def replacement_source(
    unit: UnitOfWork, scope: MaintenanceScope, request: FixedReplacement
) -> ReplacementSource:
    home = scope.household_id
    rule = unit.recurrence.schedule(home, request.schedule_id)
    if rule is None:
        raise NotFound("recurrence_rule_missing")
    if rule.revision != request.schedule_revision:
        raise Conflict("recurrence_review_stale")
    policy = (
        replace(rule.policy, repeated_time=scope.require(unit).repeated_time)
        if request.use_household_fold
        else rule.policy
    )
    if rule.state is not ScheduleState.ACTIVE or (
        rule.pattern == request.pattern and rule.policy == policy
    ):
        raise Conflict("recurrence_state_change_unavailable")
    start = request.pattern.start
    if type(start) is not type(rule.pattern.start):
        raise Conflict("recurrence_pattern_requires_replacement")
    progress = unit.recurrence.progress(home, rule.schedule_id)
    definition = unit.tasks.definition(home, rule.definition_id)
    if progress is None or definition is None or not progress.matches_schedule(rule):
        raise StorageFailure("invalid_recurrence_source")
    if definition.state is not DefinitionState.ACTIVE:
        raise Conflict("recurrence_state_change_unavailable")
    nominal = start.local.isoformat()
    if unit.recurrence.has_absent_fixed_slot_from(home, rule.schedule_id, nominal):
        raise Conflict("recurrence_review_source_absent")
    slots = unit.recurrence.fixed_slots_from(home, rule.schedule_id, nominal)
    if len(slots) > _SLOT_LIMIT:
        raise Conflict("recurrence_review_too_large")
    replaced, retained = [], []
    for slot in slots:
        work = unit.tasks.occurrence(home, slot.occurrence_id)
        if work is None:
            raise StorageFailure("invalid_recurrence_source")
        deadline = effective_deadline(unit, work, slot)
        cancelled = work.state is OccurrenceState.CANCELLED
        previously_replaced = (
            cancelled
            and slot.schedule.pattern_revision < rule.pattern_revision
            and unit.recurrence.has_replaced_fixed_work(home, rule.schedule_id, work.occurrence_id)
        )
        exception = rule.exception(slot.planned.nominal)
        excluded = (
            cancelled and exception is not None and exception.kind is FixedExceptionKind.EXCLUDE
        )
        item = AffectedWork(
            work, slot.key, slot.planned.nominal, deadline, previously_replaced, excluded
        )
        eligible = (
            not slot.added
            and slot.schedule.pattern_revision == rule.pattern_revision
            and work.state in (OccurrenceState.AVAILABLE, OccurrenceState.ASSIGNED)
            and deadline.document.decode() == slot.planned.value()
            and occurrence_work_history(unit, work) is WorkHistory.UNSTARTED
        )
        if eligible:
            if (
                work.definition_snapshot != definition
                or work.prerequisite_ids
                or work.required_subtask_ids
                or unit.tasks.has_current_dependents(home, work.occurrence_id)
                or any(
                    (member := unit.members.get(home, subject)) is None
                    or member.status is not MemberStatus.ACTIVE
                    for subject in work.assignee_ids
                )
            ):
                raise Conflict("recurrence_replacement_assignments_need_review")
            replaced.append(item)
        else:
            retained.append(item)
    if not replaced:
        raise Conflict("recurrence_state_change_unavailable")
    # Moves from earlier dates stay visible and must also participate in collision review.
    old_open = unit.tasks.occurrences(
        home, definition_id=rule.definition_id, open_only=True, limit=101
    )
    if len(old_open) > _SLOT_LIMIT:
        raise Conflict("recurrence_review_too_large")
    for work in old_open:
        earlier = unit.recurrence.fixed_slot_for_occurrence(home, work.occurrence_id)
        if (
            earlier is not None
            and earlier.schedule.schedule_id == rule.schedule_id
            and earlier.planned.nominal.local < start.local
        ):
            retained.append(
                AffectedWork(
                    work,
                    earlier.key,
                    earlier.planned.nominal,
                    effective_deadline(unit, work, earlier),
                )
            )
    upcoming = replace(
        rule,
        pattern=request.pattern,
        policy=policy,
        revision=rule.revision + 1,
        pattern_revision=rule.pattern_revision + 1,
    )
    effects = unit.inventory.effects(home, tuple(item.work.occurrence_id for item in replaced))
    return ReplacementSource(
        rule, upcoming, progress, definition, tuple(replaced), tuple(retained), effects
    )


@dataclass(frozen=True, slots=True)
class PreparedReplacement:
    source: ReplacementSource
    before: NominalSlot
    steps: tuple[FixedBatch, ...]
    pairing: tuple[AffectedWork | None, ...]
    future_until: int

    def document(self) -> JsonDocument:
        rule = self.source
        try:
            return JsonDocument.from_value(
                {
                    "previous_progress_revision": rule.progress.revision,
                    **(
                        {"repeated_time": rule.upcoming.policy.repeated_time.value}
                        if rule.current.policy != rule.upcoming.policy
                        else {}
                    ),
                    "definition_revision": rule.definition.revision,
                    "before": self.before.local.isoformat(),
                    "retained_work": [item.value() for item in rule.retained],
                    "cancelled_work": [item.value() for item in rule.replaceable],
                    **(
                        {
                            "inventory_effects": [
                                {
                                    **asdict(effect),
                                    "kind": effect.kind.value,
                                    "remaining": str(effect.remaining),
                                }
                                for effect in rule.effects
                            ]
                        }
                        if rule.effects
                        else {}
                    ),
                    "prospective_slots": [
                        {
                            "planned": planned.value(),
                            "replaces": None if old is None else old.work.occurrence_id,
                        }
                        for planned, old in zip(
                            (
                                slot
                                for step in self.steps
                                for slot in step.slots
                                if rule.upcoming.exception(slot.nominal) is None
                            ),
                            self.pairing,
                            strict=True,
                        )
                    ],
                }
            )
        except InvalidInput:
            raise Conflict("recurrence_review_too_large") from None

    def commit(
        self,
        unit: UnitOfWork,
        materializer: FixedMaintenance,
        commands: AtomicCommands,
        command: CommandKey,
        access: TaskAccess,
        request: FixedReplacement,
    ) -> JsonObject:
        old, rule = self.source.current, self.source.upcoming
        home = rule.household_id
        unit.recurrence.save_schedule(rule, old.revision)
        progress = self.source.progress
        unit.recurrence.save_progress(
            FixedProgress(
                rule.schedule_id,
                home,
                rule.pattern_revision,
                FixedCursor(cursor_binding(rule.pattern, rule.policy)),
                progress.revision + 1,
            ),
            progress.revision,
        )
        replacements: dict[str, str] = {}
        additions: list[JsonValue] = []
        originals = iter(self.pairing)
        for batch in self.steps:
            expects_work = bool(batch.slots) and rule.exception(batch.slots[0].nominal) is None
            prior = next(originals) if expects_work else None
            step = materializer.commit_reviewed_step(
                unit, rule, batch, self.before, assignees=prior.work.assignee_ids if prior else ()
            )
            if expects_work and step.occurrence_id is None:
                raise Conflict("recurrence_review_stale")
            if step.occurrence_id is not None:
                if prior is None:
                    additions.append(step.occurrence_id)
                else:
                    replacements[prior.work.occurrence_id] = step.occurrence_id
        for affected in self.source.replaceable:
            work = affected.work
            transition = TransitionTask(
                work.occurrence_id, work.revision, OccurrenceState.CANCELLED, request.reason
            )
            key = JsonDocument.from_value(
                {"review_key": command.key, "occurrence_id": work.occurrence_id}
            ).fingerprint
            transition_key = CommandKey(home, command.actor_id, "task.transition", key)
            authority = TaskCommandAuthorization(
                access,
                home,
                transition_key.action,
                work.occurrence_id,
                transition_target=transition.target,
            )
            replace(commands, authorization=authority).in_unit(
                unit,
                transition_key,
                transition.document(),
                partial(transition_occurrence, household_id=home, request=transition),
            )
        moved, retained = self._transfer_effects(unit, replacements)
        return {
            "kind": "fixed_replacement",
            "schedule_id": rule.schedule_id,
            "schedule_revision": rule.revision,
            "pattern_revision": rule.pattern_revision,
            "replacements": dict[str, JsonValue](replacements),
            "cancelled": [item.work.occurrence_id for item in self.source.replaceable],
            "added": additions,
            **(
                {"inventory_transferred": moved, "inventory_retained": retained}
                if moved or retained
                else {}
            ),
        }

    def _transfer_effects(
        self, unit: UnitOfWork, replacements: dict[str, str]
    ) -> tuple[list[JsonValue], list[JsonValue]]:
        # New occurrences are materialized from this exact reviewed definition.
        materials = {
            (line.line_id, line.binding.reference_id) for line in self.source.definition.materials
        }
        moved: list[JsonValue] = []
        retained: list[JsonValue] = []
        for effect in self.source.effects:
            assert effect.occurrence_id is not None
            replacement = replacements.get(effect.occurrence_id)
            if replacement is None or (effect.line_id, effect.reference_id) not in materials:
                retained.append(effect.effect_id)
                continue
            unit.inventory.update_effect(
                replace(effect, occurrence_id=replacement, revision=effect.revision + 1),
                effect.revision,
            )
            moved.append({"id": effect.effect_id, "from": effect.occurrence_id, "to": replacement})
        return moved, retained
