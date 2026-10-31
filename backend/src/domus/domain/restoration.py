"""Pure complete-operation evidence and streaming checkpoint/history reconciliation."""

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, replace
from typing import cast

from domus.domain.errors import Conflict, InvalidInput
from domus.domain.snapshots import Snapshot
from domus.domain.storage import (
    AuditEntry,
    CommandKey,
    Installation,
    JsonDocument,
    JsonObject,
    OutboxEvent,
    Receipt,
    validate_identifier,
)


@dataclass(frozen=True, slots=True)
class OperationEvidence:
    receipt: Receipt
    audit: AuditEntry
    event: OutboxEvent
    position: int
    delivered: bool

    def __post_init__(self) -> None:
        r, a, e = self.receipt, self.audit, self.event
        if (
            not isinstance(r, Receipt)
            or not isinstance(a, AuditEntry)
            or not isinstance(e, OutboxEvent)
            or not isinstance(r.command, CommandKey)
            or r.restoration is not None
            or type(self.position) is not int
            or not 1 <= self.position <= 2**63 - 1
            or type(self.delivered) is not bool
            or not isinstance(r.payload_fingerprint, str)
            or not re.fullmatch(r"[a-f0-9]{64}", r.payload_fingerprint)
            or type(r.created_at) is not int
            or not 0 <= r.created_at <= 2**63 - 1
            or type(a.created_at) is not int
            or type(e.created_at) is not int
            or a.operation_id != r.operation_id
            or e.event_id != r.operation_id
            or a.command != r.command
            or e.household_id != r.command.household_id
            or e.event_type != r.command.action
            or a.created_at != r.created_at
            or e.created_at != r.created_at
            or not isinstance(r.result, JsonDocument)
            or not isinstance(a.detail, JsonDocument)
            or not isinstance(e.payload, JsonDocument)
        ):
            raise InvalidInput("invalid_restore_evidence")
        validate_identifier(r.operation_id)

    @property
    def command_scope(self) -> tuple[str, str, str, str]:
        command = self.receipt.command
        return command.household_id, command.actor_id, command.action, command.key


@dataclass(frozen=True, slots=True)
class RetainedOperation:
    evidence: OperationEvidence
    current: bool
    archived_by: str | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.evidence, OperationEvidence)
            or type(self.current) is not bool
            or (not self.current and self.archived_by is None)
        ):
            raise InvalidInput("invalid_retained_operation")
        if self.archived_by is not None:
            validate_identifier(self.archived_by)

    def value(self) -> JsonObject:
        r, a, e = self.evidence.receipt, self.evidence.audit, self.evidence.event
        return {
            "household_id": r.command.household_id,
            "actor_id": r.command.actor_id,
            "action": r.command.action,
            "command_key": r.command.key,
            "payload_fingerprint": r.payload_fingerprint,
            "operation_id": r.operation_id,
            "result": r.result.decode(),
            "created_at": r.created_at,
            "audit_detail": a.detail.decode(),
            "event_payload": e.payload.decode(),
            "position": self.evidence.position,
            "delivered": self.evidence.delivered,
            "current": self.current,
            "archived_by": self.archived_by,
        }

    @classmethod
    def from_value(cls, value: object) -> RetainedOperation:
        fields = {
            "household_id",
            "actor_id",
            "action",
            "command_key",
            "payload_fingerprint",
            "operation_id",
            "result",
            "created_at",
            "audit_detail",
            "event_payload",
            "position",
            "delivered",
            "current",
            "archived_by",
        }
        if type(value) is not dict or set(value) != fields:
            raise InvalidInput("invalid_retained_operation")
        data = cast(dict[str, object], value)
        key = CommandKey(
            *(
                cast(str, data[name])
                for name in ("household_id", "actor_id", "action", "command_key")
            )
        )
        operation_id, timestamp = cast(str, data["operation_id"]), cast(int, data["created_at"])
        return cls(
            OperationEvidence(
                Receipt(
                    key,
                    cast(str, data["payload_fingerprint"]),
                    operation_id,
                    JsonDocument.from_value(data["result"]),
                    timestamp,
                ),
                AuditEntry(
                    operation_id, key, JsonDocument.from_value(data["audit_detail"]), timestamp
                ),
                OutboxEvent(
                    operation_id,
                    key.household_id,
                    key.action,
                    JsonDocument.from_value(data["event_payload"]),
                    timestamp,
                ),
                cast(int, data["position"]),
                cast(bool, data["delivered"]),
            ),
            cast(bool, data["current"]),
            cast(str | None, data["archived_by"]),
        )


def _ordered(values: Iterable[RetainedOperation]) -> Iterator[RetainedOperation]:
    previous: tuple[str, str, str, str] | None = None
    identities, positions = set[str](), set[int]()
    for value in values:
        if not isinstance(value, RetainedOperation):
            raise InvalidInput("invalid_retained_operation")
        scope, identifier = value.evidence.command_scope, value.evidence.receipt.operation_id
        if previous is not None and scope <= previous:
            raise InvalidInput("restore_evidence_order")
        if identifier in identities or value.evidence.position in positions:
            raise InvalidInput("restore_operation_collision")
        previous = scope
        identities.add(identifier)
        positions.add(value.evidence.position)
        yield value


