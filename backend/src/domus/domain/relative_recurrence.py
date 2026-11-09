"""Completion-relative rule, progress and original-cycle facts contain no authority grants."""

import json
import re
from dataclasses import asdict, dataclass, replace
from datetime import timedelta
from enum import StrEnum

from domus.domain.errors import InvalidInput
from domus.domain.identity import validate_revision
from domus.domain.recurrence_planning import PlannedSlot
from domus.domain.recurrence_records import MAINTENANCE_ACTOR, ScheduleState
from domus.domain.recurrence_rules import NominalDate
from domus.domain.recurrence_time import LocalInstant, NominalTime, RelativeInterval, TimePolicy
from domus.domain.storage import (
    CommandKey,
    Installation,
    JsonDocument,
    Receipt,
    validate_identifier,
)
from domus.domain.task_values import VerificationState, validate_task_time
from domus.domain.tasks import TaskCycle


class SuccessorVisibility(StrEnum):
    AT_COMPLETION = "at_completion"
    AT_VERIFICATION = "at_verification"


@dataclass(frozen=True, slots=True)
class RelativeOperation:
    """A reference to original proof; possession grants no execution capability."""

    command: CommandKey
    operation_id: str

    def __post_init__(self) -> None:
        validate_identifier(self.operation_id)
        if not isinstance(self.command, CommandKey):
            raise InvalidInput("invalid_relative_operation")


@dataclass(frozen=True, slots=True)
class RelativeSchedule:
    schedule_id: str
    household_id: str
    definition_id: str
    initial: PlannedSlot
    interval: RelativeInterval
    policy: TimePolicy
    created_at: int
    visibility: SuccessorVisibility = SuccessorVisibility.AT_COMPLETION
    state: ScheduleState = ScheduleState.ACTIVE
    revision: int = 1
    pattern_revision: int = 1

    def __post_init__(self) -> None:
        for value in (self.schedule_id, self.household_id, self.definition_id):
            validate_identifier(value)
        validate_revision(self.revision)
        validate_revision(self.pattern_revision)
        validate_task_time(self.created_at)
        if (
            not isinstance(self.initial, PlannedSlot)
            or not isinstance(self.interval, RelativeInterval)
            or not isinstance(self.policy, TimePolicy)
            or not isinstance(self.visibility, SuccessorVisibility)
            or not isinstance(self.state, ScheduleState)
            or self.pattern_revision > self.revision
        ):
            raise InvalidInput("invalid_relative_schedule")

        # A reviewed fold change applies to successors. The issued initial instant
        # and its original policy remain the anchor recorded in earlier proof.
        if self.initial.resolved is not None:
            initial_policy = self.initial.resolved.policy
            if initial_policy != self.policy and (
                self.pattern_revision == 1
                or replace(initial_policy, repeated_time=self.policy.repeated_time) != self.policy
            ):
                raise InvalidInput("invalid_relative_schedule")

    def same_timing(self, other: RelativeSchedule) -> bool:
        return (self.initial, self.interval, self.policy, self.visibility) == (
            other.initial,
            other.interval,
            other.policy,
            other.visibility,
        )

    def generation_document(self) -> JsonDocument:
        return JsonDocument(
            json.dumps(
                {
                    "version": 1,
                    "schedule_id": self.schedule_id,
                    "household_id": self.household_id,
                    "definition_id": self.definition_id,
                    "created_at": self.created_at,
                    "pattern_revision": self.pattern_revision,
                    "initial": self.initial.value(),
                    "interval_days": self.interval.days,
                    "policy": asdict(self.policy),
                    "visibility": self.visibility.value,
                }
            )
        )

    @property
    def binding(self) -> str:
        return self.generation_document().fingerprint

    def allows_successor(self, cycle: TaskCycle) -> bool:
        if not isinstance(cycle, TaskCycle) or cycle.household_id != self.household_id:
            raise InvalidInput("invalid_relative_source")
        return (
            self.state is ScheduleState.ACTIVE
            and cycle.closed_at is None
            and cycle.verification is not VerificationState.REJECTED
            and (
                self.visibility is SuccessorVisibility.AT_COMPLETION
                or cycle.verification in (VerificationState.NONE, VerificationState.APPROVED)
            )
        )


