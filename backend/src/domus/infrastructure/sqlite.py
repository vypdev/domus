"""Owned SQLite files with explicit, bounded and atomic transaction boundaries."""

import math
import os
import sqlite3
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from pathlib import Path

from domus.application.ports import UnitOfWork
from domus.domain.errors import (
    Conflict,
    DatabaseRejected,
    DomusError,
    InvalidInput,
    StorageBusy,
    StorageFailure,
)
from domus.domain.storage import (
    AuditEntry,
    CommandKey,
    Household,
    Installation,
    JsonDocument,
    OutboxEvent,
    Receipt,
    validate_identifier,
)
from domus.infrastructure.sqlite_history import HISTORY_STATEMENTS, SQLiteHistory
from domus.infrastructure.sqlite_identity import SQLiteMembers, SQLitePolicies
from domus.infrastructure.sqlite_recovery import SQLiteRecoveries
from domus.infrastructure.sqlite_task_material_schema import (
    MATERIAL_STATEMENTS,
    MATERIAL_TABLES,
    migrate_task_documents,
)
from domus.infrastructure.sqlite_task_materials import SQLiteTaskMaterials
from domus.infrastructure.sqlite_task_schema import TASK_STATEMENTS, TASK_TABLES
from domus.infrastructure.sqlite_tasks import SQLiteTasks

SCHEMA_VERSION = 6
APPLICATION_ID = 0x444F4D55
BASE_STATEMENTS = (
    "CREATE TABLE installation(singleton INTEGER PRIMARY KEY CHECK(singleton=1), "
    "instance_id TEXT NOT NULL, channel TEXT NOT NULL CHECK(channel IN ('stable','edge')))",
    "CREATE TABLE households(household_id TEXT PRIMARY KEY, singleton INTEGER NOT NULL "
    "DEFAULT 1 UNIQUE CHECK(singleton=1), name TEXT NOT NULL, time_zone TEXT NOT NULL, "
    "revision INTEGER NOT NULL CHECK(revision>=1))",
    "CREATE TABLE receipts(household_id TEXT NOT NULL REFERENCES households(household_id), "
    "actor_id TEXT NOT NULL, action TEXT NOT NULL, command_key TEXT NOT NULL, "
    "payload_fingerprint TEXT NOT NULL, operation_id TEXT NOT NULL UNIQUE, "
    "result TEXT NOT NULL, created_at INTEGER NOT NULL, "
    "PRIMARY KEY(household_id,actor_id,action,command_key))",
    "CREATE TABLE audit(operation_id TEXT PRIMARY KEY, "
    "household_id TEXT NOT NULL REFERENCES households(household_id), "
    "actor_id TEXT NOT NULL, action TEXT NOT NULL, command_key TEXT NOT NULL, "
    "detail TEXT NOT NULL, created_at INTEGER NOT NULL)",
    "CREATE TABLE outbox(position INTEGER PRIMARY KEY AUTOINCREMENT, "
    "event_id TEXT NOT NULL UNIQUE, "
    "household_id TEXT NOT NULL REFERENCES households(household_id), "
    "event_type TEXT NOT NULL, payload TEXT NOT NULL, created_at INTEGER NOT NULL, "
    "delivered INTEGER NOT NULL DEFAULT 0 CHECK(delivered IN (0,1)))",
    "CREATE INDEX outbox_pending ON outbox(delivered,position)",
)
IDENTITY_STATEMENTS = (
    "CREATE TABLE members(member_id TEXT PRIMARY KEY, "
    "household_id TEXT NOT NULL REFERENCES households(household_id), ha_user_id TEXT NOT NULL, "
    "role TEXT NOT NULL CHECK(role IN ('administrator','adult','restricted','viewer')), "
    "status TEXT NOT NULL CHECK(status IN ('pending','active','suspended','archived')), "
    "revision INTEGER NOT NULL CHECK(revision>=1), exceptions TEXT NOT NULL, "
    "UNIQUE(household_id,ha_user_id))",
    "CREATE TABLE household_policy(household_id TEXT PRIMARY KEY "
    "REFERENCES households(household_id), mapping_mode TEXT NOT NULL, target_ha_user_id TEXT, "
    "revision INTEGER NOT NULL CHECK(revision>=1), adjustments TEXT NOT NULL, "
    "CHECK((mapping_mode='all_ha_administrators' AND target_ha_user_id IS NULL) "
    "OR (mapping_mode IN ('setup_administrator','selected_ha_user') "
    "AND target_ha_user_id IS NOT NULL)))",
)
RECOVERY_STATEMENTS = (
    "CREATE TABLE recovery_requests(request_id TEXT PRIMARY KEY, "
    "household_id TEXT NOT NULL REFERENCES households(household_id), "
    "target_ha_user_id TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision>=1), "
    "state TEXT NOT NULL CHECK(state IN ('pending','approved','consumed','canceled')), "
    "created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL, detail TEXT NOT NULL)",
    "CREATE INDEX recovery_pending ON recovery_requests(household_id,state,expires_at)",
)
SCHEMA_STATEMENTS = (
    *BASE_STATEMENTS,
    *IDENTITY_STATEMENTS,
    *RECOVERY_STATEMENTS,
    *HISTORY_STATEMENTS,
    *TASK_STATEMENTS,
    *MATERIAL_STATEMENTS,
)
BASE_TABLES = {"installation", "households", "receipts", "audit", "outbox"}
IDENTITY_TABLES = BASE_TABLES | {"members", "household_policy"}
RECOVERY_TABLES = IDENTITY_TABLES | {"recovery_requests"}
HISTORY_TABLES = RECOVERY_TABLES | {"retained_operations"}
TASK_SCHEMA_TABLES = HISTORY_TABLES | TASK_TABLES
TABLES = TASK_SCHEMA_TABLES | MATERIAL_TABLES


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


