"""Absolute session leases never turn unavailability into authority or a renewed login."""

from collections.abc import Callable
from dataclasses import replace

import pytest

from domus.application.session_values import SessionLease
from domus.application.sessions import SessionGuard
from domus.domain.errors import (
    Conflict,
    IdentityRejected,
    IdentityUnavailable,
    InvalidInput,
    Unauthenticated,
)
from domus.domain.identity import HumanIdentity
from domus.infrastructure.memory_sessions import MemorySessions

HUMAN = HumanIdentity("ha_1", True, True, False)
ORDINARY = replace(HUMAN, is_administrator=False)


class Clock:
    value = 100

    def now(self) -> int:
        return self.value


class Verifier:
    def __init__(self) -> None:
        self.result = HUMAN
        self.error: Exception | None = None
        self.callback: Callable[[], None] = lambda: None
        self.calls = 0

    def prove(self, session_id: str) -> HumanIdentity:
        self.calls += 1
        self.callback()
        if self.error:
            raise self.error
        return self.result


def fixture() -> tuple[SessionGuard, MemorySessions, Verifier, Clock]:
    sessions, verifier, clock = MemorySessions(), Verifier(), Clock()
    sessions.add(SessionLease("session_1", HUMAN, 0, 200))
    return SessionGuard(sessions, verifier, clock), sessions, verifier, clock


@pytest.mark.parametrize(
    "started,expires",
    [(0, 0), (100, 99), (-1, 100), (True, 100), (0, True), (0, 28_800_001), (0, 2**63)],
)
def test_lease_has_strict_bounded_monotonic_lifetime(started: object, expires: object) -> None:
    with pytest.raises(InvalidInput, match="invalid_session_lease"):
        SessionLease("session_1", HUMAN, started, expires)


def test_lease_requires_eligible_identity() -> None:
    with pytest.raises(InvalidInput, match="invalid_session_lease"):
        SessionLease("session_1", "ha_1", 0, 100)
    assert SessionLease("session_1", HUMAN, 0, 28_800_000).expires_at == 28_800_000


def test_session_handle_is_omitted_from_diagnostic_representation() -> None:
    assert "private-session-handle" not in repr(
        SessionLease("private-session-handle", HUMAN, 0, 100)
    )


def test_every_fresh_read_and_write_reproves_exact_subject_without_extending_expiry() -> None:
    guard, sessions, verifier, _ = fixture()
    assert guard.read("session_1") == HUMAN
    verifier.result = ORDINARY
    assert guard.write("session_1") == ORDINARY
    assert verifier.calls == 2
    assert sessions.get("session_1") == SessionLease("session_1", ORDINARY, 0, 200)


def test_outage_read_uses_latest_proof_but_write_is_blocked_without_extension() -> None:
    guard, sessions, verifier, _ = fixture()
    verifier.result = ORDINARY
    assert guard.read("session_1") == ORDINARY
    verifier.error = IdentityUnavailable("ha_unavailable")
    assert guard.read("session_1") == ORDINARY
    with pytest.raises(IdentityUnavailable, match="ha_unavailable"):
        guard.write("session_1")
    assert sessions.get("session_1").expires_at == 200


def test_session_status_distinguishes_fresh_proof_from_bounded_read_grace() -> None:
    guard, _, verifier, _ = fixture()
    status = guard.status("session_1")
    assert status.human == HUMAN and status.fresh and status.expires_at == 200
    verifier.error = IdentityUnavailable("ha_unavailable")
    status = guard.status("session_1")
    assert status.human == HUMAN and not status.fresh and status.expires_at == 200


@pytest.mark.parametrize("time", [-1, 200, 201])
def test_missing_expired_and_backwards_clock_leases_cannot_invoke_provider(time: int) -> None:
    guard, sessions, verifier, clock = fixture()
    clock.value = time
    with pytest.raises(Unauthenticated, match="session_expired"):
        guard.read("session_1")
    assert sessions.get("session_1") is None
    with pytest.raises(Unauthenticated, match="session_required"):
        guard.write("session_1")
    assert verifier.calls == 0


