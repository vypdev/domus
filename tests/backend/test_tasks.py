"""Task records preserve scope, immutable work snapshots and cycle-bound decisions."""

from dataclasses import FrozenInstanceError, replace

import pytest

from domus.domain.errors import Conflict, Forbidden, InvalidInput
from domus.domain.identity import Role
from domus.domain.task_values import (
    DefinitionState,
    DependencyGate,
    OccurrenceState,
    TaskContent,
    TaskOverrides,
    TaskPerformer,
    TaskRequirement,
    TaskRules,
    VerificationState,
)
from domus.domain.tasks import HouseholdTaskPolicy, TaskCycle, TaskDefinition, TaskOccurrence


def definition(**changes: object) -> TaskDefinition:
    return replace(TaskDefinition("definition", "home", TaskContent("Wipe table"), 10), **changes)


def occurrence(**changes: object) -> TaskOccurrence:
    return replace(definition().new_occurrence("occurrence", 20), **changes)


def cycle(**changes: object) -> TaskCycle:
    result = TaskCycle.record(
        "cycle",
        "home",
        "occurrence",
        recorded_by="adult",
        performers=(TaskPerformer("adult", Role.ADULT),),
        rules=TaskRules(),
        definition_revision=1,
        task_policy_revision=1,
        identity_policy_revision=1,
        performed_at=30,
        recorded_at=40,
    )
    return replace(result, **changes)


def restricted_cycle(**changes: object) -> TaskCycle:
    result = TaskCycle.record(
        "cycle",
        "home",
        "occurrence",
        recorded_by="adult",
        performers=(TaskPerformer("child", Role.RESTRICTED),),
        rules=TaskRules(),
        definition_revision=1,
        task_policy_revision=1,
        identity_policy_revision=1,
        performed_at=30,
        recorded_at=40,
    )
    return replace(result, **changes)


def test_definition_changes_never_rewrite_the_existing_occurrence_snapshot() -> None:
    first = definition()
    work = first.new_occurrence("occurrence", 20)
    changed = first.revise(
        TaskContent("Different title"), TaskOverrides(point_value_minor=100), DefinitionState.PAUSED
    )
    assert changed.revision == 2 and changed.state is DefinitionState.PAUSED
    assert work.definition_snapshot is first
    assert work.definition_snapshot.content.title == "Wipe table"
    assert work.definition_snapshot.overrides.point_value_minor is None
    archived = changed.revise(changed.content, changed.overrides, DefinitionState.ARCHIVED)
    assert archived.revision == 3 and work.state is OccurrenceState.AVAILABLE
    renamed = first.revise(TaskContent("Renamed"), first.overrides, first.state)
    assert renamed.state is DefinitionState.ACTIVE and renamed.revision == 2
    with pytest.raises(FrozenInstanceError):
        first.content = TaskContent("Mutation")


def test_definition_edits_require_change_and_archived_is_terminal() -> None:
    original = definition()
    with pytest.raises(Conflict, match="task_unchanged"):
        original.revise(original.content, original.overrides, original.state)
    archived = definition(state=DefinitionState.ARCHIVED)
    with pytest.raises(Conflict):
        archived.revise(TaskContent("Edit"), archived.overrides, archived.state)
    with pytest.raises(Conflict):
        original.revise(original.content, original.overrides, DefinitionState.DRAFT)


def test_initial_occurrence_state_matches_definition_and_assignment() -> None:
    assert definition().new_occurrence("one", 20).state is OccurrenceState.AVAILABLE
    assigned = definition().new_occurrence("two", 20, assignees=("member",))
    assert assigned.state is OccurrenceState.ASSIGNED and assigned.assignee_ids == ("member",)
    draft = definition(state=DefinitionState.DRAFT)
    assert draft.new_occurrence("three", 20).state is OccurrenceState.DRAFT
    with pytest.raises(InvalidInput):
        draft.new_occurrence("four", 20, assignees=("member",))
    for state in (DefinitionState.PAUSED, DefinitionState.ARCHIVED):
        with pytest.raises(Conflict, match="task_definition_unavailable"):
            definition(state=state).new_occurrence("another", 20)


