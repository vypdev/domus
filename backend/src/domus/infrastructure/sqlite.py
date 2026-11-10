"""Owned SQLite files with explicit, bounded and atomic transaction boundaries."""

import math
import os
import re
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
from domus.domain.fold_policy import FoldPolicy
from domus.domain.storage import (
    DEFAULT_MATERIALIZATION_HORIZON_DAYS,
    MAX_MATERIALIZATION_HORIZON_DAYS,
    MIN_MATERIALIZATION_HORIZON_DAYS,
    AuditEntry,
    Household,
    Installation,
    JsonDocument,
    OutboxEvent,
    validate_identifier,
)
from domus.infrastructure.sqlite_calendar import SQLiteCalendar
from domus.infrastructure.sqlite_calendar_preferences import (
    CALENDAR_PREFERENCE_STATEMENT,
    SQLiteCalendarPreferences,
)
from domus.infrastructure.sqlite_history import HISTORY_STATEMENTS, SQLiteHistory
from domus.infrastructure.sqlite_identity import SQLiteMembers, SQLitePolicies
from domus.infrastructure.sqlite_inventory import (
    CATALOG_STATEMENTS,
    CATALOG_TABLES,
    INVENTORY_STATEMENTS,
    INVENTORY_TABLES,
    MOVEMENT_HISTORY_STATEMENTS,
    REPLENISHMENT_STATEMENT,
    SQLiteInventory,
)
from domus.infrastructure.sqlite_member_profile_schema import PROFILE_STATEMENTS, PROFILE_TABLES
from domus.infrastructure.sqlite_member_profiles import SQLitePreferences, SQLitePresentations
from domus.infrastructure.sqlite_point_allocations import (
    ALLOCATION_STATEMENTS,
    ALLOCATION_TABLES,
    SQLitePointAllocations,
)
from domus.infrastructure.sqlite_points import POINTS_STATEMENTS, POINTS_TABLE, SQLitePoints
from domus.infrastructure.sqlite_receipts import SQLiteReceipts, _command, _scope
from domus.infrastructure.sqlite_recovery import SQLiteRecoveries
from domus.infrastructure.sqlite_recurrence import SQLiteRecurrences
from domus.infrastructure.sqlite_recurrence_schema import (
    RECURRENCE_STATEMENTS,
    RECURRENCE_TABLES,
    RELATIVE_LIFECYCLE_STATEMENTS,
    RELATIVE_LIFECYCLE_TABLES,
)
from domus.infrastructure.sqlite_rewards import REWARD_STATEMENTS, REWARD_TABLES, SQLiteRewards
from domus.infrastructure.sqlite_shopping import (
    SHOPPING_CANCELLATION_STATEMENTS,
    SHOPPING_CANCELLATION_TABLE,
    SHOPPING_EXTRA_STATEMENTS,
    SHOPPING_RECEIPT_CORRECTION_STATEMENTS,
    SHOPPING_RECEIPT_CORRECTION_TABLE,
    SHOPPING_RECEIPT_VOID_STATEMENTS,
    SHOPPING_RECEIPT_VOID_TABLE,
    SHOPPING_SESSION_STATEMENTS,
    SHOPPING_SESSION_TABLES,
    SHOPPING_STATEMENTS,
    SHOPPING_TABLES,
    SQLiteShopping,
)
from domus.infrastructure.sqlite_task_categories import (
    CATEGORY_STATEMENTS,
    CATEGORY_TABLE,
    SQLiteTaskCategories,
)
from domus.infrastructure.sqlite_task_material_schema import (
    MATERIAL_STATEMENTS,
    MATERIAL_TABLES,
    migrate_task_documents,
)
from domus.infrastructure.sqlite_task_materials import SQLiteTaskMaterials
from domus.infrastructure.sqlite_task_reviews import REVIEW_STATEMENTS
from domus.infrastructure.sqlite_task_schema import (
    MISSED_OCCURRENCE_STATEMENT,
    MISSED_OCCURRENCE_TABLE,
    TASK_STATEMENTS,
    TASK_TABLES,
)
from domus.infrastructure.sqlite_tasks import SQLiteTasks

