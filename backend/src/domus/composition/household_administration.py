"""Reuse a deployment's already bound authority, transactions and original-operation context."""

from domus.application.household_administration_queries import HouseholdAdministrationQueries
from domus.application.member_profile_commands import MemberProfileCommands
from domus.entrypoints.administration_http import AdministrationHTTPContext
from domus.entrypoints.household_http import HouseholdHTTPContext


def administration_services(household: HouseholdHTTPContext) -> AdministrationHTTPContext:
    existing = household.household

    def queries() -> HouseholdAdministrationQueries:
        current = household.queries()
        return HouseholdAdministrationQueries(
            current.transactions, current.human, current.household_id
        )

    return AdministrationHTTPContext(
        queries,
        MemberProfileCommands(
            existing.transactions,
            existing.actor,
            existing.clock,
            existing.identifiers,
            existing.household_id,
        ),
        household.queries,
    )
