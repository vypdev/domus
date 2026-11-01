"""Preparation binds the source schema/identity/generation even when operation facts coincide."""

from dataclasses import replace

import pytest
from test_owned_generations import fixture as generation_fixture
from test_sqlite_restoration import fixture as restoration_fixture
from test_sqlite_snapshots import Clock

from domus.domain.errors import InvalidInput
from domus.domain.restoration import PreparedRestoration, RestoreSource
from domus.infrastructure.owned_storage import open_storage
from domus.infrastructure.sqlite_restoration import SQLiteRestorations
from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots


def test_bare_source_and_managed_generation_source_are_explicit_and_roundtrip(tmp_path):
    bare_root = tmp_path / "bare"
    bare_root.mkdir(mode=0o700)
    adapter, store, _, _ = restoration_fixture(bare_root)
    result = adapter.prepare("restore-bare")
    assert result.source == RestoreSource(store.installation, 7, None, None)
    assert result.document().decode()["format_version"] == 2
    assert PreparedRestoration.from_value(result.document().decode()) == result
    root, slot, selection = generation_fixture(tmp_path)
    storage = open_storage(root, "edge")
    try:
        archive = tmp_path / "snapshot"
        snapshot = SQLiteSnapshots(storage.database, archive, storage.installation, Clock()).create(
            "snapshot"
        )
        prepared = SQLiteRestorations(
            storage.database,
            archive,
            tmp_path / "prepared",
            storage.installation,
            Clock(),
            snapshot,
        ).prepare("restore-generation")
        assert prepared.source.generation_id == selection.generation_id
        assert prepared.source.identity_sha256 == selection.document().fingerprint
        assert prepared.source.schema_version == 7
        assert PreparedRestoration.from_value(prepared.document().decode()) == prepared
    finally:
        storage.close()


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", True),
        ("schema_version", 0),
        ("schema_version", 2**31),
        ("generation_id", "../escape"),
        ("identity_sha256", "wrong"),
        ("identity_sha256", 1),
    ],
)
def test_source_binding_rejects_invalid_shape_and_unbound_generation(tmp_path, field, value):
    adapter, store, _, _ = restoration_fixture(tmp_path)
    source = RestoreSource(store.installation, 4, "generation-1", "a" * 64)
    with pytest.raises(InvalidInput):
        replace(source, **{field: value})
    with pytest.raises(InvalidInput):
        RestoreSource(store.installation, 4, "generation-1", None)


def test_generation_identity_changes_the_frontier_even_for_identical_operation_rows(tmp_path):
    root, slot, selection = generation_fixture(tmp_path)
    storage = open_storage(root, "edge")
    try:
        archive = tmp_path / "snapshot"
        snapshot = SQLiteSnapshots(storage.database, archive, storage.installation, Clock()).create(
            "snapshot"
        )
        first = SQLiteRestorations(
            storage.database, archive, tmp_path / "one", storage.installation, Clock(), snapshot
        ).prepare("one")
    finally:
        storage.close()

    later = replace(selection, generation_id="generation-2")
    second = slot.with_name(later.generation_id)
    second.mkdir(mode=0o700)
    for name in ("domus.sqlite3", "installation.json"):
        (second / name).write_bytes((slot / name).read_bytes())
        (second / name).chmod(0o600)
    (second / "generation.json").write_text(later.document().encoded)
    (second / "generation.json").chmod(0o600)
    (root / "installation.json").write_text(later.document().encoded)
    storage = open_storage(root, "edge")
    try:
        next_result = SQLiteRestorations(
            storage.database, archive, tmp_path / "two", storage.installation, Clock(), snapshot
        ).prepare("two")
        assert next_result.source_frontier_sha256 != first.source_frontier_sha256
        assert next_result.source.generation_id == later.generation_id
    finally:
        storage.close()


@pytest.mark.parametrize("value", [[], {}, {"extra": True}])
def test_source_parser_rejects_incomplete_or_unknown_fields(value):
    with pytest.raises(InvalidInput):
        RestoreSource.from_value(value)


@pytest.mark.parametrize("damage", ["missing_identity", "foreign_identity", "foreign_marker"])
def test_source_binding_rejects_invalid_managed_subject(tmp_path, damage):
    import json

    from domus.domain.errors import DatabaseRejected
    from domus.infrastructure.restore_source import source_binding
    from domus.infrastructure.sqlite_snapshots import _directory

    root, slot, selection = generation_fixture(tmp_path)
    if damage == "missing_identity":
        (slot / "installation.json").unlink()
    elif damage == "foreign_identity":
        value = json.loads((slot / "installation.json").read_text())
        value["channel"] = "stable"
        (slot / "installation.json").write_text(json.dumps(value))
    else:
        (slot / "generation.json").write_text(
            replace(selection, installation=replace(selection.installation, channel="stable"))
            .document()
            .encoded
        )
    with _directory(slot, private=True) as directory:
        with pytest.raises(DatabaseRejected):
            source_binding(directory, selection.installation, 4)
