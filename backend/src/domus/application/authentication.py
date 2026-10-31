"""Browser-bound single-use login orchestration does not own HA tokens or URLs."""

import base64
import hashlib
from dataclasses import dataclass, field

from domus.application.authentication_values import LoginAttempt, validate_login_material
from domus.application.identity_ports import LeaseClock, LoginAttempts, LoginEntropy, LoginProvider
from domus.application.session_values import SessionLease, validate_session_lifetime
from domus.domain.errors import IdentityRejected, InvalidInput
from domus.domain.storage import validate_identifier


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()


@dataclass(frozen=True, slots=True)
class LoginStart:
    authorization_url: str = field(repr=False)
    browser_token: str = field(repr=False)


@dataclass
class Authentication:
    attempts: LoginAttempts
    provider: LoginProvider = field(repr=False)
    clock: LeaseClock
    entropy: LoginEntropy
    lifetime: int = 3_600_000

    def __post_init__(self) -> None:
        validate_session_lifetime(self.lifetime)

    def _material(self) -> str:
        value = self.entropy.new()
        validate_login_material(value)
        return value

    def start(self) -> LoginStart:
        state, verifier, browser = self._material(), self._material(), self._material()
        now = self.clock.now()
        attempt = LoginAttempt(_digest(state), _digest(browser), verifier, now, now + 300_000)
        self.attempts.add(attempt, now)
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
            .rstrip(b"=")
            .decode("ascii")
        )
        return LoginStart(self.provider.authorization_url(state, challenge), browser)

    def _take(self, state: str, browser: str) -> LoginAttempt:
        try:
            validate_login_material(state)
            validate_login_material(browser)
        except InvalidInput:
            raise IdentityRejected("invalid_login_attempt") from None
        return self.attempts.take(_digest(state), _digest(browser), self.clock.now())

    def cancel(self, state: str, browser: str) -> None:
        self._take(state, browser)

    def complete(self, code: str, state: str, browser: str) -> SessionLease:
        attempt = self._take(state, browser)
        session_id = "s_" + self._material()
        validate_identifier(session_id)
        now = self.clock.now()
        deadline = now + self.lifetime
        lease = self.provider.sign_in(code, attempt.verifier, session_id, now, deadline)
        if (
            lease.session_id != session_id
            or lease.started_at != now
            or lease.expires_at != deadline
            or not lease.valid_at(self.clock.now())
        ):
            self.provider.sign_out(session_id)
            raise IdentityRejected("invalid_login_result")
        return lease
