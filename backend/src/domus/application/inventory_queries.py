"""Project protected product stock and its append-only movement history."""

from dataclasses import dataclass

from domus.application.authorization import HouseholdAccess
from domus.application.fixed_materialization import MaintenanceScope
from domus.application.ports import Transactions, UnitOfWork
from domus.application.task_ports import TaskCursors
from domus.domain.errors import NotFound
from domus.domain.identity import HumanIdentity, Permission, allows, effective_role
from domus.domain.inventory import PANTRY, BaseUnit, MovementKind, stock_quantity
from domus.domain.storage import JsonDocument


@dataclass(frozen=True, slots=True)
class ReplenishmentView:
    source_id: str
    minimum: str
    target: str
    revision: str
    needed: str


@dataclass(frozen=True, slots=True)
class CatalogStock:
    product_id: str
    name: str
    base_unit: BaseUnit
    recorded: str
    reserved: str
    available: str
    replenishment: ReplenishmentView


@dataclass(frozen=True, slots=True)
class InventoryView:
    location_id: str
    may_manage: bool
    products: tuple[CatalogStock, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class MovementView:
    movement_id: str
    quantity: str
    kind: MovementKind
    member_id: str
    author_alias: str | None
    created_at: str
    reason: str | None
    task_occurrence_id: str | None
    corrects: str | None
    corrected_by: str | None


@dataclass(frozen=True, slots=True)
class MovementHistory:
    product_id: str
    product_name: str
    base_unit: BaseUnit
    movements: tuple[MovementView, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class InventoryQueries:
    store: Transactions
    scope: MaintenanceScope
    human: HumanIdentity
    cursors: TaskCursors

    def _access(
        self, unit: UnitOfWork, query: str, limit: int, product_id: str | None
    ) -> tuple[str, bool, JsonDocument]:
        home = self.scope.require(unit).household_id
        member = HouseholdAccess(self.human).require(unit, home, Permission.HOUSEHOLD_READ)
        policy = unit.policies.get(home)
        assert policy is not None
        role = effective_role(self.human, member, policy)
        assert role is not None
        binding = JsonDocument.from_value(
            {
                "query": query,
                "product": product_id,
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
        return home, allows(self.human, member, policy, Permission.INVENTORY_MANAGE, home), binding

    def report(self, *, limit: int, cursor: str | None) -> InventoryView:
        with self.store.read() as unit:
            home, may_manage, binding = self._access(unit, "inventory-catalog-v1", limit, None)
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
                available = recorded - reserved
                policy = stock.replenishment(home, product.product_id)
                page.append(
                    CatalogStock(
                        product.product_id,
                        product.name,
                        product.base_unit,
                        stock_quantity(recorded),
                        stock_quantity(reserved),
                        stock_quantity(available),
                        ReplenishmentView(
                            product.product_id,
                            stock_quantity(policy.minimum),
                            stock_quantity(policy.target),
                            str(policy.revision),
                            stock_quantity(policy.needed(available)),
                        ),
                    )
                )
            return InventoryView(PANTRY, may_manage, tuple(page), next_cursor)

    def history(self, product_id: str, *, limit: int, cursor: str | None) -> MovementHistory:
        with self.store.read() as unit:
            home, _, binding = self._access(unit, "inventory-history-v1", limit, product_id)
            stock = unit.inventory
            product = stock.product(home, product_id)
            if product is None:
                raise NotFound("inventory_product_missing")
            through = 2**63 - 1 if cursor is None else int(self.cursors.decode(binding, cursor))
            records = stock.history(home, product.reference_id, through, limit + 1)
            next_cursor = (
                self.cursors.encode(binding, str(records[limit - 1].position - 1))
                if len(records) > limit
                else None
            )
            page: list[MovementView] = []
            for entry in records[:limit]:
                movement = entry.movement
                author = unit.presentations.get(home, movement.member_id)
                assert author is not None
                page.append(
                    MovementView(
                        movement.movement_id,
                        stock_quantity(movement.delta),
                        movement.kind,
                        movement.member_id,
                        author.alias,
                        str(movement.created_at),
                        movement.reason
                        if movement.kind
                        in (MovementKind.ADJUSTMENT, MovementKind.INTAKE_CORRECTION)
                        else None,
                        None if movement.posting is None else movement.posting.occurrence_id,
                        movement.corrects,
                        entry.corrected_by,
                    )
                )
            return MovementHistory(
                product_id, product.name, product.base_unit, tuple(page), next_cursor
            )
