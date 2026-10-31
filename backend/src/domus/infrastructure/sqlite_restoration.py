"""Prepare and inspect a private blocked checkpoint plus complete processed-operation plan."""

import hashlib
import itertools
import json
import math
import os
import sqlite3
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from domus.application.ports import Clock
from domus.domain.errors import Conflict, DatabaseRejected, DomusError, InvalidInput, StorageFailure
from domus.domain.restoration import (
    OperationEvidence,
    PreparedRestoration,
    RetainedOperation,
    reconcile_operations,
)
from domus.domain.snapshots import Snapshot
from domus.domain.storage import (
    AuditEntry,
    Installation,
    JsonDocument,
    OutboxEvent,
    _unique_object,
    validate_identifier,
)
from domus.infrastructure.owned_storage import (
    RESTORE_MANIFEST,
    RESTORE_OPERATIONS,
    _file,
    _identity,
    _write_identity,
)
from domus.infrastructure.sqlite import SQLiteDatabase, _receipt
from domus.infrastructure.sqlite_snapshots import (
    SQLiteSnapshots,
    _Budget,
    _connection,
    _directory,
    _hash,
    _verify_database,
)

_DATABASE, _IDENTITY, _OPERATIONS = "domus.sqlite3", "installation.json", RESTORE_OPERATIONS
_FILES = {_DATABASE, _IDENTITY, _OPERATIONS, RESTORE_MANIFEST}
_ROW_LIMIT = 262_144


