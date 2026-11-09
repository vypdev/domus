"""Persist policy revisions and completion snapshots beside the existing Points ledger."""

import json
import sqlite3
from dataclasses import asdict, dataclass
from typing import Any

from domus.domain.errors import InvalidInput, StorageFailure
from domus.domain.point_allocation import (
    AllocationMode,
    AllocationPolicy,
    AllocationSetting,
    CompletionAllocation,
    PointAllocation,
    ShareRounding,
)
from domus.domain.points import require_allocation_cycle
from domus.domain.storage import JsonDocument
from domus.infrastructure.sqlite_task_records import read_cycle

ALLOCATION_TABLES = {"point_allocation_settings", "point_completion_allocations"}
ALLOCATION_STATEMENTS = (
    "CREATE TABLE point_allocation_settings(household_id TEXT NOT NULL REFERENCES households,"
    "scope TEXT NOT NULL, definition_id TEXT, revision INTEGER NOT NULL CHECK(revision>=1),"
    "document TEXT CHECK(document IS NULL OR json_valid(document)),"
    "CHECK((definition_id IS NULL AND scope='household' AND document IS NOT NULL) OR "
    "(definition_id IS NOT NULL AND scope='task:'||definition_id)),"
    "PRIMARY KEY(household_id,scope), FOREIGN KEY(household_id,definition_id) "
    "REFERENCES task_definitions(household_id,definition_id))",
    "CREATE TABLE point_completion_allocations(position INTEGER PRIMARY KEY AUTOINCREMENT,"
    "household_id TEXT NOT NULL REFERENCES households, cycle_id TEXT NOT NULL REFERENCES "
    "task_cycles, definition_id TEXT NOT NULL, document TEXT NOT NULL CHECK(json_valid(document)),"
    "UNIQUE(household_id,cycle_id), FOREIGN KEY(household_id,definition_id) "
    "REFERENCES task_definitions(household_id,definition_id))",
    "CREATE INDEX point_allocation_rotation ON point_completion_allocations("
    "household_id,definition_id,position) WHERE json_extract(document,'$.policy.mode')="
    "'conserve_total'",
)


def _scope(definition_id: str | None) -> str:
    return "household" if definition_id is None else "task:" + definition_id


def _policy(data: dict[str, Any]) -> AllocationPolicy:
    return AllocationPolicy(
        AllocationMode(data["mode"]),
        data["precision"],
        None if data["rounding"] is None else ShareRounding(data["rounding"]),
    )


def read_allocation_setting(row: sqlite3.Row) -> AllocationSetting:
    try:
        document = row["document"]
        return AllocationSetting(
            None if document is None else _policy(JsonDocument(document).decode()),
            row["revision"],
        )
    except InvalidInput, KeyError, TypeError, ValueError:
        raise StorageFailure("invalid_points_policy") from None


def read_completion_allocation(row: sqlite3.Row) -> CompletionAllocation:
    try:
        value: dict[str, Any] = JsonDocument(row["document"]).decode()
        facts = value["allocation"]
        return CompletionAllocation(
            _policy(value["policy"]),
            value["policy_revision"],
            value["override_definition_id"],
            value["base"],
            value["previous_recipient"],
            PointAllocation(
                tuple(tuple(share) for share in facts["shares"]), facts["next_recipient"]
            ),
        )
    except InvalidInput, KeyError, TypeError, ValueError:
        raise StorageFailure("invalid_points_allocation") from None


@dataclass
class SQLitePointAllocations:
    connection: sqlite3.Connection

    def setting(self, household_id: str, definition_id: str | None) -> AllocationSetting | None:
        row = self.connection.execute(
            "SELECT * FROM point_allocation_settings WHERE household_id=? AND scope=?",
            (household_id, _scope(definition_id)),
        ).fetchone()
        return None if row is None else read_allocation_setting(row)

    def put_setting(
        self, household_id: str, definition_id: str | None, setting: AllocationSetting
    ) -> None:
        self.connection.execute(
            "INSERT INTO point_allocation_settings VALUES(?,?,?,?,?) "
            "ON CONFLICT(household_id,scope) DO UPDATE SET revision=excluded.revision, "
            "document=excluded.document",
            (
                household_id,
                _scope(definition_id),
                definition_id,
                setting.revision,
                None
                if setting.policy is None
                else JsonDocument(json.dumps(asdict(setting.policy))).encoded,
            ),
        )

    def snapshot(self, household_id: str, cycle_id: str) -> CompletionAllocation | None:
        row = self.connection.execute(
            "SELECT * FROM point_completion_allocations WHERE household_id=? AND cycle_id=?",
            (household_id, cycle_id),
        ).fetchone()
        return None if row is None else read_completion_allocation(row)

    def last_conserved(self, household_id: str, definition_id: str) -> CompletionAllocation | None:
        row = self.connection.execute(
            "SELECT * FROM point_completion_allocations WHERE household_id=? AND definition_id=? "
            "AND json_extract(document,'$.policy.mode')='conserve_total' "
            "ORDER BY position DESC LIMIT 1",
            (household_id, definition_id),
        ).fetchone()
        return None if row is None else read_completion_allocation(row)

    def freeze(
        self, household_id: str, cycle_id: str, definition_id: str, snapshot: CompletionAllocation
    ) -> None:
        self.connection.execute(
            "INSERT INTO point_completion_allocations"
            "(household_id,cycle_id,definition_id,document) VALUES(?,?,?,?)",
            (
                household_id,
                cycle_id,
                definition_id,
                JsonDocument(json.dumps(asdict(snapshot))).encoded,
            ),
        )


def verify_point_allocations(connection: sqlite3.Connection) -> None:
    for row in connection.execute("SELECT * FROM point_allocation_settings"):
        read_allocation_setting(row)
    rotations: dict[tuple[str, str], str | None] = {}
    for row in connection.execute(
        "SELECT a.*, c.document AS cycle_document, w.definition_id AS cycle_definition "
        "FROM point_completion_allocations a LEFT JOIN task_cycles c "
        "ON a.household_id=c.household_id AND a.cycle_id=c.cycle_id LEFT JOIN task_occurrences w "
        "ON c.household_id=w.household_id AND c.occurrence_id=w.occurrence_id "
        "ORDER BY a.position"
    ):
        if row["cycle_definition"] != row["definition_id"]:
            raise StorageFailure("invalid_points_allocation")
        snapshot = read_completion_allocation(row)
        cycle = read_cycle(row["cycle_document"])
        require_allocation_cycle(snapshot, cycle, row["definition_id"])
        if snapshot.policy.mode is AllocationMode.CONSERVE_TOTAL:
            key = (row["household_id"], row["definition_id"])
            if key in rotations and rotations[key] != snapshot.previous_recipient:
                raise StorageFailure("invalid_points_rotation")
            rotations[key] = snapshot.allocation.next_recipient
