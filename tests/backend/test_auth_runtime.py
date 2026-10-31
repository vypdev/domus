"""Process-local authentication sources use the correct clock and cryptographic entropy."""

import pytest

from domus.infrastructure.auth_runtime import MonotonicClock, SecureEntropy


def test_monotonic_clock_uses_integer_milliseconds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("domus.infrastructure.auth_runtime.time.monotonic_ns", lambda: 123_456_789)
    assert MonotonicClock().now() == 123


def test_entropy_uses_32_private_random_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    def token(size: int) -> str:
        assert size == 32
        return "_" + "r" * 42

    monkeypatch.setattr("domus.infrastructure.auth_runtime.secrets.token_urlsafe", token)
    assert SecureEntropy().new() == "_" + "r" * 42
