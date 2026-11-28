"""Location lifecycle acceptance uses real writers, retained receipts and old SQL."""

import hashlib
import json
import sqlite3
from contextlib import closing
from dataclasses import replace
from pathlib import Path

import pytest
from test_activation_compatibility import identity_at
from test_household_commands import Actor, Clock
from test_inventory_catalog_http import INVENTORY, VIEWER, get, post, register
from test_inventory_catalog_storage import setup
from test_recurrence_http import USER
from test_rewards_http import member_context
from test_rewards_storage import command_evidence, race
from test_shared_shopping import queries
from test_stock_transfers import location
from test_task_commands import resource
from test_task_runtime import api as api

from domus.application.inventory import CatalogAction, InventoryCommands, InventorySettlement
from domus.application.task_requests import CompleteTask, CreateTask
from domus.domain.errors import Conflict, InvalidInput, NotFound, StorageFailure
from domus.domain.identity import (
    MAX_REVISION,
    HumanIdentity,
    Member,
    MemberStatus,
    Permission,
    PermissionRule,
    Role,
)
from domus.domain.inventory import PANTRY, BaseUnit, EffectKind, StorageLocation
from domus.domain.storage import Installation, Receipt
from domus.domain.task_material_values import MaterialQuantity, MaterialSelection, MaterialUsage
from domus.domain.task_values import MaterialRecording, TaskContent, TaskOverrides
from domus.infrastructure import sqlite as storage
from domus.infrastructure.application_runtime import SecureIdentifiers
from domus.infrastructure.owned_storage import open_storage
from domus.infrastructure.sqlite import SQLiteDatabase
from domus.infrastructure.sqlite_activation import SQLiteActivation
from domus.infrastructure.sqlite_inventory import SQLiteInventory, verify_inventory_locations
from domus.infrastructure.sqlite_restoration import SQLiteRestorations
from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots, _verify_database

M = MaterialQuantity


def scene(root, *, quantity="2"):
    tasks, store, commands = setup(root)
    product = commands.register("product", "Flour", BaseUnit.GRAM).result.decode()["product_id"]
    target = location(commands)
    commands.intake("stock", product, M("5"))
    commands.transfer("to-cupboard", product, PANTRY, target, M(quantity))
    return tasks, store, commands, product, target


def current(store, target):
    with store.read() as unit:
        return unit.inventory.location("home", target)


def test_location_transitions_validate_state_identity_and_revision():
    """C01/C02: metadata changes retain identity and require real transitions."""
    original = StorageLocation("cupboard", "Cupboard")
    capitalized = original.rename("CUPBOARD")
    assert capitalized.location_id == original.location_id and capitalized.revision == 2
    archived = capitalized.set_archived(True)
    assert archived.archived and archived.revision == 3
    restored = archived.set_archived(False)
    assert not restored.archived and restored.name == "CUPBOARD" and restored.revision == 4
    for action, code in (
        (lambda: original.rename("Cupboard"), "inventory_location_unchanged"),
        (lambda: archived.rename("Other"), "inventory_location_archived"),
        (lambda: original.set_archived(False), "inventory_location_state_conflict"),
        (lambda: archived.set_archived(True), "inventory_location_state_conflict"),
        (
            lambda: replace(original, revision=MAX_REVISION).rename("Other"),
            "inventory_location_revision_exhausted",
        ),
    ):
        with pytest.raises(Conflict, match=code):
            action()
    for action in (
        lambda: replace(original, archived=1),
        lambda: original.set_archived(1),
        lambda: replace(original, revision=0),
    ):
        with pytest.raises(InvalidInput):
            action()
    assert original == StorageLocation("cupboard", "Cupboard")


