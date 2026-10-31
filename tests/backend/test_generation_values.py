"""An active generation is an exact installation selection, never an arbitrary path."""

from dataclasses import FrozenInstanceError, replace

import pytest

from domus.domain.errors import InvalidInput
from domus.domain.generations import GenerationSelection
from domus.domain.storage import Installation

INSTALLATION = Installation("047cc6fb-dfb0-4fa4-b3c3-e0fe54d116b6", "edge")


def test_selection_roundtrips_without_paths_or_mutable_identity():
    value = GenerationSelection(INSTALLATION, "generation-1")
    assert value.document().decode() == {
        "schema_version": 2,
        "instance_id": INSTALLATION.instance_id,
        "channel": "edge",
        "state": "ready",
        "generation_id": "generation-1",
    }
    assert GenerationSelection.from_value(value.document().decode()) == value
    assert replace(value, installation=Installation(INSTALLATION.instance_id, "stable")) != value
    with pytest.raises(FrozenInstanceError):
        value.generation_id = "other"


@pytest.mark.parametrize(
    "generation", ["", ".", "..", "../other", "/tmp/db", "with space", "x" * 129, None]
)
def test_generation_cannot_escape_its_fixed_parent(generation):
    with pytest.raises(InvalidInput):
        GenerationSelection(INSTALLATION, generation)


def test_selection_requires_an_explicit_installation():
    with pytest.raises(InvalidInput):
        GenerationSelection(None, "valid")


@pytest.mark.parametrize(
    "change", ["list", "extra", "missing", "version", "boolean", "state", "channel"]
)
def test_root_document_is_exact_and_versioned(change):
    value = GenerationSelection(INSTALLATION, "generation-1").document().decode()
    if change == "list":
        value = []
    elif change == "extra":
        value["database_path"] = "elsewhere"
    elif change == "missing":
        del value["generation_id"]
    elif change == "version":
        value["schema_version"] = 3
    elif change == "boolean":
        value["schema_version"] = True
    elif change == "state":
        value["state"] = "preparing"
    else:
        value["channel"] = "wrong"
    with pytest.raises(InvalidInput):
        GenerationSelection.from_value(value)
