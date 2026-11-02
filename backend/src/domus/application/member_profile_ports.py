"""Scoped profile storage; application authorization precedes use of either repository."""

from typing import Protocol

from domus.domain.member_profiles import MemberPreferences, MemberPresentation


class MemberPresentations(Protocol):
    def get(self, household_id: str, member_id: str) -> MemberPresentation | None: ...
    def save(self, presentation: MemberPresentation, expected_revision: int) -> None: ...


class MemberPreferencesRepository(Protocol):
    def get(self, household_id: str, member_id: str) -> MemberPreferences | None: ...
    def save(self, preferences: MemberPreferences, expected_revision: int) -> None: ...
