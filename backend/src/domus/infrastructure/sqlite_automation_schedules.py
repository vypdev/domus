"""Current schedule CAS, durable admissions and terminal outcomes share one connection."""

import sqlite3
from dataclasses import dataclass, replace

from domus.application.automation_scheduled_documents import (
    read_run,
    read_schedule,
    run_document,
    schedule_document,
)
from domus.domain.automation_scheduling import (
    DailyAutomationSchedule,
    ScheduledAutomationRun,
    ScheduledOutcome,
)
from domus.domain.errors import Conflict, InvalidInput, StorageFailure
from domus.domain.storage import Installation, validate_identifier


def _limit(value: int, maximum: int = 101) -> None:
    if type(value) is not int or not 1 <= value <= maximum:
        raise InvalidInput("invalid_page_size")


def _headers(row: sqlite3.Row, expected: dict[str, object]) -> None:
    if any(
        type(row[key]) is not type(value) or row[key] != value for key, value in expected.items()
    ):
        raise StorageFailure("invalid_daily_automation_record")


def _schedule_headers(value: DailyAutomationSchedule) -> dict[str, object]:
    return {
        "household_id": value.grant.household_id,
        "rule_id": value.grant.draft.rule_id,
        "revision": value.revision,
        "grant_id": value.grant.grant_id,
        "rule_revision": value.grant.draft.revision,
        "control_revision": value.control_revision,
        "next_at": value.next_time.instant_ms,
    }


def _run_headers(value: ScheduledAutomationRun) -> dict[str, object]:
    return {
        "household_id": value.grant.household_id,
        "trigger_key": value.key,
        "rule_id": value.grant.draft.rule_id,
        "rule_revision": value.grant.draft.revision,
        "grant_id": value.grant.grant_id,
        "outcome": value.outcome.value,
        "admitted_at": value.admitted_at,
    }


