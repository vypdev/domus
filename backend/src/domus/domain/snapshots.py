"""Immutable snapshot metadata identifies one checkpoint without local paths or credentials."""

import re
from dataclasses import dataclass

from domus.domain.errors import InvalidInput
from domus.domain.storage import Installation, JsonDocument, validate_identifier


def _timestamp(value: int) -> None:
    if type(value) is not int or not 0 <= value <= 2**63 - 1:
        raise InvalidInput("invalid_snapshot_timestamp")


@dataclass(frozen=True, slots=True)
class Snapshot:
    snapshot_id: str
    installation: Installation
    schema_version: int
    captured_at: int
    last_committed_at: int | None
    database_sha256: str
    database_bytes: int
    identity_sha256: str
    format_version: int = 1

    def __post_init__(self) -> None:
        validate_identifier(self.snapshot_id)
        _timestamp(self.captured_at)
        if self.last_committed_at is not None:
            _timestamp(self.last_committed_at)
        if (
            not isinstance(self.installation, Installation)
            or type(self.format_version) is not int
            or self.format_version != 1
            or type(self.schema_version) is not int
            or not 1 <= self.schema_version <= 2**31 - 1
            or type(self.database_bytes) is not int
            or not 1 <= self.database_bytes <= 2**63 - 1
        ):
            raise InvalidInput("invalid_snapshot")
        for digest in (self.database_sha256, self.identity_sha256):
            if type(digest) is not str or not re.fullmatch(r"[a-f0-9]{64}", digest):
                raise InvalidInput("invalid_snapshot_digest")

    def document(self) -> JsonDocument:
        return JsonDocument.from_value(
            {
                "format_version": self.format_version,
                "snapshot_id": self.snapshot_id,
                "instance_id": self.installation.instance_id,
                "channel": self.installation.channel,
                "schema_version": self.schema_version,
                "captured_at": self.captured_at,
                "last_committed_at": self.last_committed_at,
                "database_sha256": self.database_sha256,
                "database_bytes": self.database_bytes,
                "identity_sha256": self.identity_sha256,
            }
        )
