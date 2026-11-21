"""Deliberate daily enablement, revocation and adoption preserve rule-owned authority."""

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import timedelta
from typing import cast

from domus.application.automation_preview import owned_product, require_configuration
from domus.application.automation_scheduled_documents import planned_document
from domus.application.automation_scheduled_planning import DailyAutomationPlanner
from domus.application.commands import AtomicCommands, Change
from domus.application.fixed_materialization import MaintenanceScope
from domus.application.identity_ports import CurrentHuman
from domus.application.ports import Clock, Identifiers, Transactions, UnitOfWork
from domus.application.task_authorization import TaskAccess
from domus.domain.automation import AutomationControl, AutomationDraft, DailyTrigger
from domus.domain.automation_scheduling import DailyAutomationSchedule, RuleExecutionGrant
from domus.domain.errors import (
    Conflict,
    Forbidden,
    IntegrationUnavailable,
    InvalidInput,
    NotFound,
    StorageFailure,
)
from domus.domain.identity import HumanIdentity, Member, Permission, validate_revision
from domus.domain.recurrence_time import ResolvedTime, TimePolicy
from domus.domain.storage import CommandKey, JsonDocument, Receipt, validate_identifier

ENABLE_DAILY_AUTOMATION = "automation.daily.enable"
DISABLE_DAILY_AUTOMATION = "automation.daily.disable"
ADOPT_DAILY_POLICY = "automation.daily.adopt"
_ACTIONS = (ENABLE_DAILY_AUTOMATION, DISABLE_DAILY_AUTOMATION, ADOPT_DAILY_POLICY)


def _same_timing(left: TimePolicy, right: TimePolicy) -> bool:
    return (left.zone, left.data_identity, left.repeated_time) == (
        right.zone,
        right.data_identity,
        right.repeated_time,
    )


def _expected(value: int) -> None:
    if type(value) is not int or value < 0:
        raise InvalidInput("invalid_daily_automation_control")
    if value != 0:
        validate_revision(value)


@dataclass(frozen=True, slots=True)
class DailyControlRequest:
    rule_id: str
    rule_revision: int
    expected_control_revision: int
    expected_schedule_revision: int

    def __post_init__(self) -> None:
        validate_identifier(self.rule_id)
        validate_revision(self.rule_revision)
        _expected(self.expected_control_revision)
        _expected(self.expected_schedule_revision)

    def document(self) -> JsonDocument:
        return JsonDocument.from_value(
            {
                "rule_id": self.rule_id,
                "rule_revision": self.rule_revision,
                "expected_control_revision": self.expected_control_revision,
                "expected_schedule_revision": self.expected_schedule_revision,
            }
        )


@dataclass(frozen=True, slots=True)
class ReviewedDailyRequest(DailyControlRequest):
    reviewed: ResolvedTime

    def __post_init__(self) -> None:
        super(ReviewedDailyRequest, self).__post_init__()
        if not isinstance(self.reviewed, ResolvedTime):
            raise InvalidInput("invalid_daily_automation_review")

    def document(self) -> JsonDocument:
        return JsonDocument.from_value(
            {
                **super(ReviewedDailyRequest, self).document().decode(),
                "reviewed": planned_document(self.reviewed).decode(),
            }
        )


@dataclass(frozen=True, slots=True)
class DailyAutomationReview:
    draft: AutomationDraft
    control: AutomationControl | None
    schedule: DailyAutomationSchedule | None
    proposed_policy: TimePolicy
    proposed_times: tuple[ResolvedTime, ...]
    proposed_error: str | None
    approved_times: tuple[ResolvedTime, ...] | None
    approved_error: str | None
    active_draft: AutomationDraft | None
    may_grant_tasks: bool

    @property
    def policy_changed(self) -> bool:
        return self.schedule is not None and not _same_timing(
            self.schedule.policy, self.proposed_policy
        )


@dataclass(frozen=True, slots=True)
class _ControlAuthority:
    human: HumanIdentity
    scope: MaintenanceScope
    command: CommandKey

    def owner(self, unit: UnitOfWork) -> Member:
        home = self.scope.require(unit).household_id
        member = require_configuration(unit, home, self.human)
        if self.command.action == ENABLE_DAILY_AUTOMATION:
            TaskAccess(self.human).require(unit, home, Permission.TASKS_CREATE)
        return member

    def require(self, command: CommandKey, unit: UnitOfWork) -> None:
        if command != self.command or command.action not in _ACTIONS:
            raise Forbidden("permission_denied")
        member = self.owner(unit)
        original = unit.receipts.get(command)
        if original is not None and original.result.decode().get("member_id") != member.member_id:
            raise Forbidden("permission_denied")