def test_http_lifecycle_retains_stock_history_receipts_and_current_authority(api):
    """C01/C02/C03/C05: both HTTP compositions protect the complete journey."""
    api.user(USER, True)
    with api.store.write() as unit:
        unit.members.save(Member("viewer", "home", VIEWER, Role.VIEWER, MemberStatus.ACTIVE, 1), 0)
    product = register(api, "flour", "Flour", "gram")
    assert post(api, "stock", "intake", product_id=product, quantity="5").status_code == 200
    added = post(api, "new-location", "add-location", name="Cupboard").json()
    target = added["result"]["location_id"]
    assert added["result"] == {"location_id": target, "name": "Cupboard"}
    move = dict(
        product_id=product, source_location=PANTRY, destination_location=target, quantity="2"
    )
    assert post(api, "move", "transfer", **move).status_code == 200
    args = dict(location_id=target, name="Kitchen cupboard", expected_revision="1")
    renamed = post(api, "rename", "rename-location", **args)
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["result"] == {
        "location_id": target,
        "name": "Kitchen cupboard",
        "revision": "2",
        "archived": False,
    }
    assert post(api, "rename", "rename-location", **args).json() == renamed.json()
    assert (
        post(api, "rename", "rename-location", **(args | {"name": "Other"})).json()["code"]
        == "idempotency_conflict"
    )
    assert (
        post(api, "stale", "rename-location", **(args | {"name": "Other"})).json()["code"]
        == "revision_conflict"
    )
    blocked = post(api, "archive", "archive-location", location_id=target, expected_revision="2")
    assert blocked.status_code == 409 and blocked.json()["code"] == "inventory_location_not_empty"
    assert (
        post(
            api,
            "back",
            "transfer",
            **(move | {"source_location": target, "destination_location": PANTRY}),
        ).status_code
        == 200
    )
    history_url = f"{INVENTORY}/products/{product}/movements"
    before = api.client.get(history_url, headers=member_context(USER)).json()
    saved = post(api, "archive", "archive-location", location_id=target, expected_revision="2")
    assert saved.status_code == 200 and saved.json()["result"]["archived"] is True
    archived = get(api).json()["locations"][0]
    assert archived == {
        "location_id": target,
        "name": "Kitchen cupboard",
        "revision": "3",
        "archived": True,
        "archive_blocked_reason": None,
    }
    history = api.client.get(history_url, headers=member_context(USER)).json()
    assert history["movements"] == before["movements"] and history["total"] == before["total"]
    assert next(item for item in history["locations"] if item["location_id"] == target)["archived"]
    assert post(api, "late", "transfer", **move).json()["code"] == "inventory_location_archived"
    assert (
        post(
            api, "pantry", "archive-location", location_id=PANTRY, expected_revision="1"
        ).status_code
        == 404
    )
    assert (
        post(
            api, "foreign", "restore-location", location_id="foreign", expected_revision="1"
        ).status_code
        == 404
    )
    original_url = f"{INVENTORY}/requests/inventory.rename-location/rename"
    assert api.client.get(original_url, headers=member_context(USER)).json() == renamed.json()
    api.user(VIEWER)
    assert get(api, VIEWER).json()["locations"] == [archived]
    for action in ("rename-location", "archive-location", "restore-location"):
        data = {"location_id": target, "expected_revision": "3"}
        if action == "rename-location":
            data["name"] = "Viewer change"
        assert post(api, action, action, user=VIEWER, **data).status_code == 403
    assert api.client.get(original_url, headers=member_context(VIEWER)).status_code == 403
    api.user(USER, True)
    restored = post(api, "restore", "restore-location", location_id=target, expected_revision="3")
    assert restored.status_code == 200 and restored.json()["result"]["revision"] == "4"
    assert post(api, "again", "transfer", **move).status_code == 200
    with api.store.write() as unit:
        member = unit.members.by_user("home", USER)
        unit.members.save(
            replace(member, status=MemberStatus.SUSPENDED, revision=member.revision + 1),
            member.revision,
        )
    assert api.client.get(original_url, headers=member_context(USER)).status_code == 403


