"""Current-authorized roster/directory projections fence bounded provider reads outside SQLite."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

from domus.application.authorization import HouseholdAccess
from domus.application.household_queries import HouseholdQueries, MemberView
from domus.application.identity_ports import ReadHuman
from domus.application.member_source_ports import MemberProfileSource
from domus.application.ports import Transactions, UnitOfWork
from domus.domain.errors import Conflict, IdentityRejected, StorageFailure
from domus.domain.identity import HouseholdPolicy, HumanIdentity, Member, Permission, allows
from domus.domain.member_profiles import MemberPresentation
from domus.domain.member_sources import (
    MemberSourceSnapshot,
    ProfileDirectory,
    SourceState,
)
from domus.domain.storage import validate_identifier


@dataclass(frozen=True, slots=True)
class RosterMetadata:
    state: SourceState
    name: str | None


@dataclass(frozen=True, slots=True)
class RosterMember:
    member: MemberView
    presentation: MemberPresentation
    metadata: RosterMetadata


@dataclass(frozen=True, slots=True)
class RosterView:
    members: tuple[RosterMember, ...]
    directory_state: SourceState


@dataclass(frozen=True, slots=True)
class _Identity:
    actor: Member
    policy: HouseholdPolicy
    members: tuple[Member, ...]


@dataclass(frozen=True, slots=True)
class HouseholdRosterQueries:
    transactions: Transactions
    actor: ReadHuman
    source: MemberProfileSource
    household_id: str = "home"

    def __post_init__(self) -> None:
        validate_identifier(self.household_id)

    def _identity(
        self, unit: UnitOfWork, human: HumanIdentity, permission: Permission
    ) -> _Identity:
        actor = HouseholdAccess(human).require(unit, self.household_id, permission)
        members = unit.members.list(self.household_id)
        if len(members) > 256:
            raise StorageFailure("invalid_identity_record")
        return _Identity(
            actor, cast(HouseholdPolicy, unit.policies.get(self.household_id)), members
        )

    def _read[T](
        self,
        permission: Permission,
        project: Callable[[UnitOfWork, HumanIdentity, MemberSourceSnapshot, _Identity], T],
    ) -> T:
        human = self.actor.read()
        with self.transactions.read() as unit:
            before = self._identity(unit, human, permission)
        sources = self.source.read()
        if not isinstance(sources, MemberSourceSnapshot):
            raise StorageFailure("invalid_member_source_record")
        if sources.subject != human.ha_user_id:
            raise IdentityRejected("identity_mismatch")
        current = self.actor.read()
        if current.ha_user_id != human.ha_user_id:
            raise IdentityRejected("identity_mismatch")
        with self.transactions.read() as unit:
            after = self._identity(unit, current, permission)
            if after != before:
                raise Conflict("identity_state_changed")
            return project(unit, current, sources, after)

    def roster(self) -> RosterView:
        def project(
            unit: UnitOfWork, human: HumanIdentity, sources: MemberSourceSnapshot, state: _Identity
        ) -> RosterView:
            privileged = allows(
                human, state.actor, state.policy, Permission.MEMBERS_MANAGE, self.household_id
            )
            existing = HouseholdQueries(self.transactions, human, self.household_id)
            result = []
            for member in state.members:
                presentation = unit.presentations.get(self.household_id, member.member_id)
                if presentation is None:
                    raise StorageFailure("invalid_member_profile_record")
                metadata = sources.profile(member.ha_user_id)
                name = metadata.profile.name if metadata.profile is not None else None
                result.append(
                    RosterMember(
                        existing._view(member, privileged=privileged),
                        presentation,
                        RosterMetadata(
                            SourceState.UNAVAILABLE
                            if metadata.state is SourceState.AVAILABLE and name is None
                            else metadata.state,
                            name,
                        ),
                    )
                )
            return RosterView(tuple(result), sources.directory.state)

        return self._read(Permission.MEMBERS_READ, project)

    def directory(self) -> ProfileDirectory:
        def project(
            unit: UnitOfWork, human: HumanIdentity, sources: MemberSourceSnapshot, state: _Identity
        ) -> ProfileDirectory:
            return ProfileDirectory(
                sources.directory.state,
                tuple(profile for profile in sources.directory.profiles if profile.eligible),
            )

        return self._read(Permission.POLICY_MANAGE, project)
