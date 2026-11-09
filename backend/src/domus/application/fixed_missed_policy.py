"""Review a per-definition policy change without altering an occurrence or rule."""

from dataclasses import dataclass

from domus.application.fixed_materialization import MaintenanceScope
from domus.application.ports import UnitOfWork
from domus.domain.errors import Conflict, InvalidInput, NotFound, StorageFailure
from domus.domain.identity import validate_revision
from domus.domain.recurrence_records import ScheduleState
from domus.domain.storage import JsonDocument, validate_identifier
from domus.domain.task_values import (
    DefinitionState,
    MissedOccurrencePolicy,
    MissedOccurrenceSettings,
)


@dataclass(frozen=True, slots=True)
class FixedMissedPolicy:
    schedule_id: str
    schedule_revision: int
    policy_revision: int
    policy: MissedOccurrencePolicy

    def __post_init__(self) -> None:
        validate_identifier(self.schedule_id)
        validate_revision(self.schedule_revision)
        if (
            not isinstance(self.policy, MissedOccurrencePolicy)
            or type(self.policy_revision) is not int
            or not 0 <= self.policy_revision <= 2**63 - 1
        ):
            raise InvalidInput("invalid_missed_occurrence_settings")

    def document(self) -> JsonDocument:
        return JsonDocument.from_value(
            {
                "version": 1,
                "kind": "fixed_missed_policy",
                "schedule_id": self.schedule_id,
                "schedule_revision": self.schedule_revision,
                "policy_revision": self.policy_revision,
                "missed_occurrence_policy": self.policy.value,
            }
        )


def missed_policy_plan(
    unit: UnitOfWork, scope: MaintenanceScope, request: FixedMissedPolicy
) -> tuple[MissedOccurrenceSettings, JsonDocument]:
    home = scope.household_id
    rule = unit.recurrence.schedule(home, request.schedule_id)
    if rule is None:
        raise NotFound("recurrence_rule_missing")
    current = unit.tasks.missed_occurrence_settings(home, rule.definition_id)
    if rule.revision != request.schedule_revision or current.revision != request.policy_revision:
        raise Conflict("recurrence_review_stale")
    definition = unit.tasks.definition(home, rule.definition_id)
    if definition is None:
        raise StorageFailure("invalid_recurrence_source")
    if rule.state is ScheduleState.RETIRED or definition.state is not DefinitionState.ACTIVE:
        raise Conflict("recurrence_state_change_unavailable")
    return current.revise(request.policy), JsonDocument.from_value(
        {
            "definition_id": definition.definition_id,
            "definition_revision": definition.revision,
            "previous_policy": current.policy.value,
            "missed_occurrence_policy": request.policy.value,
        }
    )
