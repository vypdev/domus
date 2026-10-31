"""Bind a coherent operation frontier to its managed identity and generation."""

import hashlib
import os
import sqlite3
from collections.abc import Callable, Iterator

from domus.domain.errors import DatabaseRejected
from domus.domain.generations import GenerationSelection
from domus.domain.restoration import RestoreSource, RetainedOperation
from domus.domain.storage import Installation
from domus.infrastructure.owned_storage import GENERATION_MARKER, _document, _metadata
from domus.infrastructure.sqlite_history import encode_operation, iter_operations


def source_binding(directory: int, installation: Installation, version: int) -> RestoreSource:
    names = set(os.listdir(directory))
    if "installation.json" not in names:
        if GENERATION_MARKER in names:
            raise DatabaseRejected("invalid_restore_source")
        return RestoreSource(installation, version, None, None)
    identity, state, nested = _metadata(directory)
    if identity != installation or state != "ready" or nested is not None:
        raise DatabaseRejected("invalid_restore_source")
    if GENERATION_MARKER in names:
        selection = GenerationSelection.from_value(_document(directory, GENERATION_MARKER).decode())
        if selection.installation != installation:
            raise DatabaseRejected("invalid_restore_source")
        return RestoreSource(
            installation, version, selection.generation_id, selection.document().fingerprint
        )
    return RestoreSource(
        installation, version, None, _document(directory, "installation.json").fingerprint
    )


class BoundFrontier:
    def __init__(
        self, connection: sqlite3.Connection, source: RestoreSource, check: Callable[[], None]
    ):
        self.connection, self.check = connection, check
        self.digest = hashlib.sha256(source.document().encoded.encode("utf-8"))

    def __iter__(self) -> Iterator[RetainedOperation]:
        for value in iter_operations(self.connection, self.check):
            self.digest.update((encode_operation(value) + "\n").encode("utf-8"))
            yield value

    def fingerprint(self) -> str:
        return self.digest.hexdigest()
