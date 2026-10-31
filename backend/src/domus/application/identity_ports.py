"""Session and live-proof contracts contain neither HA transport DTOs nor credentials."""

from typing import Protocol

from domus.domain.identity import HumanIdentity
from domus.domain.sessions import SessionLease


class LeaseClock(Protocol):
    """Process-local monotonic milliseconds; never persisted across a restart."""

    def now(self) -> int: ...


class LiveIdentity(Protocol):
    """Reprove through private server credentials bound to the opaque session ID.

    Explicit rejection or malformed proof raises IdentityRejected. Only a true
    bounded availability failure raises IdentityUnavailable, permitting read grace.
    """

    def prove(self, session_id: str) -> HumanIdentity: ...


class SessionLeases(Protocol):
    def get(self, session_id: str) -> SessionLease | None: ...
    def add(self, lease: SessionLease) -> None: ...
    def refresh(self, expected: SessionLease, human: HumanIdentity) -> bool: ...
    def remove(self, session_id: str) -> None: ...
    def discard_expired(self, now: int) -> int: ...
