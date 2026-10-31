"""Common strict wire models are separate from application and domain records."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, from_attributes=True)


class ErrorResponse(StrictModel):
    state: Literal["blocked"]
    code: str
    message: str
    action_required: str
    correlation_id: str
