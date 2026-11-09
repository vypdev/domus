"""Exercise the pre-category database as exported by the real schema-14 runtime."""

import hashlib
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

from domus.domain.storage import CommandKey, Installation
from domus.infrastructure.sqlite import APPLICATION_ID, SQLiteDatabase

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/sqlite/v14.sql"
FIXTURE_SHA256 = "acbd5cca8b4ad2177c9ab0fb448efd3502db352081607da1674ce3e39c3acb9a"
SLOT = "259a69c04141d744e9458abb6accd428b26969ec1bf245334de7e9ea7435b11a"


def test_schema14_fixture_retains_snapshots_and_original_operations(tmp_path):
    payload = FIXTURE.read_bytes()
    assert hashlib.sha256(payload).hexdigest() == FIXTURE_SHA256
    database = tmp_path / "fixture.sqlite3"
    database.touch(mode=0o600)
    with closing(sqlite3.connect(database, autocommit=True)) as connection:
        connection.executescript(payload.decode())
        assert connection.execute("PRAGMA user_version").fetchone() == (14,)
        assert connection.execute("PRAGMA application_id").fetchone() == (APPLICATION_ID,)
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        installation = Installation(
            *connection.execute("SELECT instance_id, channel FROM installation").fetchone()
        )
    store = SQLiteDatabase(database, installation)
    store.initialize(require_existing=True)
    with store.read() as unit:
        work = unit.tasks.occurrence("home", "identity-9")
        assert work.definition_snapshot == unit.tasks.definition("home", "identity-8")
        assert work.definition_snapshot.content.tags == ("Garden",)
        scheduled = unit.tasks.occurrence("home", "identity-6")
        assert scheduled.definition_snapshot == unit.tasks.definition("home", "identity-3")
        assert scheduled.due_at == 1774746000000
        slot = unit.recurrence.slot("home", SLOT)
        assert slot.schedule == unit.recurrence.schedule("home", "identity-4")
        assert slot.occurrence_id == scheduled.occurrence_id
        assert slot.planned.nominal.local == datetime(2026, 3, 29, 2, 30)
        assert slot.planned.resolved.instant_ms == scheduled.due_at

        created = CommandKey("home", "ha_admin", "task.create", "legacy-tag-only")
        rule = CommandKey("home", "ha_admin", "recurrence.fixed.create", "scheduled")
        materialized = CommandKey("home", "system:recurrence", "recurrence.materialize", SLOT)
        audit = {row.operation_id: row for row in unit.audit.entries("home")}
        outbox = {row.event_id: row for row in unit.outbox.pending()}
        for command, operation in (
            (created, "identity-10"),
            (rule, "identity-5"),
            (materialized, "identity-7"),
        ):
            receipt = unit.receipts.get(command)
            assert receipt.operation_id == operation
            assert not receipt.historical
            assert audit[operation].command == command
            assert outbox[operation].event_type == command.action
