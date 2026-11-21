"""Household managers read current and historical scheduled facts under current authority."""

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

from domus.application.automation_preview import require_configuration
from domus.application.automation_scheduled_documents import receipt_run
from domus.application.fixed_materialization import MaintenanceScope
from domus.application.ports import Transactions, UnitOfWork
from domus.application.task_authorization import TaskAccess
from domus.application.task_ports import TaskCursors
from domus.domain.automation_scheduling import (
    ScheduledAutomationRun,
    ScheduledOutcome,
    automation_rule_principal,
)
from domus.domain.errors import Forbidden, InvalidInput, NotFound, StorageFailure
from domus.domain.identity import HumanIdentity, Permission
from domus.domain.recurrence_time import MAX_INSTANT_MS, TimeResolution
from domus.domain.storage import CommandKey, JsonDocument, Receipt, validate_identifier


@dataclass(frozen=True, slots=True)
class ScheduledRunSummary:
    trigger_key: str
    rule_revision: str
    control_revision: str
    requested_local: str
    resolved_local: str
    scheduled_at: int
    time_zone: str
    resolution: TimeResolution
    admitted_at: int
    outcome: ScheduledOutcome
    finished_at: int | None
    historical: bool
    task_created: bool
    task_occurrence_id: str | None
    operation_id: str | None


@dataclass(frozen=True, slots=True)
class ScheduledRunPage:
    rule_id: str
    items: tuple[ScheduledRunSummary, ...]
    next_cursor: str | None


def _position(value: str) -> tuple[int, str]:
    match = re.fullmatch(r"(0|[1-9][0-9]{0,14})\.([a-f0-9]{64})", value)
    if match is None or int(match[1]) > MAX_INSTANT_MS:
        raise InvalidInput("invalid_task_cursor")
    return int(match[1]), match[2]


def _summary(
    unit: UnitOfWork, run: ScheduledAutomationRun, proof: Receipt | None, *, task_access: bool
) -> ScheduledRunSummary:
    historical = proof is not None and proof.historical
    linked = None
    if run.outcome is ScheduledOutcome.CREATED:
        task = unit.receipts.get(
            CommandKey(run.grant.household_id, run.grant.principal, "task.create", run.key)
        )
        if (
            proof is None
            or task is None
            or task.operation_id != run.task_operation_id
            or task.result.decode().get("occurrence_id") != run.task_occurrence_id
        ):
            raise StorageFailure("invalid_daily_automation_task_proof")
        historical = historical or task.historical
        if (
            not historical
            and task_access
            and unit.tasks.occurrence(run.grant.household_id, cast(str, run.task_occurrence_id))
            is not None
        ):
            linked = run.task_occurrence_id
    return ScheduledRunSummary(
        run.key,
        str(run.grant.draft.revision),
        str(run.control_revision),
        run.planned.nominal.local.isoformat(),
        run.planned.resolved_local.isoformat(),
        run.planned.instant_ms,
        run.planned.policy.zone,
        run.planned.resolution,
        run.admitted_at,
        run.outcome,
        run.finished_at,
        historical,
        run.outcome is ScheduledOutcome.CREATED,
        linked,
        None if proof is None else proof.operation_id,
    )


@dataclass(frozen=True, slots=True)
class ScheduledAutomationHistory:
    transactions: Transactions
    scope: MaintenanceScope
    read_actor: Callable[[], HumanIdentity]
    cursors: TaskCursors

    def page(self, rule_id: str, *, limit: int, cursor: str | None) -> ScheduledRunPage:
        validate_identifier(rule_id)
        if type(limit) is not int or not 1 <= limit <= 100:
            raise InvalidInput("invalid_page_size")
        human = self.read_actor()
        with self.transactions.read() as unit:
            home = self.scope.require(unit).household_id
            member = require_configuration(unit, home, human)
            if unit.automation_drafts.latest(home, rule_id) is None:
                raise NotFound("automation_draft_missing")
            principal = automation_rule_principal(self.scope.installation, home, rule_id)
            binding = JsonDocument.from_value(
                {
                    "query": "scheduled-automation-runs-v1",
                    "installation": self.scope.installation.instance_id,
                    "channel": self.scope.installation.channel,
                    "household": home,
                    "actor": human.ha_user_id,
                    "member": member.member_id,
                    "rule": rule_id,
                    "limit": limit,
                }
            )
            before = None if cursor is None else _position(self.cursors.decode(binding, cursor))
            rows = unit.scheduled_automations.history(home, rule_id, before=before, limit=limit + 1)
            combined: dict[str, tuple[ScheduledAutomationRun, Receipt | None]] = {}
            for run in rows:
                proof = unit.receipts.get(
                    CommandKey(home, principal, "automation.scheduled.run", run.key)
                )
                if proof is None:
                    proof = unit.receipts.get(
                        CommandKey(home, principal, "automation.scheduled.admit", run.key)
                    )
                    combined[run.key] = (run, proof)
                else:
                    combined[run.key] = (receipt_run(proof), proof)
            for proof in unit.receipts.archived_scheduled_runs(
                home, principal, before=before, limit=limit + 1
            ):
                run = receipt_run(proof)
                if run.key not in combined:
                    combined[run.key] = (run, proof)
            values = sorted(
                combined.values(), key=lambda item: (item[0].admitted_at, item[0].key), reverse=True
            )
            for run, _ in values:
                if (
                    run.grant.installation != self.scope.installation
                    or run.grant.household_id != home
                    or run.grant.draft.rule_id != rule_id
                ):
                    raise StorageFailure("invalid_daily_automation_history")
            try:
                TaskAccess(human).require(unit, home, Permission.TASKS_READ)
            except Forbidden:
                task_access = False
            else:
                task_access = True
            items = tuple(
                _summary(unit, run, proof, task_access=task_access) for run, proof in values[:limit]
            )
            next_cursor = None
            if len(values) > limit:
                last = values[limit - 1][0]
                next_cursor = self.cursors.encode(binding, str(last.admitted_at) + "." + last.key)
            return ScheduledRunPage(rule_id, items, next_cursor)
