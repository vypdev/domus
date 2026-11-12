"""Preview one manual rule using only currently authorized household facts."""

from dataclasses import dataclass
from functools import cache

from domus.application.authorization import HouseholdAccess
from domus.application.fixed_materialization import MaintenanceScope
from domus.application.ports import Transactions, UnitOfWork
from domus.application.task_authorization import TaskAccess
from domus.domain.automation import AutomationRule, AutomationSimulation, simulate
from domus.domain.errors import NotFound
from domus.domain.identity import HumanIdentity, Permission


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
        access = HouseholdAccess(self.human)
        access.require(unit, home, Permission.HOUSEHOLD_READ)
        access.require(unit, home, Permission.AUTOMATIONS_CONFIGURE)
        TaskAccess(self.human).require(unit, home, Permission.TASKS_CREATE)
        return home

    def access(self) -> AutomationPreviewAccess:
        with self.transactions.read() as unit:
            return AutomationPreviewAccess(self._require(unit))

    def preview(self, rule: AutomationRule) -> AutomationSimulation:
        with self.transactions.read() as unit:
            home = self._require(unit)
            stock = unit.inventory

            @cache
            def below_minimum(product_id: str) -> bool:
                product = stock.product(home, product_id)
                if product is None:
                    raise NotFound("inventory_product_missing")
                available = stock.balance(home, product.reference_id) - stock.reserved(
                    home, product.reference_id
                )
                return stock.replenishment(home, product_id).needed(available) > 0

            return simulate(rule, below_minimum)
