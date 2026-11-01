"""Short-lived keyset positions signed for one application-supplied query context."""

import base64
import hmac
from dataclasses import dataclass, field

from domus.application.ports import Clock
from domus.domain.errors import InvalidInput
from domus.domain.storage import JsonDocument, validate_identifier


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    decoded = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    if _encode(decoded) != value:
        raise InvalidInput("invalid_task_cursor")
    return decoded


@dataclass(frozen=True, slots=True)
class TaskCursor:
    """A process key may invalidate pagination on restart; this is not a snapshot lease."""

    clock: Clock
    key: bytes = field(repr=False)
    lifetime_ms: int = 300_000

    def __post_init__(self) -> None:
        if (
            type(self.key) is not bytes
            or not 32 <= len(self.key) <= 128
            or type(self.lifetime_ms) is not int
            or not 1 <= self.lifetime_ms <= 3_600_000
        ):
            raise InvalidInput("invalid_task_cursor_configuration")

    def _now(self) -> int:
        now = self.clock.now()
        if type(now) is not int or not 0 <= now <= 2**63 - 1 - self.lifetime_ms:
            raise InvalidInput("invalid_task_cursor")
        return now

    def encode(self, binding: JsonDocument, after: str) -> str:
        validate_identifier(after)
        now = self._now()
        payload = _encode(
            JsonDocument.from_value(
                {
                    "v": 1,
                    "c": binding.fingerprint,
                    "a": after,
                    "i": now,
                    "e": now + self.lifetime_ms,
                }
            ).encoded.encode("utf-8")
        )
        return payload + "." + _encode(hmac.digest(self.key, payload.encode("ascii"), "sha256"))

    def decode(self, binding: JsonDocument, token: str) -> str:
        try:
            if not isinstance(token, str) or not 1 <= len(token) <= 512:
                raise InvalidInput("invalid_task_cursor")
            payload, signature = token.split(".")
            raw = _decode(payload)
            supplied = _decode(signature)
            expected = hmac.digest(self.key, payload.encode("ascii"), "sha256")
            if not hmac.compare_digest(supplied, expected):
                raise InvalidInput("invalid_task_cursor")
            value = JsonDocument(raw.decode("utf-8")).decode()
            if set(value) != {"v", "c", "a", "i", "e"}:
                raise InvalidInput("invalid_task_cursor")
            version, context, after, issued, expires = (
                value[key] for key in ("v", "c", "a", "i", "e")
            )
            now = self._now()
            if (
                type(version) is not int
                or version != 1
                or context != binding.fingerprint
                or type(issued) is not int
                or type(expires) is not int
                or not 0 <= issued <= now < expires <= 2**63 - 1
                or expires - issued > self.lifetime_ms
                or not isinstance(after, str)
            ):
                raise InvalidInput("invalid_task_cursor")
            validate_identifier(after)
            return after
        except ValueError, UnicodeError, InvalidInput:
            raise InvalidInput("invalid_task_cursor") from None
