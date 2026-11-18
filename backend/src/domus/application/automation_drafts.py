"""Save inactive rules and recover the exact original, under current local authority."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from domus.application.automation_preview import (
    AutomationCommandAuthority,
    owned_product,
    require_configuration,
)
from domus.application.commands import AtomicCommands, Change
from domus.application.fixed_materialization import MaintenanceScope
from domus.application.identity_ports import CurrentHuman
from domus.application.ports import Clock, Identifiers, Transactions, UnitOfWork
from domus.application.task_ports import TaskCursors
from domus.domain.automation import AutomationDraft, AutomationRule
from domus.domain.errors import InvalidInput, NotFound
from domus.domain.identity import (
    HumanIdentity,
    effective_role,
    validate_revision,
)
from domus.domain.storage import CommandKey, JsonDocument, Receipt, validate_identifier

SAVE_DRAFT = "automation.draft.save"


@dataclass(frozen=True, slots=True)
class SaveDraft:
    rule_id: str | None
    expected_revision: int
    rule: AutomationRule

    def __post_init__(self) -> None:
        if self.rule_id is None:
            if type(self.expected_revision) is not int or self.expected_revision != 0:
                raise InvalidInput("invalid_revision")
        else:
            validate_identifier(self.rule_id)
            validate_revision(self.expected_revision)

    def document(self) -> JsonDocument:
        return JsonDocument.from_value(
            {
                **self.rule.document().decode(),
                "rule_id": self.rule_id,
                "expected_revision": self.expected_revision,
            }
        )


@dataclass(frozen=True, slots=True)
class DraftSummary:
    rule_id: str
    revision: str
    title: str
    state: Literal["draft"] = "draft"
    enabled: Literal[False] = False


@dataclass(frozen=True, slots=True)
class DraftPage:
    drafts: tuple[DraftSummary, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class AutomationDrafts:
    transactions: Transactions
    scope: MaintenanceScope
    actor: CurrentHuman
    read_actor: Callable[[], HumanIdentity]
    clock: Clock
    identifiers: Identifiers
    cursors: TaskCursors

    def list(self, *, limit: int, cursor: str | None) -> DraftPage:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise InvalidInput("invalid_page_size")
        human = self.read_actor()
        with self.transactions.read() as unit:
            home = self.scope.require(unit).household_id
            member = require_configuration(unit, home, human)
            policy = unit.policies.get(home)
            assert policy is not None
            role = effective_role(human, member, policy)
            assert role is not None
            binding = JsonDocument.from_value(
                {
                    "query": "automation-drafts-v1",
                    "installation": self.scope.installation.instance_id,
                    "channel": self.scope.installation.channel,
                    "household": home,
                    "member": member.member_id,
                    "membership_revision": member.revision,
                    "policy_revision": policy.revision,
                    "role": role.value,
                    "limit": limit,
                }
            )
            after = "" if cursor is None else self.cursors.decode(binding, cursor)
            drafts = unit.automation_drafts.page(home, after, limit + 1)
            next_cursor = (
                self.cursors.encode(binding, drafts[limit - 1].rule_id)
                if len(drafts) > limit
                else None
            )
            return DraftPage(
                tuple(
                    DraftSummary(item.rule_id, str(item.revision), item.rule.task.title)
                    for item in drafts[:limit]
                ),
                next_cursor,
            )

    def reopen(self, rule_id: str) -> AutomationDraft:
        human = self.read_actor()
        with self.transactions.read() as unit:
            home = self.scope.require(unit).household_id
            require_configuration(unit, home, human)
            validate_identifier(rule_id)
            draft = unit.automation_drafts.latest(home, rule_id)
            if draft is None:
                raise NotFound("automation_draft_missing")
            return draft

    def _authority(self, human: HumanIdentity, key: str) -> AutomationCommandAuthority:
        command = CommandKey(self.scope.household_id, human.ha_user_id, SAVE_DRAFT, key)
        return AutomationCommandAuthority(human, self.scope, command)

    def save(self, key: str, request: SaveDraft) -> Receipt:
        authority = self._authority(self.actor.current(), key)
        home = authority.command.household_id
        commands = AtomicCommands(self.transactions, authority, self.clock, self.identifiers)

        def apply(unit: UnitOfWork) -> Change:
            rule_id = self.identifiers.new() if request.rule_id is None else request.rule_id
            for product_id in request.rule.stock_products():
                owned_product(unit, home, product_id)
            draft = AutomationDraft(rule_id, request.expected_revision + 1, request.rule)
            unit.automation_drafts.append(home, draft)
            fact = JsonDocument.from_value({"rule_id": rule_id, "revision": str(draft.revision)})
            result = JsonDocument.from_value(
                {
                    **fact.decode(),
                    "member_id": authority.owner(unit).member_id,
                    "state": "draft",
                    "enabled": False,
                }
            )
            return Change(result, fact, fact, requires_delivery=False)

        return commands.execute(authority.command, request.document(), apply)

    def original(self, key: str) -> Receipt:
        authority = self._authority(self.read_actor(), key)
        with self.transactions.read() as unit:
            authority.require(authority.command, unit)
            receipt = unit.receipts.get(authority.command)
            if receipt is None:
                raise NotFound("operation_missing")
            return receipt
