"""Durable activation facts distinguish a selected pointer from completed activation."""

import re
from dataclasses import dataclass
from typing import Literal, cast

from domus.domain.errors import InvalidInput
from domus.domain.restoration import PreparedRestoration
from domus.domain.snapshots import Snapshot
from domus.domain.storage import JsonDocument, validate_identifier


@dataclass(frozen=True, slots=True)
class ActivationRecord:
    prepared: PreparedRestoration
    phase: Literal["pending", "materialized", "active"]
    database_sha256: str | None = None
    database_bytes: int | None = None
    activated_at: int | None = None
    rollback_snapshot: Snapshot | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.prepared, PreparedRestoration)
            or self.prepared.source is None
            or self.prepared.source.identity_sha256 is None
            or self.phase not in ("pending", "materialized", "active")
        ):
            raise InvalidInput("invalid_activation_record")
        if self.phase == "pending":
            if any(
                value is not None
                for value in (
                    self.database_sha256,
                    self.database_bytes,
                    self.activated_at,
                    self.rollback_snapshot,
                )
            ):
                raise InvalidInput("invalid_activation_record")
        elif (
            type(self.database_sha256) is not str
            or not re.fullmatch(r"[a-f0-9]{64}", self.database_sha256)
            or type(self.database_bytes) is not int
            or not 1 <= self.database_bytes <= 2**63 - 1
            or not isinstance(self.rollback_snapshot, Snapshot)
            or self.rollback_snapshot.installation != self.prepared.installation
        ):
            raise InvalidInput("invalid_activation_record")
        if self.phase == "active":
            if type(self.activated_at) is not int or not 0 <= self.activated_at <= 2**63 - 1:
                raise InvalidInput("invalid_activation_record")
        elif self.activated_at is not None:
            raise InvalidInput("invalid_activation_record")

    def document(self) -> JsonDocument:
        return JsonDocument.from_value(
            {
                "format_version": 1,
                "prepared": self.prepared.document().decode(),
                "phase": self.phase,
                "database_sha256": self.database_sha256,
                "database_bytes": self.database_bytes,
                "activated_at": self.activated_at,
                "rollback_snapshot": self.rollback_snapshot.document().decode()
                if self.rollback_snapshot is not None
                else None,
            }
        )

    @classmethod
    def from_value(cls, value: object) -> ActivationRecord:
        if type(value) is not dict or set(value) != {
            "format_version",
            "prepared",
            "phase",
            "database_sha256",
            "database_bytes",
            "activated_at",
            "rollback_snapshot",
        }:
            raise InvalidInput("invalid_activation_record")
        data = cast(dict[str, object], value)
        if type(data["format_version"]) is not int or data["format_version"] != 1:
            raise InvalidInput("invalid_activation_record")
        return cls(
            PreparedRestoration.from_value(data["prepared"]),
            cast(Literal["pending", "materialized", "active"], data["phase"]),
            cast(str | None, data["database_sha256"]),
            cast(int | None, data["database_bytes"]),
            cast(int | None, data["activated_at"]),
            Snapshot.from_value(data["rollback_snapshot"])
            if data["rollback_snapshot"] is not None
            else None,
        )


@dataclass(frozen=True, slots=True)
class ActivationStatus:
    record: ActivationRecord
    selected_generation: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.record, ActivationRecord):
            raise InvalidInput("invalid_activation_status")
        if self.selected_generation is not None:
            validate_identifier(self.selected_generation)

    @property
    def state(self) -> Literal["pending", "active", "historical"]:
        if self.record.phase != "active":
            return "pending"
        return (
            "active"
            if self.selected_generation == self.record.prepared.restore_id
            else "historical"
        )

    def document(self) -> JsonDocument:
        return JsonDocument.from_value(
            {
                "state": self.state,
                "selected_generation": self.selected_generation,
                "activation": self.record.document().decode(),
            }
        )
