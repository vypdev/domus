"""Material quantities and Inventory-owned binding facts never infer permissions or stock."""

from dataclasses import FrozenInstanceError, replace

import pytest

from domus.domain.errors import InvalidInput
from domus.domain.task_material_values import (
    MaterialBinding,
    MaterialLine,
    MaterialQuantity,
    MaterialSelection,
    MaterialUsage,
    validate_material_lines,
    validate_material_selections,
    validate_material_usages,
)


def binding(**changes):
    return replace(
        MaterialBinding("home", "binding", "product", "unit", "location", 1, 6, "Cleaner"),
        **changes,
    )


def line(identity="line", **changes):
    return MaterialLine(identity, binding(**changes), MaterialQuantity("1"))


@pytest.mark.parametrize(
    "value,precision",
    [("0", 0), ("1", 0), ("0.000001", 6), ("1.01", 2), ("999999999999.999999", 6)],
)
def test_quantities_are_bounded_canonical_strings_without_float_arithmetic(value, precision):
    quantity = MaterialQuantity(value)
    assert quantity.value == value and quantity.precision == precision
    assert quantity.is_zero is (value == "0")
    with pytest.raises(FrozenInstanceError):
        quantity.value = "2"


@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        0,
        1.1,
        "",
        "-1",
        "-0",
        "+1",
        "01",
        "00.1",
        ".1",
        "1.",
        "0.0",
        "1.0",
        "1.20",
        "1.0000001",
        "1000000000000",
        "1e2",
        "NaN",
        "Infinity",
        " 1",
        "1\n",
        "１",
    ],
)
def test_noncanonical_or_unbounded_quantities_are_invalid(value):
    with pytest.raises(InvalidInput, match="invalid_material_quantity"):
        MaterialQuantity(value)


@pytest.mark.parametrize(
    "changes",
    [
        {"reference_id": "bad id"},
        {"product_id": ""},
        {"unit_id": None},
        {"location_id": "bad/id"},
        {"revision": True},
        {"revision": 0},
        {"precision": True},
        {"precision": -1},
        {"precision": 7},
        {"label": "x" * 161},
        {"label": "bad\x00label"},
    ],
)
def test_binding_facts_require_known_safe_identity_precision_and_text(changes):
    with pytest.raises(InvalidInput):
        binding(**changes)


def test_binding_target_identity_preserves_stock_target_but_not_display_metadata():
    original = binding()
    assert original.target == binding(revision=2, label="New label").target
    assert original.target != binding(location_id="other").target
    original.require_quantity(MaterialQuantity("0.000001"))
    with pytest.raises(InvalidInput, match="invalid_material_precision"):
        binding(precision=0).require_quantity(MaterialQuantity("0.1"))
    with pytest.raises(InvalidInput):
        original.require_quantity("1")


@pytest.mark.parametrize(
    "build",
    [
        lambda: MaterialLine("bad id", binding(), MaterialQuantity("1")),
        lambda: MaterialLine("line", None, MaterialQuantity("1")),
        lambda: MaterialLine("line", binding(), "1"),
        lambda: MaterialLine("line", binding(precision=0), MaterialQuantity("1.5")),
        lambda: MaterialSelection("bad/id", MaterialQuantity("1")),
        lambda: MaterialSelection("binding", "1"),
        lambda: MaterialUsage("line", "1"),
        lambda: MaterialUsage("bad id", MaterialQuantity("1")),
    ],
)
def test_material_lines_selection_and_usage_cannot_lose_typed_provenance(build):
    with pytest.raises(InvalidInput):
        build()


def test_lists_are_typed_bounded_unique_and_household_scoped():
    lines = (line(),)
    selections = (MaterialSelection("binding", MaterialQuantity("1")),)
    usages = (MaterialUsage("line", MaterialQuantity("0")),)
    validate_material_lines(lines, "home")
    validate_material_selections(selections)
    validate_material_usages(usages, lines)
    validate_material_lines((), "home")
    validate_material_selections(())
    validate_material_usages((), ())
    failures = [
        lambda: validate_material_lines(list(lines), "home"),
        lambda: validate_material_lines((None,), "home"),
        lambda: validate_material_lines(lines * 33, "home"),
        lambda: validate_material_lines(lines * 2, "home"),
        lambda: validate_material_lines((line("first"), line("second")), "home"),
        lambda: validate_material_lines(lines, "other"),
        lambda: validate_material_selections(list(selections)),
        lambda: validate_material_selections((None,)),
        lambda: validate_material_selections(selections * 33),
        lambda: validate_material_selections(selections * 2),
        lambda: validate_material_usages(list(usages), lines),
        lambda: validate_material_usages(usages, (None,)),
        lambda: validate_material_usages(
            usages, (line(), line("other", household_id="other", reference_id="other"))
        ),
        lambda: validate_material_usages((None,), lines),
        lambda: validate_material_usages(usages * 33, lines),
        lambda: validate_material_usages(usages * 2, lines),
        lambda: validate_material_usages((MaterialUsage("foreign", MaterialQuantity("1")),), lines),
        lambda: validate_material_usages(
            (MaterialUsage("line", MaterialQuantity("0.1")),), (line(precision=0),)
        ),
    ]
    for invalid in failures:
        with pytest.raises(InvalidInput):
            invalid()
