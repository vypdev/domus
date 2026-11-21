"""Closed semantic documents retain reviewed timing and immutable admission snapshots."""

from datetime import date, datetime
from typing import cast

from domus.domain.automation import AutomationDraft, AutomationRule
from domus.domain.automation_scheduling import (
    DailyAutomationSchedule,
    DailySuppression,
    RuleExecutionGrant,
    ScheduledAutomationRun,
    ScheduledOutcome,
)
from domus.domain.errors import InvalidInput, StorageFailure
from domus.domain.fold_policy import FoldPolicy
from domus.domain.recurrence_time import NominalTime, ResolvedTime, TimePolicy, TimeResolution
from domus.domain.storage import Installation, JsonDocument, JsonObject, Receipt


def _grant_value(value: RuleExecutionGrant) -> JsonObject:
    return {
        "installation_id": value.installation.instance_id,
        "channel": value.installation.channel,
        "household_id": value.household_id,
        "grant_id": value.grant_id,
        "rule_id": value.draft.rule_id,
        "rule_revision": value.draft.revision,
        "rule": value.draft.rule.document().encoded,
    }


def _grant(data: JsonObject) -> RuleExecutionGrant:
    return RuleExecutionGrant(
        Installation(cast(str, data["installation_id"]), cast(str, data["channel"])),
        cast(str, data["household_id"]),
        cast(str, data["grant_id"]),
        AutomationDraft(
            cast(str, data["rule_id"]),
            cast(int, data["rule_revision"]),
            AutomationRule.from_document(JsonDocument(cast(str, data["rule"]))),
        ),
    )


def _policy_value(value: TimePolicy) -> JsonObject:
    return {
        "zone": value.zone,
        "data_identity": value.data_identity,
        "repeated_time": value.repeated_time.value,
        "revision": value.revision,
    }


def _policy(data: JsonObject) -> TimePolicy:
    return TimePolicy(
        cast(str, data["zone"]),
        cast(str, data["data_identity"]),
        FoldPolicy(cast(str, data["repeated_time"])),
        cast(int, data["revision"]),
    )


def _time_value(value: ResolvedTime) -> JsonObject:
    return {
        "nominal": value.nominal.local.isoformat(),
        "policy": _policy_value(value.policy),
        "resolved_local": value.resolved_local.isoformat(),
        "offset_seconds": value.offset_seconds,
        "resolution": value.resolution.value,
        "zone_digest": value.zone_digest,
    }


def _time(data: JsonObject) -> ResolvedTime:
    return ResolvedTime(
        NominalTime(datetime.fromisoformat(cast(str, data["nominal"]))),
        _policy(cast(JsonObject, data["policy"])),
        datetime.fromisoformat(cast(str, data["resolved_local"])),
        cast(int, data["offset_seconds"]),
        TimeResolution(cast(str, data["resolution"])),
        cast(str, data["zone_digest"]),
    )


def planned_document(value: ResolvedTime) -> JsonDocument:
    return JsonDocument.from_value(_time_value(value))


def read_planned(document: JsonDocument) -> ResolvedTime:
    try:
        value = _time(document.decode())
        if planned_document(value) != document:
            raise InvalidInput("invalid_daily_automation_review")
        return value
    except InvalidInput, KeyError, TypeError, ValueError:
        raise InvalidInput("invalid_daily_automation_review") from None


def schedule_document(value: DailyAutomationSchedule) -> JsonDocument:
    suppression: JsonObject | None = None
    if value.suppression is not None:
        suppression = {
            "first": _time_value(value.suppression.first),
            "through_ms": value.suppression.through_ms,
        }
    data: JsonObject = {
        "version": 1,
        "grant": _grant_value(value.grant),
        "control_revision": value.control_revision,
        "revision": value.revision,
        "policy": _policy_value(value.policy),
        "next_time": _time_value(value.next_time),
        "startup_cutoff_ms": value.startup_cutoff_ms,
        "last_nominal": None if value.last_nominal is None else value.last_nominal.isoformat(),
        "suppression": suppression,
    }
    return JsonDocument.from_value(data)


def read_schedule(encoded: str) -> DailyAutomationSchedule:
    try:
        document = JsonDocument(encoded)
        data = document.decode()
        suppression = cast(JsonObject | None, data["suppression"])
        value = DailyAutomationSchedule(
            _grant(cast(JsonObject, data["grant"])),
            cast(int, data["control_revision"]),
            _policy(cast(JsonObject, data["policy"])),
            _time(cast(JsonObject, data["next_time"])),
            cast(int, data["startup_cutoff_ms"]),
            None
            if data["last_nominal"] is None
            else date.fromisoformat(cast(str, data["last_nominal"])),
            None
            if suppression is None
            else DailySuppression(
                _time(cast(JsonObject, suppression["first"])), cast(int, suppression["through_ms"])
            ),
            cast(int, data["revision"]),
        )
        if schedule_document(value).encoded != encoded:
            raise InvalidInput("invalid_daily_automation_record")
        return value
    except InvalidInput, KeyError, TypeError, ValueError:
        raise StorageFailure("invalid_daily_automation_record") from None


def run_document(value: ScheduledAutomationRun) -> JsonDocument:
    return JsonDocument.from_value(
        {
            "version": 1,
            "grant": _grant_value(value.grant),
            "control_revision": value.control_revision,
            "planned": _time_value(value.planned),
            "admitted_at": value.admitted_at,
            "outcome": value.outcome.value,
            "finished_at": value.finished_at,
            "task_operation_id": value.task_operation_id,
            "task_occurrence_id": value.task_occurrence_id,
        }
    )


def read_run(encoded: str) -> ScheduledAutomationRun:
    try:
        document = JsonDocument(encoded)
        data = document.decode()
        value = ScheduledAutomationRun(
            _grant(cast(JsonObject, data["grant"])),
            cast(int, data["control_revision"]),
            _time(cast(JsonObject, data["planned"])),
            cast(int, data["admitted_at"]),
            ScheduledOutcome(cast(str, data["outcome"])),
            cast(int | None, data["finished_at"]),
            cast(str | None, data["task_operation_id"]),
            cast(str | None, data["task_occurrence_id"]),
        )
        if run_document(value).encoded != encoded:
            raise InvalidInput("invalid_daily_automation_record")
        return value
    except InvalidInput, KeyError, TypeError, ValueError:
        raise StorageFailure("invalid_daily_automation_record") from None


def receipt_run(receipt: Receipt) -> ScheduledAutomationRun:
    try:
        value = read_run(JsonDocument.from_value(receipt.result.decode().get("run")).encoded)
    except InvalidInput:
        raise StorageFailure("invalid_daily_automation_outcome") from None
    if (
        receipt.command.action not in ("automation.scheduled.admit", "automation.scheduled.run")
        or receipt.command.household_id != value.grant.household_id
        or receipt.command.actor_id != value.grant.principal
        or receipt.command.key != value.key
        or receipt.result.decode().get("trigger_key") != value.key
        or (receipt.command.action == "automation.scheduled.admit")
        != (value.outcome is ScheduledOutcome.QUEUED)
    ):
        raise StorageFailure("invalid_daily_automation_outcome")
    return value
