"""OS-backed entropy and process-local monotonic time for ephemeral authentication."""

import secrets
import time


class MonotonicClock:
    def now(self) -> int:
        return time.monotonic_ns() // 1_000_000


class SecureEntropy:
    def new(self) -> str:
        return secrets.token_urlsafe(32)
