"""Transaction-local SQLite Inventory with append-only stock evidence."""

import sqlite3
from dataclasses import astuple, dataclass
from typing import cast

from domus.application.inventory_ports import LedgerEntry
from domus.domain.errors import Conflict, StorageFailure
from domus.domain.inventory import (
    MAX_NAMED_LOCATIONS,
    MAX_STOCK_UNITS,
    PANTRY,
    BaseUnit,
    CatalogProduct,
    EffectKind,
    InventoryEffect,
    MovementKind,
    ReplenishmentPolicy,
    StockMovement,
    StockTransfer,
    StorageLocation,
    stock_units,
    validate_stock_reason,
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


MOVEMENT_HISTORY_STATEMENTS = (
    "ALTER TABLE inventory_movements RENAME TO inventory_movements_v20",
    INVENTORY_STATEMENTS[-1]
    .replace(
        "reason TEXT NOT NULL, posting TEXT, corrects TEXT,",
        "reason TEXT NOT NULL, posting TEXT, corrects TEXT, kind TEXT NOT NULL,",
    )
    .replace(
        "CHECK((posting IS NOT NULL) OR (delta>0 AND corrects IS NULL))",
        "CHECK((kind='intake' AND posting IS NULL AND corrects IS NULL AND delta>0) OR "
        "(kind='adjustment' AND posting IS NULL AND corrects IS NULL) OR "
        "(kind='intake_correction' AND posting IS NULL AND corrects IS NOT NULL AND delta<0) OR "
        "(kind='task_consumption' AND posting IS NOT NULL AND corrects IS NULL AND delta<0) OR "
        "(kind='task_correction' AND posting IS NOT NULL AND corrects IS NOT NULL))",
    ),
    "INSERT INTO inventory_movements SELECT *, CASE WHEN posting IS NULL THEN 'intake' "
    "WHEN corrects IS NULL THEN 'task_consumption' ELSE 'task_correction' END "
    "FROM inventory_movements_v20 ORDER BY position",
    "DROP TABLE inventory_movements_v20",
    "CREATE INDEX inventory_history ON inventory_movements(household_id,reference_id,position)",
)


CATALOG_TABLES = {"inventory_products"}
CATALOG_STATEMENTS = (
    "CREATE TABLE inventory_products(household_id TEXT NOT NULL, product_id TEXT NOT NULL, "
    "reference_id TEXT NOT NULL, name TEXT NOT NULL, "
    "base_unit TEXT NOT NULL CHECK(base_unit IN ('piece','gram','millilitre')), "
    "PRIMARY KEY(household_id,product_id), UNIQUE(household_id,reference_id), "
    "FOREIGN KEY(household_id,reference_id) "
    "REFERENCES inventory_materials(household_id,reference_id)) STRICT",
)

REPLENISHMENT_STATEMENT = (
    "CREATE TABLE inventory_replenishment(household_id TEXT NOT NULL, product_id TEXT NOT NULL, "
    f"minimum INTEGER NOT NULL CHECK(minimum BETWEEN 0 AND {MAX_STOCK_UNITS}), "
    f"target INTEGER NOT NULL CHECK(target BETWEEN minimum AND {MAX_STOCK_UNITS}), "
    "revision INTEGER NOT NULL CHECK(revision>0), PRIMARY KEY(household_id,product_id), "
    "FOREIGN KEY(household_id,product_id) "
    "REFERENCES inventory_products(household_id,product_id)) STRICT"
)


LOCATION_TABLES = {"inventory_locations", "inventory_transfers"}
LOCATION_STATEMENTS = (
    "CREATE TABLE inventory_locations(household_id TEXT NOT NULL "
    "REFERENCES households(household_id), location_id TEXT NOT NULL CHECK(location_id!='pantry'), "
    "name TEXT NOT NULL, name_key TEXT NOT NULL, "
    "PRIMARY KEY(household_id,location_id), UNIQUE(household_id,name_key)) STRICT",
    "CREATE TABLE inventory_transfers(household_id TEXT NOT NULL, transfer_id TEXT NOT NULL, "
    "product_id TEXT NOT NULL, source_location TEXT NOT NULL, destination_location TEXT NOT NULL, "
    "withdrawal_id TEXT NOT NULL, deposit_id TEXT NOT NULL, "
    "PRIMARY KEY(household_id,transfer_id), UNIQUE(household_id,withdrawal_id), "
    "UNIQUE(household_id,deposit_id), CHECK(source_location!=destination_location), "
    "FOREIGN KEY(household_id,product_id) REFERENCES inventory_products(household_id,product_id), "
    "FOREIGN KEY(household_id,withdrawal_id) "
    "REFERENCES inventory_movements(household_id,movement_id), "
    "FOREIGN KEY(household_id,deposit_id) "
    "REFERENCES inventory_movements(household_id,movement_id)) STRICT",
    # Preserve the existing ledger and its dependent foreign keys. The transfer identifier
    # specializes an adjustment into one of the two immutable transfer legs.
    "ALTER TABLE inventory_movements ADD COLUMN transfer_id TEXT "
    "CHECK(transfer_id IS NULL OR (kind='adjustment' AND posting IS NULL AND corrects IS NULL))",
    "CREATE INDEX inventory_transfer_legs ON inventory_movements(household_id,transfer_id) "
    "WHERE transfer_id IS NOT NULL",
)


def _transfer(row: sqlite3.Row) -> StockTransfer:
    return StockTransfer(
        row["transfer_id"],
        row["product_id"],
        row["source_location"],
        row["destination_location"],
        row["withdrawal_id"],
        row["deposit_id"],
    )


def _product(row: sqlite3.Row) -> CatalogProduct:
    return CatalogProduct(
        row["product_id"], row["reference_id"], row["name"], BaseUnit(row["base_unit"])
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
    posting, corrects = row["posting"], row["corrects"]
    transfer_id = row["transfer_id"] if "transfer_id" in row.keys() else None
    if transfer_id is not None:
        kind = MovementKind.TRANSFER
    elif "kind" in row.keys():
        kind = MovementKind(row["kind"])
    elif posting is None:
        kind = MovementKind.INTAKE
    else:
        kind = MovementKind.TASK_CONSUMPTION if corrects is None else MovementKind.TASK_CORRECTION
    return StockMovement(
        row["household_id"],
        row["reference_id"],
        row["movement_id"],
        row["source_key"],
        row["member_id"],
        row["delta"],
        row["created_at"],
        row["reason"],
        kind,
        None if posting is None else read_posting(JsonDocument(posting).decode()),
        corrects,
        transfer_id,
    )


@dataclass(frozen=True, slots=True)
class SQLiteInventory:
    connection: sqlite3.Connection

    def add_product(self, home: str, product: CatalogProduct) -> None:
        self.connection.execute(
            "INSERT INTO inventory_products VALUES (?,?,?,?,?)", (home, *astuple(product))
        )

    def product(self, home: str, product_id: str) -> CatalogProduct | None:
        row = self.connection.execute(
            "SELECT * FROM inventory_products WHERE household_id=? AND product_id=?",
            (home, product_id),
        ).fetchone()
        return None if row is None else _product(row)

    def products(self, home: str, after: str, limit: int) -> tuple[CatalogProduct, ...]:
        return tuple(
            _product(row)
            for row in self.connection.execute(
                "SELECT * FROM inventory_products WHERE household_id=? AND product_id>? "
                "ORDER BY product_id LIMIT ?",
                (home, after, limit),
            )
        )

    def replenishment(self, home: str, product_id: str) -> ReplenishmentPolicy:
        row = self.connection.execute(
            "SELECT minimum,target,revision FROM inventory_replenishment "
            "WHERE household_id=? AND product_id=?",
            (home, product_id),
        ).fetchone()
        return ReplenishmentPolicy() if row is None else ReplenishmentPolicy(*row)

    def save_replenishment(self, home: str, product_id: str, policy: ReplenishmentPolicy) -> None:
        self.connection.execute(
            "INSERT INTO inventory_replenishment VALUES (?,?,?,?,?) "
            "ON CONFLICT(household_id,product_id) DO UPDATE SET "
            "minimum=excluded.minimum,target=excluded.target,revision=excluded.revision",
            (home, product_id, policy.minimum, policy.target, policy.revision),
        )

    def locations(self, home: str) -> tuple[StorageLocation, ...]:
        return tuple(
            StorageLocation(row["location_id"], row["name"])
            for row in self.connection.execute(
                "SELECT location_id,name FROM inventory_locations "
                "WHERE household_id=? ORDER BY name_key",
                (home,),
            )
        )

    def add_location(self, home: str, value: StorageLocation) -> None:
        self.connection.execute(
            "INSERT INTO inventory_locations VALUES (?,?,?,?)",
            (home, value.location_id, value.name, value.name.casefold()),
        )

    def location_is_used(self, home: str, location_id: str) -> bool:
        return (
            self.connection.execute(
                "SELECT 1 FROM inventory_materials WHERE household_id=? AND location_id=? LIMIT 1",
                (home, location_id),
            ).fetchone()
            is not None
        )

    def location_bindings(self, home: str, product_id: str) -> dict[str, str]:
        return dict(
            self.connection.execute(
                "SELECT m.location_id,m.reference_id FROM inventory_materials m "
                "LEFT JOIN inventory_locations l USING(household_id,location_id) "
                "WHERE m.household_id=? AND m.product_id=? "
                "AND (m.location_id=? OR l.location_id IS NOT NULL)",
                (home, product_id, PANTRY),
            )
        )

    def add_transfer(self, home: str, value: StockTransfer) -> None:
        self.connection.execute(
            "INSERT INTO inventory_transfers VALUES (?,?,?,?,?,?,?)", (home, *astuple(value))
        )

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

    def effects_for_references(
        self, home: str, references: tuple[str, ...]
    ) -> tuple[InventoryEffect, ...]:
        placeholders = ",".join("?" for _ in references)
        return tuple(
            _effect(row)
            for row in self.connection.execute(
                "SELECT * FROM inventory_effects WHERE household_id=? "
                f"AND occurrence_id IS NOT NULL AND reference_id IN ({placeholders}) "
                "AND (kind='demand' OR remaining>0)",
                (home, *references),
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

    def correction_id(self, home: str, original_id: str) -> str | None:
        row = self.connection.execute(
            "SELECT movement_id FROM inventory_movements WHERE household_id=? AND corrects=?",
            (home, original_id),
        ).fetchone()
        return None if row is None else cast(str, row["movement_id"])

    def history(
        self, home: str, references: tuple[str, ...], through: int, limit: int
    ) -> tuple[LedgerEntry, ...]:
        placeholders = ",".join("?" for _ in references)
        return tuple(
            LedgerEntry(
                row["position"],
                _movement(row),
                row["corrected_by"],
                None if row["transfer_id"] is None else _transfer(row),
            )
            for row in self.connection.execute(
                "SELECT m.*, c.movement_id AS corrected_by, "
                "t.product_id,t.source_location,t.destination_location,"
                "t.withdrawal_id,t.deposit_id "
                "FROM inventory_movements m "
                "LEFT JOIN inventory_movements c ON c.household_id=m.household_id "
                "AND c.corrects=m.movement_id "
                "LEFT JOIN inventory_transfers t ON t.household_id=m.household_id "
                "AND t.transfer_id=m.transfer_id WHERE m.household_id=? "
                f"AND m.reference_id IN ({placeholders}) "
                "AND m.position<=? ORDER BY m.position DESC LIMIT ?",
                (home, *references, through, limit),
            )
        )

    def append(self, value: StockMovement, balance: int) -> None:
        posting = (
            None if value.posting is None else JsonDocument.from_value(posting_value(value.posting))
        )
        self.connection.execute(
            "INSERT INTO inventory_movements(household_id,reference_id,movement_id,source_key,"
            "member_id,delta,created_at,reason,posting,corrects,kind,transfer_id) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
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
                MovementKind.ADJUSTMENT if value.kind is MovementKind.TRANSFER else value.kind,
                value.transfer_id,
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
        if movement.kind in (MovementKind.ADJUSTMENT, MovementKind.INTAKE_CORRECTION):
            validate_stock_reason(movement.reason)
        if movement.kind is MovementKind.INTAKE_CORRECTION:
            original = stock.movement_by_id(movement.household_id, cast(str, movement.corrects))
            if (
                original is None
                or original.kind is not MovementKind.INTAKE
                or movement.delta != -original.delta
            ):
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


def verify_inventory_catalog(connection: sqlite3.Connection) -> None:
    stock = SQLiteInventory(connection)
    for row in connection.execute("SELECT * FROM inventory_products"):
        product = _product(row)
        home = row["household_id"]
        if stock.material(home, product.reference_id) != product.binding(home):
            raise StorageFailure("invalid_inventory_catalog_binding")


def verify_replenishment(connection: sqlite3.Connection) -> None:
    for minimum, target in connection.execute(
        "SELECT r.minimum,r.target FROM inventory_replenishment AS r "
        "JOIN inventory_products AS p USING(household_id,product_id) WHERE p.base_unit='piece'"
    ):
        if minimum % 1_000_000 or target % 1_000_000:
            raise StorageFailure("invalid_replenishment_bounds")


def verify_inventory_locations(connection: sqlite3.Connection) -> None:
    stock = SQLiteInventory(connection)
    for home, count in connection.execute(
        "SELECT household_id,COUNT(*) FROM inventory_locations GROUP BY household_id"
    ):
        if count > MAX_NAMED_LOCATIONS:
            raise StorageFailure("invalid_inventory_locations")
        for location in stock.locations(home):
            key = connection.execute(
                "SELECT name_key FROM inventory_locations WHERE household_id=? AND location_id=?",
                (home, location.location_id),
            ).fetchone()[0]
            if key != location.name.casefold():
                raise StorageFailure("invalid_inventory_locations")

    for row in connection.execute(
        "SELECT m.household_id,m.reference_id,m.location_id,m.product_id "
        "FROM inventory_materials m "
        "JOIN inventory_locations l USING(household_id,location_id)"
    ):
        home, reference, location, product_id = row
        product = stock.product(home, product_id)
        if product is None or stock.material(home, reference) != product.binding(
            home, location=location, reference=reference
        ):
            raise StorageFailure("invalid_inventory_catalog_binding")

    for row in connection.execute("SELECT * FROM inventory_transfers"):
        home = row["household_id"]
        transfer = _transfer(row)
        validate_identifier(transfer.transfer_id)
        references = stock.location_bindings(home, transfer.product_id)
        legs = connection.execute(
            "SELECT * FROM inventory_movements WHERE household_id=? AND transfer_id=? "
            "ORDER BY delta LIMIT 3",
            (home, transfer.transfer_id),
        ).fetchall()
        if len(legs) != 2:
            raise StorageFailure("invalid_inventory_transfer")
        withdrawal, deposit = map(_movement, legs)
        if (
            withdrawal.movement_id != transfer.withdrawal_id
            or deposit.movement_id != transfer.deposit_id
            or withdrawal.reference_id != references.get(transfer.source_location)
            or deposit.reference_id != references.get(transfer.destination_location)
            or withdrawal.delta >= 0
            or deposit.delta != -withdrawal.delta
            or withdrawal.member_id != deposit.member_id
            or withdrawal.created_at != deposit.created_at
            or withdrawal.reason != ""
            or deposit.reason != ""
        ):
            raise StorageFailure("invalid_inventory_transfer")

    if (
        connection.execute(
            "SELECT 1 FROM inventory_movements m LEFT JOIN inventory_transfers t "
            "USING(household_id,transfer_id) WHERE m.transfer_id IS NOT NULL "
            "AND t.transfer_id IS NULL LIMIT 1"
        ).fetchone()
        is not None
    ):
        raise StorageFailure("invalid_inventory_transfer")
