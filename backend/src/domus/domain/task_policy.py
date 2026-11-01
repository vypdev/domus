"""Pure task lifecycle and participation decisions; these rules never grant access."""

from collections.abc import Mapping

from domus.domain.errors import Conflict, InvalidInput
from domus.domain.identity import Role
from domus.domain.storage import validate_identifier
from domus.domain.task_values import (
    DefinitionState,
    DependencyGate,
    OccurrenceState,
    TaskPerformer,
    TaskRequirement,
    TaskRules,
    VerificationMode,
    VerificationState,
    validate_performers,
    validate_task_ids,
    validate_task_text,
)

_DEFINITION_NEXT = {
    DefinitionState.DRAFT: frozenset({DefinitionState.ACTIVE, DefinitionState.ARCHIVED}),
    DefinitionState.ACTIVE: frozenset({DefinitionState.PAUSED, DefinitionState.ARCHIVED}),
    DefinitionState.PAUSED: frozenset({DefinitionState.ACTIVE, DefinitionState.ARCHIVED}),
    DefinitionState.ARCHIVED: frozenset(),
}
_OCCURRENCE_NEXT = {
    OccurrenceState.DRAFT: frozenset({OccurrenceState.AVAILABLE}),
    OccurrenceState.AVAILABLE: frozenset({OccurrenceState.ASSIGNED, OccurrenceState.BLOCKED}),
    OccurrenceState.ASSIGNED: frozenset(
        {OccurrenceState.AVAILABLE, OccurrenceState.IN_PROGRESS, OccurrenceState.BLOCKED}
    ),
    OccurrenceState.IN_PROGRESS: frozenset({OccurrenceState.BLOCKED}),
    OccurrenceState.BLOCKED: frozenset({OccurrenceState.AVAILABLE, OccurrenceState.ASSIGNED}),
}


def next_definition_state(current: DefinitionState, target: DefinitionState) -> DefinitionState:
    if not isinstance(current, DefinitionState) or not isinstance(target, DefinitionState):
        raise InvalidInput("invalid_task_state")
    if target not in _DEFINITION_NEXT[current]:
        raise Conflict("task_transition_conflict")
    return target


def next_occurrence_state(
    current: OccurrenceState,
    target: OccurrenceState,
    assignees: tuple[str, ...],
    reason: str = "",
) -> OccurrenceState:
    """Validate a prospective assignment; completion and reopening have dedicated commands."""
    if not isinstance(current, OccurrenceState) or not isinstance(target, OccurrenceState):
        raise InvalidInput("invalid_task_state")
    validate_task_ids(assignees)
    ordinary = target in _OCCURRENCE_NEXT.get(current, ())
    terminal = current in _OCCURRENCE_NEXT and target in (
        OccurrenceState.CANCELLED,
        OccurrenceState.SKIPPED,
    )
    if not ordinary and not terminal:
        raise Conflict("task_transition_conflict")
    if (target in (OccurrenceState.ASSIGNED, OccurrenceState.IN_PROGRESS) and not assignees) or (
        target is OccurrenceState.AVAILABLE and assignees
    ):
        raise InvalidInput("invalid_task_assignment")
    validate_task_text(
        reason,
        1000,
        required=target
        in (OccurrenceState.BLOCKED, OccurrenceState.CANCELLED, OccurrenceState.SKIPPED),
        multiline=True,
    )
    return target


def require_completion_state(current: OccurrenceState) -> None:
    if not isinstance(current, OccurrenceState):
        raise InvalidInput("invalid_task_state")
    if current not in (
        OccurrenceState.AVAILABLE,
        OccurrenceState.ASSIGNED,
        OccurrenceState.IN_PROGRESS,
    ):
        raise Conflict("task_transition_conflict")


def reopened_state(current: OccurrenceState, assignees: tuple[str, ...]) -> OccurrenceState:
    if not isinstance(current, OccurrenceState):
        raise InvalidInput("invalid_task_state")
    validate_task_ids(assignees)
    if current is not OccurrenceState.COMPLETED:
        raise Conflict("task_transition_conflict")
    return OccurrenceState.ASSIGNED if assignees else OccurrenceState.AVAILABLE


def claim_matches_task(role: Role, rules: TaskRules) -> bool:
    """Profile/policy eligibility only; current claim permission and capacity are separate."""
    if not isinstance(role, Role):
        raise InvalidInput("invalid_task_performer")
    return rules.claim_allowed and role in rules.eligible_roles


def verification_required(performers: tuple[TaskPerformer, ...], rules: TaskRules) -> bool:
    validate_performers(performers)
    return rules.verification is VerificationMode.ADULT or any(
        performer.role not in (Role.ADMINISTRATOR, Role.ADULT) for performer in performers
    )


def can_approve(
    approver: TaskPerformer, performers: tuple[TaskPerformer, ...], *, independent: bool
) -> bool:
    """Participation rule only; application must also require current adult approval authority."""
    validate_performers(performers)
    if type(independent) is not bool:
        raise InvalidInput("invalid_task_rules")
    return approver.role in (Role.ADMINISTRATOR, Role.ADULT) and (
        not independent
        or all(approver.member_id != performer.member_id for performer in performers)
    )


def requirements_satisfied(requirements: tuple[TaskRequirement, ...], gate: DependencyGate) -> bool:
    """Evaluate an explicit mode without selecting a household or task default."""
    if (
        not isinstance(gate, DependencyGate)
        or type(requirements) is not tuple
        or any(not isinstance(item, TaskRequirement) for item in requirements)
    ):
        raise InvalidInput("invalid_task_requirement")
    validate_task_ids(tuple(item.occurrence_id for item in requirements), maximum=64)
    return all(
        item.state is OccurrenceState.COMPLETED
        and item.verification is not VerificationState.REJECTED
        and (
            gate is DependencyGate.PERFORMED
            or item.verification in (VerificationState.NONE, VerificationState.APPROVED)
        )
        for item in requirements
    )


def validate_dependency_graph(graph: Mapping[str, tuple[str, ...]]) -> None:
    """Validate the combined prerequisite/subtask graph without recursive stack growth.

    Application must first resolve every node within the current household transaction.
    A graph edge names a required occurrence; completing work does not mutate this graph.
    """
    remaining = dict.fromkeys(graph, 0)
    dependents: dict[str, list[str]] = {node: [] for node in graph}
    for node, requirements in graph.items():
        validate_identifier(node)
        validate_task_ids(requirements, maximum=64)
        for required in requirements:
            if required == node or required not in remaining:
                raise InvalidInput("invalid_task_dependency")
            remaining[node] += 1
            dependents[required].append(node)
    ready = [node for node, count in remaining.items() if count == 0]
    visited = 0
    while ready:
        node = ready.pop()
        visited += 1
        for dependent in dependents[node]:
            remaining[dependent] -= 1
            if remaining[dependent] == 0:
                ready.append(dependent)
    if visited != len(graph):
        raise InvalidInput("task_dependency_cycle")
