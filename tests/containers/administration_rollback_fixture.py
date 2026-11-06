"""Fictional owned data passed to immutable packaged applications; no external HA access."""

import hashlib
import io
import json
import os
import shutil
import sys
from pathlib import Path

import domus
from domus.application.household_commands import HouseholdCommands, SetupHousehold
from domus.application.member_profile_commands import (
    AliasUpdate,
    MemberProfileCommands,
    PreferencesUpdate,
)
from domus.composition import admin, ingress, server
from domus.domain.errors import DatabaseRejected
from domus.domain.identity import HumanIdentity
from domus.domain.member_profiles import MemberLocale
from domus.entrypoints.ui_bundle import load_bundle
from domus.infrastructure.application_runtime import SecureIdentifiers, SystemClock, TimeZoneCatalog
from domus.infrastructure.sqlite import SCHEMA_VERSION
from domus.infrastructure.sqlite_history import iter_operations

ROOT = Path("/data/domus")
RECORD = Path("/data/snapshots/administration.json")
USER = "a" * 32
ORIGIN = "https://fictional-domus.example"
TABLES = (
    "households",
    "members",
    "household_policy",
    "member_presentations",
    "member_preferences",
    "receipts",
    "audit",
    "outbox",
)


class Human:
    def current(self):
        return HumanIdentity(USER, True, True, False)

    def get(self, _user_id):
        raise AssertionError("No external directory subject is selected")


def console(*arguments):
    output, errors = io.StringIO(), io.StringIO()
    status = admin.main(
        ["--channel", "edge", "--data-directory", str(ROOT), *arguments],
        output_stream=output,
        error_stream=errors,
    )
    assert status == 0, errors.getvalue()
    return json.loads(output.getvalue())


def state(store):
    with store._connection() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        return {
            table: [
                list(row) for row in connection.execute(f'SELECT * FROM "{table}" ORDER BY rowid')
            ]
            for table in TABLES
        }


def proofs(store):
    with store._connection() as connection:
        return {
            value.evidence.receipt.operation_id: value.value()
            for value in iter_operations(connection)
        }


def ui():
    root = Path(domus.__file__).parent / "ui"
    assert load_bundle(root) is not None
    result = {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }
    assert len(result) == 4
    return result


def runtime_at(mode, root):
    return (
        ingress.create_owned_runtime("fictional-supervisor", "edge", root, (ORIGIN,))
        if mode == "native"
        else server.create_owned_runtime("http://fictional-ha.local", ORIGIN, "edge", root)
    )


