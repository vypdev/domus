"""Authorize configuration and freeze the effective allocation under the completion writer."""

import json
from dataclasses import asdict, dataclass

from domus.application.authorization import HouseholdAccess, MembershipAuthorization
from domus.application.commands import AtomicCommands, Change
from domus.application.family_ports import FamilyAllocationEvidence
from domus.application.identity_ports import CurrentHuman
from domus.application.ports import Clock, Identifiers, Transactions, UnitOfWork
from domus.application.task_authorization import TaskAccess
from domus.application.task_facts import resolved_rules
from domus.domain.errors import Conflict, Forbidden, InvalidInput, NotFound
from domus.domain.identity import HumanIdentity, Permission
from domus.domain.point_allocation import (
    AllocationMode,
    AllocationPolicy,
    AllocationSetting,
    CompletionAllocation,
    allocate_points,
)
from domus.domain.storage import CommandKey, JsonDocument, Receipt, validate_identifier

ALLOCATION_ACTION = "points.allocation.update"


def household_allocation(unit: UnitOfWork, home: str, base: int) -> tuple[AllocationPolicy, int]:
    default = unit.point_allocations.setting(home, None)
    if default is None:
        return AllocationPolicy(precision=2 if base % 100 else 0), 0
    assert default.policy is not None
    return default.policy, default.revision


def effective_allocation(
    unit: UnitOfWork, home: str, definition_id: str, base: int
) -> tuple[AllocationPolicy, int, str | None]:
    override = unit.point_allocations.setting(home, definition_id)
    if override is not None and override.policy is not None:
        return override.policy, override.revision, definition_id
    policy, revision = household_allocation(unit, home, base)
    return policy, revision, None


def resolve_allocation(
    unit: UnitOfWork,
    home: str,
    definition_id: str,
    base: int,
    performers: tuple[str, ...],
    manual_shares: tuple[tuple[str, int], ...] | None,
) -> CompletionAllocation:
    policy, revision, override = effective_allocation(unit, home, definition_id, base)
    previous = None
    if policy.mode is AllocationMode.CONSERVE_TOTAL:
        last = unit.point_allocations.last_conserved(home, definition_id)
        previous = (
            unit.points.next_recipient(home, definition_id)
            if last is None
            else last.allocation.next_recipient
        )
    shares = allocate_points(
        policy,
        base,
        performers,
        next_recipient=previous,
        manual_shares=manual_shares or (),
    )
    return CompletionAllocation(policy, revision, override, base, previous, shares)


def allocation_document(snapshot: CompletionAllocation) -> JsonDocument:
    return JsonDocument(json.dumps(asdict(snapshot)))


@dataclass(frozen=True, slots=True)
class AllocationCommands:
    store: Transactions
    actor: CurrentHuman
    clock: Clock
    identifiers: Identifiers
    household_id: str = "home"

    def configure(
        self,
        key: str,
        definition_id: str | None,
        policy: AllocationPolicy | None,
        expected_revision: int,
    ) -> Receipt:
        if definition_id is not None:
            validate_identifier(definition_id)
        elif policy is None:
            raise InvalidInput("invalid_points_policy")
        if type(expected_revision) is not int or not 0 <= expected_revision < 2**63 - 1:
            raise InvalidInput("invalid_revision")
        setting = AllocationSetting(policy, expected_revision + 1)
        action = ALLOCATION_ACTION
        human = self.actor.current()
        authorization = MembershipAuthorization(
            HouseholdAccess(human), action, Permission.POINTS_MANAGE
        )
        command = CommandKey(self.household_id, human.ha_user_id, action, key)
        payload = JsonDocument(
            json.dumps({"definition_id": definition_id, "setting": asdict(setting)})
        )

        def apply(unit: UnitOfWork) -> Change:
            if (
                definition_id is not None
                and unit.tasks.definition(self.household_id, definition_id) is None
            ):
                raise Forbidden("permission_denied")
            current = unit.point_allocations.setting(self.household_id, definition_id)
            actual = 0 if current is None else current.revision
            if expected_revision != actual:
                raise Conflict("revision_conflict")
            unit.point_allocations.put_setting(self.household_id, definition_id, setting)
            return Change(payload, payload, payload)

        return AtomicCommands(self.store, authorization, self.clock, self.identifiers).execute(
            command, payload, apply
        )


@dataclass(frozen=True, slots=True)
class AllocationSettingsView:
    household: AllocationSetting | None
    override: AllocationSetting | None


@dataclass(frozen=True, slots=True)
class AllocationPreview:
    allocation: FamilyAllocationEvidence
    actual_total: int
    fingerprint: str


@dataclass(frozen=True, slots=True)
class AllocationQueries:
    store: Transactions
    human: HumanIdentity
    household_id: str = "home"

    def settings(self, definition_id: str | None) -> AllocationSettingsView:
        with self.store.read() as unit:
            HouseholdAccess(self.human).require(unit, self.household_id, Permission.POINTS_MANAGE)
            selected = None
            if definition_id is not None:
                if unit.tasks.definition(self.household_id, definition_id) is None:
                    raise Forbidden("permission_denied")
                selected = unit.point_allocations.setting(self.household_id, definition_id)
            return AllocationSettingsView(
                unit.point_allocations.setting(self.household_id, None), selected
            )

    def original(self, key: str) -> Receipt:
        with self.store.read() as unit:
            HouseholdAccess(self.human).require(unit, self.household_id, Permission.POINTS_MANAGE)
            receipt = unit.receipts.get(
                CommandKey(self.household_id, self.human.ha_user_id, ALLOCATION_ACTION, key)
            )
            if receipt is None:
                raise NotFound("operation_missing")
            return receipt

    def preview(
        self,
        occurrence_id: str,
        expected_revision: int,
        performers: tuple[str, ...],
        manual_shares: tuple[tuple[str, int], ...] | None,
    ) -> AllocationPreview:
        with self.store.read() as unit:
            work = unit.tasks.occurrence(self.household_id, occurrence_id)
            if work is None:
                raise Forbidden("permission_denied")
            TaskAccess(self.human).performers(unit, work, performers)
            if manual_shares is not None:
                HouseholdAccess(self.human).require(
                    unit, self.household_id, Permission.POINTS_MANAGE
                )
            if work.revision != expected_revision:
                raise Conflict("revision_conflict")
            rules, _ = resolved_rules(unit, work)
            snapshot = resolve_allocation(
                unit,
                self.household_id,
                work.definition_snapshot.definition_id,
                rules.point_value_minor,
                performers,
                manual_shares,
            )
            return AllocationPreview(
                FamilyAllocationEvidence.from_snapshot(snapshot),
                snapshot.allocation.total,
                allocation_document(snapshot).fingerprint,
            )
