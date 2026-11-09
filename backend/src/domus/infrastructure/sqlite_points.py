"""Append one receipt and optional exact ledger posting for each task event."""

import json
import sqlite3
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from typing import Any, cast

from domus.application.family_ports import FamilyAllocationEvidence, FamilyLedgerEntry, FamilyWork
from domus.domain.errors import InvalidInput, StorageFailure
from domus.domain.points import (
    LEGACY_POLICY,
    PointsPosting,
    conserve_points,
    frozen_points,
    points_source_fingerprint,
)
from domus.domain.restoration import RetainedOperation
from domus.domain.storage import Installation, JsonDocument
from domus.domain.task_events import TaskLifecycleEvent
from domus.infrastructure.sqlite_point_allocations import SQLitePointAllocations
from domus.infrastructure.sqlite_task_history import (
    RESTORED_AWARD_CLOSURE,
    SQLiteTaskHistory,
    task_source_record,
)
from domus.infrastructure.sqlite_task_records import read_cycle

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


_MEMBER_SHARES = """
FROM points_task_receipts p
JOIN json_each(p.document, '$.shares') share
WHERE p.household_id=:household AND p.effect>0
    AND json_extract(share.value, '$[0]')=:member
"""

_MEMBER_HISTORY = """
SELECT p.*, c.occurrence_id, json_extract(c.document, '$.verified_at') AS verified_at,
    json_extract(w.document, '$.definition_snapshot.content.title') AS title
FROM points_task_receipts p
JOIN task_cycles c ON c.household_id=p.household_id AND c.cycle_id=p.cycle_id
JOIN task_occurrences w ON w.household_id=c.household_id AND w.occurrence_id=c.occurrence_id
WHERE p.household_id=:household AND p.effect>0
    AND EXISTS (
        SELECT 1 FROM json_each(p.document, '$.shares') share
        WHERE json_extract(share.value, '$[0]')=:member
    )
    AND (:after IS NULL OR p.position < (
        SELECT position FROM points_task_receipts
        WHERE household_id=:household AND event_id=:after
    ))
ORDER BY p.position DESC LIMIT :limit
"""

_MEMBER_WORK = f"""
SELECT c.document, w.definition_id,
    json_extract(w.document, '$.definition_snapshot.content.title') AS title,
    c.closed_at IS NULL AND json_extract(c.document, '$.verification')!='rejected'
    AND NOT EXISTS (
        SELECT 1 FROM points_task_receipts p
        WHERE p.household_id=c.household_id AND p.cycle_id=c.cycle_id AND p.effect=1
    ) AND NOT EXISTS (
        SELECT 1 FROM retained_operations
        WHERE household_id=c.household_id
            AND json_extract(document, '$.event_payload.cycle.cycle_id')=c.cycle_id
            AND {RESTORED_AWARD_CLOSURE}
    ) AS awaiting_credit,
    (
        SELECT MAX(progress.created_at) FROM outbox progress
        WHERE progress.household_id=c.household_id AND progress.event_type='task.transition'
            AND json_extract(progress.payload, '$.occurrence_id')=c.occurrence_id
            AND json_extract(progress.payload, '$.state')='in_progress'
            AND progress.created_at <= json_extract(c.document, '$.performed_at')
            AND progress.created_at > COALESCE((
                SELECT MAX(prior.closed_at) FROM task_cycles prior
                WHERE prior.household_id=c.household_id AND prior.occurrence_id=c.occurrence_id
                    AND prior.cycle_id!=c.cycle_id
                    AND prior.closed_at <= json_extract(c.document, '$.recorded_at')
            ), -1)
    ) AS started_at
FROM task_cycles c
JOIN task_occurrences w ON w.household_id=c.household_id AND w.occurrence_id=c.occurrence_id
WHERE c.household_id=:household
    AND json_extract(c.document, '$.performed_at')>=:start
    AND json_extract(c.document, '$.performed_at')<:end
    AND EXISTS (
        SELECT 1 FROM json_each(c.document, '$.performers') performer
        WHERE json_extract(performer.value, '$.member_id')=:member
    )
ORDER BY json_extract(c.document, '$.performed_at') DESC, c.cycle_id DESC
"""


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
            "AND effect=1 AND position<=? AND COALESCE(json_extract(document,'$.policy_version'),"
            "'conserve_total.v1')=? ORDER BY position DESC LIMIT 1",
            (
                household_id,
                definition_id,
                2**63 - 1 if before is None else before - 1,
                LEGACY_POLICY,
            ),
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

    def member_totals(
        self, household_id: str, member_id: str, start: int, end: int
    ) -> tuple[int, int]:
        row = self.connection.execute(
            "SELECT COALESCE(SUM(json_extract(share.value, '$[1]')),0), "
            "COALESCE(SUM(CASE WHEN json_extract(p.document,'$.performed_at')>=:start "
            "AND json_extract(p.document,'$.performed_at')<:end "
            "THEN json_extract(share.value, '$[1]') ELSE 0 END),0) " + _MEMBER_SHARES,
            {"household": household_id, "member": member_id, "start": start, "end": end},
        ).fetchone()
        return int(row[0]), int(row[1])

    def member_history(
        self, household_id: str, member_id: str, after: str | None, limit: int
    ) -> tuple[FamilyLedgerEntry, ...]:
        entries = []
        snapshots = SQLitePointAllocations(self.connection)
        for row in self.connection.execute(
            _MEMBER_HISTORY,
            {"household": household_id, "member": member_id, "after": after, "limit": limit},
        ):
            posting = _posting(row)
            snapshot = snapshots.snapshot(household_id, posting.cycle_id)
            if snapshot is None:
                shares = tuple((member, abs(amount)) for member, amount in posting.shares)
                allocation = FamilyAllocationEvidence.legacy(posting.precision, shares)
            else:
                allocation = FamilyAllocationEvidence.from_snapshot(snapshot)
            entries.append(
                FamilyLedgerEntry(
                    posting.event_id,
                    posting.cycle_id,
                    row["occurrence_id"],
                    row["title"],
                    dict(posting.shares)[member_id],
                    posting.performed_at,
                    row["verified_at"],
                    posting.posted_at,
                    posting.reverses,
                    posting.policy_version,
                    allocation,
                )
            )
        return tuple(entries)

    def member_work(
        self, household_id: str, member_id: str, start: int, end: int
    ) -> Iterable[FamilyWork]:
        for row in self.connection.execute(
            _MEMBER_WORK,
            {"household": household_id, "member": member_id, "start": start, "end": end},
        ):
            yield FamilyWork(
                read_cycle(row["document"]),
                row["definition_id"],
                row["title"],
                row["started_at"],
                bool(row["awaiting_credit"]),
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


def verify_points_records(
    connection: sqlite3.Connection, installation: Installation, *, has_allocations: bool = False
) -> None:
    history = SQLiteTaskHistory(connection)
    points = SQLitePoints(connection)
    allocations = SQLitePointAllocations(connection) if has_allocations else None
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
            snapshot = (
                None if allocations is None else allocations.snapshot(scope, event.cycle.cycle_id)
            )
            expected = (
                conserve_points(
                    event,
                    award.posted_at,
                    points.next_recipient(scope, event.definition_id, before=position),
                )
                if snapshot is None
                else frozen_points(event, award.posted_at, snapshot)
            )
            if not event.points_eligible or award != expected:
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
