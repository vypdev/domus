"""Private OAuth sessions bind credentials to leases and erase/revoke only owned grants."""

from dataclasses import replace
from threading import Event, Lock, Thread, current_thread
from urllib.parse import parse_qs, urlsplit

import pytest

from domus.application.session_values import SessionLease
from domus.application.sessions import SessionGuard
from domus.domain.errors import Conflict, IdentityRejected, IdentityUnavailable, InvalidInput
from domus.domain.identity import HumanIdentity
from domus.infrastructure.ha_config import HAEndpoint, OAuthConfiguration
from domus.infrastructure.ha_http import OAuthTokens
from domus.infrastructure.memory_sessions import MemorySessions
from domus.infrastructure.standalone_sessions import StandaloneIdentity

HUMAN = HumanIdentity("a" * 32, False, True, False)
TOKENS = OAuthTokens("private-access", "private-refresh", 1800, "homeassistant")


class Clock:
    value = 100

    def now(self) -> int:
        return self.value


class OAuth:
    def __init__(self) -> None:
        self.configuration = OAuthConfiguration(
            HAEndpoint("http://ha.local"), "https://domus.example"
        )
        self.issued = TOKENS
        self.refreshed = replace(TOKENS, access_token="renewed-access")
        self.revoke_error = None
        self.revoked = []
        self.refreshes = 0

    def exchange(self, code: str, verifier: str) -> OAuthTokens:
        assert code == "code" and verifier == "v" * 43
        return self.issued

    def refresh(self, token: str, provider: str) -> OAuthTokens:
        assert token == TOKENS.refresh_token and provider == TOKENS.provider
        self.refreshes += 1
        return self.refreshed

    def revoke(self, token: str) -> None:
        self.revoked.append(token)
        if self.revoke_error:
            raise self.revoke_error


class Socket:
    endpoint = HAEndpoint("http://ha.local")

    def __init__(self) -> None:
        self.human = HUMAN
        self.error = None
        self.tokens = []
        self.callback = lambda: None

    def current_user(self, tokens: OAuthTokens) -> HumanIdentity:
        self.callback()
        self.tokens.append(tokens.access_token)
        if self.error:
            raise self.error
        return self.human


def fixture(capacity: int = 256) -> tuple[StandaloneIdentity, OAuth, Socket, Clock]:
    oauth, socket, clock = OAuth(), Socket(), Clock()
    return (
        StandaloneIdentity(oauth, socket, clock, MemorySessions(max_sessions=capacity)),
        oauth,
        socket,
        clock,
    )


def sign_in(provider: StandaloneIdentity, key: str = "session_1") -> SessionLease:
    return provider.sign_in("code", "v" * 43, key, 100, 3_600_100)


def test_authorization_url_has_only_fixed_client_callback_state_and_s256() -> None:
    provider, _, _, _ = fixture()
    url = urlsplit(provider.authorization_url("s" * 43, "c" * 43))
    assert url.scheme == "http" and url.netloc == "ha.local" and url.path == "/auth/authorize"
    assert parse_qs(url.query) == {
        "client_id": ["https://domus.example/"],
        "redirect_uri": ["https://domus.example/api/v1/auth/callback"],
        "state": ["s" * 43],
        "code_challenge": ["c" * 43],
        "code_challenge_method": ["S256"],
    }
    with pytest.raises(InvalidInput):
        provider.authorization_url("bad", "c" * 43)


def test_sign_in_reproves_each_request_and_refreshes_without_extending_lease() -> None:
    provider, oauth, socket, clock = fixture()
    lease = sign_in(provider)
    assert provider.get("session_1") == lease
    guard = SessionGuard(provider, provider, clock)
    assert guard.read("session_1") == HUMAN
    socket.human = replace(HUMAN, is_administrator=True)
    clock.value = 1_770_100
    assert guard.write("session_1").is_administrator
    assert oauth.refreshes == 1
    assert socket.tokens[-1] == "renewed-access"
    assert provider.get("session_1").expires_at == lease.expires_at
    assert "private-access" not in repr(provider) and "private-refresh" not in repr(provider)


def test_logout_clears_local_lease_and_revokes_only_that_ha_grant() -> None:
    provider, oauth, _, _ = fixture()
    sign_in(provider)
    assert provider.sign_out("session_1") is True
    assert provider.get("session_1") is None
    assert oauth.revoked == ["private-refresh"]
    assert provider.sign_out("session_1") is None
    with pytest.raises(IdentityRejected, match="session_required"):
        provider.prove("session_1")


