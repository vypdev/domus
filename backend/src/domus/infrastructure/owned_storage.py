"""Own one private data directory, a stable installation identity and its process lease."""

import fcntl
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast
from uuid import uuid4

from domus.domain.errors import DatabaseRejected, InvalidInput, StorageBusy, StorageFailure
from domus.domain.storage import Installation, JsonDocument
from domus.infrastructure.sqlite import SQLiteDatabase

_MARKER = "installation.json"
_NEXT = ".installation.next"
_DATABASE = "domus.sqlite3"
_LOCK = "runtime.lock"
_ALLOWED = {
    _MARKER,
    _NEXT,
    _DATABASE,
    _LOCK,
    *(_DATABASE + suffix for suffix in ("-journal", "-wal", "-shm")),
}


@dataclass
class OwnedStorage:
    installation: Installation
    database: SQLiteDatabase
    _directory: int | None = field(repr=False)
    _lock: int | None = field(repr=False)

    def close(self) -> None:
        descriptors = self._lock, self._directory
        self._lock = self._directory = None
        for descriptor in descriptors:
            if descriptor is not None:
                os.close(descriptor)


def _file(directory: int, name: str, flags: int = os.O_RDONLY) -> int:
    descriptor = os.open(
        name, flags | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, 0o600, dir_fd=directory
    )
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o600
        ):
            raise DatabaseRejected("unsafe_installation_file")
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def _identity(directory: int) -> tuple[Installation, str]:
    descriptor = _file(directory, _MARKER)
    try:
        content = os.read(descriptor, 1025)
    finally:
        os.close(descriptor)
    try:
        if len(content) > 1024:
            raise InvalidInput("invalid_document")
        value = JsonDocument(content.decode("utf-8")).decode()
        if (
            set(value) != {"schema_version", "instance_id", "channel", "state"}
            or type(value["schema_version"]) is not int
            or value["schema_version"] != 1
            or value["state"] not in ("initializing", "ready")
        ):
            raise InvalidInput("invalid_document")
        installation = Installation(cast(str, value["instance_id"]), cast(str, value["channel"]))
        return installation, value["state"]
    except InvalidInput, UnicodeError:
        raise DatabaseRejected("invalid_installation_identity") from None


def _write_identity(
    directory: int, installation: Installation, state: str, *, create: bool = False
) -> None:
    name = _MARKER if create else _NEXT
    if not create and _NEXT in os.listdir(directory):
        os.unlink(_NEXT, dir_fd=directory)
    descriptor = _file(directory, name, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    with os.fdopen(descriptor, "w", encoding="utf-8") as target:
        target.write(
            JsonDocument.from_value(
                {
                    "schema_version": 1,
                    "instance_id": installation.instance_id,
                    "channel": installation.channel,
                    "state": state,
                }
            ).encoded
        )
        target.flush()
        os.fsync(target.fileno())
    if not create:
        os.replace(_NEXT, _MARKER, src_dir_fd=directory, dst_dir_fd=directory)
    os.fsync(directory)


def _open(root: Path, channel: str) -> OwnedStorage:
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    lock = None
    try:
        info = os.fstat(directory)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise DatabaseRejected("unsafe_installation_directory")
        lock = _file(directory, _LOCK, os.O_RDWR | os.O_CREAT)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise StorageBusy("installation_in_use") from None
        names = set(os.listdir(directory))
        if names - _ALLOWED:
            raise DatabaseRejected("unexpected_installation_artifact")
        for name in names - {_LOCK}:
            os.close(_file(directory, name))
        if _MARKER not in names:
            if names - {_LOCK}:
                raise DatabaseRejected("missing_installation_identity")
            installation, state = Installation(str(uuid4()), channel), "initializing"
            _write_identity(directory, installation, state, create=True)
        else:
            installation, state = _identity(directory)
        if installation.channel != channel:
            raise DatabaseRejected("installation_channel_mismatch")
        ready = state == "ready"
        if ready and _DATABASE not in names:
            raise DatabaseRejected("missing_installation_database")
        database = SQLiteDatabase(root / _DATABASE, installation)
        database.initialize(require_existing=ready)
        if not ready:
            _write_identity(directory, installation, "ready")
        elif _NEXT in names:
            os.unlink(_NEXT, dir_fd=directory)
            os.fsync(directory)
        return OwnedStorage(installation, database, directory, lock)
    except BaseException:
        if lock is not None:
            os.close(lock)
        os.close(directory)
        raise


def open_storage(root: Path, channel: str) -> OwnedStorage:
    """Open a trusted operator-owned existing 0700 directory, holding its lock until close.

    No listener may start until this succeeds. A ready marker never permits an empty or
    missing database; interrupted first initialization resumes only its persisted UUID.
    The private directory is an operator trust boundary, not protection from its owner.
    """
    if channel not in ("stable", "edge"):
        raise InvalidInput("invalid_installation_channel")
    try:
        return _open(root, channel)
    except OSError:
        raise StorageFailure("storage_failure") from None
