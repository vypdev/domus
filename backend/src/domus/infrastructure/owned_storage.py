"""Own one private data directory, a stable installation identity and its process lease."""

import fcntl
import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast
from uuid import uuid4

from domus.domain.errors import DatabaseRejected, InvalidInput, StorageBusy, StorageFailure
from domus.domain.generations import GenerationSelection
from domus.domain.storage import Installation, JsonDocument
from domus.infrastructure.sqlite import SQLiteDatabase

_MARKER = "installation.json"
_NEXT = ".installation.next"
_DATABASE = "domus.sqlite3"
_LOCK = "runtime.lock"
_MAINTENANCE = "maintenance.lock"
RESTORE_MANIFEST = "restore.json"
RESTORE_OPERATIONS = "operations.jsonl"
GENERATION_MARKER = "generation.json"
_GENERATIONS = "generations"
_ARCHIVES = "archives"
_ALLOWED = {
    _MARKER,
    _NEXT,
    _DATABASE,
    _LOCK,
    _MAINTENANCE,
    *(_DATABASE + suffix for suffix in ("-journal", "-wal", "-shm")),
}


@dataclass
class OwnedStorage:
    installation: Installation
    database: SQLiteDatabase
    _directory: int | None = field(repr=False)
    _lock: int | None = field(repr=False)
    _maintenance: int | None = field(default=None, repr=False)
    generation_id: str | None = None

    def close(self) -> None:
        descriptors = self._maintenance, self._lock, self._directory
        self._maintenance = self._lock = self._directory = None
        _close(*descriptors)


def _close(*descriptors: int | None) -> None:
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


def _document(directory: int, name: str) -> JsonDocument:
    descriptor = _file(directory, name)
    try:
        content = os.read(descriptor, 1025)
    finally:
        os.close(descriptor)
    try:
        if len(content) > 1024:
            raise InvalidInput("invalid_document")
        return JsonDocument(content.decode("utf-8"))
    except InvalidInput, UnicodeError:
        raise DatabaseRejected("invalid_installation_identity") from None


def _metadata(directory: int) -> tuple[Installation, str, GenerationSelection | None]:
    try:
        value = _document(directory, _MARKER).decode()
        if value.get("schema_version") == 2:
            selection = GenerationSelection.from_value(value)
            return selection.installation, "ready", selection
        if (
            set(value) != {"schema_version", "instance_id", "channel", "state"}
            or type(value["schema_version"]) is not int
            or value["schema_version"] != 1
            or value["state"] not in ("initializing", "ready")
        ):
            raise InvalidInput("invalid_document")
        installation = Installation(cast(str, value["instance_id"]), cast(str, value["channel"]))
        return installation, value["state"], None
    except InvalidInput:
        raise DatabaseRejected("invalid_installation_identity") from None


def _identity(directory: int) -> tuple[Installation, str]:
    installation, state, _ = _metadata(directory)
    return installation, state


@contextmanager
def _private_directory(parent: int, name: str) -> Iterator[int]:
    descriptor = os.open(
        name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent
    )
    try:
        info = os.fstat(descriptor)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise DatabaseRejected("unsafe_installation_directory")
        yield descriptor
    finally:
        os.close(descriptor)


def _generation_database(root: Path, directory: int, selection: GenerationSelection) -> Path:
    with _private_directory(directory, _GENERATIONS) as generations:
        with _private_directory(generations, selection.generation_id) as slot:
            names = set(os.listdir(slot))
            required = {_MARKER, _DATABASE, GENERATION_MARKER}
            allowed = required | {_DATABASE + suffix for suffix in ("-journal", "-wal", "-shm")}
            if not required <= names or names - allowed:
                raise DatabaseRejected("invalid_generation_artifacts")
            for name in names:
                os.close(_file(slot, name))
            installation, state, nested = _metadata(slot)
            if (
                installation != selection.installation
                or state != "ready"
                or nested is not None
                or _document(slot, GENERATION_MARKER) != selection.document()
            ):
                raise DatabaseRejected("invalid_generation_identity")
    return root / _GENERATIONS / selection.generation_id / _DATABASE


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


def _acquire(directory: int, name: str, mode: int) -> int:
    descriptor = _file(directory, name, os.O_RDWR | os.O_CREAT)
    try:
        fcntl.flock(descriptor, mode | fcntl.LOCK_NB)
        return descriptor
    except BaseException as error:
        os.close(descriptor)
        if isinstance(error, BlockingIOError):
            raise StorageBusy("installation_in_use") from None
        raise


