"""Project the authorized product catalog from the existing stock and reservation records."""

from dataclasses import dataclass

from domus.application.authorization import HouseholdAccess
from domus.application.fixed_materialization import MaintenanceScope
from domus.application.ports import Transactions
from domus.application.task_ports import TaskCursors
from domus.domain.identity import HumanIdentity, Permission, allows, effective_role
from domus.domain.inventory import PANTRY, BaseUnit, stock_quantity
from domus.domain.storage import JsonDocument


@dataclass(frozen=True, slots=True)
class CatalogStock:
    product_id: str
    name: str
    base_unit: BaseUnit
    recorded: str
    reserved: str
    available: str


@dataclass(frozen=True, slots=True)
class InventoryView:
    location_id: str
    may_manage: bool
    products: tuple[CatalogStock, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class InventoryQueries:
    store: Transactions
    scope: MaintenanceScope
    human: HumanIdentity
    cursors: TaskCursors

    def report(self, *, limit: int, cursor: str | None) -> InventoryView:
        with self.store.read() as unit:
            home = self.scope.require(unit).household_id
            member = HouseholdAccess(self.human).require(unit, home, Permission.HOUSEHOLD_READ)
            policy = unit.policies.get(home)
            assert policy is not None
            role = effective_role(self.human, member, policy)
            assert role is not None
            binding = JsonDocument.from_value(
                {
                    "query": "inventory-catalog-v1",
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
            stock = unit.inventory
            products = stock.products(home, after, limit + 1)
            next_cursor = (
                self.cursors.encode(binding, products[limit - 1].product_id)
                if len(products) > limit
                else None
            )
            page: list[CatalogStock] = []
            for product in products[:limit]:
                recorded = stock.balance(home, product.reference_id)
                reserved = stock.reserved(home, product.reference_id)
                page.append(
                    CatalogStock(
                        product.product_id,
                        product.name,
                        product.base_unit,
                        stock_quantity(recorded),
                        stock_quantity(reserved),
                        stock_quantity(recorded - reserved),
                    )
                )
            return InventoryView(
                PANTRY,
                allows(self.human, member, policy, Permission.INVENTORY_MANAGE, home),
                tuple(page),
                next_cursor,
            )