def _encoded(value: RetainedOperation) -> bytes:
    return (
        json.dumps(value.value(), sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _operations(connection: sqlite3.Connection, budget: _Budget) -> Iterator[RetainedOperation]:
    for row in connection.execute(
        "SELECT r.*,a.detail AS audit_detail,o.payload AS event_payload,o.position,o.delivered "
        "FROM receipts r JOIN audit a ON a.operation_id=r.operation_id "
        "JOIN outbox o ON o.event_id=r.operation_id "
        "ORDER BY r.household_id,r.actor_id,r.action,r.command_key"
    ):
        budget.check()
        receipt = _receipt(row)
        assert receipt is not None
        yield RetainedOperation(
            OperationEvidence(
                receipt,
                AuditEntry(
                    receipt.operation_id,
                    receipt.command,
                    JsonDocument(row["audit_detail"]),
                    receipt.created_at,
                ),
                OutboxEvent(
                    receipt.operation_id,
                    receipt.command.household_id,
                    receipt.command.action,
                    JsonDocument(row["event_payload"]),
                    receipt.created_at,
                ),
                row["position"],
                bool(row["delivered"]),
            ),
            True,
        )


def _read_operations(directory: int, budget: _Budget) -> Iterator[RetainedOperation]:
    descriptor = _file(directory, _OPERATIONS)
    with os.fdopen(descriptor, "rb") as stream:
        while line := stream.readline(_ROW_LIMIT + 1):
            budget.check()
            if len(line) > _ROW_LIMIT or not line.endswith(b"\n"):
                raise DatabaseRejected("invalid_restore_operations")
            try:
                yield RetainedOperation.from_value(
                    json.loads(line.decode("utf-8"), object_pairs_hook=_unique_object)
                )
            except DomusError, ValueError, UnicodeError, RecursionError:
                raise DatabaseRejected("invalid_restore_operations") from None


def _pending(installation: Installation) -> JsonDocument:
    return JsonDocument.from_value(
        {
            "schema_version": 1,
            "instance_id": installation.instance_id,
            "channel": installation.channel,
            "state": "restore_pending",
        }
    )


def _read_document(directory: int, name: str) -> JsonDocument:
    descriptor = _file(directory, name)
    try:
        content = os.read(descriptor, 16_385)
    finally:
        os.close(descriptor)
    try:
        if len(content) > 16_384:
            raise InvalidInput("invalid_document")
        return JsonDocument(content.decode("utf-8"))
    except DomusError, UnicodeError:
        raise DatabaseRejected("invalid_restore_manifest") from None


@dataclass
class SQLiteRestorations:
    database: SQLiteDatabase | None
    snapshot_location: Path | None
    location: Path
    installation: Installation
    clock: Clock
    checkpoint: Snapshot | None = None
    timeout: float = 30
    monotonic: Callable[[], float] = field(default=time.monotonic, repr=False)

    def __post_init__(self) -> None:
        if (
            type(self.timeout) not in (int, float)
            or not math.isfinite(self.timeout)
            or not 0 < self.timeout <= 3600
        ):
            raise InvalidInput("invalid_restore_timeout")

    def prepare(self, restore_id: str) -> PreparedRestoration:
        validate_identifier(restore_id)
        if self.database is None or self.snapshot_location is None or self.checkpoint is None:
            raise InvalidInput("restore_sources_required")
        if (
            self.database.installation != self.installation
            or self.checkpoint.installation != self.installation
        ):
            raise DatabaseRejected("installation_mismatch")
        budget = _Budget(self.monotonic() + self.timeout, self.monotonic)
        inspected = SQLiteSnapshots(
            None,
            self.snapshot_location,
            self.installation,
            self.clock,
            self.timeout,
            self.monotonic,
        ).inspect()
        budget.check()
        if inspected != self.checkpoint:
            raise DatabaseRejected("restore_checkpoint_changed")
        if self.location.resolve().is_relative_to(self.snapshot_location.resolve()):
            raise InvalidInput("restore_destination_inside_source")
        try:
            with _directory(self.database.path.parent, private=False) as source_dir:
                os.close(_file(source_dir, self.database.path.name))
                if _IDENTITY in os.listdir(source_dir):
                    installation, state = _identity(source_dir)
                    if installation != self.installation or state != "ready":
                        raise DatabaseRejected("installation_mismatch")
                    if self.location.resolve().is_relative_to(self.database.path.parent):
                        raise InvalidInput("restore_destination_inside_source")
                with _connection(self.database.path, budget, readonly=True) as current:
                    current.execute("BEGIN")
                    source_version = _verify_database(current, self.database, previous=True)
                    with _directory(self.location.parent, private=False) as parent:
                        try:
                            os.mkdir(self.location.name, 0o700, dir_fd=parent)
                        except FileExistsError:
                            raise Conflict("restore_destination_exists") from None
                        with _directory(self.location, private=True) as target:
                            return self._prepare(
                                current, source_version, target, parent, restore_id, budget
                            )
        except OSError:
            raise StorageFailure("restore_storage_failure") from None

    def _prepare(
        self,
        current: sqlite3.Connection,
        source_version: int,
        target: int,
        parent: int,
        restore_id: str,
        budget: _Budget,
    ) -> PreparedRestoration:
        checkpoint = cast(Snapshot, self.checkpoint)
        with _directory(cast(Path, self.snapshot_location), private=True) as archive:
            source_fd = _file(archive, _DATABASE)
            with os.fdopen(source_fd, "rb") as source:
                descriptor = _file(target, _DATABASE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                with os.fdopen(descriptor, "wb") as outgoing:
                    while chunk := source.read(1_048_576):
                        budget.check()
                        outgoing.write(chunk)
                    outgoing.flush()
                    os.fsync(outgoing.fileno())
        digest, size = _hash(target, _DATABASE, budget)
        if (digest, size) != (checkpoint.database_sha256, checkpoint.database_bytes):
            raise DatabaseRejected("snapshot_checksum_mismatch")
        source_hash = hashlib.sha256(
            JsonDocument.from_value(
                {
                    "instance_id": self.installation.instance_id,
                    "channel": self.installation.channel,
                    "schema_version": source_version,
                }
            ).encoded.encode("utf-8")
        )

        def frontier() -> Iterator[RetainedOperation]:
            for item in _operations(current, budget):
                source_hash.update(_encoded(item))
                yield item

        journal_hash = hashlib.sha256()
        count = active = highwater = 0
        database = SQLiteDatabase(self.location / _DATABASE, self.installation)
        with _connection(database.path, budget, readonly=True) as selected:
            _verify_database(selected, database, previous=True)
            descriptor = _file(target, _OPERATIONS, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(descriptor, "wb") as output:
                for item in reconcile_operations(
                    _operations(selected, budget), frontier(), restore_id
                ):
                    budget.check()
                    encoded = _encoded(item)
                    output.write(encoded)
                    journal_hash.update(encoded)
                    count += 1
                    active += int(item.current)
                    highwater = max(highwater, item.evidence.position)
                output.flush()
                os.fsync(output.fileno())
        _write_identity(target, self.installation, "restore_pending", create=True)
        identity_hash, _ = _hash(target, _IDENTITY, budget)
        result = PreparedRestoration(
            restore_id,
            checkpoint,
            source_hash.hexdigest(),
            journal_hash.hexdigest(),
            identity_hash,
            count,
            active,
            highwater,
            self.clock.now(),
        )
        budget.check()
        descriptor = _file(target, RESTORE_MANIFEST, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(descriptor, "w", encoding="utf-8") as manifest:
            manifest.write(result.document().encoded)
            manifest.flush()
            os.fsync(manifest.fileno())
        os.fsync(target)
        os.fsync(parent)
        budget.check()
        return result

    def inspect(self) -> PreparedRestoration:
        budget = _Budget(self.monotonic() + self.timeout, self.monotonic)
        try:
            with _directory(self.location, private=True) as directory:
                if set(os.listdir(directory)) != _FILES:
                    raise DatabaseRejected("incomplete_restore_preparation")
                try:
                    result = PreparedRestoration.from_value(
                        _read_document(directory, RESTORE_MANIFEST).decode()
                    )
                except InvalidInput:
                    raise DatabaseRejected("invalid_restore_manifest") from None
                if result.installation != self.installation:
                    raise DatabaseRejected("installation_mismatch")
                checkpoint = result.checkpoint
                for name, expected in (
                    (_DATABASE, checkpoint.database_sha256),
                    (_IDENTITY, result.identity_sha256),
                    (_OPERATIONS, result.operations_sha256),
                ):
                    digest, size = _hash(directory, name, budget)
                    if digest != expected or (
                        name == _DATABASE and size != checkpoint.database_bytes
                    ):
                        raise DatabaseRejected("restore_checksum_mismatch")
                if _read_document(directory, _IDENTITY) != _pending(self.installation):
                    raise DatabaseRejected("invalid_restore_identity")
                database = SQLiteDatabase(self.location / _DATABASE, self.installation)
                count = active = highwater = 0
                with _connection(database.path, budget, readonly=True) as selected:
                    version = _verify_database(selected, database, previous=True)
                    committed = selected.execute("SELECT max(created_at) FROM receipts").fetchone()[
                        0
                    ]
                    if (
                        version != checkpoint.schema_version
                        or committed != checkpoint.last_committed_at
                    ):
                        raise DatabaseRejected("restore_checkpoint_changed")
                    left, right = itertools.tee(_read_operations(directory, budget))
                    for planned, actual in zip(
                        reconcile_operations(
                            _operations(selected, budget), left, result.restore_id
                        ),
                        right,
                        strict=True,
                    ):
                        if planned != actual:
                            raise DatabaseRejected("invalid_restore_projection")
                        count += 1
                        active += int(actual.current)
                        highwater = max(highwater, actual.evidence.position)
                if (count, active, highwater) != (
                    result.operation_count,
                    result.current_operations,
                    result.highwater,
                ):
                    raise DatabaseRejected("invalid_restore_counts")
                budget.check()
                return result
        except OSError:
            raise StorageFailure("restore_storage_failure") from None
