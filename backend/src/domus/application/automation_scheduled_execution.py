"""Durable daily admission and one atomic task effect share the existing command engine."""

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import timedelta
from typing import cast

from domus.application.automation_preview import evaluate_scheduled_rule
from domus.application.automation_scheduled_authority import (
    ADMIT_SCHEDULED_AUTOMATION,
    RUN_SCHEDULED_AUTOMATION,
    ScheduledRuleAuthority,
)
from domus.application.automation_scheduled_cancellation import ScheduledCancellations
from domus.application.automation_scheduled_documents import (
    matching_run,
    run_document,
    scheduled_payload,
)
from domus.application.automation_scheduled_planning import DailyAutomationPlanner
from domus.application.commands import AtomicCommands, Change
from domus.application.fixed_materialization import MaintenanceScope
from domus.application.ports import Clock, Identifiers, Transactions, UnitOfWork
from domus.application.task_creation_command import TaskCreationCommand
from domus.application.task_requests import CreateTask
from domus.domain.automation import DailyTrigger
from domus.domain.automation_scheduling import (
    DailyAutomationSchedule,
    DailySuppression,
    ScheduledAutomationRun,
    ScheduledOutcome,
)
from domus.domain.errors import Forbidden, InvalidInput, NotFound, StorageFailure
from domus.domain.recurrence_time import MAX_INSTANT_MS
from domus.domain.storage import CommandKey, JsonDocument, JsonValue, Receipt, validate_identifier


@dataclass(frozen=True, slots=True)
class ScheduledAutomationStep:
    status: str
    rule_id: str
    trigger_key: str | None = None
    receipt: Receipt | None = None


