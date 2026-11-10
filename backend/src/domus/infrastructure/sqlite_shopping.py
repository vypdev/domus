"""Store purchase and receipt evidence beside the Pantry ledger."""

import sqlite3
from dataclasses import astuple, dataclass

from domus.domain.errors import StorageFailure
from domus.domain.inventory import MAX_STOCK_UNITS, BaseUnit, MovementKind
from domus.domain.shopping import Purchase, PurchaseReceipt
from domus.domain.storage import validate_identifier
from domus.domain.task_values import validate_task_text, validate_task_time
from domus.infrastructure.sqlite_inventory import SQLiteInventory

SHOPPING_TABLES = {"shopping_purchases", "shopping_receipts"}
SHOPPING_STATEMENTS = (
    "CREATE TABLE shopping_purchases(position INTEGER PRIMARY KEY, household_id TEXT NOT NULL, "
    "purchase_id TEXT NOT NULL, product_id TEXT, name TEXT NOT NULL, "
    "base_unit TEXT NOT NULL CHECK(base_unit IN ('piece','gram','millilitre')), "
    f"purchased INTEGER NOT NULL CHECK(purchased BETWEEN 1 AND {MAX_STOCK_UNITS}), "
    "received INTEGER NOT NULL CHECK(received BETWEEN 0 AND purchased), "
    "settled INTEGER NOT NULL CHECK(settled BETWEEN 0 AND received), "
    "revision INTEGER NOT NULL CHECK(revision>0), member_id TEXT NOT NULL, "
    "created_at INTEGER NOT NULL CHECK(created_at>=0), UNIQUE(household_id,purchase_id), "
    "CHECK(product_id IS NOT NULL OR (base_unit='piece' AND settled=received)), "
    "FOREIGN KEY(household_id,product_id) REFERENCES inventory_products(household_id,product_id), "
    "FOREIGN KEY(household_id,member_id) REFERENCES members(household_id,member_id)) STRICT",
    "CREATE UNIQUE INDEX shopping_open_pantry ON shopping_purchases(household_id,product_id) "
    "WHERE product_id IS NOT NULL AND settled<purchased",
    "CREATE INDEX shopping_history ON shopping_purchases(household_id,position)",
    "CREATE TABLE shopping_receipts(position INTEGER PRIMARY KEY, household_id TEXT NOT NULL, "
    "receipt_id TEXT NOT NULL, purchase_id TEXT NOT NULL, "
    f"quantity INTEGER NOT NULL CHECK(quantity BETWEEN 1 AND {MAX_STOCK_UNITS}), "
    "member_id TEXT NOT NULL, created_at INTEGER NOT NULL CHECK(created_at>=0), "
    "movement_id TEXT, UNIQUE(household_id,receipt_id), UNIQUE(household_id,movement_id), "
    "FOREIGN KEY(household_id,purchase_id) "
    "REFERENCES shopping_purchases(household_id,purchase_id), "
    "FOREIGN KEY(household_id,member_id) REFERENCES members(household_id,member_id), "
    "FOREIGN KEY(household_id,movement_id) "
    "REFERENCES inventory_movements(household_id,movement_id)) STRICT",
    "CREATE INDEX shopping_receipt_history ON shopping_receipts(household_id,purchase_id,position)",
)


def _purchase(row: sqlite3.Row) -> Purchase:
    return Purchase(
        row["purchase_id"],
        row["product_id"],
        row["name"],
        BaseUnit(row["base_unit"]),
        row["purchased"],
        row["received"],
        row["settled"],
        row["revision"],
        row["member_id"],
        row["created_at"],
    )


def _receipt(row: sqlite3.Row) -> PurchaseReceipt:
    return PurchaseReceipt(
        row["receipt_id"],
        row["purchase_id"],
        row["quantity"],
        row["member_id"],
        row["created_at"],
        row["movement_id"],
    )


