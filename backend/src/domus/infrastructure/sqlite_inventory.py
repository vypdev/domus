"""Transaction-local SQLite Inventory with append-only stock evidence."""

import sqlite3
from dataclasses import astuple, dataclass
from typing import cast

from domus.domain.errors import Conflict, StorageFailure
from domus.domain.inventory import (
    MAX_STOCK_UNITS,
    EffectKind,
    InventoryEffect,
    StockMovement,
    stock_units,
)
from domus.domain.storage import JsonDocument, validate_identifier
from domus.domain.task_material_values import MaterialBinding
from domus.domain.task_values import validate_task_time
from domus.infrastructure.sqlite_task_material_records import posting_value, read_posting

INVENTORY_TABLES = {"inventory_materials", "inventory_effects", "inventory_movements"}
INVENTORY_STATEMENTS = (
    "CREATE TABLE inventory_materials(household_id TEXT NOT NULL "
    "REFERENCES households(household_id), "
    "reference_id TEXT NOT NULL, product_id TEXT NOT NULL, unit_id TEXT NOT NULL, "
    "location_id TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision=1), "
    "precision INTEGER NOT NULL CHECK(precision BETWEEN 0 AND 6), label TEXT NOT NULL, "
    f"balance INTEGER NOT NULL CHECK(balance BETWEEN 0 AND {MAX_STOCK_UNITS}), "
    "PRIMARY KEY(household_id,reference_id), UNIQUE(household_id,product_id,location_id)) STRICT",
    "CREATE TABLE inventory_effects(household_id TEXT NOT NULL, effect_id TEXT NOT NULL, "
    "kind TEXT NOT NULL CHECK(kind IN ('reservation','demand')), reference_id TEXT NOT NULL, "
    "origin_id TEXT, occurrence_id TEXT, line_id TEXT, "
    f"remaining INTEGER NOT NULL CHECK(remaining BETWEEN 0 AND {MAX_STOCK_UNITS}), "
    "revision INTEGER NOT NULL CHECK(revision>=1), PRIMARY KEY(household_id,effect_id), "
    "UNIQUE(household_id,occurrence_id,reference_id,kind), "
    "CHECK((origin_id IS NOT NULL AND occurrence_id IS NOT NULL AND line_id IS NOT NULL) OR "
    "(kind='demand' AND origin_id IS NULL AND occurrence_id IS NULL AND line_id IS NULL)), "
    "FOREIGN KEY(household_id,reference_id) "
    "REFERENCES inventory_materials(household_id,reference_id), "
    "FOREIGN KEY(household_id,origin_id) REFERENCES task_occurrences(household_id,occurrence_id), "
    "FOREIGN KEY(household_id,occurrence_id) "
    "REFERENCES task_occurrences(household_id,occurrence_id)) STRICT",
    "CREATE INDEX inventory_reservations ON inventory_effects(household_id,reference_id) "
    "WHERE kind='reservation' AND remaining>0",
    "CREATE TABLE inventory_movements(position INTEGER PRIMARY KEY, household_id TEXT NOT NULL, "
    "reference_id TEXT NOT NULL, movement_id TEXT NOT NULL, source_key TEXT NOT NULL, "
    "member_id TEXT NOT NULL, delta INTEGER NOT NULL "
    f"CHECK(delta BETWEEN {-MAX_STOCK_UNITS} AND {MAX_STOCK_UNITS} AND delta!=0), "
    "created_at INTEGER NOT NULL CHECK(created_at>=0), "
    "reason TEXT NOT NULL, posting TEXT, corrects TEXT, "
    "UNIQUE(household_id,movement_id), UNIQUE(household_id,source_key), "
    "UNIQUE(household_id,reference_id,movement_id), UNIQUE(household_id,corrects), "
    "CHECK((posting IS NOT NULL) OR (delta>0 AND corrects IS NULL)), "
    "FOREIGN KEY(household_id,reference_id) "
    "REFERENCES inventory_materials(household_id,reference_id), "
    "FOREIGN KEY(household_id,reference_id,corrects) "
    "REFERENCES inventory_movements(household_id,reference_id,movement_id), "
    "FOREIGN KEY(household_id,member_id) REFERENCES members(household_id,member_id)) STRICT",
)


def _effect(row: sqlite3.Row) -> InventoryEffect:
    return InventoryEffect(
        row["household_id"],
        row["effect_id"],
        EffectKind(row["kind"]),
        row["reference_id"],
        row["origin_id"],
        row["occurrence_id"],
        row["line_id"],
        row["remaining"],
        row["revision"],
    )


def _movement(row: sqlite3.Row) -> StockMovement:
    posting = row["posting"]
    return StockMovement(
        row["household_id"],
        row["reference_id"],
        row["movement_id"],
        row["source_key"],
        row["member_id"],
        row["delta"],
        row["created_at"],
        row["reason"],
        None if posting is None else read_posting(JsonDocument(posting).decode()),
        row["corrects"],
    )