@dataclass
class SQLiteScheduledAutomations:
    connection: sqlite3.Connection
    installation: Installation

    def pending_count(
        self, household_id: str, *, rule_id: str | None = None, limit: int = 1000
    ) -> int:
        validate_identifier(household_id)
        _limit(limit, 1001)
        where = "" if rule_id is None else " AND rule_id=?"
        parameters = (household_id,) if rule_id is None else (household_id, rule_id)
        if rule_id is not None:
            validate_identifier(rule_id)
        row = self.connection.execute(
            "SELECT count(*) FROM (SELECT 1 FROM automation_scheduled_runs "
            "WHERE household_id=? AND outcome='queued'" + where + " LIMIT ?)",
            (*parameters, limit),
        ).fetchone()
        return int(row[0])

    def _schedule(self, row: sqlite3.Row) -> DailyAutomationSchedule:
        value = read_schedule(row["document"])
        _headers(row, _schedule_headers(value))
        if value.grant.installation != self.installation:
            raise StorageFailure("invalid_daily_automation_record")
        return value

    def _run(self, row: sqlite3.Row) -> ScheduledAutomationRun:
        value = read_run(row["document"])
        _headers(row, _run_headers(value))
        if value.grant.installation != self.installation:
            raise StorageFailure("invalid_daily_automation_record")
        return value

    def schedule(self, household_id: str, rule_id: str) -> DailyAutomationSchedule | None:
        validate_identifier(household_id)
        validate_identifier(rule_id)
        row = self.connection.execute(
            "SELECT * FROM automation_daily_schedules WHERE household_id=? AND rule_id=?",
            (household_id, rule_id),
        ).fetchone()
        return None if row is None else self._schedule(row)

    def save_schedule(self, value: DailyAutomationSchedule, expected_revision: int) -> None:
        if type(expected_revision) is not int or value.revision != expected_revision + 1:
            raise Conflict("revision_conflict")
        if value.grant.installation != self.installation:
            raise InvalidInput("invalid_daily_automation_scope")
        headers = _schedule_headers(value)
        values = (*headers.values(), schedule_document(value).encoded)
        if expected_revision == 0:
            changed = self.connection.execute(
                "INSERT INTO automation_daily_schedules VALUES(?,?,?,?,?,?,?,?) "
                "ON CONFLICT(household_id,rule_id) DO NOTHING",
                values,
            ).rowcount
        else:
            changed = self.connection.execute(
                "UPDATE automation_daily_schedules SET household_id=?,rule_id=?,revision=?,"
                "grant_id=?,rule_revision=?,control_revision=?,next_at=?,document=? "
                "WHERE household_id=? AND rule_id=? AND revision=?",
                (*values, value.grant.household_id, value.grant.draft.rule_id, expected_revision),
            ).rowcount
        if changed != 1:
            raise Conflict("revision_conflict")

    def schedules(
        self, household_id: str, *, after: str | None = None, limit: int = 100
    ) -> tuple[DailyAutomationSchedule, ...]:
        validate_identifier(household_id)
        _limit(limit)
        if after is not None:
            validate_identifier(after)
        return tuple(
            self._schedule(row)
            for row in self.connection.execute(
                "SELECT s.* FROM automation_daily_schedules s "
                "JOIN automation_rule_controls c ON c.household_id=s.household_id "
                "AND c.rule_id=s.rule_id AND c.enabled=1 AND c.rule_revision=s.rule_revision "
                "WHERE s.household_id=? AND s.rule_id>? ORDER BY s.rule_id LIMIT ?",
                (household_id, "" if after is None else after, limit),
            )
        )

    def run(self, household_id: str, trigger_key: str) -> ScheduledAutomationRun | None:
        validate_identifier(household_id)
        validate_identifier(trigger_key)
        row = self.connection.execute(
            "SELECT * FROM automation_scheduled_runs WHERE household_id=? AND trigger_key=?",
            (household_id, trigger_key),
        ).fetchone()
        return None if row is None else self._run(row)

    def admit(self, value: ScheduledAutomationRun) -> None:
        if (
            value.outcome is not ScheduledOutcome.QUEUED
            or value.grant.installation != self.installation
        ):
            raise InvalidInput("invalid_daily_automation_admission")
        values = (*_run_headers(value).values(), run_document(value).encoded)
        if (
            self.connection.execute(
                "INSERT INTO automation_scheduled_runs VALUES(?,?,?,?,?,?,?,?) "
                "ON CONFLICT(household_id,trigger_key) DO NOTHING",
                values,
            ).rowcount
            != 1
        ):
            raise Conflict("daily_automation_trigger_admitted")

    def finish(self, value: ScheduledAutomationRun) -> None:
        if value.outcome is ScheduledOutcome.QUEUED:
            raise InvalidInput("invalid_daily_automation_outcome")
        expected = replace(
            value,
            outcome=ScheduledOutcome.QUEUED,
            finished_at=None,
            task_operation_id=None,
            task_occurrence_id=None,
        )
        if (
            self.connection.execute(
                "UPDATE automation_scheduled_runs SET outcome=?,document=? "
                "WHERE household_id=? AND trigger_key=? AND outcome='queued' AND document=?",
                (
                    value.outcome.value,
                    run_document(value).encoded,
                    value.grant.household_id,
                    value.key,
                    run_document(expected).encoded,
                ),
            ).rowcount
            != 1
        ):
            raise Conflict("daily_automation_run_finished")

    def pending(
        self,
        household_id: str,
        *,
        rule_id: str | None = None,
        limit: int = 100,
        after: tuple[int, str] | None = None,
    ) -> tuple[ScheduledAutomationRun, ...]:
        validate_identifier(household_id)
        _limit(limit, 1001)
        if rule_id is not None:
            validate_identifier(rule_id)
        where = "" if rule_id is None else " AND rule_id=?"
        parameters = (household_id,) if rule_id is None else (household_id, rule_id)
        cursor: tuple[object, ...] = ()
        if after is not None:
            if type(after[0]) is not int or after[0] < 0:
                raise InvalidInput("invalid_daily_automation_cursor")
            validate_identifier(after[1])
            where += " AND (admitted_at,trigger_key)>(?,?)"
            cursor = after
        return tuple(
            self._run(row)
            for row in self.connection.execute(
                "SELECT * FROM automation_scheduled_runs WHERE household_id=? AND outcome='queued'"
                + where
                + " ORDER BY admitted_at,trigger_key LIMIT ?",
                (*parameters, *cursor, limit),
            )
        )

    def history(
        self,
        household_id: str,
        rule_id: str,
        *,
        before: tuple[int, str] | None = None,
        limit: int = 25,
    ) -> tuple[ScheduledAutomationRun, ...]:
        validate_identifier(household_id)
        validate_identifier(rule_id)
        _limit(limit)
        where = "" if before is None else " AND (admitted_at,trigger_key)<(?,?)"
        parameters: tuple[object, ...] = (household_id, rule_id)
        if before is not None:
            if type(before[0]) is not int or before[0] < 0:
                raise InvalidInput("invalid_daily_automation_cursor")
            validate_identifier(before[1])
            parameters += before
        return tuple(
            self._run(row)
            for row in self.connection.execute(
                "SELECT * FROM automation_scheduled_runs WHERE household_id=? AND rule_id=?"
                + where
                + " ORDER BY admitted_at DESC,trigger_key DESC LIMIT ?",
                (*parameters, limit),
            )
        )
