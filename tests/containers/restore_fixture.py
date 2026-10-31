"""Disposable packaged-data fixtures; never connect to HA or modify an owner installation."""

import hashlib
import json
import os
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

from domus.application.household_commands import HouseholdCommands, SetupHousehold
from domus.application.household_queries import HouseholdQueries
from domus.domain.identity import HumanIdentity
from domus.infrastructure.application_runtime import SecureIdentifiers, TimeZoneCatalog
from domus.infrastructure.owned_storage import attach_storage
from domus.infrastructure.sqlite_activation import SQLiteActivation

ROOT = Path("/data/domus")


class Actor:
    def current(self):
        return HumanIdentity("packaged-fixture-human", True, True, False)

    def get(self, _identifier):
        raise AssertionError("This fixture does not use a directory lookup")


class Clock:
    def now(self):
        return 100


def commands(database):
    return HouseholdCommands(
        database, Actor(), Actor(), TimeZoneCatalog(), Clock(), SecureIdentifiers()
    )


def private_layout():
    assert os.getuid() == os.getgid() == 65532
    for folder, directories, files in os.walk(ROOT):
        directory = Path(folder)
        assert directory.stat().st_uid == 65532 and directory.stat().st_mode & 0o777 == 0o700
        for name in directories + files:
            path = directory / name
            assert not path.is_symlink() and path.stat().st_uid == 65532
            assert path.stat().st_mode & 0o777 == (0o700 if path.is_dir() else 0o600)


def main():
    mode = sys.argv[1]
    if mode == "fault":
        point = sys.argv[2]
        with closing(attach_storage(ROOT, "edge")) as storage:
            installation = storage.installation
        original = os.replace
        inode = ROOT.stat().st_ino

        def terminate(source, target, **kwargs):
            result = original(source, target, **kwargs)
            if os.fstat(kwargs["dst_dir_fd"]).st_ino == inode:
                if target == "installation.json" and point == "selected":
                    os._exit(37)
                if target == "activation.json" and point == "pending":
                    os._exit(37)
            return result

        os.replace = terminate
        SQLiteActivation(ROOT, installation, Clock(), Path("/data/snapshots/prepared")).activate()
        raise AssertionError("The process did not terminate at its selected boundary")
    with closing(attach_storage(ROOT, "edge")) as storage:
        service = commands(storage.database)
        if mode == "initialize":
            service.setup("setup", SetupHousehold("Checkpoint home", "UTC"))
        elif mode == "later":
            receipt = service.update("later", "Later home", "UTC", 1)
            if sys.argv[2] == "delivered":
                with storage.database.write() as unit:
                    unit.outbox.acknowledge(receipt.operation_id)
        elif mode == "after":
            service.update("after", "After activation", "UTC", 1)
        elif mode == "active":
            replay = service.update("later", "Later home", "UTC", 1)
            assert replay.historical
            view = HouseholdQueries(storage.database, Actor().current()).operation(
                replay.operation_id
            )
            assert view.delivered == (sys.argv[2] == "delivered")
            with storage.database.read() as unit:
                assert unit.households.current().name == "Checkpoint home"
                assert len(unit.audit.entries("home")) == len(unit.outbox.pending()) == 1
        elif mode == "rollback":
            assert not service.update("later", "Later home", "UTC", 1).historical
            assert service.update("after", "After activation", "UTC", 1).historical
            with storage.database.read() as unit:
                assert unit.households.current().name == "Later home"
            with storage.database._connection() as connection:
                assert (
                    connection.execute(
                        "SELECT seq FROM sqlite_sequence WHERE name='outbox'"
                    ).fetchone()[0]
                    == 3
                )
                assert (
                    connection.execute("SELECT COUNT(*) FROM retained_operations").fetchone()[0]
                    == 3
                )
        else:
            raise AssertionError("Unknown fixture operation")
        with storage.database._connection() as connection:
            assert connection.execute("PRAGMA user_version").fetchone()[0] == 4
        private_layout()
        print(
            json.dumps(
                {
                    "instance_id": storage.installation.instance_id,
                    "generation_id": storage.generation_id,
                    "flat_sha256": hashlib.sha256(
                        (ROOT / "domus.sqlite3").read_bytes()
                    ).hexdigest(),
                    "python": sys.version.split()[0],
                    "sqlite": sqlite3.sqlite_version,
                }
            )
        )


if __name__ == "__main__":
    main()
