"""Capture schema 34 with unchanged historical source, never by downgrading current tables.

Export BASE's backend/src with git archive and pass that directory as --runtime.
Run in the repository's dependency environment; all imported historical source
bytes are checked against Git before the old runtime creates any database.
"""

import argparse
import hashlib
import json
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

BASE = "1acd83cd8ee2aa1fd25a64b830a74c1413ab24c8"
FILENAME = "v34-barcode-upgrade-source"


def capture(root: Path, runtime: Path, destination: Path, work: Path) -> None:
    package = runtime / "domus"
    inventory = {}
    for line in subprocess.check_output(
        ["git", "ls-tree", "-r", BASE, "--", "backend/src/domus"], cwd=root, text=True
    ).splitlines():
        metadata, name = line.split("\t", 1)
        if not name.endswith(".py"):
            continue
        mode, kind, expected = metadata.split()
        relative = name.removeprefix("backend/src/domus/")
        path = package / relative
        assert mode == "100644" and kind == "blob" and not path.is_symlink()
        raw = path.read_bytes()
        assert hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest() == expected
        inventory[relative] = hashlib.sha256(raw).hexdigest()
    assert set(inventory) == {str(path.relative_to(package)) for path in package.rglob("*.py")}
    sys.path.insert(0, str(runtime))
    import domus
    from domus.domain.storage import Installation
    from domus.infrastructure.sqlite import APPLICATION_ID, SCHEMA_VERSION, SQLiteDatabase
    from domus.infrastructure.sqlite_snapshots import _verify_database

    assert Path(domus.__file__).resolve().parent == package
    assert SCHEMA_VERSION == 34
    prior = root / "tests/fixtures/sqlite/v30-purchase-store-source.sql"
    assert prior.read_bytes() == subprocess.check_output(
        ["git", "show", BASE + ":tests/fixtures/sqlite/" + prior.name], cwd=root
    )
    work.mkdir(parents=True, exist_ok=False)
    path = work / "source.sqlite3"
    with closing(sqlite3.connect(path, autocommit=True)) as db:
        db.executescript(prior.read_text())
        installation = Installation(
            *db.execute("SELECT instance_id,channel FROM installation").fetchone()
        )
        before = {
            name: db.execute('SELECT * FROM "' + name + '"').fetchall()
            for (name,) in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    path.chmod(0o600)
    store = SQLiteDatabase(path, installation)
    store.initialize(require_existing=True)
    with closing(sqlite3.connect(path)) as db:
        db.row_factory = sqlite3.Row
        assert _verify_database(db, store, previous=False) == 34
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        for name, rows in before.items():
            current = [tuple(row) for row in db.execute('SELECT * FROM "' + name + '"')]
            assert [row[: len(rows[0])] for row in current] == rows if rows else current == []
        dumped = (
            "\n".join(db.iterdump())
            + f"\nPRAGMA application_id={APPLICATION_ID};\nPRAGMA user_version=34;\n"
        )
    restored = work / "roundtrip.sqlite3"
    with closing(sqlite3.connect(restored, autocommit=True)) as db:
        db.executescript(dumped)
    restored.chmod(0o600)
    SQLiteDatabase(restored, installation).initialize(require_existing=True)
    with closing(sqlite3.connect(path)) as original, closing(sqlite3.connect(restored)) as copy:
        assert list(original.iterdump()) == list(copy.iterdump())
    target = destination / (FILENAME + ".sql")
    provenance = destination / (FILENAME + ".provenance.json")
    assert not target.exists() and not provenance.exists()
    target.write_text(dumped)
    provenance.write_text(
        json.dumps(
            {
                "schemaVersion": 34,
                "historicalRuntimeCommit": BASE,
                "runtimeSourceFilesMatched": len(inventory),
                "runtimeSourceInventorySHA256": hashlib.sha256(
                    json.dumps(inventory, sort_keys=True).encode()
                ).hexdigest(),
                "inputFixture": str(prior.relative_to(root)),
                "inputFixtureSHA256": hashlib.sha256(prior.read_bytes()).hexdigest(),
                "outputFixtureSHA256": hashlib.sha256(target.read_bytes()).hexdigest(),
                "allInputRowsPreserved": True,
                "roundtripRowsEqual": True,
                "scope": (
                    "Synthetic data upgraded by unchanged historical schema-34 source, "
                    "not current code or a claim about a published wheel."
                ),
            },
            indent=2,
        )
        + "\n"
    )
    print(target)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "runtime", "destination", "work"):
        parser.add_argument("--" + name, type=Path, required=True)
    arguments = parser.parse_args()
    capture(
        *(getattr(arguments, name).resolve() for name in ("root", "runtime", "destination", "work"))
    )
