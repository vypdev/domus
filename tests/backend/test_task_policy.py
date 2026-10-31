"""Independent lifecycle tables and attribution rules protect claims and adult approval."""

from dataclasses import replace

import pytest

from domus.domain.errors import Conflict, InvalidInput
from domus.domain.identity import Role
from domus.domain.task_policy import (
    can_approve,
    claim_matches_task,
    next_definition_state,
    next_occurrence_state,
    reopened_state,
    require_completion_state,
    validate_dependency_graph,
    verification_required,
)
from domus.domain.task_values import DefinitionState as D
from domus.domain.task_values import OccurrenceState as O
from domus.domain.task_values import TaskPerformer, TaskRules, VerificationMode


@pytest.mark.parametrize("current", list(D))
@pytest.mark.parametrize("target", list(D))
def test_definition_transition_matrix(current: D, target: D) -> None:
    allowed = {
        ("draft", "active"),
        ("draft", "archived"),
        ("active", "paused"),
        ("active", "archived"),
        ("paused", "active"),
        ("paused", "archived"),
    }
    if (current.value, target.value) in allowed:
        assert next_definition_state(current, target) is target
    else:
        with pytest.raises(Conflict, match="task_transition_conflict"):
            next_definition_state(current, target)


@pytest.mark.parametrize("current", list(O))
@pytest.mark.parametrize("target", list(O))
def test_occurrence_graph_never_uses_generic_completion_or_reopen(current: O, target: O) -> None:
    normal = {
        "draft": {"available"},
        "available": {"assigned", "blocked"},
        "assigned": {"available", "in_progress", "blocked"},
        "in_progress": {"blocked"},
        "blocked": {"available", "assigned"},
    }
    expected = target.value in normal.get(current.value, set()) or (
        current.value in {"draft", "available", "assigned", "in_progress", "blocked"}
        and target.value in {"cancelled", "skipped"}
    )
    assignees = ("m",) if target in (O.ASSIGNED, O.IN_PROGRESS) else ()
    if expected:
        assert next_occurrence_state(current, target, assignees, "Explained") is target
    else:
        with pytest.raises(Conflict):
            next_occurrence_state(current, target, assignees, "Explained")


@pytest.mark.parametrize("current,target", [("active", D.PAUSED), (D.ACTIVE, "paused")])
def test_definition_strings_are_not_typed_states(current: object, target: object) -> None:
    with pytest.raises(InvalidInput):
        next_definition_state(current, target)


@pytest.mark.parametrize("current,target", [("available", O.ASSIGNED), (O.AVAILABLE, "assigned")])
def test_occurrence_strings_are_not_typed_states(current: object, target: object) -> None:
    with pytest.raises(InvalidInput):
        next_occurrence_state(current, target, ("m",))


@pytest.mark.parametrize(
    "current,target,ids",
    [
        (O.AVAILABLE, O.ASSIGNED, ()),
        (O.ASSIGNED, O.IN_PROGRESS, ()),
        (O.ASSIGNED, O.AVAILABLE, ("m",)),
    ],
)
def test_assignment_state_matches_actual_prospective_assignment(
    current: O, target: O, ids: tuple[str, ...]
) -> None:
    with pytest.raises(InvalidInput, match="invalid_task_assignment"):
        next_occurrence_state(current, target, ids)


@pytest.mark.parametrize("target", [O.BLOCKED, O.CANCELLED, O.SKIPPED])
def test_block_cancel_skip_require_a_real_reason(target: O) -> None:
    with pytest.raises(InvalidInput):
        next_occurrence_state(O.ASSIGNED, target, ("m",), " ")
    assert next_occurrence_state(O.ASSIGNED, target, ("m",), "Not possible\nReviewed") is target


def test_optional_transition_reason_is_still_bounded() -> None:
    assert next_occurrence_state(O.DRAFT, O.AVAILABLE, ()) is O.AVAILABLE
    assert next_occurrence_state(O.DRAFT, O.AVAILABLE, (), "x" * 1000) is O.AVAILABLE
    with pytest.raises(InvalidInput):
        next_occurrence_state(O.DRAFT, O.AVAILABLE, (), "x" * 1001)


