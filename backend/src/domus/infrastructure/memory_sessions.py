"""Bounded process-local leases; restart requires authentication, not database secrets."""

from dataclasses import replace
from threading import Lock

from domus.domain.errors import Conflict, IdentityUnavailable, InvalidInput
from domus.domain.identity import HumanIdentity
from domus.domain.sessions import SessionLease


class MemorySessions:
    def __init__(self, *, max_sessions: int = 256) -> None:
        if type(max_sessions) is not int or not 1 <= max_sessions <= 1024:
            raise InvalidInput("invalid_session_capacity")
        self._maximum = max_sessions
        self._leases: dict[str, SessionLease] = {}
        self._lock = Lock()

    def get(self, session_id: str) -> SessionLease | None:
        with self._lock:
            return self._leases.get(session_id)

    def add(self, lease: SessionLease) -> None:
        with self._lock:
            if lease.session_id in self._leases:
                raise Conflict("session_exists")
            if len(self._leases) >= self._maximum:
                raise IdentityUnavailable("session_capacity")
            self._leases[lease.session_id] = lease

    def refresh(self, expected: SessionLease, human: HumanIdentity) -> bool:
        if human.ha_user_id != expected.human.ha_user_id:
            raise InvalidInput("identity_mismatch")
        with self._lock:
            if self._leases.get(expected.session_id) != expected:
                return False
            self._leases[expected.session_id] = replace(expected, human=human)
            return True

    def remove(self, session_id: str) -> None:
        with self._lock:
            self._leases.pop(session_id, None)

    def discard_expired(self, now: int) -> int:
        with self._lock:
            expired = [key for key, lease in self._leases.items() if not lease.valid_at(now)]
            for key in expired:
                del self._leases[key]
            return len(expired)
