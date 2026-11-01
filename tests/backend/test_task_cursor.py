"""Signed pagination tokens cannot cross identities, filters or their short lifetime."""

import base64
import hmac
import json
from dataclasses import dataclass

import pytest

from domus.domain.errors import InvalidInput
from domus.domain.storage import JsonDocument
from domus.infrastructure.task_cursor import TaskCursor


@dataclass
class Clock:
    value: int = 1000

    def now(self):
        return self.value


KEY = b"task-pagination-test-key-32-bytes!!"
BINDING = JsonDocument.from_value({"actor": "ha_admin", "limit": 25, "query": "tasks"})


def signed(value):
    payload = base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b"=")
    signature = hmac.digest(KEY, payload, "sha256")
    return (payload + b"." + base64.urlsafe_b64encode(signature).rstrip(b"=")).decode()


def test_cursor_is_opaque_bounded_and_reusable_until_exact_expiry():
    clock = Clock()
    codec = TaskCursor(clock, KEY)
    token = codec.encode(BINDING, "occurrence-128")
    assert len(token) <= 512 and "ha_admin" not in token and repr(KEY) not in repr(codec)
    assert codec.decode(BINDING, token) == "occurrence-128"
    clock.value = 300999
    assert codec.decode(BINDING, token) == "occurrence-128"
    clock.value += 1
    with pytest.raises(InvalidInput, match="invalid_task_cursor"):
        codec.decode(BINDING, token)


@pytest.mark.parametrize("binding", [{"actor": "other"}, {"limit": 100}, {"query": "history"}])
def test_cursor_rejects_a_different_binding_or_process_key(binding):
    codec = TaskCursor(Clock(), KEY)
    token = codec.encode(BINDING, "occ")
    with pytest.raises(InvalidInput):
        codec.decode(JsonDocument.from_value(binding), token)
    with pytest.raises(InvalidInput):
        TaskCursor(Clock(), b"x" * 32).decode(BINDING, token)


@pytest.mark.parametrize(
    "token", [None, 1, "", "x" * 513, "a", "a.b.c", "=.a", "a.=", "a.b", "ab.cd", "é.a"]
)
def test_malformed_encoding_is_not_accepted(token):
    with pytest.raises(InvalidInput, match="invalid_task_cursor"):
        TaskCursor(Clock(), KEY).decode(BINDING, token)


def test_validly_encoded_payload_and_signature_changes_fail_mac_verification():
    codec = TaskCursor(Clock(), KEY)
    token = codec.encode(BINDING, "occ")
    payload, signature = token.split(".")
    for altered in (
        "A" + payload[1:] + "." + signature,
        payload + "." + ("B" if signature[0] == "A" else "A") + signature[1:],
    ):
        with pytest.raises(InvalidInput):
            codec.decode(BINDING, altered)


@pytest.mark.parametrize(
    "changes",
    [
        {"v": 2},
        {"v": True},
        {"extra": 1},
        {"a": "bad id"},
        {"a": None},
        {"i": True},
        {"i": -1},
        {"i": 1001},
        {"i": 2**63},
        {"e": 1000},
        {"e": True},
        {"e": 2**63},
        {"e": 3601001},
        {"c": "other"},
    ],
)
def test_even_signed_invalid_version_scope_position_and_times_fail_closed(changes):
    value = {"v": 1, "c": BINDING.fingerprint, "a": "occ", "i": 1000, "e": 301000}
    value.update(changes)
    with pytest.raises(InvalidInput, match="invalid_task_cursor"):
        TaskCursor(Clock(), KEY).decode(BINDING, signed(value))


def test_signed_invalid_json_or_noncanonical_base64_is_rejected():
    codec = TaskCursor(Clock(), KEY)
    for body in (b"not-json", b"[]", b'{"v":1,"v":1}'):
        payload = base64.urlsafe_b64encode(body).rstrip(b"=")
        signature = base64.urlsafe_b64encode(hmac.digest(KEY, payload, "sha256")).rstrip(b"=")
        with pytest.raises(InvalidInput):
            codec.decode(BINDING, (payload + b"." + signature).decode())
    # The final base64 character may contain unused bits, which must be canonical.
    token = codec.encode(BINDING, "occ")
    payload, signature = token.split(".")
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    changed = signature[:-1] + alphabet[alphabet.index(signature[-1]) + 1]
    with pytest.raises(InvalidInput):
        codec.decode(BINDING, payload + "." + changed)


@pytest.mark.parametrize(
    "key,ttl",
    [(b"short", 1), ("x" * 32, 1), (b"x" * 129, 1), (KEY, True), (KEY, 0), (KEY, 3600001)],
)
def test_invalid_runtime_configuration_is_rejected(key, ttl):
    with pytest.raises(InvalidInput):
        TaskCursor(Clock(), key, ttl)


@pytest.mark.parametrize("now", [True, -1, 2**63, 2**63 - 1])
def test_unrepresentable_clock_cannot_issue_or_validate_a_cursor(now):
    codec = TaskCursor(Clock(now), KEY)
    with pytest.raises(InvalidInput):
        codec.encode(BINDING, "occ")
    with pytest.raises(InvalidInput):
        codec.decode(BINDING, TaskCursor(Clock(), KEY).encode(BINDING, "occ"))


def test_position_requires_a_bounded_identifier():
    with pytest.raises(InvalidInput):
        TaskCursor(Clock(), KEY).encode(BINDING, "bad position")
