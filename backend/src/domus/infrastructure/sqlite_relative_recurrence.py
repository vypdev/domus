"""Relative records share rule identity and CAS while preserving current and absent originals."""

import sqlite3
from dataclasses import dataclass
from typing import cast

from domus.domain.errors import Conflict, DomusError, InvalidInput, StorageFailure
from domus.domain.recurrence_records import MAINTENANCE_ACTOR, ScheduleState
from domus.domain.relative_recurrence import RelativeProgress, RelativeSchedule, RelativeSlot
from domus.domain.storage import CommandKey, JsonDocument, validate_identifier
from domus.infrastructure.sqlite_receipts import SQLiteReceipts
from domus.infrastructure.sqlite_recurrence_rows import (
    SQLiteRecurrenceRows,
    _expected,
    _model,
    _page,
)
from domus.infrastructure.sqlite_relative_recurrence_records import (
    read_relative_progress,
    read_relative_schedule,
    read_relative_slot,
    relative_progress_document,
    relative_schedule_document,
    relative_slot_document,
)
from domus.infrastructure.sqlite_tasks import SQLiteTasks


def _rule_headers(value: RelativeSchedule) -> dict[str, object]:
    return {
        "schedule_id": value.schedule_id,
        "household_id": value.household_id,
        "definition_id": value.definition_id,
        "revision": value.revision,
        "pattern_revision": value.pattern_revision,
        "state": value.state.value,
        "timing_kind": "completion_relative",
    }


def _progress_headers(value: RelativeProgress) -> dict[str, object]:
    return {
        "schedule_id": value.schedule_id,
        "household_id": value.household_id,
        "revision": value.revision,
        "pattern_revision": value.pattern_revision,
        "timing_kind": "completion_relative",
    }


def _proof_headers(value: RelativeProgress) -> dict[str, object]:
    assert value.evidence is not None
    return {
        "schedule_id": value.schedule_id,
        "household_id": value.household_id,
        "progress_revision": value.revision,
        "operation_id": value.evidence.operation_id,
        "evidence_fingerprint": relative_progress_document(value).fingerprint,
    }


def _slot_headers(value: RelativeSlot) -> dict[str, object]:
    source = value.source
    return {
        "household_id": value.schedule.household_id,
        "slot_key": value.key,
        "schedule_id": value.schedule.schedule_id,
        "definition_id": value.schedule.definition_id,
        "pattern_revision": value.schedule.pattern_revision,
        "occurrence_id": value.occurrence_id,
        "source_occurrence_id": None if source is None else source.cycle.occurrence_id,
        "source_cycle_id": None if source is None else source.cycle.cycle_id,
        "created_at": value.created_at,
        "receipt_actor": value.command.actor_id,
        "receipt_action": value.command.action,
        "timing_kind": "completion_relative",
    }