@pytest.mark.parametrize(
    "changes",
    [
        {"definition_id": "bad id"},
        {"household_id": "bad id"},
        {"content": "Title"},
        {"overrides": {}},
        {"state": "active"},
        {"revision": 0},
        {"created_at": True},
    ],
)
def test_definition_rejects_untrusted_or_unversioned_records(changes: dict[str, object]) -> None:
    with pytest.raises(InvalidInput):
        definition(**changes)


def test_household_defaults_and_override_snapshots_remain_separate() -> None:
    policy = HouseholdTaskPolicy("home", TaskRules())
    changed = policy.revise(replace(policy.rules, claim_allowed=False))
    assert changed.revision == 2 and not changed.rules.claim_allowed
    inherited = definition().overrides
    assert not inherited.resolve(changed.rules).claim_allowed
    assert TaskOverrides(claim_allowed=True).resolve(changed.rules).claim_allowed
    with pytest.raises(Conflict, match="task_unchanged"):
        policy.revise(policy.rules)


@pytest.mark.parametrize(
    "values", [("bad id", TaskRules(), 1), ("home", {}, 1), ("home", TaskRules(), 0)]
)
def test_household_task_policy_is_typed_and_versioned(values: tuple[object, ...]) -> None:
    with pytest.raises(InvalidInput):
        HouseholdTaskPolicy(*values)


@pytest.mark.parametrize(
    "changes",
    [
        {"occurrence_id": "bad id"},
        {"household_id": "other"},
        {"definition_snapshot": "definition"},
        {"state": "available"},
        {"revision": True},
        {"created_at": 9},
        {"due_at": True},
        {"prerequisite_ids": ("occurrence",)},
        {"required_subtask_ids": ("occurrence",)},
        {"current_cycle_id": "cycle"},
        {"current_cycle_id": "bad id"},
        {"state": OccurrenceState.COMPLETED},
        {"state": OccurrenceState.ASSIGNED},
        {"state": OccurrenceState.IN_PROGRESS},
        {"assignee_ids": ("member",)},
        {"state": OccurrenceState.BLOCKED},
        {"state_reason": "bad\x00"},
    ],
)
def test_occurrence_shape_cannot_claim_completion_or_assignment_without_its_facts(
    changes: dict[str, object],
) -> None:
    with pytest.raises(InvalidInput):
        occurrence(**changes)


def test_due_time_and_dependencies_preserve_their_exact_identity() -> None:
    work = occurrence(prerequisite_ids=("before",), required_subtask_ids=("child",), due_at=0)
    assert work.due_at == 0 and work.prerequisite_ids == ("before",)
    assert work.required_subtask_ids == ("child",)


def test_assignment_and_release_are_explicit_and_do_not_clear_block_reasons() -> None:
    work = occurrence().assign(("child",))
    assert work.state is OccurrenceState.ASSIGNED and work.revision == 2
    started = work.transition(OccurrenceState.IN_PROGRESS)
    reassigned = started.assign(("adult",))
    assert reassigned.state is OccurrenceState.IN_PROGRESS and reassigned.revision == 4
    with pytest.raises(InvalidInput):
        started.assign(())
    blocked = started.transition(OccurrenceState.BLOCKED, "No supplies")
    released = blocked.assign(())
    assert released.state is OccurrenceState.BLOCKED and released.state_reason == "No supplies"
    available = released.transition(OccurrenceState.AVAILABLE)
    assert available.state is OccurrenceState.AVAILABLE and available.state_reason == ""
    assert work.assign(()).state is OccurrenceState.AVAILABLE
    with pytest.raises(Conflict, match="task_unchanged"):
        work.assign(work.assignee_ids)
    with pytest.raises(Conflict):
        definition(state=DefinitionState.DRAFT).new_occurrence("draft", 20).assign(("member",))


def test_completion_requires_exact_real_required_set_and_explicit_gate() -> None:
    work = occurrence(prerequisite_ids=("before",), required_subtask_ids=("child",))
    requirements = (
        TaskRequirement("before", OccurrenceState.COMPLETED, VerificationState.PENDING),
        TaskRequirement("child", OccurrenceState.COMPLETED, VerificationState.NONE),
    )
    with pytest.raises(Conflict, match="task_dependencies_incomplete"):
        work.complete(
            cycle(rules=replace(TaskRules(), dependency_gate=DependencyGate.APPROVED)),
            requirements=requirements,
        )
    completed = work.complete(cycle(), requirements=requirements)
    assert completed.state is OccurrenceState.COMPLETED and completed.current_cycle_id == "cycle"
    assert completed.revision == 2
    for wrong in [
        (),
        requirements[:1],
        requirements + (TaskRequirement("extra", OccurrenceState.AVAILABLE),),
    ]:
        with pytest.raises(InvalidInput, match="invalid_task_requirement"):
            work.complete(cycle(), requirements=wrong)
    with pytest.raises(Conflict):
        completed.complete(cycle(), requirements=requirements)


