"""Strict bounded task wire values map to transport-independent application requests."""

import re
from typing import Annotated, Literal

from pydantic import BeforeValidator, Field

from domus.domain.identity import Role
from domus.domain.task_material_values import MaterialQuantity, MaterialSelection, MaterialUsage
from domus.domain.task_values import (
    DefinitionState,
    DependencyGate,
    MaterialRecording,
    OccurrenceState,
    Priority,
    TaskContent,
    TaskOverrides,
    TaskRules,
    VerificationMode,
    VerificationState,
)
from domus.entrypoints.http_contract import StrictModel

Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")]
Revision = Annotated[int, Field(ge=1, le=2**63 - 1)]
TaskTime = Annotated[int, Field(ge=0, le=2**63 - 1)]
WireRole = Annotated[Role, Field(strict=False)]
Quantity = Annotated[
    str,
    Field(min_length=1, max_length=19, pattern=r"^(?:0|[1-9][0-9]{0,11})(?:\.[0-9]{0,5}[1-9])?$"),
]


def _query_integer(value: object) -> object:
    if isinstance(value, str):
        if not re.fullmatch(r"[1-9][0-9]{0,2}", value):
            raise ValueError("invalid_page_size")
        return int(value)
    return value


class PageQuery(StrictModel):
    limit: Annotated[int, BeforeValidator(_query_integer)] = Field(default=25, ge=1, le=100)
    cursor: str | None = Field(default=None, min_length=1, max_length=512)


class DefinitionsQuery(PageQuery):
    state: DefinitionState | None = Field(default=None, strict=False)


class OccurrencesQuery(PageQuery):
    state: OccurrenceState | None = Field(default=None, strict=False)
    assignee_id: Identifier | None = None
    definition_id: Identifier | None = None


class MaterialsQuery(StrictModel):
    cycle_id: Identifier


class MaterialSelectionBody(StrictModel):
    reference_id: Identifier
    planned_quantity: Quantity

    def domain(self) -> MaterialSelection:
        return MaterialSelection(self.reference_id, MaterialQuantity(self.planned_quantity))


class MaterialUsageBody(StrictModel):
    line_id: Identifier
    quantity: Quantity

    def domain(self) -> MaterialUsage:
        return MaterialUsage(self.line_id, MaterialQuantity(self.quantity))


class ContentBody(StrictModel):
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=4000)
    priority: Priority = Field(default=Priority.NORMAL, strict=False)
    tags: list[Annotated[str, Field(min_length=1, max_length=64)]] = Field(
        default_factory=list, max_length=16
    )
    materials: list[MaterialSelectionBody] | None = Field(default=None, max_length=32)

    def content(self) -> TaskContent:
        return TaskContent(self.title, self.description, self.priority, tuple(self.tags))

    def selections(self) -> tuple[MaterialSelection, ...] | None:
        return None if self.materials is None else tuple(value.domain() for value in self.materials)


class OverridesBody(StrictModel):
    claim_allowed: bool | None = None
    eligible_roles: list[WireRole] | None = Field(default=None, max_length=4)
    verification: VerificationMode | None = Field(default=None, strict=False)
    adult_performer_may_approve: bool | None = None
    task_scoped_material_consumption: bool | None = None
    material_recording: MaterialRecording | None = Field(default=None, strict=False)
    point_value_minor: int | None = Field(default=None, ge=0, le=1_000_000)
    dependency_gate: DependencyGate | None = Field(default=None, strict=False)

    def domain(self) -> TaskOverrides:
        return TaskOverrides(
            self.claim_allowed,
            None if self.eligible_roles is None else tuple(self.eligible_roles),
            self.verification,
            self.adult_performer_may_approve,
            self.task_scoped_material_consumption,
            self.material_recording,
            self.point_value_minor,
            self.dependency_gate,
        )


class RulesBody(StrictModel):
    claim_allowed: bool = True
    eligible_roles: list[WireRole] = Field(
        default_factory=lambda: [Role.ADMINISTRATOR, Role.ADULT, Role.RESTRICTED], max_length=4
    )
    verification: VerificationMode = Field(default=VerificationMode.ROLE_DEFAULT, strict=False)
    adult_performer_may_approve: bool = True
    task_scoped_material_consumption: bool = True
    material_recording: MaterialRecording = Field(
        default=MaterialRecording.REVIEW_ON_COMPLETION, strict=False
    )
    point_value_minor: int = Field(default=0, ge=0, le=1_000_000)
    dependency_gate: DependencyGate = Field(default=DependencyGate.PERFORMED, strict=False)

    def domain(self) -> TaskRules:
        return TaskRules(
            self.claim_allowed,
            tuple(self.eligible_roles),
            self.verification,
            self.adult_performer_may_approve,
            self.task_scoped_material_consumption,
            self.material_recording,
            self.point_value_minor,
            self.dependency_gate,
        )


class CreateDefinitionBody(ContentBody):
    expected_revision: int = Field(default=0, ge=0, le=0)
    state: Literal["draft", "active"] = "active"
    overrides: OverridesBody = Field(default_factory=OverridesBody)


class UpdateDefinitionBody(ContentBody):
    expected_revision: Revision
    state: DefinitionState = Field(strict=False)
    overrides: OverridesBody | None = None


class PolicyBody(StrictModel):
    expected_revision: int = Field(ge=0, le=2**63 - 1)
    rules: RulesBody


class CreateOccurrenceBody(StrictModel):
    expected_revision: int = Field(default=0, ge=0, le=0)
    assignee_ids: list[Identifier] = Field(default_factory=list, max_length=32)
    prerequisite_ids: list[Identifier] = Field(default_factory=list, max_length=32)
    required_subtask_ids: list[Identifier] = Field(default_factory=list, max_length=32)
    due_at: TaskTime | None = None


class OccurrenceBody(StrictModel):
    expected_revision: Revision


class AssignmentBody(OccurrenceBody):
    assignee_ids: list[Identifier] = Field(max_length=32)


class DependenciesBody(OccurrenceBody):
    prerequisite_ids: list[Identifier] = Field(default_factory=list, max_length=32)
    required_subtask_ids: list[Identifier] = Field(default_factory=list, max_length=32)


class TransitionBody(OccurrenceBody):
    target: OccurrenceState = Field(strict=False)
    reason: str = Field(default="", max_length=1000)


class CompleteBody(OccurrenceBody):
    performer_ids: list[Identifier] = Field(min_length=1, max_length=32)
    performed_at: TaskTime
    material_usages: list[MaterialUsageBody] | None = Field(default=None, max_length=32)

    def usages(self) -> tuple[MaterialUsage, ...] | None:
        return (
            None
            if self.material_usages is None
            else tuple(value.domain() for value in self.material_usages)
        )


class VerifyBody(OccurrenceBody):
    cycle_id: Identifier
    decision: VerificationState = Field(strict=False)
    reason: str = Field(default="", max_length=1000)


class ReopenBody(OccurrenceBody):
    cycle_id: Identifier
    reason: str = Field(min_length=1, max_length=1000)