@dataclass(frozen=True, slots=True)
class DailyAutomationControl:
    transactions: Transactions
    scope: MaintenanceScope
    actor: CurrentHuman
    read_actor: Callable[[], HumanIdentity]
    clock: Clock
    identifiers: Identifiers
    planner: DailyAutomationPlanner

    def _authority(self, human: HumanIdentity, action: str, key: str) -> _ControlAuthority:
        return _ControlAuthority(
            human, self.scope, CommandKey(self.scope.household_id, human.ha_user_id, action, key)
        )

    def _draft(self, unit: UnitOfWork, rule_id: str, revision: int) -> AutomationDraft:
        draft = unit.automation_drafts.revision(self.scope.household_id, rule_id, revision)
        if draft is None:
            raise NotFound("automation_draft_missing")
        if not isinstance(draft.rule.trigger, DailyTrigger):
            raise InvalidInput("automation_requires_daily_trigger")
        return draft

    def _policy(self, unit: UnitOfWork) -> TimePolicy:
        home = self.scope.require(unit)
        return TimePolicy(
            home.time_zone, self.planner.times.data_identity, home.repeated_time, home.revision
        )

    def review(self, rule_id: str, rule_revision: int) -> DailyAutomationReview:
        validate_revision(rule_revision)
        return cast(DailyAutomationReview, self._review(rule_id, rule_revision))

    def active_review(self, rule_id: str) -> DailyAutomationReview | None:
        """Discover the active daily revision without granting manual execution authority."""
        return self._review(rule_id, None)

    def _review(self, rule_id: str, rule_revision: int | None) -> DailyAutomationReview | None:
        validate_identifier(rule_id)
        authority = self._authority(self.read_actor(), DISABLE_DAILY_AUTOMATION, "review")
        with self.transactions.read() as unit:
            authority.owner(unit)
            draft = None if rule_revision is None else self._draft(unit, rule_id, rule_revision)
            control = unit.automation_controls.get(self.scope.household_id, rule_id)
            schedule = unit.scheduled_automations.schedule(self.scope.household_id, rule_id)
            active_draft = (
                None
                if control is None
                else unit.automation_drafts.revision(
                    self.scope.household_id, rule_id, control.rule_revision
                )
            )
            if control is not None and active_draft is None:
                raise StorageFailure("invalid_daily_automation_source")
            if rule_revision is None:
                if unit.automation_drafts.latest(self.scope.household_id, rule_id) is None:
                    raise NotFound("automation_draft_missing")
                if control is None or not control.enabled:
                    return None
                current = cast(AutomationDraft, active_draft)
                if not isinstance(current.rule.trigger, DailyTrigger):
                    return None
                draft = current
            selected = cast(AutomationDraft, draft)
            try:
                TaskAccess(authority.human).require(
                    unit, self.scope.household_id, Permission.TASKS_CREATE
                )
            except Forbidden:
                may_grant_tasks = False
            else:
                may_grant_tasks = True
            policy = self._policy(unit)
            after = max(self.clock.now(), 0 if schedule is None else schedule.startup_cutoff_ms)
            frontier = (
                schedule.last_nominal
                if schedule is not None and schedule.grant.draft == selected
                else None
            )
            proposed_error = None
            try:
                proposed = self.planner.upcoming(
                    cast(DailyTrigger, selected.rule.trigger).time,
                    policy,
                    after,
                    after_date=frontier,
                )
            except (IntegrationUnavailable, InvalidInput) as failure:
                proposed = ()
                proposed_error = failure.code
            approved = None
            error = None
            if schedule is not None:
                trigger = cast(DailyTrigger, schedule.grant.draft.rule.trigger)
                try:
                    self.planner.require_approved(schedule.next_time)
                    approved = self.planner.upcoming(
                        trigger.time, schedule.policy, after, after_date=schedule.last_nominal
                    )
                except (IntegrationUnavailable, InvalidInput) as failure:
                    error = failure.code
            return DailyAutomationReview(
                selected,
                control,
                schedule,
                policy,
                proposed,
                proposed_error,
                approved,
                error,
                active_draft,
                may_grant_tasks,
            )

    def _current(
        self, unit: UnitOfWork, request: DailyControlRequest
    ) -> tuple[AutomationControl | None, DailyAutomationSchedule | None]:
        home = self.scope.household_id
        control = unit.automation_controls.get(home, request.rule_id)
        schedule = unit.scheduled_automations.schedule(home, request.rule_id)
        if request.expected_control_revision != (
            0 if control is None else control.control_revision
        ) or request.expected_schedule_revision != (0 if schedule is None else schedule.revision):
            raise Conflict("revision_conflict")
        return control, schedule

    def _reviewed(
        self,
        unit: UnitOfWork,
        request: ReviewedDailyRequest,
        draft: AutomationDraft,
        previous: DailyAutomationSchedule | None,
    ) -> tuple[ResolvedTime, int]:
        after = max(self.clock.now(), 0 if previous is None else previous.startup_cutoff_ms)
        frontier = (
            previous.last_nominal
            if previous is not None and previous.grant.draft == draft
            else None
        )
        first = self.planner.next(
            cast(DailyTrigger, draft.rule.trigger).time,
            self._policy(unit),
            after,
            after_date=frontier,
        )
        if request.reviewed != first:
            raise Conflict("automation_timing_review_changed")
        return first, after

    def _result(
        self,
        unit: UnitOfWork,
        authority: _ControlAuthority,
        control: AutomationControl,
        schedule: DailyAutomationSchedule,
    ) -> Change:
        result = JsonDocument.from_value(
            {
                "rule_id": control.rule_id,
                "rule_revision": str(control.rule_revision),
                "control_revision": str(control.control_revision),
                "enabled": control.enabled,
                "schedule_revision": str(schedule.revision),
                "grant_id": schedule.grant.grant_id,
                "approved_next": planned_document(schedule.next_time).decode(),
            }
        )
        outcome = JsonDocument.from_value(
            {**result.decode(), "member_id": authority.owner(unit).member_id}
        )
        return Change(outcome, result, result, requires_delivery=False)

    def enable(self, key: str, request: ReviewedDailyRequest) -> Receipt:
        authority = self._authority(self.actor.current(), ENABLE_DAILY_AUTOMATION, key)

        def apply(unit: UnitOfWork) -> Change:
            current, previous = self._current(unit, request)
            draft = self._draft(unit, request.rule_id, request.rule_revision)
            for product_id in draft.rule.stock_products():
                owned_product(unit, self.scope.household_id, product_id)
            first, after = self._reviewed(unit, request, draft, previous)
            revision = 1 if current is None else current.control_revision + 1
            grant = RuleExecutionGrant(
                self.scope.installation, self.scope.household_id, self.identifiers.new(), draft
            )
            schedule = DailyAutomationSchedule(
                grant,
                revision,
                first.policy,
                first,
                after,
                last_nominal=first.nominal.local.date() - timedelta(days=1),
                revision=1 if previous is None else previous.revision + 1,
            )
            control = AutomationControl(request.rule_id, request.rule_revision, revision, True)
            unit.scheduled_automations.cancel_pending(
                self.scope.household_id, request.rule_id, self.clock.now()
            )
            unit.automation_controls.save(
                self.scope.household_id, control, request.expected_control_revision
            )
            unit.scheduled_automations.save_schedule(schedule, request.expected_schedule_revision)
            return self._result(unit, authority, control, schedule)

        return AtomicCommands(self.transactions, authority, self.clock, self.identifiers).execute(
            authority.command, request.document(), apply
        )

    def _active(
        self, unit: UnitOfWork, request: DailyControlRequest
    ) -> tuple[AutomationControl, DailyAutomationSchedule]:
        control, schedule = self._current(unit, request)
        if control is None or schedule is None or not control.enabled:
            raise Conflict("automation_disabled")
        if (
            control.rule_revision != request.rule_revision
            or schedule.grant.draft.revision != request.rule_revision
        ):
            raise Conflict("revision_conflict")
        return control, schedule

    def disable(self, key: str, request: DailyControlRequest) -> Receipt:
        authority = self._authority(self.actor.current(), DISABLE_DAILY_AUTOMATION, key)

        def apply(unit: UnitOfWork) -> Change:
            previous, schedule = self._active(unit, request)
            control = replace(
                previous, control_revision=previous.control_revision + 1, enabled=False
            )
            updated = replace(
                schedule, control_revision=control.control_revision, revision=schedule.revision + 1
            )
            unit.scheduled_automations.cancel_pending(
                self.scope.household_id, request.rule_id, self.clock.now()
            )
            unit.automation_controls.save(
                self.scope.household_id, control, previous.control_revision
            )
            unit.scheduled_automations.save_schedule(updated, schedule.revision)
            return self._result(unit, authority, control, updated)

        return AtomicCommands(self.transactions, authority, self.clock, self.identifiers).execute(
            authority.command, request.document(), apply
        )

    def adopt(self, key: str, request: ReviewedDailyRequest) -> Receipt:
        authority = self._authority(self.actor.current(), ADOPT_DAILY_POLICY, key)

        def apply(unit: UnitOfWork) -> Change:
            previous, schedule = self._active(unit, request)
            first, after = self._reviewed(unit, request, schedule.grant.draft, schedule)
            if _same_timing(first.policy, schedule.policy):
                raise Conflict("automation_timing_unchanged")
            control = replace(previous, control_revision=previous.control_revision + 1)
            updated = replace(
                schedule,
                control_revision=control.control_revision,
                revision=schedule.revision + 1,
                policy=first.policy,
                next_time=first,
                startup_cutoff_ms=after,
                last_nominal=first.nominal.local.date() - timedelta(days=1),
            )
            unit.automation_controls.save(
                self.scope.household_id, control, previous.control_revision
            )
            unit.scheduled_automations.save_schedule(updated, schedule.revision)
            return self._result(unit, authority, control, updated)

        return AtomicCommands(self.transactions, authority, self.clock, self.identifiers).execute(
            authority.command, request.document(), apply
        )

    def original(self, action: str, key: str) -> Receipt:
        if action not in _ACTIONS:
            raise InvalidInput("invalid_automation_action")
        authority = self._authority(self.read_actor(), action, key)
        with self.transactions.read() as unit:
            authority.require(authority.command, unit)
            receipt = unit.receipts.get(authority.command)
            if receipt is None:
                raise NotFound("operation_missing")
            return receipt