@pytest.mark.parametrize(
    "changes",
    [
        {"household_id": "other"},
        {"occurrence_id": "other"},
        {"definition_revision": 2},
        {"closed_at": 40},
        {"recorded_at": 15, "performed_at": 15},
    ],
)
def test_completion_cannot_attach_a_foreign_closed_or_precreation_cycle(
    changes: dict[str, object],
) -> None:
    with pytest.raises(InvalidInput):
        occurrence().complete(cycle(**changes), requirements=())


def test_actual_performers_drive_verification_and_policy_changes_do_not_waive_a_pending_cycle() -> (
    None
):
    saved = restricted_cycle()
    assert saved.verification is VerificationState.PENDING and saved.recorded_by == "adult"
    assert saved.performers == (TaskPerformer("child", Role.RESTRICTED),)
    assert saved.rules.adult_performer_may_approve
    assert (
        saved.definition_revision
        == saved.task_policy_revision
        == saved.identity_policy_revision
        == 1
    )
    assert saved.rules == TaskRules() and saved.performed_at == 30 and saved.recorded_at == 40
    with pytest.raises(InvalidInput):
        replace(saved, verification=VerificationState.NONE)


def test_approval_preserves_open_cycle_and_requires_a_current_adult_participation_rule() -> None:
    saved = restricted_cycle()
    approved = saved.verify(VerificationState.APPROVED, TaskPerformer("adult", Role.ADULT), 50)
    assert approved.verification is VerificationState.APPROVED and approved.verified_at == 50
    assert approved.closed_at is None and approved.revision == 2
    with pytest.raises(Forbidden):
        saved.verify(VerificationState.APPROVED, TaskPerformer("child", Role.RESTRICTED), 50)
    collaborative = replace(
        saved, performers=(*saved.performers, TaskPerformer("adult", Role.ADULT))
    )
    assert collaborative.verify(VerificationState.APPROVED, TaskPerformer("adult", Role.ADULT), 50)
    independent = replace(
        collaborative, rules=replace(saved.rules, adult_performer_may_approve=False)
    )
    with pytest.raises(Forbidden):
        independent.verify(VerificationState.APPROVED, TaskPerformer("adult", Role.ADULT), 50)
    assert independent.verify(VerificationState.APPROVED, TaskPerformer("other", Role.ADULT), 50)


def test_rejection_retains_work_and_old_cycle_requires_explicit_reopen() -> None:
    saved = restricted_cycle()
    with pytest.raises(InvalidInput):
        saved.verify(VerificationState.REJECTED, TaskPerformer("adult", Role.ADULT), 50)
    rejected = saved.verify(
        VerificationState.REJECTED, TaskPerformer("adult", Role.ADULT), 50, "Incomplete work"
    )
    assert rejected.performers == saved.performers and rejected.performed_at == saved.performed_at
    assert rejected.closed_at is None and rejected.verification is VerificationState.REJECTED
    with pytest.raises(Conflict):
        rejected.verify(VerificationState.APPROVED, TaskPerformer("adult", Role.ADULT), 60)
    with pytest.raises(InvalidInput):
        saved.verify(VerificationState.NONE, TaskPerformer("adult", Role.ADULT), 50)
    with pytest.raises(InvalidInput):
        saved.verify(VerificationState.APPROVED, "adult", 50)


