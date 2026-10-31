"""A preparation result must match its requested checkpoint and installation."""

from dataclasses import dataclass
from typing import Protocol

from domus.application.ports import Identifiers
from domus.domain.errors import InvalidInput, StorageFailure
from domus.domain.restoration import PreparedRestoration
from domus.domain.snapshots import Snapshot
from domus.domain.storage import Installation


class RestorationArchive(Protocol):
    def prepare(self, restore_id: str) -> PreparedRestoration: ...
    def inspect(self) -> PreparedRestoration: ...


@dataclass
class RestorationCommands:
    archive: RestorationArchive
    installation: Installation
    identifiers: Identifiers
    checkpoint: Snapshot | None = None

    def _checked(self, result: PreparedRestoration) -> PreparedRestoration:
        if result.installation != self.installation or (
            self.checkpoint is not None and result.checkpoint != self.checkpoint
        ):
            raise StorageFailure("invalid_restore_result")
        return result

    def prepare(self) -> PreparedRestoration:
        if self.checkpoint is None or self.checkpoint.installation != self.installation:
            raise InvalidInput("restore_checkpoint_required")
        restore_id = self.identifiers.new()
        result = self._checked(self.archive.prepare(restore_id))
        if result.restore_id != restore_id:
            raise StorageFailure("invalid_restore_result")
        return result

    def inspect(self) -> PreparedRestoration:
        return self._checked(self.archive.inspect())
