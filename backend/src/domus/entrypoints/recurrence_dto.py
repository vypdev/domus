"""Closed wire inputs for the manual adoption review."""

from typing import Annotated

from pydantic import Field

from domus.application.recurrence_review import ManualAdoption, ReviewedAdoption
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

    def reviewed(self) -> ReviewedAdoption:
        return ReviewedAdoption(self.selection(), self.preview_key, self.plan_fingerprint)
