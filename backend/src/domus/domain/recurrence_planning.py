"""Immutable bounded planning progress; these records are not persisted execution proof."""

import hashlib
import json
import re
from dataclasses import asdict, dataclass

from domus.domain.errors import InvalidInput
from domus.domain.recurrence_rules import FixedPattern, NominalDate, NominalSlot
from domus.domain.recurrence_time import NominalTime, ResolvedTime, TimePolicy
from domus.domain.storage import CommandKey, JsonDocument, JsonObject, validate_identifier


def cursor_binding(pattern: FixedPattern, policy: TimePolicy) -> str:
    value = {"version": 1, "pattern": pattern.fingerprint, "policy": asdict(policy)}
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class FixedCursor:
    binding: str
    period_index: int = 0
    offset: int = 0
    nominal_count: int = 0
    closed: bool = False

    def __post_init__(self) -> None:
        if (
            not isinstance(self.binding, str)
            or re.fullmatch(r"[a-f0-9]{64}", self.binding) is None
            or type(self.period_index) is not int
            or not 0 <= self.period_index <= 2**63 - 1
            or type(self.offset) is not int
            or not 0 <= self.offset <= 366
            or type(self.nominal_count) is not int
            or not 0 <= self.nominal_count <= 2**63 - 1
            or type(self.closed) is not bool
        ):
            raise InvalidInput("invalid_recurrence_cursor")


@dataclass(frozen=True, slots=True)
class PlannedSlot:
    """Nominal/resolved facts shared by timing modes; rule membership is checked separately."""

    nominal: NominalSlot
    resolved: ResolvedTime | None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.nominal, NominalDate | NominalTime)
            or (isinstance(self.nominal, NominalDate) and self.resolved is not None)
            or (
                isinstance(self.nominal, NominalTime)
                and (
                    not isinstance(self.resolved, ResolvedTime)
                    or self.resolved.nominal != self.nominal
                )
            )
        ):
            raise InvalidInput("invalid_recurrence_slot")

    def value(self) -> JsonObject:
        resolved = self.resolved
        return {
            "nominal": {
                "kind": "date" if isinstance(self.nominal, NominalDate) else "time",
                "local": self.nominal.local.isoformat(),
            },
            "resolved": None
            if resolved is None
            else {
                "nominal": {"kind": "time", "local": resolved.nominal.local.isoformat()},
                "policy": {
                    "zone": resolved.policy.zone,
                    "data_identity": resolved.policy.data_identity,
                    "repeated_time": resolved.policy.repeated_time.value,
                    "revision": resolved.policy.revision,
                },
                "resolved_local": resolved.resolved_local.isoformat(),
                "offset_seconds": resolved.offset_seconds,
                "resolution": resolved.resolution.value,
                "zone_digest": resolved.zone_digest,
            },
        }


PlannedFixedSlot = PlannedSlot


@dataclass(frozen=True, slots=True)
class CursorTimeEvidence:
    cursor: FixedCursor
    policy: TimePolicy
    range_complete: bool
    last: PlannedSlot | None = None
    terminal: PlannedSlot | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.cursor, FixedCursor)
            or not isinstance(self.policy, TimePolicy)
            or type(self.range_complete) is not bool
            or (self.cursor.closed and not self.range_complete)
        ):
            raise InvalidInput("invalid_recurrence_cursor_evidence")
        for slot in (self.last, self.terminal):
            if slot is not None and (
                not isinstance(slot, PlannedSlot)
                or (slot.resolved is not None and slot.resolved.policy != self.policy)
            ):
                raise InvalidInput("invalid_recurrence_cursor_evidence")
        if (
            self.last is not None
            and self.terminal is not None
            and self.last.resolved is not None
            and self.terminal.resolved is not None
            and self.last.resolved.zone_digest != self.terminal.resolved.zone_digest
        ):
            raise InvalidInput("invalid_recurrence_cursor_evidence")

    def document(self) -> JsonDocument:
        return JsonDocument.from_value(
            {
                "version": 1,
                "cursor": asdict(self.cursor),
                "policy": {
                    "zone": self.policy.zone,
                    "data_identity": self.policy.data_identity,
                    "repeated_time": self.policy.repeated_time.value,
                    "revision": self.policy.revision,
                },
                "range_complete": self.range_complete,
                "last": None if self.last is None else self.last.value(),
                "terminal": None if self.terminal is None else self.terminal.value(),
            }
        )


@dataclass(frozen=True, slots=True)
class CursorEvidence:
    time: CursorTimeEvidence
    command: CommandKey
    operation_id: str

    def __post_init__(self) -> None:
        validate_identifier(self.operation_id)
        if not isinstance(self.time, CursorTimeEvidence) or not isinstance(
            self.command, CommandKey
        ):
            raise InvalidInput("invalid_recurrence_cursor_evidence")

    def document(self) -> JsonDocument:
        return JsonDocument.from_value(
            {
                "version": 1,
                "time": self.time.document().decode(),
                "command": asdict(self.command),
                "operation_id": self.operation_id,
            }
        )


@dataclass(frozen=True, slots=True)
class FixedBatch:
    slots: tuple[PlannedFixedSlot, ...]
    cursor: FixedCursor
    periods_scanned: int
    range_complete: bool
    terminal: PlannedSlot | None = None


@dataclass(frozen=True, slots=True)
class StartCheck:
    matches: bool
    first_permitted: NominalSlot | None
    search_complete: bool
    continuation: FixedCursor