@dataclass(frozen=True, slots=True)
class RelativeProgress:
    schedule_id: str
    household_id: str
    pattern_revision: int
    binding: str
    current_occurrence_id: str | None = None
    current_slot_key: str | None = None
    source_after: int = 0
    last_run_at: int | None = None
    revision: int = 1
    evidence: RelativeOperation | None = None

    def __post_init__(self) -> None:
        validate_identifier(self.schedule_id)
        validate_identifier(self.household_id)
        validate_revision(self.pattern_revision)
        validate_revision(self.revision)
        if self.current_occurrence_id is not None:
            validate_identifier(self.current_occurrence_id)
        if self.current_slot_key is not None:
            validate_identifier(self.current_slot_key)
        if self.last_run_at is not None:
            validate_task_time(self.last_run_at)
        if (
            not isinstance(self.binding, str)
            or re.fullmatch(r"[a-f0-9]{64}", self.binding) is None
            or (self.current_occurrence_id is None) != (self.current_slot_key is None)
            or type(self.source_after) is not int
            or not 0 <= self.source_after <= 2**63 - 1
            or (self.evidence is not None and not isinstance(self.evidence, RelativeOperation))
        ):
            raise InvalidInput("invalid_relative_progress")

    def matches_schedule(self, schedule: RelativeSchedule) -> bool:
        return (
            self.schedule_id == schedule.schedule_id
            and self.household_id == schedule.household_id
            and self.pattern_revision == schedule.pattern_revision
            and self.binding == schedule.binding
            and (self.evidence is None or self.evidence.command.household_id == self.household_id)
        )

    @property
    def pristine(self) -> bool:
        return (
            self.current_occurrence_id is None
            and self.source_after == 0
            and self.last_run_at is None
            and self.evidence is None
        )

    def state_document(self) -> JsonDocument:
        """Business continuation excludes observational time and mutable CAS revision."""
        return JsonDocument.from_value(
            {
                "version": 1,
                "schedule_id": self.schedule_id,
                "household_id": self.household_id,
                "pattern_revision": self.pattern_revision,
                "binding": self.binding,
                "current_occurrence_id": self.current_occurrence_id,
                "current_slot_key": self.current_slot_key,
                "source_after": self.source_after,
            }
        )

    def matches_receipt(self, receipt: Receipt | None) -> bool:
        evidence = self.evidence
        if evidence is None:
            return self.pristine
        if (
            receipt is None
            or receipt.command != evidence.command
            or receipt.operation_id != evidence.operation_id
        ):
            return False
        return JsonDocument.from_value(
            {"state": receipt.result.decode().get("relative_progress")}
        ) == JsonDocument.from_value({"state": self.state_document().decode()})


@dataclass(frozen=True, slots=True)
class RelativeSource:
    cycle: TaskCycle
    performed_local: LocalInstant

    def __post_init__(self) -> None:
        if (
            not isinstance(self.cycle, TaskCycle)
            or not isinstance(self.performed_local, LocalInstant)
            or self.cycle != self.cycle.completion_snapshot()
            or self.cycle.performed_at != self.performed_local.instant_ms
        ):
            raise InvalidInput("invalid_relative_source")

    @classmethod
    def from_cycle(cls, cycle: TaskCycle, local: LocalInstant) -> RelativeSource:
        if not isinstance(cycle, TaskCycle):
            raise InvalidInput("invalid_relative_source")
        return cls(cycle.completion_snapshot(), local)


