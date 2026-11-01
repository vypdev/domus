"""Public absence adapter alias; the semantic default has no provider implementation or I/O."""

from domus.application.task_material_ports import MissingTaskInventory as UnavailableTaskInventory

__all__ = ["UnavailableTaskInventory"]