SCHEMA_VERSION = 28
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
HOUSEHOLD_HORIZON_STATEMENT = (
    "ALTER TABLE households ADD COLUMN materialization_horizon_days INTEGER NOT NULL "
    f"DEFAULT {DEFAULT_MATERIALIZATION_HORIZON_DAYS} "
    "CHECK(typeof(materialization_horizon_days)='integer' AND materialization_horizon_days "
    f"BETWEEN {MIN_MATERIALIZATION_HORIZON_DAYS} AND {MAX_MATERIALIZATION_HORIZON_DAYS})"
)
HOUSEHOLD_FOLD_STATEMENT = (
    "ALTER TABLE households ADD COLUMN repeated_time TEXT NOT NULL DEFAULT 'first_instant' "
    "CHECK(repeated_time IN ('first_instant','second_instant'))"
)
SCHEMA_STATEMENTS = (
    *BASE_STATEMENTS,
    *IDENTITY_STATEMENTS,
    *RECOVERY_STATEMENTS,
    *HISTORY_STATEMENTS,
    *TASK_STATEMENTS,
    *MATERIAL_STATEMENTS,
    *REVIEW_STATEMENTS,
    *RECURRENCE_STATEMENTS,
    *PROFILE_STATEMENTS,
    *RELATIVE_LIFECYCLE_STATEMENTS,
    CALENDAR_PREFERENCE_STATEMENT,
    HOUSEHOLD_HORIZON_STATEMENT,
    HOUSEHOLD_FOLD_STATEMENT,
    MISSED_OCCURRENCE_STATEMENT,
    *CATEGORY_STATEMENTS,
    *POINTS_STATEMENTS,
    *INVENTORY_STATEMENTS,
    *ALLOCATION_STATEMENTS,
    *REWARD_STATEMENTS,
    *CATALOG_STATEMENTS,
    *MOVEMENT_HISTORY_STATEMENTS,
    REPLENISHMENT_STATEMENT,
    *SHOPPING_STATEMENTS,
    *SHOPPING_EXTRA_STATEMENTS,
    *SHOPPING_SESSION_STATEMENTS,
    *SHOPPING_CANCELLATION_STATEMENTS,
    *SHOPPING_RECEIPT_VOID_STATEMENTS,
    *SHOPPING_RECEIPT_CORRECTION_STATEMENTS,
)
BASE_TABLES = {"installation", "households", "receipts", "audit", "outbox"}
IDENTITY_TABLES = BASE_TABLES | {"members", "household_policy"}
RECOVERY_TABLES = IDENTITY_TABLES | {"recovery_requests"}
HISTORY_TABLES = RECOVERY_TABLES | {"retained_operations"}
TASK_SCHEMA_TABLES = HISTORY_TABLES | TASK_TABLES
MATERIAL_SCHEMA_TABLES = TASK_SCHEMA_TABLES | MATERIAL_TABLES
RECURRENCE_SCHEMA_TABLES = MATERIAL_SCHEMA_TABLES | RECURRENCE_TABLES
PROFILE_SCHEMA_TABLES = RECURRENCE_SCHEMA_TABLES | PROFILE_TABLES
LIFECYCLE_SCHEMA_TABLES = PROFILE_SCHEMA_TABLES | RELATIVE_LIFECYCLE_TABLES
CALENDAR_SCHEMA_TABLES = LIFECYCLE_SCHEMA_TABLES | {"calendar_preferences"}
MISSED_SCHEMA_TABLES = CALENDAR_SCHEMA_TABLES | {MISSED_OCCURRENCE_TABLE}
CATEGORY_SCHEMA_TABLES = MISSED_SCHEMA_TABLES | {CATEGORY_TABLE}
POINTS_SCHEMA_TABLES = CATEGORY_SCHEMA_TABLES | {POINTS_TABLE}
INVENTORY_SCHEMA_TABLES = POINTS_SCHEMA_TABLES | INVENTORY_TABLES
ALLOCATION_SCHEMA_TABLES = INVENTORY_SCHEMA_TABLES | ALLOCATION_TABLES
REWARD_SCHEMA_TABLES = ALLOCATION_SCHEMA_TABLES | REWARD_TABLES
CATALOG_SCHEMA_TABLES = REWARD_SCHEMA_TABLES | CATALOG_TABLES
REPLENISHMENT_SCHEMA_TABLES = CATALOG_SCHEMA_TABLES | {"inventory_replenishment"}
PURCHASE_SCHEMA_TABLES = REPLENISHMENT_SCHEMA_TABLES | SHOPPING_TABLES
SHOPPING_LIST_SCHEMA_TABLES = PURCHASE_SCHEMA_TABLES | {"shopping_extras"}
SESSION_SCHEMA_TABLES = SHOPPING_LIST_SCHEMA_TABLES | SHOPPING_SESSION_TABLES
CANCELLATION_SCHEMA_TABLES = SESSION_SCHEMA_TABLES | {SHOPPING_CANCELLATION_TABLE}
VOID_SCHEMA_TABLES = CANCELLATION_SCHEMA_TABLES | {SHOPPING_RECEIPT_VOID_TABLE}
TABLES = VOID_SCHEMA_TABLES | {SHOPPING_RECEIPT_CORRECTION_TABLE}


