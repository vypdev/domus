"""Common strict wire models are separate from application and domain records."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

PositiveRevision = Annotated[
    int,
    Field(
        ge=1,
        le=2**63 - 1,
        json_schema_extra={"minimum": 1, "maximum": 2**63 - 1, "format": "int64"},
    ),
]
NonnegativeRevision = Annotated[
    int,
    Field(
        ge=0,
        le=2**63 - 1,
        json_schema_extra={"minimum": 0, "maximum": 2**63 - 1, "format": "int64"},
    ),
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, from_attributes=True)


class ErrorResponse(StrictModel):
    state: Literal["blocked"]
    code: str
    message: str
    action_required: str
    correlation_id: str