@pytest.mark.parametrize("state", list(O))
def test_only_recordable_work_states_accept_dedicated_completion(state: O) -> None:
    if state in (O.AVAILABLE, O.ASSIGNED, O.IN_PROGRESS):
        require_completion_state(state)
    else:
        with pytest.raises(Conflict):
            require_completion_state(state)


def test_completion_and_reopen_reject_untyped_states_and_reopen_only_completed_work() -> None:
    with pytest.raises(InvalidInput):
        require_completion_state("available")
    with pytest.raises(InvalidInput):
        reopened_state("completed", ())
    for state in O:
        if state is not O.COMPLETED:
            with pytest.raises(Conflict):
                reopened_state(state, ())
    assert reopened_state(O.COMPLETED, ()) is O.AVAILABLE
    assert reopened_state(O.COMPLETED, ("m",)) is O.ASSIGNED


def test_owner_claim_default_is_profile_scoped_and_policy_can_disable_or_change_it() -> None:
    for role in Role:
        assert claim_matches_task(role, TaskRules()) is (role is not Role.VIEWER)
        assert not claim_matches_task(role, replace(TaskRules(), claim_allowed=False))
        assert claim_matches_task(role, replace(TaskRules(), eligible_roles=(Role.VIEWER,))) is (
            role is Role.VIEWER
        )
    with pytest.raises(InvalidInput):
        claim_matches_task("restricted", TaskRules())


def test_actual_performers_determine_verification_not_recording_actor() -> None:
    adult, child = TaskPerformer("adult", Role.ADULT), TaskPerformer("child", Role.RESTRICTED)
    assert not verification_required((adult,), TaskRules())
    assert verification_required((adult, child), TaskRules())
    assert verification_required((child,), TaskRules())
    assert verification_required(
        (adult,), replace(TaskRules(), verification=VerificationMode.ADULT)
    )
    assert verification_required((TaskPerformer("custom", Role.VIEWER),), TaskRules())


@pytest.mark.parametrize("role", list(Role))
@pytest.mark.parametrize("participated", [False, True])
@pytest.mark.parametrize("independent", [False, True])
def test_adult_participant_default_and_independent_alternative(
    role: Role, participated: bool, independent: bool
) -> None:
    approver = TaskPerformer("adult", role)
    performers = (TaskPerformer("adult" if participated else "other", Role.RESTRICTED),)
    assert can_approve(approver, performers, independent=independent) is (
        role in (Role.ADMINISTRATOR, Role.ADULT) and (not independent or not participated)
    )


def test_verification_cannot_accept_empty_performers_or_nonboolean_independence() -> None:
    with pytest.raises(InvalidInput):
        verification_required((), TaskRules())
    with pytest.raises(InvalidInput):
        can_approve(TaskPerformer("m", Role.ADULT), (), independent=False)
    with pytest.raises(InvalidInput):
        can_approve(
            TaskPerformer("m", Role.ADULT), (TaskPerformer("p", Role.RESTRICTED),), independent=1
        )


def test_empty_disconnected_and_shared_prerequisite_graphs_are_valid() -> None:
    validate_dependency_graph({})
    validate_dependency_graph({"a": (), "b": ("a",), "c": ("a",), "d": ("b", "c"), "e": ()})


@pytest.mark.parametrize(
    "graph",
    [
        {"a": ("a",)},
        {"a": ("missing",)},
        {"a": ("b",), "b": ("a",)},
        {"a": ("b",), "b": ("c",), "c": ("a",)},
        {"bad id": ()},
        {"a": ("b", "b"), "b": ()},
    ],
)
def test_unknown_duplicate_self_or_cyclic_dependencies_are_rejected(
    graph: dict[str, tuple[str, ...]],
) -> None:
    with pytest.raises(InvalidInput):
        validate_dependency_graph(graph)


def test_deep_graph_avoids_python_recursion_limit() -> None:
    graph = {str(i): (str(i - 1),) if i else () for i in range(3000)}
    validate_dependency_graph(graph)
    graph["0"] = ("2999",)
    with pytest.raises(InvalidInput, match="task_dependency_cycle"):
        validate_dependency_graph(graph)
