"""Capture genuine schema-37 stock history using the accepted Edge.95 wheel.

Run with the wheel installed in an isolated environment. Every installed Python
module must match BASE; a newer runtime cannot manufacture the previous schema.
The input, identities, operations and output are synthetic public test fixtures.
"""

import argparse
import hashlib
import json
import sqlite3
import subprocess
from contextlib import closing
from pathlib import Path

BASE = "0a8c2939909bd849cdef60e711eb0796b3da3863"
FILENAME = "v37-storage-location-source"


class Clock:
    def now(self) -> int:
        return 100


class Identifiers:
    def __init__(self) -> None:
        self.count = 0

    def new(self) -> str:
        self.count += 1
        return f"schema37-location-capture-{self.count}"


class Actor:
    def current(self):
        from domus.domain.identity import HumanIdentity

        return HumanIdentity("ha_admin", True, True, False)


def rows(path: Path) -> dict[str, list[tuple]]:
    with closing(sqlite3.connect(path)) as connection:
        return {
            name: sorted(connection.execute(f'SELECT * FROM "{name}"').fetchall(), key=repr)
            for (name,) in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
        }


def capture(root: Path, wheel: Path, destination: Path, work: Path) -> None:
    import domus
    from domus.application.inventory import CatalogAction, InventoryCommands
    from domus.domain.inventory import PANTRY, BaseUnit
    from domus.domain.storage import Installation
    from domus.domain.task_material_values import MaterialQuantity
    from domus.infrastructure.sqlite import APPLICATION_ID, SCHEMA_VERSION, SQLiteDatabase
    from domus.infrastructure.sqlite_snapshots import _verify_database

    artifact = json.loads(
        subprocess.check_output(["git", "show", BASE + ":addon-edge/artifact.json"], cwd=root)
    )
    assert artifact["storageSchema"] == SCHEMA_VERSION == 37
    assert hashlib.sha256(wheel.read_bytes()).hexdigest() == artifact["wheelSHA256"]
    package = Path(domus.__file__).resolve().parent
    assert package != root / "backend/src/domus"
    inventory = {}
    for line in subprocess.check_output(
        ["git", "ls-tree", "-r", BASE, "--", "backend/src/domus"], cwd=root, text=True
    ).splitlines():
        metadata, name = line.split("\t", 1)
        if not name.endswith(".py"):
            continue
        mode, kind, expected = metadata.split()
        path = package / name.removeprefix("backend/src/domus/")
        assert mode == "100644" and kind == "blob" and not path.is_symlink()
        raw = path.read_bytes()
        assert hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest() == expected
        inventory[str(path.relative_to(package))] = hashlib.sha256(raw).hexdigest()
    assert set(inventory) == {str(path.relative_to(package)) for path in package.rglob("*.py")}
    assert len(inventory) == 250
    prior_name = "tests/fixtures/sqlite/v36-shopping-annotations-source.sql"
    prior = root / prior_name
    assert prior.read_bytes() == subprocess.check_output(
        ["git", "show", BASE + ":" + prior_name], cwd=root
    )
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / (FILENAME + ".sql")
    provenance = destination / (FILENAME + ".provenance.json")
    assert not target.exists() and not provenance.exists()
    work.mkdir(parents=True, exist_ok=False)
    path = work / "source.sqlite3"
    with closing(sqlite3.connect(path, autocommit=True)) as connection:
        connection.executescript(prior.read_text())
        assert connection.execute("PRAGMA user_version").fetchone() == (36,)
        installation = Installation(
            *connection.execute("SELECT instance_id,channel FROM installation").fetchone()
        )
    path.chmod(0o600)
    store = SQLiteDatabase(path, installation)
    store.initialize(require_existing=True)
    preserved = rows(path)
    actor = Actor()
    commands = InventoryCommands(store, actor, Clock(), Identifiers())
    product = commands.register(
        "v37-location-product", "Lifecycle source flour", BaseUnit.GRAM
    ).result.decode()["product_id"]
    locations = {}
    receipts = {}
    for key, name in (
        ("cupboard", "Lifecycle source cupboard"),
        ("drawer", "Lifecycle source drawer"),
        ("shelf", "Lifecycle source old shelf"),
    ):
        receipt = commands.add_location("v37-location-" + key, name)
        locations[key] = receipt.result.decode()["location_id"]
        receipts[key] = receipt
    commands.intake("v37-location-intake", product, MaterialQuantity("5.000001"))
    original = commands.transfer(
        "v37-location-transfer",
        product,
        PANTRY,
        locations["cupboard"],
        MaterialQuantity("3.000001"),
    )
    commands.transfer(
        "v37-location-return", product, locations["cupboard"], PANTRY, MaterialQuantity("1")
    )
    commands.transfer(
        "v37-location-shelf-in", product, PANTRY, locations["shelf"], MaterialQuantity("1")
    )
    commands.transfer(
        "v37-location-shelf-out", product, locations["shelf"], PANTRY, MaterialQuantity("1")
    )
    assert (
        commands.original(CatalogAction.TRANSFER, "v37-location-transfer", actor.current())
        == original
    )
    assert (
        commands.add_location("v37-location-cupboard", "Lifecycle source cupboard")
        == receipts["cupboard"]
    )
    current = rows(path)
    for table, before in preserved.items():
        # Appending audit/outbox rows advances SQLite's allocation counters.
        # Compare all business rows here and the complete roundtrip below.
        if table == "sqlite_sequence":
            continue
        assert all(row in current[table] for row in before), table
    with closing(sqlite3.connect(path)) as connection:
        connection.row_factory = sqlite3.Row
        assert _verify_database(connection, store, previous=False) == 37
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("SELECT COUNT(*) FROM inventory_transfers").fetchone()[0] == 4
        assert [row[1] for row in connection.execute("PRAGMA table_info(inventory_locations)")] == [
            "household_id",
            "location_id",
            "name",
            "name_key",
        ]
        dumped = "\n".join(connection.iterdump()) + "\n"
    dumped += f"PRAGMA application_id={APPLICATION_ID};\nPRAGMA user_version=37;\n"
    restored_path = work / "roundtrip.sqlite3"
    with closing(sqlite3.connect(restored_path, autocommit=True)) as connection:
        connection.executescript(dumped)
    restored_path.chmod(0o600)
    SQLiteDatabase(restored_path, installation).initialize(require_existing=True)
    assert rows(path) == rows(restored_path)
    target.write_text(dumped)
    provenance.write_text(
        json.dumps(
            {
                "schemaVersion": 37,
                "acceptedBaseCommit": BASE,
                "runtimeArtifactSource": artifact["sourceCommit"],
                "runtimeArtifactVersion": artifact["version"],
                "runtimeArtifactWheelSHA256": artifact["wheelSHA256"],
                "actualWheelChecked": True,
                "installedRuntimeFilesMatched": len(inventory),
                "installedRuntimeInventorySHA256": hashlib.sha256(
                    json.dumps(inventory, sort_keys=True).encode()
                ).hexdigest(),
                "inputFixture": prior_name,
                "inputFixtureSHA256": hashlib.sha256(prior.read_bytes()).hexdigest(),
                "outputFixtureSHA256": hashlib.sha256(target.read_bytes()).hexdigest(),
                "oldBusinessRowsPreserved": True,
                "sqliteSequenceMayAdvance": True,
                "roundtripRowsEqual": True,
                "productID": product,
                "locations": locations,
                "originalTransferOperation": original.operation_id,
                "pairedTransfers": 4,
                "scope": (
                    "Synthetic household, identity, stock and history captured by unchanged "
                    "installed Edge.95; not generated by schema38 code."
                ),
            },
            indent=2,
        )
        + "\n"
    )
    print(
        json.dumps(
            {"fixture": str(target), "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    arguments = parser.parse_args()
    capture(
        arguments.root.resolve(),
        arguments.wheel.resolve(),
        arguments.destination.resolve(),
        arguments.work.resolve(),
    )
