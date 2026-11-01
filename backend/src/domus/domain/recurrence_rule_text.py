"""Bounded closed RRULE input is validated before any permissive library interpretation."""

import re
from datetime import UTC, date, datetime

from domus.domain.errors import InvalidInput
from domus.domain.recurrence_rules import (
    ByDay,
    FixedPattern,
    Frequency,
    NominalDate,
    NominalSlot,
    Weekday,
)

_ALLOWED = frozenset(
    ("FREQ", "INTERVAL", "WKST", "BYDAY", "BYMONTH", "BYMONTHDAY", "BYSETPOS", "COUNT", "UNTIL")
)


def _integer(value: str, *, signed: bool = False) -> int:
    if re.fullmatch(r"[+-]?[0-9]{1,6}" if signed else r"[0-9]{1,6}", value) is None:
        raise InvalidInput("invalid_recurrence_rule")
    return int(value)


def _parts(text: str) -> dict[str, str]:
    if not isinstance(text, str) or not 1 <= len(text) <= 2048:
        raise InvalidInput("invalid_recurrence_rule")
    text = text.removeprefix("RRULE:")
    if re.fullmatch(r"[A-Z0-9=,;+\-]+", text) is None:
        raise InvalidInput("invalid_recurrence_rule")
    values = {}
    for part in text.split(";"):
        pair = part.split("=")
        if len(pair) != 2 or pair[0] not in _ALLOWED or pair[0] in values or not pair[1]:
            raise InvalidInput("invalid_recurrence_rule")
        values[pair[0]] = pair[1]
    if "FREQ" not in values:
        raise InvalidInput("invalid_recurrence_rule")
    return values


def _by_day(text: str) -> tuple[ByDay, ...]:
    values = []
    for part in text.split(","):
        match = re.fullmatch(r"([+-]?[1-5])?(MO|TU|WE|TH|FR|SA|SU)", part)
        if match is None:
            raise InvalidInput("invalid_recurrence_rule")
        values.append(ByDay(Weekday(match[2]), int(match[1]) if match[1] else None))
    return tuple(values)


def _until(text: str) -> NominalDate | int:
    if re.fullmatch(r"[0-9]{8}", text):
        return NominalDate(date(int(text[:4]), int(text[4:6]), int(text[6:8])))
    if re.fullmatch(r"[0-9]{8}T[0-9]{6}Z", text) is None:
        raise InvalidInput("invalid_recurrence_rule")
    value = datetime(
        int(text[:4]),
        int(text[4:6]),
        int(text[6:8]),
        int(text[9:11]),
        int(text[11:13]),
        int(text[13:15]),
        tzinfo=UTC,
    )
    delta = value - datetime(1970, 1, 1, tzinfo=UTC)
    return delta.days * 86_400_000 + delta.seconds * 1000


def _numbers(values: dict[str, str], name: str) -> tuple[int, ...]:
    return (
        tuple(_integer(v, signed=True) for v in values[name].split(",")) if name in values else ()
    )


def parse_fixed_pattern(text: str, start: NominalSlot) -> FixedPattern:
    values = _parts(text)
    try:
        return FixedPattern(
            start,
            Frequency(values["FREQ"]),
            _integer(values.get("INTERVAL", "1")),
            Weekday(values.get("WKST", "MO")),
            _by_day(values["BYDAY"]) if "BYDAY" in values else (),
            _numbers(values, "BYMONTH"),
            _numbers(values, "BYMONTHDAY"),
            _numbers(values, "BYSETPOS"),
            count=_integer(values["COUNT"]) if "COUNT" in values else None,
            until=_until(values["UNTIL"]) if "UNTIL" in values else None,
        )
    except ValueError:
        raise InvalidInput("invalid_recurrence_rule") from None
