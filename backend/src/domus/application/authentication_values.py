"""Ephemeral login contracts stay outside household domain entities and business storage."""

import hmac
import re
from dataclasses import dataclass, field

from domus.domain.errors import InvalidInput


def validate_login_material(value: str) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9._~-]{43,128}", value):
        raise InvalidInput("invalid_login_material")


@dataclass(frozen=True, slots=True)
class LoginAttempt:
    state_digest: str
    browser_digest: str
    verifier: str = field(repr=False)
    issued_at: int
    expires_at: int

    def __post_init__(self) -> None:
        for digest in (self.state_digest, self.browser_digest):
            if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
                raise InvalidInput("invalid_login_attempt")
        validate_login_material(self.verifier)
        if (
            type(self.issued_at) is not int
            or type(self.expires_at) is not int
            or not 0 <= self.issued_at < self.expires_at <= 2**63 - 1
            or self.expires_at - self.issued_at > 300_000
        ):
            raise InvalidInput("invalid_login_attempt")

    def valid_at(self, now: int) -> bool:
        return self.issued_at <= now < self.expires_at

    def matches_browser(self, browser_digest: str) -> bool:
        return hmac.compare_digest(self.browser_digest, browser_digest)
