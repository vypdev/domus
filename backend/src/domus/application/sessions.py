"""Fresh proof for writes; bounded read grace only for an original live lease."""

from dataclasses import dataclass

from domus.application.identity_ports import LeaseClock, LiveIdentity, SessionAccess
from domus.application.session_values import SessionLease
from domus.domain.errors import IdentityRejected, IdentityUnavailable, Unauthenticated
from domus.domain.identity import HumanIdentity


@dataclass(frozen=True, slots=True)
class SessionStatus:
    human: HumanIdentity
    fresh: bool
    expires_at: int


@dataclass
class SessionGuard:
    sessions: SessionAccess
    identity: LiveIdentity
    clock: LeaseClock

    def _require_time(self, lease: SessionLease) -> None:
        if not lease.valid_at(self.clock.now()):
            self.sessions.remove(lease.session_id)
            raise Unauthenticated("session_expired")

    def _prove(self, session_id: str, *, write: bool) -> SessionStatus:
        lease = self.sessions.get(session_id)
        if lease is None:
            raise Unauthenticated("session_required")
        self._require_time(lease)
        fresh = True
        try:
            human = self.identity.prove(session_id)
        except IdentityUnavailable:
            if write:
                raise
            human = lease.human
            fresh = False
        except Unauthenticated:
            self.sessions.remove(session_id)
            raise
        self._require_time(lease)
        if human.ha_user_id != lease.human.ha_user_id:
            self.sessions.remove(session_id)
            raise IdentityRejected("identity_mismatch")
        if not self.sessions.refresh(lease, human):
            raise Unauthenticated("session_changed")
        return SessionStatus(human, fresh, lease.expires_at)

    def read(self, session_id: str) -> HumanIdentity:
        return self._prove(session_id, write=False).human

    def write(self, session_id: str) -> HumanIdentity:
        return self._prove(session_id, write=True).human

    def status(self, session_id: str) -> SessionStatus:
        return self._prove(session_id, write=False)
