"""Additive read views keep legacy Shopping response shapes unchanged."""

from dataclasses import dataclass

from domus.application.ports import UnitOfWork
from domus.application.shopping_list import (
    ShoppingListItem,
    ShoppingListView,
    ShoppingSourcesView,
    ShoppingSourceView,
)
from domus.domain.shopping_annotations import ShoppingAnnotation
from domus.domain.shopping_needs import NeedKind


@dataclass(frozen=True, slots=True)
class AnnotatedShoppingItem:
    item: ShoppingListItem
    annotation: ShoppingAnnotation | None


@dataclass(frozen=True, slots=True)
class AnnotatedShoppingListView:
    items: tuple[AnnotatedShoppingItem, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class AnnotatedShoppingSource:
    source: ShoppingSourceView
    annotation: ShoppingAnnotation | None


@dataclass(frozen=True, slots=True)
class AnnotatedShoppingSourcesView:
    item: ShoppingListItem
    sources: tuple[AnnotatedShoppingSource, ...]
    next_cursor: str | None


def _annotation(unit: UnitOfWork, home: str, extra_id: str) -> ShoppingAnnotation:
    extra = unit.shopping.extra(home, extra_id)
    assert extra is not None
    return extra.annotation


def annotate_list(unit: UnitOfWork, home: str, view: ShoppingListView) -> AnnotatedShoppingListView:
    return AnnotatedShoppingListView(
        tuple(
            AnnotatedShoppingItem(
                item,
                None if item.extra_id is None else _annotation(unit, home, item.extra_id),
            )
            for item in view.items
        ),
        view.next_cursor,
    )


def annotate_sources(
    unit: UnitOfWork, home: str, view: ShoppingSourcesView
) -> AnnotatedShoppingSourcesView:
    return AnnotatedShoppingSourcesView(
        view.item,
        tuple(
            AnnotatedShoppingSource(
                source,
                _annotation(unit, home, source.origin_id)
                if source.kind is NeedKind.EXTRA
                else None,
            )
            for source in view.sources
        ),
        view.next_cursor,
    )
