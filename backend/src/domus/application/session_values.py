"""Private application session metadata uses monotonic deadlines, never browser claims."""

from dataclasses import dataclass, field

from domus.domain.errors import InvalidInput
from domus.domain.identity import HumanIdentity
from domus.domain.storage import validate_identifier


def validate_session_lifetime(lifetime: int) -> None:
    if type(lifetime) is not int or not 300_000 <= lifetime <= 28_800_000:
        raise InvalidInput("invalid_session_lifetime")


@dataclass(frozen=True, slots=True)
class SessionLease:
    session_id: str = field(repr=False)
    human: HumanIdentity
    started_at: int
    expires_at: int

    def __post_init__(self) -> None:
        validate_identifier(self.session_id)
        if (
            not isinstance(self.human, HumanIdentity)
            or type(self.started_at) is not int
            or type(self.expires_at) is not int
            or not 0 <= self.started_at < self.expires_at <= 2**63 - 1
            or self.expires_at - self.started_at > 28_800_000
        ):
            raise InvalidInput("invalid_session_lease")

    def valid_at(self, now: int) -> bool:
        return self.started_at <= now < self.expires_at
