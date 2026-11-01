"""Private, checksummed SQLite checkpoints use the database backup API and strict inspection."""

import hashlib
import math
import os
import re
import sqlite3
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from domus.application.ports import Clock
from domus.domain.errors import (
    Conflict,
    DatabaseRejected,
    DomusError,
    InvalidInput,
    StorageFailure,
)
from domus.domain.recovery import RecoveryRequest
from domus.domain.snapshots import Snapshot
from domus.domain.storage import CommandKey, Installation, JsonDocument, validate_identifier
from domus.infrastructure.owned_storage import _file, _identity, _write_identity
from domus.infrastructure.sqlite import (
    BASE_STATEMENTS,
    IDENTITY_STATEMENTS,
    RECOVERY_STATEMENTS,
    SQLiteDatabase,
    SQLiteUnit,
    _storage_error,
)
from domus.infrastructure.sqlite_history import (
    HISTORY_STATEMENTS,
    last_committed_at,
    verify_history,
)
from domus.infrastructure.sqlite_recovery import _record as _recovery
from domus.infrastructure.sqlite_task_integrity import verify_task_records
from domus.infrastructure.sqlite_task_schema import TASK_STATEMENTS

_DATABASE = "domus.sqlite3"
_IDENTITY = "installation.json"
_MANIFEST = "manifest.json"
_FILES = {_DATABASE, _IDENTITY, _MANIFEST}


@dataclass
class _Budget:
    deadline: float
    now: Callable[[], float]

    def check(self) -> None:
        if self.now() >= self.deadline:
            raise StorageFailure("snapshot_timeout")

    def progress(self, _status: int, _remaining: int, _total: int) -> None:
        self.check()

    def sql(self) -> int:
        return int(self.now() >= self.deadline)


@contextmanager
def _directory(path: Path, *, private: bool) -> Iterator[int]:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        info = os.fstat(descriptor)
        mode = info.st_mode & 0o7777
        if info.st_uid != os.getuid() or (mode != 0o700 if private else bool(mode & 0o022)):
            raise DatabaseRejected("unsafe_snapshot_directory")
        yield descriptor
    finally:
        os.close(descriptor)


@contextmanager
def _connection(path: Path, budget: _Budget, *, readonly: bool) -> Iterator[sqlite3.Connection]:
    try:
        connection = sqlite3.connect(
            path.absolute().as_uri() + ("?mode=ro" if readonly else "?mode=rw"),
            uri=True,
            autocommit=True,
            timeout=0.25,
        )
        try:
            connection.row_factory = sqlite3.Row
            connection.set_progress_handler(budget.sql, 1000)
            connection.execute("PRAGMA trusted_schema=OFF")
            if readonly:
                connection.execute("PRAGMA query_only=ON")
            yield connection
        finally:
            connection.close()
    except sqlite3.Error as error:
        budget.check()
        raise _storage_error(error) from None


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
        )
        for statement in statements:
            connection.execute(statement)
        return _schema(connection)
    finally:
        connection.close()


