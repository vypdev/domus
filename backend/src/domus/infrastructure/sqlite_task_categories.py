"""SQLite owns category uniqueness, scope and optimistic revision writes."""

import sqlite3
from dataclasses import dataclass

from domus.domain.errors import Conflict, InvalidInput, StorageFailure
from domus.domain.storage import validate_identifier
from domus.domain.task_categories import MAX_ACTIVE_TASK_CATEGORIES, TaskCategory

CATEGORY_TABLE = "task_categories"
CATEGORY_STATEMENTS = (
    "CREATE TABLE task_categories(category_id TEXT PRIMARY KEY NOT NULL, "
    "household_id TEXT NOT NULL REFERENCES households(household_id), "
    "label TEXT NOT NULL, label_key TEXT NOT NULL, "
    "revision INTEGER NOT NULL CHECK(typeof(revision)='integer' AND revision>=1), "
    "archived INTEGER NOT NULL CHECK(archived IN (0,1)))",
    "CREATE UNIQUE INDEX task_categories_active_label "
    "ON task_categories(household_id,label_key) WHERE archived=0",
)


def _category(row: sqlite3.Row) -> TaskCategory:
    try:
        value = TaskCategory(
            row["category_id"],
            row["household_id"],
            row["label"],
            row["revision"],
            bool(row["archived"]),
        )
        if row["archived"] not in (0, 1) or value.label_key != row["label_key"]:
            raise InvalidInput("invalid_task_category")
        return value
    except InvalidInput:
        raise StorageFailure("invalid_task_category_record") from None


@dataclass
class SQLiteTaskCategories:
    connection: sqlite3.Connection

    def active(self, household_id: str) -> tuple[TaskCategory, ...]:
        validate_identifier(household_id)
        values = tuple(
            _category(row)
            for row in self.connection.execute(
                "SELECT * FROM task_categories WHERE household_id=? AND archived=0 "
                "ORDER BY label_key LIMIT ?",
                (household_id, MAX_ACTIVE_TASK_CATEGORIES + 1),
            )
        )
        if len(values) > MAX_ACTIVE_TASK_CATEGORIES:
            raise StorageFailure("invalid_task_category_record")
        return values

    def get(self, household_id: str, category_id: str) -> TaskCategory | None:
        validate_identifier(household_id)
        validate_identifier(category_id)
        row = self.connection.execute(
            "SELECT * FROM task_categories WHERE household_id=? AND category_id=?",
            (household_id, category_id),
        ).fetchone()
        return None if row is None else _category(row)

    def save(self, category: TaskCategory, expected_revision: int) -> None:
        if category.revision != expected_revision + 1:
            raise Conflict("revision_conflict")
        try:
            if expected_revision == 0:
                self.connection.execute(
                    "INSERT INTO task_categories VALUES (?,?,?,?,?,?)",
                    (
                        category.category_id,
                        category.household_id,
                        category.label,
                        category.label_key,
                        category.revision,
                        int(category.archived),
                    ),
                )
                return
            changed = self.connection.execute(
                "UPDATE task_categories SET label=?, label_key=?, revision=?, archived=? "
                "WHERE household_id=? AND category_id=? AND revision=?",
                (
                    category.label,
                    category.label_key,
                    category.revision,
                    int(category.archived),
                    category.household_id,
                    category.category_id,
                    expected_revision,
                ),
            )
            if changed.rowcount != 1:
                raise Conflict("revision_conflict")
        except sqlite3.IntegrityError:
            raise Conflict("task_category_conflict") from None

    def verified_ids(self, household_id: str) -> frozenset[str]:
        self.active(household_id)
        return frozenset(
            _category(row).category_id
            for row in self.connection.execute(
                "SELECT * FROM task_categories WHERE household_id=?", (household_id,)
            )
        )