@dataclass(frozen=True, slots=True)
class ScheduledAutomationExecution:
    transactions: Transactions
    scope: MaintenanceScope
    clock: Clock
    identifiers: Identifiers
    planner: DailyAutomationPlanner
    startup_ms: int

    def __post_init__(self) -> None:
        if type(self.startup_ms) is not int or not 0 <= self.startup_ms <= MAX_INSTANT_MS:
            raise InvalidInput("invalid_daily_automation_startup")

    def _command(self, run: ScheduledAutomationRun, action: str) -> CommandKey:
        return CommandKey(self.scope.household_id, run.grant.principal, action, run.key)

    def _require_schedule(self, unit: UnitOfWork, rule_id: str) -> DailyAutomationSchedule:
        home = self.scope.require(unit).household_id
        schedule = unit.scheduled_automations.schedule(home, rule_id)
        if schedule is None:
            raise NotFound("daily_automation_schedule_missing")
        control = unit.automation_controls.get(home, rule_id)
        if not schedule.grant.permits(
            self.scope.installation, home, control, schedule.grant.grant_id
        ):
            raise Forbidden("daily_automation_grant_denied")
        if (
            unit.automation_drafts.revision(home, rule_id, schedule.grant.draft.revision)
            != schedule.grant.draft
        ):
            raise StorageFailure("invalid_daily_automation_source")
        self.planner.require_approved(schedule.next_time)
        return schedule

    def _startup(
        self, unit: UnitOfWork, schedule: DailyAutomationSchedule
    ) -> DailyAutomationSchedule:
        if self.startup_ms <= schedule.startup_cutoff_ms:
            return schedule
        next_time = schedule.next_time
        suppression = schedule.suppression
        frontier = schedule.last_nominal
        if next_time.instant_ms <= self.startup_ms:
            trigger = cast(DailyTrigger, schedule.grant.draft.rule.trigger)
            next_time = self.planner.next(
                trigger.time, schedule.policy, self.startup_ms, after_date=schedule.last_nominal
            )
            suppression = DailySuppression(schedule.next_time, self.startup_ms)
            frontier = next_time.nominal.local.date() - timedelta(days=1)
        updated = replace(
            schedule,
            next_time=next_time,
            startup_cutoff_ms=self.startup_ms,
            suppression=suppression,
            last_nominal=frontier,
            revision=schedule.revision + 1,
        )
        unit.scheduled_automations.save_schedule(updated, schedule.revision)
        return updated

    def _advance(self, unit: UnitOfWork, schedule: DailyAutomationSchedule) -> None:
        trigger = cast(DailyTrigger, schedule.grant.draft.rule.trigger)
        nominal = schedule.next_time.nominal.local.date()
        following = self.planner.next(
            trigger.time, schedule.policy, schedule.next_time.instant_ms, after_date=nominal
        )
        unit.scheduled_automations.save_schedule(
            replace(
                schedule,
                next_time=following,
                last_nominal=following.nominal.local.date() - timedelta(days=1),
                revision=schedule.revision + 1,
            ),
            schedule.revision,
        )

    def _payload(self, run: ScheduledAutomationRun) -> JsonDocument:
        # Policy and grant changes cannot give one immutable rule/date a second
        # identity. The original receipt retains its complete admitted snapshot.
        return scheduled_payload(run)

    def _outcome(
        self, receipt: Receipt, expected: ScheduledAutomationRun
    ) -> ScheduledAutomationRun:
        return matching_run(receipt, expected)

    def admit(
        self, rule_id: str, *, should_continue: Callable[[], bool] = lambda: True
    ) -> ScheduledAutomationStep:
        validate_identifier(rule_id)
        if not should_continue():
            return ScheduledAutomationStep("stopped", rule_id)
        with self.transactions.write() as unit:
            schedule = self._require_schedule(unit, rule_id)
            if not should_continue():
                return ScheduledAutomationStep("stopped", rule_id)
            schedule = self._startup(unit, schedule)
            if schedule.next_time.instant_ms > self.clock.now():
                return ScheduledAutomationStep("future", rule_id)
            home = self.scope.household_id
            if (
                unit.scheduled_automations.pending_count(home, rule_id=rule_id, limit=100) >= 100
                or unit.scheduled_automations.pending_count(home, limit=1000) >= 1000
            ):
                return ScheduledAutomationStep("queue_full", rule_id)
            run = ScheduledAutomationRun(
                schedule.grant, schedule.control_revision, schedule.next_time, self.clock.now()
            )
            command = self._command(run, ADMIT_SCHEDULED_AUTOMATION)
            authority = ScheduledRuleAuthority(self.scope, run, command)
            authority.require(command, unit)
            existing = unit.scheduled_automations.run(home, run.key)
            original = unit.receipts.get(self._command(run, RUN_SCHEDULED_AUTOMATION))
            admitted = unit.receipts.get(command)
            if existing is not None or original is not None or admitted is not None:
                if existing is None:
                    proof = cast(Receipt, original if original is not None else admitted)
                    retained = self._outcome(proof, run)
                    queued = replace(
                        retained,
                        outcome=ScheduledOutcome.QUEUED,
                        finished_at=None,
                        task_operation_id=None,
                        task_occurrence_id=None,
                    )
                    unit.scheduled_automations.admit(queued)
                    if retained.outcome is ScheduledOutcome.QUEUED:
                        ScheduledCancellations(
                            self.transactions, self.scope, self.clock, self.identifiers
                        ).one(unit, queued)
                    else:
                        unit.scheduled_automations.finish(retained)
                self._advance(unit, schedule)
                return ScheduledAutomationStep("retained", rule_id, run.key, original or admitted)

            def apply(target: UnitOfWork) -> Change:
                target.scheduled_automations.admit(run)
                self._advance(target, schedule)
                fact = JsonDocument.from_value(
                    {"trigger_key": run.key, "run": run_document(run).decode()}
                )
                return Change(fact, fact, fact, requires_delivery=False)

            receipt = AtomicCommands(
                self.transactions, authority, self.clock, self.identifiers
            ).in_unit(unit, command, self._payload(run), apply)
            return ScheduledAutomationStep("admitted", rule_id, run.key, receipt)

    def execute(
        self, trigger_key: str, *, should_continue: Callable[[], bool] = lambda: True
    ) -> ScheduledAutomationStep:
        validate_identifier(trigger_key)
        if not should_continue():
            return ScheduledAutomationStep("stopped", "pending", trigger_key)
        with self.transactions.write() as unit:
            home = self.scope.require(unit).household_id
            run = unit.scheduled_automations.run(home, trigger_key)
            if run is None:
                raise NotFound("daily_automation_run_missing")
            rule_id = run.grant.draft.rule_id
            if not should_continue():
                return ScheduledAutomationStep("stopped", rule_id, trigger_key)
            if run.outcome is not ScheduledOutcome.QUEUED:
                return ScheduledAutomationStep(run.outcome.value, rule_id, trigger_key)
            command = self._command(run, RUN_SCHEDULED_AUTOMATION)
            authority = ScheduledRuleAuthority(self.scope, run, command)
            try:
                authority.require(command, unit)
            except Forbidden:
                receipt = ScheduledCancellations(
                    self.transactions, self.scope, self.clock, self.identifiers
                ).one(unit, run)
                actual = self._outcome(receipt, run)
                return ScheduledAutomationStep(actual.outcome.value, rule_id, trigger_key, receipt)

            def apply(target: UnitOfWork) -> Change:
                conditions: list[JsonValue] = []
                matched: bool | None = None
                try:
                    evaluation = evaluate_scheduled_rule(target, home, run.grant.draft.rule)
                except NotFound:
                    finished = run.finish(ScheduledOutcome.DENIED, self.clock.now())
                else:
                    matched = evaluation.matched
                    conditions = [
                        {
                            "path": list(value.path),
                            "kind": value.kind,
                            "matched": value.matched,
                            "product_id": value.product_id,
                        }
                        for value in evaluation.conditions
                    ]
                    finished = self._effect(target, run, evaluation.matched)
                target.scheduled_automations.finish(finished)
                fact = JsonDocument.from_value(
                    {
                        "trigger_key": run.key,
                        "run": run_document(finished).decode(),
                        "condition_matched": matched,
                        "conditions": conditions,
                    }
                )
                return Change(fact, fact, fact, requires_delivery=False)

            receipt = AtomicCommands(
                self.transactions, authority, self.clock, self.identifiers
            ).in_unit(unit, command, self._payload(run), apply)
            actual = self._outcome(receipt, run)
            saved = unit.scheduled_automations.run(home, trigger_key)
            if saved == run:
                unit.scheduled_automations.finish(actual)
            return ScheduledAutomationStep(actual.outcome.value, rule_id, trigger_key, receipt)

    def _effect(
        self, unit: UnitOfWork, run: ScheduledAutomationRun, matched: bool
    ) -> ScheduledAutomationRun:
        if not matched:
            return run.finish(ScheduledOutcome.NO_TASK, self.clock.now())
        request = CreateTask(run.grant.draft.rule.task)
        command = self._command(run, "task.create")
        authority = ScheduledRuleAuthority(self.scope, run, command, request)
        receipt = TaskCreationCommand(
            self.transactions, authority, self.clock, self.identifiers
        ).execute(command, request, unit)
        return run.finish(
            ScheduledOutcome.CREATED,
            self.clock.now(),
            task_operation_id=receipt.operation_id,
            task_occurrence_id=cast(str, receipt.result.decode().get("occurrence_id")),
        )