def _records(connection: sqlite3.Connection, version: int, installation: Installation) -> None:
    rows = connection.execute("PRAGMA integrity_check(1)").fetchall()
    if len(rows) != 1 or tuple(rows[0]) != ("ok",):
        raise DatabaseRejected("invalid_snapshot_database")
    if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise DatabaseRejected("invalid_snapshot_database")
    identities = connection.execute("SELECT singleton FROM installation").fetchall()
    households = connection.execute("SELECT household_id,singleton FROM households").fetchall()
    if (
        len(identities) != 1
        or identities[0][0] != 1
        or len(households) > 1
        or any(row[1] != 1 for row in households)
    ):
        raise DatabaseRejected("invalid_snapshot_database")
    for query in (
        "SELECT 1 FROM receipts r LEFT JOIN audit a ON a.operation_id=r.operation_id "
        "LEFT JOIN outbox o ON o.event_id=r.operation_id WHERE a.operation_id IS NULL "
        "OR o.event_id IS NULL OR a.household_id!=r.household_id OR a.actor_id!=r.actor_id "
        "OR a.action!=r.action OR a.command_key!=r.command_key OR o.household_id!=r.household_id "
        "OR o.event_type!=r.action OR a.created_at!=r.created_at "
        "OR o.created_at!=r.created_at LIMIT 1",
        "SELECT 1 FROM audit a LEFT JOIN receipts r ON r.operation_id=a.operation_id "
        "WHERE r.operation_id IS NULL LIMIT 1",
        "SELECT 1 FROM outbox o LEFT JOIN receipts r ON r.operation_id=o.event_id "
        "WHERE r.operation_id IS NULL LIMIT 1",
    ):
        if connection.execute(query).fetchone() is not None:
            raise DatabaseRejected("incomplete_snapshot_evidence")
    try:
        for table, field in (("receipts", "result"), ("audit", "detail"), ("outbox", "payload")):
            for row in connection.execute(f"SELECT * FROM {table}"):
                JsonDocument(row[field])
                timestamp = row["created_at"]
                if type(timestamp) is not int or not 0 <= timestamp <= 2**63 - 1:
                    raise InvalidInput("invalid_snapshot_timestamp")
                if table == "outbox" and row["delivered"] not in (0, 1):
                    raise InvalidInput("invalid_snapshot_delivery")
                identifier = row["event_id"] if table == "outbox" else row["operation_id"]
                validate_identifier(identifier)
                if table != "outbox":
                    CommandKey(
                        row["household_id"], row["actor_id"], row["action"], row["command_key"]
                    )
        unit = SQLiteUnit(connection)
        for row in households:
            unit.households.get(row[0])
            if version >= 2:
                members = unit.members.list(row[0])
                policy = unit.policies.get(row[0])
                if version >= 5:
                    verify_task_records(connection, row[0], members, policy)
        if version >= 3:
            for row in connection.execute("SELECT * FROM recovery_requests"):
                value = cast(RecoveryRequest, _recovery(row))
                if value.installation != installation:
                    raise DatabaseRejected("invalid_snapshot_database")
        if version >= 4:
            verify_history(connection)
    except DomusError as error:
        raise DatabaseRejected("invalid_snapshot_records") from error


def _verify_database(
    connection: sqlite3.Connection, database: SQLiteDatabase, *, previous: bool
) -> int:
    version = database._inspect(connection, allow_previous=previous)
    if _schema(connection) != _expected_schema(version):
        raise DatabaseRejected("unrelated_database")
    _records(connection, version, database.installation)
    return version


def _copy(source: sqlite3.Connection, target: sqlite3.Connection, budget: _Budget) -> None:
    source.backup(target, pages=128, progress=budget.progress, sleep=0.01)
    target.execute("PRAGMA journal_mode=DELETE")


def _hash(directory: int, name: str, budget: _Budget) -> tuple[str, int]:
    descriptor = _file(directory, name)
    digest, size = hashlib.sha256(), 0
    with os.fdopen(descriptor, "rb") as source:
        while chunk := source.read(1_048_576):
            budget.check()
            digest.update(chunk)
            size += len(chunk)
    budget.check()
    return digest.hexdigest(), size


def _manifest(directory: int) -> Snapshot:
    descriptor = _file(directory, _MANIFEST)
    try:
        content = os.read(descriptor, 16_385)
    finally:
        os.close(descriptor)
    try:
        if len(content) > 16_384:
            raise InvalidInput("invalid_document")
        document = JsonDocument(content.decode("utf-8"))
        value = document.decode()
        result = Snapshot(
            cast(str, value["snapshot_id"]),
            Installation(cast(str, value["instance_id"]), cast(str, value["channel"])),
            cast(int, value["schema_version"]),
            cast(int, value["captured_at"]),
            cast(int | None, value["last_committed_at"]),
            cast(str, value["database_sha256"]),
            cast(int, value["database_bytes"]),
            cast(str, value["identity_sha256"]),
            cast(int, value["format_version"]),
        )
        if result.document() != document:
            raise InvalidInput("invalid_document")
        return result
    except DomusError, KeyError, UnicodeError:
        raise DatabaseRejected("invalid_snapshot_manifest") from None


