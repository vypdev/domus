"""Bounded private attempt storage atomically checks browser binding before consumption."""

from threading import Lock

from domus.application.authentication_values import LoginAttempt
from domus.domain.errors import Conflict, IdentityRejected, IdentityUnavailable, InvalidInput


class MemoryLoginAttempts:
    def __init__(self, *, max_attempts: int = 128) -> None:
        if type(max_attempts) is not int or not 1 <= max_attempts <= 1024:
            raise InvalidInput("invalid_login_capacity")
        self._maximum = max_attempts
        self._attempts: dict[str, LoginAttempt] = {}
        self._lock = Lock()

    def add(self, attempt: LoginAttempt, now: int) -> None:
        with self._lock:
            expired = [key for key, record in self._attempts.items() if not record.valid_at(now)]
            for key in expired:
                del self._attempts[key]
            if attempt.state_digest in self._attempts:
                raise Conflict("login_attempt_exists")
            if len(self._attempts) >= self._maximum:
                raise IdentityUnavailable("login_capacity")
            self._attempts[attempt.state_digest] = attempt

    def take(self, state_digest: str, browser_digest: str, now: int) -> LoginAttempt:
        with self._lock:
            attempt = self._attempts.get(state_digest)
            if attempt is None:
                raise IdentityRejected("invalid_login_attempt")
            if not attempt.valid_at(now):
                del self._attempts[state_digest]
                raise IdentityRejected("login_attempt_expired")
            if not attempt.matches_browser(browser_digest):
                raise IdentityRejected("invalid_login_attempt")
            del self._attempts[state_digest]
            return attempt