@pytest.mark.parametrize("outage", [False, True])
def test_expiry_during_provider_io_cannot_return_either_fresh_or_outage_access(
    outage: bool,
) -> None:
    guard, sessions, verifier, clock = fixture()
    verifier.callback = lambda: setattr(clock, "value", 200)
    if outage:
        verifier.error = IdentityUnavailable("ha_unavailable")
    with pytest.raises(Unauthenticated, match="session_expired"):
        guard.read("session_1")
    assert sessions.get("session_1") is None


def test_explicit_ha_rejection_revokes_session_and_cannot_fall_back_on_next_outage() -> None:
    guard, sessions, verifier, _ = fixture()
    verifier.error = IdentityRejected("ha_rejected")
    with pytest.raises(IdentityRejected):
        guard.read("session_1")
    assert sessions.get("session_1") is None
    verifier.error = IdentityUnavailable("ha_unavailable")
    with pytest.raises(Unauthenticated, match="session_required"):
        guard.read("session_1")


def test_mismatched_fresh_identity_is_rejected_and_destroys_original_session() -> None:
    guard, sessions, verifier, _ = fixture()
    verifier.result = replace(HUMAN, ha_user_id="ha_2")
    with pytest.raises(IdentityRejected, match="identity_mismatch"):
        guard.write("session_1")
    assert sessions.get("session_1") is None


@pytest.mark.parametrize("outage", [False, True])
def test_logout_during_proof_is_not_resurrected_by_late_result(outage: bool) -> None:
    guard, sessions, verifier, _ = fixture()
    verifier.callback = lambda: sessions.remove("session_1")
    if outage:
        verifier.error = IdentityUnavailable("ha_unavailable")
    with pytest.raises(Unauthenticated, match="session_changed"):
        guard.read("session_1")
    assert sessions.get("session_1") is None


def test_concurrent_changed_identity_cannot_be_overwritten_by_stale_proof() -> None:
    guard, sessions, verifier, _ = fixture()
    original = sessions.get("session_1")
    verifier.callback = lambda: sessions.refresh(original, ORDINARY)
    with pytest.raises(Unauthenticated, match="session_changed"):
        guard.write("session_1")
    assert sessions.get("session_1").human == ORDINARY


def test_memory_store_capacity_duplicate_and_cleanup_keep_active_leases() -> None:
    sessions = MemorySessions(max_sessions=1)
    lease = SessionLease("session_1", HUMAN, 0, 100)
    sessions.add(lease)
    with pytest.raises(Conflict, match="session_exists"):
        sessions.add(lease)
    with pytest.raises(IdentityUnavailable, match="session_capacity"):
        sessions.add(replace(lease, session_id="session_2"))
    assert sessions.discard_expired(99) == 0
    assert sessions.discard_expired(100) == 1
    sessions.add(replace(lease, session_id="session_2", started_at=100, expires_at=200))
    assert sessions.get("session_2") is not None


def test_refresh_preserves_deadline_and_cannot_retarget_an_identity() -> None:
    sessions = MemorySessions()
    lease = SessionLease("session_1", HUMAN, 0, 100)
    sessions.add(lease)
    with pytest.raises(InvalidInput, match="identity_mismatch"):
        sessions.refresh(lease, replace(HUMAN, ha_user_id="ha_2"))
    assert sessions.get("session_1") == lease
    assert sessions.refresh(lease, ORDINARY)
    assert not sessions.refresh(lease, HUMAN)
    sessions.remove("session_1")
    assert not sessions.refresh(lease, HUMAN)
    sessions.remove("session_1")


@pytest.mark.parametrize("capacity", [0, -1, True, 1025])
def test_session_store_capacity_is_bounded(capacity: object) -> None:
    with pytest.raises(InvalidInput, match="invalid_session_capacity"):
        MemorySessions(max_sessions=capacity)
