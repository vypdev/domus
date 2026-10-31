"""Retained facts are independent of current household rows and never become pending delivery."""

import heapq
import json
import sqlite3
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, replace
from typing import cast

from domus.domain.errors import Conflict, DomusError, InvalidInput, StorageFailure
from domus.domain.recovery import closed_recovery
from domus.domain.restoration import OperationEvidence, RetainedOperation
from domus.domain.storage import (
    AuditEntry,
    CommandKey,
    JsonDocument,
    OutboxEvent,
    Receipt,
    RestorationProvenance,
    _unique_object,
)

HISTORY_STATEMENTS = (
    "CREATE TABLE retained_operations(household_id TEXT NOT NULL, actor_id TEXT NOT NULL, "
    "action TEXT NOT NULL, command_key TEXT NOT NULL, operation_id TEXT NOT NULL UNIQUE, "
    "position INTEGER NOT NULL UNIQUE CHECK(position>=1), "
    "current INTEGER NOT NULL CHECK(current IN (0,1)), archived_by TEXT, document TEXT NOT NULL, "
    "closed_recovery_id TEXT, "
    "PRIMARY KEY(household_id,actor_id,action,command_key))",
    "CREATE INDEX retained_recovery ON retained_operations(household_id,closed_recovery_id) "
    "WHERE current=0 AND closed_recovery_id IS NOT NULL",
)
_CURRENT = (
    "SELECT r.*,a.detail AS audit_detail,o.payload AS event_payload,o.position,o.delivered "
    "FROM receipts r JOIN audit a ON a.operation_id=r.operation_id "
    "JOIN outbox o ON o.event_id=r.operation_id "
)


def _scope(command: CommandKey) -> tuple[str, str, str, str]:
    return command.household_id, command.actor_id, command.action, command.key


