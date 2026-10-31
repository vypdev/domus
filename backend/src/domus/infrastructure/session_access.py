"""Opaque server-session adapters keep private transport material outside request DTOs."""

from dataclasses import dataclass, field

from domus.application.sessions import SessionGuard
from domus.domain.errors import IdentityRejected
from domus.domain.identity import HumanIdentity
from domus.infrastructure.standalone_sessions import StandaloneIdentity


@dataclass(frozen=True, slots=True)
class SessionActor:
    guard: SessionGuard = field(repr=False)
    session_id: str = field(repr=False)

    def read(self) -> HumanIdentity:
        return self.guard.read(self.session_id)

    def current(self) -> HumanIdentity:
        return self.guard.write(self.session_id)


@dataclass(frozen=True, slots=True)
class SessionDirectory:
    identity: StandaloneIdentity = field(repr=False)
    session_id: str = field(repr=False)

    def get(self, ha_user_id: str) -> HumanIdentity:
        humans = self.eligible((ha_user_id,))
        if not humans:
            raise IdentityRejected("ha_subject_rejected")
        return humans[0]

    def eligible(self, ha_user_ids: tuple[str, ...]) -> tuple[HumanIdentity, ...]:
        return self.identity.directory(self.session_id, ha_user_ids)
