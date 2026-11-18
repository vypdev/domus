"""Immutable revisions of household automation drafts."""

import sqlite3
from dataclasses import dataclass

from domus.domain.automation import AutomationDraft, AutomationRule
from domus.domain.errors import Conflict, InvalidInput, StorageFailure
from domus.domain.storage import JsonDocument

AUTOMATION_DRAFT_TABLE = "automation_draft_revisions"
AUTOMATION_DRAFT_STATEMENT = (
    "CREATE TABLE automation_draft_revisions("
    "household_id TEXT NOT NULL REFERENCES households(household_id), "
    "rule_id TEXT NOT NULL, revision INTEGER NOT NULL "
    "CHECK(typeof(revision)='integer' AND revision>=1), definition TEXT NOT NULL, "
    "PRIMARY KEY(household_id,rule_id,revision))"
)


def _draft(row: sqlite3.Row) -> AutomationDraft:
    try:
        rule = AutomationRule.from_document(JsonDocument(row["definition"]))
        return AutomationDraft(row["rule_id"], row["revision"], rule)
    except InvalidInput:
        raise StorageFailure("invalid_automation_draft_record") from None


@dataclass
class SQLiteAutomationDrafts:
    connection: sqlite3.Connection

    def latest(self, household_id: str, rule_id: str) -> AutomationDraft | None:
        row = self.connection.execute(
            "SELECT rule_id,revision,definition FROM automation_draft_revisions "
            "WHERE household_id=? AND rule_id=? ORDER BY revision DESC LIMIT 1",
            (household_id, rule_id),
        ).fetchone()
        return _draft(row) if row is not None else None

    def revision(self, household_id: str, rule_id: str, revision: int) -> AutomationDraft | None:
        row = self.connection.execute(
            "SELECT rule_id,revision,definition FROM automation_draft_revisions "
            "WHERE household_id=? AND rule_id=? AND revision=?",
            (household_id, rule_id, revision),
        ).fetchone()
        return _draft(row) if row is not None else None

    def page(self, household_id: str, after: str, limit: int) -> tuple[AutomationDraft, ...]:
        return tuple(
            _draft(row)
            for row in self.connection.execute(
                "SELECT d.rule_id,d.revision,d.definition FROM automation_draft_revisions d "
                "JOIN (SELECT rule_id,max(revision) AS revision FROM automation_draft_revisions "
                "WHERE household_id=? AND rule_id>? GROUP BY rule_id ORDER BY rule_id LIMIT ?) "
                "AS heads ON d.rule_id=heads.rule_id AND d.revision=heads.revision "
                "WHERE d.household_id=? ORDER BY d.rule_id",
                (household_id, after, limit, household_id),
            )
        )

    def append(self, household_id: str, draft: AutomationDraft) -> None:
        changed = self.connection.execute(
            "INSERT INTO automation_draft_revisions(household_id,rule_id,revision,definition) "
            "SELECT ?,?,?,? WHERE coalesce((SELECT max(revision) FROM automation_draft_revisions "
            "WHERE household_id=? AND rule_id=?),0)=?",
            (
                household_id,
                draft.rule_id,
                draft.revision,
                draft.rule.document().encoded,
                household_id,
                draft.rule_id,
                draft.revision - 1,
            ),
        ).rowcount
        if changed != 1:
            raise Conflict("revision_conflict")


def verify_automation_drafts(connection: sqlite3.Connection) -> None:
    previous: tuple[str, str] | None = None
    revision = 0
    for row in connection.execute(
        "SELECT * FROM automation_draft_revisions ORDER BY household_id,rule_id,revision"
    ):
        scope = row["household_id"], row["rule_id"]
        revision = revision + 1 if scope == previous else 1
        draft = _draft(row)
        if draft.revision != revision or draft.rule.document().encoded != row["definition"]:
            raise StorageFailure("invalid_automation_draft_record")
        previous = scope
