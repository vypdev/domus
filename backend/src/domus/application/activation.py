"""Semantic activation commands bind results to the requested installation and preparation."""

from dataclasses import dataclass
from typing import Protocol

from domus.domain.activation import ActivationStatus
from domus.domain.errors import InvalidInput, StorageFailure
from domus.domain.restoration import PreparedRestoration
from domus.domain.storage import Installation, validate_identifier


class Activations(Protocol):
    def activate(self) -> ActivationStatus: ...
    def resume(self) -> ActivationStatus: ...
    def inspect(self) -> ActivationStatus: ...


@dataclass
class ActivationCommands:
    activations: Activations
    installation: Installation
    prepared: PreparedRestoration | None = None
    restore_id: str | None = None

    def _checked(self, result: ActivationStatus, *, complete: bool) -> ActivationStatus:
        if (
            result.record.prepared.installation != self.installation
            or (self.prepared is not None and result.record.prepared != self.prepared)
            or (
                self.restore_id is not None and result.record.prepared.restore_id != self.restore_id
            )
            or (complete and result.state == "pending")
        ):
            raise StorageFailure("invalid_activation_result")
        return result

    def _selection(self) -> None:
        if self.prepared is None and self.restore_id is None:
            raise InvalidInput("activation_selection_required")
        if self.prepared is not None and self.prepared.installation != self.installation:
            raise InvalidInput("activation_selection_required")
        if self.restore_id is not None:
            validate_identifier(self.restore_id)

    def activate(self) -> ActivationStatus:
        self._selection()
        return self._checked(self.activations.activate(), complete=True)

    def resume(self) -> ActivationStatus:
        self._selection()
        return self._checked(self.activations.resume(), complete=True)

    def inspect(self) -> ActivationStatus:
        self._selection()
        return self._checked(self.activations.inspect(), complete=False)
