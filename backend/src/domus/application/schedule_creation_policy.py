"""Bind scheduled creation to the current household's versioned time policy."""

from domus.application.ports import UnitOfWork
from domus.domain.errors import Conflict, Forbidden
from domus.domain.recurrence_time import TimePolicy


def schedule_creation_policy(unit: UnitOfWork, household_id: str, data_identity: str) -> TimePolicy:
    household = unit.households.get(household_id)
    if household is None:
        raise Forbidden("permission_denied")
    return TimePolicy(
        household.time_zone, data_identity, household.repeated_time, household.revision
    )


def require_schedule_creation_policy(
    unit: UnitOfWork, household_id: str, data_identity: str, expected: TimePolicy
) -> None:
    if schedule_creation_policy(unit, household_id, data_identity) != expected:
        raise Conflict("recurrence_review_stale")