def encode_operation(value: RetainedOperation) -> str:
    return json.dumps(value.value(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _record(row: sqlite3.Row) -> RetainedOperation:
    try:
        document = row["document"]
        if not isinstance(document, str) or len(document.encode("utf-8")) > 262_144:
            raise InvalidInput("invalid_retained_operation")
        result = RetainedOperation.from_value(
            json.loads(document, object_pairs_hook=_unique_object)
        )
        if tuple(
            row[name]
            for name in (
                "household_id",
                "actor_id",
                "action",
                "command_key",
                "operation_id",
                "position",
                "current",
                "archived_by",
                "closed_recovery_id",
            )
        ) != (
            *result.evidence.command_scope,
            result.evidence.receipt.operation_id,
            result.evidence.position,
            int(result.current),
            result.archived_by,
            closed_recovery(result.evidence.receipt) if not result.current else None,
        ):
            raise InvalidInput("invalid_retained_operation")
        return result
    except DomusError, ValueError, UnicodeError, RecursionError:
        raise StorageFailure("invalid_retained_operation") from None


def _evidence(row: sqlite3.Row) -> OperationEvidence:
    command = CommandKey(
        *(row[name] for name in ("household_id", "actor_id", "action", "command_key"))
    )
    if row["delivered"] not in (0, 1):
        raise StorageFailure("invalid_operation_record")
    return OperationEvidence(
        Receipt(
            command,
            row["payload_fingerprint"],
            row["operation_id"],
            JsonDocument(row["result"]),
            row["created_at"],
        ),
        AuditEntry(
            row["operation_id"], command, JsonDocument(row["audit_detail"]), row["created_at"]
        ),
        OutboxEvent(
            row["operation_id"],
            command.household_id,
            command.action,
            JsonDocument(row["event_payload"]),
            row["created_at"],
        ),
        row["position"],
        bool(row["delivered"]),
    )


def _current(connection: sqlite3.Connection, command: CommandKey) -> OperationEvidence | None:
    row = connection.execute(
        _CURRENT + "WHERE r.household_id=? AND r.actor_id=? AND r.action=? AND r.command_key=?",
        _scope(command),
    ).fetchone()
    return _evidence(row) if row is not None else None


def _same(original: OperationEvidence, retained: OperationEvidence) -> bool:
    return replace(original, delivered=retained.delivered) == retained and (
        not original.delivered or retained.delivered
    )


def iter_operations(
    connection: sqlite3.Connection, check: Callable[[], None] = lambda: None
) -> Iterator[RetainedOperation]:
    """Merge sorted current and historical frontiers while streaming payloads."""
    modern = connection.execute("PRAGMA user_version").fetchone()[0] >= 4

    def current() -> Iterator[RetainedOperation]:
        for row in connection.execute(
            _CURRENT + "ORDER BY r.household_id,r.actor_id,r.action,r.command_key"
        ):
            check()
            evidence = _evidence(row)
            retained = SQLiteHistory(connection).get(evidence.receipt.command) if modern else None
            yield RetainedOperation(
                evidence, True, retained.archived_by if retained is not None else None
            )

    def history() -> Iterator[RetainedOperation]:
        if modern:
            for row in connection.execute(
                "SELECT * FROM retained_operations WHERE current=0 "
                "ORDER BY household_id,actor_id,action,command_key"
            ):
                check()
                yield _record(row)

    yield from heapq.merge(current(), history(), key=lambda value: value.evidence.command_scope)


def verify_history(connection: sqlite3.Connection) -> None:
    """Verify current projection, complete facts, unique identities and sequence continuity."""
    highwater = 0
    for row in connection.execute("SELECT * FROM retained_operations"):
        retained = _record(row)
        highwater = max(highwater, retained.evidence.position)
        original = _current(connection, retained.evidence.receipt.command)
        if retained.current:
            if original is None or not _same(retained.evidence, original):
                raise StorageFailure("invalid_retained_projection")
        elif (
            connection.execute(
                "SELECT 1 FROM receipts r JOIN outbox o ON o.event_id=r.operation_id "
                "WHERE (r.household_id=? AND r.actor_id=? AND r.action=? AND r.command_key=?) "
                "OR r.operation_id=? OR o.position=? LIMIT 1",
                (
                    *retained.evidence.command_scope,
                    retained.evidence.receipt.operation_id,
                    retained.evidence.position,
                ),
            ).fetchone()
            is not None
        ):
            raise StorageFailure("invalid_retained_projection")
    # Table uniqueness plus the cross-current checks above already prove a unique frontier.
    for row in connection.execute(_CURRENT):
        highwater = max(highwater, _evidence(row).position)
    rows = connection.execute("SELECT seq FROM sqlite_sequence WHERE name='outbox'").fetchall()
    sequence = rows[0][0] if rows else 0
    if len(rows) > 1 or type(sequence) is not int or not highwater <= sequence <= 2**63 - 1:
        raise StorageFailure("invalid_retained_sequence")


def last_committed_at(connection: sqlite3.Connection) -> int | None:
    if connection.execute("PRAGMA user_version").fetchone()[0] < 4:
        return cast(
            int | None, connection.execute("SELECT max(created_at) FROM receipts").fetchone()[0]
        )
    return max(
        (value.evidence.receipt.created_at for value in iter_operations(connection)), default=None
    )


@dataclass
class SQLiteHistory:
    connection: sqlite3.Connection

    def closed_recovery(self, household_id: str, request_id: str) -> bool:
        row = self.connection.execute(
            "SELECT * FROM retained_operations WHERE household_id=? "
            "AND closed_recovery_id=? AND current=0 LIMIT 1",
            (household_id, request_id),
        ).fetchone()
        if row is None:
            return False
        _record(row)
        return True

    def get(self, command: CommandKey) -> RetainedOperation | None:
        row = self.connection.execute(
            "SELECT * FROM retained_operations WHERE household_id=? AND actor_id=? "
            "AND action=? AND command_key=?",
            _scope(command),
        ).fetchone()
        return _record(row) if row is not None else None

    @staticmethod
    def projected(value: RetainedOperation) -> Receipt:
        provenance = (
            RestorationProvenance(value.archived_by, value.current)
            if value.archived_by is not None
            else None
        )
        return replace(value.evidence.receipt, restoration=provenance)

    def receipt(self, command: CommandKey, original: Receipt | None) -> Receipt | None:
        retained = self.get(command)
        if retained is None:
            return original
        if retained.current != (original is not None) or (
            original is not None and original != retained.evidence.receipt
        ):
            raise StorageFailure("invalid_retained_projection")
        return self.projected(retained)

    def operation(self, household_id: str, actor_id: str, operation_id: str) -> Receipt | None:
        row = self.connection.execute(
            "SELECT * FROM retained_operations WHERE household_id=? "
            "AND actor_id=? AND operation_id=?",
            (household_id, actor_id, operation_id),
        ).fetchone()
        if row is None:
            return None
        retained = _record(row)
        if retained.current:
            raise StorageFailure("invalid_retained_projection")
        return self.projected(retained)

    def delivery(self, event_id: str) -> bool | None:
        row = self.connection.execute(
            "SELECT * FROM retained_operations WHERE operation_id=?", (event_id,)
        ).fetchone()
        if row is None:
            return None
        value = _record(row)
        if value.current:
            raise StorageFailure("invalid_retained_projection")
        return value.evidence.delivered

    def install(self, operations: Iterable[RetainedOperation]) -> None:
        """Only verified offline composition calls this; no commit or activation is implicit."""
        if not self.connection.in_transaction:
            raise StorageFailure("restore_import_transaction_required")
        self.connection.execute("SAVEPOINT restore_history")
        try:
            self._install(operations)
            verify_history(self.connection)
        except BaseException as error:
            self.connection.execute("ROLLBACK TO restore_history")
            self.connection.execute("RELEASE restore_history")
            if isinstance(error, sqlite3.IntegrityError):
                raise Conflict("restore_history_conflict") from None
            raise
        self.connection.execute("RELEASE restore_history")

    def _install(self, operations: Iterable[RetainedOperation]) -> None:
        count = highwater = 0
        previous = None
        for value in operations:
            evidence = value.evidence
            if previous is not None and evidence.command_scope <= previous:
                raise Conflict("restore_history_conflict")
            previous = evidence.command_scope
            original = _current(self.connection, evidence.receipt.command)
            if value.current != (original is not None) or (
                original is not None and not _same(original, evidence)
            ):
                raise Conflict("restore_history_conflict")
            retained = self.get(evidence.receipt.command)
            if retained is not None and (
                not _same(retained.evidence, evidence)
                or (retained.archived_by is not None and retained.archived_by != value.archived_by)
            ):
                raise Conflict("restore_history_conflict")
            self.connection.execute(
                "INSERT INTO retained_operations VALUES (?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(household_id,actor_id,action,command_key) DO UPDATE SET "
                "operation_id=excluded.operation_id,position=excluded.position,current=excluded.current,"
                "archived_by=excluded.archived_by,document=excluded.document,"
                "closed_recovery_id=excluded.closed_recovery_id",
                (
                    *evidence.command_scope,
                    evidence.receipt.operation_id,
                    evidence.position,
                    int(value.current),
                    value.archived_by,
                    encode_operation(value),
                    closed_recovery(evidence.receipt) if not value.current else None,
                ),
            )
            if value.current and evidence.delivered:
                self.connection.execute(
                    "UPDATE outbox SET delivered=1 WHERE event_id=?",
                    (evidence.receipt.operation_id,),
                )
            count += 1
            highwater = max(highwater, evidence.position)
        if (
            self.connection.execute("SELECT count(*) FROM retained_operations").fetchone()[0]
            != count
            or self.connection.execute(
                "SELECT 1 FROM receipts r LEFT JOIN retained_operations h ON "
                "r.operation_id=h.operation_id WHERE h.operation_id IS NULL LIMIT 1"
            ).fetchone()
            is not None
        ):
            raise Conflict("restore_history_incomplete")
        if (
            self.connection.execute(
                "UPDATE sqlite_sequence SET seq=max(seq,?) WHERE name='outbox'", (highwater,)
            ).rowcount
            == 0
        ):
            self.connection.execute(
                "INSERT INTO sqlite_sequence(name,seq) VALUES ('outbox',?)", (highwater,)
            )
