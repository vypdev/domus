"""Scoped recurrence repositories never commit independently or infer caller authority."""

import sqlite3
from dataclasses import dataclass
from typing import cast

from domus.domain.errors import Conflict, DomusError, InvalidInput, StorageFailure
from domus.domain.recurrence_frontier import RecurrenceFrontier
from domus.domain.recurrence_records import (
    FixedProgress,
    FixedSchedule,
    ScheduledSlot,
    ScheduleState,
)
from domus.domain.recurrence_rules import NominalDate
from domus.domain.storage import Installation, validate_identifier
from domus.infrastructure.sqlite_receipts import SQLiteReceipts
from domus.infrastructure.sqlite_recurrence_records import (
    frontier_document,
    progress_document,
    read_frontier,
    read_progress,
    read_schedule,
    read_slot,
    schedule_document,
    slot_document,
)
from domus.infrastructure.sqlite_recurrence_rows import (
    _expected,
    _model,
    _page,
)
from domus.infrastructure.sqlite_relative_recurrence import SQLiteRelativeRecurrences


def frontier_headers(value: RecurrenceFrontier) -> dict[str, object]:
    return {
        "household_id": value.household_id,
        "after_schedule_id": value.after_schedule_id,
        "selected_at": value.selected_at,
        "revision": value.revision,
    }


def schedule_headers(value: FixedSchedule) -> dict[str, object]:
    return {
        "schedule_id": value.schedule_id,
        "household_id": value.household_id,
        "definition_id": value.definition_id,
        "revision": value.revision,
        "pattern_revision": value.pattern_revision,
        "state": value.state.value,
        "timing_kind": "fixed_calendar",
    }


def progress_headers(value: FixedProgress) -> dict[str, object]:
    return {
        "schedule_id": value.schedule_id,
        "household_id": value.household_id,
        "pattern_revision": value.pattern_revision,
        "revision": value.revision,
        "timing_kind": "fixed_calendar",
    }


def _evidence_headers(value: FixedProgress) -> dict[str, object]:
    evidence = value.evidence
    assert evidence is not None
    return {
        "household_id": value.household_id,
        "schedule_id": value.schedule_id,
        "progress_revision": value.revision,
        "operation_id": evidence.operation_id,
        "evidence_fingerprint": evidence.document().fingerprint,
    }


def _original(connection: sqlite3.Connection, value: FixedProgress) -> bool:
    evidence = value.evidence
    if evidence is None:
        return value.pristine
    try:
        receipt = SQLiteReceipts(connection).get(evidence.command)
        return (
            receipt is not None
            and receipt.operation_id == evidence.operation_id
            and receipt.result.decode().get("schedule_id") == value.schedule_id
            and receipt.result.decode().get("cursor_evidence") == evidence.time.document().decode()
        )
    except DomusError:
        return False


def slot_headers(value: ScheduledSlot) -> dict[str, object]:
    return {
        "household_id": value.schedule.household_id,
        "slot_key": value.key,
        "schedule_id": value.schedule.schedule_id,
        "definition_id": value.schedule.definition_id,
        "pattern_revision": value.schedule.pattern_revision,
        "occurrence_id": value.occurrence_id,
        "nominal_kind": "date" if isinstance(value.planned.nominal, NominalDate) else "time",
        "nominal_value": value.planned.nominal.local.isoformat(),
        "resolved_at": None
        if value.planned.resolved is None
        else value.planned.resolved.instant_ms,
        "created_at": value.created_at,
        "receipt_actor": value.command.actor_id,
        "receipt_action": value.command.action,
        "timing_kind": "fixed_calendar",
    }


