"""Snapshot manifests describe one immutable checkpoint without filesystem or credential data."""

from dataclasses import replace

import pytest

from domus.domain.errors import InvalidInput
from domus.domain.snapshots import Snapshot
from domus.domain.storage import Installation

INSTALLATION = Installation("047cc6fb-dfb0-4fa4-b3c3-e0fe54d116b6", "edge")


def snapshot() -> Snapshot:
    return Snapshot("snapshot-1", INSTALLATION, 3, 2000, 1000, "a" * 64, 16384, "b" * 64)


def test_manifest_is_canonical_detached_and_has_no_credentials_or_local_paths() -> None:
    value = snapshot()
    document = value.document()
    decoded = document.decode()
    assert decoded == {
        "format_version": 1,
        "snapshot_id": "snapshot-1",
        "instance_id": INSTALLATION.instance_id,
        "channel": "edge",
        "schema_version": 3,
        "captured_at": 2000,
        "last_committed_at": 1000,
        "database_sha256": "a" * 64,
        "database_bytes": 16384,
        "identity_sha256": "b" * 64,
    }
    decoded["snapshot_id"] = "changed"
    assert value.document() == document
    assert replace(value, last_committed_at=None).document().decode()["last_committed_at"] is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("snapshot_id", "bad id"),
        ("installation", None),
        ("format_version", True),
        ("format_version", 2),
        ("schema_version", True),
        ("schema_version", 0),
        ("schema_version", 2**31),
        ("captured_at", True),
        ("captured_at", -1),
        ("captured_at", 2**63),
        ("last_committed_at", -1),
        ("last_committed_at", True),
        ("last_committed_at", 2**63),
        ("database_sha256", "A" * 64),
        ("database_sha256", "a" * 63),
        ("identity_sha256", "secret"),
        ("database_bytes", True),
        ("database_bytes", 0),
        ("database_bytes", 2**63),
    ],
)
def test_invalid_manifest_cannot_be_published_as_a_snapshot(field: str, value: object) -> None:
    with pytest.raises(InvalidInput):
        replace(snapshot(), **{field: value})
