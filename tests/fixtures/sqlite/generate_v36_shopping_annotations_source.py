"""Capture genuine schema-36 Shopping state before annotation migration.

Run against an unchanged BASE runtime with backend/src and tests/backend on
PYTHONPATH. The recipe refuses a newer or modified runtime. The source fixture,
identities, requests and all data are synthetic.
"""

import argparse
import hashlib
import json
import shutil
import sqlite3
import subprocess
import tempfile
import zipfile
from contextlib import closing
from pathlib import Path

BASE = "0cdc633e3d4bb374f31277cb4861fbe13de9b9ea"
FILENAME = "v36-shopping-annotations-source"


def source_proof(root: Path, wheel: Path | None) -> dict[str, object]:
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
        assert actual == expected, f"Runtime differs from accepted schema-36 source: {name}"
        inventory[name] = hashlib.sha256(raw).hexdigest()
    authored = {str(path.relative_to(root)) for path in (root / "backend/src/domus").rglob("*.py")}
    assert authored == {name for name in inventory if name.endswith(".py")}
    artifact = json.loads(
        subprocess.check_output(["git", "show", BASE + ":addon-edge/artifact.json"], cwd=root)
    )
    assert artifact["storageSchema"] == 36
    if wheel is not None:
        assert hashlib.sha256(wheel.read_bytes()).hexdigest() == artifact["wheelSHA256"]
        with zipfile.ZipFile(wheel) as package:
            for name, digest in inventory.items():
                assert (
                    hashlib.sha256(package.read(name.removeprefix("backend/src/"))).hexdigest()
                    == digest
                )
    return {
        "acceptedBaseCommit": BASE,
        "runtimeArtifactSource": artifact["sourceCommit"],
        "runtimeArtifactVersion": artifact["version"],
        "runtimeArtifactWheelSHA256": artifact["wheelSHA256"],
        "actualWheelChecked": wheel is not None,
        "trackedBackendRuntimeFiles": len(inventory),
        "runtimeInventorySHA256": hashlib.sha256(
            json.dumps(inventory, sort_keys=True).encode()
        ).hexdigest(),
        "allTrackedBackendRuntimeFilesMatchBase": True,
    }


def database_rows(path: Path) -> dict[str, list[tuple]]:
    with closing(sqlite3.connect(path)) as connection:
        return {
            name: sorted(connection.execute(f'SELECT * FROM "{name}"').fetchall(), key=repr)
            for (name,) in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
        }


class Identifiers:
    def __init__(self) -> None:
        self.count = 0

    def new(self) -> str:
        self.count += 1
        return f"schema36-capture-{self.count}"