def main():
    phase, mode, delivery = sys.argv[1:]
    assert phase in ("initialize", "later", "refuse", "restored", "rollback")
    assert mode in ("native", "standalone") and delivery in ("pending", "acknowledged")
    assert os.getuid() == os.getgid() == 65532
    assert SCHEMA_VERSION == (10 if phase in ("later", "restored") else 9)
    if phase == "refuse":
        saved = json.loads(RECORD.read_text())
        selected = ROOT / "generations" / saved["selected_generation"] / "domus.sqlite3"
        digest = hashlib.sha256(selected.read_bytes()).hexdigest()
        try:
            runtime_at(mode, ROOT)
        except DatabaseRejected as error:
            assert error.code == "unsupported_schema"
        else:
            raise AssertionError("Schema 9 runtime accepted a schema 10 generation")
        assert hashlib.sha256(selected.read_bytes()).hexdigest() == digest
        print(json.dumps({"refused_schema": 10, "database_sha256": digest}))
        return
    if phase == "rollback":
        before = Path("/data/snapshots/before")
        compatible = Path("/data/snapshots/compatible-nine")
        compatible.mkdir(mode=0o700)
        for name in ("installation.json", "domus.sqlite3"):
            shutil.copyfile(before / name, compatible / name)
            (compatible / name).chmod(0o600)
        saved = json.loads(RECORD.read_text())
        runtime = runtime_at(mode, compatible)
        try:
            store = runtime.storage.database
            assert state(store) == saved["initial_state"]
            assert set(proofs(store)) == {saved["setup_operation"], saved["before_operation"]}
            print(json.dumps({"state": state(store), "ui": ui(), "schema": SCHEMA_VERSION}))
        finally:
            runtime.close()
        return
    runtime = runtime_at(mode, ROOT)
    try:
        store, actor, clock, ids = (
            runtime.storage.database,
            Human(),
            SystemClock(),
            SecureIdentifiers(),
        )
        household = HouseholdCommands(store, actor, actor, TimeZoneCatalog(), clock, ids)
        profiles = MemberProfileCommands(store, actor, clock, ids)
        if phase == "initialize":
            initial = household.setup("setup", SetupHousehold("Rollback household", "UTC"))
            with store.read() as unit:
                member = unit.members.by_user("home", USER)
            prior = profiles.update_alias(
                "before-alias", AliasUpdate(member.member_id, 1, "Before upgrade")
            )
            record = {
                "mode": mode,
                "delivery": delivery,
                "instance_id": runtime.storage.installation.instance_id,
                "member_id": member.member_id,
                "setup_operation": initial.operation_id,
                "before_operation": prior.operation_id,
                "initial_state": state(store),
            }
        else:
            record = json.loads(RECORD.read_text())
            assert (record["mode"], record["delivery"]) == (mode, delivery)
            assert runtime.storage.installation.instance_id == record["instance_id"]
            member_id = record["member_id"]
            if phase == "later":
                assert state(store) == record["initial_state"]
                alias = profiles.update_alias(
                    "after-alias", AliasUpdate(member_id, 2, "After upgrade")
                )
                private = profiles.update_preferences(
                    "after-prefs", PreferencesUpdate(1, MemberLocale.SPANISH, False)
                )
                assert not alias.historical and not private.historical
                if delivery == "acknowledged":
                    with store.write() as unit:
                        assert unit.outbox.acknowledge(alias.operation_id)
                record.update(
                    after_alias_operation=alias.operation_id,
                    after_preferences_operation=private.operation_id,
                    original_proofs=proofs(store),
                )
                assert len(record["original_proofs"]) == 4
            else:
                assert runtime.storage.generation_id == record["selected_generation"]
                assert (
                    store.path
                    == ROOT / "generations" / record["selected_generation"] / "domus.sqlite3"
                )
                assert state(store) == record["initial_state"]
                original = proofs(store)
                assert original.keys() == record["original_proofs"].keys()
                later_ids = {record["after_alias_operation"], record["after_preferences_operation"]}
                for operation_id, prior in record["original_proofs"].items():
                    current = dict(original[operation_id])
                    assert current.pop("current") is (operation_id not in later_ids)
                    assert current.pop("archived_by") == (
                        record["selected_generation"] if operation_id in later_ids else None
                    )
                    assert current == {
                        key: value
                        for key, value in prior.items()
                        if key not in ("current", "archived_by")
                    }
                before = store.path.read_bytes()
                alias = profiles.update_alias(
                    "after-alias", AliasUpdate(member_id, 2, "After upgrade")
                )
                private = profiles.update_preferences(
                    "after-prefs", PreferencesUpdate(1, MemberLocale.SPANISH, False)
                )
                initial = household.setup("setup", SetupHousehold("Rollback household", "UTC"))
                assert alias.historical and alias.operation_id == record["after_alias_operation"]
                assert (
                    private.historical
                    and private.operation_id == record["after_preferences_operation"]
                )
                assert not initial.historical and initial.operation_id == record["setup_operation"]
                assert state(store) == record["initial_state"] and proofs(store) == original
                assert store.path.read_bytes() == before
                status = console("restore", "status", record["selected_generation"])
                assert status["state"] == "active"
                record["original_operations_preserved"] = True
        observation = {
            "state": state(store),
            "ui": ui(),
            "schema": SCHEMA_VERSION,
            "generation_id": runtime.storage.generation_id,
        }
    finally:
        runtime.close()
    if phase == "initialize":
        checkpoint = console("snapshot", "create", "/data/snapshots/before")
        assert checkpoint["snapshot"]["schema_version"] == 9
        record["checkpoint"] = checkpoint["snapshot"]
    elif phase == "later":
        prepared = console(
            "restore", "prepare", "/data/snapshots/before", "/data/snapshots/prepared"
        )
        assert prepared["state"] == "prepared"
        active = console("restore", "activate", "/data/snapshots/prepared")
        assert active["state"] == "active"
        record["selected_generation"] = active["selected_generation"]
    RECORD.write_text(json.dumps(record))
    print(json.dumps({**record, **observation}))


if __name__ == "__main__":
    main()
