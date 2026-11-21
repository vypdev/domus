"""Scoped current/retained command receipts shared by storage adapters without a unit cycle."""

import sqlite3
from dataclasses import dataclass

from domus.domain.errors import Conflict, InvalidInput, StorageFailure
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

    def automation_run_page(
        self,
        household_id: str,
        actor_id: str,
        member_id: str,
        rule_id: str,
        *,
        limit: int,
        through: int,
    ) -> tuple[tuple[int, Receipt], ...]:
        scope = (household_id, actor_id, rule_id, member_id, through)
        rows = self.connection.execute(
            "SELECT r.operation_id,o.position,0 AS historical FROM receipts r "
            "JOIN outbox o ON o.event_id=r.operation_id "
            "WHERE r.household_id=? AND r.actor_id=? AND r.action='automation.run' "
            "AND json_extract(r.result,'$.rule_id')=? AND json_extract(r.result,'$.member_id')=? "
            "AND o.position<=? UNION ALL "
            "SELECT operation_id,position,1 AS historical FROM retained_operations "
            "WHERE household_id=? AND actor_id=? AND action='automation.run' AND current=0 "
            "AND json_extract(document,'$.result.rule_id')=? "
            "AND json_extract(document,'$.result.member_id')=? AND position<=? "
            "ORDER BY position DESC LIMIT ?",
            (*scope, *scope, limit),
        ).fetchall()
        page = []
        for row in rows:
            receipt = self.get_operation(household_id, actor_id, row["operation_id"])
            if receipt is None or receipt.historical != bool(row["historical"]):
                raise StorageFailure("invalid_retained_projection")
            page.append((row["position"], receipt))
        return tuple(page)

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

    def archived_scheduled_runs(
        self,
        household_id: str,
        principal: str,
        *,
        before: tuple[int, str] | None,
        limit: int,
    ) -> tuple[Receipt, ...]:
        position = (
            ""
            if before is None
            else (" AND (json_extract(h.document,'$.result.run.admitted_at'),h.command_key)<(?,?)")
        )
        after: tuple[object, ...] = () if before is None else before
        rows = self.connection.execute(
            "SELECT h.operation_id FROM retained_operations h "
            "WHERE h.household_id=? AND h.actor_id=? AND h.current=0 "
            "AND h.action IN ('automation.scheduled.admit','automation.scheduled.run') "
            "AND (h.action='automation.scheduled.run' OR ("
            "NOT EXISTS(SELECT 1 FROM retained_operations r WHERE r.household_id=h.household_id "
            "AND r.actor_id=h.actor_id AND r.command_key=h.command_key "
            "AND r.action='automation.scheduled.run') AND "
            "NOT EXISTS(SELECT 1 FROM receipts r WHERE r.household_id=h.household_id "
            "AND r.actor_id=h.actor_id AND r.command_key=h.command_key "
            "AND r.action='automation.scheduled.run')))"
            + position
            + " ORDER BY json_extract(h.document,'$.result.run.admitted_at') DESC,"
            "h.command_key DESC LIMIT ?",
            (household_id, principal, *after, limit),
        ).fetchall()
        result = []
        for row in rows:
            receipt = self.get_operation(household_id, principal, row["operation_id"])
            if receipt is None or not receipt.historical:
                raise StorageFailure("invalid_retained_projection")
            result.append(receipt)
        return tuple(result)
