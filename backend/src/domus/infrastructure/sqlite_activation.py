"""Publish one verified offline generation and resume its durable transition without replay."""

import math
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import cast

from domus.application.ports import Clock
from domus.domain.activation import ActivationRecord, ActivationStatus
from domus.domain.errors import (
    Conflict,
    DatabaseRejected,
    DomusError,
    InvalidInput,
    NotFound,
    StorageFailure,
)
from domus.domain.generations import GenerationSelection
from domus.domain.restoration import PreparedRestoration, RestoreSource
from domus.domain.snapshots import Snapshot
from domus.domain.storage import Installation, JsonDocument, validate_identifier
from domus.infrastructure.offline_storage import OfflineStorage, offline_storage
from domus.infrastructure.owned_storage import (
    ACTIVATION_MANIFEST,
    ACTIVATION_NEXT,
    GENERATION_MARKER,
    _document,
    _file,
    _generation_database,
    _metadata,
    _private_directory,
    _write_identity,
    attach_storage,
)
from domus.infrastructure.restore_source import BoundFrontier
from domus.infrastructure.sqlite import SQLiteDatabase
from domus.infrastructure.sqlite_history import SQLiteHistory, last_committed_at
from domus.infrastructure.sqlite_restoration import (
    SQLiteRestorations,
    _read_document,
    _read_operations,
)
from domus.infrastructure.sqlite_snapshots import (
    SQLiteSnapshots,
    _Budget,
    _connection,
    _directory,
    _hash,
    _verify_database,
)
from domus.infrastructure.sqlite_snapshots import _copy as _backup

_INPUT_FILES = {"domus.sqlite3", "installation.json", "operations.jsonl", "restore.json"}
_SLOT_FILES = {
    "domus.sqlite3",
    "installation.json",
    GENERATION_MARKER,
    ".installation.next",
    GENERATION_MARKER + ".next",
    *("domus.sqlite3" + suffix for suffix in ("-journal", "-wal", "-shm")),
}


def _record(directory: int, name: str) -> ActivationRecord:
    try:
        return ActivationRecord.from_value(_read_document(directory, name).decode())
    except InvalidInput:
        raise DatabaseRejected("invalid_activation_record") from None


def _atomic(directory: int, name: str, document: JsonDocument, stage: str | None = None) -> None:
    temporary = stage or name + ".next"
    descriptor = _file(directory, temporary, os.O_RDWR | os.O_CREAT)
    with os.fdopen(descriptor, "wb") as stream:
        stream.truncate(0)
        stream.write(document.encoded.encode("utf-8"))
        stream.flush()
        os.fsync(stream.fileno())
    if name in os.listdir(directory):
        os.close(_file(directory, name))
    os.replace(temporary, name, src_dir_fd=directory, dst_dir_fd=directory)
    os.fsync(directory)


def _child(directory: int, name: str) -> None:
    try:
        os.mkdir(name, 0o700, dir_fd=directory)
    except FileExistsError:
        pass
    with _private_directory(directory, name):
        pass


def _copy(source: int, target: int, name: str, budget: _Budget) -> None:
    incoming = _file(source, name)
    with os.fdopen(incoming, "rb") as stream:
        outgoing = _file(target, name, os.O_RDWR | os.O_CREAT)
        with os.fdopen(outgoing, "wb") as destination:
            destination.truncate(0)
            while chunk := stream.read(1_048_576):
                budget.check()
                destination.write(chunk)
            destination.flush()
            os.fsync(destination.fileno())


