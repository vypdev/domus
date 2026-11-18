"""Read one member's previously committed manual automation outcomes."""

import re
from collections.abc import Callable
from dataclasses import dataclass

from domus.application.automation_execution import RUN_AUTOMATION
from domus.application.automation_preview import AutomationCommandAuthority
from domus.application.fixed_materialization import MaintenanceScope
from domus.application.ports import Transactions, UnitOfWork
from domus.application.task_authorization import TaskAccess
from domus.application.task_ports import TaskCursors
from domus.domain.errors import Forbidden, InvalidInput, NotFound, StorageFailure
from domus.domain.identity import MAX_REVISION, HumanIdentity, Permission, validate_revision
from domus.domain.storage import CommandKey, JsonDocument, Receipt, validate_identifier


@dataclass(frozen=True, slots=True)
class AutomationRunSummary:
    operation_id: str
    created_at: int
    rule_revision: str
    condition_matched: bool
    task_created: bool
    historical: bool
    task_occurrence_id: str | None


@dataclass(frozen=True, slots=True)
class AutomationRunPage:
    rule_id: str
    items: tuple[AutomationRunSummary, ...]
    next_cursor: str | None


def _position(marker: str) -> int:
    if not re.fullmatch(r"[1-9][0-9]{0,18}", marker) or int(marker) > MAX_REVISION:
        raise InvalidInput("invalid_task_cursor")
    return int(marker)


def _task_access(unit: UnitOfWork, home: str, actor: HumanIdentity) -> bool:
    try:
        TaskAccess(actor).require(unit, home, Permission.TASKS_READ)
    except Forbidden:
        return False
    return True


def _summary(
    unit: UnitOfWork,
    receipt: Receipt,
    *,
    task_access: bool,
) -> AutomationRunSummary:
    result = receipt.result.decode()
    revision = result.get("rule_revision")
    matched = result.get("condition_matched")
    occurrence_id = result.get("task_occurrence_id")
    task_operation_id = result.get("task_operation_id")
    try:
        if (
            not isinstance(revision, str)
            or str(int(revision)) != revision
            or type(matched) is not bool
            or (
                matched
                and not (isinstance(occurrence_id, str) and isinstance(task_operation_id, str))
            )
            or (not matched and (occurrence_id is not None or task_operation_id is not None))
            or type(receipt.created_at) is not int
            or not 0 <= receipt.created_at <= MAX_REVISION
        ):
            raise InvalidInput("invalid_automation_run_receipt")
        validate_revision(int(revision))
        if isinstance(occurrence_id, str) and isinstance(task_operation_id, str):
            validate_identifier(occurrence_id)
            validate_identifier(task_operation_id)
    except InvalidInput, ValueError:
        raise StorageFailure("invalid_automation_run_receipt") from None

    linked = (
        occurrence_id
        if isinstance(occurrence_id, str)
        and not receipt.historical
        and task_access
        and unit.tasks.occurrence(receipt.command.household_id, occurrence_id) is not None
        else None
    )
    return AutomationRunSummary(
        receipt.operation_id,
        receipt.created_at,
        revision,
        matched,
        matched,
        receipt.historical,
        linked,
    )


@dataclass(frozen=True, slots=True)
class AutomationRunHistory:
    transactions: Transactions
    scope: MaintenanceScope
    read_actor: Callable[[], HumanIdentity]
    cursors: TaskCursors

    def page(self, rule_id: str, *, limit: int, cursor: str | None) -> AutomationRunPage:
        validate_identifier(rule_id)
        if type(limit) is not int or not 1 <= limit <= 100:
            raise InvalidInput("invalid_page_size")
        human = self.read_actor()
        home = self.scope.household_id
        authority = AutomationCommandAuthority(
            human, self.scope, CommandKey(home, human.ha_user_id, RUN_AUTOMATION, "history")
        )
        with self.transactions.read() as unit:
            member = authority.owner(unit)
            if unit.automation_drafts.latest(home, rule_id) is None:
                raise NotFound("automation_draft_missing")
            binding = JsonDocument.from_value(
                {
                    "query": "manual-automation-runs-v1",
                    "installation": self.scope.installation.instance_id,
                    "channel": self.scope.installation.channel,
                    "household": home,
                    "actor": human.ha_user_id,
                    "member": member.member_id,
                    "rule": rule_id,
                    "limit": limit,
                }
            )
            through = (
                MAX_REVISION
                if cursor is None
                else _position(self.cursors.decode(binding, cursor)) - 1
            )
            rows = unit.receipts.automation_run_page(
                home, human.ha_user_id, member.member_id, rule_id, limit=limit + 1, through=through
            )
            can_read_task = _task_access(unit, home, human)
            return AutomationRunPage(
                rule_id,
                tuple(
                    _summary(unit, receipt, task_access=can_read_task)
                    for _, receipt in rows[:limit]
                ),
                self.cursors.encode(binding, str(rows[limit - 1][0]))
                if len(rows) > limit
                else None,
            )