def test_archive_checks_only_direct_live_effects_and_keeps_reserved_names(tmp_path):
    """C02: general demand and settled history do not prevent archive."""
    _, store, commands, product, target = scene(tmp_path)
    commands.transfer("empty", product, target, PANTRY, M("2"))
    with store.read() as unit:
        refs = unit.inventory.location_bindings("home", product)
    general = commands.commit_effect("general", EffectKind.DEMAND, refs[PANTRY], M("1"))
    direct = commands.commit_effect("direct", EffectKind.DEMAND, refs[target], M("1"))
    with pytest.raises(Conflict, match="inventory_location_pending_effects"):
        commands.archive_location("archive", target, 1)
    with store.write() as unit:
        effect = unit.inventory.effect("home", direct.result.decode()["effect_id"])
        unit.inventory.update_effect(
            replace(effect, remaining=0, revision=effect.revision + 1), effect.revision
        )
    before = queries(commands).history(product, limit=25, cursor=None)
    archived = commands.archive_location("archive", target, 1)
    assert current(store, target).archived and archived.result.decode()["revision"] == "2"
    with store.read() as unit:
        assert (
            unit.inventory.effect("home", general.result.decode()["effect_id"]).remaining
            == 1_000_000
        )
        binding = unit.inventory.material("home", refs[target])
        assert unit.inventory.location("other-home", target) is None
    for action in (
        lambda: commands.add_location("duplicate", "CUPBOARD"),
        lambda: commands.commit_effect("late-effect", EffectKind.DEMAND, refs[target], M("1")),
        lambda: commands.receive("late-stock", binding, M("1")),
    ):
        with pytest.raises(Conflict):
            action()
    other = location(commands, "other-location", "Drawer")
    with pytest.raises(Conflict, match="inventory_location_exists"):
        commands.rename_location("reserved-name", other, "cupboard", 1)
    assert queries(commands).history(product, limit=25, cursor=None).movements == before.movements
    commands.restore_location("restore", target, 2)
    commands.transfer("usable", product, PANTRY, target, M("1"))
    assert not current(store, target).archived


@pytest.mark.parametrize(
    "quantity,denied,mode,state",
    [
        (None, False, MaterialRecording.REVIEW_ON_COMPLETION, "pending_recording"),
        ("1", True, MaterialRecording.REVIEW_ON_COMPLETION, "pending_authorization"),
        ("1", False, MaterialRecording.REVIEW_ON_COMPLETION, "pending_regularization"),
        ("1", False, MaterialRecording.SEPARATE, "pending_processing"),
    ],
)
def test_every_pending_material_state_blocks_an_empty_bound_location(
    tmp_path, quantity, denied, mode, state
):
    """C02: pending usage remains independent of current stock/effect totals."""
    tasks, store, commands, product, target = scene(tmp_path)
    commands.transfer("empty", product, target, PANTRY, M("2"))
    with store.read() as unit:
        reference = unit.inventory.location_bindings("home", product)[target]
        member = unit.members.by_user("home", "ha_admin")
    tasks = replace(
        tasks,
        inventory_factory=lambda unit: InventorySettlement(
            unit.inventory, Clock(), commands.identifiers
        ),
    )
    _, occurrence = resource(
        tasks.create(
            "work",
            CreateTask(
                TaskContent("Use cupboard flour"),
                materials=(MaterialSelection(reference, M("1")),),
                overrides=TaskOverrides(material_recording=mode),
            ),
        )
    )
    with store.read() as unit:
        line = unit.tasks.occurrence("home", occurrence).definition_snapshot.materials[0]
    if denied:
        with store.write() as unit:
            unit.members.save(
                replace(
                    member,
                    exceptions=(PermissionRule(Permission.TASKS_MATERIAL_USE, False),),
                    revision=member.revision + 1,
                ),
                member.revision,
            )
    usages = None if quantity is None else (MaterialUsage(line.line_id, M(quantity)),)
    result = tasks.complete(
        "complete", CompleteTask(occurrence, 1, (member.member_id,), 95, usages)
    )
    assert result.result.decode()["materials"][0]["state"] == state
    with store.read() as unit:
        assert unit.task_materials.has_pending_location("home", target)
        assert not unit.task_materials.has_pending_location("other-home", target)
        assert not unit.task_materials.has_pending_location("home", "other-location")
        usage = unit.inventory.location_usage("home", target)
        assert not usage.recorded_stock and not usage.pending_effects
    with pytest.raises(Conflict, match="inventory_location_pending_effects"):
        commands.archive_location("archive", target, 1)
    assert current(store, target).revision == 1