def test_failed_remote_revoke_retains_local_logout_and_sanitized_diagnostic(
    caplog: pytest.LogCaptureFixture,
) -> None:
    provider, oauth, _, _ = fixture()
    sign_in(provider)
    oauth.revoke_error = IdentityUnavailable("ha_unavailable")
    assert not provider.sign_out("session_1")
    assert provider.get("session_1") is None
    assert "ha_grant_cleanup_unavailable" in caplog.text
    assert "private-refresh" not in caplog.text


def test_failed_proof_or_full_capacity_never_retains_new_grant() -> None:
    provider, oauth, socket, _ = fixture(capacity=1)
    sign_in(provider)
    with pytest.raises(IdentityUnavailable, match="session_capacity"):
        sign_in(provider, "session_2")
    assert provider.get("session_2") is None
    assert oauth.revoked == ["private-refresh"]
    socket.error = IdentityRejected("ha_rejected")
    with pytest.raises(IdentityRejected):
        sign_in(provider, "session_3")
    assert provider.get("session_3") is None
    assert len(oauth.revoked) == 2


def test_duplicate_session_cannot_replace_old_credentials() -> None:
    provider, oauth, _, _ = fixture()
    original = sign_in(provider)
    with pytest.raises(Conflict, match="session_exists"):
        sign_in(provider)
    assert provider.get("session_1") == original
    assert oauth.revoked == []


def test_rejected_fresh_proof_destroys_lease_and_cannot_use_outage_later() -> None:
    provider, _, socket, clock = fixture()
    sign_in(provider)
    guard = SessionGuard(provider, provider, clock)
    socket.error = IdentityRejected("ha_rejected")
    with pytest.raises(IdentityRejected):
        guard.read("session_1")
    assert provider.get("session_1") is None
    socket.error = IdentityUnavailable("ha_unavailable")
    with pytest.raises(IdentityRejected, match="session_required"):
        provider.prove("session_1")


def test_expired_sessions_and_credentials_are_pruned_before_new_sign_in() -> None:
    provider, _, _, clock = fixture(capacity=1)
    sign_in(provider)
    clock.value = 3_600_100
    provider.sign_in("code", "v" * 43, "session_2", clock.value, clock.value + 3_600_000)
    assert provider.get("session_1") is None
    assert provider.get("session_2") is not None


def test_lease_that_expires_during_initial_proof_is_not_installed() -> None:
    provider, oauth, socket, clock = fixture()
    socket.callback = lambda: setattr(clock, "value", 3_600_100)
    with pytest.raises(IdentityRejected, match="session_expired"):
        sign_in(provider)
    assert provider.get("session_1") is None
    assert oauth.revoked == ["private-refresh"]


def test_logout_during_proof_does_not_resurrect_private_credentials() -> None:
    provider, _, socket, _ = fixture()
    sign_in(provider)
    socket.callback = lambda: provider.remove("session_1")
    with pytest.raises(IdentityRejected, match="session_changed"):
        provider.prove("session_1")
    assert provider.get("session_1") is None


def test_already_waiting_proof_rechecks_removed_session_before_using_credentials() -> None:
    provider, _, socket, _ = fixture()
    sign_in(provider)
    entered, waiting, release = Event(), Event(), Event()

    class NotifyingGate:
        def __init__(self) -> None:
            self.lock = Lock()

        def __enter__(self) -> None:
            if current_thread().name == "second":
                waiting.set()
            self.lock.acquire()

        def __exit__(self, *exception: object) -> None:
            self.lock.release()

    # Observe the waiting boundary without relying on scheduler timing or sleeps.
    original = provider._credentials["session_1"]
    provider._credentials["session_1"] = replace(original, gate=NotifyingGate())

    def held_proof() -> None:
        entered.set()
        assert release.wait(timeout=3)

    socket.callback = held_proof
    results = []

    def prove() -> None:
        try:
            results.append(provider.prove("session_1"))
        except IdentityRejected as error:
            results.append(error.code)

    first = Thread(target=prove, name="first")
    second = Thread(target=prove, name="second")
    first.start()
    assert entered.wait(timeout=3)
    second.start()
    assert waiting.wait(timeout=3)
    provider.remove("session_1")
    release.set()
    first.join(timeout=3)
    second.join(timeout=3)
    assert not first.is_alive() and not second.is_alive()
    assert len(results) == 2 and all(isinstance(result, str) for result in results)


def test_standalone_clients_must_share_the_same_operator_endpoint() -> None:
    oauth, socket, clock = OAuth(), Socket(), Clock()
    socket.endpoint = HAEndpoint("http://another")
    with pytest.raises(InvalidInput, match="identity_endpoint_mismatch"):
        StandaloneIdentity(oauth, socket, clock)