@dataclass(frozen=True, slots=True)
class SQLiteShopping:
    connection: sqlite3.Connection

    def purchase(self, home: str, purchase_id: str) -> Purchase | None:
        row = self.connection.execute(
            "SELECT * FROM shopping_purchases WHERE household_id=? AND purchase_id=?",
            (home, purchase_id),
        ).fetchone()
        return None if row is None else _purchase(row)

    def purchases(self, home: str, through: int, limit: int) -> tuple[tuple[int, Purchase], ...]:
        return tuple(
            (row["position"], _purchase(row))
            for row in self.connection.execute(
                "SELECT * FROM shopping_purchases WHERE household_id=? AND position<=? "
                "ORDER BY position DESC LIMIT ?",
                (home, through, limit),
            )
        )

    def outstanding(self, home: str, product_id: str) -> int:
        row = self.connection.execute(
            "SELECT purchased-settled FROM shopping_purchases WHERE household_id=? "
            "AND product_id=? AND settled<purchased",
            (home, product_id),
        ).fetchone()
        return 0 if row is None else int(row[0])

    def add_purchase(self, home: str, purchase: Purchase) -> None:
        self.connection.execute(
            "INSERT INTO shopping_purchases VALUES (NULL,?,?,?,?,?,?,?,?,?,?,?)",
            (home, *astuple(purchase)),
        )

    def update_purchase(self, home: str, purchase: Purchase) -> None:
        self.connection.execute(
            "UPDATE shopping_purchases SET received=?,settled=?,revision=? "
            "WHERE household_id=? AND purchase_id=?",
            (purchase.received, purchase.settled, purchase.revision, home, purchase.purchase_id),
        )

    def receipt(self, home: str, receipt_id: str) -> PurchaseReceipt | None:
        row = self.connection.execute(
            "SELECT * FROM shopping_receipts WHERE household_id=? AND receipt_id=?",
            (home, receipt_id),
        ).fetchone()
        return None if row is None else _receipt(row)

    def receipts(
        self, home: str, purchase_id: str, through: int, limit: int
    ) -> tuple[tuple[int, PurchaseReceipt], ...]:
        return tuple(
            (row["position"], _receipt(row))
            for row in self.connection.execute(
                "SELECT * FROM shopping_receipts WHERE household_id=? AND purchase_id=? "
                "AND position<=? ORDER BY position DESC LIMIT ?",
                (home, purchase_id, through, limit),
            )
        )

    def add_receipt(self, home: str, receipt: PurchaseReceipt) -> None:
        self.connection.execute(
            "INSERT INTO shopping_receipts VALUES (NULL,?,?,?,?,?,?,?)",
            (home, *astuple(receipt)),
        )

    def link_movement(self, home: str, receipt_id: str, movement_id: str) -> None:
        self.connection.execute(
            "UPDATE shopping_receipts SET movement_id=? WHERE household_id=? AND receipt_id=?",
            (movement_id, home, receipt_id),
        )


def verify_shopping_records(connection: sqlite3.Connection) -> None:
    stock = SQLiteInventory(connection)
    for row in connection.execute("SELECT * FROM shopping_purchases"):
        purchase, home = _purchase(row), row["household_id"]
        validate_identifier(purchase.purchase_id)
        validate_task_text(purchase.name, 160, required=True)
        validate_task_time(purchase.created_at)
        product = None
        if purchase.product_id is not None:
            product = stock.product(home, purchase.product_id)
            if product is None or product.base_unit != purchase.base_unit:
                raise StorageFailure("invalid_shopping_records")
        if purchase.base_unit is BaseUnit.PIECE and purchase.purchased % 1_000_000:
            raise StorageFailure("invalid_shopping_records")
        received, settled, revision = 0, 0, 1
        for receipt_row in connection.execute(
            "SELECT * FROM shopping_receipts WHERE household_id=? AND purchase_id=?",
            (home, purchase.purchase_id),
        ):
            receipt = _receipt(receipt_row)
            validate_identifier(receipt.receipt_id)
            validate_task_time(receipt.created_at)
            if purchase.base_unit is BaseUnit.PIECE and receipt.quantity % 1_000_000:
                raise StorageFailure("invalid_shopping_records")
            received += receipt.quantity
            revision += 1
            movement = stock.movement(home, receipt.stock_source)
            if receipt.movement_id != (None if movement is None else movement.movement_id):
                raise StorageFailure("invalid_shopping_records")
            if movement is not None:
                if (
                    product is None
                    or movement.reference_id != product.reference_id
                    or movement.kind is not MovementKind.INTAKE
                    or movement.delta != receipt.quantity
                ):
                    raise StorageFailure("invalid_shopping_records")
                settled += receipt.quantity
                revision += 1
        if product is None:
            settled = received
        if (received, settled, revision) != (
            purchase.received,
            purchase.settled,
            purchase.revision,
        ):
            raise StorageFailure("invalid_shopping_records")
