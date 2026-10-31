"""Private in-memory OAuth credentials bind to server-owned, nonextendable leases."""

import logging
from dataclasses import dataclass, field
from threading import Lock, RLock
from urllib.parse import urlencode

from domus.application.authentication_values import validate_login_material
from domus.application.identity_ports import LeaseClock
from domus.application.session_values import SessionLease
from domus.application.sessions import SessionGuard
from domus.domain.errors import Conflict, DomusError, IdentityRejected, InvalidInput
from domus.domain.identity import HumanIdentity
from domus.infrastructure.ha_http import HomeAssistantOAuth, OAuthTokens
from domus.infrastructure.ha_websocket import HomeAssistantWebSocket
from domus.infrastructure.memory_sessions import MemorySessions

_LOGGER = logging.getLogger("domus.auth")


@dataclass(frozen=True, slots=True)
class _Credentials:
    tokens: OAuthTokens = field(repr=False)
    renew_at: int
    gate: Lock = field(default_factory=Lock, repr=False, compare=False)


@dataclass
class StandaloneIdentity:
    oauth: HomeAssistantOAuth = field(repr=False)
    socket: HomeAssistantWebSocket = field(repr=False)
    clock: LeaseClock
    leases: MemorySessions = field(default_factory=MemorySessions, repr=False)
    _credentials: dict[str, _Credentials] = field(default_factory=dict, init=False, repr=False)
    _lock: RLock = field(default_factory=RLock, init=False, repr=False)
    _closed: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.oauth.configuration.ha != self.socket.endpoint:
            raise InvalidInput("identity_endpoint_mismatch")

    def authorization_url(self, state: str, challenge: str) -> str:
        validate_login_material(state)
        validate_login_material(challenge)
        config = self.oauth.configuration
        return (
            config.ha.origin
            + "/auth/authorize?"
            + urlencode(
                {
                    "client_id": config.client_id,
                    "redirect_uri": config.callback_url,
                    "state": state,
                    "code_challenge": challenge,
                    "code_challenge_method": "S256",
                }
            )
        )

    def _record(self, tokens: OAuthTokens, gate: Lock | None = None) -> _Credentials:
        return _Credentials(
            tokens,
            self.clock.now() + max(0, tokens.expires_in * 1000 - 30_000),
            gate if gate is not None else Lock(),
        )

    def _revoke(self, tokens: OAuthTokens) -> bool:
        try:
            self.oauth.revoke(tokens.refresh_token)
        except DomusError:
            _LOGGER.warning("ha_grant_cleanup_unavailable")
            return False
        return True

    def sign_in(
        self, code: str, verifier: str, session_id: str, issued_at: int, expires_at: int
    ) -> SessionLease:
        with self._lock:
            if self._closed:
                raise IdentityRejected("server_closed")
            if self.leases.get(session_id) is not None:
                raise Conflict("session_exists")
        tokens = self.oauth.exchange(code, verifier)
        try:
            human = self.socket.current_user(tokens)
            lease = SessionLease(session_id, human, issued_at, expires_at)
            if not lease.valid_at(self.clock.now()):
                raise IdentityRejected("session_expired")
            with self._lock:
                if self._closed:
                    raise IdentityRejected("server_closed")
                self.leases.discard_expired(self.clock.now())
                for key in tuple(self._credentials):
                    if self.leases.get(key) is None:
                        del self._credentials[key]
                self.leases.add(lease)
                self._credentials[session_id] = self._record(tokens)
            return lease
        except BaseException:
            self._revoke(tokens)
            raise

    def get(self, session_id: str) -> SessionLease | None:
        with self._lock:
            return self.leases.get(session_id)

    def refresh(self, expected: SessionLease, human: HumanIdentity) -> bool:
        with self._lock:
            return self.leases.refresh(expected, human)

    def remove(self, session_id: str) -> None:
        """Erase local credentials; this does not promise upstream grant revocation."""
        with self._lock:
            self.leases.remove(session_id)
            self._credentials.pop(session_id, None)

    def prove(self, session_id: str) -> HumanIdentity:
        with self._lock:
            selected = self._credentials.get(session_id)
            if selected is None:
                raise IdentityRejected("session_required")
        with selected.gate:
            with self._lock:
                selected = self._credentials.get(session_id)
                if selected is None:
                    raise IdentityRejected("session_required")
            tokens = selected.tokens
            if self.clock.now() >= selected.renew_at:
                tokens = self.oauth.refresh(tokens.refresh_token, tokens.provider)
            human = self.socket.current_user(tokens)
            with self._lock:
                if self._credentials.get(session_id) is not selected:
                    raise IdentityRejected("session_changed")
                if tokens is not selected.tokens:
                    self._credentials[session_id] = self._record(tokens, selected.gate)
            return human

    def sign_out(self, session_id: str) -> bool | None:
        with self._lock:
            credentials = self._credentials.get(session_id)
            self.remove(session_id)
        return None if credentials is None else self._revoke(credentials.tokens)

    def directory(self, session_id: str, ha_user_ids: tuple[str, ...]) -> tuple[HumanIdentity, ...]:
        if not ha_user_ids:
            return ()
        SessionGuard(self, self, self.clock).write(session_id)
        with self._lock:
            selected = self._credentials.get(session_id)
            if selected is None:
                raise IdentityRejected("session_changed")
        with selected.gate:
            with self._lock:
                if self._credentials.get(session_id) is not selected:
                    raise IdentityRejected("session_changed")
            humans = self.socket.directory_users(selected.tokens.access_token, ha_user_ids)
            with self._lock:
                lease = self.leases.get(session_id)
                if self._credentials.get(session_id) is not selected or lease is None:
                    raise IdentityRejected("session_changed")
                if not lease.valid_at(self.clock.now()):
                    self.remove(session_id)
                    raise IdentityRejected("session_expired")
            return humans

    def shutdown(self) -> tuple[int, int]:
        """Erase every local credential; at most two bounded remote revoke calls."""
        with self._lock:
            self._closed = True
            records = tuple(self._credentials.items())
            self._credentials.clear()
            for session_id, _ in records:
                self.leases.remove(session_id)
        revoked = sum(self._revoke(record.tokens) for _, record in records[:2])
        return revoked, len(records) - revoked