def test_archived_binding_preserves_work_and_requires_restore_for_new_consumption(tmp_path):
    """C02/C05: an existing task may finish, but archived stock is never posted."""
    tasks, store, commands, product, target = scene(tmp_path)
    commands.transfer("empty", product, target, PANTRY, M("2"))
    with store.read() as unit:
        reference = unit.inventory.location_bindings("home", product)[target]
        member = unit.members.by_user("home", "ha_admin")
    tasks = replace(
        tasks,
        inventory_factory=lambda unit: InventorySettlement(
            unit.inventory, Clock(), commands.identifiers
        ),
    )
    _, occurrence = resource(
        tasks.create(
            "work",
            CreateTask(
                TaskContent("Earlier plan"), materials=(MaterialSelection(reference, M("1")),)
            ),
        )
    )
    with store.read() as unit:
        line = unit.tasks.occurrence("home", occurrence).definition_snapshot.materials[0]
    commands.archive_location("archive", target, 1)
    result = tasks.complete(
        "done",
        CompleteTask(
            occurrence, 1, (member.member_id,), 95, (MaterialUsage(line.line_id, M("1")),)
        ),
    )
    outcome = result.result.decode()["materials"][0]
    assert (
        outcome["pending_reason"] == "inventory_location_archived"
        and outcome["movement_id"] is None
    )
    assert "restore the archived location" in outcome["action_required"]
    assert (
        tasks.complete(
            "done",
            CompleteTask(
                occurrence, 1, (member.member_id,), 95, (MaterialUsage(line.line_id, M("1")),)
            ),
        )
        == result
    )
    with pytest.raises(InvalidInput, match="invalid_material_reference"):
        tasks.create(
            "new-plan",
            CreateTask(TaskContent("New plan"), materials=(MaterialSelection(reference, M("1")),)),
        )
    reopened = SQLiteDatabase(store.path, store.installation)
    reopened.initialize(require_existing=True)
    assert current(reopened, target).archived
    commands.restore_location("restore", target, 2)
    commands.transfer("stock-for-review", product, PANTRY, target, M("1"))


def test_real_archive_transfer_effect_and_edit_races_never_strand_stock(tmp_path):
    """C04: independent writers choose one valid stock/lifecycle outcome."""
    _, store, commands = setup(tmp_path)
    product = commands.register("product", "Flour", BaseUnit.GRAM).result.decode()["product_id"]
    target = location(commands)
    commands.intake("stock", product, M("1"))
    other = replace(commands, transactions=SQLiteDatabase(store.path, store.installation))
    results = race(
        lambda: commands.archive_location("archive", target, 1),
        lambda: other.transfer("transfer", product, PANTRY, target, M("1")),
    )
    assert sum(isinstance(item, Receipt) for item in results) == 1
    if current(store, target).archived:
        assert results[1] == "inventory_location_archived"
        assert len(queries(commands).history(product, limit=25, cursor=None).movements) == 1
    else:
        assert results[0] == "inventory_location_not_empty"
        assert len(queries(commands).history(product, limit=25, cursor=None).movements) == 3
    editable = location(commands, "editable", "Drawer")
    edits = race(
        lambda: commands.rename_location("one", editable, "One", 1),
        lambda: other.rename_location("two", editable, "Two", 1),
    )
    assert edits.count("revision_conflict") == 1 and current(store, editable).revision == 2
    effect_target = location(commands, "effect-target", "Shelf")
    # Establish a real catalog binding and empty it before racing a direct demand.
    if current(store, target).archived:
        commands.restore_location("restore-race", target, 2)
    else:
        commands.transfer("empty-race", product, target, PANTRY, M("1"))
    commands.transfer("bind-shelf", product, PANTRY, effect_target, M("1"))
    commands.transfer("empty-shelf", product, effect_target, PANTRY, M("1"))
    with store.read() as unit:
        reference = unit.inventory.location_bindings("home", product)[effect_target]
    effects = race(
        lambda: commands.archive_location("archive-shelf", effect_target, 1),
        lambda: other.commit_effect("demand-shelf", EffectKind.DEMAND, reference, M("1")),
    )
    if current(store, effect_target).archived:
        assert effects[1] == "inventory_location_archived"
    else:
        assert effects[0] == "inventory_location_pending_effects"


