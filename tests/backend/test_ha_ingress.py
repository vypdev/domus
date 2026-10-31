"""Only Supervisor's actual socket peer may supply a candidate human subject."""

from dataclasses import dataclass

import pytest

from domus.domain.errors import IdentityRejected, IdentityUnavailable, InvalidInput
from domus.domain.identity import HumanIdentity
from domus.infrastructure.ha_config import HAEndpoint
from domus.infrastructure.ha_ingress import SupervisorIdentity

USER = "a" * 32
HEADERS = (
    ("X-Remote-User-Id", USER),
    ("X-Remote-User-Name", "Administrator"),
    ("X-Forwarded-For", "172.30.32.2"),
)


@dataclass
class Lookup:
    endpoint: HAEndpoint = HAEndpoint.supervisor()
    calls: int = 0
    identity: HumanIdentity = HumanIdentity(USER, False, True, False)
    error: Exception | None = None

    def directory_user(self, token: str, user_id: str) -> HumanIdentity:
        assert token == "private-supervisor-token" and user_id == USER
        self.calls += 1
        if self.error:
            raise self.error
        return self.identity


def test_actual_supervisor_peer_is_required_before_any_lookup_or_forwarded_header() -> None:
    lookup = Lookup()
    verifier = SupervisorIdentity(lookup, "private-supervisor-token")
    for peer in ("127.0.0.1", "192.168.1.10", "::ffff:172.30.32.2", ""):
        with pytest.raises(IdentityRejected, match="untrusted_ingress_peer"):
            verifier.prove(peer, HEADERS)
    assert lookup.calls == 0


def test_core_proof_overrules_header_name_and_transport_privilege() -> None:
    lookup = Lookup()
    verifier = SupervisorIdentity(lookup, "private-supervisor-token")
    assert not verifier.prove("172.30.32.2", HEADERS).is_administrator
    lookup.identity = HumanIdentity(USER, True, True, False)
    assert verifier.prove("172.30.32.2", HEADERS).is_administrator
    assert lookup.calls == 2
    assert "private-supervisor-token" not in repr(verifier)


@pytest.mark.parametrize(
    "headers",
    [
        (),
        (("X-Remote-User-Name", "Owner"),),
        (("X-Remote-User-Id", "bad-id"),),
        (("X-Remote-User-Id", USER), ("x-remote-user-id", USER)),
        (("X-Remote-User-Id", USER + ", " + USER),),
    ],
)
def test_missing_malformed_or_duplicate_header_does_not_establish_human(headers: tuple) -> None:
    lookup = Lookup()
    with pytest.raises(IdentityRejected, match="invalid_ingress_subject"):
        SupervisorIdentity(lookup, "private-supervisor-token").prove("172.30.32.2", headers)
    assert lookup.calls == 0


def test_lookup_must_match_candidate_and_failures_never_fall_back_to_headers() -> None:
    lookup = Lookup(identity=HumanIdentity("b" * 32, True, True, False))
    verifier = SupervisorIdentity(lookup, "private-supervisor-token")
    with pytest.raises(IdentityRejected, match="identity_mismatch"):
        verifier.prove("172.30.32.2", HEADERS)
    lookup.error = IdentityUnavailable("ha_unavailable")
    with pytest.raises(IdentityUnavailable):
        verifier.prove("172.30.32.2", HEADERS)
    lookup.error = IdentityRejected("ha_subject_rejected")
    with pytest.raises(IdentityRejected):
        verifier.prove("172.30.32.2", HEADERS)


def test_standalone_endpoint_cannot_be_repurposed_for_ingress_identity() -> None:
    lookup = Lookup(endpoint=HAEndpoint("http://ha.local"))
    with pytest.raises(InvalidInput, match="ingress_requires_supervisor"):
        SupervisorIdentity(lookup, "private-supervisor-token")
