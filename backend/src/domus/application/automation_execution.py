"""Enable pinned revisions and admit a single explicit household automation action."""

from collections.abc import Callable
from dataclasses import dataclass

from domus.application.automation_preview import (
    AutomationCommandAuthority,
    evaluate_rule,
    owned_product,
)
from domus.application.commands import AtomicCommands, Change
from domus.application.fixed_materialization import MaintenanceScope
from domus.application.identity_ports import CurrentHuman
from domus.application.ports import Clock, Identifiers, Transactions, UnitOfWork
from domus.application.task_commands import TaskCommands
from domus.application.task_requests import CreateTask
from domus.domain.automation import AutomationControl, AutomationDraft
from domus.domain.errors import Conflict, InvalidInput, NotFound
from domus.domain.identity import HumanIdentity, validate_revision
from domus.domain.storage import CommandKey, JsonDocument, JsonObject, Receipt, validate_identifier

SET_AUTOMATION_CONTROL = "automation.control.set"
RUN_AUTOMATION = "automation.run"


@dataclass(frozen=True, slots=True)
class ConfigureAutomation:
    rule_id: str
    rule_revision: int
    expected_control_revision: int
    enabled: bool

    def __post_init__(self) -> None:
        validate_identifier(self.rule_id)
        validate_revision(self.rule_revision)
        if type(self.expected_control_revision) is not int or type(self.enabled) is not bool:
            raise InvalidInput("invalid_automation_control")
        if self.expected_control_revision != 0:
            validate_revision(self.expected_control_revision)

    def document(self) -> JsonDocument:
        return JsonDocument.from_value(
            {
                "rule_id": self.rule_id,
                "rule_revision": str(self.rule_revision),
                "expected_control_revision": str(self.expected_control_revision),
                "enabled": self.enabled,
            }
        )


@dataclass(frozen=True, slots=True)
class RunAutomation:
    rule_id: str
    rule_revision: int
    control_revision: int

    def __post_init__(self) -> None:
        validate_identifier(self.rule_id)
        validate_revision(self.rule_revision)
        validate_revision(self.control_revision)

    def document(self) -> JsonDocument:
        return JsonDocument.from_value(
            {
                "rule_id": self.rule_id,
                "rule_revision": str(self.rule_revision),
                "control_revision": str(self.control_revision),
            }
        )


@dataclass(frozen=True, slots=True)
class ConfiguredAutomation:
    rule_revision: int
    control_revision: int
    enabled: bool
    title: str


@dataclass(frozen=True, slots=True)
class AutomationExecutionState:
    rule_id: str
    latest_revision: int
    latest_title: str
    control: ConfiguredAutomation | None
    latest_manual: bool


def _manual_revision(unit: UnitOfWork, home: str, rule_id: str, revision: int) -> AutomationDraft:
    draft = unit.automation_drafts.revision(home, rule_id, revision)
    if draft is None:
        raise NotFound("automation_draft_missing")
    if draft.rule.trigger != "manual":
        raise InvalidInput("automation_requires_manual_trigger")
    return draft


def _control_result(control: AutomationControl) -> JsonObject:
    return {
        "rule_id": control.rule_id,
        "rule_revision": str(control.rule_revision),
        "control_revision": str(control.control_revision),
        "enabled": control.enabled,
    }


