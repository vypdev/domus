"""Revisioned profile effects and private originals commit under current authority."""

from dataclasses import dataclass, replace

from domus.application.commands import AtomicCommands, Change
from domus.application.identity_ports import CurrentHuman
from domus.application.member_profile_access import (
    ALIAS_ACTION,
    PREFERENCES_ACTION,
    ProfileAuthorization,
    preference_owner,
)
from domus.application.ports import Clock, Identifiers, Transactions, UnitOfWork
from domus.domain.errors import Conflict, StorageFailure
from domus.domain.identity import HumanIdentity
from domus.domain.member_profiles import MemberLocale, MemberPreferences, MemberPresentation
from domus.domain.storage import CommandKey, JsonDocument, Receipt, validate_identifier


@dataclass(frozen=True, slots=True)
class AliasUpdate:
    member_id: str
    expected_revision: int
    alias: str | None

    def __post_init__(self) -> None:
        value = MemberPresentation(self.member_id, "validation", self.alias, self.expected_revision)
        object.__setattr__(self, "alias", value.alias)

    def document(self) -> JsonDocument:
        return JsonDocument.from_value(
            {
                "member_id": self.member_id,
                "expected_revision": self.expected_revision,
                "alias": self.alias,
            }
        )


@dataclass(frozen=True, slots=True)
class PreferencesUpdate:
    expected_revision: int
    locale: MemberLocale | None
    routine_participation_summaries: bool

    def __post_init__(self) -> None:
        MemberPreferences(
            "validation",
            "validation",
            self.locale,
            self.routine_participation_summaries,
            self.expected_revision,
        )

    def document(self) -> JsonDocument:
        return JsonDocument.from_value(
            {
                "expected_revision": self.expected_revision,
                "locale": self.locale.value if self.locale is not None else None,
                "routine_participation_summaries": self.routine_participation_summaries,
            }
        )


@dataclass
class MemberProfileCommands:
    transactions: Transactions
    actor: CurrentHuman
    clock: Clock
    identifiers: Identifiers
    household_id: str = "home"

    def __post_init__(self) -> None:
        validate_identifier(self.household_id)

    def _commands(
        self, human: HumanIdentity, action: str, subject_member_id: str | None = None
    ) -> AtomicCommands:
        return AtomicCommands(
            self.transactions,
            ProfileAuthorization(human, action, subject_member_id),
            self.clock,
            self.identifiers,
        )

    def update_alias(self, key: str, request: AliasUpdate) -> Receipt:
        human = self.actor.current()
        command = CommandKey(self.household_id, human.ha_user_id, ALIAS_ACTION, key)

        def apply(unit: UnitOfWork) -> Change:
            current = unit.presentations.get(self.household_id, request.member_id)
            if current is None:
                raise Conflict("member_missing")
            if current.revision != request.expected_revision:
                raise Conflict("revision_conflict")
            changed = replace(current, alias=request.alias, revision=current.revision + 1)
            unit.presentations.save(changed, request.expected_revision)
            result = JsonDocument.from_value(
                {
                    "member_id": changed.member_id,
                    "revision": changed.revision,
                    "alias": changed.alias,
                }
            )
            detail = JsonDocument.from_value(
                {
                    "transition": "member.presentation.updated",
                    "member_id": changed.member_id,
                    "previous_revision": current.revision,
                    "revision": changed.revision,
                }
            )
            return Change(
                result,
                detail,
                JsonDocument.from_value(
                    {"member_id": changed.member_id, "revision": changed.revision}
                ),
            )

        return self._commands(human, ALIAS_ACTION, request.member_id).execute(
            command, request.document(), apply
        )

    def update_preferences(self, key: str, request: PreferencesUpdate) -> Receipt:
        human = self.actor.current()
        command = CommandKey(self.household_id, human.ha_user_id, PREFERENCES_ACTION, key)

        def apply(unit: UnitOfWork) -> Change:
            member = preference_owner(unit, human, self.household_id, write=True)
            current = unit.preferences.get(self.household_id, member.member_id)
            if current is None:
                raise StorageFailure("invalid_member_profile_record")
            if current.revision != request.expected_revision:
                raise Conflict("revision_conflict")
            changed = replace(
                current,
                locale=request.locale,
                routine_participation_summaries=request.routine_participation_summaries,
                revision=current.revision + 1,
            )
            unit.preferences.save(changed, request.expected_revision)
            result = JsonDocument.from_value(
                {
                    "member_id": changed.member_id,
                    "revision": changed.revision,
                    "locale": changed.locale.value if changed.locale is not None else None,
                    "routine_participation_summaries": changed.routine_participation_summaries,
                    "notification_delivery": "unavailable",
                }
            )
            detail = JsonDocument.from_value(
                {
                    "transition": "member.preferences.updated",
                    "member_id": changed.member_id,
                    "previous_revision": current.revision,
                    "revision": changed.revision,
                }
            )
            # Shared surfaces contain mutation facts only, never private values or fingerprints.
            return Change(
                result,
                detail,
                JsonDocument.from_value(
                    {"member_id": changed.member_id, "revision": changed.revision}
                ),
            )

        return self._commands(human, PREFERENCES_ACTION).execute(command, request.document(), apply)
