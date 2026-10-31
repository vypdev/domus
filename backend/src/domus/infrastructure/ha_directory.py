"""A fixed HA directory adapter supplies human facts, never household privileges."""

from dataclasses import dataclass, field

from domus.domain.identity import HumanIdentity
from domus.infrastructure.ha_http import _secret
from domus.infrastructure.ha_websocket import HomeAssistantWebSocket


@dataclass(frozen=True, slots=True)
class HomeAssistantDirectory:
    lookup: HomeAssistantWebSocket
    transport_token: str = field(repr=False)

    def __post_init__(self) -> None:
        _secret(self.transport_token)

    def get(self, ha_user_id: str) -> HumanIdentity:
        return self.lookup.directory_user(self.transport_token, ha_user_id)

    def eligible(self, ha_user_ids: tuple[str, ...]) -> tuple[HumanIdentity, ...]:
        return self.lookup.directory_users(self.transport_token, ha_user_ids)
