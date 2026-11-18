"""The saved automation revision currently authorized for explicit later admission."""

import sqlite3
from dataclasses import dataclass

from domus.domain.automation import AutomationControl
from domus.domain.errors import Conflict, InvalidInput, StorageFailure
from domus.domain.storage import validate_identifier

AUTOMATION_CONTROL_TABLE = "automation_rule_controls"
AUTOMATION_CONTROL_STATEMENT = (
    "CREATE TABLE automation_rule_controls("
    "household_id TEXT NOT NULL, rule_id TEXT NOT NULL, "
    "rule_revision INTEGER NOT NULL CHECK(typeof(rule_revision)='integer' AND rule_revision>=1), "
    "control_revision INTEGER NOT NULL "
    "CHECK(typeof(control_revision)='integer' AND control_revision>=1), "
    "enabled INTEGER NOT NULL CHECK(typeof(enabled)='integer' AND enabled IN (0,1)), "
    "PRIMARY KEY(household_id,rule_id), "
    "FOREIGN KEY(household_id,rule_id,rule_revision) "
    "REFERENCES automation_draft_revisions(household_id,rule_id,revision))"
)


def _control(row: sqlite3.Row) -> AutomationControl:
    try:
        enabled = row["enabled"]
        if type(enabled) is not int or enabled not in (0, 1):
            raise InvalidInput("invalid_automation_control")
        return AutomationControl(
            row["rule_id"], row["rule_revision"], row["control_revision"], enabled == 1
        )
    except InvalidInput:
        raise StorageFailure("invalid_automation_control_record") from None


@dataclass
class SQLiteAutomationControls:
    connection: sqlite3.Connection

    def get(self, household_id: str, rule_id: str) -> AutomationControl | None:
        row = self.connection.execute(
            "SELECT rule_id,rule_revision,control_revision,enabled FROM automation_rule_controls "
            "WHERE household_id=? AND rule_id=?",
            (household_id, rule_id),
        ).fetchone()
        return _control(row) if row is not None else None

    def save(self, household_id: str, control: AutomationControl, expected_revision: int) -> None:
        if control.control_revision != expected_revision + 1:
            raise Conflict("revision_conflict")
        if expected_revision == 0:
            changed = self.connection.execute(
                "INSERT INTO automation_rule_controls VALUES(?,?,?,?,?) "
                "ON CONFLICT(household_id,rule_id) DO NOTHING",
                (
                    household_id,
                    control.rule_id,
                    control.rule_revision,
                    control.control_revision,
                    control.enabled,
                ),
            ).rowcount
        else:
            changed = self.connection.execute(
                "UPDATE automation_rule_controls SET rule_revision=?,control_revision=?,enabled=? "
                "WHERE household_id=? AND rule_id=? AND control_revision=?",
                (
                    control.rule_revision,
                    control.control_revision,
                    control.enabled,
                    household_id,
                    control.rule_id,
                    expected_revision,
                ),
            ).rowcount
        if changed != 1:
            raise Conflict("revision_conflict")


def verify_automation_controls(connection: sqlite3.Connection) -> None:
    for row in connection.execute("SELECT * FROM automation_rule_controls"):
        validate_identifier(row["household_id"])
        _control(row)
