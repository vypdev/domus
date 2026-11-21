"""Capture real schema-35 state before scheduled execution changes its compatibility.

Run from a checkout whose backend matches BASE, with backend/src and tests/backend
on PYTHONPATH. The recipe may be read from a newer checkout; it refuses newer or
modified runtime sources. All identities and records are synthetic.
"""

import argparse
import hashlib
import json
import shutil
import sqlite3
import subprocess
import tempfile
from contextlib import closing
from pathlib import Path

BASE = "0d9aefecce18528f8da175dd32db1a9250c9b0d9"
FILENAME = "v35-daily-automation-source"


def source_proof(root: Path) -> dict[str, object]:
    rows = subprocess.check_output(
        ["git", "ls-tree", "-r", BASE, "--", "backend/src/domus"], cwd=root, text=True
    ).splitlines()
    inventory = {}
    for row in rows:
        metadata, name = row.split("\t", 1)
        mode, kind, expected = metadata.split()
        path = root / name
        assert mode == "100644" and kind == "blob" and path.is_file() and not path.is_symlink()
        raw = path.read_bytes()
        actual = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        assert actual == expected, f"Runtime differs from schema-35 source: {name}"
        inventory[name] = hashlib.sha256(raw).hexdigest()
    authored = {str(path.relative_to(root)) for path in (root / "backend/src/domus").rglob("*.py")}
    assert authored == {name for name in inventory if name.endswith(".py")}
    return {
        "runtimeCommit": BASE,
        "trackedBackendRuntimeFiles": len(inventory),
        "runtimeInventorySHA256": hashlib.sha256(
            json.dumps(inventory, sort_keys=True).encode()
        ).hexdigest(),
        "allTrackedBackendRuntimeFilesMatchBase": True,
    }


def database_rows(path: Path) -> dict[str, list[tuple]]:
    with closing(sqlite3.connect(path)) as connection:
        tables = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        return {
            name: sorted(connection.execute(f'SELECT * FROM "{name}"').fetchall(), key=repr)
            for (name,) in tables
        }