def _open(root: Path, channel: str, *, attach: bool) -> OwnedStorage:
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    lock = maintenance = None
    try:
        info = os.fstat(directory)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise DatabaseRejected("unsafe_installation_directory")
        present = set(os.listdir(directory))
        if {RESTORE_MANIFEST, RESTORE_OPERATIONS, GENERATION_MARKER} & present:
            raise DatabaseRejected("restore_not_active")
        if _MARKER in present:
            _metadata(directory)
        if not attach:
            lock = _acquire(directory, _LOCK, fcntl.LOCK_EX)
        maintenance = _acquire(directory, _MAINTENANCE, fcntl.LOCK_SH if attach else fcntl.LOCK_EX)
        names = set(os.listdir(directory))
        metadata = _metadata(directory) if _MARKER in names else None
        selection = metadata[2] if metadata is not None else None
        subdirectories = {_GENERATIONS, _ARCHIVES} if selection is not None else set()
        if names - _ALLOWED - subdirectories:
            raise DatabaseRejected("unexpected_installation_artifact")
        for name in names:
            if name in subdirectories:
                with _private_directory(directory, name):
                    pass
            else:
                os.close(_file(directory, name))
        if _MARKER not in names:
            if attach or names - {_LOCK, _MAINTENANCE}:
                raise DatabaseRejected("missing_installation_identity")
            installation, state = Installation(str(uuid4()), channel), "initializing"
            _write_identity(directory, installation, state, create=True)
        else:
            installation, state, _ = cast(
                tuple[Installation, str, GenerationSelection | None], metadata
            )
        if installation.channel != channel:
            raise DatabaseRejected("installation_channel_mismatch")
        ready = state == "ready"
        if ready and selection is None and _DATABASE not in names:
            raise DatabaseRejected("missing_installation_database")
        path = (
            _generation_database(root, directory, selection)
            if selection is not None
            else root / _DATABASE
        )
        database = SQLiteDatabase(path, installation)
        if attach:
            if not ready:
                raise DatabaseRejected("installation_not_ready")
            with database.read():
                pass
        else:
            database.initialize(require_existing=ready)
            if not ready:
                _write_identity(directory, installation, "ready")
            elif _NEXT in names:
                os.unlink(_NEXT, dir_fd=directory)
                os.fsync(directory)
            fcntl.flock(maintenance, fcntl.LOCK_SH)
        return OwnedStorage(
            installation,
            database,
            directory,
            lock,
            maintenance,
            selection.generation_id if selection is not None else None,
        )
    except BaseException:
        _close(maintenance, lock, directory)
        raise


def open_storage(root: Path, channel: str) -> OwnedStorage:
    """Open a trusted operator-owned existing 0700 directory, holding its lock until close.

    No listener may start until this succeeds. A ready marker never permits an empty or
    missing database; interrupted first initialization resumes only its persisted UUID.
    The private directory is an operator trust boundary, not protection from its owner.
    """
    return _storage(root, channel, attach=False)


def attach_storage(root: Path, channel: str) -> OwnedStorage:
    """Attach an installation-console operation without migration or UUID/schema creation.

    A shared maintenance guard coexists with the one runtime while excluding startup
    migrations/offline maintenance. The actual approval still requires explicit console input.
    """
    return _storage(root, channel, attach=True)


def attach_database(path: Path, installation: Installation) -> SQLiteDatabase:
    """Inspect an explicit standalone file without creation/migration or protocol bypass."""
    try:
        directory = os.open(
            path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        )
        try:
            info = os.fstat(directory)
            if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o022:
                raise DatabaseRejected("unsafe_installation_directory")
            _no_owned_marker(directory)
            os.close(_file(directory, path.name))
            database = SQLiteDatabase(path, installation)
            with database.read():
                pass
            return database
        finally:
            os.close(directory)
    except OSError:
        raise StorageFailure("storage_failure") from None


def _no_owned_marker(directory: int) -> None:
    for name in (_MARKER, GENERATION_MARKER, RESTORE_MANIFEST, RESTORE_OPERATIONS):
        try:
            os.stat(name, dir_fd=directory, follow_symlinks=False)
        except FileNotFoundError:
            continue
        raise InvalidInput("owned_directory_required")


def reject_owned_database(path: Path) -> None:
    """Explicit runtime files cannot bypass owned-directory startup/lifecycle rules."""
    try:
        directory = os.open(
            path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        )
        try:
            _no_owned_marker(directory)
        finally:
            os.close(directory)
    except OSError:
        raise StorageFailure("storage_failure") from None


def _storage(root: Path, channel: str, *, attach: bool) -> OwnedStorage:
    if channel not in ("stable", "edge"):
        raise InvalidInput("invalid_installation_channel")
    try:
        return _open(root, channel, attach=attach)
    except OSError:
        raise StorageFailure("storage_failure") from None