@dataclass
class SQLiteRecurrences(SQLiteRelativeRecurrences):
    connection: sqlite3.Connection
    installation: Installation

    def frontier(self, household_id: str) -> RecurrenceFrontier | None:
        validate_identifier(household_id)
        return _model(
            self.connection.execute(
                "SELECT * FROM recurrence_frontiers WHERE household_id=?", (household_id,)
            ).fetchone(),
            read_frontier,
            frontier_headers,
        )

    def save_frontier(self, value: RecurrenceFrontier, expected_revision: int) -> None:
        _expected(expected_revision)
        if value.revision != expected_revision + 1:
            raise Conflict("revision_conflict")
        self._write(
            "recurrence_frontiers",
            frontier_headers(value),
            frontier_document(value).encoded,
            expected_revision,
            identity="household_id",
        )

    def schedule(self, household_id: str, schedule_id: str) -> FixedSchedule | None:
        validate_identifier(household_id)
        validate_identifier(schedule_id)
        return _model(
            self.connection.execute(
                "SELECT * FROM recurrence_rules WHERE household_id=? AND schedule_id=? "
                "AND timing_kind='fixed_calendar'",
                (household_id, schedule_id),
            ).fetchone(),
            read_schedule,
            schedule_headers,
        )

    def progress(self, household_id: str, schedule_id: str) -> FixedProgress | None:
        validate_identifier(household_id)
        validate_identifier(schedule_id)
        value = _model(
            self.connection.execute(
                "SELECT * FROM recurrence_progress WHERE household_id=? AND schedule_id=? "
                "AND timing_kind='fixed_calendar'",
                (household_id, schedule_id),
            ).fetchone(),
            read_progress,
            progress_headers,
        )
        if value is not None:
            rule = self.schedule(household_id, schedule_id)
            row = self.connection.execute(
                "SELECT * FROM recurrence_progress_evidence WHERE household_id=? AND schedule_id=?",
                (household_id, schedule_id),
            ).fetchone()
            headers_match = (
                row is None
                if value.evidence is None
                else (
                    row is not None
                    and all(
                        type(row[key]) is type(expected) and row[key] == expected
                        for key, expected in _evidence_headers(value).items()
                    )
                )
            )
            if (
                rule is None
                or not value.matches_schedule(rule)
                or not headers_match
                or not _original(self.connection, value)
            ):
                raise StorageFailure("invalid_recurrence_record")
        return value

    def slot(self, household_id: str, slot_key: str) -> ScheduledSlot | None:
        validate_identifier(household_id)
        validate_identifier(slot_key)
        return self._slot(
            self.connection.execute(
                "SELECT * FROM recurrence_slots WHERE household_id=? AND slot_key=?",
                (household_id, slot_key),
            ).fetchone()
        )

    def _slot(self, row: sqlite3.Row | None) -> ScheduledSlot | None:
        value = _model(row, read_slot, slot_headers)
        if value is not None and value.installation != self.installation:
            raise StorageFailure("invalid_recurrence_record")
        if value is not None:
            try:
                valid = value.matches_receipt(SQLiteReceipts(self.connection).get(value.command))
            except DomusError:
                valid = False
            if not valid:
                raise StorageFailure("invalid_recurrence_record")
        return value

    def save_schedule(self, value: FixedSchedule, expected_revision: int) -> None:
        _expected(expected_revision)
        if value.revision != expected_revision + 1:
            raise Conflict("revision_conflict")
        previous = self.schedule(value.household_id, value.schedule_id)
        if previous is not None:
            changed = value.pattern != previous.pattern or value.policy != previous.policy
            if (
                value.definition_id != previous.definition_id
                or value.created_at != previous.created_at
                or value.pattern_revision != previous.pattern_revision + int(changed)
            ):
                raise Conflict("recurrence_identity_conflict")
        self._write(
            "recurrence_rules",
            schedule_headers(value),
            schedule_document(value).encoded,
            expected_revision,
        )

    def save_progress(self, value: FixedProgress, expected_revision: int) -> None:
        _expected(expected_revision)
        if value.revision != expected_revision + 1:
            raise Conflict("revision_conflict")
        rule = self.schedule(value.household_id, value.schedule_id)
        if (
            rule is None
            or not value.matches_schedule(rule)
            or not _original(self.connection, value)
        ):
            raise Conflict("recurrence_cursor_mismatch")
        self._write(
            "recurrence_progress",
            progress_headers(value),
            progress_document(value).encoded,
            expected_revision,
        )
        if value.evidence is None:
            self.connection.execute(
                "DELETE FROM recurrence_progress_evidence WHERE household_id=? AND schedule_id=?",
                (value.household_id, value.schedule_id),
            )
        else:
            headers = _evidence_headers(value)
            self.connection.execute(
                f"INSERT INTO recurrence_progress_evidence({','.join(headers)}) "
                f"VALUES ({','.join('?' for _ in headers)}) "
                "ON CONFLICT(household_id,schedule_id) DO UPDATE SET "
                "progress_revision=excluded.progress_revision, operation_id=excluded.operation_id, "
                "evidence_fingerprint=excluded.evidence_fingerprint",
                tuple(headers.values()),
            )

    def add_slot(self, value: ScheduledSlot) -> None:
        if value.installation != self.installation:
            raise Conflict("recurrence_scope_mismatch")
        current = self.schedule(value.schedule.household_id, value.schedule.schedule_id)
        if (
            current is None
            or value.schedule.pattern_revision != current.pattern_revision
            or not value.consistent_with(current)
        ):
            raise Conflict("recurrence_source_conflict")
        values = {**slot_headers(value), "document": slot_document(value).encoded}
        try:
            self.connection.execute(
                f"INSERT INTO recurrence_slots({','.join(values)}) "
                f"VALUES ({','.join('?' for _ in values)})",
                tuple(values.values()),
            )
        except sqlite3.IntegrityError:
            raise Conflict("recurrence_slot_conflict") from None

    def schedules(
        self,
        household_id: str,
        *,
        limit: int = 25,
        after: str | None = None,
        state: ScheduleState | None = None,
    ) -> tuple[FixedSchedule, ...]:
        where, parameters = _page(household_id, limit, after, "schedule_id")
        where.append("timing_kind='fixed_calendar'")
        if state is not None:
            if not isinstance(state, ScheduleState):
                raise InvalidInput("invalid_recurrence_state")
            where.append("state=?")
            parameters.append(state.value)
        rows = self.connection.execute(
            "SELECT * FROM recurrence_rules WHERE "
            + " AND ".join(where)
            + " ORDER BY schedule_id LIMIT ?",
            (*parameters, limit),
        )
        return tuple(
            cast(FixedSchedule, _model(row, read_schedule, schedule_headers)) for row in rows
        )

    def slots(
        self, household_id: str, schedule_id: str, *, limit: int = 25, after: str | None = None
    ) -> tuple[ScheduledSlot, ...]:
        where, parameters = _page(household_id, limit, after, "slot_key")
        validate_identifier(schedule_id)
        where.append("schedule_id=?")
        parameters.append(schedule_id)
        rows = self.connection.execute(
            "SELECT * FROM recurrence_slots WHERE "
            + " AND ".join(where)
            + " ORDER BY slot_key LIMIT ?",
            (*parameters, limit),
        )
        return tuple(cast(ScheduledSlot, self._slot(row)) for row in rows)
