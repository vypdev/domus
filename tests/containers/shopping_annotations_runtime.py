"""Exercise genuine prior data and annotation recovery in an installed CPU image."""

import json
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from domus.application.inventory import CatalogAction, InventoryCommands
from domus.domain.errors import Conflict, InvalidInput
from domus.domain.identity import HumanIdentity
from domus.domain.shopping_annotations import ShoppingAnnotation, ShoppingPriority
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


ANNOTATION = ShoppingAnnotation("Literal\r\n\t😀 <b>kept</b>", ShoppingPriority.URGENT)


def service(store):
    return InventoryCommands(store, Actor(), Clock(), SecureIdentifiers())


def verify_reopened(root, receipt, *, restored):
    with closing(open_storage(root, "edge")) as owned:
        commands = service(owned.database)
        saved = commands.add_extra(
            "image-annotation",
            None,
            "Packaged request",
            MaterialQuantity("2"),
            annotation=ANNOTATION,
        )
        assert saved.operation_id == receipt["operation"]
        original = commands.original(CatalogAction.CLEAR_EXTRA, "image-clear", Actor().current())
        assert original.historical is restored
        with owned.database.read() as unit:
            extra = unit.shopping.extra("home", receipt["extra"])
            assert extra.annotation == ANNOTATION
            assert (extra.cleared_at is None) is restored


def exercise(fixtures, version):
    assert SCHEMA_VERSION == 37
    kind = "shopping-annotations" if version == 36 else "inventory-history"
    source = fixtures / f"v{version}-{kind}-source.sql"
    with TemporaryDirectory(prefix="shopping-annotations-image-") as temporary:
        base = Path(temporary)
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
                assert db.execute("PRAGMA user_version").fetchone()[0] == 37
                assert db.execute("PRAGMA foreign_key_check").fetchall() == []
                for name in tables:
                    selection = ",".join('"' + column + '"' for column in columns[name])
                    assert [
                        tuple(row) for row in db.execute(f'SELECT {selection} FROM "{name}"')
                    ] == rows[name]
                assert all(
                    tuple(row) == ("", "normal")
                    for row in db.execute("SELECT note,priority FROM shopping_extras")
                )
            commands = service(store)
            effect_tables = (
                "shopping_extras",
                "receipts",
                "audit",
                "outbox",
                "inventory_movements",
            )
            with store._connection() as db:
                counts = {
                    table: db.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                    for table in effect_tables
                }
            for code in range(0x80, 0xA0):
                try:
                    commands.add_extra(
                        "invalid-c1-" + str(code),
                        None,
                        "Rejected request",
                        MaterialQuantity("1"),
                        annotation=ShoppingAnnotation(chr(code)),
                    )
                except InvalidInput as error:
                    assert str(error) == "invalid_shopping_note"
                else:
                    raise AssertionError("A packaged C1 control created a shopping request")
            with store._connection() as db:
                assert {
                    table: db.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                    for table in effect_tables
                } == counts
            if version == 36:
                provenance = json.loads(
                    (fixtures / "v36-shopping-annotations-source.provenance.json").read_text()
                )["fixtures"]
                legacy = commands.add_extra(
                    "v36-active-free", None, "Schema36 fruit", MaterialQuantity("2")
                )
                assert legacy.operation_id == provenance["activeFreeOperation"]
                try:
                    commands.add_extra(
                        "v36-active-free",
                        None,
                        "Schema36 fruit",
                        MaterialQuantity("2"),
                        annotation=ShoppingAnnotation(),
                    )
                except Conflict as error:
                    assert str(error) == "idempotency_conflict"
                else:
                    raise AssertionError("Explicit annotation changed a genuine legacy request")
            saved = commands.add_extra(
                "image-annotation",
                None,
                "Packaged request",
                MaterialQuantity("2"),
                annotation=ANNOTATION,
            )
            receipt = {"operation": saved.operation_id, "extra": saved.result.decode()["extra_id"]}
            assert (
                commands.add_extra(
                    "image-annotation",
                    None,
                    "Packaged request",
                    MaterialQuantity("2"),
                    annotation=ANNOTATION,
                )
                == saved
            )
            archive, target = base / "archive", base / "prepared"
            checkpoint = SQLiteSnapshots(store, archive, store.installation, Clock()).create(
                "image-annotated"
            )
            assert checkpoint.schema_version == 37
            commands.clear_extra("image-clear", receipt["extra"])
            SQLiteRestorations(
                store, archive, target, store.installation, Clock(), checkpoint
            ).prepare("image-restore")
        finally:
            owned.close()
        # Each check starts a fresh interpreter against the same installed product.
        for restored in (False, True):
            if restored:
                assert (
                    SQLiteActivation(root, store.installation, Clock(), target).activate().state
                    == "active"
                )
            completed = subprocess.run(
                [sys.executable, __file__, "reopen", str(root), json.dumps(receipt), str(restored)],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
            assert completed.returncode == 0, completed.stdout + completed.stderr
    print(
        json.dumps(
            {
                "source_schema": version,
                "current_schema": 37,
                "all_original_columns_preserved": True,
                "literal_annotations": True,
                "fresh_process_replay": True,
                "snapshot_restoration": True,
                "historical_clear_preserved": True,
            }
        )
    )


if __name__ == "__main__":
    if sys.argv[1] == "reopen":
        verify_reopened(Path(sys.argv[2]), json.loads(sys.argv[3]), restored=sys.argv[4] == "True")
    else:
        exercise(Path(sys.argv[1]), int(sys.argv[2]))
