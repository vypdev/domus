"""Session and live-proof contracts contain neither HA transport DTOs nor credentials."""

from typing import Protocol

from domus.application.authentication_values import LoginAttempt
from domus.application.session_values import SessionLease
from domus.domain.identity import HumanIdentity


class CurrentHuman(Protocol):
    """Obtain fresh server-side human proof for a mutation; never a submitted DTO."""

    def current(self) -> HumanIdentity: ...


class HumanDirectory(Protocol):
    """Resolve one exact, currently eligible human through a configured authority."""

    def get(self, ha_user_id: str) -> HumanIdentity: ...

    def eligible(self, ha_user_ids: tuple[str, ...]) -> tuple[HumanIdentity, ...]:
        """Return only confirmed eligible requested humans from one bounded lookup.

        Omission means confirmed absence/ineligibility. Transport, authorization
        or malformed-source failures must raise, never become partial success.
        """
        ...


class LeaseClock(Protocol):
    """Process-local monotonic milliseconds; never persisted across a restart."""

    def now(self) -> int: ...


class LiveIdentity(Protocol):
    """Reprove through private server credentials bound to the opaque session ID.

    Explicit rejection or malformed proof raises IdentityRejected. Only a true
    bounded availability failure raises IdentityUnavailable, permitting read grace.
    """

    def prove(self, session_id: str) -> HumanIdentity: ...


class SessionAccess(Protocol):
    def get(self, session_id: str) -> SessionLease | None: ...
    def refresh(self, expected: SessionLease, human: HumanIdentity) -> bool: ...
    def remove(self, session_id: str) -> None: ...


class SessionLeases(SessionAccess, Protocol):
    def add(self, lease: SessionLease) -> None: ...
    def discard_expired(self, now: int) -> int: ...


class LoginAttempts(Protocol):
    def add(self, attempt: LoginAttempt, now: int) -> None: ...
    def take(self, state_digest: str, browser_digest: str, now: int) -> LoginAttempt: ...


class LoginProvider(Protocol):
    """Own provider credentials, exact endpoint and cleanup outside business storage."""

    def authorization_url(self, state: str, challenge: str) -> str: ...
    def sign_in(
        self, code: str, verifier: str, session_id: str, issued_at: int, expires_at: int
    ) -> SessionLease: ...
    def sign_out(self, session_id: str) -> bool | None: ...


class LoginEntropy(Protocol):
    def new(self) -> str: ...
