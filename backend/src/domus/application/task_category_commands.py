"""Manage the authorized household catalog and its original command receipts."""

from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Literal, cast

from domus.application.commands import AtomicCommands, Change
from domus.application.identity_ports import CurrentHuman
from domus.application.ports import Clock, Identifiers, Transactions, UnitOfWork
from domus.application.task_authorization import TaskAccess, TaskCommandAuthorization
from domus.domain.errors import Conflict, Forbidden, InvalidInput, NotFound
from domus.domain.identity import HumanIdentity, Permission, validate_revision
from domus.domain.storage import CommandKey, JsonDocument, JsonObject, Receipt
from domus.domain.task_categories import MAX_ACTIVE_TASK_CATEGORIES, TaskCategory, category_label

CategoryAction = Literal["task.category.create", "task.category.rename", "task.category.archive"]


def require_active_category(unit: UnitOfWork, household_id: str, category_id: str) -> TaskCategory:
    current = unit.task_categories.get(household_id, category_id)
    if current is None or current.archived:
        raise InvalidInput("task_category_unavailable")
    return current


@dataclass(frozen=True, slots=True)
class CategoryCatalog:
    categories: tuple[TaskCategory, ...]
    can_manage: bool


def category_catalog(unit: UnitOfWork, access: TaskAccess, household_id: str) -> CategoryCatalog:
    access.require(unit, household_id, Permission.TASKS_READ)
    try:
        access.require(unit, household_id, Permission.TASKS_CONFIGURE)
        can_manage = True
    except Forbidden:
        can_manage = False
    return CategoryCatalog(unit.task_categories.active(household_id), can_manage)


@dataclass(frozen=True, slots=True)
class TaskCategoryCommands:
    transactions: Transactions
    actor: CurrentHuman
    read_actor: Callable[[], HumanIdentity]
    clock: Clock
    identifiers: Identifiers
    household_id: str = "home"

    def catalog(self) -> CategoryCatalog:
        access = TaskAccess(self.read_actor())
        with self.transactions.read() as unit:
            return category_catalog(unit, access, self.household_id)

    def _authority(
        self, human: HumanIdentity, action: CategoryAction, key: str
    ) -> tuple[CommandKey, TaskCommandAuthorization]:
        command = CommandKey(self.household_id, human.ha_user_id, action, key)
        return command, TaskCommandAuthorization(TaskAccess(human), self.household_id, action)

    def _execute(
        self,
        action: CategoryAction,
        key: str,
        payload: JsonDocument,
        change: Callable[[UnitOfWork], TaskCategory],
    ) -> Receipt:
        command, authority = self._authority(self.actor.current(), action, key)

        def apply(unit: UnitOfWork) -> Change:
            category = change(unit)
            result = cast(JsonObject, asdict(category))
            return Change(
                JsonDocument.from_value(result),
                JsonDocument.from_value({"request": payload.decode(), "result": result}),
                JsonDocument.from_value({"version": 1, "kind": action, **result}),
            )

        return AtomicCommands(self.transactions, authority, self.clock, self.identifiers).execute(
            command, payload, apply
        )

    def create(self, key: str, label: str) -> Receipt:
        normalized = category_label(label)
        payload = JsonDocument.from_value({"expected_revision": 0, "label": label})

        def change(unit: UnitOfWork) -> TaskCategory:
            if len(unit.task_categories.active(self.household_id)) >= MAX_ACTIVE_TASK_CATEGORIES:
                raise Conflict("task_category_capacity")
            category = TaskCategory(self.identifiers.new(), self.household_id, normalized)
            unit.task_categories.save(category, 0)
            return category

        return self._execute("task.category.create", key, payload, change)

    def rename(self, key: str, category_id: str, expected_revision: int, label: str) -> Receipt:
        return self._edit(key, category_id, expected_revision, label)

    def archive(self, key: str, category_id: str, expected_revision: int) -> Receipt:
        return self._edit(key, category_id, expected_revision, None)

    def _edit(
        self, key: str, category_id: str, expected_revision: int, label: str | None
    ) -> Receipt:
        validate_revision(expected_revision)
        normalized = None if label is None else category_label(label)
        payload = JsonDocument.from_value(
            {"category_id": category_id, "expected_revision": expected_revision, "label": label}
        )

        def change(unit: UnitOfWork) -> TaskCategory:
            current = require_active_category(unit, self.household_id, category_id)
            if current.revision != expected_revision:
                raise Conflict("revision_conflict")
            updated = current.revise(
                current.label if normalized is None else normalized, archive=normalized is None
            )
            unit.task_categories.save(updated, expected_revision)
            return updated

        action: CategoryAction = (
            "task.category.archive" if normalized is None else "task.category.rename"
        )
        return self._execute(action, key, payload, change)

    def original(self, action: CategoryAction, key: str) -> Receipt:
        command, authority = self._authority(self.read_actor(), action, key)
        with self.transactions.read() as unit:
            authority.require(command, unit)
            receipt = unit.receipts.get(command)
            if receipt is None:
                raise NotFound("operation_missing")
            return receipt
