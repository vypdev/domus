"""Shared bounded row/CAS mechanics; record kind remains part of every typed write."""

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass

from domus.domain.errors import Conflict, InvalidInput, StorageFailure
from domus.domain.storage import Installation, validate_identifier


def _model[T](
    row: sqlite3.Row | None, decode: Callable[[str], T], headers: Callable[[T], dict[str, object]]
) -> T | None:
    if row is None:
        return None
    value = decode(row["document"])
    if any(
        type(row[key]) is not type(expected) or row[key] != expected
        for key, expected in headers(value).items()
    ):
        raise StorageFailure("invalid_recurrence_record")
    return value


def _expected(value: int) -> None:
    if type(value) is not int or not 0 <= value <= 2**63 - 1:
        raise InvalidInput("invalid_revision")


def _page(
    household_id: str, limit: int, after: str | None, key: str
) -> tuple[list[str], list[object]]:
    validate_identifier(household_id)
    if type(limit) is not int or not 1 <= limit <= 101:
        raise InvalidInput("invalid_page_size")
    where, parameters = ["household_id=?"], [household_id]
    if after is not None:
        validate_identifier(after)
        where.append(key + ">?")
        parameters.append(after)
    return where, list(parameters)


@dataclass
class SQLiteRecurrenceRows:
    connection: sqlite3.Connection
    installation: Installation

    def _write(
        self,
        table: str,
        headers: dict[str, object],
        document: str,
        expected: int,
        *,
        identity: str = "schedule_id",
    ) -> None:
        values = {**headers, "document": document}
        keys: tuple[str, ...] = (
            ("household_id",) if identity == "household_id" else ("household_id", identity)
        )
        if "timing_kind" in headers:
            keys += ("timing_kind",)
        try:
            if expected == 0:
                self.connection.execute(
                    f"INSERT INTO {table}({','.join(values)}) "
                    f"VALUES ({','.join('?' for _ in values)})",
                    tuple(values.values()),
                )
            elif (
                self.connection.execute(
                    f"UPDATE {table} SET {','.join(key + '=?' for key in values)} "
                    f"WHERE {' AND '.join(key + '=?' for key in keys)} AND revision=?",
                    (*values.values(), *(headers[key] for key in keys), expected),
                ).rowcount
                != 1
            ):
                raise Conflict("revision_conflict")
        except sqlite3.IntegrityError:
            raise Conflict("recurrence_record_conflict") from None