def _storage_error(error: sqlite3.Error) -> DomusError:
    if getattr(error, "sqlite_errorcode", 0) & 0xFF in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
        return StorageBusy("storage_busy")
    return StorageFailure("storage_failure")


@dataclass
class SQLiteHouseholds:
    connection: sqlite3.Connection

    def get(self, household_id: str) -> Household | None:
        row = self.connection.execute(
            "SELECT * FROM households WHERE household_id=?", (household_id,)
        ).fetchone()
        return self._record(row)

    def current(self) -> Household | None:
        return self._record(self.connection.execute("SELECT * FROM households").fetchone())

    @staticmethod
    def _record(row: sqlite3.Row | None) -> Household | None:
        if row is None:
            return None
        return Household(row["household_id"], row["name"], row["time_zone"], row["revision"])

    def save(self, household: Household, expected_revision: int) -> None:
        if household.revision != expected_revision + 1:
            raise Conflict("revision_conflict")
        if expected_revision == 0:
            try:
                self.connection.execute(
                    "INSERT INTO households(household_id,name,time_zone,revision) VALUES (?,?,?,?)",
                    (
                        household.household_id,
                        household.name,
                        household.time_zone,
                        household.revision,
                    ),
                )
            except sqlite3.IntegrityError:
                raise Conflict("household_exists") from None
        else:
            updated = self.connection.execute(
                "UPDATE households SET name=?,time_zone=?,revision=? "
                "WHERE household_id=? AND revision=?",
                (
                    household.name,
                    household.time_zone,
                    household.revision,
                    household.household_id,
                    expected_revision,
                ),
            )
            if updated.rowcount != 1:
                raise Conflict("revision_conflict")


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


@dataclass
class SQLiteAudit:
    connection: sqlite3.Connection

    def append(self, entry: AuditEntry) -> None:
        self.connection.execute(
            "INSERT INTO audit VALUES (?,?,?,?,?,?,?)",
            (entry.operation_id, *_scope(entry.command), entry.detail.encoded, entry.created_at),
        )

    def entries(self, household_id: str) -> tuple[AuditEntry, ...]:
        return tuple(
            AuditEntry(
                row["operation_id"], _command(row), JsonDocument(row["detail"]), row["created_at"]
            )
            for row in self.connection.execute(
                "SELECT * FROM audit WHERE household_id=? ORDER BY rowid", (household_id,)
            )
        )

    def setup_actor(self, household_id: str) -> str | None:
        rows = self.connection.execute(
            "SELECT actor_id FROM audit WHERE household_id=? AND action='household.setup' LIMIT 2",
            (household_id,),
        ).fetchall()
        if not rows:
            return None
        if len(rows) != 1:
            raise StorageFailure("invalid_setup_provenance")
        try:
            actor_id: str = rows[0]["actor_id"]
            validate_identifier(actor_id)
            return actor_id
        except InvalidInput:
            raise StorageFailure("invalid_setup_provenance") from None


@dataclass
class SQLiteOutbox:
    connection: sqlite3.Connection

    def append(self, event: OutboxEvent) -> None:
        self.connection.execute(
            "INSERT INTO outbox(event_id,household_id,event_type,payload,created_at) "
            "VALUES (?,?,?,?,?)",
            (
                event.event_id,
                event.household_id,
                event.event_type,
                event.payload.encoded,
                event.created_at,
            ),
        )

    def pending(self, limit: int = 50) -> tuple[OutboxEvent, ...]:
        if type(limit) is not int or not 1 <= limit <= 200:
            raise InvalidInput("invalid_page_size")
        return tuple(
            OutboxEvent(
                row["event_id"],
                row["household_id"],
                row["event_type"],
                JsonDocument(row["payload"]),
                row["created_at"],
            )
            for row in self.connection.execute(
                "SELECT * FROM outbox WHERE delivered=0 ORDER BY position LIMIT ?", (limit,)
            )
        )

    def acknowledge(self, event_id: str) -> bool:
        return (
            self.connection.execute(
                "UPDATE outbox SET delivered=1 WHERE event_id=? AND delivered=0", (event_id,)
            ).rowcount
            == 1
        )

    def delivered(self, event_id: str) -> bool | None:
        row = self.connection.execute(
            "SELECT delivered FROM outbox WHERE event_id=?", (event_id,)
        ).fetchone()
        if row is None:
            return SQLiteHistory(self.connection).delivery(event_id)
        value = row["delivered"]
        if type(value) is not int or value not in (0, 1):
            raise StorageFailure("invalid_operation_record")
        return value == 1


