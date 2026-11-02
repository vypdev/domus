"""Scoped current/retained command receipts shared by storage adapters without a unit cycle."""

import sqlite3
from dataclasses import dataclass

from domus.domain.errors import Conflict, InvalidInput
from domus.domain.storage import CommandKey, JsonDocument, Receipt
from domus.infrastructure.sqlite_history import SQLiteHistory


def _scope(command: CommandKey) -> tuple[str, str, str, str]:
    return command.household_id, command.actor_id, command.action, command.key


def _command(row: sqlite3.Row) -> CommandKey:
    return CommandKey(row["household_id"], row["actor_id"], row["action"], row["command_key"])


def _receipt(row: sqlite3.Row | None) -> Receipt | None:
    if row is None:
        return None
    return Receipt(
        _command(row),
        row["payload_fingerprint"],
        row["operation_id"],
        JsonDocument(row["result"]),
        row["created_at"],
    )


@dataclass
class SQLiteReceipts:
    connection: sqlite3.Connection

    def get(self, command: CommandKey) -> Receipt | None:
        original = _receipt(
            self.connection.execute(
                "SELECT * FROM receipts WHERE household_id=? AND actor_id=? "
                "AND action=? AND command_key=?",
                _scope(command),
            ).fetchone()
        )
        return SQLiteHistory(self.connection).receipt(command, original)

    def get_operation(self, household_id: str, actor_id: str, operation_id: str) -> Receipt | None:
        original = _receipt(
            self.connection.execute(
                "SELECT * FROM receipts WHERE household_id=? AND actor_id=? AND operation_id=?",
                (household_id, actor_id, operation_id),
            ).fetchone()
        )
        history = SQLiteHistory(self.connection)
        if original is not None:
            return history.receipt(original.command, original)
        return history.operation(household_id, actor_id, operation_id)

    def add(self, receipt: Receipt) -> None:
        if receipt.restoration is not None:
            raise InvalidInput("receipt_projection_not_storable")
        if (
            self.connection.execute(
                "SELECT 1 FROM retained_operations WHERE operation_id=? OR "
                "(household_id=? AND actor_id=? AND action=? AND command_key=?) LIMIT 1",
                (receipt.operation_id, *_scope(receipt.command)),
            ).fetchone()
            is not None
        ):
            raise Conflict("operation_collision")
        self.connection.execute(
            "INSERT INTO receipts VALUES (?,?,?,?,?,?,?,?)",
            (
                *_scope(receipt.command),
                receipt.payload_fingerprint,
                receipt.operation_id,
                receipt.result.encoded,
                receipt.created_at,
            ),
        )
