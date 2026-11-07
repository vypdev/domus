"""Closed wire inputs for the manual adoption review."""

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import Field

from domus.application.fixed_skip_review import FixedSkip
from domus.application.fixed_state_review import FixedStateChange
from domus.application.recurrence_review import ManualAdoption, ReviewedChange
from domus.application.relative_attachment_review import AttachmentChoice, AttachRelative
from domus.application.relative_state_review import RelativeSettings, RelativeStateChange
from domus.application.reschedule_review import RescheduleSelection
from domus.domain.errors import InvalidInput
from domus.domain.recurrence_records import ScheduleState
from domus.domain.recurrence_rules import NominalDate, NominalSlot
from domus.domain.recurrence_time import FoldPolicy, NominalTime, RelativeInterval
from domus.domain.relative_recurrence import SuccessorVisibility
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


class FixedSkipBody(StrictModel):
    schedule_id: Identifier
    schedule_revision: Revision
    slot_key: Identifier
    occurrence_id: Identifier
    occurrence_revision: Revision
    reason: Annotated[str, Field(min_length=1, max_length=1000)]

    def selection(self) -> FixedSkip:
        return FixedSkip(
            self.schedule_id,
            self.schedule_revision,
            self.slot_key,
            self.occurrence_id,
            self.occurrence_revision,
            self.reason,
        )


class ReviewedFixedSkipBody(FixedSkipBody):
    preview_key: Identifier
    plan_fingerprint: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]

    def reviewed(self) -> ReviewedChange:
        return ReviewedChange(self.selection(), self.preview_key, self.plan_fingerprint)


class NominalDateBody(StrictModel):
    kind: Literal["date"]
    local: Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")]


class NominalTimeBody(StrictModel):
    kind: Literal["time"]
    local: Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d{1,3})?)?$")]


NominalBody = Annotated[NominalDateBody | NominalTimeBody, Field(discriminator="kind")]


def nominal(body: NominalBody) -> NominalSlot:
    try:
        if isinstance(body, NominalDateBody):
            return NominalDate(date.fromisoformat(body.local))
        return NominalTime(datetime.fromisoformat(body.local))
    except ValueError:
        raise InvalidInput("invalid_recurrence_local_time") from None


class RelativeAttachmentBody(StrictModel):
    definition_id: Identifier
    definition_revision: Revision
    occurrence_id: Identifier
    occurrence_revision: Revision
    initial: NominalBody
    interval_days: Annotated[int, Field(ge=1, le=36600)]
    zone: Annotated[str, Field(min_length=1, max_length=128)]
    repeated_time: Literal["first_instant", "second_instant"] = "first_instant"
    visibility: Literal["at_completion", "at_verification"] = "at_completion"
    choice: Literal["adopt", "retain_manual"]

    def selection(self) -> AttachRelative:
        return AttachRelative(
            self.definition_id,
            self.definition_revision,
            self.occurrence_id,
            self.occurrence_revision,
            nominal(self.initial),
            RelativeInterval(self.interval_days),
            self.zone,
            FoldPolicy(self.repeated_time),
            SuccessorVisibility(self.visibility),
            AttachmentChoice(self.choice),
        )


class ReviewedRelativeAttachmentBody(RelativeAttachmentBody):
    preview_key: Identifier
    plan_fingerprint: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]

    def reviewed(self) -> ReviewedChange:
        return ReviewedChange(self.selection(), self.preview_key, self.plan_fingerprint)


class RelativeSettingsBody(StrictModel):
    schedule_id: Identifier
    schedule_revision: Revision
    interval_days: Annotated[int, Field(ge=1, le=36600)]
    visibility: Literal["at_completion", "at_verification"]

    def selection(self) -> RelativeSettings:
        return RelativeSettings(
            self.schedule_id,
            self.schedule_revision,
            RelativeInterval(self.interval_days),
            SuccessorVisibility(self.visibility),
        )


class ReviewedRelativeSettingsBody(RelativeSettingsBody):
    preview_key: Identifier
    plan_fingerprint: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]

    def reviewed(self) -> ReviewedChange:
        return ReviewedChange(self.selection(), self.preview_key, self.plan_fingerprint)


class RescheduleBody(FixedSkipBody):
    destination: NominalBody

    def move(self) -> RescheduleSelection:
        return RescheduleSelection(
            self.schedule_id,
            self.schedule_revision,
            self.slot_key,
            self.occurrence_id,
            self.occurrence_revision,
            nominal(self.destination),
            self.reason,
        )


class ReviewedRescheduleBody(RescheduleBody):
    preview_key: Identifier
    plan_fingerprint: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]

    def reviewed(self) -> ReviewedChange:
        return ReviewedChange(self.move(), self.preview_key, self.plan_fingerprint)


class FixedStateBody(StrictModel):
    schedule_id: Identifier
    schedule_revision: Revision
    target: Literal["active", "paused"]

    def selection(self) -> FixedStateChange:
        return FixedStateChange(
            self.schedule_id, self.schedule_revision, ScheduleState(self.target)
        )


class ReviewedFixedStateBody(FixedStateBody):
    preview_key: Identifier
    plan_fingerprint: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]

    def reviewed(self) -> ReviewedChange:
        return ReviewedChange(self.selection(), self.preview_key, self.plan_fingerprint)
