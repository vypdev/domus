"""Closed wire inputs for the manual adoption review."""

from typing import Annotated, Literal

from pydantic import Field

from domus.application.recurrence_review import ManualAdoption, ReviewedChange
from domus.application.relative_state_review import RelativeStateChange
from domus.domain.recurrence_records import ScheduleState
from domus.entrypoints.http_contract import StrictModel
from domus.entrypoints.task_dto import Identifier, Revision


class ManualAdoptionBody(StrictModel):
    schedule_id: Identifier
    schedule_revision: Revision
    occurrence_id: Identifier
    occurrence_revision: Revision

    def selection(self) -> ManualAdoption:
        return ManualAdoption(
            self.schedule_id, self.schedule_revision, self.occurrence_id, self.occurrence_revision
        )


class ReviewedAdoptionBody(ManualAdoptionBody):
    preview_key: Identifier
    plan_fingerprint: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]

    def reviewed(self) -> ReviewedChange:
        return ReviewedChange(self.selection(), self.preview_key, self.plan_fingerprint)


class RelativeStateBody(StrictModel):
    schedule_id: Identifier
    schedule_revision: Revision
    target: Literal["active", "paused"]

    def selection(self) -> RelativeStateChange:
        return RelativeStateChange(
            self.schedule_id, self.schedule_revision, ScheduleState(self.target)
        )


class ReviewedStateBody(RelativeStateBody):
    preview_key: Identifier
    plan_fingerprint: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]

    def reviewed(self) -> ReviewedChange:
        return ReviewedChange(self.selection(), self.preview_key, self.plan_fingerprint)