def test_reopening_closes_only_the_named_cycle_and_retains_its_fact_snapshot() -> None:
    saved = restricted_cycle()
    work = occurrence().assign(("child",)).complete(saved, requirements=())
    updated, approved = work.verify(
        saved, VerificationState.APPROVED, TaskPerformer("adult", Role.ADULT), 50
    )
    reopened, closed = updated.reopen(approved, 60, "Review the result")
    assert reopened.state is OccurrenceState.ASSIGNED and reopened.current_cycle_id is None
    assert closed.closed_at == 60 and closed.performers == saved.performers
    assert closed.verification is VerificationState.APPROVED and closed.verified_at == 50
    assert reopened.revision == 5 and closed.revision == 3
    with pytest.raises(Conflict):
        closed.verify(VerificationState.APPROVED, TaskPerformer("adult", Role.ADULT), 70)
    with pytest.raises(Conflict):
        closed.close(70)
    with pytest.raises(Conflict):
        reopened.reopen(closed, 70, "Again")
    with pytest.raises(InvalidInput):
        updated.reopen(approved, 60, " ")
    with pytest.raises(InvalidInput):
        updated.reopen(replace(approved, cycle_id="other"), 60, "Wrong cycle")
    new_cycle = replace(saved, cycle_id="new", recorded_at=70, performed_at=65)
    again = reopened.complete(new_cycle, requirements=())
    with pytest.raises(InvalidInput):
        again.verify(closed, VerificationState.APPROVED, TaskPerformer("adult", Role.ADULT), 80)


def test_reopen_without_assignees_returns_available_and_keeps_completed_work() -> None:
    saved = cycle()
    work = occurrence().complete(saved, requirements=())
    reopened, closed = work.reopen(saved, 50, "Repeat work")
    assert reopened.state is OccurrenceState.AVAILABLE and closed.closed_at == 50
    assert work.state is OccurrenceState.COMPLETED and work.current_cycle_id == "cycle"
    with pytest.raises(Conflict):
        work.assign(("other",))


@pytest.mark.parametrize(
    "changes",
    [
        {"cycle_id": "bad id"},
        {"recorded_by": "bad id"},
        {"rules": {}},
        {"definition_revision": 0},
        {"task_policy_revision": True},
        {"identity_policy_revision": 0},
        {"revision": 0},
        {"performed_at": -1},
        {"performed_at": 41},
        {"recorded_at": True},
        {"verification": "none"},
        {"verified_at": 50},
        {"verified_by": TaskPerformer("adult", Role.ADULT)},
        {"verification_reason": "Unexpected"},
        {"closed_at": 39},
        {"closed_at": True},
    ],
)
def test_malformed_cycle_is_not_safe_restoration_input(changes: dict[str, object]) -> None:
    with pytest.raises(InvalidInput):
        cycle(**changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"verified_at": None},
        {"verified_by": None},
        {"verified_by": "adult"},
        {"verified_at": 39},
        {"closed_at": 49},
        {"verified_by": TaskPerformer("child", Role.RESTRICTED)},
    ],
)
def test_approved_record_needs_consistent_adult_decision_and_time(
    changes: dict[str, object],
) -> None:
    saved = restricted_cycle().verify(
        VerificationState.APPROVED, TaskPerformer("adult", Role.ADULT), 50
    )
    with pytest.raises(InvalidInput):
        replace(saved, **changes)


def test_cycle_revision_and_current_pointer_must_match_before_deciding_or_reopening() -> None:
    saved = restricted_cycle()
    work = occurrence().complete(saved, requirements=())
    updated, approved = work.verify(
        saved, VerificationState.APPROVED, TaskPerformer("adult", Role.ADULT), 50
    )
    assert updated.current_cycle_revision == 2
    with pytest.raises(InvalidInput):
        updated.reopen(saved, 60, "Stale cycle revision")
    with pytest.raises(InvalidInput):
        occurrence().verify(
            saved, VerificationState.APPROVED, TaskPerformer("adult", Role.ADULT), 50
        )
    with pytest.raises(InvalidInput):
        work.verify("bad cycle", VerificationState.APPROVED, TaskPerformer("adult", Role.ADULT), 50)
    with pytest.raises(InvalidInput):
        occurrence().complete("bad cycle", requirements=())
    with pytest.raises(InvalidInput):
        replace(updated, current_cycle_revision=True)
    with pytest.raises(InvalidInput):
        occurrence(current_cycle_revision=1)
    assert approved.closed_at is None


def test_untyped_decision_and_precreation_definition_snapshot_are_rejected() -> None:
    saved = restricted_cycle()
    with pytest.raises(InvalidInput):
        saved.verify("approved", TaskPerformer("adult", Role.ADULT), 50)
    for state in (DefinitionState.PAUSED, DefinitionState.ARCHIVED):
        with pytest.raises(InvalidInput):
            occurrence(definition_snapshot=definition(state=state))