def reconcile_operations(
    checkpoint: Iterable[RetainedOperation], current: Iterable[RetainedOperation], restore_id: str
) -> Iterator[RetainedOperation]:
    """Consume sorted complete frontiers; publish no result until this stream finishes.

    Only identity/position sets grow with history; payloads are processed one record at a time.
    A checkpoint is a complete prefix of retained operation positions, independent of wall clocks.
    Acknowledgements are monotonic knowledge, never a fabricated delivery of rolled-away work.
    """
    validate_identifier(restore_id)
    selected = iter(_ordered(checkpoint))
    expected = next(selected, None)
    checkpoint_highwater, first_extra = 0, None
    for source in _ordered(current):
        scope = source.evidence.command_scope
        if expected is not None and scope > expected.evidence.command_scope:
            raise Conflict("restore_checkpoint_unexplained")
        if expected is not None and scope == expected.evidence.command_scope:
            if replace(source.evidence, delivered=expected.evidence.delivered) != expected.evidence:
                raise Conflict("restore_evidence_conflict")
            if expected.evidence.delivered and not source.evidence.delivered:
                raise Conflict("restore_delivery_regressed")
            if expected.archived_by is not None and expected.archived_by != source.archived_by:
                raise Conflict("restore_history_conflict")
            checkpoint_highwater = max(checkpoint_highwater, expected.evidence.position)
            result = replace(
                source,
                current=expected.current,
                archived_by=source.archived_by or (None if expected.current else restore_id),
            )
            expected = next(selected, None)
        else:
            position = source.evidence.position
            first_extra = position if first_extra is None else min(first_extra, position)
            result = replace(source, current=False, archived_by=source.archived_by or restore_id)
        yield result
    if expected is not None:
        raise Conflict("restore_checkpoint_unexplained")
    if first_extra is not None and first_extra <= checkpoint_highwater:
        raise Conflict("restore_checkpoint_incomplete")


@dataclass(frozen=True, slots=True)
class PreparedRestoration:
    restore_id: str
    checkpoint: Snapshot
    source_frontier_sha256: str
    operations_sha256: str
    identity_sha256: str
    operation_count: int
    current_operations: int
    highwater: int
    prepared_at: int

    def __post_init__(self) -> None:
        validate_identifier(self.restore_id)
        if (
            not isinstance(self.checkpoint, Snapshot)
            or any(
                type(value) is not int or not 0 <= value <= 2**63 - 1
                for value in (
                    self.operation_count,
                    self.current_operations,
                    self.highwater,
                    self.prepared_at,
                )
            )
            or self.current_operations > self.operation_count
            or self.highwater < self.operation_count
            or (self.operation_count == 0) != (self.highwater == 0)
        ):
            raise InvalidInput("invalid_restore_preparation")
        for digest in (self.source_frontier_sha256, self.operations_sha256, self.identity_sha256):
            if type(digest) is not str or not re.fullmatch(r"[a-f0-9]{64}", digest):
                raise InvalidInput("invalid_restore_digest")

    @property
    def installation(self) -> Installation:
        return self.checkpoint.installation

    def document(self) -> JsonDocument:
        return JsonDocument.from_value(
            {
                "format_version": 1,
                "state": "prepared",
                "restore_id": self.restore_id,
                "checkpoint": self.checkpoint.document().decode(),
                "source_frontier_sha256": self.source_frontier_sha256,
                "operations_sha256": self.operations_sha256,
                "identity_sha256": self.identity_sha256,
                "operation_count": self.operation_count,
                "current_operations": self.current_operations,
                "highwater": self.highwater,
                "prepared_at": self.prepared_at,
            }
        )

    @classmethod
    def from_value(cls, value: object) -> PreparedRestoration:
        if type(value) is not dict:
            raise InvalidInput("invalid_restore_preparation")
        data = cast(dict[str, object], value)
        try:
            if type(data["format_version"]) is not int or data["format_version"] != 1:
                raise InvalidInput("invalid_restore_preparation")
            snapshot = data["checkpoint"]
            if type(snapshot) is not dict:
                raise InvalidInput("invalid_restore_preparation")
            item = cast(dict[str, object], snapshot)
            checkpoint = Snapshot(
                cast(str, item["snapshot_id"]),
                Installation(cast(str, item["instance_id"]), cast(str, item["channel"])),
                cast(int, item["schema_version"]),
                cast(int, item["captured_at"]),
                cast(int | None, item["last_committed_at"]),
                cast(str, item["database_sha256"]),
                cast(int, item["database_bytes"]),
                cast(str, item["identity_sha256"]),
                cast(int, item["format_version"]),
            )
            result = cls(
                cast(str, data["restore_id"]),
                checkpoint,
                cast(str, data["source_frontier_sha256"]),
                cast(str, data["operations_sha256"]),
                cast(str, data["identity_sha256"]),
                cast(int, data["operation_count"]),
                cast(int, data["current_operations"]),
                cast(int, data["highwater"]),
                cast(int, data["prepared_at"]),
            )
            if result.document().decode() != data:
                raise InvalidInput("invalid_restore_preparation")
            return result
        except KeyError:
            raise InvalidInput("invalid_restore_preparation") from None
