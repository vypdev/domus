"""Reuse a deployment's already bound authority, transactions and original-operation context."""

from collections.abc import Callable
from dataclasses import dataclass, field

from domus.application.household_administration_queries import HouseholdAdministrationQueries
from domus.application.household_queries import HouseholdQueries
from domus.application.household_roster import HouseholdRosterQueries
from domus.application.member_profile_commands import MemberProfileCommands
from domus.application.member_source_ports import MemberProfileSource
from domus.domain.identity import HumanIdentity
from domus.domain.member_sources import (
    MemberSourceSnapshot,
    ProfileDirectory,
    ProfileResult,
    SourceState,
)
from domus.entrypoints.administration_http import AdministrationHTTPContext
from domus.entrypoints.household_http import HouseholdHTTPContext


@dataclass(frozen=True, slots=True)
class _ReadProof:
    queries: Callable[[], HouseholdQueries] = field(repr=False)

    def read(self) -> HumanIdentity:
        return self.queries().human


@dataclass(frozen=True, slots=True)
class _UnavailableSource:
    actor: _ReadProof = field(repr=False)

    def read(self) -> MemberSourceSnapshot:
        return MemberSourceSnapshot(
            self.actor.read().ha_user_id,
            ProfileDirectory(SourceState.UNAVAILABLE),
            ProfileResult(SourceState.UNAVAILABLE),
        )


def administration_services(
    household: HouseholdHTTPContext, source: MemberProfileSource | None = None
) -> AdministrationHTTPContext:
    existing = household.household

    def queries() -> HouseholdAdministrationQueries:
        current = household.queries()
        return HouseholdAdministrationQueries(
            current.transactions, current.human, current.household_id
        )

    reader = _ReadProof(household.queries)
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
        HouseholdRosterQueries(
            existing.transactions,
            reader,
            source if source is not None else _UnavailableSource(reader),
            existing.household_id,
        ),
    )