@dataclass
class SQLiteActivation:
    root: Path
    installation: Installation
    clock: Clock
    prepared_location: Path | None = None
    restore_id: str | None = None
    timeout: float = 30
    monotonic: Callable[[], float] = time.monotonic

    def __post_init__(self) -> None:
        if (
            type(self.timeout) not in (int, float)
            or not math.isfinite(self.timeout)
            or not 0 < self.timeout <= 3600
        ):
            raise InvalidInput("invalid_restore_timeout")
        if self.restore_id is not None:
            validate_identifier(self.restore_id)

    def _inspect_input(self, location: Path) -> PreparedRestoration:
        return SQLiteRestorations(
            None,
            None,
            location,
            self.installation,
            self.clock,
            timeout=self.timeout,
            monotonic=self.monotonic,
        ).inspect()

    def _pending(self, directory: int) -> ActivationRecord | None:
        names = set(os.listdir(directory))
        if ACTIVATION_MANIFEST not in names and ACTIVATION_NEXT not in names:
            return None
        result = _record(
            directory, ACTIVATION_MANIFEST if ACTIVATION_MANIFEST in names else ACTIVATION_NEXT
        )
        if result.phase == "active" or result.prepared.installation != self.installation:
            raise DatabaseRejected("invalid_activation_record")
        if ACTIVATION_MANIFEST not in names and result.phase != "pending":
            raise DatabaseRejected("invalid_activation_record")
        return result

    def _selected_id(self, pending: ActivationRecord | None) -> str:
        if self.restore_id is not None:
            return self.restore_id
        if self.prepared_location is not None:
            return self._inspect_input(self.prepared_location).restore_id
        if pending is not None:
            return pending.prepared.restore_id
        raise NotFound("activation_missing")

    def _completed(self, directory: int, identifier: str) -> ActivationRecord | None:
        if "activations" not in os.listdir(directory):
            return None
        with _private_directory(directory, "activations") as activations:
            if identifier not in os.listdir(activations):
                return None
            with _private_directory(activations, identifier) as evidence:
                if ACTIVATION_MANIFEST not in os.listdir(evidence):
                    return None
                value = _record(evidence, ACTIVATION_MANIFEST)
                if (
                    value.phase != "active"
                    or value.prepared.restore_id != identifier
                    or value.prepared.installation != self.installation
                ):
                    raise DatabaseRejected("invalid_activation_record")
                return value

    def _check_source(
        self, storage: OfflineStorage, prepared: PreparedRestoration, budget: _Budget
    ) -> None:
        if prepared.source is None or prepared.source.identity_sha256 is None:
            raise InvalidInput("managed_restore_binding_required")
        if prepared.source != storage.source:
            raise Conflict("restore_source_changed")
        with _connection(storage.database.path, budget, readonly=True) as connection:
            connection.execute("BEGIN")
            frontier = BoundFrontier(connection, storage.source, budget.check)
            for _ in frontier:
                pass
            if frontier.fingerprint() != prepared.source_frontier_sha256:
                raise Conflict("restore_source_changed")
        budget.check()

    def _sealed_input(
        self, storage: OfflineStorage, record: ActivationRecord, budget: _Budget
    ) -> Path:
        identifier = record.prepared.restore_id
        _child(storage.directory, "activations")
        with _private_directory(storage.directory, "activations") as activations:
            _child(activations, identifier)
            with _private_directory(activations, identifier) as evidence:
                _child(evidence, "input")
                with _private_directory(evidence, "input") as target:
                    path = self.root / "activations" / identifier / "input"
                    if set(os.listdir(target)) == _INPUT_FILES:
                        try:
                            if self._inspect_input(path) == record.prepared:
                                return path
                        except DomusError:
                            pass
                    if (
                        self.prepared_location is None
                        or self._inspect_input(self.prepared_location) != record.prepared
                    ):
                        raise DatabaseRejected("activation_input_required")
                    if set(os.listdir(target)) - _INPUT_FILES:
                        raise DatabaseRejected("invalid_activation_artifacts")
                    with _directory(self.prepared_location, private=True) as source:
                        for name in (
                            "installation.json",
                            "domus.sqlite3",
                            "operations.jsonl",
                            "restore.json",
                        ):
                            _copy(source, target, name, budget)
                    os.fsync(target)
                    os.fsync(evidence)
                    os.fsync(activations)
                    os.fsync(storage.directory)
        if self._inspect_input(path) != record.prepared:
            raise DatabaseRejected("activation_input_changed")
        return path

    def _verify_target(
        self, storage: OfflineStorage, record: ActivationRecord, budget: _Budget
    ) -> None:
        selection = GenerationSelection(self.installation, record.prepared.restore_id)
        path = _generation_database(self.root, storage.directory, selection)
        with _directory(path.parent, private=True) as slot:
            digest, size = _hash(slot, "domus.sqlite3", budget)
            if (digest, size) != (record.database_sha256, record.database_bytes):
                raise DatabaseRejected("activation_target_changed")
        database = SQLiteDatabase(path, self.installation)
        with _connection(path, budget, readonly=True) as connection:
            _verify_database(connection, database, previous=False)
        budget.check()

    def _materialize(
        self, storage: OfflineStorage, record: ActivationRecord, location: Path, budget: _Budget
    ) -> ActivationRecord:
        if record.phase == "materialized":
            self._verify_target(storage, record, budget)
            return record
        identifier = record.prepared.restore_id
        rollback = self._source_checkpoint(storage, record, budget)
        _child(storage.directory, "generations")
        with _private_directory(storage.directory, "generations") as generations:
            _child(generations, identifier)
            with _private_directory(generations, identifier) as slot:
                names = set(os.listdir(slot))
                if names - _SLOT_FILES:
                    raise DatabaseRejected("invalid_activation_artifacts")
                for name in names:
                    os.close(_file(slot, name))
                _write_identity(
                    slot,
                    self.installation,
                    "restore_pending",
                    create="installation.json" not in names,
                )
                for name in names - {"installation.json"}:
                    os.unlink(name, dir_fd=slot)
                with _directory(location, private=True) as input_dir:
                    _copy(input_dir, slot, "domus.sqlite3", budget)
                path = self.root / "generations" / identifier / "domus.sqlite3"
                database = SQLiteDatabase(path, self.installation)
                database.initialize(require_existing=True)
                with _connection(path, budget, readonly=False) as connection:
                    connection.execute("PRAGMA foreign_keys=ON")
                    connection.execute("BEGIN IMMEDIATE")
                    try:
                        with _directory(location, private=True) as input_dir:
                            SQLiteHistory(connection).install(_read_operations(input_dir, budget))
                        connection.execute("COMMIT")
                    except BaseException:
                        connection.execute("ROLLBACK")
                        raise
                with _connection(path, budget, readonly=True) as connection:
                    _verify_database(connection, database, previous=False)
                descriptor = _file(slot, "domus.sqlite3")
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
                digest, size = _hash(slot, "domus.sqlite3", budget)
                _atomic(
                    slot,
                    GENERATION_MARKER,
                    GenerationSelection(self.installation, identifier).document(),
                )
                _write_identity(slot, self.installation, "ready")
                os.fsync(slot)
                os.fsync(generations)
                os.fsync(storage.directory)
        result = replace(
            record,
            phase="materialized",
            database_sha256=digest,
            database_bytes=size,
            rollback_snapshot=rollback,
        )
        self._verify_target(storage, result, budget)
        _atomic(storage.directory, ACTIVATION_MANIFEST, result.document())
        return result

    def _source_checkpoint(
        self, storage: OfflineStorage, record: ActivationRecord, budget: _Budget
    ) -> Snapshot:
        identifier = record.prepared.restore_id
        path = self.root / "activations" / identifier / "source-checkpoint"
        with _private_directory(storage.directory, "activations") as activations:
            with _private_directory(activations, identifier) as evidence:
                _child(evidence, "source-checkpoint")
                with _private_directory(evidence, "source-checkpoint") as target:
                    names = set(os.listdir(target))
                    if "manifest.json" in names and GENERATION_MARKER not in names:
                        snapshot = SQLiteSnapshots(
                            None, path, self.installation, self.clock, timeout=self.timeout
                        ).inspect()
                        self._check_checkpoint_frontier(path, record, budget)
                        return snapshot
                    allowed = {
                        "domus.sqlite3",
                        "installation.json",
                        "manifest.json",
                        "manifest.json.next",
                        GENERATION_MARKER,
                        GENERATION_MARKER + ".next",
                        ".installation.next",
                    }
                    if names - allowed:
                        raise DatabaseRejected("invalid_activation_artifacts")
                    for name in names:
                        os.close(_file(target, name))
                    _atomic(
                        target,
                        GENERATION_MARKER,
                        GenerationSelection(self.installation, identifier).document(),
                    )
                    for name in names - {GENERATION_MARKER}:
                        os.unlink(name, dir_fd=target)
                    _write_identity(target, self.installation, "restore_pending", create=True)
                    descriptor = _file(
                        target, "domus.sqlite3", os.O_CREAT | os.O_EXCL | os.O_WRONLY
                    )
                    os.close(descriptor)
                    with _connection(storage.database.path, budget, readonly=True) as source:
                        source.execute("BEGIN")
                        with _connection(
                            path / "domus.sqlite3", budget, readonly=False
                        ) as outgoing:
                            _backup(source, outgoing, budget)
                    database = SQLiteDatabase(path / "domus.sqlite3", self.installation)
                    with _connection(database.path, budget, readonly=True) as source:
                        version = _verify_database(source, database, previous=True)
                        committed = last_committed_at(source)
                    _write_identity(target, self.installation, "ready")
                    descriptor = _file(target, "domus.sqlite3")
                    try:
                        os.fsync(descriptor)
                    finally:
                        os.close(descriptor)
                    digest, size = _hash(target, "domus.sqlite3", budget)
                    identity_hash, _ = _hash(target, "installation.json", budget)
                    snapshot = Snapshot(
                        identifier,
                        self.installation,
                        version,
                        self.clock.now(),
                        committed,
                        digest,
                        size,
                        identity_hash,
                    )
                    _atomic(target, "manifest.json", snapshot.document())
                    os.unlink(GENERATION_MARKER, dir_fd=target)
                    os.fsync(target)
                    os.fsync(evidence)
        self._check_checkpoint_frontier(path, record, budget)
        return SQLiteSnapshots(
            None, path, self.installation, self.clock, timeout=self.timeout
        ).inspect()

    def _check_checkpoint_frontier(
        self, path: Path, record: ActivationRecord, budget: _Budget
    ) -> None:
        with _connection(path / "domus.sqlite3", budget, readonly=True) as connection:
            frontier = BoundFrontier(
                connection, cast(RestoreSource, record.prepared.source), budget.check
            )
            for _ in frontier:
                pass
            if frontier.fingerprint() != record.prepared.source_frontier_sha256:
                raise DatabaseRejected("activation_rollback_changed")

    def _finish(
        self, storage: OfflineStorage, record: ActivationRecord, budget: _Budget
    ) -> ActivationStatus:
        self._verify_target(storage, record, budget)
        identifier = record.prepared.restore_id
        rollback_path = self.root / "activations" / identifier / "source-checkpoint"
        if (
            SQLiteSnapshots(
                None, rollback_path, self.installation, self.clock, timeout=self.timeout
            ).inspect()
            != record.rollback_snapshot
        ):
            raise DatabaseRejected("activation_rollback_changed")
        _, _, selected = _metadata(storage.directory)
        if selected != GenerationSelection(self.installation, identifier):
            raise DatabaseRejected("activation_selection_changed")
        completed = self._completed(storage.directory, identifier)
        if completed is not None:
            if replace(completed, phase="materialized", activated_at=None) != record:
                raise Conflict("activation_record_conflict")
        else:
            completed = replace(record, phase="active", activated_at=self.clock.now())
            with _private_directory(storage.directory, "activations") as activations:
                with _private_directory(activations, identifier) as evidence:
                    _atomic(evidence, ACTIVATION_MANIFEST, completed.document())
                os.fsync(activations)
        budget.check()
        os.unlink(ACTIVATION_MANIFEST, dir_fd=storage.directory)
        os.fsync(storage.directory)
        budget.check()
        return ActivationStatus(completed, identifier)

    def activate(self) -> ActivationStatus:
        budget = _Budget(self.monotonic() + self.timeout, self.monotonic)
        try:
            with offline_storage(
                self.root, self.installation.channel, timeout=self.timeout, monotonic=self.monotonic
            ) as storage:
                if storage.installation != self.installation:
                    raise DatabaseRejected("installation_mismatch")
                pending = self._pending(storage.directory)
                identifier = self._selected_id(pending)
                external = (
                    self._inspect_input(self.prepared_location)
                    if self.prepared_location is not None
                    else None
                )
                if external is not None and external.restore_id != identifier:
                    raise Conflict("activation_record_conflict")
                if pending is not None and (
                    pending.prepared.restore_id != identifier
                    or (external is not None and external != pending.prepared)
                ):
                    raise Conflict("activation_in_progress")
                if pending is None:
                    completed = self._completed(storage.directory, identifier)
                    if completed is not None:
                        if external is not None and completed.prepared != external:
                            raise Conflict("activation_record_conflict")
                        budget.check()
                        return ActivationStatus(completed, storage.source.generation_id)
                    if external is None:
                        raise NotFound("activation_missing")
                    self._check_source(storage, external, budget)
                    if "generations" in os.listdir(storage.directory):
                        with _private_directory(storage.directory, "generations") as generations:
                            if identifier in os.listdir(generations):
                                raise Conflict("activation_destination_exists")
                    if "activations" in os.listdir(storage.directory):
                        with _private_directory(storage.directory, "activations") as activations:
                            if identifier in os.listdir(activations):
                                raise Conflict("activation_destination_exists")
                    pending = ActivationRecord(external, "pending")
                    _atomic(storage.directory, ACTIVATION_MANIFEST, pending.document())
                elif ACTIVATION_MANIFEST not in os.listdir(storage.directory):
                    self._check_source(storage, pending.prepared, budget)
                    _atomic(storage.directory, ACTIVATION_MANIFEST, pending.document())
                if storage.source.generation_id == identifier:
                    if pending.phase != "materialized":
                        raise DatabaseRejected("invalid_activation_record")
                    return self._finish(storage, pending, budget)
                self._check_source(storage, pending.prepared, budget)
                location = self._sealed_input(storage, pending, budget)
                materialized = self._materialize(storage, pending, location, budget)
                budget.check()
                if _document(storage.directory, "installation.json") != storage.root_identity:
                    raise Conflict("restore_source_changed")
                _atomic(
                    storage.directory,
                    "installation.json",
                    GenerationSelection(self.installation, identifier).document(),
                    ".installation.next",
                )
                return self._finish(storage, materialized, budget)
        except OSError:
            raise StorageFailure("activation_uncertain") from None

    def resume(self) -> ActivationStatus:
        return self.activate()

    def inspect(self) -> ActivationStatus:
        try:
            return self._inspect()
        except OSError:
            raise StorageFailure("activation_inspection_failed") from None

    def _inspect(self) -> ActivationStatus:
        budget = _Budget(self.monotonic() + self.timeout, self.monotonic)
        # A pending transition blocks serving; completed records permit shared inspection.
        if any((self.root / name).exists() for name in (ACTIVATION_MANIFEST, ACTIVATION_NEXT)):
            with offline_storage(
                self.root, self.installation.channel, timeout=self.timeout, monotonic=self.monotonic
            ) as storage:
                if storage.installation != self.installation:
                    raise DatabaseRejected("installation_mismatch")
                pending = self._pending(storage.directory)
                identifier = self._selected_id(pending)
                if pending is not None and pending.prepared.restore_id == identifier:
                    budget.check()
                    return ActivationStatus(pending, storage.source.generation_id)
                completed = self._completed(storage.directory, identifier)
                if completed is None:
                    raise NotFound("activation_missing")
                budget.check()
                return ActivationStatus(completed, storage.source.generation_id)
        attached = attach_storage(self.root, self.installation.channel)
        try:
            if attached.installation != self.installation:
                raise DatabaseRejected("installation_mismatch")
            completed = self._completed(cast(int, attached._directory), self._selected_id(None))
            if completed is None:
                raise NotFound("activation_missing")
            budget.check()
            return ActivationStatus(completed, attached.generation_id)
        finally:
            attached.close()