def capture(root: Path, destination: Path, wheel: Path | None) -> None:
    proof = source_proof(root, wheel)
    from test_household_commands import Actor, Clock

    import domus
    from domus.application.inventory import CatalogAction, InventoryCommands
    from domus.domain.storage import Installation
    from domus.domain.task_material_values import MaterialQuantity
    from domus.infrastructure.sqlite import APPLICATION_ID, SCHEMA_VERSION, SQLiteDatabase
    from domus.infrastructure.sqlite_snapshots import _verify_database

    assert Path(domus.__file__).resolve().parent == root / "backend/src/domus"
    assert SCHEMA_VERSION == 36
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / (FILENAME + ".sql")
    manifest = destination / (FILENAME + ".provenance.json")
    assert not target.exists() and not manifest.exists()
    work = Path(tempfile.mkdtemp(prefix="domus-157-schema36-capture-"))
    try:
        path = work / "source.sqlite3"
        prior = root / "tests/fixtures/sqlite/v23-shared-shopping-source.sql"
        with closing(sqlite3.connect(path, autocommit=True)) as connection:
            connection.executescript(prior.read_text())
            assert connection.execute("PRAGMA user_version").fetchone() == (23,)
            installation = Installation(
                *connection.execute("SELECT instance_id,channel FROM installation").fetchone()
            )
            product = connection.execute(
                "SELECT product_id FROM inventory_products WHERE name='Oil'"
            ).fetchone()[0]
            preserved = {
                table: connection.execute(f'SELECT * FROM "{table}"').fetchall()
                for table in ("shopping_receipts", "inventory_replenishment", "inventory_effects")
            }
        path.chmod(0o600)
        store = SQLiteDatabase(path, installation)
        store.initialize(require_existing=True)
        actor, clock, identifiers = Actor(), Clock(), Identifiers()
        commands = InventoryCommands(store, actor, clock, identifiers)
        active = commands.add_extra(
            "v36-active-tracked", product, None, MaterialQuantity("0.000001")
        )
        free = commands.add_extra("v36-active-free", None, "Schema36 fruit", MaterialQuantity("2"))
        spare = commands.add_extra(
            "v36-cleared-free", None, "Schema36 spare", MaterialQuantity("1")
        )
        cleared = commands.clear_extra("v36-clear", spare.result.decode()["extra_id"])
        assert (
            commands.add_extra("v36-active-tracked", product, None, MaterialQuantity("0.000001"))
            == active
        )
        assert (
            commands.original(CatalogAction.ADD_EXTRA, "v36-active-free", actor.current()) == free
        )
        assert commands.original(CatalogAction.CLEAR_EXTRA, "v36-clear", actor.current()) == cleared
        with closing(sqlite3.connect(path)) as connection:
            connection.row_factory = sqlite3.Row
            assert _verify_database(connection, store, previous=False) == 36
            assert connection.execute("PRAGMA application_id").fetchone()[0] == APPLICATION_ID
            assert connection.execute("PRAGMA user_version").fetchone()[0] == 36
            assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
            columns = [row[1] for row in connection.execute("PRAGMA table_info(shopping_extras)")]
            assert "note" not in columns and "priority" not in columns
            extras = connection.execute("SELECT * FROM shopping_extras").fetchall()
            assert len(extras) == 3 and sum(row["cleared_at"] is None for row in extras) == 2
            for table, before in preserved.items():
                assert [
                    tuple(row) for row in connection.execute(f'SELECT * FROM "{table}"')
                ] == before
            dumped = "\n".join(connection.iterdump()) + "\n"
        dumped += f"PRAGMA application_id={APPLICATION_ID};\nPRAGMA user_version=36;\n"
        restored_path = work / "roundtrip.sqlite3"
        with closing(sqlite3.connect(restored_path, autocommit=True)) as connection:
            connection.executescript(dumped)
        restored = SQLiteDatabase(restored_path, installation)
        restored.initialize(require_existing=True)
        assert database_rows(path) == database_rows(restored_path)
        original = database_rows(path)
        target.write_text(dumped)
        proof.update(
            {
                "schemaVersion": 36,
                "applicationId": APPLICATION_ID,
                "installation": {
                    "instanceId": installation.instance_id,
                    "channel": installation.channel,
                },
                "priorSourceFixture": prior.name,
                "priorSourceFixtureSHA256": hashlib.sha256(prior.read_bytes()).hexdigest(),
                "priorSourceSchema": 23,
                "fixture": target.name,
                "fixtureSHA256": hashlib.sha256(target.read_bytes()).hexdigest(),
                "bytes": target.stat().st_size,
                "tableRows": {name: len(rows) for name, rows in original.items()},
                "fixtures": {
                    "product": product,
                    "activeTrackedExtra": active.result.decode()["extra_id"],
                    "activeFreeExtra": free.result.decode()["extra_id"],
                    "clearedFreeExtra": spare.result.decode()["extra_id"],
                    "activeTrackedOperation": active.operation_id,
                    "activeFreeOperation": free.operation_id,
                    "clearOperation": cleared.operation_id,
                },
                "qualification": (
                    "Actual accepted schema36 runtime migration, application commands and verified "
                    "SQL roundtrip; every original table row equal."
                ),
                "noCurrentSchemaRelabeling": True,
                "recipe": Path(__file__).name,
                "recipeSHA256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "command": (
                    "PYTHONPATH=backend/src:tests/backend .venv/bin/python <recipe> "
                    "--source-root <accepted36-checkout> --reference-wheel <exact72-wheel> "
                    "--output-dir <fixtures>"
                ),
            }
        )
        manifest.write_text(json.dumps(proof, indent=2) + "\n")
    except BaseException:
        print(f"Schema-36 capture failed; original producer retained at {work}")
        raise
    else:
        files = list(work.iterdir())
        assert all(path.is_file() and not path.is_symlink() for path in files)
        allocation = sum(path.stat().st_blocks * 512 for path in files)
        free_before = shutil.disk_usage(work).free
        for path in files:
            path.unlink()
        work.rmdir()
        proof["completedProducerRetirement"] = {
            "files": len(files),
            "allocatedBytes": allocation,
            "filesystemFreeChange": shutil.disk_usage(work.parent).free - free_before,
        }
        manifest.write_text(json.dumps(proof, indent=2) + "\n")
        print(json.dumps({"fixture": str(target), "sha256": proof["fixtureSHA256"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=Path.cwd())
    parser.add_argument("--reference-wheel", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    root = args.source_root.resolve()
    capture(root, args.output_dir or root / "tests/fixtures/sqlite", args.reference_wheel)
