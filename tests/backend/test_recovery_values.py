"""Recovery is target-bound, short-lived and cannot reopen a completed approval."""

from dataclasses import replace

import pytest

from domus.domain.errors import Conflict, InvalidInput
from domus.domain.identity import (
    AdministratorMapping,
    HouseholdPolicy,
    MappingMode,
    Member,
    MemberStatus,
    Role,
)
from domus.domain.recovery import RecoveryRequest, RecoveryState
from domus.domain.storage import Installation

INSTALLATION = Installation("047cc6fb-dfb0-4fa4-b3c3-e0fe54d116b6", "edge")
MAPPING = AdministratorMapping(MappingMode.SETUP, "lost_admin")
POLICY = HouseholdPolicy("home", MAPPING, 2)


def request() -> RecoveryRequest:
    return RecoveryRequest(
        "request", "home", "ha_new", INSTALLATION, MAPPING, 2, None, 0, 1000, 601000
    )


def test_recovery_approval_has_absolute_deadline_and_atomic_single_use_transitions() -> None:
    pending = request()
    assert pending.state is RecoveryState.PENDING and pending.revision == 1
    pending.require_current(INSTALLATION, POLICY, None)
    approved = pending.approve(2000)
    assert approved.expires_at == 602000 and approved.approved_at == 2000
    assert approved.revision == 2 and approved.visible_state(3000) == "approved"
    consumed = approved.consume(3000)
    assert consumed.state is RecoveryState.CONSUMED and consumed.revision == 3
    assert consumed.closed_at == 3000 and consumed.visible_state(900000) == "consumed"
    with pytest.raises(Conflict, match="recovery_not_pending"):
        approved.approve(3000)
    with pytest.raises(Conflict, match="recovery_not_approved"):
        pending.consume(3000)
    with pytest.raises(Conflict, match="recovery_not_approved"):
        consumed.consume(4000)
    with pytest.raises(Conflict, match="recovery_closed"):
        consumed.cancel(4000)


@pytest.mark.parametrize(
    "approved,now",
    [(False, 601000), (False, 700000), (False, 999), (True, 602000), (True, 700000), (True, 1999)],
)
def test_recovery_cannot_approve_or_complete_outside_its_fixed_phase_window(
    approved: bool, now: int
) -> None:
    value = request().approve(2000) if approved else request()
    assert value.visible_state(now) == "expired"
    with pytest.raises(Conflict, match="recovery_expired"):
        value.consume(now) if approved else value.approve(now)


@pytest.mark.parametrize("approved", [False, True])
def test_owner_can_cancel_pending_or_approved_request_even_after_expiry(approved: bool) -> None:
    value = request().approve(2000) if approved else request()
    canceled = value.cancel(900000)
    assert canceled.visible_state(900001) == "canceled"
    assert canceled.revision == value.revision + 1
    with pytest.raises(Conflict, match="recovery_closed"):
        canceled.cancel(900001)


@pytest.mark.parametrize(
    "field,value",
    [
        ("request_id", "bad id"),
        ("household_id", ""),
        ("target_ha_user_id", "bad id"),
        ("installation", None),
        ("mapping", AdministratorMapping(MappingMode.ALL)),
        ("policy_revision", 0),
        ("member_id", "bad id"),
        ("member_revision", 1),
        ("created_at", True),
        ("created_at", -1),
        ("created_at", 2**63),
        ("expires_at", 601001),
        ("state", "pending"),
        ("revision", 2),
        ("approved_at", 2000),
        ("closed_at", 2000),
    ],
)
def test_invalid_recovery_value_cannot_be_persisted(field: str, value: object) -> None:
    with pytest.raises(InvalidInput):
        replace(request(), **{field: value})


@pytest.mark.parametrize(
    "change",
    [
        {"approved_at": 999},
        {"approved_at": 601000},
        {"approved_at": True},
        {"closed_at": 3000},
        {"revision": 1},
    ],
)
def test_approved_record_requires_consistent_time_and_state(change: dict) -> None:
    with pytest.raises(InvalidInput):
        replace(request().approve(2000), **change)


@pytest.mark.parametrize(
    "change", [{"closed_at": None}, {"closed_at": 1999}, {"closed_at": 602000}, {"revision": 2}]
)
def test_consumed_record_cannot_fabricate_completion(change: dict) -> None:
    with pytest.raises(InvalidInput):
        replace(request().approve(2000).consume(3000), **change)


def test_member_and_policy_binding_detects_retargeting_or_stale_revision() -> None:
    member = Member("member", "home", "ha_new", Role.VIEWER, MemberStatus.PENDING, 1)
    bound = replace(request(), member_id="member", member_revision=1)
    bound.require_current(INSTALLATION, POLICY, member)
    for installation, policy, person in [
        (Installation(INSTALLATION.instance_id, "stable"), POLICY, member),
        (INSTALLATION, None, member),
        (INSTALLATION, replace(POLICY, revision=3), member),
        (INSTALLATION, replace(POLICY, household_id="other"), member),
        (
            INSTALLATION,
            replace(POLICY, mapping=AdministratorMapping(MappingMode.SELECTED, "other")),
            member,
        ),
        (INSTALLATION, POLICY, None),
        (INSTALLATION, POLICY, replace(member, revision=2)),
        (INSTALLATION, POLICY, replace(member, ha_user_id="other")),
        (INSTALLATION, POLICY, replace(member, household_id="other")),
    ]:
        with pytest.raises(Conflict, match="recovery_binding_changed"):
            bound.require_current(installation, policy, person)
    with pytest.raises(InvalidInput):
        replace(request(), member_id="member", member_revision=0)


def test_cancellation_rejects_time_before_the_request_was_created() -> None:
    with pytest.raises(Conflict, match="recovery_expired"):
        request().cancel(999)
