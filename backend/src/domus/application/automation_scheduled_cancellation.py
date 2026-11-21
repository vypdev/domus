"""A queued cancellation retains its original terminal proof across restoration."""

from dataclasses import dataclass

from domus.application.automation_scheduled_authority import RUN_SCHEDULED_AUTOMATION
from domus.application.automation_scheduled_documents import (
    matching_run,
    run_document,
    scheduled_payload,
)
from domus.application.commands import AtomicCommands, Change
from domus.application.fixed_materialization import MaintenanceScope
from domus.application.ports import Clock, Identifiers, Transactions, UnitOfWork
from domus.domain.automation_scheduling import ScheduledAutomationRun, ScheduledOutcome
from domus.domain.errors import Forbidden, StorageFailure
from domus.domain.storage import CommandKey, JsonDocument, Receipt


@dataclass(frozen=True, slots=True)
class _CancellationAuthority:
    scope: MaintenanceScope
    run: ScheduledAutomationRun

    def require(self, command: CommandKey, unit: UnitOfWork) -> None:
        home = self.scope.require(unit).household_id
        expected = CommandKey(
            home, self.run.grant.principal, RUN_SCHEDULED_AUTOMATION, self.run.key
        )
        if (
            command != expected
            or self.run.grant.installation != self.scope.installation
            or self.run.grant.household_id != home
            or self.run.outcome is not ScheduledOutcome.QUEUED
            or unit.scheduled_automations.run(home, self.run.key) != self.run
        ):
            raise Forbidden("daily_automation_cancellation_denied")


@dataclass(frozen=True, slots=True)
class ScheduledCancellations:
    transactions: Transactions
    scope: MaintenanceScope
    clock: Clock
    identifiers: Identifiers

    def pending(self, unit: UnitOfWork, rule_id: str) -> int:
        home = self.scope.require(unit).household_id
        values = unit.scheduled_automations.pending(home, rule_id=rule_id, limit=101)
        if len(values) > 100:
            raise StorageFailure("invalid_daily_automation_queue")
        for value in values:
            self.one(unit, value)
        return len(values)

    def one(self, unit: UnitOfWork, run: ScheduledAutomationRun) -> Receipt:
        command = CommandKey(
            self.scope.household_id, run.grant.principal, RUN_SCHEDULED_AUTOMATION, run.key
        )

        def apply(_target: UnitOfWork) -> Change:
            cancelled = run.finish(ScheduledOutcome.CANCELLED, self.clock.now())
            fact = JsonDocument.from_value(
                {
                    "trigger_key": run.key,
                    "run": run_document(cancelled).decode(),
                    "condition_matched": None,
                    "conditions": [],
                }
            )
            return Change(fact, fact, fact, requires_delivery=False)

        receipt = AtomicCommands(
            self.transactions, _CancellationAuthority(self.scope, run), self.clock, self.identifiers
        ).in_unit(unit, command, scheduled_payload(run), apply)
        # A restored original may already describe a committed effect. Preserve that
        # actual outcome instead of relabelling it as a newly cancelled run.
        unit.scheduled_automations.finish(matching_run(receipt, run))
        return receipt
