"""Immutable identities, canonical payloads and durable household facts."""

import hashlib
import json
import math
import re
from dataclasses import dataclass
from typing import Self, cast
from uuid import UUID

from domus.domain.errors import InvalidInput

type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]
type JsonObject = dict[str, JsonValue]


def validate_identifier(value: str) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", value):
        raise InvalidInput("invalid_identifier")


def _json_value(value: object, depth: int = 0) -> None:
    if depth > 16:
        raise InvalidInput("invalid_document")
    if type(value) in (type(None), bool, int, str):
        return
    if type(value) is float and math.isfinite(value):
        return
    if type(value) is list:
        for item in value:
            _json_value(item, depth + 1)
        return
    if type(value) is dict:
        for key, item in value.items():
            if not isinstance(key, str):
                raise InvalidInput("invalid_document")
            _json_value(item, depth + 1)
        return
    raise InvalidInput("invalid_document")


def _unique_object(pairs: list[tuple[str, JsonValue]]) -> JsonObject:
    result: JsonObject = {}
    for key, value in pairs:
        if key in result:
            raise InvalidInput("invalid_document")
        result[key] = value
    return result


@dataclass(frozen=True, slots=True)
class JsonDocument:
    """A bounded canonical object whose decoded copies cannot mutate its digest."""

    encoded: str

    def __post_init__(self) -> None:
        try:
            if not isinstance(self.encoded, str) or len(self.encoded.encode("utf-8")) > 65_536:
                raise InvalidInput("invalid_document")
            value = json.loads(self.encoded, object_pairs_hook=_unique_object)
            if not isinstance(value, dict):
                raise InvalidInput("invalid_document")
            _json_value(value)
            encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            if len(encoded.encode("utf-8")) > 65_536:
                raise InvalidInput("invalid_document")
        except TypeError, ValueError, UnicodeError, RecursionError:
            raise InvalidInput("invalid_document") from None
        object.__setattr__(self, "encoded", encoded)

    @classmethod
    def from_value(cls, value: object) -> Self:
        _json_value(value)
        try:
            return cls(json.dumps(value, ensure_ascii=False))
        except TypeError, ValueError:
            raise InvalidInput("invalid_document") from None

    def decode(self) -> JsonObject:
        return cast(JsonObject, json.loads(self.encoded))

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(self.encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class Installation:
    """Database ownership is explicit and cannot cross Stable and Edge."""

    instance_id: str
    channel: str

    def __post_init__(self) -> None:
        try:
            identity = UUID(self.instance_id)
        except ValueError, TypeError, AttributeError:
            raise InvalidInput("invalid_installation") from None
        if (
            str(identity) != self.instance_id
            or not identity.int
            or self.channel not in ("stable", "edge")
        ):
            raise InvalidInput("invalid_installation")


@dataclass(frozen=True, slots=True)
class CommandKey:
    """Possession of a replay key never replaces current actor authorization."""

    household_id: str
    actor_id: str
    action: str
    key: str

    def __post_init__(self) -> None:
        for value in (self.household_id, self.actor_id, self.action, self.key):
            validate_identifier(value)


@dataclass(frozen=True, slots=True)
class Household:
    """The minimal durable household record; timezone catalogs belong to ports."""

    household_id: str
    name: str
    time_zone: str
    revision: int

    def __post_init__(self) -> None:
        validate_identifier(self.household_id)
        if (
            not isinstance(self.name, str)
            or not isinstance(self.time_zone, str)
            or not self.name.strip()
            or len(self.name) > 160
            or any(ord(character) < 32 for character in self.name)
            or not self.time_zone
            or len(self.time_zone) > 128
            or any(ord(character) < 32 for character in self.time_zone)
            or type(self.revision) is not int
            or self.revision < 1
            or self.revision > 2**63 - 1
        ):
            raise InvalidInput("invalid_household")
        try:
            self.name.encode("utf-8")
            self.time_zone.encode("utf-8")
        except UnicodeError:
            raise InvalidInput("invalid_household") from None
        object.__setattr__(self, "name", self.name.strip())


@dataclass(frozen=True, slots=True)
class Receipt:
    """The original committed result, scoped independently of its public identifier."""

    command: CommandKey
    payload_fingerprint: str
    operation_id: str
    result: JsonDocument
    created_at: int


@dataclass(frozen=True, slots=True)
class AuditEntry:
    """An immutable business transition with its authenticated attribution."""

    operation_id: str
    command: CommandKey
    detail: JsonDocument
    created_at: int


@dataclass(frozen=True, slots=True)
class OutboxEvent:
    """A committed fact awaiting independent, duplicate-safe projection."""

    event_id: str
    household_id: str
    event_type: str
    payload: JsonDocument
    created_at: int
