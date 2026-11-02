"""Bounded HA presentation facts are independent of identity and household authority."""

from dataclasses import dataclass
from enum import StrEnum
from typing import cast
from unicodedata import category

from domus.domain.errors import InvalidInput
from domus.domain.storage import validate_identifier


class SourceState(StrEnum):
    AVAILABLE = "available"
    ABSENT = "absent"
    DENIED = "denied"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class HAProfile:
    ha_user_id: str
    name: str | None
    eligible: bool

    def __post_init__(self) -> None:
        validate_identifier(self.ha_user_id)
        if type(self.eligible) is not bool:
            raise InvalidInput("invalid_member_source")
        if self.name is None:
            return
        if not isinstance(self.name, str):
            raise InvalidInput("invalid_member_source")
        try:
            self.name.encode("utf-8")
        except UnicodeError:
            raise InvalidInput("invalid_member_source") from None
        if (
            not self.name.strip()
            or len(self.name) > 256
            or any(category(character) == "Cc" for character in self.name)
        ):
            raise InvalidInput("invalid_member_source")


@dataclass(frozen=True, slots=True)
class ProfileResult:
    state: SourceState
    profile: HAProfile | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.state, SourceState):
            raise InvalidInput("invalid_member_source")
        if self.state is SourceState.AVAILABLE:
            if not isinstance(self.profile, HAProfile):
                raise InvalidInput("invalid_member_source")
        elif self.profile is not None:
            raise InvalidInput("invalid_member_source")


@dataclass(frozen=True, slots=True)
class ProfileDirectory:
    state: SourceState
    profiles: tuple[HAProfile, ...] = ()

    def __post_init__(self) -> None:
        if (
            not isinstance(self.state, SourceState)
            or self.state is SourceState.ABSENT
            or type(self.profiles) is not tuple
            or len(self.profiles) > 256
            or any(not isinstance(profile, HAProfile) for profile in self.profiles)
            or len({profile.ha_user_id for profile in self.profiles}) != len(self.profiles)
            or (self.state is not SourceState.AVAILABLE and bool(self.profiles))
        ):
            raise InvalidInput("invalid_member_source")

    def profile(self, ha_user_id: str) -> ProfileResult:
        validate_identifier(ha_user_id)
        if self.state is not SourceState.AVAILABLE:
            return ProfileResult(self.state)
        value = next(
            (profile for profile in self.profiles if profile.ha_user_id == ha_user_id), None
        )
        return (
            ProfileResult(SourceState.ABSENT)
            if value is None
            else ProfileResult(SourceState.AVAILABLE, value)
        )


@dataclass(frozen=True, slots=True)
class MemberSourceSnapshot:
    subject: str
    directory: ProfileDirectory
    own: ProfileResult

    def __post_init__(self) -> None:
        validate_identifier(self.subject)
        if not isinstance(self.directory, ProfileDirectory) or not isinstance(
            self.own, ProfileResult
        ):
            raise InvalidInput("invalid_member_source")
        if (
            self.own.state is SourceState.AVAILABLE
            and cast(HAProfile, self.own.profile).ha_user_id != self.subject
        ):
            raise InvalidInput("invalid_member_source")
        if self.directory.state is SourceState.AVAILABLE and self.own != self.directory.profile(
            self.subject
        ):
            raise InvalidInput("invalid_member_source")

    def profile(self, ha_user_id: str) -> ProfileResult:
        return self.own if ha_user_id == self.subject else self.directory.profile(ha_user_id)