@dataclass
class SQLiteSnapshots:
    database: SQLiteDatabase | None
    location: Path
    installation: Installation
    clock: Clock
    timeout: float = 30
    monotonic: Callable[[], float] = field(default=time.monotonic, repr=False)

    def __post_init__(self) -> None:
        if (
            type(self.timeout) not in (int, float)
            or not math.isfinite(self.timeout)
            or not 0 < self.timeout <= 3600
        ):
            raise InvalidInput("invalid_snapshot_timeout")

    def create(self, snapshot_id: str) -> Snapshot:
        validate_identifier(snapshot_id)
        if self.database is None:
            raise InvalidInput("snapshot_source_required")
        if self.database.installation != self.installation:
            raise DatabaseRejected("installation_mismatch")
        budget = _Budget(self.monotonic() + self.timeout, self.monotonic)
        try:
            with _directory(self.database.path.parent, private=False) as source_directory:
                os.close(_file(source_directory, self.database.path.name))
                if _IDENTITY in os.listdir(source_directory):
                    identity, state = _identity(source_directory)
                    if identity != self.installation or state != "ready":
                        raise DatabaseRejected("installation_mismatch")
                    if self.location.resolve().is_relative_to(self.database.path.parent):
                        raise InvalidInput("snapshot_destination_inside_source")
                with _connection(self.database.path, budget, readonly=True) as source:
                    source.execute("BEGIN")
                    version = _verify_database(source, self.database, previous=False)
                    committed = last_committed_at(source)
                    captured = self.clock.now()
                    with _directory(self.location.parent, private=False) as parent:
                        try:
                            os.mkdir(self.location.name, 0o700, dir_fd=parent)
                        except FileExistsError:
                            raise Conflict("snapshot_destination_exists") from None
                        with _directory(self.location, private=True) as target_directory:
                            descriptor = _file(
                                target_directory, _DATABASE, os.O_CREAT | os.O_EXCL | os.O_RDWR
                            )
                            os.close(descriptor)
                            with _connection(
                                self.location / _DATABASE, budget, readonly=False
                            ) as target:
                                _copy(source, target, budget)
                                _verify_database(
                                    target,
                                    SQLiteDatabase(self.location / _DATABASE, self.installation),
                                    previous=False,
                                )
                            _write_identity(
                                target_directory, self.installation, "ready", create=True
                            )
                            database_hash, size = _hash(target_directory, _DATABASE, budget)
                            identity_hash, _ = _hash(target_directory, _IDENTITY, budget)
                            result = Snapshot(
                                snapshot_id,
                                self.installation,
                                version,
                                captured,
                                committed,
                                database_hash,
                                size,
                                identity_hash,
                            )
                            descriptor = _file(target_directory, _DATABASE, os.O_RDONLY)
                            try:
                                os.fsync(descriptor)
                            finally:
                                os.close(descriptor)
                            descriptor = _file(
                                target_directory, _MANIFEST, os.O_CREAT | os.O_EXCL | os.O_WRONLY
                            )
                            with os.fdopen(descriptor, "w", encoding="utf-8") as manifest:
                                manifest.write(result.document().encoded)
                                manifest.flush()
                                os.fsync(manifest.fileno())
                            os.fsync(target_directory)
                        os.fsync(parent)
                    return result
        except OSError:
            raise StorageFailure("snapshot_storage_failure") from None

    def inspect(self) -> Snapshot:
        budget = _Budget(self.monotonic() + self.timeout, self.monotonic)
        try:
            with _directory(self.location, private=True) as directory:
                if set(os.listdir(directory)) != _FILES:
                    raise DatabaseRejected("incomplete_snapshot")
                result = _manifest(directory)
                if result.installation != self.installation:
                    raise DatabaseRejected("installation_mismatch")
                digest, size = _hash(directory, _DATABASE, budget)
                identity_hash, _ = _hash(directory, _IDENTITY, budget)
                if (
                    digest != result.database_sha256
                    or size != result.database_bytes
                    or identity_hash != result.identity_sha256
                ):
                    raise DatabaseRejected("snapshot_checksum_mismatch")
                identity, state = _identity(directory)
                if identity != self.installation or state != "ready":
                    raise DatabaseRejected("installation_mismatch")
                database = SQLiteDatabase(self.location / _DATABASE, self.installation)
                with _connection(database.path, budget, readonly=True) as connection:
                    version = _verify_database(connection, database, previous=True)
                    committed = last_committed_at(connection)
                    if version != result.schema_version or committed != result.last_committed_at:
                        raise DatabaseRejected("snapshot_checkpoint_mismatch")
                return result
        except OSError:
            raise StorageFailure("snapshot_storage_failure") from None