@dataclass
class SQLiteRelativeRecurrences(SQLiteRecurrenceRows):
    def relative_schedule(self, household_id: str, schedule_id: str) -> RelativeSchedule | None:
        validate_identifier(household_id)
        validate_identifier(schedule_id)
        return _model(
            self.connection.execute(
                "SELECT * FROM recurrence_rules WHERE household_id=? AND schedule_id=? "
                "AND timing_kind='completion_relative'",
                (household_id, schedule_id),
            ).fetchone(),
            read_relative_schedule,
            _rule_headers,
        )

    def save_relative_schedule(self, value: RelativeSchedule, expected_revision: int) -> None:
        _expected(expected_revision)
        if value.revision != expected_revision + 1:
            raise Conflict("revision_conflict")
        previous = self.relative_schedule(value.household_id, value.schedule_id)
        if previous is not None and (
            value.definition_id != previous.definition_id
            or value.created_at != previous.created_at
            or value.pattern_revision
            != previous.pattern_revision + int(not previous.same_timing(value))
        ):
            raise Conflict("recurrence_identity_conflict")
        self._write(
            "recurrence_rules",
            _rule_headers(value),
            relative_schedule_document(value).encoded,
            expected_revision,
        )

    def _relative_work(self, value: RelativeSlot) -> bool:
        tasks = SQLiteTasks(self.connection)
        work = tasks.occurrence(value.schedule.household_id, value.occurrence_id)
        if (
            work is None
            or work.definition_snapshot.definition_id != value.schedule.definition_id
            or work.created_at != value.created_at
        ):
            return False
        if value.source is None:
            return True
        source = value.source
        parent = tasks.occurrence(value.schedule.household_id, source.cycle.occurrence_id)
        cycle = tasks.cycle(value.schedule.household_id, source.cycle.cycle_id)
        return (
            parent is not None
            and parent.definition_snapshot.definition_id == value.schedule.definition_id
            and cycle is not None
            and cycle.completion_snapshot() == source.cycle
        )

    def _relative_slot(self, row: sqlite3.Row | None) -> RelativeSlot | None:
        value = _model(row, read_relative_slot, _slot_headers)
        if value is None:
            return None
        current = self.relative_schedule(value.schedule.household_id, value.schedule.schedule_id)
        try:
            valid = (
                value.installation == self.installation
                and current is not None
                and value.consistent_with(current)
                and self._relative_work(value)
                and value.matches_receipt(SQLiteReceipts(self.connection).get(value.command))
            )
        except DomusError:
            valid = False
        if not valid:
            raise StorageFailure("invalid_recurrence_record")
        return value

    def relative_slot(self, household_id: str, slot_key: str) -> RelativeSlot | None:
        validate_identifier(household_id)
        validate_identifier(slot_key)
        return self._relative_slot(
            self.connection.execute(
                "SELECT * FROM recurrence_relative_slots WHERE household_id=? AND slot_key=?",
                (household_id, slot_key),
            ).fetchone()
        )

    def add_relative_slot(self, value: RelativeSlot) -> None:
        if value.installation != self.installation:
            raise Conflict("recurrence_scope_mismatch")
        current = self.relative_schedule(value.schedule.household_id, value.schedule.schedule_id)
        if (
            current is None
            or value.schedule.pattern_revision != current.pattern_revision
            or not value.consistent_with(current)
            or not self._relative_work(value)
        ):
            raise Conflict("recurrence_source_conflict")
        fields = {**_slot_headers(value), "document": relative_slot_document(value).encoded}
        try:
            self.connection.execute(
                f"INSERT INTO recurrence_relative_slots({','.join(fields)}) "
                f"VALUES ({','.join('?' for _ in fields)})",
                tuple(fields.values()),
            )
        except sqlite3.IntegrityError:
            raise Conflict("recurrence_slot_conflict") from None

    def _relative_continuation(self, value: RelativeProgress, rule: RelativeSchedule) -> bool:
        if not value.matches_schedule(rule):
            return False
        evidence = value.evidence
        receipt = (
            None if evidence is None else SQLiteReceipts(self.connection).get(evidence.command)
        )
        if not value.matches_receipt(receipt):
            return False
        if value.current_occurrence_id is None:
            return True
        key = cast(str, value.current_slot_key)
        saved = self.relative_slot(value.household_id, key)
        if saved is not None:
            return (
                saved.occurrence_id == value.current_occurrence_id
                and saved.schedule.schedule_id == rule.schedule_id
            )
        original = SQLiteReceipts(self.connection).get(
            CommandKey(value.household_id, MAINTENANCE_ACTOR, "recurrence.materialize", key)
        )
        # An adopted task may predate the restored-away mapping. Its presence cannot
        # authorize recreating that already processed mapping or erase the manual work.
        work = SQLiteTasks(self.connection).occurrence(
            value.household_id, value.current_occurrence_id
        )
        return (
            original is not None
            and original.historical
            and (work is None or work.definition_snapshot.definition_id == rule.definition_id)
            and JsonDocument.from_value(
                {
                    name: original.result.decode().get(name)
                    for name in ("slot_key", "occurrence_id", "schedule_id", "definition_id")
                }
            )
            == JsonDocument.from_value(
                {
                    "slot_key": key,
                    "occurrence_id": value.current_occurrence_id,
                    "schedule_id": rule.schedule_id,
                    "definition_id": rule.definition_id,
                }
            )
        )

    def relative_progress(self, household_id: str, schedule_id: str) -> RelativeProgress | None:
        validate_identifier(household_id)
        validate_identifier(schedule_id)
        value = _model(
            self.connection.execute(
                "SELECT * FROM recurrence_progress WHERE household_id=? AND schedule_id=? "
                "AND timing_kind='completion_relative'",
                (household_id, schedule_id),
            ).fetchone(),
            read_relative_progress,
            _progress_headers,
        )
        if value is None:
            return None
        rule = self.relative_schedule(household_id, schedule_id)
        row = self.connection.execute(
            "SELECT * FROM recurrence_progress_evidence WHERE household_id=? AND schedule_id=?",
            (household_id, schedule_id),
        ).fetchone()
        headers_match = (
            row is None
            if value.evidence is None
            else row is not None
            and all(
                type(row[key]) is type(expected) and row[key] == expected
                for key, expected in _proof_headers(value).items()
            )
        )
        try:
            valid = rule is not None and headers_match and self._relative_continuation(value, rule)
        except DomusError:
            valid = False
        if not valid:
            raise StorageFailure("invalid_recurrence_record")
        return value

    def save_relative_progress(self, value: RelativeProgress, expected_revision: int) -> None:
        _expected(expected_revision)
        if value.revision != expected_revision + 1:
            raise Conflict("revision_conflict")
        rule = self.relative_schedule(value.household_id, value.schedule_id)
        try:
            valid = rule is not None and self._relative_continuation(value, rule)
        except DomusError:
            raise StorageFailure("invalid_recurrence_record") from None
        if not valid:
            raise Conflict("relative_progress_mismatch")
        self._write(
            "recurrence_progress",
            _progress_headers(value),
            relative_progress_document(value).encoded,
            expected_revision,
        )
        if value.evidence is None:
            self.connection.execute(
                "DELETE FROM recurrence_progress_evidence WHERE household_id=? AND schedule_id=?",
                (value.household_id, value.schedule_id),
            )
        else:
            headers = _proof_headers(value)
            self.connection.execute(
                f"INSERT INTO recurrence_progress_evidence({','.join(headers)}) "
                f"VALUES ({','.join('?' for _ in headers)}) "
                "ON CONFLICT(household_id,schedule_id) DO UPDATE SET "
                "progress_revision=excluded.progress_revision, operation_id=excluded.operation_id, "
                "evidence_fingerprint=excluded.evidence_fingerprint",
                tuple(headers.values()),
            )

    def relative_schedules(
        self,
        household_id: str,
        *,
        limit: int = 25,
        after: str | None = None,
        state: ScheduleState | None = None,
    ) -> tuple[RelativeSchedule, ...]:
        where, parameters = _page(household_id, limit, after, "schedule_id")
        where.append("timing_kind='completion_relative'")
        if state is not None:
            if not isinstance(state, ScheduleState):
                raise InvalidInput("invalid_recurrence_state")
            where.append("state=?")
            parameters.append(state.value)
        return tuple(
            cast(RelativeSchedule, _model(row, read_relative_schedule, _rule_headers))
            for row in self.connection.execute(
                "SELECT * FROM recurrence_rules WHERE "
                + " AND ".join(where)
                + " ORDER BY schedule_id LIMIT ?",
                (*parameters, limit),
            )
        )

    def relative_slots(
        self, household_id: str, schedule_id: str, *, limit: int = 25, after: str | None = None
    ) -> tuple[RelativeSlot, ...]:
        where, parameters = _page(household_id, limit, after, "slot_key")
        validate_identifier(schedule_id)
        where.append("schedule_id=?")
        parameters.append(schedule_id)
        return tuple(
            cast(RelativeSlot, self._relative_slot(row))
            for row in self.connection.execute(
                "SELECT * FROM recurrence_relative_slots WHERE "
                + " AND ".join(where)
                + " ORDER BY slot_key LIMIT ?",
                (*parameters, limit),
            )
        )
