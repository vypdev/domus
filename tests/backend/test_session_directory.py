"""Server-owned session adapters never expose or substitute the delegated human grant."""

from dataclasses import replace

import pytest
from test_standalone_sessions import fixture, sign_in

from domus.application.sessions import SessionGuard
from domus.domain.errors import Forbidden, IdentityRejected, Unauthenticated
from domus.domain.identity import HumanIdentity
from domus.infrastructure.session_access import SessionActor, SessionDirectory

TARGET = "b" * 32


def adapters() -> tuple:
    identity, oauth, socket, clock = fixture()
    lease = sign_in(identity)
    calls = []

    def directory(token: str, users: tuple[str, ...]) -> tuple[HumanIdentity, ...]:
        calls.append((token, users))
        return tuple(HumanIdentity(user, False, True, False) for user in users)

    socket.directory_users = directory
    return identity, oauth, socket, clock, lease, calls


def test_private_directory_and_actor_share_exact_original_session() -> None:
    identity, _, _, clock, lease, calls = adapters()
    actor = SessionActor(SessionGuard(identity, identity, clock), lease.session_id)
    directory = SessionDirectory(identity, lease.session_id)
    assert actor.read() == actor.current() == lease.human
    assert directory.get(TARGET).ha_user_id == TARGET
    assert calls == [("private-access", (TARGET,))]
    assert directory.eligible(()) == ()
    assert len(calls) == 1
    assert lease.session_id not in repr(actor) and lease.session_id not in repr(directory)
    assert "private-access" not in repr(directory)


def test_expired_or_logged_out_session_never_performs_a_directory_lookup() -> None:
    identity, _, _, clock, lease, calls = adapters()
    directory = SessionDirectory(identity, lease.session_id)
    clock.value = lease.expires_at
    with pytest.raises(Unauthenticated):
        directory.get(TARGET)
    assert calls == []
    with pytest.raises(Unauthenticated):
        directory.eligible((TARGET,))
    assert calls == []


def test_missing_target_does_not_remove_the_requesting_human_session() -> None:
    identity, _, socket, _, lease, _ = adapters()
    socket.directory_users = lambda *_: ()
    with pytest.raises(IdentityRejected, match="ha_subject_rejected"):
        SessionDirectory(identity, lease.session_id).get(TARGET)
    assert identity.get(lease.session_id) is not None


def test_directory_uses_refreshed_private_token_without_changing_original_deadline() -> None:
    identity, _, _, clock, lease, calls = adapters()
    clock.value += 1_770_000
    assert SessionDirectory(identity, lease.session_id).get(TARGET).ha_user_id == TARGET
    assert calls == [("renewed-access", (TARGET,))]
    assert identity.get(lease.session_id).expires_at == lease.expires_at


def test_logout_during_directory_lookup_prevents_returning_old_proof() -> None:
    identity, _, socket, _, lease, _ = adapters()

    def directory(*_: object) -> tuple[HumanIdentity, ...]:
        identity.remove(lease.session_id)
        return (HumanIdentity(TARGET, False, True, False),)

    socket.directory_users = directory
    with pytest.raises(IdentityRejected, match="session_changed"):
        SessionDirectory(identity, lease.session_id).get(TARGET)


def test_directory_permission_failure_is_not_a_human_role_or_session_rejection() -> None:
    identity, _, socket, _, lease, _ = adapters()

    def denied(*_: object) -> None:
        raise Forbidden("ha_directory_forbidden")

    socket.directory_users = denied
    with pytest.raises(Forbidden):
        SessionDirectory(identity, lease.session_id).eligible((TARGET,))
    assert identity.get(lease.session_id) is not None


def test_changed_source_identity_cannot_use_the_previous_users_private_directory() -> None:
    identity, _, socket, _, lease, calls = adapters()
    socket.human = replace(socket.human, ha_user_id="c" * 32)
    with pytest.raises(IdentityRejected, match="identity_mismatch"):
        SessionDirectory(identity, lease.session_id).get(TARGET)
    assert calls == [] and identity.get(lease.session_id) is None


def test_logout_immediately_after_actor_proof_blocks_directory_preparation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity, _, _, _, lease, calls = adapters()
    original = SessionGuard.write

    def proof_then_logout(guard: SessionGuard, session_id: str) -> HumanIdentity:
        human = original(guard, session_id)
        identity.remove(session_id)
        return human

    monkeypatch.setattr(SessionGuard, "write", proof_then_logout)
    with pytest.raises(IdentityRejected, match="session_changed"):
        SessionDirectory(identity, lease.session_id).get(TARGET)
    assert calls == []


def test_logout_while_waiting_for_credential_gate_cannot_reuse_the_selected_grant() -> None:
    identity, _, _, _, lease, calls = adapters()

    class InterleavedGate:
        entered = 0

        def __enter__(self) -> None:
            self.entered += 1
            if self.entered == 2:
                identity.remove(lease.session_id)

        def __exit__(self, *_: object) -> None:
            pass

    record = identity._credentials[lease.session_id]
    identity._credentials[lease.session_id] = replace(record, gate=InterleavedGate())
    with pytest.raises(IdentityRejected, match="session_changed"):
        SessionDirectory(identity, lease.session_id).get(TARGET)
    assert calls == [] and identity.get(lease.session_id) is None


def test_expiry_during_directory_lookup_erases_local_access_and_discards_the_result() -> None:
    identity, _, socket, clock, lease, _ = adapters()

    def slow_lookup(*_: object) -> tuple[HumanIdentity, ...]:
        clock.value = lease.expires_at
        return (HumanIdentity(TARGET, False, True, False),)

    socket.directory_users = slow_lookup
    with pytest.raises(IdentityRejected, match="session_expired"):
        SessionDirectory(identity, lease.session_id).get(TARGET)
    assert identity.get(lease.session_id) is None
    assert lease.session_id not in identity._credentials
