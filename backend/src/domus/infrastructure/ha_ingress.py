"""Supervisor peer + stripped subject header + fresh Core proof establish identity."""

from dataclasses import dataclass, field

from domus.domain.errors import IdentityRejected, InvalidInput
from domus.domain.identity import HumanIdentity
from domus.infrastructure.ha_http import _secret
from domus.infrastructure.ha_websocket import HomeAssistantWebSocket, _user_id


@dataclass(frozen=True, slots=True)
class SupervisorIdentity:
    lookup: HomeAssistantWebSocket
    transport_token: str = field(repr=False)

    def __post_init__(self) -> None:
        if not self.lookup.endpoint.supervised:
            raise InvalidInput("ingress_requires_supervisor")
        _secret(self.transport_token)

    def subject(self, peer: str, headers: tuple[tuple[str, str], ...]) -> str:
        """Return only a trusted candidate, never human or administrator proof.

        peer must be the socket peer with proxy rewriting disabled by wiring.
        Forwarded headers and names cannot supply it. Duplicate subjects fail.
        """
        if peer != "172.30.32.2":
            raise IdentityRejected("untrusted_ingress_peer")
        candidates = [value for name, value in headers if name.lower() == "x-remote-user-id"]
        try:
            if len(candidates) != 1:
                raise InvalidInput("invalid_ha_user_id")
            return _user_id(candidates[0])
        except InvalidInput:
            raise IdentityRejected("invalid_ingress_subject") from None

    def prove(self, peer: str, headers: tuple[tuple[str, str], ...]) -> HumanIdentity:
        subject = self.subject(peer, headers)
        human = self.lookup.directory_user(self.transport_token, subject)
        if human.ha_user_id != subject:
            raise IdentityRejected("identity_mismatch")
        return human