@dataclass(frozen=True, slots=True)
class RelativeSlot:
    installation: Installation
    schedule: RelativeSchedule
    planned: PlannedSlot
    occurrence_id: str
    created_at: int
    source: RelativeSource | None = None

    def __post_init__(self) -> None:
        validate_identifier(self.occurrence_id)
        validate_task_time(self.created_at)
        if (
            not isinstance(self.installation, Installation)
            or not isinstance(self.schedule, RelativeSchedule)
            or not isinstance(self.planned, PlannedSlot)
            or self.created_at < self.schedule.created_at
            or type(self.planned.nominal) is not type(self.schedule.initial.nominal)
            or (
                self.planned.resolved is not None
                and self.planned.resolved.policy != self.schedule.policy
            )
        ):
            raise InvalidInput("invalid_relative_slot")
        if self.source is None:
            if self.planned != self.schedule.initial:
                raise InvalidInput("invalid_relative_slot")
            return
        source = self.source
        if (
            not isinstance(source, RelativeSource)
            or source.cycle.household_id != self.schedule.household_id
            or source.cycle.occurrence_id == self.occurrence_id
            or source.cycle.recorded_at > self.created_at
            or source.performed_local.policy != self.schedule.policy
            or (
                self.planned.resolved is not None
                and self.planned.resolved.zone_digest != source.performed_local.zone_digest
            )
        ):
            raise InvalidInput("invalid_relative_slot")
        try:
            local = source.performed_local.local + timedelta(days=self.schedule.interval.days)
        except OverflowError:
            raise InvalidInput("recurrence_time_out_of_range") from None
        expected = (
            NominalDate(local.date())
            if isinstance(self.schedule.initial.nominal, NominalDate)
            else NominalTime(local)
        )
        if self.planned.nominal != expected:
            raise InvalidInput("invalid_relative_slot")

    def consistent_with(self, current: RelativeSchedule) -> bool:
        original = self.schedule
        return (
            original.schedule_id == current.schedule_id
            and original.household_id == current.household_id
            and original.definition_id == current.definition_id
            and original.created_at == current.created_at
            and original.revision <= current.revision
            and original.pattern_revision <= current.pattern_revision
            and (
                original.pattern_revision < current.pattern_revision
                or original.same_timing(current)
            )
        )

    @property
    def evidence_fingerprint(self) -> str:
        schedule = self.schedule
        source = self.source
        value = {
            "version": 1,
            "installation": asdict(self.installation),
            "generation": schedule.generation_document().decode(),
            "planned": self.planned.value(),
            "occurrence_id": self.occurrence_id,
            "created_at": self.created_at,
            "source": None
            if source is None
            else {
                "cycle": asdict(source.cycle),
                "performed_local": {
                    "instant_ms": source.performed_local.instant_ms,
                    "local": source.performed_local.local.isoformat(),
                    "offset_seconds": source.performed_local.offset_seconds,
                    "policy": asdict(source.performed_local.policy),
                    "zone_digest": source.performed_local.zone_digest,
                },
            },
        }
        return JsonDocument(json.dumps(value)).fingerprint

    def matches_receipt(self, receipt: Receipt | None) -> bool:
        if receipt is None or receipt.command != self.command or receipt.historical:
            return False
        result = receipt.result.decode()
        keys = (
            "slot_key",
            "occurrence_id",
            "schedule_id",
            "definition_id",
            "relative_slot_fingerprint",
        )
        return JsonDocument.from_value(
            {key: result.get(key) for key in keys}
        ) == JsonDocument.from_value(
            {
                "slot_key": self.key,
                "occurrence_id": self.occurrence_id,
                "schedule_id": self.schedule.schedule_id,
                "definition_id": self.schedule.definition_id,
                "relative_slot_fingerprint": self.evidence_fingerprint,
            }
        )

    @property
    def key(self) -> str:
        source = (
            None
            if self.source is None
            else {
                "occurrence": self.source.cycle.occurrence_id,
                "cycle": self.source.cycle.cycle_id,
            }
        )
        return JsonDocument.from_value(
            {
                "version": 1,
                "instance": self.installation.instance_id,
                "channel": self.installation.channel,
                "household": self.schedule.household_id,
                "schedule": self.schedule.schedule_id,
                "pattern_revision": self.schedule.pattern_revision,
                "timing": "completion_relative",
                "source": source,
            }
        ).fingerprint

    @property
    def command(self) -> CommandKey:
        return CommandKey(
            self.schedule.household_id, MAINTENANCE_ACTOR, "recurrence.materialize", self.key
        )