def _schema(connection: sqlite3.Connection) -> tuple[tuple[str, str], ...]:
    return tuple(
        (row[0], re.sub(r"\s+", " ", row[1]))
        for row in connection.execute(
            "SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    )


def _expected_schema(version: int) -> tuple[tuple[str, str], ...]:
    connection = sqlite3.connect(":memory:", autocommit=True)
    try:
        statements = (
            *BASE_STATEMENTS,
            *(IDENTITY_STATEMENTS if version >= 2 else ()),
            *(RECOVERY_STATEMENTS if version >= 3 else ()),
            *(HISTORY_STATEMENTS if version >= 4 else ()),
            *(TASK_STATEMENTS if version >= 5 else ()),
            *(MATERIAL_STATEMENTS if version >= 6 else ()),
            *(REVIEW_STATEMENTS if version >= 7 else ()),
            *(RECURRENCE_STATEMENTS if version >= 8 else ()),
            *(PROFILE_STATEMENTS if version >= 9 else ()),
            *(RELATIVE_LIFECYCLE_STATEMENTS if version >= 10 else ()),
            *((CALENDAR_PREFERENCE_STATEMENT,) if version >= 11 else ()),
            *((HOUSEHOLD_HORIZON_STATEMENT,) if version >= 12 else ()),
            *((HOUSEHOLD_FOLD_STATEMENT,) if version >= 13 else ()),
            *((MISSED_OCCURRENCE_STATEMENT,) if version >= 14 else ()),
            *(CATEGORY_STATEMENTS if version >= 15 else ()),
            *(POINTS_STATEMENTS if version >= 16 else ()),
            *(INVENTORY_STATEMENTS if version >= 17 else ()),
            *(ALLOCATION_STATEMENTS if version >= 18 else ()),
            *(REWARD_STATEMENTS if version >= 19 else ()),
            *(CATALOG_STATEMENTS if version >= 20 else ()),
            *(MOVEMENT_HISTORY_STATEMENTS if version >= 21 else ()),
            *((REPLENISHMENT_STATEMENT,) if version >= 22 else ()),
            *(SHOPPING_STATEMENTS if version >= 23 else ()),
            *(SHOPPING_EXTRA_STATEMENTS if version >= 24 else ()),
            *(SHOPPING_SESSION_STATEMENTS if version >= 25 else ()),
            *(SHOPPING_CANCELLATION_STATEMENTS if version >= 26 else ()),
            *(SHOPPING_RECEIPT_VOID_STATEMENTS if version >= 27 else ()),
            *(SHOPPING_RECEIPT_CORRECTION_STATEMENTS if version >= 28 else ()),
        )
        for statement in statements:
            connection.execute(statement)
        return _schema(connection)
    finally:
        connection.close()


def _storage_error(error: sqlite3.Error) -> DomusError:
    if getattr(error, "sqlite_errorcode", 0) & 0xFF in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
        return StorageBusy("storage_busy")
    return StorageFailure("storage_failure")


_HOUSEHOLD_SELECT = (
    "SELECT household_id,name,time_zone,revision,materialization_horizon_days,repeated_time "
    "FROM households"
)


@dataclass
class SQLiteHouseholds:
    connection: sqlite3.Connection

    def get(self, household_id: str) -> Household | None:
        row = self.connection.execute(
            _HOUSEHOLD_SELECT + " WHERE household_id=?", (household_id,)
        ).fetchone()
        return self._record(row)

    def current(self) -> Household | None:
        return self._record(self.connection.execute(_HOUSEHOLD_SELECT).fetchone())

    @staticmethod
    def _record(row: sqlite3.Row | None) -> Household | None:
        if row is None:
            return None
        try:
            return Household(
                row["household_id"],
                row["name"],
                row["time_zone"],
                row["revision"],
                row["materialization_horizon_days"],
                FoldPolicy(row["repeated_time"]),
            )
        except InvalidInput, ValueError:
            raise StorageFailure("invalid_identity_record") from None

    def save(self, household: Household, expected_revision: int) -> None:
        if household.revision != expected_revision + 1:
            raise Conflict("revision_conflict")
        if expected_revision == 0:
            try:
                self.connection.execute(
                    "INSERT INTO households(household_id,name,time_zone,revision,"
                    "materialization_horizon_days,repeated_time) VALUES (?,?,?,?,?,?)",
                    (
                        household.household_id,
                        household.name,
                        household.time_zone,
                        household.revision,
                        household.materialization_horizon_days,
                        household.repeated_time.value,
                    ),
                )
            except sqlite3.IntegrityError:
                raise Conflict("household_exists") from None
        else:
            updated = self.connection.execute(
                "UPDATE households SET name=?,time_zone=?,revision=?,"
                "materialization_horizon_days=?,repeated_time=? "
                "WHERE household_id=? AND revision=?",
                (
                    household.name,
                    household.time_zone,
                    household.revision,
                    household.materialization_horizon_days,
                    household.repeated_time.value,
                    household.household_id,
                    expected_revision,
                ),
            )
            if updated.rowcount != 1:
                raise Conflict("revision_conflict")


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
    def __init__(self, connection: sqlite3.Connection, installation: Installation) -> None:
        self.recurrence = SQLiteRecurrences(connection, installation)
        self.calendar = SQLiteCalendar(connection)
        self.calendar_preferences = SQLiteCalendarPreferences(connection)
        self.households = SQLiteHouseholds(connection)
        self.receipts = SQLiteReceipts(connection)
        self.audit = SQLiteAudit(connection)
        self.outbox = SQLiteOutbox(connection)
        self.members = SQLiteMembers(connection)
        self.presentations = SQLitePresentations(connection)
        self.preferences = SQLitePreferences(connection)
        self.policies = SQLitePolicies(connection)
        self.recoveries = SQLiteRecoveries(connection)
        self.tasks = SQLiteTasks(connection)
        self.task_materials = SQLiteTaskMaterials(connection)
        self.task_categories = SQLiteTaskCategories(connection)
        self.points = SQLitePoints(connection)
        self.inventory = SQLiteInventory(connection)
        self.shopping = SQLiteShopping(connection)
        self.point_allocations = SQLitePointAllocations(connection)
        self.rewards = SQLiteRewards(connection)


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
            if version != SCHEMA_VERSION and not (allow_previous and 1 <= version < SCHEMA_VERSION):
                raise DatabaseRejected("unsupported_schema")
            expected_tables = {
                1: BASE_TABLES,
                2: IDENTITY_TABLES,
                3: RECOVERY_TABLES,
                4: HISTORY_TABLES,
                5: TASK_SCHEMA_TABLES,
                6: MATERIAL_SCHEMA_TABLES,
                7: MATERIAL_SCHEMA_TABLES,
                8: RECURRENCE_SCHEMA_TABLES,
                9: PROFILE_SCHEMA_TABLES,
                10: LIFECYCLE_SCHEMA_TABLES,
                11: CALENDAR_SCHEMA_TABLES,
                12: CALENDAR_SCHEMA_TABLES,
                13: CALENDAR_SCHEMA_TABLES,
                14: MISSED_SCHEMA_TABLES,
                15: CATEGORY_SCHEMA_TABLES,
                16: POINTS_SCHEMA_TABLES,
                17: INVENTORY_SCHEMA_TABLES,
                18: ALLOCATION_SCHEMA_TABLES,
                19: REWARD_SCHEMA_TABLES,
                20: CATALOG_SCHEMA_TABLES,
                21: CATALOG_SCHEMA_TABLES,
                22: REPLENISHMENT_SCHEMA_TABLES,
                23: PURCHASE_SCHEMA_TABLES,
                24: SHOPPING_LIST_SCHEMA_TABLES,
                25: SESSION_SCHEMA_TABLES,
                26: CANCELLATION_SCHEMA_TABLES,
                27: VOID_SCHEMA_TABLES,
            }.get(version, TABLES)
            if application_id != APPLICATION_ID or objects != expected_tables:
                raise DatabaseRejected("unrelated_database")
            identity = connection.execute("SELECT instance_id,channel FROM installation").fetchone()
            if identity is None or tuple(identity) != (
                self.installation.instance_id,
                self.installation.channel,
            ):
                raise DatabaseRejected("installation_mismatch")
        except sqlite3.Error as error:
            mapped = _storage_error(error)
            if isinstance(mapped, StorageBusy):
                raise mapped from None
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
                elif version < SCHEMA_VERSION:
                    if version >= 9 and _schema(connection) != _expected_schema(version):
                        raise DatabaseRejected("unrelated_database")
                    migration = (
                        *(IDENTITY_STATEMENTS if version == 1 else ()),
                        *(RECOVERY_STATEMENTS if version < 3 else ()),
                        *(HISTORY_STATEMENTS if version < 4 else ()),
                        *(TASK_STATEMENTS if version < 5 else ()),
                        *(MATERIAL_STATEMENTS if version < 6 else ()),
                        *(REVIEW_STATEMENTS if version < 7 else ()),
                        *(RECURRENCE_STATEMENTS if version < 8 else ()),
                        *(PROFILE_STATEMENTS if version < 9 else ()),
                        *(RELATIVE_LIFECYCLE_STATEMENTS if version < 10 else ()),
                        *((CALENDAR_PREFERENCE_STATEMENT,) if version < 11 else ()),
                        *((HOUSEHOLD_HORIZON_STATEMENT,) if version < 12 else ()),
                        *((HOUSEHOLD_FOLD_STATEMENT,) if version < 13 else ()),
                        *((MISSED_OCCURRENCE_STATEMENT,) if version < 14 else ()),
                        *(CATEGORY_STATEMENTS if version < 15 else ()),
                        *(POINTS_STATEMENTS if version < 16 else ()),
                        *(INVENTORY_STATEMENTS if version < 17 else ()),
                        *(ALLOCATION_STATEMENTS if version < 18 else ()),
                        *(REWARD_STATEMENTS if version < 19 else ()),
                        *(CATALOG_STATEMENTS if version < 20 else ()),
                        *(MOVEMENT_HISTORY_STATEMENTS if version < 21 else ()),
                        *((REPLENISHMENT_STATEMENT,) if version < 22 else ()),
                        *(SHOPPING_STATEMENTS if version < 23 else ()),
                        *(SHOPPING_EXTRA_STATEMENTS if version < 24 else ()),
                        *(SHOPPING_SESSION_STATEMENTS if version < 25 else ()),
                        *(SHOPPING_CANCELLATION_STATEMENTS if version < 26 else ()),
                        *(SHOPPING_RECEIPT_VOID_STATEMENTS if version < 27 else ()),
                        *SHOPPING_RECEIPT_CORRECTION_STATEMENTS,
                    )
                    for statement in migration:
                        connection.execute(statement)
                    if version < 11:
                        connection.execute(
                            "INSERT INTO calendar_preferences(household_id,member_id) "
                            "SELECT household_id,member_id FROM members"
                        )
                    if version < 6:
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
                yield SQLiteUnit(connection, self.installation)
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
