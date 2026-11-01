"""Immutable task inputs and policy values; construction does not prove authority."""

from dataclasses import dataclass
from enum import StrEnum

from domus.domain.errors import Conflict, InvalidInput
from domus.domain.identity import Role, validate_revision
from domus.domain.storage import validate_identifier


class DefinitionState(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class OccurrenceState(StrEnum):
    DRAFT = "draft"
    AVAILABLE = "available"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


class Priority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class VerificationMode(StrEnum):
    ROLE_DEFAULT = "role_default"
    ADULT = "authorized_adult"


class MaterialRecording(StrEnum):
    REVIEW_ON_COMPLETION = "review_on_completion"
    SEPARATE = "separate_recording"


class VerificationState(StrEnum):
    NONE = "none"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class DependencyGate(StrEnum):
    PERFORMED = "performed"
    APPROVED = "approved"


def validate_task_text(
    value: str, maximum: int, *, required: bool, multiline: bool = False
) -> None:
    if (
        not isinstance(value, str)
        or len(value) > maximum
        or (required and not value.strip())
        or any(
            (ord(char) < 32 and (not multiline or char not in "\t\n\r")) or ord(char) == 127
            for char in value
        )
    ):
        raise InvalidInput("invalid_task_text")
    try:
        value.encode("utf-8")
    except UnicodeError:
        raise InvalidInput("invalid_task_text") from None


def validate_task_ids(values: tuple[str, ...], *, maximum: int = 32) -> None:
    if (
        type(maximum) is not int
        or maximum not in (32, 64)
        or type(values) is not tuple
        or len(values) > maximum
    ):
        raise InvalidInput("invalid_task_ids")
    for value in values:
        validate_identifier(value)
    if len(set(values)) != len(values):
        raise InvalidInput("invalid_task_ids")


def validate_task_time(value: int) -> None:
    if type(value) is not int or not 0 <= value <= 2**63 - 1:
        raise InvalidInput("invalid_task_time")


def next_task_revision(value: int) -> int:
    validate_revision(value)
    if value == 2**63 - 1:
        raise Conflict("task_revision_exhausted")
    return value + 1


@dataclass(frozen=True, slots=True)
class TaskContent:
    title: str
    description: str = ""
    priority: Priority = Priority.NORMAL
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        validate_task_text(self.title, 160, required=True)
        validate_task_text(self.description, 4000, required=False, multiline=True)
        if not isinstance(self.priority, Priority):
            raise InvalidInput("invalid_task_priority")
        if type(self.tags) is not tuple or len(self.tags) > 16:
            raise InvalidInput("invalid_task_tags")
        for tag in self.tags:
            validate_task_text(tag, 64, required=True)
        if len(set(self.tags)) != len(self.tags):
            raise InvalidInput("invalid_task_tags")


@dataclass(frozen=True, slots=True)
class TaskRules:
    """Resolved task policy; current human and member grants are checked separately."""

    claim_allowed: bool = True
    eligible_roles: tuple[Role, ...] = (Role.ADMINISTRATOR, Role.ADULT, Role.RESTRICTED)
    verification: VerificationMode = VerificationMode.ROLE_DEFAULT
    adult_performer_may_approve: bool = True
    task_scoped_material_consumption: bool = True
    material_recording: MaterialRecording = MaterialRecording.REVIEW_ON_COMPLETION
    point_value_minor: int = 0
    dependency_gate: DependencyGate = DependencyGate.PERFORMED

    def __post_init__(self) -> None:
        if (
            type(self.claim_allowed) is not bool
            or type(self.adult_performer_may_approve) is not bool
            or type(self.task_scoped_material_consumption) is not bool
            or type(self.eligible_roles) is not tuple
            or len(self.eligible_roles) > len(Role)
            or any(not isinstance(role, Role) for role in self.eligible_roles)
            or len(set(self.eligible_roles)) != len(self.eligible_roles)
            or not isinstance(self.verification, VerificationMode)
            or not isinstance(self.material_recording, MaterialRecording)
            or type(self.point_value_minor) is not int
            or not 0 <= self.point_value_minor <= 1_000_000
            or not isinstance(self.dependency_gate, DependencyGate)
        ):
            raise InvalidInput("invalid_task_rules")


@dataclass(frozen=True, slots=True)
class TaskOverrides:
    """None inherits; explicit false, zero and an empty tuple remain real overrides."""

    claim_allowed: bool | None = None
    eligible_roles: tuple[Role, ...] | None = None
    verification: VerificationMode | None = None
    adult_performer_may_approve: bool | None = None
    task_scoped_material_consumption: bool | None = None
    material_recording: MaterialRecording | None = None
    point_value_minor: int | None = None
    dependency_gate: DependencyGate | None = None

    def __post_init__(self) -> None:
        self.resolve(TaskRules())

    def resolve(self, defaults: TaskRules) -> TaskRules:
        return TaskRules(
            defaults.claim_allowed if self.claim_allowed is None else self.claim_allowed,
            defaults.eligible_roles if self.eligible_roles is None else self.eligible_roles,
            defaults.verification if self.verification is None else self.verification,
            defaults.adult_performer_may_approve
            if self.adult_performer_may_approve is None
            else self.adult_performer_may_approve,
            defaults.task_scoped_material_consumption
            if self.task_scoped_material_consumption is None
            else self.task_scoped_material_consumption,
            defaults.material_recording
            if self.material_recording is None
            else self.material_recording,
            defaults.point_value_minor
            if self.point_value_minor is None
            else self.point_value_minor,
            defaults.dependency_gate if self.dependency_gate is None else self.dependency_gate,
        )


@dataclass(frozen=True, slots=True)
class TaskPerformer:
    """Member/role facts supplied by application proof, snapshotted at completion."""

    member_id: str
    role: Role

    def __post_init__(self) -> None:
        validate_identifier(self.member_id)
        if not isinstance(self.role, Role):
            raise InvalidInput("invalid_task_performer")


def validate_performers(performers: tuple[TaskPerformer, ...]) -> None:
    if (
        type(performers) is not tuple
        or not 1 <= len(performers) <= 32
        or any(not isinstance(performer, TaskPerformer) for performer in performers)
    ):
        raise InvalidInput("invalid_task_performers")
    validate_task_ids(tuple(performer.member_id for performer in performers))


@dataclass(frozen=True, slots=True)
class TaskRequirement:
    """A current required occurrence resolved by the household-scoped application query."""

    occurrence_id: str
    state: OccurrenceState
    verification: VerificationState | None = None

    def __post_init__(self) -> None:
        validate_identifier(self.occurrence_id)
        if (
            not isinstance(self.state, OccurrenceState)
            or (
                self.state is OccurrenceState.COMPLETED
                and not isinstance(self.verification, VerificationState)
            )
            or (self.state is not OccurrenceState.COMPLETED and self.verification is not None)
        ):
            raise InvalidInput("invalid_task_requirement")
