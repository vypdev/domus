"""Browser-bound, single-use login attempts precede all HA exchanges and session issuance."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier

import pytest

from domus.application.authentication import Authentication
from domus.application.authentication_values import LoginAttempt
from domus.application.session_values import SessionLease
from domus.domain.errors import Conflict, IdentityRejected, IdentityUnavailable, InvalidInput
from domus.domain.identity import HumanIdentity
from domus.infrastructure.memory_attempts import MemoryLoginAttempts

STATE, VERIFIER, BROWSER = "s" * 43, "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk", "b" * 43
SESSION = "s_" + "x" * 43
HUMAN = HumanIdentity("ha_1", False, True, False)


class Clock:
    value = 100

    def now(self) -> int:
        return self.value


class Entropy:
    def __init__(self) -> None:
        self.values = iter((STATE, VERIFIER, BROWSER, "x" * 43))

    def new(self) -> str:
        return next(self.values)


class Provider:
    def __init__(self) -> None:
        self.exchanges = []
        self.signed_out = []
        self.error = None
        self.change = lambda lease: lease
        self.challenge = None

    def authorization_url(self, state: str, challenge: str) -> str:
        assert state == STATE
        self.challenge = challenge
        return "https://ha.example/auth/authorize?state=" + state

    def sign_in(
        self, code: str, verifier: str, session_id: str, issued_at: int, expires_at: int
    ) -> SessionLease:
        self.exchanges.append((code, verifier))
        if self.error:
            raise self.error
        return self.change(SessionLease(session_id, HUMAN, issued_at, expires_at))

    def sign_out(self, session_id: str) -> bool:
        self.signed_out.append(session_id)
        return True


def fixture() -> tuple[Authentication, MemoryLoginAttempts, Provider, Clock]:
    attempts, provider, clock = MemoryLoginAttempts(), Provider(), Clock()
    return Authentication(attempts, provider, clock, Entropy()), attempts, provider, clock


def test_start_uses_pkce_s256_and_completion_consumes_browser_bound_attempt() -> None:
    flow, _, provider, clock = fixture()
    start = flow.start()
    assert start.browser_token == BROWSER
    assert start.authorization_url == "https://ha.example/auth/authorize?state=" + STATE
    assert provider.challenge == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
    clock.value = 200
    lease = flow.complete("code", STATE, BROWSER)
    assert lease == SessionLease(SESSION, HUMAN, 200, 3_600_200)
    assert provider.exchanges == [("code", VERIFIER)]
    with pytest.raises(IdentityRejected, match="invalid_login_attempt"):
        flow.complete("code", STATE, BROWSER)
    assert len(provider.exchanges) == 1
    assert BROWSER not in repr(start)


def test_wrong_browser_binding_cannot_consume_legitimate_attempt() -> None:
    flow, _, provider, _ = fixture()
    flow.start()
    with pytest.raises(IdentityRejected, match="invalid_login_attempt"):
        flow.complete("code", STATE, "w" * 43)
    assert provider.exchanges == []
    assert flow.complete("code", STATE, BROWSER).human == HUMAN


@pytest.mark.parametrize("state,browser", [("wrong", BROWSER), (STATE, ""), ("z" * 43, BROWSER)])
def test_invalid_or_unknown_attempt_is_rejected_before_provider(state: str, browser: str) -> None:
    flow, _, provider, _ = fixture()
    flow.start()
    with pytest.raises(IdentityRejected):
        flow.complete("code", state, browser)
    assert provider.exchanges == []


def test_upstream_failure_consumes_valid_attempt_without_a_second_exchange() -> None:
    flow, _, provider, _ = fixture()
    flow.start()
    provider.error = IdentityUnavailable("ha_unavailable")
    with pytest.raises(IdentityUnavailable):
        flow.complete("code", STATE, BROWSER)
    with pytest.raises(IdentityRejected):
        flow.complete("code", STATE, BROWSER)
    assert len(provider.exchanges) == 1


@pytest.mark.parametrize("time", [99, 300_100])
def test_expired_or_backwards_clock_attempt_cannot_exchange(time: int) -> None:
    flow, _, provider, clock = fixture()
    flow.start()
    clock.value = time
    with pytest.raises(IdentityRejected, match="login_attempt_expired"):
        flow.complete("code", STATE, BROWSER)
    assert provider.exchanges == []


@pytest.mark.parametrize(
    "change",
    [
        lambda lease: replace(lease, session_id="someone_else"),
        lambda lease: replace(lease, expires_at=lease.expires_at + 1),
    ],
)
def test_provider_cannot_retarget_or_extend_server_owned_session(change: object) -> None:
    flow, _, provider, _ = fixture()
    flow.start()
    provider.change = change
    with pytest.raises(IdentityRejected, match="invalid_login_result"):
        flow.complete("code", STATE, BROWSER)
    assert provider.signed_out == [SESSION]


def test_session_expiry_during_exchange_cleans_only_allocated_session() -> None:
    flow, _, provider, clock = fixture()
    flow.start()

    def expire(lease: SessionLease) -> SessionLease:
        clock.value = lease.expires_at
        return lease

    provider.change = expire
    with pytest.raises(IdentityRejected, match="invalid_login_result"):
        flow.complete("code", STATE, BROWSER)
    assert provider.signed_out == [SESSION]


def attempt() -> LoginAttempt:
    return LoginAttempt("a" * 64, "b" * 64, VERIFIER, 100, 300_100)


def test_attempt_repr_capacity_duplicate_and_expired_cleanup() -> None:
    attempts = MemoryLoginAttempts(max_attempts=1)
    record = attempt()
    attempts.add(record, 100)
    assert VERIFIER not in repr(record)
    with pytest.raises(Conflict, match="login_attempt_exists"):
        attempts.add(record, 100)
    with pytest.raises(IdentityUnavailable, match="login_capacity"):
        attempts.add(replace(record, state_digest="c" * 64), 100)
    attempts.add(
        replace(record, state_digest="c" * 64, issued_at=300_100, expires_at=600_100), 300_100
    )
    with pytest.raises(IdentityRejected, match="invalid_login_attempt"):
        attempts.take(record.state_digest, record.browser_digest, 300_100)


def test_competing_callbacks_only_one_can_take_the_attempt() -> None:
    attempts = MemoryLoginAttempts()
    record = attempt()
    attempts.add(record, 100)
    ready = Barrier(2)

    def claim() -> object:
        ready.wait(timeout=3)
        try:
            return attempts.take(record.state_digest, record.browser_digest, 101)
        except IdentityRejected as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: claim(), range(2)))
    assert results.count(record) == 1 and results.count("invalid_login_attempt") == 1


@pytest.mark.parametrize("capacity", [0, -1, True, 1025])
def test_attempt_capacity_is_bounded(capacity: object) -> None:
    with pytest.raises(InvalidInput):
        MemoryLoginAttempts(max_attempts=capacity)


@pytest.mark.parametrize("lifetime", [0, True, 299_999, 28_800_001])
def test_session_lifetime_is_explicit_and_bounded(lifetime: object) -> None:
    with pytest.raises(InvalidInput):
        Authentication(MemoryLoginAttempts(), Provider(), Clock(), Entropy(), lifetime=lifetime)


def test_attempt_value_rejects_unbounded_verifier_digest_and_lifetime() -> None:
    for changes in (
        {"state_digest": "bad"},
        {"browser_digest": "bad"},
        {"verifier": "bad"},
        {"issued_at": True},
        {"expires_at": 100},
        {"expires_at": 300_101},
    ):
        with pytest.raises(InvalidInput):
            replace(attempt(), **changes)
