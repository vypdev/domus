"""Real offline activation migrates frozen inputs and preserves closed recovery guards."""

import hashlib
import json
import sqlite3
from contextlib import closing
from dataclasses import replace
from pathlib import Path

import pytest
from test_recovery_commands import configured, start
from test_snapshot_values import INSTALLATION
from test_sqlite_snapshots import Clock

from domus.domain.errors import Conflict
from domus.domain.snapshots import Snapshot
from domus.infrastructure.owned_storage import open_storage
from domus.infrastructure.sqlite import SQLiteDatabase
from domus.infrastructure.sqlite_activation import SQLiteActivation
from domus.infrastructure.sqlite_restoration import SQLiteRestorations
from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots


def identity_at(root, installation):
    path = root / "installation.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "instance_id": installation.instance_id,
                "channel": installation.channel,
                "state": "ready",
            }
        )
    )
    path.chmod(0o600)
    return path


@pytest.mark.parametrize("version", [1, 2, 3, 4])
def test_real_activation_upgrades_only_target_from_frozen_source_and_checkpoint(tmp_path, version):
    archive, root = tmp_path / "snapshot", tmp_path / "root"
    archive.mkdir(mode=0o700)
    root.mkdir(mode=0o700)
    database = archive / "domus.sqlite3"
    frozen = Path(__file__).resolve().parents[1] / f"fixtures/sqlite/v{version}.sql"
    with closing(sqlite3.connect(database, autocommit=True)) as connection:
        connection.executescript(frozen.read_text())
        # Frozen v1/v2 contain a dummy fingerprint; use a canonical digest for replay evidence.
        if version < 3:
            connection.execute("UPDATE receipts SET payload_fingerprint=?", ("a" * 64,))
    database.chmod(0o600)
    identity = identity_at(archive, INSTALLATION)
    checkpoint = Snapshot(
        "old",
        INSTALLATION,
        version,
        2000,
        100,
        hashlib.sha256(database.read_bytes()).hexdigest(),
        database.stat().st_size,
        hashlib.sha256(identity.read_bytes()).hexdigest(),
    )
    (archive / "manifest.json").write_text(checkpoint.document().encoded)
    (archive / "manifest.json").chmod(0o600)
    source = root / "domus.sqlite3"
    source.write_bytes(database.read_bytes())
    source.chmod(0o600)
    identity_at(root, INSTALLATION)
    original = source.read_bytes()
    target = tmp_path / "prepared"
    prepared = SQLiteRestorations(
        SQLiteDatabase(source, INSTALLATION), archive, target, INSTALLATION, Clock(), checkpoint
    ).prepare("restore-old")
    assert prepared.source.schema_version == version
    result = SQLiteActivation(root, INSTALLATION, Clock(), target).activate()
    assert result.state == "active" and result.record.rollback_snapshot.schema_version == version
    assert source.read_bytes() == original == database.read_bytes()
    selected = open_storage(root, "edge")
    try:
        with selected.database._connection() as connection:
            assert connection.execute("PRAGMA user_version").fetchone()[0] == 8
            assert connection.execute("SELECT COUNT(*) FROM retained_operations").fetchone()[0] == (
                2 if version == 4 else 1
            )
        with selected.database.read() as unit:
            assert unit.households.current().revision == (1 if version >= 3 else 3)
            assert len(unit.audit.entries("home")) == len(unit.outbox.pending()) == 1
    finally:
        selected.close()


@pytest.mark.parametrize("terminal", ["consume", "cancel"])
def test_actual_activation_of_old_approval_cannot_rearm_closed_recovery(tmp_path, terminal):
    commands, approval, original, actor, clock, console = configured(tmp_path)
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    path = root / "domus.sqlite3"
    path.write_bytes(original.path.read_bytes())
    path.chmod(0o600)
    identity_at(root, original.installation)
    database = SQLiteDatabase(path, original.installation)
    commands = replace(commands, transactions=database)
    approval = replace(approval, transactions=database)
    request_id = start(commands)
    approval.approve(request_id)
    archive = tmp_path / "snapshot"
    snapshot = SQLiteSnapshots(database, archive, original.installation, Clock()).create("approved")
    if terminal == "consume":
        commands.complete("terminal", request_id, 2)
    else:
        commands.cancel("terminal", request_id, 2)
    target = tmp_path / "prepared"
    SQLiteRestorations(database, archive, target, original.installation, Clock(), snapshot).prepare(
        "restore-approved"
    )
    SQLiteActivation(root, original.installation, Clock(), target).activate()
    selected = open_storage(root, "edge")
    commands = replace(commands, transactions=selected.database)
    approval = replace(approval, transactions=selected.database)
    try:
        replay = (
            commands.complete("terminal", request_id, 2)
            if terminal == "consume"
            else commands.cancel("terminal", request_id, 2)
        )
        assert replay.historical
        for attempt in (
            lambda: commands.complete("new-key", request_id, 2),
            lambda: commands.cancel("new-key", request_id, 2),
            lambda: approval.approve(request_id),
            lambda: commands.status(request_id),
        ):
            with pytest.raises(Conflict, match="recovery_closed"):
                attempt()
        with selected.database.read() as unit:
            assert unit.members.by_user("home", "ha_new") is None
            assert unit.recoveries.pending("home", clock.now()) == ()
        assert len(console.reviews) == 1
    finally:
        selected.close()
