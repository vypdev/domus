"""Snapshot use cases cannot report a provider result for another request or installation."""

from dataclasses import replace

import pytest
from test_snapshot_values import INSTALLATION, snapshot

from domus.application.snapshots import SnapshotCommands
from domus.domain.errors import StorageFailure
from domus.domain.storage import Installation


class Identifiers:
    def new(self):
        return "snapshot-1"


class Archive:
    value = snapshot()

    def create(self, snapshot_id):
        assert snapshot_id == "snapshot-1"
        return self.value

    def inspect(self):
        return self.value


def test_snapshot_use_cases_return_only_the_configured_installation_result() -> None:
    commands = SnapshotCommands(Archive(), INSTALLATION, Identifiers())
    assert commands.create() == snapshot()
    assert commands.inspect() == snapshot()


@pytest.mark.parametrize("operation", ["create", "inspect"])
def test_other_installation_result_is_not_published(operation: str) -> None:
    archive = Archive()
    archive.value = replace(
        snapshot(), installation=Installation(INSTALLATION.instance_id, "stable")
    )
    with pytest.raises(StorageFailure, match="invalid_snapshot_result"):
        getattr(SnapshotCommands(archive, INSTALLATION, Identifiers()), operation)()


def test_capture_result_for_a_different_id_is_not_published() -> None:
    archive = Archive()
    archive.value = replace(snapshot(), snapshot_id="another")
    with pytest.raises(StorageFailure, match="invalid_snapshot_result"):
        SnapshotCommands(archive, INSTALLATION, Identifiers()).create()