def test_failure_after_location_update_rolls_back_state_and_all_evidence(tmp_path, monkeypatch):
    """C05: an interrupted metadata write leaves no state, receipt or audit effect."""
    _, store, commands = setup(tmp_path)
    target = location(commands)
    before, counts = current(store, target), command_evidence(store)
    save = SQLiteInventory.save_location
    with monkeypatch.context() as patch:

        def fail(stock, home, value, revision):
            save(stock, home, value, revision)
            raise StorageFailure("injected_location_failure")

        patch.setattr(SQLiteInventory, "save_location", fail)
        with pytest.raises(StorageFailure, match="injected_location_failure"):
            commands.rename_location("rename", target, "Kitchen cupboard", 1)
    assert current(store, target) == before and command_evidence(store) == counts
    with pytest.raises(NotFound, match="operation_missing"):
        commands.original(CatalogAction.RENAME_LOCATION, "rename", commands.actor.current())
    renamed = commands.rename_location("rename", target, "Kitchen cupboard", 1)
    assert commands.rename_location("rename", target, "Kitchen cupboard", 1) == renamed
    with pytest.raises(Conflict, match="inventory_location_unchanged"):
        commands.rename_location("unchanged", target, "Kitchen cupboard", 2)
    assert current(store, target).revision == 2
    with store.write() as unit:
        with pytest.raises(Conflict, match="revision_conflict"):
            unit.inventory.save_location(
                "other-home", replace(before, name="Foreign", revision=2), 1
            )
    assert current(store, target).name == "Kitchen cupboard"


def test_archived_names_still_count_towards_the_complete_location_capacity(tmp_path):
    """C02: archive retains the identity/name and does not create catalog space."""
    _, store, commands = setup(tmp_path)
    targets = [location(commands, f"location-{i}", f"Location {i}") for i in range(32)]
    commands.archive_location("archive", targets[0], 1)
    with pytest.raises(Conflict, match="inventory_location_limit"):
        location(commands, "over-capacity", "Another location")
    with store.read() as unit:
        assert len(unit.inventory.locations("home")) == 32
    commands.restore_location("restore", targets[0], 2)
    assert not current(store, targets[0]).archived


def test_snapshot_validation_rejects_malformed_or_live_archived_locations(tmp_path):
    """C06: an imported archived row cannot conceal stock or pending effects."""
    _, store, commands, product, target = scene(tmp_path)
    with closing(sqlite3.connect(store.path, autocommit=True)) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA ignore_check_constraints=ON")
        db.execute("UPDATE inventory_locations SET archived=1 WHERE location_id=?", (target,))
        with pytest.raises(StorageFailure, match="invalid_archived_inventory_location"):
            verify_inventory_locations(db)
        db.execute("UPDATE inventory_locations SET archived=0 WHERE location_id=?", (target,))
        commands.transfer("empty", product, target, PANTRY, M("2"))
        with store.read() as unit:
            reference = unit.inventory.location_bindings("home", product)[target]
        commands.commit_effect("direct", EffectKind.DEMAND, reference, M("1"))
        db.execute("UPDATE inventory_locations SET archived=1 WHERE location_id=?", (target,))
        with pytest.raises(StorageFailure, match="invalid_archived_inventory_location"):
            verify_inventory_locations(db)
        for sql in (
            "UPDATE inventory_locations SET archived=2",
            "UPDATE inventory_locations SET archived=0,revision=0",
        ):
            db.execute(sql)
            with pytest.raises(StorageFailure, match="invalid_inventory_locations"):
                verify_inventory_locations(db)
        db.execute("UPDATE inventory_locations SET archived=0,revision=1")
        verify_inventory_locations(db)


