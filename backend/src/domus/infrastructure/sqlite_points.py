"""Append one receipt and optional exact ledger posting for each task event."""

import json
import sqlite3
from dataclasses import asdict, dataclass
from typing import Any, cast

from domus.domain.errors import InvalidInput, StorageFailure
from domus.domain.points import PointsPosting, conserve_points, points_source_fingerprint
from domus.domain.restoration import RetainedOperation
from domus.domain.storage import Installation, JsonDocument
from domus.domain.task_events import TaskLifecycleEvent
from domus.infrastructure.sqlite_task_history import (
    RESTORED_AWARD_CLOSURE,
    SQLiteTaskHistory,
    task_source_record,
)

POINTS_TABLE = "points_task_receipts"
POINTS_STATEMENTS = (
    "CREATE TABLE points_task_receipts(household_id TEXT NOT NULL REFERENCES households,"
    "event_id TEXT NOT NULL REFERENCES receipts(operation_id), position INTEGER NOT NULL "
    "REFERENCES outbox(position), cycle_id TEXT NOT NULL REFERENCES task_cycles, "
    "definition_id TEXT NOT NULL, fingerprint TEXT NOT NULL "
    "CHECK(length(fingerprint)=64 AND fingerprint NOT GLOB '*[^0-9a-f]*'), "
    "effect INTEGER NOT NULL CHECK(effect IN (0,1,2)), document TEXT, "
    "PRIMARY KEY(household_id,event_id), UNIQUE(household_id,position), "
    "CHECK((effect=0 AND document IS NULL) OR "
    "(effect>0 AND document IS NOT NULL AND json_valid(document))), "
    "FOREIGN KEY(household_id,definition_id) "
    "REFERENCES task_definitions(household_id,definition_id))",
    "CREATE UNIQUE INDEX points_one_effect_per_cycle "
    "ON points_task_receipts(household_id,cycle_id,effect) WHERE effect>0",
    "CREATE INDEX points_definition_rotation "
    "ON points_task_receipts(household_id,definition_id,position) WHERE effect=1",
    "CREATE INDEX points_restored_award_closure ON retained_operations("
    "household_id,json_extract(document,'$.event_payload.cycle.cycle_id'),position) "
    f"WHERE {RESTORED_AWARD_CLOSURE}",
)


def _posting(row: sqlite3.Row) -> PointsPosting:
    try:
        value: dict[str, Any] = JsonDocument(row["document"]).decode()
        value["shares"] = tuple(tuple(share) for share in value["shares"])
        posting = PointsPosting(**value)
        if (
            posting.event_id != row["event_id"]
            or posting.cycle_id != row["cycle_id"]
            or posting.definition_id != row["definition_id"]
            or (posting.reverses is not None) != (row["effect"] == 2)
        ):
            raise InvalidInput("invalid_points_posting")
        return posting
    except InvalidInput, KeyError, TypeError, ValueError:
        raise StorageFailure("invalid_points_posting") from None


@dataclass
class SQLitePoints:
    connection: sqlite3.Connection

    def position(self, household_id: str) -> int:
        return int(
            self.connection.execute(
                "SELECT COALESCE(MAX(position),0) FROM points_task_receipts WHERE household_id=?",
                (household_id,),
            ).fetchone()[0]
        )

    def processed(self, household_id: str, event_id: str) -> str | None:
        row = self.connection.execute(
            "SELECT fingerprint FROM points_task_receipts WHERE household_id=? AND event_id=?",
            (household_id, event_id),
        ).fetchone()
        return None if row is None else cast(str, row[0])

    def next_recipient(
        self, household_id: str, definition_id: str, *, before: int | None = None
    ) -> str | None:
        row = self.connection.execute(
            "SELECT * FROM points_task_receipts WHERE household_id=? AND definition_id=? "
            "AND effect=1 AND position<=? ORDER BY position DESC LIMIT 1",
            (household_id, definition_id, 2**63 - 1 if before is None else before - 1),
        ).fetchone()
        return None if row is None else _posting(row).next_recipient

    def ledger(self, household_id: str, cycle_id: str) -> tuple[PointsPosting, ...]:
        return tuple(
            _posting(row)
            for row in self.connection.execute(
                "SELECT * FROM points_task_receipts WHERE household_id=? AND cycle_id=? "
                "AND effect>0 ORDER BY effect LIMIT 2",
                (household_id, cycle_id),
            )
        )

    def add(
        self, event: TaskLifecycleEvent, fingerprint: str, posting: PointsPosting | None
    ) -> None:
        self.connection.execute(
            "INSERT INTO points_task_receipts VALUES (?,?,?,?,?,?,?,?)",
            (
                event.cycle.household_id,
                event.event_id,
                event.position,
                event.cycle.cycle_id,
                event.definition_id,
                fingerprint,
                0 if posting is None else 1 if posting.reverses is None else 2,
                None if posting is None else JsonDocument(json.dumps(asdict(posting))).encoded,
            ),
        )


def verify_points_records(connection: sqlite3.Connection, installation: Installation) -> None:
    history = SQLiteTaskHistory(connection)
    points = SQLitePoints(connection)
    previous = 0
    for row in connection.execute("SELECT * FROM points_task_receipts ORDER BY position"):
        scope, position = row["household_id"], row["position"]
        sources = history.lifecycle_events(scope, limit=1, after=previous)
        if not sources or sources[0].position != position:
            raise StorageFailure("invalid_points_source")
        previous = position
        event = task_source_record(RetainedOperation(sources[0], True)).event(installation)
        if (
            event.event_id != row["event_id"]
            or event.cycle.cycle_id != row["cycle_id"]
            or event.definition_id != row["definition_id"]
            or points_source_fingerprint(event) != row["fingerprint"]
        ):
            raise StorageFailure("invalid_points_source")
        if row["effect"] == 1:
            award = _posting(row)
            rotation = points.next_recipient(scope, event.definition_id, before=position)
            if not event.points_eligible or award != conserve_points(
                event, award.posted_at, rotation
            ):
                raise StorageFailure("invalid_points_posting")
        elif row["effect"] == 2:
            reversal = _posting(row)
            entries = points.ledger(scope, event.cycle.cycle_id)
            if (
                not event.closes_awards
                or len(entries) != 2
                or reversal != entries[0].reverse(event.event_id, reversal.posted_at)
            ):
                raise StorageFailure("invalid_points_posting")
