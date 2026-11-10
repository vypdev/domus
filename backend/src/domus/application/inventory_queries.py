"""Project protected product stock and its append-only movement history."""

from dataclasses import dataclass

from domus.application.authorization import HouseholdAccess
from domus.application.fixed_materialization import MaintenanceScope
from domus.application.ports import Transactions, UnitOfWork
from domus.application.shopping_list import (
    ShoppingListItem,
    ShoppingListView,
    ShoppingSourcesView,
    free_extra,
    project,
    task_needs,
)
from domus.application.task_ports import TaskCursors
from domus.domain.errors import NotFound
from domus.domain.identity import HumanIdentity, Permission, allows, effective_role
from domus.domain.inventory import PANTRY, BaseUnit, MovementKind, stock_quantity
from domus.domain.shopping import Purchase, PurchaseReceipt, PurchaseSession
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
    reference_id: str
    name: str
    base_unit: BaseUnit
    recorded: str
    reserved: str
    available: str
    replenishment: ReplenishmentView
    outstanding_purchase: str
    shopping_needed: str


@dataclass(frozen=True, slots=True)
class InventoryView:
    location_id: str
    may_manage: bool
    may_shop: bool
    may_request: bool
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
    shopping_receipt: bool


@dataclass(frozen=True, slots=True)
class MovementHistory:
    product_id: str
    product_name: str
    base_unit: BaseUnit
    movements: tuple[MovementView, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class PurchaseView:
    purchase_id: str
    product_id: str | None
    name: str
    base_unit: BaseUnit
    purchased: str
    received: str
    remaining: str
    pending_stock: str
    cancelled: str
    revision: str
    member_id: str
    author_alias: str | None
    created_at: str


@dataclass(frozen=True, slots=True)
class PurchasesView:
    purchases: tuple[PurchaseView, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class PurchaseSessionView:
    session_id: str
    member_id: str
    author_alias: str | None
    created_at: str


@dataclass(frozen=True, slots=True)
class PurchaseSessionsView:
    sessions: tuple[PurchaseSessionView, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class PurchaseSessionDetail:
    session: PurchaseSessionView
    items: tuple[PurchaseView, ...]


@dataclass(frozen=True, slots=True)
class PhysicalReceiptVoidView:
    reason: str
    member_id: str
    author_alias: str | None
    created_at: str


@dataclass(frozen=True, slots=True)
class PostedReceiptCorrectionView:
    movement_id: str
    reason: str
    member_id: str
    author_alias: str | None
    created_at: str
    legacy: bool


@dataclass(frozen=True, slots=True)
class PhysicalReceiptView:
    receipt_id: str
    quantity: str
    member_id: str
    author_alias: str | None
    created_at: str
    movement_id: str | None
    voided: PhysicalReceiptVoidView | None
    correction: PostedReceiptCorrectionView | None


@dataclass(frozen=True, slots=True)
class PurchaseCancellationView:
    quantity: str
    reason: str
    member_id: str
    author_alias: str | None
    created_at: str


@dataclass(frozen=True, slots=True)
class PhysicalReceiptsView:
    purchase: PurchaseView
    receipts: tuple[PhysicalReceiptView, ...]
    next_cursor: str | None
    cancellation: PurchaseCancellationView | None


def _posted_correction_view(
    unit: UnitOfWork, home: str, receipt: PurchaseReceipt
) -> PostedReceiptCorrectionView | None:
    if receipt.movement_id is None:
        return None
    correction_id = unit.inventory.correction_id(home, receipt.movement_id)
    if correction_id is None:
        return None
    movement = unit.inventory.movement_by_id(home, correction_id)
    assert movement is not None
    author = unit.presentations.get(home, movement.member_id)
    assert author is not None
    return PostedReceiptCorrectionView(
        correction_id,
        movement.reason,
        movement.member_id,
        author.alias,
        str(movement.created_at),
        unit.shopping.receipt_correction(home, receipt.receipt_id) != correction_id,
    )


def _purchase_view(unit: UnitOfWork, home: str, purchase: Purchase) -> PurchaseView:
    author = unit.presentations.get(home, purchase.member_id)
    assert author is not None
    return PurchaseView(
        purchase.purchase_id,
        purchase.product_id,
        purchase.name,
        purchase.base_unit,
        stock_quantity(purchase.purchased),
        stock_quantity(purchase.received),
        stock_quantity(purchase.remaining),
        stock_quantity(purchase.pending),
        stock_quantity(purchase.cancelled),
        str(purchase.revision),
        purchase.member_id,
        author.alias,
        str(purchase.created_at),
    )


def _session_view(unit: UnitOfWork, home: str, session: PurchaseSession) -> PurchaseSessionView:
    author = unit.presentations.get(home, session.member_id)
    assert author is not None
    return PurchaseSessionView(
        session.session_id, session.member_id, author.alias, str(session.created_at)
    )


@dataclass(frozen=True, slots=True)
class _InventoryGrants:
    manage: bool
    shop: bool
    request: bool
    tasks: bool


@dataclass(frozen=True, slots=True)
class InventoryQueries:
    store: Transactions
    scope: MaintenanceScope
    human: HumanIdentity
    cursors: TaskCursors

    def _access(
        self, unit: UnitOfWork, query: str, limit: int, product_id: str | None
    ) -> tuple[str, _InventoryGrants, JsonDocument]:
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
        return (
            home,
            _InventoryGrants(
                allows(self.human, member, policy, Permission.INVENTORY_MANAGE, home),
                allows(self.human, member, policy, Permission.SHOPPING_MANAGE, home),
                allows(self.human, member, policy, Permission.SHOPPING_REQUEST, home),
                allows(self.human, member, policy, Permission.TASKS_READ, home),
            ),
            binding,
        )

    def report(self, *, limit: int, cursor: str | None) -> InventoryView:
        with self.store.read() as unit:
            home, grants, binding = self._access(unit, "inventory-catalog-v1", limit, None)
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
                needed = policy.needed(available)
                outstanding = unit.shopping.outstanding(home, product.product_id)
                page.append(
                    CatalogStock(
                        product.product_id,
                        product.reference_id,
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
                            stock_quantity(needed),
                        ),
                        stock_quantity(outstanding),
                        stock_quantity(max(0, needed - outstanding)),
                    )
                )
            return InventoryView(
                PANTRY, grants.manage, grants.shop, grants.request, tuple(page), next_cursor
            )

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
                        movement.kind is MovementKind.INTAKE
                        and unit.shopping.is_receipt_movement(home, movement.movement_id),
                    )
                )
            return MovementHistory(
                product_id, product.name, product.base_unit, tuple(page), next_cursor
            )

    def purchases(self, *, limit: int, cursor: str | None) -> PurchasesView:
        with self.store.read() as unit:
            home, _, binding = self._access(unit, "shopping-purchases-v1", limit, None)
            through = 2**63 - 1 if cursor is None else int(self.cursors.decode(binding, cursor))
            rows = unit.shopping.purchases(home, through, limit + 1)
            next_cursor = (
                self.cursors.encode(binding, str(rows[limit - 1][0] - 1))
                if len(rows) > limit
                else None
            )
            page = tuple(_purchase_view(unit, home, purchase) for _, purchase in rows[:limit])
            return PurchasesView(page, next_cursor)

    def purchase_sessions(self, *, limit: int, cursor: str | None) -> PurchaseSessionsView:
        with self.store.read() as unit:
            home, _, binding = self._access(unit, "shopping-sessions-v1", limit, None)
            through = 2**63 - 1 if cursor is None else int(self.cursors.decode(binding, cursor))
            rows = unit.shopping.purchase_sessions(home, through, limit + 1)
            next_cursor = (
                self.cursors.encode(binding, str(rows[limit - 1][0] - 1))
                if len(rows) > limit
                else None
            )
            return PurchaseSessionsView(
                tuple(_session_view(unit, home, session) for _, session in rows[:limit]),
                next_cursor,
            )

    def purchase_session(self, session_id: str) -> PurchaseSessionDetail:
        with self.store.read() as unit:
            home, _, _ = self._access(unit, "shopping-session-v1", 0, session_id)
            session = unit.shopping.purchase_session(home, session_id)
            if session is None:
                raise NotFound("shopping_session_missing")
            return PurchaseSessionDetail(
                _session_view(unit, home, session),
                tuple(
                    _purchase_view(unit, home, purchase)
                    for purchase in unit.shopping.session_items(home, session_id)
                ),
            )

    def physical_receipts(
        self, purchase_id: str, *, limit: int, cursor: str | None
    ) -> PhysicalReceiptsView:
        with self.store.read() as unit:
            home, _, binding = self._access(unit, "shopping-receipts-v1", limit, purchase_id)
            purchase = unit.shopping.purchase(home, purchase_id)
            if purchase is None:
                raise NotFound("shopping_purchase_missing")
            through = 2**63 - 1 if cursor is None else int(self.cursors.decode(binding, cursor))
            rows = unit.shopping.receipts(home, purchase_id, through, limit + 1)
            next_cursor = (
                self.cursors.encode(binding, str(rows[limit - 1][0] - 1))
                if len(rows) > limit
                else None
            )
            page: list[PhysicalReceiptView] = []
            for _, receipt in rows[:limit]:
                correction = unit.shopping.receipt_void(home, receipt.receipt_id)
                voided = None
                if correction is not None:
                    member = unit.presentations.get(home, correction.member_id)
                    assert member is not None
                    voided = PhysicalReceiptVoidView(
                        correction.reason,
                        correction.member_id,
                        member.alias,
                        str(correction.created_at),
                    )
                author = unit.presentations.get(home, receipt.member_id)
                assert author is not None
                page.append(
                    PhysicalReceiptView(
                        receipt.receipt_id,
                        stock_quantity(receipt.quantity),
                        receipt.member_id,
                        author.alias,
                        str(receipt.created_at),
                        receipt.movement_id,
                        voided,
                        _posted_correction_view(unit, home, receipt),
                    )
                )
            cancellation = unit.shopping.cancellation(home, purchase_id)
            closed = None
            if cancellation is not None:
                author = unit.presentations.get(home, cancellation.member_id)
                assert author is not None
                closed = PurchaseCancellationView(
                    stock_quantity(cancellation.quantity),
                    cancellation.reason,
                    cancellation.member_id,
                    author.alias,
                    str(cancellation.created_at),
                )
            return PhysicalReceiptsView(
                _purchase_view(unit, home, purchase), tuple(page), next_cursor, closed
            )

    def shopping_list(self, *, limit: int, cursor: str | None) -> ShoppingListView:
        with self.store.read() as unit:
            home, grants, binding = self._access(unit, "shopping-list-v1", limit, None)
            after = "" if cursor is None else self.cursors.decode(binding, cursor)
            rows = unit.shopping.list_candidates(home, after, limit + 1)
            next_cursor = (
                self.cursors.encode(binding, rows[limit - 1][0]) if len(rows) > limit else None
            )
            products = {}
            for _, item_id, tracked in rows[:limit]:
                if tracked:
                    product = unit.inventory.product(home, item_id)
                    assert product is not None
                    products[item_id] = product
            task_sources = task_needs(unit, home, tuple(products.values())) if grants.tasks else {}
            items: list[ShoppingListItem] = []
            for _, item_id, tracked in rows[:limit]:
                if tracked:
                    product = products[item_id]
                    projected = project(
                        unit, home, product, tuple(task_sources.get(product.reference_id, ()))
                    )
                    if projected.sources:
                        items.append(projected.item)
                else:
                    extra = unit.shopping.extra(home, item_id)
                    assert extra is not None
                    items.append(free_extra(unit, home, extra))
            return ShoppingListView(tuple(items), next_cursor)

    def shopping_sources(
        self, product_id: str, *, limit: int, cursor: str | None
    ) -> ShoppingSourcesView:
        with self.store.read() as unit:
            home, grants, binding = self._access(unit, "shopping-sources-v1", limit, product_id)
            product = unit.inventory.product(home, product_id)
            if product is None:
                raise NotFound("inventory_product_missing")
            task_sources = task_needs(unit, home, (product,)) if grants.tasks else {}
            projected = project(
                unit, home, product, tuple(task_sources.get(product.reference_id, ()))
            )
            after = "" if cursor is None else self.cursors.decode(binding, cursor)
            sources = sorted(
                (source for source in projected.sources if source.source_id > after),
                key=lambda source: source.source_id,
            )
            next_cursor = (
                self.cursors.encode(binding, sources[limit - 1].source_id)
                if len(sources) > limit
                else None
            )
            return ShoppingSourcesView(
                projected.item,
                tuple(projected.view(unit, home, source) for source in sources[:limit]),
                next_cursor,
            )