@dataclass(frozen=True, slots=True)
class AutomationExecution:
    transactions: Transactions
    scope: MaintenanceScope
    actor: CurrentHuman
    read_actor: Callable[[], HumanIdentity]
    clock: Clock
    identifiers: Identifiers
    tasks: TaskCommands

    def _authority(self, human: HumanIdentity, action: str, key: str) -> AutomationCommandAuthority:
        command = CommandKey(self.scope.household_id, human.ha_user_id, action, key)
        return AutomationCommandAuthority(human, self.scope, command)

    def state(self, rule_id: str) -> AutomationExecutionState:
        validate_identifier(rule_id)
        authority = self._authority(self.read_actor(), SET_AUTOMATION_CONTROL, "read")
        home = authority.command.household_id
        with self.transactions.read() as unit:
            authority.owner(unit)
            draft = unit.automation_drafts.latest(home, rule_id)
            if draft is None:
                raise NotFound("automation_draft_missing")
            control = unit.automation_controls.get(home, rule_id)
            configured = None
            if control is not None:
                saved = _manual_revision(unit, home, rule_id, control.rule_revision)
                configured = ConfiguredAutomation(
                    control.rule_revision,
                    control.control_revision,
                    control.enabled,
                    saved.rule.task.title,
                )
            return AutomationExecutionState(
                rule_id,
                draft.revision,
                draft.rule.task.title,
                configured,
                draft.rule.trigger == "manual",
            )

    def configure(self, key: str, request: ConfigureAutomation) -> Receipt:
        authority = self._authority(self.actor.current(), SET_AUTOMATION_CONTROL, key)
        home = authority.command.household_id

        def apply(unit: UnitOfWork) -> Change:
            previous = unit.automation_controls.get(home, request.rule_id)
            current_revision = 0 if previous is None else previous.control_revision
            if request.expected_control_revision != current_revision:
                raise Conflict("revision_conflict")
            if request.enabled:
                draft = _manual_revision(unit, home, request.rule_id, request.rule_revision)
                for product_id in draft.rule.stock_products():
                    owned_product(unit, home, product_id)
            elif previous is None or not previous.enabled:
                raise Conflict("automation_disabled")
            elif request.rule_revision != previous.rule_revision:
                raise Conflict("revision_conflict")
            control = AutomationControl(
                request.rule_id, request.rule_revision, current_revision + 1, request.enabled
            )
            unit.automation_controls.save(home, control, current_revision)
            result = _control_result(control)
            fact = JsonDocument.from_value(result)
            receipt = JsonDocument.from_value(
                {**result, "member_id": authority.owner(unit).member_id}
            )
            return Change(receipt, fact, fact, requires_delivery=False)

        return AtomicCommands(self.transactions, authority, self.clock, self.identifiers).execute(
            authority.command, request.document(), apply
        )

    def run(self, key: str, request: RunAutomation) -> Receipt:
        authority = self._authority(self.actor.current(), RUN_AUTOMATION, key)
        home = authority.command.household_id

        def apply(unit: UnitOfWork) -> Change:
            control = unit.automation_controls.get(home, request.rule_id)
            if control is None or not control.enabled:
                raise Conflict("automation_disabled")
            if (
                control.control_revision != request.control_revision
                or control.rule_revision != request.rule_revision
            ):
                raise Conflict("revision_conflict")
            draft = _manual_revision(unit, home, control.rule_id, control.rule_revision)
            condition_matched = evaluate_rule(unit, home, draft.rule).would_create
            run_id = self.identifiers.new()
            task = (
                self.tasks.create_in_unit(
                    unit, authority.human, run_id, CreateTask(draft.rule.task)
                )
                if condition_matched
                else None
            )
            facts: JsonObject = {
                "rule_id": control.rule_id,
                "rule_revision": str(control.rule_revision),
                "control_revision": str(control.control_revision),
                "run_id": run_id,
                "condition_matched": condition_matched,
                "task_occurrence_id": None
                if task is None
                else task.result.decode()["occurrence_id"],
                "task_operation_id": None if task is None else task.operation_id,
            }
            fact = JsonDocument.from_value(facts)
            outcome = JsonDocument.from_value(
                {**facts, "member_id": authority.owner(unit).member_id}
            )
            return Change(outcome, fact, fact, requires_delivery=False)

        return AtomicCommands(self.transactions, authority, self.clock, self.identifiers).execute(
            authority.command, request.document(), apply
        )

    def original(self, action: str, key: str) -> Receipt:
        if action not in (SET_AUTOMATION_CONTROL, RUN_AUTOMATION):
            raise InvalidInput("invalid_automation_action")
        authority = self._authority(self.read_actor(), action, key)
        with self.transactions.read() as unit:
            authority.require(authority.command, unit)
            receipt = unit.receipts.get(authority.command)
            if receipt is None:
                raise NotFound("operation_missing")
            return receipt
