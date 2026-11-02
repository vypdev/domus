"""Private grants and original leases fence metadata through logout and refresh races."""

from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_standalone_sessions import fixture as identity_fixture
from test_standalone_sessions import sign_in

from domus.application.sessions import SessionGuard
from domus.domain.errors import IdentityRejected, IdentityUnavailable, Unauthenticated
from domus.domain.member_sources import (
    HAProfile,
    MemberSourceSnapshot,
    ProfileDirectory,
    ProfileResult,
    SourceState,
)
from domus.infrastructure import session_access, standalone_sessions


def fixture(monkeypatch):
    identity, oauth, socket, clock = identity_fixture()
    lease = sign_in(identity)
    calls = []
    event = SimpleNamespace(callback=lambda: None)

    def source(lookup, token, subject, grant):
        assert lookup is socket and token == grant.access_token
        calls.append((token, subject))

        def read():
            event.callback()
            return MemberSourceSnapshot(
                subject,
                ProfileDirectory(SourceState.DENIED),
                ProfileResult(SourceState.AVAILABLE, HAProfile(subject, "Own", True)),
            )

        return SimpleNamespace(read=read)

    monkeypatch.setattr(standalone_sessions, "HomeAssistantMemberProfiles", source, raising=False)
    return identity, oauth, socket, clock, lease, calls, event


def test_source_uses_exact_original_private_session_and_refreshed_grant(monkeypatch):
    identity, _, _, clock, lease, calls, _ = fixture(monkeypatch)
    source = session_access.SessionMemberProfiles(identity, lease.session_id)
    assert source.read().own.profile.name == "Own"
    clock.value += 1_770_000
    assert source.read().subject == lease.human.ha_user_id
    assert calls == [
        ("private-access", lease.human.ha_user_id),
        ("renewed-access", lease.human.ha_user_id),
    ]
    assert identity.get(lease.session_id).expires_at == lease.expires_at
    assert lease.session_id not in repr(source) and "private-access" not in repr(source)


@pytest.mark.parametrize("change", ["expired", "logout", "unknown"])
def test_missing_or_expired_session_cannot_trigger_metadata_lookup(monkeypatch, change):
    identity, _, _, clock, lease, calls, _ = fixture(monkeypatch)
    session = lease.session_id
    if change == "expired":
        clock.value = lease.expires_at
    elif change == "logout":
        identity.remove(session)
    else:
        session = "unknown"
    with pytest.raises(Unauthenticated):
        identity.member_sources(session)
    assert calls == []


@pytest.mark.parametrize("change", ["logout", "expiry"])
def test_metadata_returning_after_retirement_cannot_restore_private_facts(monkeypatch, change):
    identity, _, _, clock, lease, _, event = fixture(monkeypatch)
    event.callback = (
        (lambda: identity.remove(lease.session_id))
        if change == "logout"
        else (lambda: setattr(clock, "value", lease.expires_at))
    )
    with pytest.raises(IdentityRejected, match="session_changed|session_expired"):
        identity.member_sources(lease.session_id)
    assert identity.get(lease.session_id) is None and lease.session_id not in identity._credentials


def test_read_grace_is_retained_without_becoming_fresh_mutation_proof(monkeypatch):
    identity, _, socket, clock, lease, calls, _ = fixture(monkeypatch)
    socket.error = IdentityUnavailable("ha_unavailable")
    assert identity.member_sources(lease.session_id).subject == lease.human.ha_user_id
    assert len(calls) == 1 and identity.get(lease.session_id).expires_at == lease.expires_at
    with pytest.raises(IdentityUnavailable):
        SessionGuard(identity, identity, clock).write(lease.session_id)


def test_subject_change_fails_before_accessing_the_old_private_grant(monkeypatch):
    identity, _, socket, _, lease, calls, _ = fixture(monkeypatch)
    socket.human = replace(socket.human, ha_user_id="b" * 32)
    with pytest.raises(IdentityRejected, match="identity_mismatch"):
        identity.member_sources(lease.session_id)
    assert calls == []


def test_logout_after_read_proof_blocks_credential_preparation(monkeypatch):
    identity, _, _, _, lease, calls, _ = fixture(monkeypatch)
    original = SessionGuard.read

    def then_logout(guard, session):
        human = original(guard, session)
        identity.remove(session)
        return human

    monkeypatch.setattr(SessionGuard, "read", then_logout)
    with pytest.raises(IdentityRejected, match="session_changed"):
        identity.member_sources(lease.session_id)
    assert calls == []