@dataclass(frozen=True, slots=True)
class SQLiteInventory:
    connection: sqlite3.Connection

    def material(self, home: str, reference: str) -> MaterialBinding | None:
        row = self.connection.execute(
            "SELECT household_id,reference_id,product_id,unit_id,location_id,"
            "revision,precision,label "
            "FROM inventory_materials WHERE household_id=? AND reference_id=?",
            (home, reference),
        ).fetchone()
        return None if row is None else MaterialBinding(*row)

    def add_material(self, binding: MaterialBinding) -> None:
        self.connection.execute(
            "INSERT INTO inventory_materials VALUES (?,?,?,?,?,?,?,?,0)", astuple(binding)
        )

    def balance(self, home: str, reference: str) -> int:
        row = self.connection.execute(
            "SELECT balance FROM inventory_materials WHERE household_id=? AND reference_id=?",
            (home, reference),
        ).fetchone()
        return cast(int, row["balance"])

    def reserved(self, home: str, reference: str) -> int:
        row = self.connection.execute(
            "SELECT COALESCE(SUM(remaining),0) FROM inventory_effects WHERE household_id=? "
            "AND reference_id=? AND kind='reservation' AND remaining>0",
            (home, reference),
        ).fetchone()
        return cast(int, row[0])

    def effect(self, home: str, effect_id: str) -> InventoryEffect | None:
        row = self.connection.execute(
            "SELECT * FROM inventory_effects WHERE household_id=? AND effect_id=?",
            (home, effect_id),
        ).fetchone()
        return None if row is None else _effect(row)

    def effects(self, home: str, occurrences: tuple[str, ...]) -> tuple[InventoryEffect, ...]:
        if not occurrences:
            return ()
        placeholders = ",".join("?" for _ in occurrences)
        return tuple(
            _effect(row)
            for row in self.connection.execute(
                "SELECT * FROM inventory_effects WHERE household_id=? "
                f"AND occurrence_id IN ({placeholders}) AND remaining>0 ORDER BY effect_id",
                (home, *occurrences),
            )
        )

    def add_effect(self, value: InventoryEffect) -> None:
        self.connection.execute(
            "INSERT INTO inventory_effects VALUES (?,?,?,?,?,?,?,?,?)", astuple(value)
        )

    def update_effect(self, value: InventoryEffect, previous_revision: int) -> None:
        updated = self.connection.execute(
            "UPDATE inventory_effects SET occurrence_id=?,remaining=?,revision=? "
            "WHERE household_id=? AND effect_id=? AND revision=?",
            (
                value.occurrence_id,
                value.remaining,
                value.revision,
                value.household_id,
                value.effect_id,
                previous_revision,
            ),
        )
        if updated.rowcount != 1:
            raise Conflict("inventory_effect_stale")

    def _movement(self, sql: str, home: str, key: str) -> StockMovement | None:
        row = self.connection.execute(sql, (home, key)).fetchone()
        return None if row is None else _movement(row)

    def movement(self, home: str, source_key: str) -> StockMovement | None:
        return self._movement(
            "SELECT * FROM inventory_movements WHERE household_id=? AND source_key=?",
            home,
            source_key,
        )

    def movement_by_id(self, home: str, movement_id: str) -> StockMovement | None:
        return self._movement(
            "SELECT * FROM inventory_movements WHERE household_id=? AND movement_id=?",
            home,
            movement_id,
        )

    def append(self, value: StockMovement, balance: int) -> None:
        posting = (
            None if value.posting is None else JsonDocument.from_value(posting_value(value.posting))
        )
        self.connection.execute(
            "INSERT INTO inventory_movements(household_id,reference_id,movement_id,source_key,"
            "member_id,delta,created_at,reason,posting,corrects) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                value.household_id,
                value.reference_id,
                value.movement_id,
                value.source_key,
                value.member_id,
                value.delta,
                value.created_at,
                value.reason,
                None if posting is None else posting.encoded,
                value.corrects,
            ),
        )
        self.connection.execute(
            "UPDATE inventory_materials SET balance=? WHERE household_id=? AND reference_id=?",
            (balance, value.household_id, value.reference_id),
        )


def verify_inventory_records(connection: sqlite3.Connection) -> None:
    stock = SQLiteInventory(connection)
    balances: dict[tuple[str, str], int] = {}
    for row in connection.execute("SELECT * FROM inventory_movements ORDER BY position"):
        movement = _movement(row)
        key = movement.household_id, movement.reference_id
        validate_identifier(movement.source_key)
        validate_identifier(movement.movement_id)
        validate_task_time(movement.created_at)
        balance = balances.get(key, 0) + movement.delta
        posting = movement.posting
        if posting is not None:
            if (
                posting.household_id != movement.household_id
                or posting.reference_id != movement.reference_id
                or posting.movement_id != movement.movement_id
                or posting.posted_at != movement.created_at
            ):
                raise StorageFailure("invalid_inventory_movement")
            prior_units = 0
            if movement.corrects is not None:
                prior = stock.movement_by_id(movement.household_id, movement.corrects)
                if (
                    prior is None
                    or prior.posting is None
                    or prior.posting.intent_id != posting.intent_id
                ):
                    raise StorageFailure("invalid_inventory_movement")
                prior_units = stock_units(prior.posting.quantity)
            if movement.delta != prior_units - stock_units(posting.quantity):
                raise StorageFailure("invalid_inventory_movement")
        if not 0 <= balance <= MAX_STOCK_UNITS:
            raise StorageFailure("invalid_inventory_balance")
        balances[key] = balance
    for row in connection.execute(
        "SELECT household_id,reference_id,balance FROM inventory_materials"
    ):
        home, reference, balance = row
        stock.material(home, reference)
        if (
            balance != balances.get((home, reference), 0)
            or stock.reserved(home, reference) > balance
        ):
            raise StorageFailure("invalid_inventory_balance")
