"""Permitted public presentation and exclusively current-owner private preference reads."""

from dataclasses import dataclass

from domus.application.authorization import HouseholdAccess
from domus.application.member_profile_access import preference_owner
from domus.application.ports import Transactions
from domus.domain.errors import NotFound, StorageFailure
from domus.domain.identity import HumanIdentity, Permission
from domus.domain.member_profiles import MemberPreferences, MemberPresentation
from domus.domain.storage import validate_identifier


@dataclass(frozen=True, slots=True)
class HouseholdAdministrationQueries:
    transactions: Transactions
    human: HumanIdentity
    household_id: str = "home"

    def __post_init__(self) -> None:
        validate_identifier(self.household_id)

    def presentation(self, member_id: str) -> MemberPresentation:
        validate_identifier(member_id)
        with self.transactions.read() as unit:
            HouseholdAccess(self.human).require(unit, self.household_id, Permission.MEMBERS_READ)
            value = unit.presentations.get(self.household_id, member_id)
            if value is None:
                raise NotFound("member_missing")
            return value

    def preferences(self) -> MemberPreferences:
        with self.transactions.read() as unit:
            member = preference_owner(unit, self.human, self.household_id)
            value = unit.preferences.get(self.household_id, member.member_id)
            if value is None:
                raise StorageFailure("invalid_member_profile_record")
            return value