@pytest.mark.parametrize(
    "version,fixture",
    [
        (20, "v20-inventory-history-source.sql"),
        (30, "v30-purchase-store-source.sql"),
        (37, "v37-storage-location-source.sql"),
    ],
)
def test_genuine_old_sql_migration_is_atomic_and_preserves_every_original_row(
    tmp_path, monkeypatch, version, fixture
):
    """C06: real schema20/30/37 inputs preserve balances, linked transfers and receipts."""
    source = Path(__file__).parents[1] / "fixtures/sqlite" / fixture
    path = tmp_path / "domus.sqlite3"
    with closing(sqlite3.connect(path, autocommit=True)) as db:
        db.executescript(source.read_text())
        assert db.execute("PRAGMA user_version").fetchone() == (version,)
        installation = Installation(
            *db.execute("SELECT instance_id,channel FROM installation").fetchone()
        )
        tables = [
            row[0]
            for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        original = {name: db.execute('SELECT * FROM "' + name + '"').fetchall() for name in tables}
        if version >= 30:
            assert original["inventory_transfers"]
        if version == 37:
            manifest = json.loads(source.with_suffix(".provenance.json").read_text())
            assert (
                hashlib.sha256(source.read_bytes()).hexdigest() == manifest["outputFixtureSHA256"]
            )
            assert (
                manifest["installedRuntimeFilesMatched"] == 250 and manifest["actualWheelChecked"]
            )
            assert (
                len(original["inventory_locations"]) == 3
                and len(original["inventory_transfers"]) == 4
            )
    path.chmod(0o600)
    store = SQLiteDatabase(path, installation)
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        assert _verify_database(db, store, previous=True) == version
    before = path.read_bytes()
    with monkeypatch.context() as patch:
        patch.setattr(
            storage,
            "LOCATION_LIFECYCLE_STATEMENTS",
            (*storage.LOCATION_LIFECYCLE_STATEMENTS, "bad SQL"),
        )
        with pytest.raises(StorageFailure):
            store.initialize(require_existing=True)
    assert path.read_bytes() == before
    store.initialize(require_existing=True)
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("PRAGMA user_version").fetchone() == (38,)
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        for table, rows in original.items():
            actual = db.execute('SELECT * FROM "' + table + '"').fetchall()
            if rows:
                assert [row[: len(rows[0])] for row in actual] == rows
            else:
                assert actual == []
        for revision, archived in db.execute("SELECT revision,archived FROM inventory_locations"):
            assert (revision, archived) == (1, 0)
    if version == 37:
        actor = Actor()
        actor.human = HumanIdentity("ha_admin", True, True, False)
        commands = InventoryCommands(store, actor, Clock(), SecureIdentifiers())
        receipt = commands.original(
            CatalogAction.TRANSFER, "v37-location-transfer", actor.current()
        )
        assert receipt.operation_id == manifest["originalTransferOperation"]
        target = manifest["locations"]["cupboard"]
        commands.rename_location("after-migration", target, "Renamed source cupboard", 1)
        assert (
            commands.transfer(
                "v37-location-transfer", manifest["productID"], PANTRY, target, M("3.000001")
            )
            == receipt
        )


def test_restart_and_activated_restore_preserve_archived_identity_and_historical_recovery(tmp_path):
    """C05/C06: original recovery never reenacts a rolled-away restoration."""
    root = tmp_path / "owned"
    root.mkdir(mode=0o700)
    _, store, commands = setup(root)
    identity_at(root, store.installation)
    target = location(commands)
    commands.archive_location("archive", target, 1)
    archive, prepared = tmp_path / "snapshots", tmp_path / "prepared"
    checkpoint = SQLiteSnapshots(store, archive, store.installation, Clock()).create(
        "archived-location"
    )
    later = commands.restore_location("later-restore", target, 2)
    commands.rename_location("later-name", target, "Later name", 3)
    reopened = replace(commands, transactions=SQLiteDatabase(store.path, store.installation))
    assert reopened.restore_location("later-restore", target, 2) == later
    SQLiteRestorations(store, archive, prepared, store.installation, Clock(), checkpoint).prepare(
        "restore"
    )
    assert (
        SQLiteActivation(root, store.installation, Clock(), prepared).activate().state == "active"
    )
    owned = open_storage(root, "edge")
    try:
        restored = replace(commands, transactions=owned.database)
        before = current(owned.database, target)
        assert before.name == "Cupboard" and before.archived and before.revision == 2
        historical = restored.restore_location("later-restore", target, 2)
        assert (
            historical.historical
            and historical.result == later.result
            and historical.operation_id == later.operation_id
        )
        assert current(owned.database, target) == before
        restored.restore_location("current-restore", target, 2)
        assert not current(owned.database, target).archived
    finally:
        owned.close()
