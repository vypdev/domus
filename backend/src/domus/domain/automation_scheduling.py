"""Rule-owned execution grants and durable daily facts do not impersonate a member."""

from dataclasses import dataclass, replace
from datetime import date, time
from enum import StrEnum
from typing import cast

from domus.domain.automation import AutomationControl, AutomationDraft, AutomationRule, DailyTrigger
from domus.domain.errors import Conflict, InvalidInput
from domus.domain.identity import validate_revision
from domus.domain.recurrence_time import MAX_INSTANT_MS, ResolvedTime, TimePolicy
from domus.domain.storage import Installation, JsonDocument, validate_identifier


def _instant(value: int) -> None:
    if type(value) is not int or not 0 <= value <= MAX_INSTANT_MS:
        raise InvalidInput("invalid_daily_automation_instant")


def automation_rule_principal(installation: Installation, household_id: str, rule_id: str) -> str:
    validate_identifier(household_id)
    validate_identifier(rule_id)
    identity = JsonDocument.from_value(
        {
            "installation": installation.instance_id,
            "channel": installation.channel,
            "household_id": household_id,
            "rule_id": rule_id,
        }
    )
    return "system:automation:" + identity.fingerprint


@dataclass(frozen=True, slots=True)
class RuleExecutionGrant:
    installation: Installation
    household_id: str
    grant_id: str
    draft: AutomationDraft

    def __post_init__(self) -> None:
        if (
            not isinstance(self.installation, Installation)
            or not isinstance(self.draft, AutomationDraft)
            or not isinstance(self.draft.rule, AutomationRule)
            or not isinstance(self.draft.rule.trigger, DailyTrigger)
        ):
            raise InvalidInput("invalid_daily_automation_grant")
        validate_identifier(self.household_id)
        validate_identifier(self.grant_id)
        # This checks the closed task.create capability as well as the bounded
        # rule. A title proposal cannot smuggle in task overrides or materials.
        self.draft.rule.document()

    @property
    def principal(self) -> str:
        return automation_rule_principal(self.installation, self.household_id, self.draft.rule_id)

    def permits(
        self,
        installation: Installation,
        household_id: str,
        control: AutomationControl | None,
        current_grant_id: str | None,
    ) -> bool:
        return (
            installation == self.installation
            and household_id == self.household_id
            and current_grant_id == self.grant_id
            and control is not None
            and control.enabled
            and control.rule_id == self.draft.rule_id
            and control.rule_revision == self.draft.revision
        )

    def require_planned(self, planned: ResolvedTime) -> None:
        trigger = cast(DailyTrigger, self.draft.rule.trigger)
        if not isinstance(
            planned, ResolvedTime
        ) or planned.nominal.local.time() != time.fromisoformat(trigger.time):
            raise InvalidInput("invalid_daily_automation_trigger")

    def trigger_key(self, planned: ResolvedTime) -> str:
        self.require_planned(planned)
        return JsonDocument.from_value(
            {
                "principal": self.principal,
                "rule_revision": self.draft.revision,
                "nominal_date": planned.nominal.local.date().isoformat(),
            }
        ).fingerprint


@dataclass(frozen=True, slots=True)
class DailySuppression:
    first: ResolvedTime
    through_ms: int

    def __post_init__(self) -> None:
        _instant(self.through_ms)
        if not isinstance(self.first, ResolvedTime) or self.first.instant_ms > self.through_ms:
            raise InvalidInput("invalid_daily_automation_suppression")


@dataclass(frozen=True, slots=True)
class DailyAutomationSchedule:
    grant: RuleExecutionGrant
    control_revision: int
    policy: TimePolicy
    next_time: ResolvedTime
    startup_cutoff_ms: int
    last_nominal: date | None = None
    suppression: DailySuppression | None = None
    revision: int = 1

    def __post_init__(self) -> None:
        validate_revision(self.control_revision)
        validate_revision(self.revision)
        _instant(self.startup_cutoff_ms)
        if (
            not isinstance(self.grant, RuleExecutionGrant)
            or not isinstance(self.policy, TimePolicy)
            or not isinstance(self.next_time, ResolvedTime)
            or self.next_time.policy != self.policy
            or self.next_time.instant_ms <= self.startup_cutoff_ms
            or (self.last_nominal is not None and type(self.last_nominal) is not date)
            or (
                self.last_nominal is not None
                and self.next_time.nominal.local.date() <= self.last_nominal
            )
            or (self.suppression is not None and not isinstance(self.suppression, DailySuppression))
        ):
            raise InvalidInput("invalid_daily_automation_schedule")
        self.grant.require_planned(self.next_time)


class ScheduledOutcome(StrEnum):
    QUEUED = "queued"
    CREATED = "created"
    NO_TASK = "no_task"
    CANCELLED = "cancelled"
    DENIED = "denied"


@dataclass(frozen=True, slots=True)
class ScheduledAutomationRun:
    grant: RuleExecutionGrant
    control_revision: int
    planned: ResolvedTime
    admitted_at: int
    outcome: ScheduledOutcome = ScheduledOutcome.QUEUED
    finished_at: int | None = None
    task_operation_id: str | None = None
    task_occurrence_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.grant, RuleExecutionGrant):
            raise InvalidInput("invalid_daily_automation_run")
        validate_revision(self.control_revision)
        _instant(self.admitted_at)
        self.grant.require_planned(self.planned)
        if (
            not isinstance(self.outcome, ScheduledOutcome)
            or self.admitted_at < self.planned.instant_ms
            or (self.outcome is ScheduledOutcome.QUEUED) != (self.finished_at is None)
        ):
            raise InvalidInput("invalid_daily_automation_run")
        if self.finished_at is not None:
            _instant(self.finished_at)
        if self.outcome is ScheduledOutcome.CREATED:
            validate_identifier(cast(str, self.task_operation_id))
            validate_identifier(cast(str, self.task_occurrence_id))
        elif self.task_operation_id is not None or self.task_occurrence_id is not None:
            raise InvalidInput("invalid_daily_automation_run")

    @property
    def key(self) -> str:
        return self.grant.trigger_key(self.planned)

    def finish(
        self,
        outcome: ScheduledOutcome,
        at: int,
        *,
        task_operation_id: str | None = None,
        task_occurrence_id: str | None = None,
    ) -> ScheduledAutomationRun:
        if self.outcome is not ScheduledOutcome.QUEUED or outcome is ScheduledOutcome.QUEUED:
            raise Conflict("daily_automation_run_finished")
        return replace(
            self,
            outcome=outcome,
            finished_at=at,
            task_operation_id=task_operation_id,
            task_occurrence_id=task_occurrence_id,
        )
