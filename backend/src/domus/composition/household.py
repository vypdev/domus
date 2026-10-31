"""Wire the same application services to current standalone session proof and private SQLite."""

from collections.abc import Callable

from domus.application.household_commands import HouseholdCommands
from domus.application.household_queries import HouseholdQueries
from domus.application.member_commands import MemberCommands
from domus.application.policy_commands import PolicyCommands
from domus.application.ports import Transactions
from domus.application.sessions import SessionGuard
from domus.entrypoints.household_http import HouseholdHTTPContext
from domus.infrastructure.application_runtime import SecureIdentifiers, SystemClock, TimeZoneCatalog
from domus.infrastructure.session_access import SessionActor, SessionDirectory
from domus.infrastructure.standalone_sessions import StandaloneIdentity


def standalone_context(
    store: Transactions, guard: SessionGuard, identity: StandaloneIdentity
) -> Callable[[str], HouseholdHTTPContext]:
    clock, identifiers, zones = SystemClock(), SecureIdentifiers(), TimeZoneCatalog()

    def context(session_id: str) -> HouseholdHTTPContext:
        actor, directory = SessionActor(guard, session_id), SessionDirectory(identity, session_id)
        return HouseholdHTTPContext(
            lambda: HouseholdQueries(store, actor.read()),
            HouseholdCommands(store, actor, directory, zones, clock, identifiers),
            MemberCommands(store, actor, directory, clock, identifiers),
            PolicyCommands(store, actor, directory, clock, identifiers),
        )

    return context
