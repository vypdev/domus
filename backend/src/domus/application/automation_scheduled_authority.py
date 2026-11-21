"""A persisted narrow grant authorizes one actual rule admission or task effect."""

from dataclasses import dataclass

from domus.application.fixed_materialization import MaintenanceScope
from domus.application.ports import UnitOfWork
from domus.application.task_requests import CreateTask
from domus.domain.automation_scheduling import ScheduledAutomationRun, ScheduledOutcome
from domus.domain.errors import Forbidden
from domus.domain.storage import CommandKey

ADMIT_SCHEDULED_AUTOMATION = "automation.scheduled.admit"
RUN_SCHEDULED_AUTOMATION = "automation.scheduled.run"


@dataclass(frozen=True, slots=True)
class ScheduledRuleAuthority:
    scope: MaintenanceScope
    run: ScheduledAutomationRun
    command: CommandKey
    task: CreateTask | None = None

    def require(self, command: CommandKey, unit: UnitOfWork) -> None:
        home = self.scope.require(unit).household_id
        grant = self.run.grant
        if (
            command != self.command
            or command.household_id != home
            or command.actor_id != grant.principal
            or command.key != self.run.key
            or command.action
            not in (ADMIT_SCHEDULED_AUTOMATION, RUN_SCHEDULED_AUTOMATION, "task.create")
        ):
            raise Forbidden("daily_automation_grant_denied")
        current = unit.scheduled_automations.schedule(home, grant.draft.rule_id)
        control = unit.automation_controls.get(home, grant.draft.rule_id)
        if (
            current is None
            or current.grant != grant
            or not grant.permits(self.scope.installation, home, control, current.grant.grant_id)
            or control is None
            or current.control_revision != control.control_revision
            or unit.automation_drafts.revision(home, grant.draft.rule_id, grant.draft.revision)
            != grant.draft
        ):
            raise Forbidden("daily_automation_grant_denied")
        if command.action == ADMIT_SCHEDULED_AUTOMATION:
            if (
                current.next_time != self.run.planned
                or current.control_revision != self.run.control_revision
            ):
                raise Forbidden("daily_automation_grant_denied")
        elif (
            self.run.outcome is not ScheduledOutcome.QUEUED
            or unit.scheduled_automations.run(home, self.run.key) != self.run
        ):
            raise Forbidden("daily_automation_grant_denied")
        if command.action == "task.create":
            if self.task != CreateTask(grant.draft.rule.task):
                raise Forbidden("daily_automation_capability_denied")
        elif self.task is not None:
            raise Forbidden("daily_automation_capability_denied")
