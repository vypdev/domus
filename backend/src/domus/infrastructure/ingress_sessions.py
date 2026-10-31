"""Bind an existing Supervisor session to bounded local leases without another browser cookie."""

import hashlib
import hmac
import re
from dataclasses import dataclass, field
from threading import RLock

from domus.application.authentication_values import validate_login_material
from domus.application.identity_ports import LeaseClock, LoginEntropy
from domus.application.session_values import SessionLease, validate_session_lifetime
from domus.application.sessions import SessionGuard, SessionStatus
from domus.domain.errors import Forbidden, IdentityRejected, InvalidInput, Unauthenticated
from domus.domain.identity import HumanIdentity
from domus.domain.storage import Installation
from domus.infrastructure.ha_ingress import SupervisorIdentity
from domus.infrastructure.memory_sessions import MemorySessions


@dataclass(frozen=True, slots=True)
class _RequestProof:
    identity: SupervisorIdentity = field(repr=False)
    peer: str
    headers: tuple[tuple[str, str], ...] = field(repr=False)

    def prove(self, _session_id: str) -> HumanIdentity:
        return self.identity.prove(self.peer, self.headers)


class IngressSessions:
    def __init__(
        self,
        identity: SupervisorIdentity,
        installation: Installation,
        clock: LeaseClock,
        entropy: LoginEntropy,
        key: bytes,
        *,
        lifetime: int = 3_600_000,
        capacity: int = 256,
    ) -> None:
        validate_session_lifetime(lifetime)
        if type(key) is not bytes or len(key) < 32:
            raise InvalidInput("invalid_ingress_session_key")
        self.identity, self.installation = identity, installation
        self.clock, self.entropy = clock, entropy
        self.leases = MemorySessions(max_sessions=capacity)
        self._key, self._lifetime = key, lifetime
        self._bindings: dict[str, str] = {}
        self._lock = RLock()
        self._closed = False

    def request(self, peer: str, headers: tuple[tuple[str, str], ...]) -> IngressRequest:
        subject = self.identity.subject(peer, headers)
        prefixes = [value for name, value in headers if name.lower() == "x-ingress-path"]
        if len(prefixes) != 1 or not re.fullmatch(
            r"/api/hassio_ingress/[A-Za-z0-9_-]{16,256}", prefixes[0]
        ):
            raise IdentityRejected("invalid_ingress_subject")
        cookies = []
        for name, value in headers:
            if name.lower() == "cookie":
                for pair in value.split(";"):
                    cookie_name, separator, content = pair.strip().partition("=")
                    if cookie_name == "ingress_session" and separator:
                        cookies.append(content)
        if len(cookies) != 1 or not re.fullmatch(r"[a-f0-9]{128}", cookies[0]):
            raise Unauthenticated("session_required")
        context = "\0".join(
            (
                self.installation.instance_id,
                self.installation.channel,
                subject,
                prefixes[0],
                cookies[0],
            )
        )
        binding = hmac.new(
            self._key, b"binding\0" + context.encode("ascii"), hashlib.sha256
        ).hexdigest()
        return IngressRequest(self, binding, _RequestProof(self.identity, peer, headers))

    def _open(self) -> None:
        if self._closed:
            raise IdentityRejected("session_required")

    def _prune(self) -> None:
        self.leases.discard_expired(self.clock.now())
        for binding, session_id in tuple(self._bindings.items()):
            if self.leases.get(session_id) is None:
                del self._bindings[binding]

    def _existing(self, binding: str) -> str:
        with self._lock:
            self._open()
            session_id = self._bindings.get(binding)
            lease = self.leases.get(session_id) if session_id is not None else None
            if lease is None:
                self._bindings.pop(binding, None)
                raise Unauthenticated("session_required")
            if not lease.valid_at(self.clock.now()):
                self.leases.remove(lease.session_id)
                del self._bindings[binding]
                raise Unauthenticated("session_expired")
            return lease.session_id

    def _status(self, binding: str, proof: _RequestProof) -> SessionStatus:
        with self._lock:
            self._open()
            self._prune()
            session_id = self._bindings.get(binding)
        if session_id is not None:
            return SessionGuard(self.leases, proof, self.clock).status(session_id)
        human = proof.prove("")
        material = self.entropy.new()
        validate_login_material(material)
        now = self.clock.now()
        candidate = SessionLease("n_" + material, human, now, now + self._lifetime)
        with self._lock:
            self._open()
            self._prune()
            concurrent_id = self._bindings.get(binding)
            concurrent = self.leases.get(concurrent_id) if concurrent_id is not None else None
            if concurrent is not None:
                if not self.leases.refresh(concurrent, human):
                    raise IdentityRejected("session_changed")
                return SessionStatus(human, True, concurrent.expires_at)
            self.leases.add(candidate)
            self._bindings[binding] = candidate.session_id
        return SessionStatus(human, True, candidate.expires_at)

    def _csrf(self, binding: str) -> str:
        session_id = self._existing(binding)
        context = (binding + "\0" + session_id).encode("ascii")
        return hmac.new(self._key, b"csrf\0" + context, hashlib.sha256).hexdigest()

    def close(self) -> None:
        with self._lock:
            self._closed = True
            for session_id in self._bindings.values():
                self.leases.remove(session_id)
            self._bindings.clear()


@dataclass(frozen=True, slots=True)
class IngressRequest:
    _sessions: IngressSessions = field(repr=False)
    _binding: str = field(repr=False)
    _proof: _RequestProof = field(repr=False)

    def status(self) -> SessionStatus:
        return self._sessions._status(self._binding, self._proof)

    def read(self) -> HumanIdentity:
        return self.status().human

    def current(self) -> HumanIdentity:
        session_id = self._sessions._existing(self._binding)
        return SessionGuard(self._sessions.leases, self._proof, self._sessions.clock).write(
            session_id
        )

    def csrf(self) -> str:
        self.status()
        return self._sessions._csrf(self._binding)

    def verify_csrf(self, value: str) -> None:
        expected = self._sessions._csrf(self._binding)
        if not re.fullmatch(r"[a-f0-9]{64}", value) or not hmac.compare_digest(expected, value):
            raise Forbidden("request_forbidden")