def capture(root: Path, destination: Path) -> None:
    proof = source_proof(root)
    from test_household_commands import fixture
    from test_sqlite_snapshots import Clock

    import domus
    from domus.application.automation_drafts import AutomationDrafts, SaveDraft
    from domus.application.automation_execution import (
        AutomationExecution,
        ConfigureAutomation,
        RunAutomation,
    )
    from domus.application.fixed_materialization import MaintenanceScope
    from domus.application.household_commands import SetupHousehold
    from domus.application.task_commands import TaskCommands
    from domus.domain.automation import AutomationRule, DailyTrigger
    from domus.domain.task_values import TaskContent
    from domus.infrastructure.sqlite import APPLICATION_ID, SCHEMA_VERSION, SQLiteDatabase
    from domus.infrastructure.sqlite_snapshots import _verify_database
    from domus.infrastructure.task_cursor import TaskCursor

    assert Path(domus.__file__).resolve().parent == root / "backend/src/domus"
    assert SCHEMA_VERSION == 35
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / (FILENAME + ".sql")
    manifest = destination / (FILENAME + ".provenance.json")
    assert not target.exists() and not manifest.exists()
    work = Path(tempfile.mkdtemp(prefix="domus-155-schema35-capture-"))
    try:
        commands, store, actor, _, identifiers = fixture(work / "source.sqlite3")
        commands.setup("v35-setup", SetupHousehold("Synthetic schema 35", "Europe/Madrid"))
        clock = Clock()
        scope = MaintenanceScope(store.installation, "home")
        drafts = AutomationDrafts(
            store, scope, actor, actor.current, clock, identifiers, TaskCursor(clock, b"v" * 32)
        )
        execution = AutomationExecution(
            store,
            scope,
            actor,
            actor.current,
            clock,
            identifiers,
            TaskCommands(store, actor, clock, identifiers),
        )
        manual = AutomationRule(1, "manual", None, TaskContent("Schema35 manual pantry check"))
        first = drafts.save("v35-manual-draft", SaveDraft(None, 0, manual))
        rule_id = first.result.decode()["rule_id"]
        enabled = execution.configure("v35-manual-enable", ConfigureAutomation(rule_id, 1, 0, True))
        ran = execution.run("v35-manual-run", RunAutomation(rule_id, 1, 1))
        daily = AutomationRule(2, DailyTrigger("07:30"), None, TaskContent("Schema35 daily check"))
        edited = drafts.save("v35-daily-edit", SaveDraft(rule_id, 1, daily))
        inactive = drafts.save("v35-inactive-daily", SaveDraft(None, 0, daily))
        disabled = drafts.save("v35-disabled-manual", SaveDraft(None, 0, manual))
        disabled_id = disabled.result.decode()["rule_id"]
        execution.configure("v35-other-enable", ConfigureAutomation(disabled_id, 1, 0, True))
        execution.configure("v35-other-disable", ConfigureAutomation(disabled_id, 1, 1, False))
        assert execution.state(rule_id).control.enabled
        assert execution.state(rule_id).control.rule_revision == 1
        assert drafts.reopen(rule_id).revision == 2
        assert drafts.reopen(rule_id).rule == daily
        assert not execution.state(disabled_id).control.enabled
        assert drafts.original("v35-daily-edit") == edited

        with closing(sqlite3.connect(store.path)) as connection:
            connection.row_factory = sqlite3.Row
            assert _verify_database(connection, store, previous=False) == 35
            assert connection.execute("PRAGMA application_id").fetchone()[0] == APPLICATION_ID
            assert connection.execute("PRAGMA user_version").fetchone()[0] == 35
            assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
            dumped = "\n".join(connection.iterdump()) + "\n"
        dumped += f"PRAGMA application_id={APPLICATION_ID};\nPRAGMA user_version=35;\n"
        restored_path = work / "roundtrip.sqlite3"
        with closing(sqlite3.connect(restored_path, autocommit=True)) as connection:
            connection.executescript(dumped)
        restored = SQLiteDatabase(restored_path, store.installation)
        restored.initialize(require_existing=True)
        assert database_rows(store.path) == database_rows(restored_path)
        target.write_text(dumped)
        contents = database_rows(store.path)
        proof.update(
            {
                "schemaVersion": 35,
                "applicationId": APPLICATION_ID,
                "installation": {
                    "instanceId": store.installation.instance_id,
                    "channel": store.installation.channel,
                },
                "fixture": target.name,
                "fixtureSHA256": hashlib.sha256(target.read_bytes()).hexdigest(),
                "bytes": target.stat().st_size,
                "tableRows": {name: len(rows) for name, rows in contents.items()},
                "fixtures": {
                    "enabledManualRule": rule_id,
                    "enabledManualRevision": 1,
                    "latestDailyRevision": 2,
                    "inactiveDailyRule": inactive.result.decode()["rule_id"],
                    "disabledManualRule": disabled_id,
                    "manualTaskOccurrence": ran.result.decode()["task_occurrence_id"],
                    "manualRunOperation": ran.operation_id,
                    "manualEnableOperation": enabled.operation_id,
                },
                "qualification": (
                    "Actual schema 35 creation and verified SQL roundtrip; "
                    "all original table rows equal."
                ),
                "noCurrentSchemaRelabeling": True,
                "recipe": "generate_v35_daily_automation_source.py",
                "recipeSHA256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "command": (
                    "PYTHONPATH=backend/src:tests/backend .venv/bin/python <recipe-path> "
                    "--source-root <schema35-checkout> --output-dir <fixture-directory>"
                ),
                "temporaryState": (
                    "Only two completed synthetic databases; "
                    "failed producers are preserved for diagnosis."
                ),
            }
        )
        manifest.write_text(json.dumps(proof, indent=2) + "\n")
    except BaseException:
        print(f"Schema-35 capture failed; original producer retained at {work}")
        raise
    else:
        files = list(work.iterdir())
        assert all(path.is_file() and not path.is_symlink() for path in files)
        allocation = sum(path.stat().st_blocks * 512 for path in files)
        free_before = shutil.disk_usage(work).free
        shutil.rmtree(work)
        proof["completedProducerRetirement"] = {
            "files": len(files),
            "allocatedBytes": allocation,
            "filesystemFreeChange": shutil.disk_usage(destination).free - free_before,
        }
        manifest.write_text(json.dumps(proof, indent=2) + "\n")
        print(json.dumps({"fixture": str(target), "sha256": proof["fixtureSHA256"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    source = args.source_root.resolve()
    capture(source, args.output_dir or source / "tests/fixtures/sqlite")