class SQLiteUnit:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.households = SQLiteHouseholds(connection)
        self.receipts = SQLiteReceipts(connection)
        self.audit = SQLiteAudit(connection)
        self.outbox = SQLiteOutbox(connection)
        self.members = SQLiteMembers(connection)
        self.policies = SQLitePolicies(connection)
        self.recoveries = SQLiteRecoveries(connection)
        self.tasks = SQLiteTasks(connection)
        self.task_materials = SQLiteTaskMaterials(connection)


class SQLiteDatabase:
    def __init__(
        self, path: Path, installation: Installation, *, busy_timeout: float = 0.25
    ) -> None:
        if not math.isfinite(busy_timeout) or not 0 < busy_timeout <= 5:
            raise InvalidInput("invalid_storage_timeout")
        self.path = path.resolve()
        self.installation = installation
        self.busy_timeout = busy_timeout

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        try:
            connection = sqlite3.connect(
                self.path.as_uri() + "?mode=rw",
                uri=True,
                timeout=self.busy_timeout,
                autocommit=True,
            )
        except sqlite3.Error as error:
            raise _storage_error(error) from None
        connection.row_factory = sqlite3.Row
        try:
            yield connection
        finally:
            connection.close()

    def _inspect(
        self,
        connection: sqlite3.Connection,
        *,
        allow_empty: bool = False,
        allow_previous: bool = False,
    ) -> int:
        try:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            application_id = connection.execute("PRAGMA application_id").fetchone()[0]
            objects = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type IN ('table','view','trigger') "
                    "AND name NOT LIKE 'sqlite_%'"
                )
            }
            if version == 0 and application_id == 0 and not objects and allow_empty:
                return 0
            if version != SCHEMA_VERSION and not (allow_previous and version in (1, 2, 3, 4, 5)):
                raise DatabaseRejected("unsupported_schema")
            expected_tables = {
                1: BASE_TABLES,
                2: IDENTITY_TABLES,
                3: RECOVERY_TABLES,
                4: HISTORY_TABLES,
                5: TASK_SCHEMA_TABLES,
            }.get(version, TABLES)
            if application_id != APPLICATION_ID or objects != expected_tables:
                raise DatabaseRejected("unrelated_database")
            identity = connection.execute("SELECT instance_id,channel FROM installation").fetchone()
            if identity is None or tuple(identity) != (
                self.installation.instance_id,
                self.installation.channel,
            ):
                raise DatabaseRejected("installation_mismatch")
        except sqlite3.Error:
            raise DatabaseRejected("invalid_database") from None
        return int(version)

    def initialize(self, *, require_existing: bool = False) -> None:
        if not require_existing:
            try:
                descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                pass
            except OSError:
                raise StorageFailure("storage_failure") from None
            else:
                os.close(descriptor)
        with self._connection() as connection:
            self._inspect(connection, allow_empty=not require_existing, allow_previous=True)
            connection.execute("PRAGMA foreign_keys=ON")
            try:
                connection.execute("BEGIN IMMEDIATE")
                version = self._inspect(
                    connection, allow_empty=not require_existing, allow_previous=True
                )
                if version == 0:
                    for statement in SCHEMA_STATEMENTS:
                        connection.execute(statement)
                    connection.execute(
                        "INSERT INTO installation VALUES (1,?,?)",
                        (self.installation.instance_id, self.installation.channel),
                    )
                    connection.execute(f"PRAGMA application_id={APPLICATION_ID}")
                    connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
                elif version in (1, 2, 3, 4, 5):
                    migration = (
                        *(IDENTITY_STATEMENTS if version == 1 else ()),
                        *(RECOVERY_STATEMENTS if version < 3 else ()),
                        *(HISTORY_STATEMENTS if version < 4 else ()),
                        *(TASK_STATEMENTS if version < 5 else ()),
                        *MATERIAL_STATEMENTS,
                    )
                    for statement in migration:
                        connection.execute(statement)
                    migrate_task_documents(connection)
                    connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
                connection.execute("COMMIT")
            except BaseException as error:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                if isinstance(error, sqlite3.Error):
                    raise _storage_error(error) from None
                raise

    @contextmanager
    def _transaction(self, *, write: bool) -> Iterator[UnitOfWork]:
        with self._connection() as connection:
            self._inspect(connection)
            connection.execute("PRAGMA foreign_keys=ON")
            if not write:
                connection.execute("PRAGMA query_only=ON")
            try:
                connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
                self._inspect(connection)
                yield SQLiteUnit(connection)
                connection.execute("COMMIT")
            except BaseException as error:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                if isinstance(error, sqlite3.Error):
                    raise _storage_error(error) from None
                raise

    def read(self) -> AbstractContextManager[UnitOfWork]:
        return self._transaction(write=False)

    def write(self) -> AbstractContextManager[UnitOfWork]:
        return self._transaction(write=True)
