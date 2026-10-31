"""Native leases bind the existing trusted HA session without persisting or exposing its cookie."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier

import pytest
from test_ha_ingress import USER, Lookup

from domus.domain.errors import Forbidden, IdentityRejected, IdentityUnavailable, Unauthenticated
from domus.domain.storage import Installation
from domus.infrastructure.ha_ingress import SupervisorIdentity
from domus.infrastructure.ingress_sessions import IngressSessions

PREFIX = "/api/hassio_ingress/" + "b" * 43
COOKIE = "c" * 128
HEADERS = (
    ("X-Remote-User-Id", USER),
    ("X-Ingress-Path", PREFIX),
    ("Cookie", "other=ignored; ingress_session=" + COOKIE),
)


class Clock:
    value = 100

    def now(self) -> int:
        return self.value


class Entropy:
    count = 0

    def new(self) -> str:
        self.count += 1
        return f"{self.count:043d}"


def fixture(*, capacity: int = 256) -> tuple:
    lookup, clock = Lookup(), Clock()
    sessions = IngressSessions(
        SupervisorIdentity(lookup, "private-supervisor-token"),
        Installation("047cc6fb-dfb0-4fa4-b3c3-e0fe54d116b6", "edge"),
        clock,
        Entropy(),
        b"k" * 32,
        capacity=capacity,
    )
    return sessions, lookup, clock


def test_native_bootstrap_is_fresh_and_updates_preserve_original_deadline() -> None:
    sessions, lookup, clock = fixture()
    request = sessions.request("172.30.32.2", HEADERS)
    first = request.status()
    assert first.fresh and first.expires_at == 3_600_100
    csrf = request.csrf()
    clock.value += 1000
    lookup.identity = replace(lookup.identity, is_administrator=True)
    assert request.current().is_administrator
    assert request.status().expires_at == first.expires_at
    assert request.csrf() == csrf
    assert COOKIE not in repr(sessions) and COOKIE not in repr(request)
    assert COOKIE not in repr(sessions.leases)
    assert "private-supervisor-token" not in repr(sessions)


def test_outage_allows_only_original_read_grace_without_renewal() -> None:
    sessions, lookup, clock = fixture()
    request = sessions.request("172.30.32.2", HEADERS)
    first = request.status()
    csrf = request.csrf()
    lookup.error = IdentityUnavailable("ha_unavailable")
    assert not request.status().fresh and request.read() == first.human
    request.verify_csrf(csrf)
    with pytest.raises(IdentityUnavailable):
        request.current()
    assert request.status().expires_at == first.expires_at
    clock.value = first.expires_at
    with pytest.raises(Unauthenticated):
        request.verify_csrf(csrf)
    with pytest.raises(IdentityUnavailable):
        request.status()


def test_expiry_requires_new_fresh_proof_and_changes_csrf_epoch() -> None:
    sessions, lookup, clock = fixture()
    request = sessions.request("172.30.32.2", HEADERS)
    first = request.status()
    csrf = request.csrf()
    clock.value = first.expires_at
    with pytest.raises(Unauthenticated, match="session_expired"):
        request.current()
    renewed = request.status()
    assert renewed.fresh and renewed.expires_at == clock.value + 3_600_000
    assert request.csrf() != csrf
    with pytest.raises(Forbidden, match="request_forbidden"):
        request.verify_csrf(csrf)
    assert lookup.calls >= 2


def test_explicit_rejection_removes_read_grace_even_if_next_proof_is_unavailable() -> None:
    sessions, lookup, _ = fixture()
    request = sessions.request("172.30.32.2", HEADERS)
    request.status()
    lookup.error = IdentityRejected("ha_subject_rejected")
    with pytest.raises(IdentityRejected):
        request.read()
    lookup.error = IdentityUnavailable("ha_unavailable")
    with pytest.raises(IdentityUnavailable):
        request.read()


@pytest.mark.parametrize(
    "changes",
    [
        (("Cookie", "ingress_session=" + "d" * 128),),
        (("X-Ingress-Path", "/api/hassio_ingress/" + "e" * 43),),
    ],
)
def test_cookie_or_app_path_change_cannot_borrow_an_existing_lease(changes: tuple) -> None:
    sessions, lookup, _ = fixture()
    original = sessions.request("172.30.32.2", HEADERS)
    original.status()
    csrf = original.csrf()
    replaced = (
        tuple((name, value) for name, value in HEADERS if name not in {name for name, _ in changes})
        + changes
    )
    other = sessions.request("172.30.32.2", replaced)
    with pytest.raises(Unauthenticated):
        other.current()
    lookup.error = IdentityUnavailable("ha_unavailable")
    with pytest.raises(IdentityUnavailable):
        other.status()
    with pytest.raises(Unauthenticated):
        other.verify_csrf(csrf)


@pytest.mark.parametrize(
    "headers",
    [
        HEADERS[:-1],
        HEADERS[:-1] + (("Cookie", "ingress_session=bad"),),
        HEADERS + (("cookie", "ingress_session=" + COOKIE),),
        HEADERS[:-1] + (("Cookie", "ingress_session=" + COOKIE + "; ingress_session=" + COOKIE),),
        tuple((name, value) for name, value in HEADERS if name != "X-Ingress-Path"),
        HEADERS + (("x-ingress-path", PREFIX),),
    ],
)
def test_missing_ambiguous_or_malformed_metadata_fails_before_core(headers: tuple) -> None:
    sessions, lookup, _ = fixture()
    with pytest.raises((IdentityRejected, Unauthenticated)):
        sessions.request("172.30.32.2", headers).status()
    assert lookup.calls == 0


def test_untrusted_peer_cannot_use_even_a_real_cookie_and_subject() -> None:
    sessions, lookup, _ = fixture()
    with pytest.raises(IdentityRejected):
        sessions.request("127.0.0.1", HEADERS).status()
    assert lookup.calls == 0


def test_writes_and_csrf_never_bootstrap_a_missing_local_lease() -> None:
    sessions, lookup, _ = fixture()
    request = sessions.request("172.30.32.2", HEADERS)
    with pytest.raises(Unauthenticated):
        request.current()
    with pytest.raises(Unauthenticated):
        request.verify_csrf("guess")
    assert lookup.calls == 0


def test_shutdown_discards_leases_and_cannot_reauthenticate_the_same_runtime() -> None:
    sessions, lookup, _ = fixture()
    request = sessions.request("172.30.32.2", HEADERS)
    request.status()
    calls = lookup.calls
    sessions.close()
    with pytest.raises(Unauthenticated):
        request.status()
    assert lookup.calls == calls


def test_simultaneous_first_requests_share_one_lease_and_original_expiry() -> None:
    sessions, lookup, _ = fixture(capacity=1)
    gate = Barrier(2)
    original = lookup.directory_user

    def concurrent(token: str, subject: str):
        human = original(token, subject)
        gate.wait(timeout=3)
        return human

    lookup.directory_user = concurrent

    def read(_: int):
        return sessions.request("172.30.32.2", HEADERS).status()

    with ThreadPoolExecutor(max_workers=2) as workers:
        first, second = workers.map(read, (1, 2))
    assert first == second


@pytest.mark.parametrize("key", [b"short", "not-bytes"])
def test_native_session_key_must_be_private_bounded_entropy(key: bytes) -> None:
    from domus.domain.errors import InvalidInput

    with pytest.raises(InvalidInput, match="invalid_ingress_session_key"):
        IngressSessions(
            SupervisorIdentity(Lookup(), "private-supervisor-token"),
            Installation("047cc6fb-dfb0-4fa4-b3c3-e0fe54d116b6", "edge"),
            Clock(),
            Entropy(),
            key,
        )


def test_capacity_cannot_evict_valid_other_leases_and_expired_bindings_are_reclaimed() -> None:
    sessions, _, clock = fixture(capacity=1)
    first = sessions.request("172.30.32.2", HEADERS)
    first.status()
    original = first.csrf()
    changed = HEADERS[:-1] + (("Cookie", "ingress_session=" + "d" * 128),)
    second = sessions.request("172.30.32.2", changed)
    with pytest.raises(IdentityUnavailable, match="session_capacity"):
        second.status()
    assert first.csrf() == original and len(sessions._bindings) == 1
    clock.value += 3_600_000
    assert second.status().fresh and len(sessions._bindings) == 1
    with pytest.raises(Unauthenticated):
        first.verify_csrf(original)


def test_shutdown_during_fresh_proof_cannot_publish_a_new_lease() -> None:
    sessions, lookup, _ = fixture()
    original = lookup.directory_user

    def closed(token: str, subject: str):
        human = original(token, subject)
        sessions.close()
        return human

    lookup.directory_user = closed
    with pytest.raises(Unauthenticated):
        sessions.request("172.30.32.2", HEADERS).status()
    assert sessions._bindings == {}


def test_concurrent_bootstrap_losing_lease_compare_and_swap_does_not_override_current_proof(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sessions, lookup, _ = fixture()
    gate = Barrier(2)
    original = lookup.directory_user

    def concurrent(token: str, subject: str):
        human = original(token, subject)
        gate.wait(timeout=3)
        return human

    lookup.directory_user = concurrent
    monkeypatch.setattr(sessions.leases, "refresh", lambda *_: False)

    def attempt(_: int) -> str:
        try:
            sessions.request("172.30.32.2", HEADERS).status()
        except IdentityRejected as error:
            assert error.code == "session_changed"
            return "changed"
        return "created"

    with ThreadPoolExecutor(max_workers=2) as workers:
        assert sorted(workers.map(attempt, (1, 2))) == ["changed", "created"]
    assert len(sessions._bindings) == 1


@pytest.mark.parametrize(
    "channel,instance",
    [
        ("stable", "047cc6fb-dfb0-4fa4-b3c3-e0fe54d116b6"),
        ("edge", "d94fba1b-7e76-47c4-a6b0-a88ade28363e"),
    ],
)
def test_csrf_namespace_cannot_cross_installation_or_channel_even_with_test_key_reuse(
    channel: str, instance: str
) -> None:
    first, _, _ = fixture()
    left = first.request("172.30.32.2", HEADERS)
    left.status()
    right_sessions = IngressSessions(
        SupervisorIdentity(Lookup(), "private-supervisor-token"),
        Installation(instance, channel),
        Clock(),
        Entropy(),
        b"k" * 32,
    )
    right = right_sessions.request("172.30.32.2", HEADERS)
    right.status()
    assert left.csrf() != right.csrf()
    with pytest.raises(Forbidden):
        right.verify_csrf(left.csrf())
