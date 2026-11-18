"""Preview one manual rule using only currently authorized household facts."""

from dataclasses import dataclass
from functools import cache

from domus.application.authorization import HouseholdAccess
from domus.application.fixed_materialization import MaintenanceScope
from domus.application.ports import Transactions, UnitOfWork
from domus.application.task_authorization import TaskAccess
from domus.domain.automation import AutomationRule, AutomationSimulation, simulate
from domus.domain.errors import Forbidden, NotFound
from domus.domain.identity import HumanIdentity, Member, Permission
from domus.domain.inventory import CatalogProduct
from domus.domain.storage import CommandKey


def require_configuration(unit: UnitOfWork, home: str, human: HumanIdentity) -> Member:
    access = HouseholdAccess(human)
    access.require(unit, home, Permission.HOUSEHOLD_READ)
    return access.require(unit, home, Permission.AUTOMATIONS_CONFIGURE)


def owned_product(unit: UnitOfWork, home: str, product_id: str) -> CatalogProduct:
    product = unit.inventory.product(home, product_id)
    if product is None:
        raise NotFound("inventory_product_missing")
    return product


@dataclass(frozen=True, slots=True)
class AutomationCommandAuthority:
    human: HumanIdentity
    scope: MaintenanceScope
    command: CommandKey

    def owner(self, unit: UnitOfWork) -> Member:
        home = self.scope.require(unit).household_id
        member = require_configuration(unit, home, self.human)
        TaskAccess(self.human).require(unit, home, Permission.TASKS_CREATE)
        return member

    def require(self, command: CommandKey, unit: UnitOfWork) -> None:
        if command != self.command:
            raise Forbidden("permission_denied")
        owner = self.owner(unit)
        original = unit.receipts.get(command)
        if original is not None and original.result.decode().get("member_id") != owner.member_id:
            raise Forbidden("permission_denied")


def evaluate_rule(unit: UnitOfWork, home: str, rule: AutomationRule) -> AutomationSimulation:
    stock = unit.inventory

    @cache
    def below_minimum(product_id: str) -> bool:
        product = owned_product(unit, home, product_id)
        available = stock.balance(home, product.reference_id) - stock.reserved(
            home, product.reference_id
        )
        return stock.replenishment(home, product_id).needed(available) > 0

    return simulate(rule, below_minimum)


@dataclass(frozen=True, slots=True)
class AutomationPreviewAccess:
    household_id: str


@dataclass(frozen=True, slots=True)
class AutomationPreview:
    transactions: Transactions
    scope: MaintenanceScope
    human: HumanIdentity

    def _require(self, unit: UnitOfWork) -> str:
        home = self.scope.require(unit).household_id
        require_configuration(unit, home, self.human)
        TaskAccess(self.human).require(unit, home, Permission.TASKS_CREATE)
        return home

    def access(self) -> AutomationPreviewAccess:
        with self.transactions.read() as unit:
            return AutomationPreviewAccess(self._require(unit))

    def preview(self, rule: AutomationRule) -> AutomationSimulation:
        with self.transactions.read() as unit:
            home = self._require(unit)
            return evaluate_rule(unit, home, rule)
