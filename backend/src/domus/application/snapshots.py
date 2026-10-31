"""Snapshot orchestration consumes semantic archive ports rather than filesystem paths."""

from dataclasses import dataclass
from typing import Protocol

from domus.application.ports import Identifiers
from domus.domain.errors import StorageFailure
from domus.domain.snapshots import Snapshot
from domus.domain.storage import Installation


class SnapshotArchive(Protocol):
    def create(self, snapshot_id: str) -> Snapshot: ...
    def inspect(self) -> Snapshot: ...


@dataclass
class SnapshotCommands:
    archive: SnapshotArchive
    installation: Installation
    identifiers: Identifiers

    def create(self) -> Snapshot:
        snapshot_id = self.identifiers.new()
        result = self.archive.create(snapshot_id)
        if result.snapshot_id != snapshot_id or result.installation != self.installation:
            raise StorageFailure("invalid_snapshot_result")
        return result

    def inspect(self) -> Snapshot:
        result = self.archive.inspect()
        if result.installation != self.installation:
            raise StorageFailure("invalid_snapshot_result")
        return result
