"""Two fixed bounded reads supply presentation facts; technical credentials never select a human."""

from dataclasses import dataclass, field
from typing import cast

from domus.application.identity_ports import ReadHuman
from domus.domain.errors import Forbidden, IdentityRejected, IdentityUnavailable, InvalidInput
from domus.domain.member_sources import (
    HAProfile,
    MemberSourceSnapshot,
    ProfileDirectory,
    ProfileResult,
    SourceState,
)
from domus.domain.storage import JsonObject, JsonValue
from domus.infrastructure.ha_http import OAuthTokens, _secret
from domus.infrastructure.ha_websocket import HomeAssistantWebSocket, _current_human, _user_id


def _directory(records: JsonValue) -> ProfileDirectory:
    if not isinstance(records, list) or len(records) > 256:
        raise InvalidInput("invalid_member_source")
    profiles = []
    for record in records:
        if not isinstance(record, dict):
            raise InvalidInput("invalid_member_source")
        active, system = record["is_active"], record["system_generated"]
        if type(active) is not bool or type(system) is not bool:
            raise InvalidInput("invalid_member_source")
        profiles.append(
            HAProfile(
                _user_id(record["id"]), cast(str | None, record.get("name")), active and not system
            )
        )
    return ProfileDirectory(SourceState.AVAILABLE, tuple(profiles))


@dataclass(frozen=True, slots=True)
class HomeAssistantMemberProfiles:
    lookup: HomeAssistantWebSocket = field(repr=False)
    transport_token: str = field(repr=False)
    subject: str
    grant: OAuthTokens | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        _secret(self.transport_token)
        _user_id(self.subject)
        if self.grant is not None and (
            not isinstance(self.grant, OAuthTokens)
            or self.grant.access_token != self.transport_token
        ):
            raise InvalidInput("invalid_member_source")

    def _directory(self) -> ProfileDirectory:
        try:
            return _directory(self.lookup._request(self.transport_token, "config/auth/list"))
        except Forbidden:
            return ProfileDirectory(SourceState.DENIED)
        except IdentityRejected, IdentityUnavailable, InvalidInput, KeyError:
            return ProfileDirectory(SourceState.UNAVAILABLE)

    def _own(self, fallback: SourceState) -> ProfileResult:
        if self.grant is None:
            return ProfileResult(fallback)
        try:
            raw = self.lookup._request(self.transport_token, "auth/current_user")
            human = _current_human(raw, self.grant.provider)
            if human.ha_user_id != self.subject:
                raise IdentityRejected("identity_mismatch")
            profile = HAProfile(
                human.ha_user_id, cast(str | None, cast(JsonObject, raw).get("name")), True
            )
            return ProfileResult(SourceState.AVAILABLE, profile)
        except Forbidden:
            return ProfileResult(SourceState.DENIED)
        except IdentityRejected, IdentityUnavailable, InvalidInput:
            return ProfileResult(SourceState.UNAVAILABLE)

    def read(self) -> MemberSourceSnapshot:
        directory = self._directory()
        own = (
            directory.profile(self.subject)
            if directory.state is SourceState.AVAILABLE
            else self._own(directory.state)
        )
        return MemberSourceSnapshot(self.subject, directory, own)


@dataclass(frozen=True, slots=True)
class NativeMemberProfiles:
    lookup: HomeAssistantWebSocket = field(repr=False)
    transport_token: str = field(repr=False)
    actor: ReadHuman = field(repr=False)

    def read(self) -> MemberSourceSnapshot:
        human = self.actor.read()
        return HomeAssistantMemberProfiles(
            self.lookup, self.transport_token, human.ha_user_id
        ).read()
