"""Exclusive offline capability validates existing managed data without initializing the source."""

import fcntl
import math
import os
import stat
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from domus.domain.errors import DatabaseRejected, InvalidInput, StorageFailure
from domus.domain.restoration import RestoreSource
from domus.domain.storage import Installation, JsonDocument
from domus.infrastructure.owned_storage import (
    _ALLOWED,
    ACTIVATION_MANIFEST,
    ACTIVATION_NEXT,
    GENERATION_MARKER,
    RESTORE_MANIFEST,
    RESTORE_OPERATIONS,
    SNAPSHOT_MANIFEST,
    _acquire,
    _close,
    _document,
    _file,
    _generation_database,
    _metadata,
    _private_directory,
)
from domus.infrastructure.restore_source import source_binding
from domus.infrastructure.sqlite import SQLiteDatabase
from domus.infrastructure.sqlite_snapshots import _Budget, _connection, _verify_database


@dataclass(frozen=True)
class OfflineStorage:
    installation: Installation
    database: SQLiteDatabase
    source: RestoreSource
    root_identity: JsonDocument
    directory: int = field(repr=False)


def _existing_root(directory: int, channel: str) -> None:
    info = os.fstat(directory)
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise DatabaseRejected("unsafe_installation_directory")
    names = set(os.listdir(directory))
    if {GENERATION_MARKER, RESTORE_MANIFEST, RESTORE_OPERATIONS, SNAPSHOT_MANIFEST} & names:
        raise DatabaseRejected("restore_not_active")
    installation, state, _ = _metadata(directory)
    if installation.channel != channel or state != "ready":
        raise DatabaseRejected("installation_not_ready")


@contextmanager
def offline_storage(
    root: Path,
    channel: str,
    *,
    timeout: float = 30,
    monotonic: Callable[[], float] = time.monotonic,
) -> Iterator[OfflineStorage]:
    if channel not in ("stable", "edge"):
        raise InvalidInput("invalid_installation_channel")
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 3600:
        raise InvalidInput("invalid_restore_timeout")
    directory = runtime = maintenance = None
    try:
        directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        _existing_root(directory, channel)
        runtime = _acquire(directory, "runtime.lock", fcntl.LOCK_EX)
        maintenance = _acquire(directory, "maintenance.lock", fcntl.LOCK_EX)
        _existing_root(directory, channel)
        installation, _, selection = _metadata(directory)
        names = set(os.listdir(directory))
        subdirectories = (
            {"generations", "archives", "activations"}
            if selection is not None or ACTIVATION_MANIFEST in names
            else set()
        )
        allowed = _ALLOWED | {ACTIVATION_MANIFEST, ACTIVATION_NEXT} | subdirectories
        if names - allowed:
            raise DatabaseRejected("unexpected_installation_artifact")
        for name in names:
            if name in subdirectories:
                with _private_directory(directory, name):
                    pass
            else:
                os.close(_file(directory, name))
        path = (
            _generation_database(root, directory, selection)
            if selection is not None
            else root / "domus.sqlite3"
        )
        if selection is None:
            os.close(_file(directory, "domus.sqlite3"))
        database = SQLiteDatabase(path, installation)
        budget = _Budget(monotonic() + timeout, monotonic)
        with _connection(path, budget, readonly=True) as connection:
            connection.execute("BEGIN")
            version = _verify_database(connection, database, previous=True)
        with _private_source(path.parent) as source_dir:
            source = source_binding(source_dir, installation, version)
        budget.check()
        capability = OfflineStorage(
            installation, database, source, _document(directory, "installation.json"), directory
        )
    except BaseException as error:
        _close(maintenance, runtime, directory)
        if isinstance(error, OSError):
            raise StorageFailure("storage_failure") from None
        raise
    try:
        yield capability
    finally:
        _close(maintenance, runtime, directory)


@contextmanager
def _private_source(path: Path) -> Iterator[int]:
    directory = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        yield directory
    finally:
        os.close(directory)
