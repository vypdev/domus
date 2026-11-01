"""Public presentation and owner-private preferences contain no identity or authority grants."""

from dataclasses import dataclass
from enum import StrEnum
from unicodedata import category

from domus.domain.errors import InvalidInput
from domus.domain.identity import validate_revision
from domus.domain.storage import validate_identifier


class MemberLocale(StrEnum):
    ENGLISH = "en"
    SPANISH = "es"


def _scope(member_id: str, household_id: str, revision: int) -> None:
    validate_identifier(member_id)
    validate_identifier(household_id)
    validate_revision(revision)


@dataclass(frozen=True, slots=True)
class MemberPresentation:
    member_id: str
    household_id: str
    alias: str | None = None
    revision: int = 1

    def __post_init__(self) -> None:
        _scope(self.member_id, self.household_id, self.revision)
        if self.alias is None:
            return
        if not isinstance(self.alias, str):
            raise InvalidInput("invalid_member_alias")
        try:
            self.alias.encode("utf-8")
        except UnicodeError:
            raise InvalidInput("invalid_member_alias") from None
        if any(category(character) == "Cc" for character in self.alias):
            raise InvalidInput("invalid_member_alias")
        normalized = self.alias.strip()
        if not normalized or len(normalized) > 80:
            raise InvalidInput("invalid_member_alias")
        object.__setattr__(self, "alias", normalized)


@dataclass(frozen=True, slots=True)
class MemberPreferences:
    member_id: str
    household_id: str
    locale: MemberLocale | None = None
    routine_participation_summaries: bool = True
    revision: int = 1

    def __post_init__(self) -> None:
        _scope(self.member_id, self.household_id, self.revision)
        if (self.locale is not None and not isinstance(self.locale, MemberLocale)) or type(
            self.routine_participation_summaries
        ) is not bool:
            raise InvalidInput("invalid_member_preferences")
