"""Schema-6 material storage and explicit migration of version-1 task snapshots."""

import sqlite3

from domus.infrastructure.sqlite_task_records import (
    definition_document,
    occurrence_document,
    read_definition,
    read_occurrence,
)

MATERIAL_TABLES = {"task_material_intents"}
MATERIAL_STATEMENTS = (
    "CREATE UNIQUE INDEX task_cycle_material_scope "
    "ON task_cycles(household_id,occurrence_id,cycle_id)",
    "CREATE TABLE task_material_intents(intent_id TEXT PRIMARY KEY NOT NULL, "
    "household_id TEXT NOT NULL, occurrence_id TEXT NOT NULL, cycle_id TEXT NOT NULL, "
    "line_id TEXT NOT NULL, recorded_by TEXT NOT NULL, "
    "revision INTEGER NOT NULL CHECK(typeof(revision)='integer' AND revision>=1), "
    "state TEXT NOT NULL CHECK(state IN ('pending_recording','pending_authorization',"
    "'pending_regularization','pending_processing','not_used','posted','corrected','dismissed')), "
    "document TEXT NOT NULL, UNIQUE(household_id,cycle_id,line_id), "
    "FOREIGN KEY(household_id,occurrence_id,cycle_id) "
    "REFERENCES task_cycles(household_id,occurrence_id,cycle_id), "
    "FOREIGN KEY(household_id,recorded_by) REFERENCES members(household_id,member_id))",
    "CREATE INDEX task_material_cycle_page "
    "ON task_material_intents(household_id,cycle_id,intent_id)",
)


def migrate_task_documents(connection: sqlite3.Connection) -> None:
    """Caller owns atomic migration. Receipts, source events and cycles remain byte-identical."""
    for row in connection.execute("SELECT definition_id,document FROM task_definitions").fetchall():
        document = definition_document(read_definition(row["document"], version=1))
        connection.execute(
            "UPDATE task_definitions SET document=? WHERE definition_id=?",
            (document.encoded, row["definition_id"]),
        )
    for row in connection.execute("SELECT occurrence_id,document FROM task_occurrences").fetchall():
        occurrence = occurrence_document(read_occurrence(row["document"], version=1))
        connection.execute(
            "UPDATE task_occurrences SET document=? WHERE occurrence_id=?",
            (occurrence.encoded, row["occurrence_id"]),
        )
