"""Project the current shopping list from one household read transaction."""

from dataclasses import dataclass

from domus.application.ports import UnitOfWork
from domus.domain.inventory import BaseUnit, CatalogProduct, EffectKind, stock_quantity, stock_units
from domus.domain.shopping_needs import NeedKind, ShoppingExtra, ShoppingNeed, allocate_needs


@dataclass(frozen=True, slots=True)
class ExtraAttribution:
    member_id: str
    author_alias: str | None
    created_at: str


@dataclass(frozen=True, slots=True)
class ShoppingListItem:
    product_id: str | None
    extra_id: str | None
    name: str
    base_unit: BaseUnit
    pantry: str
    tasks: str
    manual: str
    total: str
    attribution: ExtraAttribution | None = None


@dataclass(frozen=True, slots=True)
class ShoppingListView:
    items: tuple[ShoppingListItem, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class ShoppingSourceView:
    source_id: str
    kind: NeedKind
    origin_id: str
    line_id: str | None
    name: str
    quantity: str
    reserved: str
    stock: str
    incoming: str
    to_buy: str
    attribution: ExtraAttribution | None


@dataclass(frozen=True, slots=True)
class ShoppingSourcesView:
    item: ShoppingListItem
    sources: tuple[ShoppingSourceView, ...]
    next_cursor: str | None


def _attribution(unit: UnitOfWork, home: str, extra: ShoppingExtra) -> ExtraAttribution:
    author = unit.presentations.get(home, extra.member_id)
    assert author is not None
    return ExtraAttribution(extra.member_id, author.alias, str(extra.created_at))


def free_extra(unit: UnitOfWork, home: str, extra: ShoppingExtra) -> ShoppingListItem:
    amount = stock_quantity(extra.quantity)
    return ShoppingListItem(
        None,
        extra.extra_id,
        extra.name,
        extra.base_unit,
        "0",
        "0",
        amount,
        amount,
        _attribution(unit, home, extra),
    )


@dataclass(frozen=True, slots=True)
class ShoppingProjection:
    product: CatalogProduct
    sources: tuple[ShoppingNeed, ...]
    extras: dict[str, ShoppingExtra]

    @property
    def item(self) -> ShoppingListItem:
        totals = dict.fromkeys(NeedKind, 0)
        for source in self.sources:
            totals[source.kind] += source.to_buy
        return ShoppingListItem(
            self.product.product_id,
            None,
            self.product.name,
            self.product.base_unit,
            stock_quantity(totals[NeedKind.PANTRY]),
            stock_quantity(totals[NeedKind.TASK]),
            stock_quantity(totals[NeedKind.EXTRA]),
            stock_quantity(sum(totals.values())),
        )

    def view(self, unit: UnitOfWork, home: str, source: ShoppingNeed) -> ShoppingSourceView:
        return ShoppingSourceView(
            source.source_id,
            source.kind,
            source.origin_id,
            source.line_id,
            source.name,
            stock_quantity(source.quantity),
            stock_quantity(source.reserved),
            stock_quantity(source.stock),
            stock_quantity(source.incoming),
            stock_quantity(source.to_buy),
            _attribution(unit, home, self.extras[source.origin_id])
            if source.kind is NeedKind.EXTRA
            else None,
        )


def task_needs(
    unit: UnitOfWork, home: str, products: tuple[CatalogProduct, ...]
) -> dict[str, list[ShoppingNeed]]:
    bindings = {product.reference_id: product.binding(home) for product in products}
    occurrences = unit.tasks.shopping_occurrences(home, tuple(bindings))
    effects = {
        (effect.occurrence_id, effect.line_id, effect.reference_id, effect.kind): effect.remaining
        for effect in unit.inventory.effects_for_references(home, tuple(bindings))
    }
    by_reference: dict[str, list[ShoppingNeed]] = {}
    for occurrence in occurrences:
        task = occurrence.definition_snapshot
        for line in sorted(task.materials, key=lambda item: item.line_id):
            reference = line.binding.reference_id
            if bindings.get(reference) != line.binding:
                continue
            identity = occurrence.occurrence_id, line.line_id, reference
            quantity = effects.get(
                (*identity, EffectKind.DEMAND), stock_units(line.planned_quantity)
            )
            reservation = min(quantity, effects.get((*identity, EffectKind.RESERVATION), 0))
            by_reference.setdefault(reference, []).append(
                ShoppingNeed(
                    NeedKind.TASK,
                    occurrence.occurrence_id,
                    task.content.title,
                    quantity,
                    line.line_id,
                    reservation,
                )
            )
    return by_reference


def project(
    unit: UnitOfWork,
    home: str,
    product: CatalogProduct,
    tasks: tuple[ShoppingNeed, ...],
) -> ShoppingProjection:
    stock = unit.inventory
    reference = product.reference_id
    available = stock.balance(home, reference) - stock.reserved(home, reference)
    pantry = stock.replenishment(home, product.product_id).needed(available)
    automatic = tasks
    if pantry:
        automatic = (
            ShoppingNeed(NeedKind.PANTRY, product.product_id, product.name, pantry),
            *tasks,
        )
    incoming = unit.shopping.outstanding(home, product.product_id)
    needs = list(allocate_needs(automatic, available, incoming))
    extras = {extra.extra_id: extra for extra in unit.shopping.extras(home, product.product_id)}
    needs.extend(
        ShoppingNeed(NeedKind.EXTRA, extra.extra_id, extra.name, extra.quantity)
        for extra in extras.values()
    )
    return ShoppingProjection(product, tuple(needs), extras)
