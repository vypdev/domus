"""A checkpoint cannot replace a rule grant's scope, definition or committed task proof."""

import sqlite3
from dataclasses import replace

from domus.application.automation_scheduled_documents import receipt_run
from domus.domain.automation_scheduling import RuleExecutionGrant, ScheduledOutcome
from domus.domain.errors import StorageFailure
from domus.domain.storage import CommandKey, Installation
from domus.infrastructure.sqlite_automation_drafts import SQLiteAutomationDrafts
from domus.infrastructure.sqlite_automation_schedules import SQLiteScheduledAutomations
from domus.infrastructure.sqlite_receipts import SQLiteReceipts


def _grant(connection: sqlite3.Connection, value: RuleExecutionGrant) -> None:
    if (
        SQLiteAutomationDrafts(connection).revision(
            value.household_id, value.draft.rule_id, value.draft.revision
        )
        != value.draft
    ):
        raise StorageFailure("invalid_daily_automation_source")


def verify_scheduled_automations(
    connection: sqlite3.Connection, installation: Installation
) -> None:
    records = SQLiteScheduledAutomations(connection, installation)
    for row in connection.execute("SELECT * FROM automation_daily_schedules"):
        value = records._schedule(row)
        _grant(connection, value.grant)
    for row in connection.execute("SELECT * FROM automation_scheduled_runs"):
        run = records._run(row)
        _grant(connection, run.grant)
        receipts = SQLiteReceipts(connection)
        admission = receipts.get(
            CommandKey(
                run.grant.household_id, run.grant.principal, "automation.scheduled.admit", run.key
            )
        )
        expected = replace(
            run,
            outcome=ScheduledOutcome.QUEUED,
            finished_at=None,
            task_operation_id=None,
            task_occurrence_id=None,
        )
        if admission is None or receipt_run(admission) != expected:
            raise StorageFailure("invalid_daily_automation_admission_proof")
        effect = receipts.get(
            CommandKey(
                run.grant.household_id, run.grant.principal, "automation.scheduled.run", run.key
            )
        )
        if run.outcome in (
            ScheduledOutcome.CREATED,
            ScheduledOutcome.NO_TASK,
            ScheduledOutcome.DENIED,
        ):
            if effect is None or receipt_run(effect) != run:
                raise StorageFailure("invalid_daily_automation_outcome_proof")
        elif effect is not None and not effect.historical:
            raise StorageFailure("invalid_daily_automation_outcome_proof")
        if run.outcome is ScheduledOutcome.CREATED:
            proof = SQLiteReceipts(connection).get(
                CommandKey(run.grant.household_id, run.grant.principal, "task.create", run.key)
            )
            if (
                proof is None
                or proof.operation_id != run.task_operation_id
                or proof.result.decode().get("occurrence_id") != run.task_occurrence_id
            ):
                raise StorageFailure("invalid_daily_automation_task_proof")
