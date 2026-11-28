"""Exercise real historical data and lifecycle recovery inside the installed image."""

import json
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from domus.application.inventory import CatalogAction, InventoryCommands
from domus.domain.errors import Conflict
from domus.domain.identity import HumanIdentity
from domus.domain.inventory import PANTRY, BaseUnit
from domus.domain.task_material_values import MaterialQuantity
from domus.infrastructure.application_runtime import SecureIdentifiers
from domus.infrastructure.owned_storage import open_storage
from domus.infrastructure.sqlite import SCHEMA_VERSION
from domus.infrastructure.sqlite_activation import SQLiteActivation
from domus.infrastructure.sqlite_restoration import SQLiteRestorations
from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots


class Actor:
    def current(self):
        return HumanIdentity("ha_admin", True, True, False)


class Clock:
    def now(self):
        return 100


def service(store):
    return InventoryCommands(store, Actor(), Clock(), SecureIdentifiers())


def verify_reopened(root, receipt, restored):
    with closing(open_storage(root, "edge")) as owned:
        commands = service(owned.database)
        replay = commands.original(
            CatalogAction.RESTORE_LOCATION, "image-later-restore", Actor().current()
        )
        assert replay.operation_id == receipt["operation"] and replay.historical is restored
        assert commands.restore_location("image-later-restore", receipt["location"], 3) == replay
        with owned.database.read() as unit:
            location = unit.inventory.location("home", receipt["location"])
            assert location.name == "Image renamed cupboard"
            assert location.archived is restored and location.revision == (3 if restored else 4)
            assert (
                unit.inventory.location_usage("home", location.location_id).recorded_stock is False
            )


def exercise(fixtures, version):
    assert SCHEMA_VERSION == 38
    source = (
        fixtures
        / {
            20: "v20-inventory-history-source.sql",
            30: "v30-purchase-store-source.sql",
            37: "v37-storage-location-source.sql",
        }[version]
    )
    with TemporaryDirectory(prefix="storage-locations-image-") as directory:
        base = Path(directory)
        root = base / "root"
        root.mkdir(mode=0o700)
        database = root / "domus.sqlite3"
        with closing(sqlite3.connect(database, autocommit=True)) as db:
            db.executescript(source.read_text())
            assert db.execute("PRAGMA user_version").fetchone()[0] == version
            instance, channel = db.execute(
                "SELECT instance_id,channel FROM installation"
            ).fetchone()
            tables = [
                row[0] for row in db.execute("SELECT name FROM sqlite_schema WHERE type='table'")
            ]
            columns = {
                name: [row[1] for row in db.execute(f'PRAGMA table_info("{name}")')]
                for name in tables
            }
            rows = {name: db.execute(f'SELECT * FROM "{name}"').fetchall() for name in tables}
        database.chmod(0o600)
        identity = root / "installation.json"
        identity.write_text(
            json.dumps(
                {"schema_version": 1, "instance_id": instance, "channel": channel, "state": "ready"}
            )
        )
        identity.chmod(0o600)
        owned = open_storage(root, "edge")
        try:
            store = owned.database
            with store._connection() as db:
                assert db.execute("PRAGMA user_version").fetchone()[0] == 38
                assert db.execute("PRAGMA foreign_key_check").fetchall() == []
                for name in tables:
                    selection = ",".join('"' + column + '"' for column in columns[name])
                    assert [
                        tuple(row) for row in db.execute(f'SELECT {selection} FROM "{name}"')
                    ] == rows[name]
                assert all(
                    tuple(row) == (1, 0)
                    for row in db.execute("SELECT revision,archived FROM inventory_locations")
                )
            commands = service(store)
            if version == 37:
                provenance = json.loads(
                    (fixtures / "v37-storage-location-source.provenance.json").read_text()
                )
                prior = commands.original(
                    CatalogAction.TRANSFER, "v37-location-transfer", Actor().current()
                )
                assert prior.operation_id == provenance["originalTransferOperation"]
                commands.rename_location(
                    "image-old-name",
                    provenance["locations"]["cupboard"],
                    "Image source cupboard",
                    1,
                )
                assert (
                    commands.original(
                        CatalogAction.TRANSFER, "v37-location-transfer", Actor().current()
                    )
                    == prior
                )
                commands.archive_location(
                    "image-historical-shelf", provenance["locations"]["shelf"], 1
                )
            product = commands.register(
                "image-product", "Image lifecycle soap", BaseUnit.PIECE
            ).result.decode()["product_id"]
            location = commands.add_location("image-location", "Image cupboard").result.decode()[
                "location_id"
            ]
            commands.intake("image-intake", product, MaterialQuantity("2"))
            transfer = commands.transfer(
                "image-transfer", product, PANTRY, location, MaterialQuantity("1")
            )
            renamed = commands.rename_location(
                "image-rename", location, "Image renamed cupboard", 1
            )
            assert renamed.result.decode()["revision"] == "2"
            assert (
                commands.transfer(
                    "image-transfer", product, PANTRY, location, MaterialQuantity("1")
                )
                == transfer
            )
            try:
                commands.archive_location("image-occupied", location, 2)
            except Conflict as error:
                assert error.code == "inventory_location_not_empty"
            else:
                raise AssertionError("Populated location was archived")
            commands.transfer("image-empty", product, location, PANTRY, MaterialQuantity("1"))
            commands.archive_location("image-archive", location, 2)
            archive, target = base / "snapshots", base / "prepared"
            checkpoint = SQLiteSnapshots(store, archive, store.installation, Clock()).create(
                "image-archived"
            )
            later = commands.restore_location("image-later-restore", location, 3)
            receipt = {"operation": later.operation_id, "location": location}
            SQLiteRestorations(
                store, archive, target, store.installation, Clock(), checkpoint
            ).prepare("image-restore")
        finally:
            owned.close()
        for restored in (False, True):
            if restored:
                assert (
                    SQLiteActivation(root, store.installation, Clock(), target).activate().state
                    == "active"
                )
            result = subprocess.run(
                [
                    sys.executable,
                    __file__,
                    "reopen",
                    str(root),
                    json.dumps(receipt),
                    json.dumps(restored),
                ],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            assert result.returncode == 0, result.stdout + result.stderr
        print(
            json.dumps(
                {
                    "source_schema": version,
                    "current_schema": 38,
                    "original_columns_preserved": True,
                    "populated_archive_refused": True,
                    "paired_transfer_receipt_retained": True,
                    "fresh_process_replay": True,
                    "snapshot_restoration": True,
                    "historical_restore_did_not_reenact": True,
                }
            )
        )


if __name__ == "__main__":
    if sys.argv[1] == "reopen":
        verify_reopened(Path(sys.argv[2]), json.loads(sys.argv[3]), json.loads(sys.argv[4]))
    else:
        exercise(Path(sys.argv[1]), int(sys.argv[2]))
